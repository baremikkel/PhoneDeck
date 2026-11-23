"""Settings edited from the browser (/settings), stored as JSON."""

from __future__ import annotations

import json
import os
import re
import threading

SETTINGS_PATH = os.path.expanduser(os.environ.get("PHONEDECK_SETTINGS", "~/.config/phonedeck/settings.json"))

DEFAULTS = {
    "claude": {"budget_5h": None, "budget_week": None, "use_login": False},
    "spotify": {"client_id": ""},
}


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(SETTINGS_PATH) as f:
                saved = json.load(f)
            for section, values in DEFAULTS.items():
                for k in values:
                    if k in saved.get(section, {}):
                        self.data[section][k] = saved[section][k]
        except (OSError, ValueError):
            pass

    def get(self, section: str, key: str):
        with self._lock:
            return self.data[section][key]

    def public(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self.data))

    def update(self, raw: dict) -> dict:
        """Validate and save. Raises ValueError with a Danish message."""
        new = self.public()
        c = raw.get("claude", {})
        for k in ("budget_5h", "budget_week"):
            if k in c:
                v = c[k]
                if v in (None, "", 0):
                    new["claude"][k] = None
                else:
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        raise ValueError("grænsen skal være et tal") from None
                    if not 1_000 <= v <= 10_000_000_000:
                        raise ValueError("grænsen skal være mellem 1.000 og 10 mia. tokens")
                    new["claude"][k] = v
        if "use_login" in c:
            new["claude"]["use_login"] = bool(c["use_login"])
        s = raw.get("spotify", {})
        if "client_id" in s:
            cid = str(s["client_id"] or "").strip()
            if cid and not re.fullmatch(r"[0-9a-fA-F]{32}", cid):
                raise ValueError("Spotify Client ID skal være 32 tegn (0-9, a-f)")
            new["spotify"]["client_id"] = cid
        with self._lock:
            self.data = new
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            tmp = SETTINGS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(new, f, indent=2)
            os.replace(tmp, SETTINGS_PATH)
        return self.public()
