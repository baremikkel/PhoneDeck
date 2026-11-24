"""Real plan usage (5-hour and weekly limits) for your Claude subscription.

Two sources; the newest numbers win:

1. Claude Code's status line (scripts/claude-statusline.py). Claude Code itself passes
   the limits to it after each reply; the script saves them to a file we read. No token
   involved, works on Windows and Linux, but only updates while Claude Code is in use.

2. Opt-in (Indstillinger → "Brug mit Claude Code-login"). Reads the access token
Claude Code keeps in ~/.claude/.credentials.json and asks Anthropic how much of
the plan's limits are used – the same numbers Claude Code's /usage shows.

* The token is only ever sent to api.anthropic.com, never logged or shown.
* We never refresh or change the token – Claude Code does that itself when you
  use it. If it has expired we simply say so.
* The endpoint is not officially documented and may change.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from phonedeck import paths

CREDENTIALS = os.path.join(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")), ".credentials.json")
URL = "https://api.anthropic.com/api/oauth/usage"
POLL = 120  # seconds
CACHE = paths.cache("claude_plan.json")  # percentages only, never the token
STATUSLINE = paths.cache("claude_ratelimits.json")  # written by scripts/claude-statusline.py


def _window(d) -> dict | None:
    if not isinstance(d, dict) or d.get("utilization") is None:
        return None
    return {"used_pct": float(d["utilization"]), "resets_at": d.get("resets_at")}


def _statusline_file() -> dict:
    try:
        with open(STATUSLINE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def statusline_seen() -> float | None:
    """When Claude Code last ran our status line (with or without limits), if ever."""
    d = _statusline_file()
    return d.get("seen") or d.get("updated") or None


def read_statusline() -> dict | None:
    """Limits saved by the Claude Code status line, in the same shape as _fetch()."""
    d = _statusline_file()
    if not d:
        return None

    def win(w):
        if not isinstance(w, dict) or w.get("used_pct") is None:
            return None
        at = w.get("resets_at")  # epoch seconds -> ISO, like the API answers
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)) if isinstance(at, (int, float)) else None
        return {"used_pct": float(w["used_pct"]), "resets_at": iso}

    out = {"five_hour": win(d.get("five_hour")), "seven_day": win(d.get("seven_day")),
           "updated": d.get("updated") or 0, "source": "statusline"}
    return out if out["five_hour"] or out["seven_day"] else None


class ClaudePlan:
    def __init__(self, use_login, stopped, poll=lambda: POLL):
        self.use_login = use_login  # callable -> bool (extension setting)
        self.poll = lambda: max(60.0, float(poll()))  # never ask Anthropic more than once a minute
        self.stopped = stopped
        self._lock = threading.Lock()
        self.data: dict = {}
        self._wake = threading.Event()
        self._backoff = 0
        # Remember the last answer across restarts so a restart doesn't ask Anthropic again
        try:
            with open(CACHE, encoding="utf-8") as f:
                cached = json.load(f)
            self.data = cached
            age = time.time() - cached.get("updated", 0)
            if age < POLL:
                self._backoff = int(POLL - age)
        except (OSError, ValueError):
            pass
        threading.Thread(target=self._loop, daemon=True).start()

    def _save(self, data: dict) -> None:
        try:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass

    def refresh_soon(self) -> None:
        self._wake.set()

    def _fetch(self) -> dict:
        try:
            with open(CREDENTIALS, encoding="utf-8") as f:
                oauth = json.load(f).get("claudeAiOauth") or {}
        except (OSError, ValueError):
            return {"error": "Fandt ikke Claude Code-login"}
        token = oauth.get("accessToken")
        if not token:
            return {"error": "Ikke logget ind i Claude Code"}
        if (oauth.get("expiresAt") or 0) / 1000 < time.time():
            return {"error": "Login udløbet – åbn Claude Code (VS Code eller terminal) for at forny"}
        req = urllib.request.Request(URL, headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "PhoneDeck",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited: wait (Retry-After, else 10 min) before asking again
                try:
                    self._backoff = max(60, int(e.headers.get("Retry-After") or 600))
                except ValueError:
                    self._backoff = 600
                return {"error": "Anthropic beder os vente – prøver igen senere"}
            return {"error": f"Anthropic svarede {e.code}"}
        return {
            "plan": oauth.get("subscriptionType"),
            "five_hour": _window(d.get("five_hour")),
            "seven_day": _window(d.get("seven_day")),
            "updated": time.time(),
        }

    def _loop(self) -> None:
        if self._backoff:  # cached numbers are still fresh – don't ask again yet
            self._wake.wait(self._backoff)
            self._wake.clear()
            self._backoff = 0
        while not self.stopped.is_set():
            if self.use_login():
                try:
                    data = self._fetch()
                except Exception as e:
                    data = {"error": str(e)}
                if "error" in data and self.data.get("five_hour"):
                    data = dict(self.data, error=data["error"])  # keep last good numbers
                elif "error" not in data:
                    self._save(data)
                with self._lock:
                    self.data = data
            wait, self._backoff = max(self.poll(), self._backoff), 0
            self._wake.wait(wait)
            self._wake.clear()

    def state(self) -> dict | None:
        """The newest numbers from the status line or the login (if turned on)."""
        login = None
        if self.use_login():
            with self._lock:
                login = dict(self.data, source="login")
        sl = read_statusline()
        if sl and login and login.get("plan"):
            sl["plan"] = login["plan"]
        good = [d for d in (sl, login) if d and d.get("five_hour")]
        if good:
            best = max(good, key=lambda d: d.get("updated") or 0)
            if best is sl:
                best.pop("error", None)  # the status line is fine even when the login isn't
            return best
        return login  # None, or the login's error
