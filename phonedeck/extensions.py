"""Extensions: every feature beyond the core lives in its own folder.

An extension is a folder containing ``extension.json`` and optionally:

    backend.py   Python code (class Extension) – runs on the PC
    page.html    a page on the phone (swipe between pages)
    page.js      phone-side code: PhoneDeck.register("<id>", {...})
    page.css     styles for the page/widgets

Folders are read from ``extensions/`` in the repo and from
``~/.config/phonedeck/extensions/``. Add a folder and it appears; remove it and it
disappears (checked every few seconds – no restart needed).

extension.json::

    {
      "id": "spotify",                 // optional, defaults to the folder name
      "name": "Spotify-kø",
      "category": "Musik",             // groups pages + settings; missing -> "Andet"
      "description": "…",
      "page": {"title": "Musik"},      // only if page.html exists
      "widgets": [{"type": "media", "name": "Musik", "icon": "play"}],
      "settings": [                    // shown under the category in /settings
        {"key": "user", "label": "Brugernavn", "type": "text", "default": ""},
        {"key": "mode", "type": "select", "options": [["a", "A"], ["b", "B"]]},
        {"key": "on", "type": "bool"}, {"key": "n", "type": "number", "min": 1},
        {"type": "info", "html": "Text with {placeholders} from info()"},
        {"type": "button", "label": "Forbind", "href": "/ext/spotify/login"},
        {"type": "button", "label": "Afbryd", "action": "disconnect"},
        {"type": "status", "key": "status"},
        {"key": "token", "label": "Token", "type": "secret"}   // stored, never sent back to a browser
      ]
    }

backend.py::

    class Extension:
        def __init__(self, ctx): ...          # ctx: id, dir, settings(), hub, port, stopped
        def state(self) -> dict: ...          # sent to the phone every second (keep it fast)
        def action(self, name, body): ...     # POST /api/ext/<id>/action/<name>
        def http_get(self, path, query, req)  # GET /ext/<id>/<path> (return False = not mine)
        def info(self) -> dict: ...           # values for {placeholders} / status in settings
        def settings_changed(self): ...
        def stop(self): ...                   # folder removed / server stopping
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import threading
import traceback
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent / "extensions"
USER_DIR = Path(os.path.expanduser("~/.config/phonedeck/extensions"))
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
CATEGORY_ORDER = ["AI", "Musik", "Udvikling", "Hjem", "System"]
STATIC_TYPES = {".html", ".js", ".css", ".png", ".svg", ".jpg", ".jpeg", ".webp", ".json", ".woff2"}
_load_counter = 0


class Context:
    """What an extension's backend gets to work with."""

    def __init__(self, ext_id: str, folder: Path, manager: "ExtensionManager", manifest: dict | None = None):
        self.id = ext_id
        self.manifest = manifest or {}
        self.dir = folder
        self._manager = manager
        self.hub = manager.hub
        self.port = manager.port
        self.stopped = threading.Event()  # set when the extension is removed
        self.cache_dir = Path(os.path.expanduser(f"~/.cache/phonedeck/{ext_id}"))

    def settings(self) -> dict:
        # pass the manifest along: while the backend is being created it isn't registered yet
        return self._manager.settings_for(self.id, self.manifest)

    def clear_settings(self, keys: list[str]) -> None:
        """Forget saved values, e.g. secret tokens – a "Glem"-button calls this."""
        self.hub.settings.clear_ext(self.id, keys)

    def other(self, ext_id: str):
        """Another extension's backend (or None), e.g. Spotify reading the music player."""
        ext = self._manager.loaded.get(ext_id)
        return ext.backend if ext else None


class Loaded:
    def __init__(self, folder: Path, manifest: dict, mtime: float):
        self.dir = folder
        self.manifest = manifest
        self.mtime = mtime
        self.backend = None
        self.ctx: Context | None = None
        self.error: str | None = None

    @property
    def id(self) -> str:
        return self.manifest["id"]


def _manifest_mtime(folder: Path) -> float:
    try:
        return max(p.stat().st_mtime for p in folder.iterdir() if p.is_file())
    except (OSError, ValueError):
        return 0.0


def _read_manifest(folder: Path) -> dict | None:
    try:
        with open(folder / "extension.json", encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[phonedeck] udvidelse {folder.name}: ugyldig extension.json ({e})")
        return None
    m["id"] = str(m.get("id") or folder.name).lower()
    if not ID_RE.match(m["id"]):
        print(f"[phonedeck] udvidelse {folder.name}: ugyldigt id")
        return None
    m["name"] = str(m.get("name") or m["id"])
    cat = m.get("category")
    m["category"] = cat.strip() if isinstance(cat, str) and cat.strip() else "Andet"
    m.setdefault("settings", [])
    m.setdefault("widgets", [])
    m["has_page"] = (folder / "page.html").is_file()
    m["has_script"] = (folder / "page.js").is_file()
    m["has_style"] = (folder / "page.css").is_file()
    if m["has_page"]:
        m.setdefault("page", {})
        m["page"].setdefault("title", m["name"])
        # every card marked data-widget="…" on the page can also be placed on the
        # home page and on your own pages – as "<extension id>.<name>"
        try:
            html = (folder / "page.html").read_text(encoding="utf-8")
        except OSError:
            html = ""
        known = {w.get("type") for w in m["widgets"]}
        for tag in re.findall(r"<[^>]*\bdata-widget=\"[^\"]+\"[^>]*>", html):
            wid = re.search(r'data-widget="([a-z0-9-]+)"', tag)
            name = re.search(r'data-widget-name="([^"]*)"', tag)
            if wid and f"{m['id']}.{wid.group(1)}" not in known:
                m["widgets"].append({"type": f"{m['id']}.{wid.group(1)}",
                                     "name": name.group(1) if name else wid.group(1),
                                     "icon": "grid", "from_page": True})
    else:
        m.pop("page", None)
    return m


def category_sort_key(cat: str) -> tuple:
    if cat in CATEGORY_ORDER:
        return (0, CATEGORY_ORDER.index(cat))
    return (2, "") if cat == "Andet" else (1, cat.lower())


class ExtensionManager:
    def __init__(self, hub, port: int):
        self.hub = hub
        self.port = port
        self.loaded: dict[str, Loaded] = {}
        self._lock = threading.RLock()
        self.revision = 0

    # ---------- discovery ----------
    def _folders(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for base in (REPO_DIR, USER_DIR):  # the user folder can override a built-in one
            if not base.is_dir():
                continue
            for folder in sorted(base.iterdir()):
                if folder.is_dir() and (folder / "extension.json").is_file():
                    found[folder.name] = folder
        return found

    def scan(self) -> bool:
        """Load new folders, drop removed ones, reload changed ones. True if anything changed."""
        changed = False
        with self._lock:
            folders = self._folders()
            seen = set()
            for folder in folders.values():
                mtime = _manifest_mtime(folder)
                manifest = _read_manifest(folder)
                if not manifest:
                    continue
                ext_id = manifest["id"]
                seen.add(ext_id)
                cur = self.loaded.get(ext_id)
                if cur and cur.dir == folder and cur.mtime == mtime:
                    continue
                if cur:
                    self._unload(cur)
                self.loaded[ext_id] = self._load(folder, manifest, mtime)
                changed = True
            for ext_id in [e for e in self.loaded if e not in seen]:
                self._unload(self.loaded.pop(ext_id))
                print(f"[phonedeck] udvidelse fjernet: {ext_id}")
                changed = True
            if changed:
                self.revision += 1
        return changed

    def _load(self, folder: Path, manifest: dict, mtime: float) -> Loaded:
        global _load_counter
        ext = Loaded(folder, manifest, mtime)
        backend_file = folder / "backend.py"
        if backend_file.is_file():
            _load_counter += 1
            name = f"phonedeck_ext_{manifest['id'].replace('-', '_')}_{_load_counter}"
            try:
                # load as a package, so backend.py can do `from .helper import X`
                spec = importlib.util.spec_from_file_location(
                    name, backend_file, submodule_search_locations=[str(folder)])
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                ext.ctx = Context(manifest["id"], folder, self, manifest)
                ext.backend = module.Extension(ext.ctx)
            except Exception as e:
                ext.error = f"{type(e).__name__}: {e}"
                traceback.print_exc()
        print(f"[phonedeck] udvidelse indlæst: {manifest['id']} ({manifest['category']})"
              + (f" – FEJL: {ext.error}" if ext.error else ""))
        return ext

    def _unload(self, ext: Loaded) -> None:
        if ext.ctx:
            ext.ctx.stopped.set()
        if ext.backend and hasattr(ext.backend, "stop"):
            try:
                ext.backend.stop()
            except Exception:
                traceback.print_exc()
        for name in [m for m in sys.modules if m.startswith(f"phonedeck_ext_{ext.id.replace('-', '_')}_")]:
            sys.modules.pop(name, None)

    # ---------- runtime ----------
    def get(self, ext_id: str):
        ext = self.loaded.get(ext_id)
        return ext.backend if ext else None

    def states(self) -> dict:
        out = {}
        for ext_id, ext in list(self.loaded.items()):
            if ext.backend and hasattr(ext.backend, "state"):
                try:
                    out[ext_id] = ext.backend.state()
                except Exception as e:
                    out[ext_id] = {"error": str(e)}
        return out

    def action(self, ext_id: str, name: str, body: dict):
        ext = self.loaded.get(ext_id)
        if not ext or not ext.backend or not hasattr(ext.backend, "action"):
            raise ValueError(f"udvidelsen '{ext_id}' er ikke installeret")
        return ext.backend.action(name, body or {})

    def info(self, ext_id: str) -> dict:
        ext = self.loaded.get(ext_id)
        if ext and ext.backend and hasattr(ext.backend, "info"):
            try:
                return ext.backend.info() or {}
            except Exception as e:
                return {"error": str(e)}
        return {}

    def settings_changed(self, ext_id: str) -> None:
        ext = self.loaded.get(ext_id)
        if ext and ext.backend and hasattr(ext.backend, "settings_changed"):
            try:
                ext.backend.settings_changed()
            except Exception:
                traceback.print_exc()

    # ---------- settings ----------
    def settings_for(self, ext_id: str, manifest: dict | None = None) -> dict:
        if manifest is None:
            ext = self.loaded.get(ext_id)
            manifest = ext.manifest if ext else {}
        saved = self.hub.settings.ext_values(ext_id)
        out = {}
        for field in manifest.get("settings", []):
            if "key" in field and field.get("type") in ("text", "number", "bool", "select", "secret"):
                out[field["key"]] = saved.get(field["key"], field.get("default"))
        return out

    def validate_settings(self, ext_id: str, values: dict) -> dict:
        ext = self.loaded.get(ext_id)
        if not ext:
            raise ValueError(f"ukendt udvidelse: {ext_id}")
        fields = {f["key"]: f for f in ext.manifest.get("settings", []) if "key" in f}
        clean = {}
        for key, value in (values or {}).items():
            f = fields.get(key)
            if not f or f.get("type") not in ("text", "number", "bool", "select", "secret"):
                continue
            label = f.get("label", key)
            t = f["type"]
            if t == "bool":
                value = bool(value)
            elif t == "number":
                if value in (None, ""):
                    value = None
                else:
                    try:
                        value = float(value)
                        value = int(value) if value.is_integer() else value
                    except (TypeError, ValueError):
                        raise ValueError(f"{label}: skal være et tal") from None
                    if "min" in f and value < f["min"] or "max" in f and value > f["max"]:
                        raise ValueError(f"{label}: skal være mellem {f.get('min')} og {f.get('max')}")
            elif t == "secret":
                value = str(value or "").strip()[:2000]
                if not value:
                    continue  # empty = keep the saved one
            elif t == "select":
                if value not in [o[0] for o in f.get("options", [])]:
                    raise ValueError(f"{label}: ugyldigt valg")
            else:
                value = str(value or "").strip()[:500]
                if value and f.get("pattern") and not re.fullmatch(f["pattern"], value):
                    raise ValueError(f"{label}: {f.get('pattern_help', 'ugyldigt format')}")
            clean[key] = value
        return clean

    # ---------- what the phone / settings page need ----------
    def public(self, with_settings: bool = False) -> list[dict]:
        out = []
        for ext in sorted(self.loaded.values(), key=lambda e: (category_sort_key(e.manifest["category"]), e.manifest["name"].lower())):
            m = ext.manifest
            item = {k: m.get(k) for k in ("id", "name", "category", "description", "page", "widgets",
                                          "has_script", "has_style")}
            item["rev"] = int(ext.mtime)
            item["error"] = ext.error
            if with_settings:
                item["settings"] = m.get("settings", [])
                values = self.settings_for(ext.id)
                secrets = self.secret_keys(ext.id)
                item["secrets_set"] = {k: bool(values.get(k)) for k in secrets}
                item["values"] = {k: ("" if k in secrets else v) for k, v in values.items()}
                item["info"] = self.info(ext.id)
            out.append(item)
        return out

    def secret_keys(self, ext_id: str) -> set[str]:
        ext = self.loaded.get(ext_id)
        return {f["key"] for f in (ext.manifest.get("settings", []) if ext else []) if f.get("type") == "secret" and "key" in f}

    def mask(self, settings: dict) -> dict:
        """Settings as sent to a browser: secret values (tokens) blanked out."""
        for ext_id, values in (settings.get("ext") or {}).items():
            for k in self.secret_keys(ext_id) & set(values):
                values[k] = ""
        return settings

    def static_file(self, ext_id: str, rel: str) -> Path | None:
        ext = self.loaded.get(ext_id)
        if not ext:
            return None
        target = (ext.dir / rel).resolve()
        if ext.dir.resolve() not in target.parents or target.suffix.lower() not in STATIC_TYPES or not target.is_file():
            return None
        return target

    def stop_all(self) -> None:
        for ext in self.loaded.values():
            self._unload(ext)
