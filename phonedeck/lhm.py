"""Temperatures, GPU load/power/VRAM and NVMe temps on Windows via LibreHardwareMonitor.

Windows has no sysfs, so PhoneDeck reads LibreHardwareMonitor's built-in web server
(Options → Remote Web Server → Run, default port 8085) at http://localhost:8085/data.json.
Only localhost is ever asked. Everything else (CPU load, RAM, network, disk) comes from
psutil as on Linux.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

URL = "http://127.0.0.1:{port}/data.json"
CACHE_S = 1.5
HARDWARE_ICONS = {"cpu", "ati", "amd", "nvidia", "intel", "hdd", "nic", "ram", "mainboard", "chip", "gpu"}


def _num(value) -> float | None:
    """'45.3 °C' / '12,5 %' / '1234 MHz' -> float"""
    if value is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    return float(m.group(0).replace(",", ".")) if m else None


class LibreHardwareMonitor:
    def __init__(self, port: int = 8085):
        self.url = URL.format(port=port)
        self._lock = threading.Lock()
        self._at = 0.0
        self._sensors: list[dict] = []   # flat: {hw, hw_id, type, name, value}
        self.ok = False

    def _walk(self, node: dict, hw: str, hw_id: str, out: list) -> None:
        sid = node.get("SensorId") or ""
        if sid:
            parts = sid.strip("/").split("/")  # e.g. amdcpu/0/temperature/2
            out.append({"hw": hw, "hw_id": "/".join(parts[:2]), "type": node.get("Type") or (parts[2] if len(parts) > 2 else ""),
                        "name": node.get("Text") or "", "value": _num(node.get("Value"))})
            return
        # hardware nodes have icons like images_icon/cpu.png, ati.png, nvidia.png, hdd.png;
        # the groups under them (temperature.png, load.png …) don't change the name
        img = (node.get("ImageURL") or "").lower().rsplit("/", 1)[-1].split(".")[0]
        if img in HARDWARE_ICONS and node.get("Text"):
            hw = node["Text"]
        for child in node.get("Children") or []:
            self._walk(child, hw, hw_id, out)

    def refresh(self) -> list[dict]:
        with self._lock:
            if time.monotonic() - self._at < CACHE_S:
                return self._sensors
            self._at = time.monotonic()
            try:
                with urllib.request.urlopen(self.url, timeout=1) as r:
                    tree = json.load(r)
                out: list[dict] = []
                self._walk(tree, "", "", out)
                self._sensors, self.ok = out, True
            except (OSError, ValueError):
                self._sensors, self.ok = [], False
            return self._sensors

    def _find(self, prefixes: tuple[str, ...], stype: str, names: tuple[str, ...]) -> float | None:
        sensors = [s for s in self.refresh() if s["hw_id"].split("/")[0].startswith(prefixes) and s["type"].lower() == stype]
        for want in names:
            for s in sensors:
                if want.lower() in s["name"].lower() and s["value"] is not None:
                    return s["value"]
        return sensors[0]["value"] if sensors and not names else None

    # ---- what Sensors asks for ----
    def cpu_temp(self) -> float | None:
        return self._find(("amdcpu", "intelcpu", "cpu"), "temperature",
                          ("Tctl", "Tdie", "Package", "Core Average", "Core Max", "CPU"))

    def gpu(self) -> dict | None:
        prefixes = ("gpu-nvidia", "gpu-amd", "gpu-intel", "nvidiagpu", "atigpu", "amdgpu", "intelgpu")
        sensors = [s for s in self.refresh() if s["hw_id"].split("/")[0].startswith(prefixes)]
        if not sensors:
            return None
        f = lambda t, *n: self._find(prefixes, t, n)  # noqa: E731
        mib = 1024 * 1024
        used, total = f("smalldata", "GPU Memory Used", "D3D Dedicated Memory Used"), f("smalldata", "GPU Memory Total")
        fan = f("control", "GPU Fan")  # 0 % is a real value: many cards stop the fan when idle
        if fan is None:
            fan = f("load", "GPU Fan")
        return {
            "name": sensors[0]["hw"] or "GPU",
            "load": f("load", "GPU Core", "D3D 3D"),
            "temp": f("temperature", "GPU Core", "GPU"),
            "temp_hot": f("temperature", "Hot Spot", "Junction"),
            "power": f("power", "GPU Package", "GPU Power", "GPU Core"),
            "clock": f("clock", "GPU Core"),
            "fan": fan,
            "vram_used": used * mib if used is not None else None,
            "vram_total": total * mib if total is not None else None,
        }

    def drives(self) -> dict[str, list[dict]]:
        """Storage sensors grouped per drive (hw_id -> sensors)."""
        out: dict[str, list[dict]] = {}
        for s in self.refresh():
            if s["hw_id"].startswith(("nvme", "hdd", "ssd", "storage")):
                out.setdefault(s["hw_id"], []).append(s)
        return out

    def nvme_temps(self) -> list[float]:
        """One temperature per drive: the composite one when there is one (NVMe drives also
        report several internal sensors and their warning/critical limits)."""
        temps = []
        for sensors in self.drives().values():
            t = [s for s in sensors if s["type"].lower() == "temperature" and s["value"] is not None
                 and not any(w in s["name"].lower() for w in ("warning", "critical", "limit"))]
            best = next((s for s in t if "composite" in s["name"].lower()), t[0] if t else None)
            if best:
                temps.append(best["value"])
        return temps[:4]


class LhmGpu:
    """Drop-in for the Linux GPU readers in sensors.py."""

    def __init__(self, lhm: LibreHardwareMonitor):
        self.lhm = lhm
        self.name = "GPU"

    def read(self) -> dict:
        return self.lhm.gpu() or {"name": self.name}
