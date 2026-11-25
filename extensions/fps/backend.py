"""FPS: how many frames per second the PC shows on screen.

Linux (GNOME): the PhoneDeck GNOME helper counts the frames GNOME presents per monitor
(phonedeck/gnome.py). Windows: the desktop compositor's own frame counter
(DwmGetCompositionTimingInfo in dwmapi.dll) – no extra programs on either.

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
            self.prev: tuple[int, float] | None = None

        def sample(self) -> dict | None:
            t = self.struct()
            t.cbSize = ctypes.sizeof(t)
            if self.dwm.DwmGetCompositionTimingInfo(None, ctypes.byref(t)) != 0:
                return None
            now = time.monotonic()
            frames = t.cFrame
            fps = None
            if self.prev and now > self.prev[1]:
                fps = max(0.0, (frames - self.prev[0]) / (now - self.prev[1]))
            self.prev = (frames, now)
            r = t.rateRefresh
            hz = r.uiNumerator / r.uiDenominator if r.uiDenominator else None
            return {"fps": fps, "refresh": hz, "app": self._foreground()}

        def _foreground(self) -> str:
            hwnd = self.user.GetForegroundWindow()
            if not hwnd:
                return ""
            buf = ctypes.create_unicode_buffer(256)
            self.user.GetWindowTextW(hwnd, buf, 256)
            title = buf.value.strip()
            pid = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                import psutil
                name = psutil.Process(pid.value).name().rsplit(".", 1)[0]
            except Exception:
                name = ""
            return title[:60] or name


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
            return self.source.sample()
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
                if self.cur:
                    self.cur, self.hist = {}, deque(maxlen=HISTORY)
                    if self.source is not None:
                        self.source.prev = None
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
            return {"status": "✓ Måler med Windows' compositor (DWM)"}
        from phonedeck import gnome
        v = gnome.version()
        if v >= 2:
            return {"status": "✓ PhoneDeck-hjælperen til GNOME er klar"}
        return {"status": "⚠ " + ("Hjælperen er for gammel – kør scripts/install-gnome-helper.sh og log ind igen"
                                  if v == 1 else "Installér hjælperen: scripts/install-gnome-helper.sh, og log ind igen")}

    def stop(self):
        self._wake.set()
