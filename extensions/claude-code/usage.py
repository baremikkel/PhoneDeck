"""Claude Code token usage, read from the local session logs.

Claude Code writes every conversation to ``~/.claude/projects/**/*.jsonl``.
Assistant entries carry a ``message.usage`` block. We tail those files
incrementally, de-duplicate by message id (streamed responses are logged more
than once) and aggregate the numbers.
"""

from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime, timedelta

ROOT = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude"))
KEEP_DAYS = 371  # a year of history for the heat map
# Claude Code deletes old transcripts (30 days by default), so daily totals are
# also saved here – the heat map keeps growing even after the logs are gone.
DAILY_CACHE = os.path.expanduser("~/.cache/phonedeck/claude_daily.json")


def _day(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d")


class ClaudeUsage:
    def __init__(self, root: str = ROOT):
        self.root = root
        self.offsets: dict[str, int] = {}
        # message id -> (epoch, model, input, output, cache_write, cache_read)
        self.records: dict[str, tuple] = {}
        self.last_scan = 0.0
        try:
            with open(DAILY_CACHE) as f:
                self.saved_daily: dict[str, int] = json.load(f)
        except (OSError, ValueError):
            self.saved_daily = {}
        self.daily: dict[str, int] = dict(self.saved_daily)

    def _update_daily(self) -> None:
        computed: dict[str, int] = {}
        for epoch, _m, inp, out, cw, _cr in self.records.values():
            d = _day(epoch)
            computed[d] = computed.get(d, 0) + inp + out + cw
        merged = dict(self.saved_daily)
        for d, v in computed.items():
            merged[d] = max(v, merged.get(d, 0))
        self.daily = merged
        if merged != self.saved_daily:
            try:
                os.makedirs(os.path.dirname(DAILY_CACHE), exist_ok=True)
                with open(DAILY_CACHE, "w") as f:
                    json.dump(merged, f)
                self.saved_daily = merged
            except OSError:
                pass

    def _ingest_line(self, line: str) -> None:
        if '"usage"' not in line:
            return
        try:
            e = json.loads(line)
        except ValueError:
            return
        msg = e.get("message")
        if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            return
        mid = msg.get("id") or e.get("requestId") or e.get("uuid")
        ts = e.get("timestamp")
        if not mid or not ts:
            return
        try:
            epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return
        u = msg["usage"]
        self.records[mid] = (
            epoch,
            msg.get("model") or "?",
            u.get("input_tokens") or 0,
            u.get("output_tokens") or 0,
            u.get("cache_creation_input_tokens") or 0,
            u.get("cache_read_input_tokens") or 0,
        )

    def scan(self) -> None:
        cutoff = time.time() - KEEP_DAYS * 86400
        for path in glob.glob(os.path.join(self.root, "projects", "**", "*.jsonl"), recursive=True):
            try:
                st = os.stat(path)
            except OSError:
                continue
            if st.st_mtime < cutoff:
                continue
            off = self.offsets.get(path, 0)
            if st.st_size < off:  # file was rewritten
                off = 0
            if st.st_size == off:
                continue
            with open(path, "rb") as f:
                f.seek(off)
                chunk = f.read()
            end = chunk.rfind(b"\n") + 1  # only complete lines
            for raw in chunk[:end].splitlines():
                self._ingest_line(raw.decode("utf-8", "replace"))
            self.offsets[path] = off + end
        self.records = {k: v for k, v in self.records.items() if v[0] >= cutoff}
        self.last_scan = time.time()
        self._update_daily()

    def daily_series(self, days: int = 365) -> dict:
        """Tokens per day for the last `days` days, oldest first (for the heat map)."""
        today = datetime.now().date()
        start = today - timedelta(days=days - 1)
        counts = [self.daily.get((start + timedelta(days=i)).isoformat(), 0) for i in range(days)]
        active = [c for c in counts if c]
        streak = 0
        for i, c in enumerate(reversed(counts)):
            if c:
                streak += 1
            elif i:
                break
        return {"start": start.isoformat(), "counts": counts, "total": sum(counts),
                "active_days": len(active), "best": max(counts), "streak": streak,
                "first": min(self.daily) if self.daily else None}

    def summary(self) -> dict:
        now = time.time()
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        week = (datetime.now() - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

        def empty():
            return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "messages": 0}

        today, last5h, last7d = empty(), empty(), empty()
        models: dict[str, int] = {}
        hourly = [0] * 24  # tokens (input+output+cache write) per hour, oldest first
        window_start = None  # start of the current 5-hour block
        block_tokens = 0
        block_max = 0  # biggest 5-hour block in the last 30 days (for reference)

        for epoch, model, inp, out, cw, cr in sorted(self.records.values()):
            for bucket, since in ((today, midnight), (last5h, now - 5 * 3600), (last7d, week)):
                if epoch >= since:
                    bucket["input"] += inp
                    bucket["output"] += out
                    bucket["cache_write"] += cw
                    bucket["cache_read"] += cr
                    bucket["messages"] += 1
            if epoch >= midnight:
                short = model.replace("claude-", "")
                models[short] = models.get(short, 0) + inp + out + cw
            age_h = int((now - epoch) // 3600)
            if 0 <= age_h < 24:
                hourly[23 - age_h] += inp + out + cw
            # Claude's usage limits reset in 5-hour blocks starting at the first message
            if window_start is None or epoch >= window_start + 5 * 3600:
                window_start = epoch - (epoch % 3600)
                block_tokens = 0
            block_tokens += inp + out + cw
            if epoch >= now - 30 * 86400:
                block_max = max(block_max, block_tokens)

        reset_in = None
        block_used = 0
        if window_start is not None and window_start + 5 * 3600 > now:
            reset_in = window_start + 5 * 3600 - now
            block_used = block_tokens  # tokens in the *current* 5-hour block

        return {
            "today": today,
            "last5h": last5h,
            "last7d": last7d,
            "models": dict(sorted(models.items(), key=lambda kv: -kv[1])),
            "hourly": hourly,
            "block_reset_in": reset_in,
            "block_used": block_used,
            "block_max": block_max,
            "available": os.path.isdir(os.path.join(self.root, "projects")),
            "daily": self.daily_series(),
        }
