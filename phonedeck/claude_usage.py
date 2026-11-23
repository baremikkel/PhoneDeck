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
KEEP_DAYS = 8


class ClaudeUsage:
    def __init__(self, root: str = ROOT):
        self.root = root
        self.offsets: dict[str, int] = {}
        # message id -> (epoch, model, input, output, cache_write, cache_read)
        self.records: dict[str, tuple] = {}
        self.last_scan = 0.0

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

        reset_in = None
        if window_start is not None and window_start + 5 * 3600 > now:
            reset_in = window_start + 5 * 3600 - now

        return {
            "today": today,
            "last5h": last5h,
            "last7d": last7d,
            "models": dict(sorted(models.items(), key=lambda kv: -kv[1])),
            "hourly": hourly,
            "block_reset_in": reset_in,
            "available": os.path.isdir(os.path.join(self.root, "projects")),
        }
