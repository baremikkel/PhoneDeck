"""Touch actions: volume, mic, media keys and user-defined shortcut buttons."""

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
    def __init__(self, media):
        self.media = media
        self.reload()

    def reload(self) -> None:
        cfg = load_config()
        self.buttons = []
        for i, b in enumerate(cfg.get("buttons", [])):
            cmd = b.get("command")
            if isinstance(cmd, str):
                cmd = ["sh", "-c", cmd]
            if not cmd or not b.get("label"):
                continue
            self.buttons.append({"id": f"custom.{i}", "label": b["label"],
                                 "icon": b.get("icon", "▶"), "command": cmd})

    def public_buttons(self) -> list[dict]:
        return [{k: b[k] for k in ("id", "label", "icon")} for b in self.buttons]

    def run(self, action: str) -> None:
        if action == "media.playpause":
            self.media.command("PlayPause")
        elif action == "media.next":
            self.media.command("Next")
        elif action == "media.previous":
            self.media.command("Previous")
        elif action == "volume.up":
            _wpctl("set-volume", "-l", "1.0", SINK, "5%+")
        elif action == "volume.down":
            _wpctl("set-volume", SINK, "5%-")
        elif action == "volume.mute":
            _wpctl("set-mute", SINK, "toggle")
        elif action == "mic.mute":
            _wpctl("set-mute", SOURCE, "toggle")
        elif action.startswith("custom."):
            btn = next((b for b in self.buttons if b["id"] == action), None)
            if btn is None:
                raise ValueError(action)
            subprocess.Popen(btn["command"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            raise ValueError(action)
