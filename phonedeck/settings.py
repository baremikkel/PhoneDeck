"""Settings edited from the browser (/settings), stored as JSON.

Core settings live under "ui". Every extension gets its own section under
"ext" -> "<extension id>", validated against the extension's own settings schema.
"""

from __future__ import annotations

import json
import os
import re
import threading

from .actions import load_config

SETTINGS_PATH = os.path.expanduser(os.environ.get("PHONEDECK_SETTINGS", "~/.config/phonedeck/settings.json"))

CORE_PAGES = ["overview", "system", "buttons"]
# Core widgets; extensions add their own (any id-like name is accepted and simply
# not shown while the extension providing it isn't installed)
CORE_WIDGETS = {"cpu", "gpu", "ram", "net", "disk", "sys", "clock", "button"}
WIDGET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
PAGE_RE = WIDGET_RE
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
    "ui": {
        "pages": ["overview", "system", "music", "claude-code", "github", "buttons"], "hidden": [],
        "dim": True, "dim_from": 23, "dim_to": 7,
        "pixel_shift": True, "deck_cols": 5, "auto_fullscreen": True,
        "home": DEFAULT_HOME,
    },
    "ext": {},
}

# page ids before extensions existed -> extension ids
OLD_PAGES = {"music": "music", "claude": "claude-code", "activity": "github"}


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
        t = str(it.get("type", ""))
        if t not in CORE_WIDGETS and not WIDGET_RE.match(t):
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


def _migrate(saved: dict) -> dict:
    """Bring settings from before the extension system over to the new layout."""
    ext = saved.setdefault("ext", {})
    if "claude" in saved:
        ext.setdefault("claude-code", {}).update(
            {k: v for k, v in saved.pop("claude").items() if v is not None})
    if "spotify" in saved:
        ext.setdefault("spotify", {}).update(saved.pop("spotify"))
    gh_user = load_config().get("github", {}).get("user")
    if gh_user and "user" not in ext.get("github", {}):
        ext.setdefault("github", {})["user"] = gh_user
    ui = saved.get("ui", {})
    if "pages" in ui:
        ui["pages"] = [OLD_PAGES.get(p, p) for p in ui["pages"]]
    if "hidden" in ui:
        ui["hidden"] = [OLD_PAGES.get(p, p) for p in ui["hidden"]]
    return saved


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(SETTINGS_PATH) as f:
                saved = _migrate(json.load(f))
            for k in DEFAULTS["ui"]:
                if k in saved.get("ui", {}):
                    self.data["ui"][k] = saved["ui"][k]
            if isinstance(saved.get("ext"), dict):
                self.data["ext"] = saved["ext"]
        except (OSError, ValueError):
            pass
        try:
            self.data["ui"]["home"] = validate_home(make_room_for_menu(self.data["ui"]["home"]))
        except (KeyError, ValueError):
            self.data["ui"]["home"] = json.loads(json.dumps(DEFAULT_HOME))

    def get(self, section: str, key: str):
        with self._lock:
            return self.data[section][key]

    def ext_values(self, ext_id: str) -> dict:
        with self._lock:
            return dict(self.data["ext"].get(ext_id, {}))

    def public(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self.data))

    def update(self, raw: dict, ext_validator=None) -> tuple[dict, list[str]]:
        """Validate and save. Returns (settings, ids of extensions whose settings changed).
        Raises ValueError with a Danish message."""
        new = self.public()
        u = raw.get("ui", {})
        if "pages" in u:
            pages = [p for p in u["pages"] if isinstance(p, str) and PAGE_RE.match(p)]
            pages += [p for p in CORE_PAGES if p not in pages]  # core pages can't be lost
            new["ui"]["pages"] = list(dict.fromkeys(pages))
        if "hidden" in u:
            hidden = [p for p in u["hidden"] if isinstance(p, str) and PAGE_RE.match(p)]
            if all(p in hidden for p in CORE_PAGES):
                raise ValueError("mindst én af Forside, System og Knapper skal være synlig")
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
        changed_ext = []
        for ext_id, values in (raw.get("ext") or {}).items():
            clean = ext_validator(ext_id, values) if ext_validator else {}
            new["ext"].setdefault(ext_id, {}).update(clean)
            changed_ext.append(ext_id)
        with self._lock:
            self.data = new
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            tmp = SETTINGS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(new, f, indent=2)
            os.replace(tmp, SETTINGS_PATH)
        return self.public(), changed_ext
