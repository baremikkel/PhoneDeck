"""Installed desktop applications (.desktop files) and their icons."""

from __future__ import annotations

import configparser
import glob
import os
import subprocess
import time

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
