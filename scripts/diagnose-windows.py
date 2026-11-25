"""Shows what Windows tells PhoneDeck about the GPU, temperatures and frame rate.

    py scripts\\diagnose-windows.py

Paste the output into the issue/chat. It only reads; nothing is changed.
"""

import ctypes
import importlib.util
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if sys.platform != "win32":
    sys.exit("Kun til Windows.")

from phonedeck import winhw as w  # noqa: E402


def line(title):
    print("\n=== " + title + " " + "=" * max(0, 60 - len(title)))


line("System")
print(sys.version.split()[0], sys.getwindowsversion())

line("Skærmkort (D3DKMT)")
gdi = ctypes.WinDLL("gdi32")
n = w._EnumAdapters2(0, None)
rc = gdi.D3DKMTEnumAdapters2(ctypes.byref(n))
print(f"EnumAdapters2 rc=0x{rc & 0xFFFFFFFF:08x} antal={n.NumAdapters}")
arr = (w._AdapterInfo * max(1, n.NumAdapters))()
n.pAdapters = arr
gdi.D3DKMTEnumAdapters2(ctypes.byref(n))
print(f"sizeof AdapterPerf={ctypes.sizeof(w._AdapterPerf)} NodePerf={ctypes.sizeof(w._NodePerf)}")
for i in range(n.NumAdapters):
    a = w._Adapter(gdi, arr[i])
    print(f"\n[{i}] {a.name!r} {a.luid} software={a.software} integrated={a.integrated}")
    print(f"    dedikeret={a.vram_total / 2**20:.0f} MiB delt={a.shared_total / 2**20:.0f} MiB")
    p = w._AdapterPerf(PhysicalAdapterIndex=0)
    q = w._QueryAdapterInfo(a.h, w.KMTQAITYPE_ADAPTERPERFDATA, ctypes.cast(ctypes.byref(p), ctypes.c_void_p), ctypes.sizeof(p))
    rc = gdi.D3DKMTQueryAdapterInfo(ctypes.byref(q))
    print(f"    ADAPTERPERFDATA rc=0x{rc & 0xFFFFFFFF:08x} temp={p.Temperature} (1/10 °C) fan={p.FanRPM} rpm "
          f"power={p.Power} memfreq={p.MemoryFrequency}")
    for node in range(12):
        np_ = w._NodePerf(NodeOrdinal=node, PhysicalAdapterIndex=0)
        q = w._QueryAdapterInfo(a.h, w.KMTQAITYPE_NODEPERFDATA, ctypes.cast(ctypes.byref(np_), ctypes.c_void_p), ctypes.sizeof(np_))
        rc = gdi.D3DKMTQueryAdapterInfo(ctypes.byref(q))
        if rc != 0:
            print(f"    node {node}: rc=0x{rc & 0xFFFFFFFF:08x} (stop)")
            break
        print(f"    node {node}: {np_.Frequency / 1e6:.0f} MHz (max {np_.MaxFrequency / 1e6:.0f})")

line("Ydelsestællere (PDH)")
hw = w.create()
if not hw:
    print("WinHardware kunne ikke starte")
else:
    for _ in range(3):
        hw.collect()
        time.sleep(1)
    for key in hw.counters.counters:
        vals = hw.counters.read(key)
        top = sorted(vals.items(), key=lambda kv: -kv[1])[:4]
        print(f"{key}: {len(vals)} instanser; største: {[(k[-60:], round(v, 1)) for k, v in top]}")
    missing = {"gpu_engine", "gpu_mem", "gpu_shared", "zone_hp", "zone"} - set(hw.counters.counters)
    if missing:
        print("mangler:", ", ".join(sorted(missing)))
    print("CPU-temperatur:", hw.cpu_temp())
    print("GPU:", hw.gpu.read() if hw.gpu else None)

line("FPS (DWM) – flyt et vindue rundt i 5 sekunder nu")
spec = importlib.util.spec_from_file_location("fps_backend", os.path.join(ROOT, "extensions", "fps", "backend.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
try:
    d = fb._Dwm()
    print(f"struct={d.struct.__name__} størrelse={ctypes.sizeof(d.struct)}")
    prev = None
    for _ in range(6):
        t = d.struct()
        t.cbSize = ctypes.sizeof(t)
        rc = d.dwm.DwmGetCompositionTimingInfo(None, ctypes.byref(t))
        cur = {k: getattr(t, k) for k in ("cRefresh", "cFrame", "cDXPresent", "cFramesDisplayed", "cRefreshesDisplayed", "cFrameDisplayed")}
        rate = t.rateRefresh
        if prev:
            print(f"rc=0x{rc & 0xFFFFFFFF:08x} hz={rate.uiNumerator}/{rate.uiDenominator} "
                  + " ".join(f"{k}+{cur[k] - prev[k]}" for k in cur))
        prev = cur
        time.sleep(1)
except Exception as e:
    print("DWM fejl:", e)
