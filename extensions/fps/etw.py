"""Frame rate on Windows from Event Tracing for Windows (ETW) – no extra programs.

Every time a DirectX program shows a frame it calls Present(), and the DXGI (DirectX
10/11/12) and Direct3D 9 runtimes log an event for it. We listen to those events in a
small real-time trace session and count them per process: frames per second for the
game in focus. It works the same on AMD, Intel and NVIDIA, in a window and in exclusive
full screen. (This is the same source PresentMon and game overlays use.)

A real-time trace needs administrator rights or membership of the built-in group
"Performance Log Users" (SID S-1-5-32-559). scripts/allow-fps-windows.ps1 adds your user
once; log out and in afterwards.
"""

from __future__ import annotations

import ctypes
import threading
import time
from collections import defaultdict, deque
from ctypes import wintypes

SESSION = "PhoneDeck-FPS"

WNODE_FLAG_TRACED_GUID = 0x00020000
EVENT_TRACE_REAL_TIME_MODE = 0x00000100
EVENT_TRACE_CONTROL_STOP = 1
EVENT_CONTROL_CODE_ENABLE_PROVIDER = 1
TRACE_LEVEL_INFORMATION = 4
PROCESS_TRACE_MODE_REAL_TIME = 0x00000100
PROCESS_TRACE_MODE_EVENT_RECORD = 0x10000000
INVALID_PROCESSTRACE_HANDLE = 0xFFFFFFFFFFFFFFFF
ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str) -> "GUID":
        h = s.strip("{}").replace("-", "")
        return cls(int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16),
                   (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:32])))

    def key(self) -> tuple:
        return (self.Data1, self.Data2, self.Data3, bytes(self.Data4))


# Present events: provider -> event ids that mean "a frame was handed over"
DXGI = GUID.parse("CA11C036-0102-4A2D-A6AD-F03CFED5D3C9")   # Present_Start, PresentMultiplaneOverlay_Start
D3D9 = GUID.parse("783ACA0A-790E-4D7F-8451-AA850511C6B9")   # Present_Start
PRESENT_IDS = {DXGI.key(): {42, 55}, D3D9.key(): {1}}


class WNODE_HEADER(ctypes.Structure):
    _fields_ = [("BufferSize", wintypes.ULONG), ("ProviderId", wintypes.ULONG),
                ("HistoricalContext", ctypes.c_uint64), ("TimeStamp", ctypes.c_int64),
                ("Guid", GUID), ("ClientContext", wintypes.ULONG), ("Flags", wintypes.ULONG)]


class EVENT_TRACE_PROPERTIES(ctypes.Structure):
    _fields_ = [("Wnode", WNODE_HEADER), ("BufferSize", wintypes.ULONG), ("MinimumBuffers", wintypes.ULONG),
                ("MaximumBuffers", wintypes.ULONG), ("MaximumFileSize", wintypes.ULONG),
                ("LogFileMode", wintypes.ULONG), ("FlushTimer", wintypes.ULONG), ("EnableFlags", wintypes.ULONG),
                ("AgeLimit", wintypes.LONG), ("NumberOfBuffers", wintypes.ULONG), ("FreeBuffers", wintypes.ULONG),
                ("EventsLost", wintypes.ULONG), ("BuffersWritten", wintypes.ULONG),
                ("LogBuffersLost", wintypes.ULONG), ("RealTimeBuffersLost", wintypes.ULONG),
                ("LoggerThreadId", wintypes.HANDLE), ("LogFileNameOffset", wintypes.ULONG),
                ("LoggerNameOffset", wintypes.ULONG)]


class _Props(ctypes.Structure):
    """EVENT_TRACE_PROPERTIES followed by room for the session name."""
    _fields_ = [("p", EVENT_TRACE_PROPERTIES), ("name", ctypes.c_wchar * 1024)]


def _props() -> _Props:
    b = _Props()
    b.p.Wnode.BufferSize = ctypes.sizeof(b)
    b.p.Wnode.Flags = WNODE_FLAG_TRACED_GUID
    b.p.Wnode.ClientContext = 1  # QPC timestamps
    b.p.LogFileMode = EVENT_TRACE_REAL_TIME_MODE
    b.p.FlushTimer = 1           # deliver events at least once a second
    b.p.LoggerNameOffset = ctypes.sizeof(EVENT_TRACE_PROPERTIES)
    return b


class EVENT_TRACE_HEADER(ctypes.Structure):
    _fields_ = [("Size", wintypes.USHORT), ("FieldTypeFlags", wintypes.USHORT), ("Version", wintypes.ULONG),
                ("ThreadId", wintypes.ULONG), ("ProcessId", wintypes.ULONG), ("TimeStamp", ctypes.c_int64),
                ("Guid", GUID), ("ProcessorTime", ctypes.c_uint64)]


class EVENT_TRACE(ctypes.Structure):
    _fields_ = [("Header", EVENT_TRACE_HEADER), ("InstanceId", wintypes.ULONG),
                ("ParentInstanceId", wintypes.ULONG), ("ParentGuid", GUID), ("MofData", ctypes.c_void_p),
                ("MofLength", wintypes.ULONG), ("ClientContext", wintypes.ULONG)]


class TRACE_LOGFILE_HEADER(ctypes.Structure):
    _fields_ = [("BufferSize", wintypes.ULONG), ("Version", wintypes.ULONG), ("ProviderVersion", wintypes.ULONG),
                ("NumberOfProcessors", wintypes.ULONG), ("EndTime", ctypes.c_int64),
                ("TimerResolution", wintypes.ULONG), ("MaximumFileSize", wintypes.ULONG),
                ("LogFileMode", wintypes.ULONG), ("BuffersWritten", wintypes.ULONG), ("LogInstanceGuid", GUID),
                ("LoggerName", ctypes.c_void_p), ("LogFileName", ctypes.c_void_p),
                ("TimeZone", ctypes.c_ubyte * 172), ("BootTime", ctypes.c_int64), ("PerfFreq", ctypes.c_int64),
                ("StartTime", ctypes.c_int64), ("ReservedFlags", wintypes.ULONG), ("BuffersLost", wintypes.ULONG)]


class EVENT_DESCRIPTOR(ctypes.Structure):
    _fields_ = [("Id", wintypes.USHORT), ("Version", ctypes.c_ubyte), ("Channel", ctypes.c_ubyte),
                ("Level", ctypes.c_ubyte), ("Opcode", ctypes.c_ubyte), ("Task", wintypes.USHORT),
                ("Keyword", ctypes.c_uint64)]


class EVENT_HEADER(ctypes.Structure):
    _fields_ = [("Size", wintypes.USHORT), ("HeaderType", wintypes.USHORT), ("Flags", wintypes.USHORT),
                ("EventProperty", wintypes.USHORT), ("ThreadId", wintypes.ULONG), ("ProcessId", wintypes.ULONG),
                ("TimeStamp", ctypes.c_int64), ("ProviderId", GUID), ("EventDescriptor", EVENT_DESCRIPTOR),
                ("ProcessorTime", ctypes.c_uint64), ("ActivityId", GUID)]


class EVENT_RECORD(ctypes.Structure):
    _fields_ = [("EventHeader", EVENT_HEADER), ("BufferContext", wintypes.ULONG),
                ("ExtendedDataCount", wintypes.USHORT), ("UserDataLength", wintypes.USHORT),
                ("ExtendedData", ctypes.c_void_p), ("UserData", ctypes.c_void_p), ("UserContext", ctypes.c_void_p)]


EVENT_RECORD_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.POINTER(EVENT_RECORD))


class EVENT_TRACE_LOGFILEW(ctypes.Structure):
    _fields_ = [("LogFileName", wintypes.LPWSTR), ("LoggerName", wintypes.LPWSTR), ("CurrentTime", ctypes.c_int64),
                ("BuffersRead", wintypes.ULONG), ("ProcessTraceMode", wintypes.ULONG),
                ("CurrentEvent", EVENT_TRACE), ("LogfileHeader", TRACE_LOGFILE_HEADER),
                ("BufferCallback", ctypes.c_void_p), ("BufferSize", wintypes.ULONG), ("Filled", wintypes.ULONG),
                ("EventsLost", wintypes.ULONG), ("EventRecordCallback", EVENT_RECORD_CALLBACK),
                ("IsKernelTrace", wintypes.ULONG), ("Context", ctypes.c_void_p)]


class NoPermission(Exception):
    pass


class PresentCounter:
    """Counts Present() calls per process id while running."""

    def __init__(self):
        self.adv = ctypes.WinDLL("advapi32")
        self.adv.StartTraceW.argtypes = [ctypes.POINTER(ctypes.c_uint64), wintypes.LPCWSTR, ctypes.c_void_p]
        self.adv.ControlTraceW.argtypes = [ctypes.c_uint64, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.ULONG]
        self.adv.EnableTraceEx2.argtypes = [ctypes.c_uint64, ctypes.POINTER(GUID), wintypes.ULONG, ctypes.c_ubyte,
                                            ctypes.c_uint64, ctypes.c_uint64, wintypes.ULONG, ctypes.c_void_p]
        self.adv.OpenTraceW.argtypes = [ctypes.POINTER(EVENT_TRACE_LOGFILEW)]
        self.adv.OpenTraceW.restype = ctypes.c_uint64
        self.adv.ProcessTrace.argtypes = [ctypes.POINTER(ctypes.c_uint64), wintypes.ULONG, ctypes.c_void_p, ctypes.c_void_p]
        self.adv.CloseTrace.argtypes = [ctypes.c_uint64]
        self.lock = threading.Lock()
        self.frames: dict[int, deque] = defaultdict(lambda: deque(maxlen=2000))
        self.session = ctypes.c_uint64(0)
        self.trace = ctypes.c_uint64(INVALID_PROCESSTRACE_HANDLE)
        self.thread: threading.Thread | None = None
        self._cb = EVENT_RECORD_CALLBACK(self._on_event)  # keep a reference: ETW calls it from C
        self.events = 0

    # ---------- the session ----------
    def _stop_session(self) -> None:
        b = _props()
        self.adv.ControlTraceW(0, SESSION, ctypes.byref(b), EVENT_TRACE_CONTROL_STOP)

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        b = _props()
        rc = self.adv.StartTraceW(ctypes.byref(self.session), SESSION, ctypes.byref(b))
        if rc == ERROR_ALREADY_EXISTS:  # left over after PhoneDeck was killed
            self._stop_session()
            b = _props()
            rc = self.adv.StartTraceW(ctypes.byref(self.session), SESSION, ctypes.byref(b))
        if rc == ERROR_ACCESS_DENIED:
            raise NoPermission()
        if rc != 0:
            raise OSError(f"StartTrace fejlede ({rc})")
        for guid in (DXGI, D3D9):
            self.adv.EnableTraceEx2(self.session, ctypes.byref(guid), EVENT_CONTROL_CODE_ENABLE_PROVIDER,
                                    TRACE_LEVEL_INFORMATION, 0, 0, 0, None)
        log = EVENT_TRACE_LOGFILEW()
        log.LoggerName = SESSION
        log.ProcessTraceMode = PROCESS_TRACE_MODE_REAL_TIME | PROCESS_TRACE_MODE_EVENT_RECORD
        log.EventRecordCallback = self._cb
        h = self.adv.OpenTraceW(ctypes.byref(log))
        if h == INVALID_PROCESSTRACE_HANDLE:
            self._stop_session()
            raise OSError(f"OpenTrace fejlede ({ctypes.GetLastError()})")
        self.trace = ctypes.c_uint64(h)
        # ProcessTrace blocks until the session stops, calling _on_event for every event
        self.thread = threading.Thread(target=self.adv.ProcessTrace, args=(ctypes.byref(self.trace), 1, None, None),
                                       daemon=True, name="fps-etw")
        self.thread.start()

    def stop(self) -> None:
        if self.trace.value != INVALID_PROCESSTRACE_HANDLE:
            self.adv.CloseTrace(self.trace)
            self.trace = ctypes.c_uint64(INVALID_PROCESSTRACE_HANDLE)
        self._stop_session()
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        with self.lock:
            self.frames.clear()

    # ---------- counting ----------
    def _on_event(self, rec) -> None:
        h = rec.contents.EventHeader
        ids = PRESENT_IDS.get(h.ProviderId.key())
        if ids and h.EventDescriptor.Id in ids:
            self.events += 1
            with self.lock:
                self.frames[h.ProcessId].append(time.monotonic())

    def fps(self, window: float = 1.0) -> dict[int, float]:
        """Frames per second per process over the last `window` seconds."""
        cut = time.monotonic() - window
        out = {}
        with self.lock:
            for pid, stamps in list(self.frames.items()):
                while stamps and stamps[0] < cut:
                    stamps.popleft()
                if stamps:
                    out[pid] = len(stamps) / window
                else:
                    del self.frames[pid]
        return out
