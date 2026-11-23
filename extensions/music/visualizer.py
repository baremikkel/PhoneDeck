"""Live audio spectrum of whatever the PC is playing (PipeWire).

``pw-record`` captures the monitor of the default output, numpy turns it into
log-spaced frequency bands. Capture only runs while at least one dashboard is
showing the visualizer, and only the band levels leave this module – never audio.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

RATE = 22050
WINDOW = 1024     # FFT size (~46 ms)
HOP = 735         # new samples per frame -> 30 fps
BANDS = 36
FMIN, FMAX = 40.0, 10000.0
RANGE_DB = 36.0  # dynamic range shown, below the recent peak


class Visualizer:
    def __init__(self):
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
            freqs = np.fft.rfftfreq(WINDOW, 1 / RATE)
            edges = np.geomspace(FMIN, FMAX, BANDS + 1)
            self._bins = [np.where((freqs >= lo) & (freqs < hi))[0] for lo, hi in zip(edges[:-1], edges[1:])]
            # make sure every band has at least one bin
            self._bins = [b if len(b) else np.array([int(np.argmin(abs(freqs - lo)))])
                          for b, lo in zip(self._bins, edges[:-1])]
            self._hann = np.hanning(WINDOW).astype(np.float32)
            # gently boost highs – music has far less energy up there
            self._tilt = np.linspace(0, 12, BANDS).astype(np.float32)

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

    def _run(self) -> None:
        cmd = ["pw-record", "-P", "{ stream.capture.sink = true node.name = phonedeck-visualizer }",
               "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.error = str(e)
            with self._lock:
                self._running = False
            return
        buf = np.zeros(WINDOW, dtype=np.float32)
        smooth = np.zeros(BANDS, dtype=np.float32)
        peak = -40.0
        try:
            while True:
                raw = proc.stdout.read(HOP * 2)
                if not raw or len(raw) < HOP * 2:
                    break
                if not self.alive():
                    break  # nobody is watching any more – stop listening
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                buf = np.concatenate([buf[HOP:], samples])
                spec = np.abs(np.fft.rfft(buf * self._hann)) / (WINDOW / 4)  # full-scale sine ≈ 0 dB
                power = np.array([spec[b].max() for b in self._bins], dtype=np.float32)
                db = 20 * np.log10(power + 1e-9) + self._tilt
                # automatic gain: scale to the loudest band of the last few seconds,
                # so the bars look the same at low and high volume
                peak = max(float(db.max()), peak - 0.08, -75.0)
                level = np.clip((db - (peak - RANGE_DB)) / RANGE_DB, 0, 1)
                if not self.gate():
                    level = np.zeros(BANDS, dtype=np.float32)  # only show the music, not other sounds
                # fast attack, slow release – looks like a real analyser
                smooth = np.where(level > smooth, level, smooth * 0.82 + level * 0.18)
                with self.cond:
                    self.bands = [int(v * 100) for v in smooth]
                    self.frame += 1
                    self.cond.notify_all()
        finally:
            proc.kill()
            proc.wait()
            with self._lock:
                self._running = False
            with self.cond:
                self.bands = [0] * BANDS
                self.frame += 1
                self.cond.notify_all()
