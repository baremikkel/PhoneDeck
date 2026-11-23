"""Minimal example extension – copy this folder to ~/.config/phonedeck/extensions/."""

import time


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.started = time.time()

    def state(self):
        # Sent to the phone every second as state.ext.hello
        return {
            "greeting": self.ctx.settings().get("greeting"),
            "uptime": int(time.time() - self.started),
        }
