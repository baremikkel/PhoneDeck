"""GitHub contribution heat map."""

import threading

from .github import GitHub


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self._start()

    def _start(self):
        self._stop = threading.Event()
        self.github = GitHub(self.ctx.settings().get("user") or None, self._stop,
                             refresh=lambda: self.ctx.number("refresh_min", 30) * 60)

    def state(self):
        if self.ctx.stopped.is_set():
            self._stop.set()
        return self.github.state()

    def settings_changed(self):  # new user name -> start over
        self._stop.set()
        self._start()

    def stop(self):
        self._stop.set()
