"""Built-in Windows hardware readings – no extra programs needed.

Everything here comes from Windows itself through ctypes:

* **GPU** (any vendor, WDDM 2.4+ / Windows 10 1803 and newer): name, dedicated VRAM size,
  temperature, fan speed and clock from the display driver (``D3DKMTQueryAdapterInfo`` in
  gdi32 – the same source Task Manager uses for its GPU temperature), plus load and VRAM
  in use from the "GPU Engine" and "GPU Adapter Memory" performance counters.
* **CPU temperature**: the ACPI "Thermal Zone Information" performance counter. It is the
  motherboard's own reading, so it can lag behind or differ a little from the CPU die
  temperature. Run LibreHardwareMonitor for the exact sensor (optional, see lhm.py).

Every call is wrapped: a missing counter or an old driver just gives ``None``.
"""

from __future__ import annotations

import ctypes
import re
import sys
import threading
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Performance counters (pdh.dll)
# ---------------------------------------------------------------------------
PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
PDH_MORE_DATA = 0x800007D2


class _FmtValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _FmtItem(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _FmtValue)]


class Counters:
    """A PDH query with wildcard counters, read as {instance: value}."""

    def __init__(self, paths: dict[str, str]):
        self.pdh = ctypes.WinDLL("pdh")
        self.query = wintypes.HANDLE()
        self.counters: dict[str, wintypes.HANDLE] = {}
        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.query)) != 0:
            raise OSError("PdhOpenQuery")
        for key, path in paths.items():
            h = wintypes.HANDLE()
            # the English names work on every language version of Windows
            if self.pdh.PdhAddEnglishCounterW(self.query, path, 0, ctypes.byref(h)) == 0:
                self.counters[key] = h

    def collect(self) -> None:
        self.pdh.PdhCollectQueryData(self.query)

    def read(self, key: str) -> dict[str, float]:
        h = self.counters.get(key)
        if h is None:
            return {}
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        fmt = PDH_FMT_DOUBLE | PDH_FMT_NOCAP100
        rc = self.pdh.PdhGetFormattedCounterArrayW(h, fmt, ctypes.byref(size), ctypes.byref(count), None)
        if (rc & 0xFFFFFFFF) != PDH_MORE_DATA or not size.value:
            return {}
        buf = (ctypes.c_byte * size.value)()
        if self.pdh.PdhGetFormattedCounterArrayW(h, fmt, ctypes.byref(size), ctypes.byref(count), buf) != 0:
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(_FmtItem))
        out = {}
        for i in range(count.value):
            it = items[i]
            if it.FmtValue.CStatus in (0, 1):  # PDH_CSTATUS_VALID_DATA / NEW_DATA
                out[it.szName or ""] = it.FmtValue.doubleValue
        return out


# ---------------------------------------------------------------------------
# Display driver (gdi32.dll D3DKMT*)
# ---------------------------------------------------------------------------
KMTQAITYPE_GETSEGMENTSIZE = 3
KMTQAITYPE_ADAPTERREGISTRYINFO = 8
KMTQAITYPE_ADAPTERTYPE = 15
KMTQAITYPE_NODEPERFDATA = 61
KMTQAITYPE_ADAPTERPERFDATA = 62


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _AdapterInfo(ctypes.Structure):
    _fields_ = [("hAdapter", wintypes.UINT), ("AdapterLuid", _LUID),
                ("NumOfSources", wintypes.ULONG), ("bPrecisePresentRegionsPreferred", wintypes.BOOL)]


class _EnumAdapters2(ctypes.Structure):
    _fields_ = [("NumAdapters", wintypes.ULONG), ("pAdapters", ctypes.POINTER(_AdapterInfo))]


class _QueryAdapterInfo(ctypes.Structure):
    _fields_ = [("hAdapter", wintypes.UINT), ("Type", wintypes.UINT),
                ("pPrivateDriverData", ctypes.c_void_p), ("PrivateDriverDataSize", wintypes.UINT)]


class _RegistryInfo(ctypes.Structure):
    _fields_ = [("AdapterString", ctypes.c_wchar * 260), ("BiosString", ctypes.c_wchar * 260),
                ("DacType", ctypes.c_wchar * 260), ("ChipType", ctypes.c_wchar * 260)]


class _SegmentSize(ctypes.Structure):
    _fields_ = [("DedicatedVideoMemorySize", ctypes.c_ulonglong),
                ("DedicatedSystemMemorySize", ctypes.c_ulonglong),
                ("SharedSystemMemorySize", ctypes.c_ulonglong)]


class _AdapterPerf(ctypes.Structure):
    _fields_ = [("PhysicalAdapterIndex", ctypes.c_uint32), ("MemoryFrequency", ctypes.c_ulonglong),
                ("MaxMemoryFrequency", ctypes.c_ulonglong), ("MaxMemoryFrequencyOC", ctypes.c_ulonglong),
                ("MemoryBandwidth", ctypes.c_ulonglong), ("PCIEBandwidth", ctypes.c_ulonglong),
                ("FanRPM", wintypes.ULONG), ("Power", wintypes.ULONG),
                ("Temperature", wintypes.ULONG),  # deci-°C
                ("PowerStateOverride", ctypes.c_ubyte)]


class _NodePerf(ctypes.Structure):
    _fields_ = [("NodeOrdinal", ctypes.c_uint32), ("PhysicalAdapterIndex", ctypes.c_uint32),
                ("Frequency", ctypes.c_ulonglong), ("MaxFrequency", ctypes.c_ulonglong),
                ("MaxFrequencyOC", ctypes.c_ulonglong), ("Voltage", wintypes.ULONG),
                ("VoltageMax", wintypes.ULONG), ("VoltageMaxOC", wintypes.ULONG),
                ("MaxTransitionLatency", ctypes.c_ulonglong)]


def _luid_key(luid: _LUID) -> str:
    """The form performance counters use: luid_0x00000000_0x0000D1F2"""
    return f"luid_0x{luid.HighPart & 0xFFFFFFFF:08x}_0x{luid.LowPart:08x}"


class _Adapter:
    def __init__(self, gdi, info: _AdapterInfo):
        self.gdi = gdi
        self.h = info.hAdapter
        self.luid = _luid_key(info.AdapterLuid)
        reg = _RegistryInfo()
        self.name = reg.AdapterString.strip() if self._query(KMTQAITYPE_ADAPTERREGISTRYINFO, reg) else ""
        seg = _SegmentSize()
        ok = self._query(KMTQAITYPE_GETSEGMENTSIZE, seg)
        self.vram_total = seg.DedicatedVideoMemorySize if ok else 0
        self.shared_total = seg.SharedSystemMemorySize if ok else 0
        # built into the CPU (Intel Iris/UHD, AMD Radeon in Ryzen …): borrows normal RAM
        self.integrated = self.vram_total < 1 << 30
        kind = wintypes.UINT(0)
        self.software = bool(self._query(KMTQAITYPE_ADAPTERTYPE, kind) and kind.value & 0b100)

    def _query(self, qtype: int, out) -> bool:
        q = _QueryAdapterInfo(self.h, qtype, ctypes.cast(ctypes.byref(out), ctypes.c_void_p), ctypes.sizeof(out))
        try:
            return self.gdi.D3DKMTQueryAdapterInfo(ctypes.byref(q)) == 0
        except OSError:
            return False

    def perf(self) -> dict:
        out: dict = {}
        p = _AdapterPerf(PhysicalAdapterIndex=0)
        if self._query(KMTQAITYPE_ADAPTERPERFDATA, p):
            out["temp"] = p.Temperature / 10 if 0 < p.Temperature < 2000 else None
            out["fan"] = p.FanRPM if p.FanRPM else None
        # the engines (3D, copy, video …) each report a clock; the 3D engine runs fastest
        clocks = []
        for node in range(12):
            n = _NodePerf(NodeOrdinal=node, PhysicalAdapterIndex=0)
            if not self._query(KMTQAITYPE_NODEPERFDATA, n):
                break
            if n.Frequency:
                clocks.append(n.Frequency)
        if clocks:
            out["clock"] = round(max(clocks) / 1e6)
        return out


def _nice_gpu_name(name: str) -> str:
    for junk in ("(R)", "(TM)", "NVIDIA GeForce ", "AMD ", "Graphics"):
        name = name.replace(junk, "" if junk != "NVIDIA GeForce " else "GeForce ")
    return " ".join(name.split()) or "GPU"


class WinGpu:
    """Drop-in for the Linux GPU readers in sensors.py (same dict keys)."""

    def __init__(self, counters: Counters):
        self.counters = counters
        self.gdi = ctypes.WinDLL("gdi32")
        n = _EnumAdapters2(0, None)
        if self.gdi.D3DKMTEnumAdapters2(ctypes.byref(n)) != 0 or not n.NumAdapters:
            raise OSError("no display adapters")
        arr = (_AdapterInfo * n.NumAdapters)()
        n.pAdapters = arr
        if self.gdi.D3DKMTEnumAdapters2(ctypes.byref(n)) != 0:
            raise OSError("D3DKMTEnumAdapters2")
        adapters = [_Adapter(self.gdi, arr[i]) for i in range(n.NumAdapters)]
        real = [a for a in adapters if not a.software and a.name] or adapters
        # the card with the most dedicated memory is the one games run on
        self.adapter = max(real, key=lambda a: (a.vram_total, a.shared_total))
        self.name = _nice_gpu_name(self.adapter.name)

    def read(self) -> dict:
        a, c = self.adapter, self.counters
        # load like Task Manager: per engine, add up every process; the busiest engine wins
        engines: dict[str, float] = {}
        for inst, v in c.read("gpu_engine").items():
            if a.luid in inst.lower():
                eng = re.sub(r"^pid_\d+_", "", inst.lower())
                engines[eng] = engines.get(eng, 0.0) + v
        load = min(100.0, max(engines.values())) if engines else None
        # an integrated GPU uses shared memory (normal RAM) instead of its own VRAM
        used = [v for inst, v in c.read("gpu_shared" if a.integrated else "gpu_mem").items() if a.luid in inst.lower()]
        total = (a.shared_total if a.integrated else a.vram_total) or None
        perf = a.perf()
        return {
            "name": self.name, "load": round(load, 1) if load is not None else None,
            "temp": perf.get("temp"), "temp_hot": None, "power": None,
            "clock": perf.get("clock"), "fan": perf.get("fan"),
            "vram_used": max(used) if used else None, "vram_total": total,
            "integrated": a.integrated,
        }


class WinHardware:
    """One PDH query for everything, sampled once per update."""

    def __init__(self):
        self.lock = threading.Lock()
        self.counters = Counters({
            "gpu_engine": r"\GPU Engine(*)\Utilization Percentage",
            "gpu_mem": r"\GPU Adapter Memory(*)\Dedicated Usage",
            "gpu_shared": r"\GPU Adapter Memory(*)\Shared Usage",
            "zone_hp": r"\Thermal Zone Information(*)\High Precision Temperature",
            "zone": r"\Thermal Zone Information(*)\Temperature",
        })
        self.counters.collect()
        try:
            self.gpu: WinGpu | None = WinGpu(self.counters)
        except (OSError, AttributeError, ValueError):
            self.gpu = None

    def collect(self) -> None:
        with self.lock:
            self.counters.collect()

    def cpu_temp(self) -> float | None:
        """Hottest ACPI thermal zone (°C)."""
        hp = [v / 10 - 273.15 for v in self.counters.read("zone_hp").values() if v > 0]
        k = hp or [v - 273.15 for v in self.counters.read("zone").values() if v > 0]
        # some boards report a fixed 27.85 °C (301 K) placeholder, or nonsense
        k = [t for t in k if 5 < t < 125 and abs(t - 27.85) > 0.1]
        return round(max(k), 1) if k else None


def create() -> WinHardware | None:
    if not IS_WINDOWS:
        return None
    try:
        return WinHardware()
    except (OSError, AttributeError) as e:
        print(f"[phonedeck] Windows-målinger ikke tilgængelige: {e}")
        return None
