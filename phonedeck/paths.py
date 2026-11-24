"""Where PhoneDeck keeps its files, per platform.

Linux:   ~/.config/phonedeck  and  ~/.cache/phonedeck
Windows: %APPDATA%\\PhoneDeck  and  %LOCALAPPDATA%\\PhoneDeck\\cache
"""

from __future__ import annotations

import os
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PhoneDeck")
    CACHE_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or CONFIG_DIR, "PhoneDeck", "cache")
else:
    CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "phonedeck")
    CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "phonedeck")


def config(*parts: str) -> str:
    return os.path.join(CONFIG_DIR, *parts)


def cache(*parts: str) -> str:
    return os.path.join(CACHE_DIR, *parts)
