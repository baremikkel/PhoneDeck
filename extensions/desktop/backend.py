"""Skrivebord: GNOME night light, do-not-disturb and dark/light theme through gsettings."""

from __future__ import annotations

import shutil
import subprocess
import threading

NIGHT = ("org.gnome.settings-daemon.plugins.color", "night-light-enabled")
WARMTH = ("org.gnome.settings-daemon.plugins.color", "night-light-temperature")
BANNERS = ("org.gnome.desktop.notifications", "show-banners")
SCHEME = ("org.gnome.desktop.interface", "color-scheme")
GTK = ("org.gnome.desktop.interface", "gtk-theme")
WARM_MIN, WARM_MAX = 1700, 4700


def _get(schema_key) -> str | None:
    try:
        r = subprocess.run(["gsettings", "get", *schema_key], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _set(schema_key, value: str) -> None:
    r = subprocess.run(["gsettings", "set", *schema_key, value], capture_output=True, text=True, timeout=3)
    if r.returncode:
        raise ValueError((r.stderr.strip() or "gsettings svarede med en fejl")[:140])


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.ok = bool(shutil.which("gsettings")) and _get(SCHEME) is not None
        self.data: dict = {}
        threading.Thread(target=self._loop, daemon=True).start()

    def _read(self) -> dict:
        warmth = _get(WARMTH) or ""
        try:
            k = int(warmth.split()[-1])
        except (ValueError, IndexError):
            k = None
        scheme = (_get(SCHEME) or "").strip("'")
        return {"ok": self.ok, "night": _get(NIGHT) == "true", "warmth": k,
                "dnd": _get(BANNERS) == "false", "dark": scheme == "prefer-dark"}

    def _loop(self):
        while not self.ctx.stopped.is_set():
            if self.ok:
                self.data = self._read()
            self.ctx.stopped.wait(3)

    def state(self):
        return self.data or {"ok": self.ok}

    def action(self, name, body):
        if not self.ok:
            raise ValueError("kræver GNOME (gsettings)")
        d = self._read()
        if name == "night":
            _set(NIGHT, "false" if d["night"] else "true")
        elif name == "dnd":
            _set(BANNERS, "true" if d["dnd"] else "false")
        elif name == "dark":
            dark = not d["dark"]
            _set(SCHEME, "'prefer-dark'" if dark else "'default'")
            # Ubuntu's Yaru: older (GTK3) programs follow the theme name, not color-scheme
            gtk = (_get(GTK) or "").strip("'")
            if gtk.startswith("Yaru"):
                base = gtk.removesuffix("-dark")
                _set(GTK, f"'{base}-dark'" if dark else f"'{base}'")
        elif name == "warmth":
            try:
                pct = max(0, min(100, int((body or {}).get("value"))))
            except (TypeError, ValueError):
                raise ValueError("ugyldig værdi") from None
            # 0 % = least warm (4700 K), 100 % = warmest (1700 K)
            _set(WARMTH, f"uint32 {round(WARM_MAX - pct / 100 * (WARM_MAX - WARM_MIN))}")
        else:
            raise ValueError(f"ukendt handling: {name}")
        self.data = self._read()
        return self.data
