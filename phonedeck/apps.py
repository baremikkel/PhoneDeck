"""Installed desktop applications (.desktop files) and their icons."""

from __future__ import annotations

import configparser
import glob
import os
import re
import shutil
import subprocess
import time
from shlex import split as _shlex

import psutil

APP_DIRS = [
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/snapd/desktop/applications",
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    "/usr/local/share/applications",
    "/usr/share/applications",
]
ICON_DIRS = [
    os.path.expanduser("~/.local/share/icons"),
    os.path.expanduser("~/.icons"),
    "/var/lib/snapd/desktop/icons",
    "/var/lib/flatpak/exports/share/icons",
    os.path.expanduser("~/.local/share/flatpak/exports/share/icons"),
    "/usr/share/icons",
    "/usr/share/pixmaps",
]


def shlex_split(s: str) -> list[str]:
    try:
        return _shlex(s)
    except ValueError:
        return s.split()


SIZES = ["scalable", "512x512", "256x256", "128x128", "96x96", "64x64", "48x48", "32x32"]


class Apps:
    def __init__(self):
        self._apps: dict[str, dict] = {}
        self._scanned = 0.0
        self._icons: dict[str, str | None] = {}

    def _scan(self) -> None:
        if time.time() - self._scanned < 60:
            return
        apps: dict[str, dict] = {}
        for d in APP_DIRS:
            for path in sorted(glob.glob(os.path.join(d, "*.desktop"))):
                app_id = os.path.basename(path)
                if app_id in apps:  # earlier dirs win (user overrides)
                    continue
                cp = configparser.RawConfigParser(strict=False, interpolation=None)
                try:
                    cp.read(path, encoding="utf-8")
                    e = cp["Desktop Entry"]
                except (configparser.Error, KeyError, UnicodeDecodeError):
                    continue
                if e.get("Type", "Application") != "Application":
                    continue
                if e.get("NoDisplay", "").lower() == "true" or e.get("Hidden", "").lower() == "true":
                    continue
                if not e.get("Exec"):
                    continue
                apps[app_id] = {"id": app_id, "name": e.get("Name", app_id), "path": path,
                                "icon": e.get("Icon", "")}
        self._apps = apps
        self._scanned = time.time()

    def list(self) -> list[dict]:
        self._scan()
        return sorted(({"id": a["id"], "name": a["name"]} for a in self._apps.values()),
                      key=lambda a: a["name"].lower())

    def get(self, app_id: str) -> dict | None:
        self._scan()
        return self._apps.get(app_id)

    # ---------- is it running? ----------
    @staticmethod
    def _signature(app: dict) -> tuple[set[str], str | None]:
        """Process names that mean "this app is running", or a Steam game id."""
        cp = configparser.RawConfigParser(strict=False, interpolation=None)
        try:
            cp.read(app["path"], encoding="utf-8")
            e = cp["Desktop Entry"]
        except (configparser.Error, KeyError, UnicodeDecodeError):
            return set(), None
        exec_ = e.get("Exec", "")
        m = re.search(r"steam://rungameid/(\d+)", exec_)
        if m:
            return set(), m.group(1)
        parts = [p for p in shlex_split(exec_) if not p.startswith("%")]
        # skip wrappers like `env FOO=1 prog` / `flatpak run org.x.Y`
        while parts and (parts[0] in ("env", "sh", "bash") or "=" in parts[0]):
            parts = parts[1:]
        names = set()
        if parts:
            if os.path.basename(parts[0]) == "flatpak" and len(parts) > 2:
                names.add(parts[-1].split(".")[-1].lower())
            else:
                names.add(os.path.basename(parts[0]).lower())
        wm = e.get("StartupWMClass", "")
        if wm:
            names.add(wm.lower().split("_")[-1])
        return {n for n in names if n and n not in ("steam", "sh", "python3", "java")}, None

    # ---------- "Aktiv" = the program has a window open ----------
    @staticmethod
    def _helper_windows() -> set[str] | None:
        """Desktop ids of apps with an open window, from the optional PhoneDeck GNOME
        extension (gnome-extension/). None when the extension isn't installed."""
        try:
            r = subprocess.run(["gdbus", "call", "--session", "--dest", "org.phonedeck.Helper",
                                "--object-path", "/org/phonedeck/Helper",
                                "--method", "org.phonedeck.Helper.WindowApps"],
                               capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            return None
        return {x.lower() for x in re.findall(r"'([^']*)'", r.stdout)}

    @staticmethod
    def _x_env() -> dict:
        env = dict(os.environ)
        env.setdefault("DISPLAY", ":0")
        if "XAUTHORITY" not in env:  # GNOME's XWayland keeps its auth file here
            auth = glob.glob(f"/run/user/{os.getuid()}/.mutter-Xwaylandauth.*")
            if auth:
                env["XAUTHORITY"] = auth[0]
        return env

    def _x_visible(self, classes: set[str]) -> bool:
        if not shutil.which("xdotool"):
            return True  # can't tell – assume the window is there
        env = self._x_env()
        for cls in classes:
            out = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls],
                                 capture_output=True, text=True, timeout=2, env=env).stdout
            if out.strip():
                return True
        return False

    @staticmethod
    def _is_x11(pid: int) -> bool:
        """Programs started without WAYLAND_DISPLAY (Electron apps, Steam, …) draw via XWayland."""
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                return b"WAYLAND_DISPLAY=" not in f.read()
        except OSError:
            return False

    def running(self, app_ids: list[str]) -> set[str]:
        """Apps from the list that have a window open right now."""
        sigs = {}
        for app_id in app_ids:
            app = self.get(app_id)
            if app:
                if "sig" not in app:
                    app["sig"] = self._signature(app)
                sigs[app_id] = app["sig"]
        if not sigs:
            return set()
        by_name: dict[str, int] = {}
        steam_pids: list[tuple[str, int]] = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            by_name.setdefault((p.info["name"] or "").lower(), p.info["pid"])
            cmd = p.info["cmdline"] or []
            if cmd:
                by_name.setdefault(os.path.basename(cmd[0]).lower(), p.info["pid"])
                if any("AppId=" in c for c in cmd):
                    steam_pids.append((" ".join(cmd), p.info["pid"]))
        helper = self._helper_windows()
        out = set()
        for app_id, (procs, steam_id) in sigs.items():
            if steam_id:
                pid = next((pid for c, pid in steam_pids if f"AppId={steam_id}" in c), None)
            else:
                pid = next((by_name[n] for n in procs if n in by_name), None)
            if pid is None:
                continue  # not running at all
            if helper is not None:  # exact answer from GNOME
                if app_id.lower() in helper or (steam_id and any(steam_id in h for h in helper)):
                    out.add(app_id)
            elif self._is_x11(pid):  # XWayland: we can see its windows ourselves
                classes = set(procs) | ({f"steam_app_{steam_id}"} if steam_id else set())
                wm = self._wm_class(app_id)
                if wm:
                    classes.add(wm)
                if self._x_visible(classes):
                    out.add(app_id)
            else:
                out.add(app_id)  # native Wayland without the helper: best guess
        return out

    def _wm_class(self, app_id: str) -> str | None:
        app = self.get(app_id)
        if not app:
            return None
        if "wm" not in app:
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            try:
                cp.read(app["path"], encoding="utf-8")
                app["wm"] = cp["Desktop Entry"].get("StartupWMClass")
            except (configparser.Error, KeyError, UnicodeDecodeError):
                app["wm"] = None
        return app["wm"]

    def launch(self, app_id: str) -> None:
        app = self.get(app_id)
        if not app:
            raise ValueError(f"ukendt program: {app_id}")
        subprocess.Popen(["gio", "launch", app["path"]], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def icon_path(self, app_id: str) -> str | None:
        """Best icon file for an app (only for apps we know – never arbitrary paths)."""
        app = self.get(app_id)
        if not app or not app["icon"]:
            return None
        name = app["icon"]
        if name in self._icons:
            return self._icons[name]
        found = None
        if os.path.isabs(name):
            found = name if os.path.isfile(name) else None
        else:
            for base in ICON_DIRS:
                if found:
                    break
                if base.endswith("pixmaps") or base.endswith("snapd/desktop/icons"):
                    for ext in (".svg", ".png"):
                        p = os.path.join(base, name + ext)
                        if os.path.isfile(p):
                            found = p
                            break
                    continue
                for size in SIZES:
                    hits = glob.glob(os.path.join(base, "*", size, "apps", name + ".svg")) + \
                           glob.glob(os.path.join(base, "*", size, "apps", name + ".png"))
                    if hits:
                        # prefer hicolor / colour themes over symbolic ones
                        hits.sort(key=lambda h: ("symbolic" in h, "hicolor" not in h))
                        found = hits[0]
                        break
        self._icons[name] = found
        return found


# Windows: the Start menu instead of .desktop files
from .paths import IS_WINDOWS  # noqa: E402

if IS_WINDOWS:
    from .apps_win import WinApps as Apps  # noqa: F811,E402
