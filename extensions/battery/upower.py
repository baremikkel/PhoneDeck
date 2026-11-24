"""Battery levels of connected devices (headsets, mice, keyboards, controllers …) from UPower."""

from __future__ import annotations

import re
import subprocess

KINDS = {  # UPower device type -> (Danish name, icon)
    "headset": ("Headset", "headset"), "headphones": ("Hovedtelefoner", "headset"),
    "mouse": ("Mus", "mouse"), "keyboard": ("Tastatur", "keyboard"), "gaming-input": ("Controller", "gamepad"),
    "touchpad": ("Touchpad", "mouse"), "tablet": ("Tegneplade", "mouse"), "phone": ("Telefon", "phone"),
    "battery": ("Batteri", "battery"), "ups": ("UPS", "battery"), "speakers": ("Højttaler", "headset"),
    "media-player": ("Afspiller", "headset"), "pen": ("Pen", "mouse"), "bluetooth-generic": ("Bluetooth", "battery"),
    "other": ("Enhed", "battery"),
}
LEVELS = {"full": 100, "high": 80, "normal": 55, "low": 20, "critical": 5}


def parse(text: str) -> list[dict]:
    devices = []
    for block in re.split(r"\n(?=Device: )", text):
        if not block.startswith("Device: ") or "DisplayDevice" in block.splitlines()[0]:
            continue
        lines = block.splitlines()
        props = {}
        kind = None
        for line in lines[1:]:
            m = re.match(r"^\s+(\S[^:]*):\s*(.*)$", line)  # "  model: X" and "    percentage: 70%"
            if m:
                props[m.group(1).strip()] = m.group(2).strip().strip("'")
            elif re.match(r"^\s{2}[a-z-]+\s*$", line):  # the device type on its own line, e.g. "  headset"
                kind = line.strip()
        if kind in (None, "line-power"):
            continue
        pct = props.get("percentage", "").rstrip("%").replace(",", ".")
        try:
            percent = round(float(pct))
        except ValueError:
            percent = None
        if percent in (None, 0) and props.get("battery-level") in LEVELS:
            percent = LEVELS[props["battery-level"]]
        if percent is None:
            continue
        name, icon = KINDS.get(kind, KINDS["other"])
        model = props.get("model") or props.get("vendor") or name
        devices.append({"id": lines[0][8:].strip().rsplit("/", 1)[-1], "name": model, "kind": name, "icon": icon,
                        "percent": percent, "state": props.get("state", ""),
                        "approx": props.get("battery-level") not in (None, "none", "unknown") and pct in ("", "0")})
    devices.sort(key=lambda d: (d["kind"] == "Batteri", d["percent"]))
    return devices


def read() -> list[dict]:
    try:
        out = subprocess.run(["upower", "-d"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse(out)
