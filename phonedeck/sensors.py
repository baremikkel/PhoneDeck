"""PC hardware sensors (Linux).

Reads CPU/RAM/network/disk via psutil and temperatures, GPU load, VRAM and
power straight from sysfs (hwmon + amdgpu). NVIDIA GPUs are read through
``nvidia-smi`` when it is available.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time
from collections import deque

import psutil

HISTORY = 90  # samples kept for sparklines


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_num(path: str, scale: float = 1.0) -> float | None:
    raw = _read(path)
    if raw is None:
        return None
    try:
        return float(raw) / scale
    except ValueError:
        return None


def _hwmon_by_name() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for d in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name = _read(os.path.join(d, "name")) or "?"
        out.setdefault(name, []).append(d)
    return out


def _hwmon_temp(d: str, label: str | None = None) -> float | None:
    """Temperature (°C) from a hwmon dir, optionally matching a label."""
    for inp in sorted(glob.glob(os.path.join(d, "temp*_input"))):
        lab = _read(inp.replace("_input", "_label"))
        if label is None or lab == label:
            return _read_num(inp, 1000)
    return None


class _AmdGpu:
    def __init__(self, card_dev: str, hwmon: str | None):
        self.dev = card_dev
        self.hwmon = hwmon
        self.name = "AMD GPU"
        # Try to get a nicer name from lspci
        slot = os.path.basename(os.path.realpath(card_dev))
        if shutil.which("lspci"):
            try:
                txt = subprocess.run(["lspci", "-s", slot], capture_output=True,
                                     text=True, timeout=2).stdout
                if "[" in txt:
                    self.name = txt.split("[")[-1].split("]")[0].split("/")[0].strip()
                    self.name = "Radeon " + self.name.replace("Radeon ", "")
            except Exception:
                pass

    def read(self) -> dict:
        d, h = self.dev, self.hwmon
        vram_used = _read_num(f"{d}/mem_info_vram_used")
        vram_total = _read_num(f"{d}/mem_info_vram_total")
        power = None
        clock = None
        fan = None
        temp = temp_hot = None
        if h:
            power = _read_num(f"{h}/power1_average", 1e6) or _read_num(f"{h}/power1_input", 1e6)
            clock = _read_num(f"{h}/freq1_input", 1e6)
            fan = _read_num(f"{h}/fan1_input")
            temp = _hwmon_temp(h, "edge") or _hwmon_temp(h)
            temp_hot = _hwmon_temp(h, "junction")
        return {
            "name": self.name,
            "load": _read_num(f"{d}/gpu_busy_percent"),
            "temp": temp,
            "temp_hot": temp_hot,
            "power": power,
            "clock": clock,
            "fan": fan,
            "vram_used": vram_used,
            "vram_total": vram_total,
        }


class _NvidiaGpu:
    FIELDS = "name,utilization.gpu,temperature.gpu,power.draw,clocks.gr,fan.speed,memory.used,memory.total"

    def __init__(self):
        self.name = "NVIDIA GPU"

    def read(self) -> dict:
        try:
            out = subprocess.run(
                ["nvidia-smi", f"--query-gpu={self.FIELDS}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2).stdout.splitlines()[0]
            vals = [v.strip() for v in out.split(",")]

            def f(i):
                try:
                    return float(vals[i])
                except (ValueError, IndexError):
                    return None
            mib = 1024 * 1024
            return {
                "name": vals[0], "load": f(1), "temp": f(2), "temp_hot": None,
                "power": f(3), "clock": f(4), "fan": f(5),
                "vram_used": (f(6) or 0) * mib, "vram_total": (f(7) or 0) * mib,
            }
        except Exception:
            return {"name": self.name}


def _cpu_name() -> str:
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            name = line.split(":", 1)[1].strip()
            for junk in ("(R)", "(TM)", " Processor", " CPU"):
                name = name.replace(junk, "")
            return " ".join(name.split())
    return "CPU"


class Sensors:
    def __init__(self):
        hw = _hwmon_by_name()
        self.cpu_name = _cpu_name()
        self.cpu_hwmon = (hw.get("k10temp") or hw.get("coretemp") or hw.get("zenpower") or [None])[0]
        self.nvme_hwmons = hw.get("nvme", [])

        self.gpu = None
        for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
            dev = f"{card}/device"
            if os.path.exists(f"{dev}/gpu_busy_percent"):
                mons = glob.glob(f"{dev}/hwmon/hwmon*")
                self.gpu = _AmdGpu(dev, mons[0] if mons else None)
                break
        if self.gpu is None and shutil.which("nvidia-smi"):
            self.gpu = _NvidiaGpu()

        self.hist = {k: deque(maxlen=HISTORY) for k in ("cpu", "gpu", "ram", "net_down", "net_up", "cpu_temp", "gpu_temp")}
        self._net_prev = psutil.net_io_counters()
        self._disk_prev = psutil.disk_io_counters()
        self._t_prev = time.monotonic()
        psutil.cpu_percent(percpu=True)  # prime the counters

    def _cpu_temp(self) -> float | None:
        if not self.cpu_hwmon:
            return None
        return (_hwmon_temp(self.cpu_hwmon, "Tctl") or _hwmon_temp(self.cpu_hwmon, "Package id 0")
                or _hwmon_temp(self.cpu_hwmon))

    def sample(self) -> dict:
        now = time.monotonic()
        dt = max(now - self._t_prev, 1e-3)
        self._t_prev = now

        cores = psutil.cpu_percent(percpu=True)
        cpu = sum(cores) / len(cores) if cores else 0.0
        freq = psutil.cpu_freq()
        vm = psutil.virtual_memory()

        net = psutil.net_io_counters()
        down = (net.bytes_recv - self._net_prev.bytes_recv) / dt
        up = (net.bytes_sent - self._net_prev.bytes_sent) / dt
        self._net_prev = net

        disk = psutil.disk_io_counters()
        d_read = d_write = 0.0
        if disk and self._disk_prev:
            d_read = (disk.read_bytes - self._disk_prev.read_bytes) / dt
            d_write = (disk.write_bytes - self._disk_prev.write_bytes) / dt
        self._disk_prev = disk
        root = psutil.disk_usage("/")

        gpu = self.gpu.read() if self.gpu else None

        self.hist["cpu"].append(round(cpu, 1))
        self.hist["ram"].append(round(vm.percent, 1))
        self.hist["net_down"].append(round(down))
        self.hist["net_up"].append(round(up))
        self.hist["gpu"].append(gpu.get("load") if gpu else None)
        cpu_temp = self._cpu_temp()
        self.hist["cpu_temp"].append(round(cpu_temp, 1) if cpu_temp is not None else None)
        gpu_temp = (gpu.get("temp_hot") or gpu.get("temp")) if gpu else None
        self.hist["gpu_temp"].append(round(gpu_temp, 1) if gpu_temp is not None else None)

        return {
            "cpu": {
                "name": self.cpu_name,
                "load": round(cpu, 1),
                "cores": [round(c) for c in cores],
                "temp": cpu_temp,
                "freq": round(freq.current) if freq else None,
            },
            "gpu": gpu,
            "ram": {"used": vm.total - vm.available, "total": vm.total, "percent": vm.percent},
            "net": {"down": down, "up": up},
            "disk": {
                "read": d_read, "write": d_write,
                "used": root.used, "total": root.total,
                "temps": [t for t in (_hwmon_temp(h) for h in self.nvme_hwmons) if t is not None],
            },
            "uptime": time.time() - psutil.boot_time(),
            "history": {k: list(v) for k, v in self.hist.items()},
        }
