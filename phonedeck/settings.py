"""Settings edited from the browser (/settings), stored as JSON."""

from __future__ import annotations

import json
import os
import re
import threading

SETTINGS_PATH = os.path.expanduser(os.environ.get("PHONEDECK_SETTINGS", "~/.config/phonedeck/settings.json"))

PAGES = ["overview", "system", "music", "claude", "activity", "buttons"]
# Widgets that can be placed on the home page grid
WIDGETS = {"cpu", "gpu", "ram", "net", "disk", "sys", "media", "claude", "donut", "clock",
           "github", "button"}
GRIDS = [(4, 2), (4, 3), (6, 3), (6, 4), (8, 4)]

DEFAULT_HOME = {
    "cols": 8, "rows": 4,
    "items": [
        {"type": "cpu", "x": 0, "y": 0, "w": 2, "h": 3},
        {"type": "gpu", "x": 2, "y": 0, "w": 2, "h": 3},
        {"type": "media", "x": 4, "y": 0, "w": 2, "h": 3},
        {"type": "claude", "x": 6, "y": 0, "w": 2, "h": 3},
        {"type": "sys", "x": 0, "y": 3, "w": 7, "h": 1},
    ],
}

DEFAULTS = {
    "claude": {"budget_5h": None, "budget_week": None, "use_login": False, "donut_mode": "left"},
    "spotify": {"client_id": ""},
    "ui": {
        "pages": PAGES, "hidden": [],
        "dim": True, "dim_from": 23, "dim_to": 7,
        "pixel_shift": True, "deck_cols": 5, "auto_fullscreen": True,
        "home": DEFAULT_HOME,
    },
}


def make_room_for_menu(h: dict) -> dict:
    """The bottom-right cell is reserved for the locked settings button.
    Shrink (or drop) whatever covers it – used for layouts saved before it existed."""
    mx, my = h["cols"] - 1, h["rows"] - 1
    items = []
    for it in h.get("items", []):
        covers = it["x"] <= mx < it["x"] + it["w"] and it["y"] <= my < it["y"] + it["h"]
        if covers:
            it = dict(it)
            if it["w"] > 1:
                it["w"] -= 1
            elif it["h"] > 1:
                it["h"] -= 1
            else:
                continue
        items.append(it)
    return dict(h, items=items)


def validate_home(h) -> dict:
    if not isinstance(h, dict):
        raise ValueError("ugyldig forside")
    cols, rows = h.get("cols"), h.get("rows")
    if (cols, rows) not in GRIDS:
        raise ValueError("ugyldig gitterstørrelse")
    items, taken = [], {(cols - 1, rows - 1)}  # bottom-right = locked menu button
    for it in h.get("items", [])[:48]:
        t = it.get("type")
        if t not in WIDGETS:
            raise ValueError(f"ukendt felt: {t}")
        try:
            x, y, w, hh = (int(it[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError):
            raise ValueError("ugyldig placering") from None
        if w < 1 or hh < 1 or x < 0 or y < 0 or x + w > cols or y + hh > rows:
            raise ValueError("et felt går uden for gitteret")
        cells = {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + hh)}
        if (cols - 1, rows - 1) in cells:
            raise ValueError("feltet nederst til højre er låst til menu-knappen")
        if cells & taken:
            raise ValueError("to felter overlapper")
        taken |= cells
        item = {"type": t, "x": x, "y": y, "w": w, "h": hh}
        if t == "button":
            item["button"] = str(it.get("button", ""))[:40]
        items.append(item)
    return {"cols": cols, "rows": rows, "items": items}


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
        try:
            self.data["ui"]["home"] = validate_home(make_room_for_menu(self.data["ui"]["home"]))
        except (KeyError, ValueError):
            self.data["ui"]["home"] = json.loads(json.dumps(DEFAULT_HOME))

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
        if "donut_mode" in c:
            if c["donut_mode"] not in ("left", "used"):
                raise ValueError("donutten skal vise 'left' eller 'used'")
            new["claude"]["donut_mode"] = c["donut_mode"]
        u = raw.get("ui", {})
        if "pages" in u:
            pages = [p for p in u["pages"] if p in PAGES]
            pages += [p for p in PAGES if p not in pages]  # never lose a page
            new["ui"]["pages"] = pages
        if "hidden" in u:
            hidden = [p for p in u["hidden"] if p in PAGES]
            if len(hidden) >= len(PAGES):
                raise ValueError("mindst én side skal være synlig")
            new["ui"]["hidden"] = hidden
        for k in ("dim", "pixel_shift", "auto_fullscreen"):
            if k in u:
                new["ui"][k] = bool(u[k])
        for k in ("dim_from", "dim_to"):
            if k in u:
                v = int(u[k])
                if not 0 <= v <= 23:
                    raise ValueError("timer skal være 0–23")
                new["ui"][k] = v
        if "deck_cols" in u:
            v = int(u["deck_cols"])
            if not 3 <= v <= 8:
                raise ValueError("3–8 knapper pr. række")
            new["ui"]["deck_cols"] = v
        if "home" in u:
            new["ui"]["home"] = validate_home(u["home"])
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
