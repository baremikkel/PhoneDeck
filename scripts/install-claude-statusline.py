#!/usr/bin/env python3
"""Adds PhoneDeck's status line to Claude Code (~/.claude/settings.json), so PhoneDeck
gets your plan limits without using your Claude login. Works on Windows and Linux.

    py scripts/install-claude-statusline.py            (Windows)
    python3 scripts/install-claude-statusline.py       (Linux)
    ... --remove                                        take it out again
    ... --force                                         replace another status line

Respects CLAUDE_CONFIG_DIR. Other settings in the file are kept as they are.
"""

from __future__ import annotations

import json
import os
import sys

MARKER = "claude-statusline.py"


def settings_path() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "settings.json")


def command() -> str:
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":  # the status line must print to stdout
        exe = os.path.join(os.path.dirname(exe), "python.exe")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), MARKER)
    # forward slashes and quotes work in cmd, PowerShell and bash alike
    q = lambda p: '"' + p.replace("\\", "/") + '"'
    return f"{q(exe)} {q(script)}"


def main() -> int:
    remove, force = "--remove" in sys.argv, "--force" in sys.argv
    path = settings_path()
    try:
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    except ValueError as e:
        print(f"Kunne ikke læse {path}: {e}\nRet filen først – den er ikke ændret.")
        return 1

    current = settings.get("statusLine")
    ours = isinstance(current, dict) and MARKER in str(current.get("command", ""))
    if remove:
        if not ours:
            print("PhoneDecks statusline var ikke sat op – intet ændret.")
            return 0
        del settings["statusLine"]
    else:
        if current and not ours and not force:
            print(f"Claude Code har allerede en statusline:\n  {current}\n"
                  "Kør igen med --force for at erstatte den.")
            return 1
        settings["statusLine"] = {"type": "command", "command": command()}

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    print(f"{'Fjernet fra' if remove else 'Sat op i'} {path}")
    if not remove:
        print("Tallene kommer efter Claude Codes næste svar (kræver Pro, Max eller Ultra).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
