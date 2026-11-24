"""Microphone level for the meter: pw-record from the default input, RMS -> 0-100.

Only runs while a phone keeps renewing its lease (the meter is on screen), and only
the level number leaves this module – never the audio itself."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import threading
import time

RATE = 16000
HOP = 800          # 50 ms -> 20 updates a second
LEASE = 4.0


class MicMeter:
    def __init__(self):
        self.available = shutil.which("pw-record") is not None
        self.error = None if self.available else "kræver pw-record (PipeWire)"
        self.cond = threading.Condition()
        self.level = 0
        self.frame = 0
        self._seen = 0.0
        self._running = False
        self._lock = threading.Lock()

    def touch(self):
        with self._lock:
            self._seen = time.monotonic()
            if not self._running and self.available:
                self._running = True
                threading.Thread(target=self._run, daemon=True).start()

    def alive(self) -> bool:
        with self._lock:
            return time.monotonic() - self._seen < LEASE

    def wait(self, frame: int, timeout: float = 1.0) -> tuple[int, int]:
        with self.cond:
            self.cond.wait_for(lambda: self.frame != frame, timeout)
            return self.frame, self.level

    def _publish(self, level: int):
        with self.cond:
            self.level = level
            self.frame += 1
            self.cond.notify_all()

    def _run(self):
        cmd = ["pw-record", "-P", "{ node.name = phonedeck-micmeter }",
               "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.error = str(e)
            with self._lock:
                self._running = False
            return
        smooth = 0.0
        try:
            while self.alive():
                raw = proc.stdout.read(HOP * 2)
                if not raw or len(raw) < HOP * 2:
                    break
                s = array.array("h", raw)
                rms = math.sqrt(sum(x * x for x in s) / len(s)) / 32768
                db = 20 * math.log10(rms + 1e-9)               # -inf .. 0 dBFS
                level = max(0.0, min(1.0, (db + 60) / 60))     # -60 dB = empty, 0 dB = full
                smooth = level if level > smooth else smooth * 0.8 + level * 0.2
                self._publish(int(smooth * 100))
        finally:
            proc.kill()
            proc.wait()
            with self._lock:
                self._running = False
            self._publish(0)
