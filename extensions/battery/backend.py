"""Batterier: battery levels of connected devices from UPower (read every 30 s)."""

from __future__ import annotations

import threading

from .upower import read


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.devices: list[dict] = []
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self.ctx.stopped.is_set():
            self.devices = read()
            self.ctx.stopped.wait(30)

    def state(self):
        return {"devices": self.devices, "warn": int(self.ctx.settings().get("warn") or 20)}
