"""The Stream Deck: buttons stored in ~/.config/phonedeck/buttons.json.

Each button has a label, an icon and an action:

    {"type": "builtin", "name": "volume.up"}        volume, mic, media, fullscreen
    {"type": "url",     "url": "https://…"}         open in the default browser
    {"type": "app",     "app": "firefox.desktop"}   start an installed program
    {"type": "hotkey",  "keys": [29, 46]}           press a key combo (ydotool)
    {"type": "command", "argv": ["prog", "arg"]}    run a program/script
    {"type": "page",    "page": "music"}            show a page on the phone (nothing runs on the PC)

Icons: {"kind": "builtin", "value": "<icon name>"} | {"kind": "emoji", "value": "💬"}
       | {"kind": "app", "value": "<desktop id>"}
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid

from .actions import BUILTINS, load_config
from . import paths
from .paths import IS_WINDOWS

if IS_WINDOWS:
    from . import win

DECK_PATH = os.path.expanduser(os.environ.get("PHONEDECK_BUTTONS", paths.config("buttons.json")))
PAGE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")  # same as settings.PAGE_RE
BUTTON_HIDE = ("label", "icon", "frame")  # parts of a button that can be hidden
MAX_BUTTONS = 150   # in total, including the ones inside folders
MAX_DEPTH = 3       # folders inside folders inside folders

# Linux input key codes ydotool understands (subset used by the editor)
MAX_KEYCODE = 248


def _default_buttons() -> list[dict]:
    order = ["volume.down", "volume.mute", "volume.up", "mic.mute",
             "media.previous", "media.playpause", "media.next", "ui.fullscreen"]
    buttons = [{"label": BUILTINS[n][0], "icon": {"kind": "builtin", "value": BUILTINS[n][1]},
                "action": {"type": "builtin", "name": n}} for n in order]
    buttons += [
        {"label": "Lås skærm", "icon": {"kind": "emoji", "value": "🔒"},
         "action": {"type": "command", "argv": ["rundll32.exe", "user32.dll,LockWorkStation"] if IS_WINDOWS
                    else ["loginctl", "lock-session"]}},
        {"label": "Skærmbillede", "icon": {"kind": "emoji", "value": "📷"},
         "action": {"type": "hotkey", "keys": [99]}},  # Print Screen
    ]
    # bring over buttons from the old config.toml format
    for b in load_config().get("buttons", []):
        cmd = b.get("command")
        if not b.get("label") or not cmd:
            continue
        argv = shell_argv(cmd) if isinstance(cmd, str) else list(cmd)
        if len(argv) == 2 and argv[0] == "xdg-open" and argv[1].startswith(("http://", "https://")):
            action = {"type": "url", "url": argv[1]}
        else:
            action = {"type": "command", "argv": argv}
        buttons.append({"label": b["label"], "icon": {"kind": "emoji", "value": b.get("icon", "▶")},
                        "action": action})
    return buttons


def _clean_icon(icon) -> dict:
    if not isinstance(icon, dict):
        return {"kind": "emoji", "value": "⭐"}
    kind, value = icon.get("kind"), str(icon.get("value", ""))[:64]
    if kind not in ("builtin", "emoji", "app"):
        kind, value = "emoji", "⭐"
    return {"kind": kind, "value": value}


def validate(raw: list, apps, _depth: int = 0, _seen: set | None = None, _count: list | None = None) -> list[dict]:
    """Return a cleaned list or raise ValueError with a Danish message.
    A button with action {"type": "folder"} holds its own "buttons" list."""
    if not isinstance(raw, list):
        raise ValueError("forventede en liste af knapper")
    seen = set() if _seen is None else _seen
    count = [0] if _count is None else _count
    out = []
    for b in raw:
        count[0] += 1
        if count[0] > MAX_BUTTONS:
            raise ValueError(f"højst {MAX_BUTTONS} knapper i alt")
        if not isinstance(b, dict):
            raise ValueError("ugyldig knap")
        label = str(b.get("label", "")).strip()[:40]
        if not label:
            raise ValueError("alle knapper skal have et navn")
        a = b.get("action") or {}
        t = a.get("type")
        children = None
        if t == "folder":
            if _depth >= MAX_DEPTH:
                raise ValueError(f"{label}: mapper kan højst ligge {MAX_DEPTH} niveauer inde i hinanden")
            action = {"type": "folder"}
            children = validate(b.get("buttons") or [], apps, _depth + 1, seen, count)
        elif t == "page":
            page = str(a.get("page", ""))
            if not PAGE_RE.match(page):
                raise ValueError(f"{label}: vælg en side")
            action = {"type": "page", "page": page}
        elif t == "builtin":
            if a.get("name") not in BUILTINS:
                raise ValueError(f"{label}: ukendt indbygget handling")
            action = {"type": "builtin", "name": a["name"]}
        elif t == "url":
            url = str(a.get("url", "")).strip()
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"{label}: adressen skal starte med https://")
            action = {"type": "url", "url": url[:2000]}
        elif t == "app":
            if not apps.get(str(a.get("app", ""))):
                raise ValueError(f"{label}: programmet findes ikke")
            action = {"type": "app", "app": a["app"]}
        elif t == "hotkey":
            keys = a.get("keys")
            if (not isinstance(keys, list) or not 1 <= len(keys) <= 6
                    or not all(isinstance(k, int) and 1 <= k <= MAX_KEYCODE for k in keys)):
                raise ValueError(f"{label}: ugyldig tastaturgenvej")
            action = {"type": "hotkey", "keys": keys, "text": str(a.get("text", ""))[:60]}
        elif t == "command":
            argv = a.get("argv")
            if isinstance(argv, str):
                argv = shell_argv(argv)
            if (not isinstance(argv, list) or not argv or len(argv) > 64
                    or not all(isinstance(x, str) and x for x in argv)):
                raise ValueError(f"{label}: ugyldig kommando")
            action = {"type": "command", "argv": argv}
        else:
            raise ValueError(f"{label}: vælg en handling")
        bid = str(b.get("id") or "")[:40]
        if not bid or bid in seen:
            bid = uuid.uuid4().hex[:10]
        seen.add(bid)
        color = str(b.get("color") or "")
        if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            color = ""
        item = {"id": bid, "label": label, "icon": _clean_icon(b.get("icon")), "action": action,
                "color": color}
        # display options: hide the name/icon/frame, or make the button invisible (still pressable)
        hide = [h for h in (b.get("hide") or []) if h in BUTTON_HIDE][:3]
        if hide:
            item["hide"] = list(dict.fromkeys(hide))
        if b.get("invisible") is True:
            item["invisible"] = True
        if children is not None:
            item["buttons"] = children
        out.append(item)
    return out


def walk(buttons: list[dict]):
    """Every button, including those inside folders."""
    for b in buttons:
        yield b
        if b["action"]["type"] == "folder":
            yield from walk(b.get("buttons", []))


class Deck:
    def __init__(self, actions, apps):
        self.actions = actions
        self.apps = apps
        self._lock = threading.Lock()
        self._mtime = None
        self.buttons: list[dict] = []
        self.reload()

    # ---- storage ----
    def reload(self) -> None:
        with self._lock:
            try:
                with open(DECK_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                self.buttons = validate(data.get("buttons", []), self.apps)
                self._mtime = os.path.getmtime(DECK_PATH)
            except FileNotFoundError:
                self.buttons = validate(_default_buttons(), self.apps)
                self._write()
            except (ValueError, OSError) as e:
                print(f"[phonedeck] Kunne ikke læse {DECK_PATH}: {e}")

    def reload_if_changed(self) -> None:
        try:
            mtime = os.path.getmtime(DECK_PATH)
        except OSError:
            mtime = None
        if mtime != self._mtime:
            self.reload()

    def _write(self) -> None:
        os.makedirs(os.path.dirname(DECK_PATH), exist_ok=True)
        tmp = DECK_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"buttons": self.buttons}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DECK_PATH)
        self._mtime = os.path.getmtime(DECK_PATH)

    def save(self, raw: list) -> list[dict]:
        cleaned = validate(raw, self.apps)
        with self._lock:
            self.buttons = cleaned
            self._write()
        return cleaned

    def reset(self) -> list[dict]:
        return self.save(_default_buttons())

    # ---- for the phone: no commands, just what it needs to draw ----
    def app_ids(self) -> list[str]:
        return [b["action"]["app"] for b in walk(self.buttons) if b["action"]["type"] == "app"]

    def public(self, running: set[str] | None = None, _buttons: list | None = None) -> list[dict]:
        out = []
        for b in self.buttons if _buttons is None else _buttons:
            p = {"id": b["id"], "label": b["label"], "icon": b["icon"], "type": b["action"]["type"],
                 "color": b.get("color", "")}
            if b.get("hide"):
                p["hide"] = b["hide"]
            if b.get("invisible"):
                p["invisible"] = True
            if b["action"]["type"] == "app":
                p["running"] = b["action"]["app"] in (running or ())
            if b["action"]["type"] == "builtin":
                p["builtin"] = b["action"]["name"]
            if b["action"]["type"] == "page":
                p["page"] = b["action"]["page"]
            if b["action"]["type"] == "folder":
                p["buttons"] = self.public(running, b.get("buttons", []))
            out.append(p)
        return out

    # ---- running ----
    def press(self, button_id: str) -> dict:
        b = next((x for x in walk(self.buttons) if x["id"] == button_id), None)
        if b is None:
            raise ValueError("ukendt knap")
        a = b["action"]
        if a["type"] in ("folder", "page"):
            return {}  # the phone opens folders and pages itself
        if a["type"] == "app" and a["app"] in self.apps.running([a["app"]]):
            return {"notice": f"{b['label']} er allerede åben"}  # don't start a second copy
        self.run(a)
        return {}

    def run(self, a: dict) -> None:
        t = a["type"]
        if t in ("folder", "page"):
            return
        if t == "builtin":
            self.actions.run(a["name"])
        elif t == "url":
            if IS_WINDOWS:
                win.open_target(a["url"])
            else:
                _spawn(["xdg-open", a["url"]])
        elif t == "app":
            self.apps.launch(a["app"])
        elif t == "hotkey":
            send_hotkey(a["keys"])
        elif t == "command":
            argv = a["argv"]
            # the editor stores typed commands as ["sh", "-c", …] – run them with cmd on Windows
            if IS_WINDOWS and len(argv) == 3 and argv[:2] == ["sh", "-c"]:
                argv = shell_argv(argv[2])
            _spawn(argv)


def shell_argv(cmd: str) -> list[str]:
    """A command typed in the editor, run by the system's shell."""
    return ["cmd", "/c", cmd] if IS_WINDOWS else ["sh", "-c", cmd]


def _spawn(argv: list[str]) -> None:
    if IS_WINDOWS:
        # detached, no console window popping up
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(argv, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         cwd=os.path.expanduser("~"))
        return
    subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, cwd=os.path.expanduser("~"))


def hotkeys_available() -> bool:
    return IS_WINDOWS or shutil.which("ydotool") is not None


def send_hotkey(keys: list[int]) -> None:
    """Press keys in order, release in reverse – e.g. [29, 46] = Ctrl+C."""
    if IS_WINDOWS:
        win.send_keys(keys)
        return
    if not hotkeys_available():
        raise ValueError("ydotool er ikke installeret")
    env = dict(os.environ)
    sock = f"/run/user/{os.getuid()}/.ydotool_socket"
    if "YDOTOOL_SOCKET" not in env and os.path.exists(sock):
        env["YDOTOOL_SOCKET"] = sock
    seq = [f"{k}:1" for k in keys] + [f"{k}:0" for k in reversed(keys)]
    subprocess.run(["ydotool", "key", *seq], env=env, timeout=3,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
