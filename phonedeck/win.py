"""Windows helpers (ctypes only – nothing to install): keys, media/volume keys, visible
windows, locking the screen. Optional: pycaw for reading volume and muting the microphone.

Only imported on Windows.
"""

from __future__ import annotations

import ctypes
import gc
import os
import queue
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

KEYEVENTF_EXTENDEDKEY = 0x1
KEYEVENTF_KEYUP = 0x2

# Linux input key codes (what the editor stores, so buttons work on both systems) -> Windows VK
EVDEV_TO_VK = {
    1: 0x1B, 11: 0x30, 12: 0xBD, 13: 0xBB, 14: 0x08, 15: 0x09, 26: 0xDB, 27: 0xDD, 28: 0x0D,
    29: 0xA2, 39: 0xBA, 40: 0xDE, 41: 0xC0, 42: 0xA0, 43: 0xDC, 51: 0xBC, 52: 0xBE, 53: 0xBF,
    54: 0xA1, 55: 0x6A, 56: 0xA4, 57: 0x20, 58: 0x14, 69: 0x90, 70: 0x91,
    71: 0x67, 72: 0x68, 73: 0x69, 74: 0x6D, 75: 0x64, 76: 0x65, 77: 0x66, 78: 0x6B,
    79: 0x61, 80: 0x62, 81: 0x63, 82: 0x60, 83: 0x6E, 86: 0xE2, 87: 0x7A, 88: 0x7B,
    96: 0x0D, 97: 0xA3, 98: 0x6F, 99: 0x2C, 100: 0xA5, 102: 0x24, 103: 0x26, 104: 0x21,
    105: 0x25, 106: 0x27, 107: 0x23, 108: 0x28, 109: 0x22, 110: 0x2D, 111: 0x2E,
    113: 0xAD, 114: 0xAE, 115: 0xAF, 119: 0x13, 125: 0x5B, 126: 0x5C, 127: 0x5D,
    163: 0xB0, 164: 0xB3, 165: 0xB1,
}
EVDEV_TO_VK.update({2 + i: 0x31 + i for i in range(9)})                       # 1-9
EVDEV_TO_VK.update({59 + i: 0x70 + i for i in range(10)})                     # F1-F10
EVDEV_TO_VK.update({183 + i: 0x7C + i for i in range(12)})                    # F13-F24
for codes, letters in (((16, 25), "QWERTYUIOP"), ((30, 38), "ASDFGHJKL"), ((44, 50), "ZXCVBNM")):
    for code, letter in zip(range(codes[0], codes[1] + 1), letters):
        EVDEV_TO_VK[code] = ord(letter)
EXTENDED = {0xA3, 0xA5, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x6F, 0x5B, 0x5C, 0x5D,
            0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB3, 0x2C}

VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB3


def _key(vk: int, up: bool) -> None:
    flags = (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0) | (KEYEVENTF_KEYUP if up else 0)
    scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
    user32.keybd_event(vk, scan, flags, 0)


def tap(vk: int) -> None:
    _key(vk, False)
    _key(vk, True)


def send_keys(evdev_codes: list[int]) -> None:
    """Press in order, release in reverse – e.g. [29, 46] = Ctrl+C."""
    vks = []
    for code in evdev_codes:
        vk = EVDEV_TO_VK.get(code)
        if vk is None:
            raise ValueError(f"tasten #{code} findes ikke på Windows")
        vks.append(vk)
    for vk in vks:
        _key(vk, False)
    for vk in reversed(vks):
        _key(vk, True)


def lock_screen() -> None:
    user32.LockWorkStation()


def open_target(target: str) -> None:
    """A URL, a document or a shortcut (.lnk) – like double-clicking it."""
    os.startfile(target)  # noqa: S606 (Windows only)


# ---------- which programs have a visible window (for "Aktiv") ----------
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def visible_window_pids() -> set[int]:
    pids: set[int] = set()

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER: skip tool windows
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        cloaked = ctypes.c_int(0)  # hidden UWP / other-desktop windows
        dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pids.add(pid.value)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return pids


# ---------- audio: volume level and microphone (optional pycaw) ----------
# All COM objects live on ONE thread that initialised COM. If a comtypes pointer is
# released on another thread (e.g. when the garbage collector happens to run in the
# visualizer thread), Windows kills the whole process with an access violation.
class _AudioCom:
    REFRESH = 30  # seconds before looking up the endpoints again (default device may change)

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def call(self, fn, timeout: float = 3):
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="audio-com", daemon=True)
                self._thread.start()
        done, box = threading.Event(), {}
        self._jobs.put((fn, done, box))
        if not done.wait(timeout):
            raise TimeoutError("lyd svarer ikke")
        if "error" in box:
            raise box["error"]
        return box["value"]

    def _run(self):
        try:
            import comtypes  # type: ignore
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except (ImportError, OSError):
            pass
        cache: dict = {}
        fetched = 0.0
        while True:
            fn, done, box = self._jobs.get()
            if time.monotonic() - fetched > self.REFRESH:
                cache.clear()
                gc.collect()  # free old COM objects here, on this thread
                fetched = time.monotonic()
            try:
                before = len(cache)
                box["value"] = fn(lambda capture: self._endpoint(cache, capture))
                if len(cache) != before:
                    gc.collect()  # temporaries from the device lookup, also freed on this thread
            except Exception as e:
                cache.clear()
                gc.collect()
                box["error"] = e
            done.set()

    @staticmethod
    def _endpoint(cache: dict, capture: bool):
        if capture in cache:
            return cache[capture]
        try:
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
        except ImportError:
            return None
        dev = AudioUtilities.GetMicrophone() if capture else AudioUtilities.GetSpeakers()
        if dev is None:
            ep = None
        elif hasattr(dev, "EndpointVolume"):  # pycaw 20240210+ wraps the device in AudioDevice
            ep = dev.EndpointVolume
        else:
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            ep = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))
        cache[capture] = ep
        return ep


_audio = _AudioCom()


def audio_level(capture: bool = False) -> dict:
    def read(endpoint):
        ep = endpoint(capture)
        if ep is None:
            return {"volume": None, "muted": False}
        return {"volume": round(ep.GetMasterVolumeLevelScalar() * 100), "muted": bool(ep.GetMute())}
    try:
        return _audio.call(read)
    except Exception:  # optional feature: never let it break the whole sample
        return {"volume": None, "muted": False}


def toggle_mic_mute() -> None:
    def toggle(endpoint):
        ep = endpoint(True)
        if ep is None:
            return False
        ep.SetMute(0 if ep.GetMute() else 1, None)
        return True
    if not _audio.call(toggle):
        raise ValueError("Mikrofon-mute kræver pycaw på Windows: pip install pycaw")


# ---------- clipboard (text) ----------
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL


def get_clipboard_text() -> str | None:
    if not user32.OpenClipboard(None):
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p) if p else None
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, data, size)
    kernel32.GlobalUnlock(h)
    if not user32.OpenClipboard(None):
        raise ValueError("udklipsholderen er optaget – prøv igen")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, h)  # Windows owns the memory from here
    finally:
        user32.CloseClipboard()
