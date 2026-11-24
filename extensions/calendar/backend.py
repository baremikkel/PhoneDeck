"""Kalender: events from up to three ICS links (Google, Outlook, iCloud …).

The links are secret addresses, so they are stored as secret settings (never sent back to
a browser) and only ever fetched – nothing is written to the calendars.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from .ical import events_between, local_zone

POLL = 10 * 60
COLOURS = ["var(--cpu)", "var(--claude)", "var(--net)"]
MAX_BYTES = 8 * 1024 * 1024


def _fetch(url: str) -> str:
    url = url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not url.startswith("https://"):
        raise ValueError("linket skal starte med https:// eller webcal://")
    req = urllib.request.Request(url, headers={"User-Agent": "PhoneDeck"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read(MAX_BYTES).decode("utf-8", "replace")


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.texts: dict[int, str] = {}   # calendar number -> last good .ics text
        self.errors: dict[int, str] = {}
        self.fetched = 0.0
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def settings_changed(self):
        self._wake.set()

    def _loop(self):
        while not self.ctx.stopped.is_set():
            s = self.ctx.settings()
            for i in (1, 2, 3):
                url = s.get(f"url{i}") or ""
                if not url:
                    self.texts.pop(i, None); self.errors.pop(i, None)
                    continue
                try:
                    self.texts[i] = _fetch(url)
                    self.errors.pop(i, None)
                except (urllib.error.URLError, OSError, ValueError) as e:
                    # never show the (secret) link itself in an error
                    self.errors[i] = str(getattr(e, "reason", None) or getattr(e, "code", None) or e).split("http")[0][:80]
            self.fetched = time.time()
            self._wake.wait(self.ctx.number("poll_min", POLL / 60) * 60)
            self._wake.clear()

    def state(self):
        s = self.ctx.settings()
        if not any(s.get(f"url{i}") for i in (1, 2, 3)):
            return {"setup": True}
        now = datetime.now().astimezone()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days = int(s.get("days") or 7)
        end = start + timedelta(days=days)
        out = []
        for i, text in sorted(self.texts.items()):
            try:
                evs = events_between(text, start, end, local_zone())
            except Exception as e:  # a broken file must not stop the dashboard
                self.errors[i] = f"kunne ikke læse kalenderen ({e.__class__.__name__})"
                continue
            name = s.get(f"name{i}") or f"Kalender {i}"
            for ev in evs:
                out.append({"title": ev["title"][:120], "location": ev["location"][:120], "cal": name,
                            "colour": COLOURS[i - 1], "all_day": ev["all_day"],
                            "start": ev["start"].timestamp(), "end": ev["end"].timestamp()})
        out.sort(key=lambda e: (e["start"], not e["all_day"]))
        return {"events": out[:200], "days": days, "errors": [f"{s.get(f'name{i}') or f'Kalender {i}'}: {m}" for i, m in self.errors.items()],
                "fetched": self.fetched}

    def action(self, name, body):
        if name == "forget":
            # secret fields can't be emptied through the form (empty = keep), so do it here
            self.ctx.clear_settings(["url1", "url2", "url3"])
            self.texts.clear(); self.errors.clear()
            return {}
        raise ValueError(f"ukendt handling: {name}")

    def _summary(self, text: str) -> str:
        """'42 begivenheder, næste 3. dec.' – so an empty-looking calendar can be told apart
        from one that didn't download (e.g. a link that gives an empty or HTML page)."""
        if "BEGIN:VCALENDAR" not in text[:2000].upper():
            return "linket gav ikke en kalender (ICS) – tjek at det er den hemmelige iCal-adresse"
        count = text.upper().count("BEGIN:VEVENT")
        now = datetime.now().astimezone()
        try:
            nxt = next(iter(events_between(text, now, now + timedelta(days=366), local_zone())), None)
        except Exception:  # noqa: BLE001
            nxt = None
        when = f"næste {nxt['start'].day}/{nxt['start'].month}" if nxt else "ingen det næste år"
        return f"{count} begivenhed{'er' if count != 1 else ''}, {when}"

    def info(self):
        n = len(self.texts)
        if self.errors:
            return {"status": "⚠ " + "; ".join(self.errors.values())}
        if not n:
            return {"status": "Ingen kalender sat op endnu"}
        s = self.ctx.settings()
        parts = [f"{s.get(f'name{i}') or f'Kalender {i}'}: {self._summary(t)}" for i, t in sorted(self.texts.items())]
        return {"status": "✓ " + " · ".join(parts)}
