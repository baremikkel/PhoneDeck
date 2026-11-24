"""Now playing on Windows: the system media controls (the same list the volume pop-up shows).

Needs the optional package ``winrt-Windows.Media.Control`` (or the older ``winsdk``):

    pip install winrt-Windows.Media.Control winrt-Windows.Storage.Streams winrt-Windows.Foundation

Without it, play/pause/next/previous still work through the media keys, but the phone
can't show the title or cover.
"""

from __future__ import annotations

import asyncio
import threading

_IMPORT_ERROR = "installer winrt-Windows.Media.Control for at se hvad der spiller"
try:  # newer split packages first, then the older all-in-one
    from winrt.windows.media.control import \
        GlobalSystemMediaTransportControlsSessionManager as Manager  # type: ignore
    from winrt.windows.storage.streams import Buffer, InputStreamOptions  # type: ignore
except ImportError as e:
    if "DLL load failed" in str(e):  # installed, but Windows refused to load it
        # e.g. Smart App Control / an application control policy blocking the unsigned .pyd
        _IMPORT_ERROR = f"Windows blokerede winrt ({str(e).split(':', 1)[-1].strip()})"
        print(f"[phonedeck] music: winrt kunne ikke indlæses: {e}")
    try:
        from winsdk.windows.media.control import \
            GlobalSystemMediaTransportControlsSessionManager as Manager  # type: ignore
        from winsdk.windows.storage.streams import Buffer, InputStreamOptions  # type: ignore
    except ImportError:
        Manager = None

from phonedeck import win

PLAYING, PAUSED = 4, 5
BROWSERS = ("firefox", "chrome", "msedge", "brave", "opera", "vivaldi")


class Media:
    source = "spotify"

    def __init__(self):
        self.error = None if Manager else _IMPORT_ERROR
        self.current_player = None
        self._session = None
        self._art: tuple[str, bytes, str] | None = None
        self._art_key = None
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    def _run(self, coro, timeout=3):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _wanted(self, app_id: str) -> bool:
        a = app_id.lower()
        if self.source == "spotify":
            return "spotify" in a
        if self.source == "no_browser":
            return not any(b in a for b in BROWSERS)
        return True

    async def _pick(self):
        mgr = await Manager.request_async()
        sessions = [s for s in mgr.get_sessions() if self._wanted(s.source_app_user_model_id or "")]
        if not sessions:
            return None

        def rank(s):
            st = s.get_playback_info().playback_status
            return (st == PLAYING, st == PAUSED, "spotify" in (s.source_app_user_model_id or "").lower())
        return max(sessions, key=rank)

    async def _state(self):
        s = await self._pick()
        self._session = s
        if s is None:
            return None
        props = await s.try_get_media_properties_async()
        info, tl = s.get_playback_info(), s.get_timeline_properties()
        app = (s.source_app_user_model_id or "").split("!")[0]
        self.current_player = app
        key = f"{props.title}|{props.artist}"
        if props.thumbnail and key != self._art_key:
            self._art_key = key
            try:
                stream = await props.thumbnail.open_read_async()
                buf = Buffer(stream.size)
                await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
                self._art = (key, bytes(buf), stream.content_type or "image/jpeg")
            except Exception:  # noqa: BLE001 – a missing cover is fine
                self._art = None
        status = {PLAYING: "Playing", PAUSED: "Paused"}.get(info.playback_status, "Stopped")
        return {
            "player": app.replace(".exe", "").split(".")[-1] if "." in app else app,
            "status": status, "title": props.title, "artist": props.artist, "album": props.album_title,
            "length": tl.end_time.total_seconds() if tl.end_time else 0,
            "position": tl.position.total_seconds() if tl.position else 0,
            "volume": None,   # Windows doesn't expose a per-player volume here (see the Lyd page)
            "art": bool(props.thumbnail), "art_key": key if props.thumbnail else None,
        }

    def state(self):
        if Manager is None:
            return {"error": self.error}
        try:
            return self._run(self._state())
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:120]}

    def command(self, method: str) -> None:
        if method not in ("PlayPause", "Next", "Previous"):
            raise ValueError(method)
        s = self._session
        if Manager is None or s is None:
            win.tap({"PlayPause": win.VK_MEDIA_PLAY_PAUSE, "Next": win.VK_MEDIA_NEXT, "Previous": win.VK_MEDIA_PREV}[method])
            return
        call = {"PlayPause": s.try_toggle_play_pause_async, "Next": s.try_skip_next_async,
                "Previous": s.try_skip_previous_async}[method]

        async def go():
            await call()
        self._run(go())

    def set_volume(self, delta: float) -> int:
        raise ValueError("På Windows styres afspillerens lydstyrke fra Windows' lydmixer")

    def art(self):
        if self._art and self._art[0] == self._art_key:
            return self._art[1], self._art[2]
        return None
