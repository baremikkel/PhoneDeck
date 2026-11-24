"""Lyd: volume per program, choosing the output/input device, a microphone level
meter and push-to-talk – all through PipeWire (pw-dump, wpctl, pw-record)."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time

from .mic import MicMeter

CACHE_S = 1.5        # pw-dump at most this often
PTT_LEASE = 2.5      # push-to-talk mutes again if the phone stops holding for this long
MAX_VOLUME = 1.5     # 150 %, like GNOME's "over-amplification"


def _run(*args: str, timeout: float = 2) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _volume(props: list) -> tuple[int | None, bool]:
    """PipeWire stores linear channel volumes; wpctl/GNOME show the cube root."""
    for p in props or []:
        vols = p.get("channelVolumes")
        if vols:
            return round((max(vols) ** (1 / 3)) * 100), bool(p.get("mute"))
    return None, False


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.ok = bool(shutil.which("pw-dump") and shutil.which("wpctl"))
        self._cache: tuple[float, dict] = (0.0, {})
        self._lock = threading.Lock()
        self.mic = MicMeter()
        self._ptt_until = 0.0
        self._ptt_on = False
        threading.Thread(target=self._ptt_watch, daemon=True).start()

    # ---------- reading ----------
    def _scan(self) -> dict:
        with self._lock:
            at, data = self._cache
            if time.monotonic() - at < CACHE_S:
                return data
            try:
                dump = json.loads(_run("pw-dump", timeout=3) or "[]")
            except ValueError:
                dump = []
            defaults = {}
            for o in dump:
                if o.get("type") == "PipeWire:Interface:Metadata":
                    for m in o.get("metadata") or []:
                        if m.get("key") in ("default.audio.sink", "default.audio.source"):
                            v = m.get("value")
                            defaults[m["key"]] = v.get("name") if isinstance(v, dict) else None
            apps, outputs, inputs = [], [], []
            for o in dump:
                if o.get("type") != "PipeWire:Interface:Node":
                    continue
                info = o.get("info") or {}
                p = info.get("props") or {}
                cls = p.get("media.class") or ""
                vol, muted = _volume((info.get("params") or {}).get("Props"))
                if cls == "Stream/Output/Audio":
                    name = p.get("application.name") or p.get("node.description") or p.get("node.name") or "?"
                    if (p.get("node.name") or "").startswith("phonedeck-"):
                        continue
                    apps.append({"id": o["id"], "name": name, "media": p.get("media.name") or "",
                                 "binary": p.get("application.process.binary") or "",
                                 "volume": vol, "muted": muted})
                elif cls in ("Audio/Sink", "Audio/Source"):
                    dev = {"id": o["id"], "name": p.get("node.description") or p.get("node.nick") or p.get("node.name"),
                           "volume": vol, "muted": muted,
                           "default": p.get("node.name") == defaults.get(
                               "default.audio.sink" if cls == "Audio/Sink" else "default.audio.source")}
                    (outputs if cls == "Audio/Sink" else inputs).append(dev)
            # the same program often has several streams (e.g. a browser) – keep them apart but sorted
            apps.sort(key=lambda a: (a["name"].lower(), a["id"]))
            data = {"apps": apps, "outputs": outputs, "inputs": inputs}
            self._cache = (time.monotonic(), data)
            return data

    def state(self):
        if not self.ok:
            return {"error": "kræver PipeWire (pw-dump og wpctl)"}
        d = dict(self._scan())
        d["ptt"] = self._ptt_on
        d["step"] = int(self.ctx.settings().get("step") or 5)
        d["max"] = round(self._max_volume() * 100)
        return d

    def _max_volume(self) -> float:
        return self.ctx.number("max_volume", MAX_VOLUME * 100) / 100

    # ---------- actions ----------
    def _node(self, body, kinds=("apps", "outputs", "inputs")) -> int:
        try:
            nid = int((body or {}).get("id"))
        except (TypeError, ValueError):
            raise ValueError("ugyldig enhed") from None
        data = self._scan()
        if not any(n["id"] == nid for k in kinds for n in data[k]):
            self._cache = (0.0, {})  # maybe it just appeared – look again
            data = self._scan()
            if not any(n["id"] == nid for k in kinds for n in data[k]):
                raise ValueError("enheden findes ikke længere")
        return nid

    def _after(self):
        self._cache = (0.0, {})  # show the change at once
        return self.state()

    def action(self, name, body):
        if not self.ok:
            raise ValueError("kræver PipeWire (pw-dump og wpctl)")
        body = body or {}
        if name == "volume":   # {id, value: 0-max}
            nid = self._node(body)
            try:
                v = max(0.0, min(self._max_volume(), float(body.get("value")) / 100))
            except (TypeError, ValueError):
                raise ValueError("ugyldig lydstyrke") from None
            _run("wpctl", "set-volume", str(nid), f"{v:.2f}")
            return self._after()
        if name == "step":     # {id, delta: -25..25}
            nid = self._node(body)
            try:
                d = max(-25, min(25, int(body.get("delta"))))
            except (TypeError, ValueError):
                raise ValueError("ugyldigt trin") from None
            _run("wpctl", "set-volume", "-l", f"{self._max_volume():.2f}", str(nid), f"{abs(d)}%{'+' if d > 0 else '-'}")
            return self._after()
        if name == "mute":     # {id}
            _run("wpctl", "set-mute", str(self._node(body)), "toggle")
            return self._after()
        if name == "default":  # {id} – an output or input device
            _run("wpctl", "set-default", str(self._node(body, ("outputs", "inputs"))))
            return self._after()
        if name == "mic_keepalive":
            self.mic.touch()
            return {}
        if name == "ptt_down":   # hold to talk: unmute while the phone keeps pinging
            self._ptt_until = time.monotonic() + PTT_LEASE
            if not self._ptt_on:
                self._ptt_on = True
                _run("wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "0")
            return {"ptt": True}
        if name == "ptt_up":
            self._ptt_release()
            return {"ptt": False}
        raise ValueError(f"ukendt handling: {name}")

    def _ptt_release(self):
        if self._ptt_on:
            self._ptt_on = False
            _run("wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "1")
            self._cache = (0.0, {})

    def _ptt_watch(self):
        # safety net: if the phone is unplugged while the button is held, mute again
        while not self.ctx.stopped.wait(0.5):
            if self._ptt_on and time.monotonic() > self._ptt_until:
                self._ptt_release()

    # ---------- microphone level (server-sent events) ----------
    def http_get(self, path, query, req):
        if path != "miclevel":
            return False
        req.stream(self._levels())
        return True

    def _levels(self):
        if not self.mic.available:
            yield json.dumps({"error": self.mic.error})
            return
        self.mic.touch()
        frame = -1
        while self.mic.alive() and not self.ctx.stopped.is_set():
            frame, level = self.mic.wait(frame)
            yield json.dumps({"level": level})

    def stop(self):
        self._ptt_release()
