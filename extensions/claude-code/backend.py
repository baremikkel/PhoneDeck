"""Claude Code usage (local logs) + plan limits (optional, via the Claude Code login)."""

import threading

from .plan import ClaudePlan
from .usage import ClaudeUsage

SCAN_EVERY = 15  # seconds


def _fmt(n):
    if not n:
        return "0"
    return f"{n / 1e6:.1f} mio." if n >= 1e6 else f"{round(n / 1e3)}k"


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.usage = ClaudeUsage()
        self.plan = ClaudePlan(lambda: bool(ctx.settings().get("use_login")), ctx.stopped)
        self._summary = {}
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self.ctx.stopped.is_set():
            try:
                self.usage.scan()
                self._summary = self.usage.summary()
            except Exception as e:  # keep running even if a log line is odd
                self._summary = {"error": str(e)}
            self.ctx.stopped.wait(SCAN_EVERY)

    def state(self):
        return {"usage": self._summary, "plan": self.plan.state(), "settings": self.ctx.settings()}

    def settings_changed(self):
        self.plan.refresh_soon()

    def info(self):
        p = self.plan.state()
        if p is None:
            plan_status = ""
        elif p.get("error"):
            plan_status = "⚠ " + p["error"]
        elif p.get("five_hour"):
            plan_status = (f"✓ {str(p.get('plan') or '').capitalize()}-plan: "
                           f"{round(p['five_hour']['used_pct'])} % brugt i 5-timers vinduet"
                           + (f", {round(p['seven_day']['used_pct'])} % af ugen" if p.get("seven_day") else ""))
        else:
            plan_status = "Henter …"
        s = self._summary
        hint = (f"Nu: {_fmt(s.get('block_used'))} · største 5-timers blok de sidste 30 dage: "
                f"{_fmt(s.get('block_max'))}") if s else ""
        return {"plan_status": plan_status, "block_hint": hint}
