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
from . import paths

SETTINGS_PATH = os.path.expanduser(os.environ.get("PHONEDECK_SETTINGS", paths.config("settings.json")))

CORE_PAGES = ["overview", "system", "buttons"]
# Core widgets; extensions add their own (any id-like name is accepted and simply
# not shown while the extension providing it isn't installed)
CORE_WIDGETS = {"cpu", "gpu", "ram", "net", "disk", "sys", "clock", "button", "menu", "goto"}
WIDGET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,60}$")  # "<extension>.<element>" for page elements
PAGE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
CUSTOM_ID_RE = re.compile(r"^[a-z0-9]{1,12}$")
OPT_RE = re.compile(r"^[a-z0-9-]{1,30}$")  # display-option keys
MAX_CUSTOM_PAGES = 10
GRIDS = [(4, 2), (4, 3), (6, 3), (6, 4), (8, 4)]

DEFAULT_HOME = {
    "cols": 8, "rows": 4,
    "items": [
        {"type": "cpu", "x": 0, "y": 0, "w": 2, "h": 3},
        {"type": "gpu", "x": 2, "y": 0, "w": 2, "h": 3},
        {"type": "media", "x": 4, "y": 0, "w": 2, "h": 3},
        {"type": "claude", "x": 6, "y": 0, "w": 2, "h": 3},
        {"type": "sys", "x": 0, "y": 3, "w": 7, "h": 1},
        {"type": "menu", "x": 7, "y": 3, "w": 1, "h": 1},  # settings/editor – an ordinary element
    ],
}

DEFAULTS = {
    "ui": {
        "pages": ["overview", "system", "music", "claude-code", "github", "buttons"], "hidden": [],
        "dim": True, "dim_from": 23, "dim_to": 7,
        "pixel_shift": True, "deck_cols": 5, "auto_fullscreen": True,
        "home": DEFAULT_HOME,
        "home_v": 2,  # 2 = the menu button is an ordinary element (not locked)
        "custom_pages": [],  # your own pages: [{"id", "title", "cols", "rows", "items"}]
    },
    "ext": {},
}

# page ids before extensions existed -> extension ids
OLD_PAGES = {"music": "music", "claude": "claude-code", "activity": "github"}


def add_menu_element(h: dict) -> dict:
    """Layouts saved while the menu button was locked to the bottom-right cell: turn it into
    an ordinary "menu" element in that cell (shrinking whatever covers it, if anything)."""
    if any(it.get("type") == "menu" for it in h.get("items", [])):
        return h
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
    items.append({"type": "menu", "x": mx, "y": my, "w": 1, "h": 1})
    return dict(h, items=items)


def validate_home(h) -> dict:
    """A grid layout (the home page or one of your own pages)."""
    if not isinstance(h, dict):
        raise ValueError("ugyldig forside")
    cols, rows = h.get("cols"), h.get("rows")
    if (cols, rows) not in GRIDS:
        raise ValueError("ugyldig gitterstørrelse")
    items, taken = [], set()
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
        if cells & taken:
            raise ValueError("to felter overlapper")
        taken |= cells
        item = {"type": t, "x": x, "y": y, "w": w, "h": hh}
        if t == "button":
            item["button"] = str(it.get("button", ""))[:40]
        if t == "goto":  # "Gå til side": switches the phone to a page
            page = str(it.get("page", ""))
            if not PAGE_RE.match(page):
                raise ValueError("vælg en side til Gå til side-knappen")
            item["page"] = page
        # display options: parts to hide ("header", "frame", "label", or a part the element marks
        # with data-opt="…"), and for buttons: invisible but still pressable
        hide = [h for h in (it.get("hide") or []) if isinstance(h, str) and OPT_RE.match(h)][:16]
        if hide:
            item["hide"] = list(dict.fromkeys(hide))
        if it.get("invisible") is True:
            item["invisible"] = True
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
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                saved = _migrate(json.load(f))
            for k in DEFAULTS["ui"]:
                if k in saved.get("ui", {}):
                    self.data["ui"][k] = saved["ui"][k]
            if isinstance(saved.get("ext"), dict):
                self.data["ext"] = saved["ext"]
            if saved.get("ui", {}).get("home_v", 1) < 2 and "home" in saved.get("ui", {}):
                self.data["ui"]["home"] = add_menu_element(self.data["ui"]["home"])
        except (OSError, ValueError):
            pass
        try:
            self.data["ui"]["home"] = validate_home(self.data["ui"]["home"])
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
        if "custom_pages" in u:
            pages, seen = [], set()
            for cp in (u["custom_pages"] or [])[:MAX_CUSTOM_PAGES]:
                pid = str(cp.get("id", ""))
                if not CUSTOM_ID_RE.match(pid) or pid in seen:
                    raise ValueError("ugyldigt side-id")
                seen.add(pid)
                title = str(cp.get("title", "")).strip()[:30] or "Min side"
                pages.append({"id": pid, "title": title, **validate_home(cp)})
            new["ui"]["custom_pages"] = pages
        changed_ext = []
        for ext_id, values in (raw.get("ext") or {}).items():
            clean = ext_validator(ext_id, values) if ext_validator else {}
            new["ext"].setdefault(ext_id, {}).update(clean)
            changed_ext.append(ext_id)
        with self._lock:
            self.data = new
            self._write(new)
        return self.public(), changed_ext

    def _write(self, data: dict) -> None:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # may hold tokens
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, SETTINGS_PATH)

    def clear_ext(self, ext_id: str, keys: list[str]) -> None:
        """Remove saved values (e.g. secret links/tokens, which the form can't empty)."""
        with self._lock:
            values = self.data["ext"].get(ext_id, {})
            for k in keys:
                values.pop(k, None)
            self._write(self.data)
