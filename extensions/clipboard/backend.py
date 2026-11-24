"""Udklip og skærmbilleder: clipboard history (in memory only) and the latest screenshots.

Clipboard: wl-paste/wl-copy on Wayland, xclip on X11, the Win32 clipboard on Windows.
Entries a password manager marks as secret (x-kde-passwordManagerHint) are skipped.
Screenshots are only ever served from the configured folder, by file name.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque

WINDOWS = sys.platform == "win32"
IMAGES = (".png", ".jpg", ".jpeg", ".webp")
MAX_TEXT = 4000


def _run(args, inp: bytes | None = None, timeout=2) -> bytes | None:
    try:
        r = subprocess.run(args, input=inp, capture_output=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


class Clipboard:
    def __init__(self):
        self.wayland = bool(os.environ.get("WAYLAND_DISPLAY")) and shutil.which("wl-paste")
        self.x11 = not self.wayland and shutil.which("xclip")
        if WINDOWS:
            from phonedeck import win
            self.win = win
        self.ok = WINDOWS or bool(self.wayland or self.x11)

    def get(self) -> str | None:
        if WINDOWS:
            return self.win.get_clipboard_text()
        if self.wayland:
            types = (_run(["wl-paste", "-l"]) or b"").decode(errors="replace").split()
            if "x-kde-passwordManagerHint" in types or not any(t.startswith("text/plain") or t in ("UTF8_STRING", "STRING", "TEXT") for t in types):
                return None
            raw = _run(["wl-paste", "-n", "-t", "text/plain"])
        else:
            targets = (_run(["xclip", "-selection", "clipboard", "-o", "-t", "TARGETS"]) or b"").decode(errors="replace").split()
            if "x-kde-passwordManagerHint" in targets:
                return None
            raw = _run(["xclip", "-selection", "clipboard", "-o"])
        return raw.decode("utf-8", "replace") if raw else None

    def set_text(self, text: str) -> None:
        if WINDOWS:
            self.win.set_clipboard_text(text)
        elif self.wayland:
            subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, start_new_session=True).communicate(text.encode(), timeout=3)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), timeout=3)

    def set_image(self, path: str) -> None:
        with open(path, "rb") as f:
            data = f.read()
        mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        if WINDOWS:
            raise ValueError("På Windows kan billeder ikke kopieres herfra endnu – åbn det på PC'en")
        if self.wayland:
            subprocess.Popen(["wl-copy", "-t", mime], stdin=subprocess.PIPE, start_new_session=True).communicate(data, timeout=5)
        else:
            subprocess.run(["xclip", "-selection", "clipboard", "-t", mime], input=data, timeout=5)


def default_folder() -> str:
    pics = None
    if not WINDOWS and shutil.which("xdg-user-dir"):
        pics = (_run(["xdg-user-dir", "PICTURES"]) or b"").decode().strip() or None
    pics = pics or os.path.join(os.path.expanduser("~"), "Pictures")
    return os.path.join(pics, "Screenshots")


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.clip = Clipboard()
        self.items: deque = deque(maxlen=50)   # [{id, text, at}] newest first – memory only
        self._last = None
        threading.Thread(target=self._loop, daemon=True).start()

    # ---------- clipboard ----------
    def _loop(self):
        while not self.ctx.stopped.wait(self.ctx.number("check_s", 1.5)):
            s = self.ctx.settings()
            if not s.get("history", True) or not self.clip.ok:
                continue
            text = self.clip.get()
            if not text or not text.strip():
                continue
            text = text[:int(self.ctx.number("max_text", MAX_TEXT))]
            digest = hashlib.sha1(text.encode()).hexdigest()[:12]
            if digest == self._last:
                continue
            self._last = digest
            # moving a known entry to the top instead of adding it twice
            for it in list(self.items):
                if it["id"] == digest:
                    self.items.remove(it)
            self.items.appendleft({"id": digest, "text": text, "at": time.time()})
            size = int(s.get("size") or 15)
            while len(self.items) > size:
                self.items.pop()

    # ---------- screenshots ----------
    def _folder(self) -> str:
        return os.path.expanduser((self.ctx.settings().get("folder") or "").strip() or default_folder())

    def _shots(self) -> list[dict]:
        folder = self._folder()
        try:
            names = [n for n in os.listdir(folder) if n.lower().endswith(IMAGES)]
        except OSError:
            return []
        files = []
        for n in names:
            try:
                files.append((os.path.getmtime(os.path.join(folder, n)), n))
            except OSError:
                pass
        return [{"name": n, "at": t} for t, n in sorted(files, reverse=True)[:int(self.ctx.number("shots", 24))]]

    def _shot_path(self, name: str) -> str | None:
        """Only a file that is in the current list – never a path from the phone."""
        if any(s["name"] == name for s in self._shots()):
            return os.path.join(self._folder(), name)
        return None

    def state(self):
        s = self.ctx.settings()
        return {
            "history": [{"id": i["id"], "text": i["text"][:300], "at": i["at"], "long": len(i["text"]) > 300}
                        for i in self.items] if s.get("history", True) else None,
            "clip_ok": self.clip.ok,
            "shots": self._shots(),
        }

    def action(self, name, body):
        body = body or {}
        if name == "clear":
            self.items.clear()
            return {}
        if name == "copy":
            it = next((i for i in self.items if i["id"] == str(body.get("id"))), None)
            if not it:
                raise ValueError("findes ikke længere i historikken")
            self.clip.set_text(it["text"])
            self._last = it["id"]
            return {}
        if name in ("shot_copy", "shot_open"):
            path = self._shot_path(str(body.get("name", "")))
            if not path:
                raise ValueError("skærmbilledet findes ikke længere")
            if name == "shot_copy":
                self.clip.set_image(path)
            elif WINDOWS:
                os.startfile(path)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", path], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {}
        raise ValueError(f"ukendt handling: {name}")

    def http_get(self, path, query, req):
        if path != "shot":
            return False
        p = self._shot_path((query.get("name") or [""])[0])
        if not p:
            req.send(404, b"", "text/plain")
            return True
        with open(p, "rb") as f:
            data = f.read(30 * 1024 * 1024)
        mime = "image/png" if p.lower().endswith(".png") else "image/webp" if p.lower().endswith(".webp") else "image/jpeg"
        req.send(200, data, mime, {"Cache-Control": "max-age=3600"})
        return True

    def info(self):
        n = len(self._shots())
        clip = "udklipsholder OK" if self.clip.ok else "⚠ kræver wl-clipboard (Wayland) eller xclip (X11)"
        return {"status": f"{clip} · {n} skærmbilleder i {self._folder()}"}
