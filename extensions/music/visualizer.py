"""Live audio spectrum of whatever the PC is playing (PipeWire).

``pw-record`` captures the monitor of the default output, numpy turns it into
log-spaced frequency bands. Capture only runs while at least one dashboard is
showing the visualizer, and only the band levels leave this module – never audio.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

WINDOWS = sys.platform == "win32"
try:  # Windows: listen to the speakers through WASAPI loopback (optional package)
    import soundcard as sc  # type: ignore
except Exception:  # noqa: BLE001 – ImportError, or no audio backend
    sc = None

RATE = 22050
WINDOW = 1024     # FFT size (~46 ms)
HOP = 735         # new samples per frame -> 30 fps
BANDS = 36
FMIN, FMAX = 40.0, 10000.0
RANGE_DB = 36.0  # dynamic range shown, below the recent peak


class Visualizer:
    def __init__(self, config=lambda: (BANDS, RANGE_DB, RATE // HOP)):
        self.config = config  # callable -> (bands, range in dB, frames per second), read per capture
        if WINDOWS:
            self.available = np is not None and sc is not None
            self.error = None if self.available else "kræver numpy og soundcard på Windows: pip install numpy soundcard"
        else:
            self.available = np is not None and shutil.which("pw-record") is not None
            self.error = None if self.available else "kræver numpy og pw-record (PipeWire)"
        self.cond = threading.Condition()
        self.bands: list[int] = [0] * BANDS
        self.frame = 0
        self._last_seen = 0.0
        self._running = False
        # set by the server: True while the music player is actually playing
        self.gate = lambda: True
        self._lock = threading.Lock()
        if self.available:
            self._hann = np.hanning(WINDOW).astype(np.float32)

    @staticmethod
    def _layout(bands: int):
        """FFT bins per band (log spaced) and the treble boost, for `bands` bars."""
        freqs = np.fft.rfftfreq(WINDOW, 1 / RATE)
        edges = np.geomspace(FMIN, FMAX, bands + 1)
        bins = [np.where((freqs >= lo) & (freqs < hi))[0] for lo, hi in zip(edges[:-1], edges[1:])]
        # make sure every band has at least one bin
        bins = [b if len(b) else np.array([int(np.argmin(abs(freqs - lo)))]) for b, lo in zip(bins, edges[:-1])]
        # gently boost highs – music has far less energy up there
        return bins, np.linspace(0, 12, bands).astype(np.float32)

    def _settings(self) -> tuple[int, float, int]:
        try:
            bands, range_db, fps = self.config()
            return (max(8, min(96, int(bands))), max(12.0, min(72.0, float(range_db))),
                    max(10, min(60, int(fps))))
        except Exception:  # noqa: BLE001 – a bad setting must not stop the bars
            return BANDS, RANGE_DB, RATE // HOP

    # ---- capture runs only while a dashboard keeps renewing its lease ----
    # (a closed EventSource is not always noticed through `adb reverse`,
    #  so we rely on the page pinging /api/viz/keepalive instead)
    LEASE = 4.0

    def touch(self) -> None:
        with self._lock:
            self._last_seen = time.monotonic()
            if not self._running and self.available:
                self._running = True
                threading.Thread(target=self._run, daemon=True).start()

    def alive(self) -> bool:
        with self._lock:
            return time.monotonic() - self._last_seen < self.LEASE

    def wait(self, frame: int, timeout: float = 1.0) -> tuple[int, list[int]]:
        with self.cond:
            self.cond.wait_for(lambda: self.frame != frame, timeout)
            return self.frame, self.bands

    def _open(self, hop: int):
        """Start listening. -> (read() giving `hop` float32 samples, or None at the end; close())"""
        if WINDOWS:
            mic = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
            rec = mic.recorder(samplerate=RATE, channels=1, blocksize=hop)
            rec.__enter__()
            return (lambda: rec.record(numframes=hop)[:, 0].astype(np.float32)), (lambda: rec.__exit__(None, None, None))
        cmd = ["pw-record", "-P", "{ stream.capture.sink = true node.name = phonedeck-visualizer }",
               "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def read():
            raw = proc.stdout.read(hop * 2)
            if not raw or len(raw) < hop * 2:
                return None
            return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        def close():
            proc.kill()
            proc.wait()
        return read, close

    def _run(self) -> None:
        n_bands, range_db, fps = self._settings()
        hop = RATE // fps
        bins, tilt = self._layout(n_bands)
        decay = 0.82 ** (30 / fps)  # bars fall equally fast at any frame rate
        try:
            read, close = self._open(hop)
        except Exception as e:  # noqa: BLE001 – no PipeWire / no loopback device
            self.error = str(e)
            with self._lock:
                self._running = False
            return
        buf = np.zeros(WINDOW, dtype=np.float32)
        smooth = np.zeros(n_bands, dtype=np.float32)
        peak = -40.0
        restart, count = False, 0
        try:
            while True:
                samples = read()
                if samples is None:
                    break
                if not self.alive():
                    break  # nobody is watching any more – stop listening
                count += 1
                if count % fps == 0 and self._settings() != (n_bands, range_db, fps):
                    restart = True  # settings changed: start over with the new ones
                    break
                buf = np.concatenate([buf[len(samples):], samples])[-WINDOW:]
                spec = np.abs(np.fft.rfft(buf * self._hann)) / (WINDOW / 4)  # full-scale sine ≈ 0 dB
                power = np.array([spec[b].max() for b in bins], dtype=np.float32)
                db = 20 * np.log10(power + 1e-9) + tilt
                # automatic gain: scale to the loudest band of the last few seconds,
                # so the bars look the same at low and high volume
                peak = max(float(db.max()), peak - 0.08 * 30 / fps, -75.0)
                level = np.clip((db - (peak - range_db)) / range_db, 0, 1)
                if not self.gate():
                    level = np.zeros(n_bands, dtype=np.float32)  # only show the music, not other sounds
                # fast attack, slow release – looks like a real analyser
                smooth = np.where(level > smooth, level, smooth * decay + level * (1 - decay))
                with self.cond:
                    self.bands = [int(v * 100) for v in smooth]
                    self.frame += 1
                    self.cond.notify_all()
        finally:
            close()
            with self._lock:
                self._running = False
            if restart:
                self.touch()  # starts a fresh capture with the new settings
            else:
                with self.cond:
                    self.bands = [0] * n_bands
                    self.frame += 1
                    self.cond.notify_all()
