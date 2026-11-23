"""HTTP server: serves the dashboard, streams state (SSE) and accepts actions."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .actions import Actions, audio_state, load_config
from .claude_usage import ClaudeUsage
from .github import GitHub
from .visualizer import Visualizer
from .media import Media
from .sensors import Sensors

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class Hub:
    """Samples everything in a background thread and fans out to clients."""

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.sensors = Sensors()
        gpu_name = load_config().get("gpu", {}).get("name")
        if gpu_name and self.sensors.gpu:
            self.sensors.gpu.name = gpu_name
        self.media = Media()
        self.claude = ClaudeUsage()
        self.actions = Actions(self.media)
        self.visualizer = Visualizer()
        self.github = GitHub(load_config().get("github", {}).get("user"))
        self.cond = threading.Condition()
        self.state: dict = {}
        self.version = 0
        self._claude_summary: dict = {}
        self._claude_next = 0.0

    def _tick(self) -> None:
        now = time.time()
        if now >= self._claude_next:
            self.actions.reload_if_changed()
            try:
                self.claude.scan()
                self._claude_summary = self.claude.summary()
            except Exception as e:  # never let one source kill the loop
                self._claude_summary = {"error": str(e)}
            self._claude_next = now + 15

        state = {
            "time": now,
            "hw": self.sensors.sample(),
            "media": self.media.state(),
            "audio": audio_state(),
            "claude": self._claude_summary,
            "github": self.github.state(),
            "buttons": self.actions.public_buttons(),
        }
        with self.cond:
            self.state = state
            self.version += 1
            self.cond.notify_all()

    def run(self) -> None:
        while True:
            start = time.monotonic()
            try:
                self._tick()
            except Exception as e:
                print(f"[phonedeck] sample error: {e}")
            time.sleep(max(0.05, self.interval - (time.monotonic() - start)))

    def wait(self, version: int, timeout: float = 15) -> tuple[int, dict]:
        with self.cond:
            self.cond.wait_for(lambda: self.version != version, timeout)
            return self.version, self.state


def make_handler(hub: Hub):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PhoneDeck"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/state":
                return self._json(hub.state)
            if path == "/api/stream":
                return self._stream()
            if path == "/api/spectrum":
                return self._spectrum()
            if path == "/api/art":
                art = hub.media.art()
                if not art:
                    return self._send(404, b"", "text/plain")
                return self._send(200, art[0], art[1], {"Cache-Control": "max-age=86400"})
            return self._static(path)

        def do_POST(self):
            if self.path == "/api/viz/keepalive":
                hub.visualizer.touch()
                return self._json({"ok": True})
            if self.path != "/api/action":
                return self._json({"error": "not found"}, 404)
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 4096)
                action = json.loads(self.rfile.read(length) or b"{}").get("action", "")
                hub.actions.run(action)
                return self._json({"ok": True})
            except ValueError:
                return self._json({"error": "unknown action"}, 400)
            except Exception as e:
                return self._json({"error": str(e)}, 500)

        def _static(self, path: str):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (WEB_DIR / rel).resolve()
            if WEB_DIR not in target.parents or not target.is_file():
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype, {"Cache-Control": "no-cache"})

        def _spectrum(self):
            viz = hub.visualizer
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if not viz.available:
                self.wfile.write(b"event: error\ndata: " + json.dumps(viz.error).encode() + b"\n\n")
                return
            viz.touch()
            frame = -1
            try:
                while viz.alive():  # ends when the page stops sending keepalives
                    frame, bands = viz.wait(frame)
                    self.wfile.write(b"data: " + json.dumps(bands, separators=(",", ":")).encode() + b"\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            version = -1
            try:
                while True:
                    version, state = hub.wait(version)
                    self.wfile.write(b"data: " + json.dumps(state).encode() + b"\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main() -> None:
    cfg = load_config().get("server", {})
    p = argparse.ArgumentParser(prog="phonedeck", description="PC-dashboard til en gammel telefon")
    p.add_argument("--host", default=cfg.get("host", "127.0.0.1"),
                   help="adresse at lytte på (standard 127.0.0.1 – brug adb reverse)")
    p.add_argument("--port", type=int, default=cfg.get("port", 8765))
    p.add_argument("--interval", type=float, default=cfg.get("interval", 1.0))
    args = p.parse_args()

    hub = Hub(args.interval)
    threading.Thread(target=hub.run, daemon=True).start()
    hub.wait(0, timeout=5)

    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(hub))
    httpd.daemon_threads = True
    print(f"[phonedeck] kører på http://{args.host}:{args.port}  (Ctrl+C for at stoppe)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
