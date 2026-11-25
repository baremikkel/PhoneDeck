"""Talks to the optional PhoneDeck GNOME extension (gnome-extension/) over D-Bus.

Wayland hides other programs' windows, keyboard input and frame timing from ordinary
programs, so a tiny GNOME Shell extension answers for PhoneDeck:

    WindowApps() -> as            apps with an open window
    SendKeys(au)                  press a key combo (version 2+)
    Fps() -> (d, d, s)            frames shown in the last second, refresh rate, focused app (version 2+)

Uses PyGObject (already needed for the music player) and falls back to the ``gdbus``
command. Every call returns None when the extension isn't there.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time

NAME = "org.phonedeck.Helper"
PATH = "/org/phonedeck/Helper"

try:
    from gi.repository import Gio, GLib
except Exception:  # Windows, or no PyGObject
    Gio = GLib = None

_lock = threading.Lock()
_bus = None
_version: tuple[float, int] = (0.0, 0)  # (checked at, version)


def _session():
    global _bus
    if _bus is None and Gio is not None:
        try:
            _bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:
            _bus = False
    return _bus or None


def call(method: str, args=None, timeout_ms: int = 1500):
    """Call a helper method; returns the unpacked result tuple, or None."""
    bus = _session()
    if bus is not None:
        try:
            res = bus.call_sync(NAME, PATH, NAME, method, args, None,
                                Gio.DBusCallFlags.NO_AUTO_START, timeout_ms, None)
            return res.unpack() if res is not None else ()
        except Exception:
            return None
    # no PyGObject: the gdbus command
    argv = ["gdbus", "call", "--session", "--dest", NAME, "--object-path", PATH,
            "--method", f"{NAME}.{method}"]
    if args is not None:
        argv.append(args.print_(True) if hasattr(args, "print_") else str(args))
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_ms / 1000 + 0.5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def version() -> int:
    """0 = no helper, 1 = old helper (windows only), 2+ = keys and FPS too. Cached 10 s."""
    global _version
    with _lock:
        at, v = _version
        if time.monotonic() - at < 10:
            return v
    v = 0
    bus = _session()
    if bus is not None:
        try:
            res = bus.call_sync(NAME, PATH, "org.freedesktop.DBus.Properties", "Get",
                                GLib.Variant("(ss)", (NAME, "Version")), None,
                                Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
            v = int(res.unpack()[0])
        except Exception:
            v = 1 if window_apps() is not None else 0
    else:
        try:
            r = subprocess.run(["gdbus", "call", "--session", "--dest", NAME, "--object-path", PATH,
                                "--method", "org.freedesktop.DBus.Properties.Get", NAME, "Version"],
                               capture_output=True, text=True, timeout=2)
            m = re.search(r"uint32 (\d+)", r.stdout)
            v = int(m.group(1)) if m else (1 if window_apps() is not None else 0)
        except (OSError, subprocess.TimeoutExpired):
            v = 0
    with _lock:
        _version = (time.monotonic(), v)
    return v


def window_apps() -> set[str] | None:
    r = call("WindowApps")
    if r is None:
        return None
    if isinstance(r, str):  # gdbus text output
        return {x.lower() for x in re.findall(r"'([^']*)'", r)}
    return {x.lower() for x in r[0]}


def send_keys(keys: list[int]) -> bool:
    if version() < 2:
        return False
    if Gio is not None and _session() is not None:
        return call("SendKeys", GLib.Variant("(au)", (keys,))) is not None
    return call("SendKeys", "[" + ", ".join(f"uint32 {k}" for k in keys) + "]") is not None


def fps() -> dict | None:
    """{"fps": 143.0, "refresh": 144.0, "app": "Cyberpunk 2077"} or None."""
    if version() < 2:
        return None
    r = call("Fps")
    if r is None:
        return None
    if isinstance(r, str):
        m = re.match(r"\(([\d.]+),\s*([\d.]+),\s*'(.*)'\)", r.strip())
        if not m:
            return None
        r = (float(m.group(1)), float(m.group(2)), m.group(3))
    return {"fps": float(r[0]), "refresh": float(r[1]) or None, "app": r[2]}
