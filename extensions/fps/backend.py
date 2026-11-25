"""FPS: how many frames per second the PC shows on screen.

Linux (GNOME): the PhoneDeck GNOME helper counts the frames GNOME presents per monitor
(phonedeck/gnome.py). Windows: DirectX logs every Present() call through Event Tracing
for Windows; etw.py counts them per program (needs "Performance Log Users" once). No
extra programs on either.

Measuring only runs while the phone shows a speedometer: the page sends "watch" every
couple of seconds, and we stop 6 seconds after the last one.
"""

from __future__ import annotations

import sys
import threading
import time
from collections import deque

WATCH_S = 6
HISTORY = 60

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Ratio(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("uiNumerator", ctypes.c_uint32), ("uiDenominator", ctypes.c_uint32)]

    def _timing_struct(pack: int):
        """DWM_TIMING_INFO – dwmapi.h declares it with 1-byte packing."""
        U, Q, R = ctypes.c_uint32, ctypes.c_uint64, _Ratio
        names = [("cbSize", U), ("rateRefresh", R), ("qpcRefreshPeriod", Q), ("rateCompose", R),
                 ("qpcVBlank", Q), ("cRefresh", Q), ("cDXRefresh", U), ("qpcCompose", Q), ("cFrame", Q),
                 ("cDXPresent", U), ("cRefreshFrame", Q), ("cFrameSubmitted", Q), ("cDXPresentSubmitted", U),
                 ("cFrameConfirmed", Q), ("cDXPresentConfirmed", U), ("cRefreshConfirmed", Q),
                 ("cDXRefreshConfirmed", U), ("cFramesLate", Q), ("cFramesOutstanding", U),
                 ("cFrameDisplayed", Q), ("qpcFrameDisplayed", Q), ("cRefreshFrameDisplayed", Q),
                 ("cFrameComplete", Q), ("qpcFrameComplete", Q), ("cFramePending", Q), ("qpcFramePending", Q),
                 ("cFramesDisplayed", Q), ("cFramesComplete", Q), ("cFramesPending", Q),
                 ("cFramesAvailable", Q), ("cFramesDropped", Q), ("cFramesMissed", Q),
                 ("cRefreshNextDisplayed", Q), ("cRefreshNextPresented", Q), ("cRefreshesDisplayed", Q),
                 ("cRefreshesPresented", Q), ("cRefreshStarted", Q), ("cPixelsReceived", Q),
                 ("cPixelsDrawn", Q), ("cBuffersEmpty", Q)]
        return type(f"DwmTiming{pack}", (ctypes.Structure,), {"_pack_": pack, "_fields_": names})

    class _Dwm:
        def __init__(self):
            self.dwm = ctypes.WinDLL("dwmapi")
            self.user = ctypes.WinDLL("user32")
            self.struct = None
            for pack in (1, 8):  # whichever size this Windows accepts
                t = _timing_struct(pack)()
                t.cbSize = ctypes.sizeof(t)
                if self.dwm.DwmGetCompositionTimingInfo(None, ctypes.byref(t)) == 0:
                    self.struct = type(t)
                    break
            if self.struct is None:
                raise OSError("DwmGetCompositionTimingInfo")
            from .etw import PresentCounter
            self.etw = PresentCounter()
            self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self.user.GetForegroundWindow.restype = wintypes.HWND

        def refresh(self) -> float | None:
            """The monitor's refresh rate. (DWM's frame counters no longer move on Windows 11,
            but the refresh rate it reports is right.)"""
            t = self.struct()
            t.cbSize = ctypes.sizeof(t)
            if self.dwm.DwmGetCompositionTimingInfo(None, ctypes.byref(t)) != 0:
                return None
            r = t.rateRefresh
            return round(r.uiNumerator / r.uiDenominator, 1) if r.uiDenominator else None

        def start(self):
            self.etw.start()

        def stop(self):
            self.etw.stop()

        def sample(self) -> dict | None:
            self.etw.start()  # no-op while running
            per_pid = self.etw.fps()
            fg_pid, title = self._foreground()
            # the program in focus; if it draws nothing itself (a browser draws in a helper
            # process), the busiest program
            if per_pid.get(fg_pid):
                fps, pid = per_pid[fg_pid], fg_pid
            elif per_pid:
                pid = max(per_pid, key=per_pid.get)
                fps, title = per_pid[pid], ""
            else:
                fps, pid = 0.0, fg_pid
            return {"fps": fps, "refresh": self.refresh(), "app": title or self._name(pid)}

        @staticmethod
        def _name(pid: int) -> str:
            try:
                import psutil
                return psutil.Process(pid).name().rsplit(".", 1)[0]
            except Exception:
                return ""

        def _foreground(self) -> tuple[int, str]:
            hwnd = self.user.GetForegroundWindow()
            if not hwnd:
                return 0, ""
            buf = ctypes.create_unicode_buffer(256)
            self.user.GetWindowTextW(hwnd, buf, 256)
            pid = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value, buf.value.strip()[:60]


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self._watch = 0.0
        self._wake = threading.Event()
        self.hist: deque = deque(maxlen=HISTORY)
        self.cur: dict = {}
        self.source = None
        self.problem = ""
        if sys.platform == "win32":
            try:
                self.source = _Dwm()
            except (OSError, AttributeError) as e:
                self.problem = f"Windows' billedtæller svarer ikke ({e})"
        threading.Thread(target=self._loop, daemon=True, name="fps").start()

    # ---------- measuring ----------
    def _sample(self) -> dict | None:
        if self.source is not None:
            from .etw import NoPermission
            try:
                s = self.source.sample()
            except NoPermission:
                self.problem = ("Windows kræver adgang til ydelseslogfiler: kør scripts\\allow-fps-windows.ps1 "
                                "én gang og log ud og ind")
                return None
            self.problem = ""
            return s
        from phonedeck import gnome
        if gnome.version() < 2:
            self.problem = ("Opdatér PhoneDeck-hjælperen til GNOME og log ind igen"
                            if gnome.version() == 1 else "Kræver PhoneDeck-hjælperen til GNOME")
            return None
        self.problem = ""
        return gnome.fps()

    def _loop(self):
        while not self.ctx.stopped.is_set():
            if time.monotonic() - self._watch > WATCH_S:
                if self.cur or self.source is not None:
                    self.cur, self.hist = {}, deque(maxlen=HISTORY)
                    if self.source is not None:
                        self.source.stop()  # end the trace session while nobody looks
                self._wake.wait(30)
                self._wake.clear()
                continue
            try:
                s = self._sample()
            except Exception as e:  # never let a driver hiccup kill the thread
                s, self.problem = None, str(e)
            if s:
                self.cur = s
                if s.get("fps") is not None:
                    self.hist.append(round(s["fps"], 1))
            self.ctx.stopped.wait(1.0)

    # ---------- extension API ----------
    def action(self, name, body):
        if name == "watch":
            first = time.monotonic() - self._watch > WATCH_S
            self._watch = time.monotonic()
            if first:
                self._wake.set()
            return {}
        raise ValueError("ukendt handling")

    def state(self):
        s = self.ctx.settings()
        vals = [v for v in self.hist if v is not None]
        try:
            top = int(s.get("max") or 0)
        except (TypeError, ValueError):
            top = 0
        low = self.ctx.number("low", 30)
        return {
            "fps": self.cur.get("fps"), "refresh": self.cur.get("refresh"), "app": self.cur.get("app") or "",
            "avg": sum(vals) / len(vals) if vals else None, "min": min(vals) if vals else None,
            "history": list(self.hist), "max": top or None,
            "low": low, "ok": max(low + 1, self.ctx.number("ok", 60)),
            "status": "" if self.cur else ("måler …" if not self.problem else "ingen måling"),
        }

    def info(self):
        if self.problem:
            return {"status": "⚠ " + self.problem}
        if self.source is not None:
            return {"status": "✓ Måler med Windows' hændelseslog for DirectX (ETW)"}
        from phonedeck import gnome
        v = gnome.version()
        if v >= 2:
            return {"status": "✓ PhoneDeck-hjælperen til GNOME er klar"}
        return {"status": "⚠ " + ("Hjælperen er for gammel – kør scripts/install-gnome-helper.sh og log ind igen"
                                  if v == 1 else "Installér hjælperen: scripts/install-gnome-helper.sh, og log ind igen")}

    def stop(self):
        self._wake.set()
        if self.source is not None:
            self.source.stop()
