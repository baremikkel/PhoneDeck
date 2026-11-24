#!/usr/bin/env python3
"""Claude Code status line that also hands your plan limits to PhoneDeck.

Claude Code runs this after each reply and passes a JSON object on stdin. For Pro/Max/
Ultra plans it contains `rate_limits` (5-hour and weekly window: % used and reset time),
the same numbers as /usage. We save just those numbers for PhoneDeck – no token or
login involved – and print a short status line back to Claude Code.

Install (Windows and Linux):  python scripts/install-claude-statusline.py
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phonedeck import paths  # noqa: E402

OUT = paths.cache("claude_ratelimits.json")


def _window(d) -> dict | None:
    if not isinstance(d, dict) or d.get("used_percentage") is None:
        return None
    try:
        return {"used_pct": float(d["used_percentage"]), "resets_at": int(d.get("resets_at") or 0) or None}
    except (TypeError, ValueError):
        return None


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read() or b"{}")
    except ValueError:
        data = {}
    rl = data.get("rate_limits") or {}
    five, week = _window(rl.get("five_hour")), _window(rl.get("seven_day"))
    try:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        try:
            with open(OUT, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        # "seen" tells PhoneDeck the status line runs, even before Claude Code has limits
        # to report (they come after the first reply, and only on Pro/Max/Ultra)
        saved["seen"] = time.time()
        if five or week:
            saved.update(five_hour=five, seven_day=week, updated=time.time())
        tmp = OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(saved, f)
        os.replace(tmp, OUT)
    except OSError:
        pass  # never break Claude Code's status line

    parts = [(data.get("model") or {}).get("display_name") or ""]
    if five:
        parts.append(f"5t {round(five['used_pct'])} %")
    if week:
        parts.append(f"uge {round(week['used_pct'])} %")
    line = " · ".join(p for p in parts if p)
    sys.stdout.buffer.write(line.encode("utf-8"))


if __name__ == "__main__":
    main()
