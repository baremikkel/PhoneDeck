"""Music: now playing via MPRIS, playback control, player volume and visualizer."""

import json
import sys
import threading
import time
import urllib.parse
import urllib.request

if sys.platform == "win32":
    from .media_win import Media
else:
    from .media import Media
from .visualizer import Visualizer


# the visualizer takes the colour of the program that is playing (MPRIS name contains the key)
APP_COLOURS = [
    ("spotif", "#1ed760"),      # Spotify, Spotifast, spotifyd
    ("firefox", "#ff7139"),
    ("chrom", "#4c8bf5"),       # Chrome, Chromium
    ("brave", "#fb542b"),
    ("edge", "#33c3f0"),
    ("opera", "#ff1b2d"),
    ("vivaldi", "#ef3939"),
    ("vlc", "#ff8800"),
    ("mpv", "#b05ee6"),
    ("rhythmbox", "#e6b422"),
    ("strawberry", "#e8455a"),
    ("tidal", "#e8e8e8"),
    ("deezer", "#a238ff"),
    ("youtube", "#ff3b3b"),
    ("discord", "#5865f2"),
    ("plexamp", "#ebaf00"),
    ("lollypop", "#3d9ae8"),
]


def app_colour(player: str | None) -> str | None:
    p = (player or "").lower()
    return next((c for key, c in APP_COLOURS if key in p), None)


def _spotify_image(url: str) -> bool:
    u = urllib.parse.urlsplit(url or "")
    return u.scheme == "https" and (u.hostname or "").endswith(("scdn.co", "spotifycdn.com"))


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.media = Media()
        self.viz = Visualizer(lambda: (ctx.number("viz_bands", 36), ctx.number("viz_range", 36),
                                       ctx.number("viz_fps", 30)))
        self._media_state = None
        self._sp_art: tuple[str, bytes, str] | None = None  # (url, bytes, type) of the Spotify cover
        self._sp_art_lock = threading.Lock()
        # only show bars while the player is actually playing (not Discord, system sounds …)
        self.viz.gate = lambda: (self._media_state or {}).get("status") == "Playing"

    def _spotify(self):
        """The Spotify extension's client, when it is set up and connected."""
        sp = getattr(self.ctx.other("spotify"), "spotify", None)
        return sp if sp and sp.state().get("connected") else None

    def _from_spotify(self) -> dict | None:
        """Now playing from Spotify's Web API – used when the system's own media controls are
        unavailable (e.g. Windows' Smart App Control blocks the winrt package)."""
        sp = self._spotify()
        d = sp.state() if sp else {}
        cur = d.get("current")
        if not cur or not cur.get("title"):
            return None
        playing = bool(d.get("playing"))
        pos = (d.get("progress") or 0) + ((time.time() - d.get("progress_at", time.time())) if playing else 0)
        art = cur.get("art_big") or cur.get("art")
        return {
            "player": "Spotify", "status": "Playing" if playing else "Paused",
            "title": cur["title"], "artist": cur.get("artist"), "album": cur.get("album"),
            "length": cur.get("duration") or 0, "position": min(pos, cur.get("duration") or pos),
            "volume": None, "art": bool(art), "art_key": art, "via": "spotify",
        }

    def state(self):
        self.media.source = self.ctx.settings().get("source") or "spotify"
        m = self.media.state()
        if (not m or m.get("error")) and (fb := self._from_spotify()):
            m = fb
        self._media_state = m
        m = m or {}
        colour = app_colour(m.get("player")) if self.ctx.settings().get("viz_colour", "app") == "app" else None
        return {"media": self._media_state, "viz_colour": colour}

    def _spotify_art(self, url: str):
        if not _spotify_image(url):
            return None
        with self._sp_art_lock:
            if self._sp_art and self._sp_art[0] == url:
                return self._sp_art[1], self._sp_art[2]
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                data, ctype = r.read(2_000_000), r.headers.get_content_type() or "image/jpeg"
        except OSError:
            return None
        if not ctype.startswith("image/"):
            return None
        with self._sp_art_lock:
            self._sp_art = (url, data, ctype)
        return data, ctype

    def action(self, name, body):
        if name in ("playpause", "next", "previous"):
            self.media.command({"playpause": "PlayPause", "next": "Next", "previous": "Previous"}[name])
            if (self._media_state or {}).get("via") == "spotify":
                sp = self._spotify()  # show the change without waiting for the next poll
                if sp:  # Spotify's servers take a moment to see the change; ask twice
                    sp.refresh_soon(delay=0.8)
                    sp.refresh_soon(delay=2.5)
        elif name in ("volume_up", "volume_down"):
            step = (self.ctx.settings().get("volume_step") or 5) / 100
            return {"volume": self.media.set_volume(step if name == "volume_up" else -step)}
        elif name == "viz_keepalive":
            self.viz.touch()
        else:
            raise ValueError(f"ukendt handling: {name}")

    def http_get(self, path, query, req):
        if path == "art":
            m = self._media_state or {}
            art = self._spotify_art(m.get("art_key")) if m.get("via") == "spotify" else self.media.art()
            if not art:
                req.send(404, b"", "text/plain")
            else:
                req.send(200, art[0], art[1], {"Cache-Control": "max-age=86400"})
            return True
        if path == "spectrum":
            req.stream(self._spectrum())
            return True
        return False

    def _spectrum(self):
        viz = self.viz
        if not viz.available:
            yield json.dumps({"error": viz.error})
            return
        viz.touch()
        frame = -1
        while viz.alive() and not self.ctx.stopped.is_set():  # ends when the page stops pinging
            frame, bands = viz.wait(frame)
            yield json.dumps(bands, separators=(",", ":"))
