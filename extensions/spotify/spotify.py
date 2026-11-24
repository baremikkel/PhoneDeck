"""Spotify Web API – the play queue ("next song"), liking the current song, your
playlists, search and "add to queue".

MPRIS has no queue for Spotify, so we ask Spotify itself. Uses your own Spotify
developer app (Client ID) with the PKCE login flow – no client secret needed.
Adding to the queue and starting a playlist need Spotify Premium.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_PATH = os.path.expanduser("~/.config/phonedeck/spotify_token.json")
import re

SCOPES = ("user-read-playback-state user-read-currently-playing user-modify-playback-state "
          "user-library-read user-library-modify playlist-read-private playlist-read-collaborative")
URI_RE = re.compile(r"^spotify:(track|episode|playlist|album):[A-Za-z0-9]{22}$")
API = "https://api.spotify.com/v1"
POLL = 10  # seconds between queue refreshes


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _track(t: dict | None) -> dict | None:
    if not t:
        return None
    images = (t.get("album") or {}).get("images") or (t.get("show") or {}).get("images") or []
    small = min(images, key=lambda i: i.get("width") or 9999)["url"] if images else None
    artists = ", ".join(a["name"] for a in t.get("artists", [])) or (t.get("show") or {}).get("name", "")
    return {"title": t.get("name"), "artist": artists, "art": small, "uri": t.get("uri"), "id": t.get("id"),
            "duration": (t.get("duration_ms") or 0) / 1000}


class Spotify:
    def __init__(self, client_id, port: int, stopped):
        self.client_id = client_id  # callable -> str (extension setting)
        self.stopped = stopped
        # the old address is kept so Spotify apps set up before extensions keep working
        self.redirect_uri = f"http://127.0.0.1:{port}/spotify/callback"
        self._lock = threading.Lock()
        self._pending: dict[str, str] = {}  # state -> code_verifier
        self.token: dict | None = None
        self.data: dict = {"connected": False}
        self._wake = threading.Event()
        try:
            with open(TOKEN_PATH) as f:
                self.token = json.load(f)
        except (OSError, ValueError):
            self.token = None
        threading.Thread(target=self._loop, daemon=True).start()

    # ---------- login (PKCE) ----------
    def login_url(self) -> str:
        cid = self.client_id()
        if not cid:
            raise ValueError("Indtast dit Spotify Client ID først")
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        with self._lock:
            self._pending = {state: verifier}  # only the latest attempt is valid
        return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
            "client_id": cid, "response_type": "code", "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256", "code_challenge": challenge,
            "scope": SCOPES, "state": state,
        })

    def callback(self, code: str, state: str) -> None:
        with self._lock:
            verifier = self._pending.pop(state, None)
        if not verifier:
            raise ValueError("Ugyldigt eller udløbet login – prøv igen")
        tok = _post_form("https://accounts.spotify.com/api/token", {
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
            "client_id": self.client_id(), "code_verifier": verifier,
        })
        self._save_token(tok)
        self._wake.set()

    def disconnect(self) -> None:
        with self._lock:
            self.token = None
            self.data = {"connected": False}
        try:
            os.remove(TOKEN_PATH)
        except OSError:
            pass

    def _save_token(self, tok: dict) -> None:
        tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
        if self.token and "refresh_token" not in tok:
            tok["refresh_token"] = self.token.get("refresh_token")
        with self._lock:
            self.token = tok
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(tok, f)

    def _access_token(self) -> str | None:
        tok = self.token
        if not tok:
            return None
        if time.time() >= tok.get("expires_at", 0):
            new = _post_form("https://accounts.spotify.com/api/token", {
                "grant_type": "refresh_token", "refresh_token": tok.get("refresh_token", ""),
                "client_id": self.client_id(),
            })
            self._save_token(new)
        return self.token["access_token"]

    def missing_scopes(self) -> bool:
        """True when the saved login is from before like/search/queue existed."""
        granted = set((self.token or {}).get("scope", "").split())
        return bool(self.token) and not set(SCOPES.split()) <= granted

    # ---------- Web API ----------
    def _api(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        access = self._access_token()
        if not access:
            raise ValueError("Spotify er ikke forbundet")
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("PUT", "POST") else None)
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            msg = {401: "Spotify-login udløbet – forbind igen",
                   403: "Spotify tillod det ikke (kræver Premium, eller forbind Spotify igen)",
                   404: "Ingen aktiv Spotify-afspiller – start afspilning først",
                   429: "Spotify: for mange forespørgsler – vent lidt"}.get(e.code, f"Spotify svarede {e.code}")
            raise ValueError(msg) from None
        return json.loads(raw) if raw else {}

    def _need_scopes(self):
        if self.missing_scopes():
            raise ValueError("Forbind Spotify igen under Indstillinger for at bruge det her")

    def like_toggle(self) -> dict:
        self._need_scopes()
        cur = (self.data.get("current") or {})
        tid = cur.get("id")
        if not tid or not (cur.get("uri") or "").startswith("spotify:track:"):
            raise ValueError("Ingen sang at like")
        liked = self._api("GET", "/me/tracks/contains", {"ids": tid})[0]
        self._api("DELETE" if liked else "PUT", "/me/tracks", {"ids": tid})
        with self._lock:
            self.data = dict(self.data, liked=not liked)
        return {"liked": not liked}

    def search(self, q: str) -> dict:
        q = (q or "").strip()[:100]
        if not q:
            return {"tracks": []}
        r = self._api("GET", "/search", {"q": q, "type": "track", "limit": 10})
        return {"tracks": [t for t in (_track(x) for x in (r.get("tracks") or {}).get("items") or []) if t]}

    def playlists(self) -> dict:
        self._need_scopes()
        r = self._api("GET", "/me/playlists", {"limit": 50})
        out = []
        for p in r.get("items") or []:
            if not p:
                continue
            imgs = p.get("images") or []
            out.append({"name": p.get("name"), "uri": p.get("uri"),
                        "owner": (p.get("owner") or {}).get("display_name", ""),
                        "count": ((p.get("tracks") or p.get("items") or {}) or {}).get("total"),
                        "art": min(imgs, key=lambda i: i.get("width") or 9999)["url"] if imgs else None})
        return {"playlists": out}

    def add_to_queue(self, uri: str) -> dict:
        self._need_scopes()
        if not URI_RE.match(uri or "") or not uri.startswith(("spotify:track:", "spotify:episode:")):
            raise ValueError("ugyldig sang")
        self._api("POST", "/me/player/queue", {"uri": uri})
        self.refresh_soon()
        return {}

    def play_context(self, uri: str) -> dict:
        self._need_scopes()
        if not URI_RE.match(uri or "") or not uri.startswith(("spotify:playlist:", "spotify:album:")):
            raise ValueError("ugyldig playliste")
        self._api("PUT", "/me/player/play", body={"context_uri": uri})
        self.refresh_soon()
        return {}

    # ---------- queue ----------
    def refresh_soon(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self.stopped.is_set():
            if self.token:
                try:
                    access = self._access_token()
                    req = urllib.request.Request("https://api.spotify.com/v1/me/player/queue",
                                                 headers={"Authorization": f"Bearer {access}"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        raw = r.read()
                    q = json.loads(raw) if raw else {}
                    queue = [_track(t) for t in (q.get("queue") or [])[:20]]
                    queue = [t for t in queue if t]
                    current = _track(q.get("currently_playing"))
                    data = {"connected": True, "current": current,
                            "next": queue[0] if queue else None, "queue": queue,
                            "reconnect": self.missing_scopes()}
                    # is the current song in "Liked Songs"? (only asked when the song changes)
                    old = self.data.get("current") or {}
                    if current and current.get("id") and not data["reconnect"]:
                        if old.get("id") == current["id"] and "liked" in self.data:
                            data["liked"] = self.data["liked"]
                        elif (current.get("uri") or "").startswith("spotify:track:"):
                            try:
                                data["liked"] = bool(self._api("GET", "/me/tracks/contains", {"ids": current["id"]})[0])
                            except (ValueError, IndexError, TypeError):
                                pass
                except urllib.error.HTTPError as e:
                    if e.code in (400, 401):
                        self.disconnect()
                        data = {"connected": False, "error": "Spotify-login udløbet – forbind igen"}
                    else:
                        data = dict(self.data, error=f"Spotify svarede {e.code}")
                except Exception as e:
                    data = dict(self.data, error=str(e))
                with self._lock:
                    self.data = data
            self._wake.wait(POLL)
            self._wake.clear()

    def state(self) -> dict:
        with self._lock:
            d = dict(self.data)
        d["configured"] = bool(self.client_id())
        return d
