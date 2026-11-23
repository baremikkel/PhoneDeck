"""GitHub contribution calendar (the green heat map) for one user.

Reads the public calendar at ``github.com/users/<user>/contributions`` – no
token needed. Private contributions are included only if "Private
contributions" is switched on in the GitHub profile settings.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.request
from datetime import date

REFRESH = 30 * 60  # seconds

_CELL = re.compile(r'data-date="(\d{4}-\d{2}-\d{2})"\s+id="([^"]+)"[^>]*?data-level="(\d)"')
_TIP = re.compile(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>')
_COUNT = re.compile(r"^(\d[\d,]*) contribution")


def fetch(user: str) -> list[dict]:
    req = urllib.request.Request(f"https://github.com/users/{user}/contributions",
                                 headers={"User-Agent": "PhoneDeck"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", "replace")
    counts = {}
    for cell_id, text in _TIP.findall(html):
        m = _COUNT.match(text.strip())
        counts[cell_id] = int(m.group(1).replace(",", "")) if m else 0
    days = [{"date": d, "count": counts.get(cid, 0), "level": int(lvl)}
            for d, cid, lvl in _CELL.findall(html)]
    days.sort(key=lambda x: x["date"])
    return days


def streak(days: list[dict]) -> int:
    """Consecutive days with contributions, ending today (or yesterday)."""
    n = 0
    today = date.today().isoformat()
    for i, d in enumerate(reversed(days)):
        if d["count"] > 0:
            n += 1
        elif i == 0 and d["date"] == today:
            continue  # nothing yet today doesn't break the streak
        else:
            break
    return n


class GitHub:
    def __init__(self, user: str | None, stopped=None):
        self.stopped = stopped or threading.Event()
        self.user = user
        self.data: dict | None = None if user else {"error": "Sæt dit GitHub-brugernavn under Indstillinger"}
        self._lock = threading.Lock()
        if user:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self.stopped.is_set():
            try:
                days = fetch(self.user)
                data = {
                    "user": self.user,
                    "days": days,
                    "total": sum(d["count"] for d in days),
                    "today": days[-1]["count"] if days else 0,
                    "streak": streak(days),
                    "best": max((d["count"] for d in days), default=0),
                    "updated": time.time(),
                }
                wait = REFRESH
            except Exception as e:
                data = dict(self.data or {}, error=str(e))
                wait = 120  # retry sooner after a failure
            with self._lock:
                self.data = data
            self.stopped.wait(wait)

    def state(self) -> dict | None:
        with self._lock:
            return self.data
