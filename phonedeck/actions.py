"""Built-in actions (volume, mic, media keys) and config.toml loading."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib

CONFIG_PATH = os.path.expanduser(
    os.environ.get("PHONEDECK_CONFIG", "~/.config/phonedeck/config.toml"))

SINK = "@DEFAULT_AUDIO_SINK@"
SOURCE = "@DEFAULT_AUDIO_SOURCE@"

# name -> (Danish label, icon name in the web UI)
BUILTINS = {
    "volume.down": ("Lavere", "volDown"),
    "volume.mute": ("Lyd", "volMute"),
    "volume.up": ("Højere", "volUp"),
    "mic.mute": ("Mikrofon", "mic"),
    "media.previous": ("Forrige", "prev"),
    "media.playpause": ("Afspil/pause", "play"),
    "media.next": ("Næste", "next"),
    "ui.fullscreen": ("Fuld skærm", "fullscreen"),  # handled on the phone itself
}


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        print(f"[phonedeck] Kunne ikke læse {CONFIG_PATH}: {e}")
        return {}


def _wpctl(*args: str) -> str:
    if not shutil.which("wpctl"):
        return ""
    return subprocess.run(["wpctl", *args], capture_output=True, text=True, timeout=2).stdout


def audio_state() -> dict:
    def parse(dev):
        out = _wpctl("get-volume", dev)
        m = re.search(r"Volume:\s*([\d.]+)", out)
        return {"volume": round(float(m.group(1)) * 100) if m else None, "muted": "MUTED" in out}
    return {"output": parse(SINK), "mic": parse(SOURCE)}


class Actions:
    def __init__(self, extensions):
        self.extensions = extensions  # media.* are handled by the "music" extension

    def run(self, action: str) -> None:
        if action.startswith("media."):
            self.extensions.action("music", action.removeprefix("media."), {})
        elif action == "volume.up":
            _wpctl("set-volume", "-l", "1.0", SINK, "5%+")
        elif action == "volume.down":
            _wpctl("set-volume", SINK, "5%-")
        elif action == "volume.mute":
            _wpctl("set-mute", SINK, "toggle")
        elif action == "mic.mute":
            _wpctl("set-mute", SOURCE, "toggle")
        elif action == "ui.fullscreen":
            pass  # the phone does this itself
        else:
            raise ValueError(action)
