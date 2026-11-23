"""Real plan usage (5-hour and weekly limits) for your Claude subscription.

Opt-in (Indstillinger → "Brug mit Claude Code-login"). Reads the access token
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

CREDENTIALS = os.path.join(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")), ".credentials.json")
URL = "https://api.anthropic.com/api/oauth/usage"
POLL = 120  # seconds


def _window(d) -> dict | None:
    if not isinstance(d, dict) or d.get("utilization") is None:
        return None
    return {"used_pct": float(d["utilization"]), "resets_at": d.get("resets_at")}


class ClaudePlan:
    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.data: dict = {}
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def refresh_soon(self) -> None:
        self._wake.set()

    def _fetch(self) -> dict:
        try:
            with open(CREDENTIALS) as f:
                oauth = json.load(f).get("claudeAiOauth") or {}
        except (OSError, ValueError):
            return {"error": "Fandt ikke Claude Code-login"}
        token = oauth.get("accessToken")
        if not token:
            return {"error": "Ikke logget ind i Claude Code"}
        if (oauth.get("expiresAt") or 0) / 1000 < time.time():
            return {"error": "Login udløbet – åbn Claude Code for at forny"}
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
        while True:
            if self.settings.get("claude", "use_login"):
                try:
                    data = self._fetch()
                except Exception as e:
                    data = {"error": str(e)}
                if "error" in data and self.data.get("five_hour"):
                    data = dict(self.data, error=data["error"])  # keep last good numbers
                with self._lock:
                    self.data = data
            else:
                with self._lock:
                    self.data = {}
            wait, self._backoff = max(POLL, getattr(self, "_backoff", 0)), 0
            self._wake.wait(wait)
            self._wake.clear()

    def state(self) -> dict | None:
        if not self.settings.get("claude", "use_login"):
            return None
        with self._lock:
            return dict(self.data)
