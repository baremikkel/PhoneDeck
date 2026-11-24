"""Installed programs on Windows: the shortcuts in the Start menu, plus Store (MSIX) apps.

Same interface as apps.Apps on Linux. A program counts as "Aktiv" when its .exe has a
visible window (EnumWindows), and it is started like a double-click on the shortcut.
Icons aren't extracted – the editor falls back to an emoji / built-in icon.
"""

from __future__ import annotations

import glob
import json
import ntpath
import os
import struct
import subprocess
import time

import psutil

from . import win

START_MENUS = [
    os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
]
SKIP = ("uninstall", "afinstaller", "readme", "help", "hjælp", "website", "documentation", "license")


def lnk_target(path: str) -> str | None:
    """The target of a .lnk file (Shell Link binary format: LinkInfo → LocalBasePath)."""
    try:
        with open(path, "rb") as f:
            data = f.read(64 * 1024)
        if len(data) < 0x4C or data[:4] != b"\x4c\x00\x00\x00":
            return None
        flags = struct.unpack_from("<I", data, 0x14)[0]
        pos = 0x4C
        if flags & 0x1:  # HasLinkTargetIDList
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        if not flags & 0x2:  # HasLinkInfo
            return None
        info = pos
        header = struct.unpack_from("<I", data, info + 4)[0]
        info_flags = struct.unpack_from("<I", data, info + 8)[0]
        if not info_flags & 0x1:  # VolumeIDAndLocalBasePath
            return None
        if header >= 0x24:  # a Unicode path is there too
            off = struct.unpack_from("<I", data, info + 28)[0]
            end = data.find(b"\x00\x00", info + off)
            while end != -1 and (end - (info + off)) % 2:
                end = data.find(b"\x00\x00", end + 1)
            return data[info + off:end].decode("utf-16-le", "replace") or None
        off = struct.unpack_from("<I", data, info + 16)[0]
        end = data.find(b"\x00", info + off)
        return data[info + off:end].decode("mbcs" if os.name == "nt" else "latin-1", "replace") or None
    except (OSError, struct.error, LookupError):
        return None


PACKAGED_EVERY = 600  # seconds between asking Windows for the Store apps (it takes a moment)


def packaged_apps() -> list[dict]:
    """Store / MSIX apps (Notepad, Calculator, Photos, Spotify from the Store …). They have no
    .lnk in the Start menu folders; Get-StartApps lists them with an AppUserModelID."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
             "Get-StartApps | Where-Object AppID -like '*!*' | Select-Object Name,AppID | ConvertTo-Json -Compress"],
            capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.decode("utf-8", "replace").strip()
        items = json.loads(out) if out else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    items = [items] if isinstance(items, dict) else items
    return [{"name": i["Name"], "aumid": i["AppID"]} for i in items
            if isinstance(i, dict) and i.get("Name") and i.get("AppID")]


class WinApps:
    def __init__(self):
        self._apps: dict[str, dict] = {}
        self._scanned = 0.0
        self._packaged: list[dict] = []
        self._packaged_at = 0.0

    def _scan(self) -> None:
        if time.time() - self._scanned < 60:
            return
        if time.time() - self._packaged_at > PACKAGED_EVERY:
            self._packaged_at = time.time()
            self._packaged = packaged_apps() or self._packaged
        apps: dict[str, dict] = {}
        for base in START_MENUS:
            for path in sorted(glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True)):
                name = os.path.splitext(os.path.basename(path))[0]
                if any(s in name.lower() for s in SKIP):
                    continue
                app_id = os.path.relpath(path, base).replace("\\", "/")
                if app_id in apps:
                    continue
                target = lnk_target(path)
                apps[app_id] = {"id": app_id, "name": name, "path": path, "icon": "",
                                "exe": ntpath.basename(target).lower() if target and target.lower().endswith(".exe") else None}
        names = {a["name"].lower() for a in apps.values()}
        for p in self._packaged:
            if p["name"].lower() in names or any(s in p["name"].lower() for s in SKIP):
                continue  # the same program as a Start menu shortcut
            app_id = "store:" + p["aumid"]
            apps[app_id] = {"id": app_id, "name": p["name"], "path": "shell:AppsFolder\\" + p["aumid"],
                            "icon": "", "exe": None}
        self._apps = apps
        self._scanned = time.time()

    def list(self) -> list[dict]:
        self._scan()
        return sorted(({"id": a["id"], "name": a["name"]} for a in self._apps.values()),
                      key=lambda a: a["name"].lower())

    def get(self, app_id: str) -> dict | None:
        self._scan()
        return self._apps.get(app_id)

    def running(self, app_ids: list[str]) -> set[str]:
        """Programs with a visible window right now."""
        wanted = {i: self.get(i) for i in app_ids}
        if not any(a and a.get("exe") for a in wanted.values()):
            return set()
        exes = set()
        for pid in win.visible_window_pids():
            try:
                exes.add(psutil.Process(pid).name().lower())
            except (psutil.Error, OSError):
                pass
        return {i for i, a in wanted.items() if a and a.get("exe") in exes}

    def launch(self, app_id: str) -> None:
        app = self.get(app_id)
        if not app:
            raise ValueError(f"ukendt program: {app_id}")
        win.open_target(app["path"])

    def icon_path(self, app_id: str) -> str | None:
        return None
