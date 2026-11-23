"""HTTP server: serves the dashboard, streams state (SSE) and accepts actions."""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .actions import BUILTINS, Actions, audio_state, load_config
from .apps import Apps
from .claude_plan import ClaudePlan
from .claude_usage import ClaudeUsage
from .deck import Deck, hotkeys_available, validate
from .github import GitHub
from .media import Media
from .sensors import Sensors
from .settings import Settings
from .spotify import Spotify
from .visualizer import Visualizer

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 64 * 1024


class Hub:
    """Samples everything in a background thread and fans out to clients."""

    def __init__(self, interval: float = 1.0, port: int = 8765):
        self.interval = interval
        self.settings = Settings()
        self.spotify = Spotify(self.settings, port)
        self.plan = ClaudePlan(self.settings)
        self._last_title = None
        self.running: set[str] = set()
        self._running_next = 0.0
        self.sensors = Sensors()
        gpu_name = load_config().get("gpu", {}).get("name")
        if gpu_name and self.sensors.gpu:
            self.sensors.gpu.name = gpu_name
        self.media = Media()
        self.claude = ClaudeUsage()
        self.actions = Actions(self.media)
        self.apps = Apps()
        self.deck = Deck(self.actions, self.apps)
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
            self.deck.reload_if_changed()  # picks up hand edits of buttons.json
            try:
                self.claude.scan()
                self._claude_summary = self.claude.summary()
            except Exception as e:  # never let one source kill the loop
                self._claude_summary = {"error": str(e)}
            self._claude_next = now + 15

        if now >= self._running_next:  # which deck programs are open right now
            try:
                self.running = self.apps.running(self.deck.app_ids())
            except Exception:
                self.running = set()
            self._running_next = now + 4

        state = {
            "time": now,
            "hw": self.sensors.sample(),
            "media": self.media.state(),
            "audio": audio_state(),
            "claude": self._claude_summary,
            "github": self.github.state(),
            "buttons": self.deck.public(self.running),
            "spotify": self.spotify.state(),
            "claude_budget": self.settings.public()["claude"],
            "claude_plan": self.plan.state(),
            "ui": self.settings.public()["ui"],
        }
        title = (state["media"] or {}).get("title")
        if title != self._last_title:  # new song -> refresh the queue right away
            self._last_title = title
            self.spotify.refresh_soon()
        with self.cond:
            self.state = state
            self.version += 1
            self.cond.notify_all()

    def poke(self) -> None:
        """Push a fresh state right away (e.g. after the deck was edited)."""
        with self.cond:
            if self.state:
                self.state = dict(self.state, buttons=self.deck.public(self.running))
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


def make_handler(hub: Hub, host: str, port: int):
    # Only answer requests addressed to us (blocks DNS-rebinding attacks) …
    allowed_hosts = {f"localhost:{port}", f"127.0.0.1:{port}", f"[::1]:{port}"}
    if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0", ""):
        allowed_hosts.add(f"{host}:{port}")

    class Handler(BaseHTTPRequestHandler):
        server_version = "PhoneDeck"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            if host == "0.0.0.0":
                return True  # user opted in to LAN access
            if self.headers.get("Host", "") in allowed_hosts:
                return True
            self._send(403, b"Forbidden", "text/plain")
            return False

        def _api_ok(self) -> bool:
            """… and only accept API calls from our own pages. A custom header can't be
            sent cross-site without a CORS preflight, which we never approve."""
            if self.headers.get("X-PhoneDeck") == "1":
                return True
            self._json({"error": "forbidden"}, 403)
            return False

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("for stor forespørgsel")
            return json.loads(self.rfile.read(length) or b"{}")

        # ---------------- GET ----------------
        def do_GET(self):
            if not self._host_ok():
                return
            url = urllib.parse.urlsplit(self.path)
            path, query = url.path, urllib.parse.parse_qs(url.query)
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
            if path == "/api/appicon":
                return self._app_icon((query.get("id") or [""])[0])
            if path == "/api/deck":
                if not self._api_ok():
                    return
                return self._json({"buttons": hub.deck.buttons,
                                   "builtins": {k: list(v) for k, v in BUILTINS.items()},
                                   "hotkeys": hotkeys_available()})
            if path == "/api/apps":
                if not self._api_ok():
                    return
                return self._json(hub.apps.list())
            if path == "/api/settings":
                if not self._api_ok():
                    return
                return self._json({"settings": hub.settings.public(),
                                   "spotify": hub.spotify.state(),
                                   "redirect_uri": hub.spotify.redirect_uri,
                                   "plan": hub.plan.state(),
                                   "claude": {k: hub.state.get("claude", {}).get(k)
                                              for k in ("block_used", "block_max", "last7d")}})
            if path == "/spotify/login":
                try:
                    return self._send(302, b"", "text/plain", {"Location": hub.spotify.login_url()})
                except ValueError as e:
                    return self._send(400, str(e).encode(), "text/plain; charset=utf-8")
            if path == "/spotify/callback":
                err = (query.get("error") or [""])[0]
                try:
                    if err:
                        raise ValueError(f"Spotify afviste: {err}")
                    hub.spotify.callback((query.get("code") or [""])[0], (query.get("state") or [""])[0])
                    msg = "ok"
                except Exception as e:
                    msg = str(e)
                return self._send(302, b"", "text/plain",
                                  {"Location": f"http://localhost:{port}/settings?spotify=" + urllib.parse.quote(msg)})
            if path == "/editor":
                path = "/editor.html"
            if path == "/settings":
                path = "/settings.html"
            return self._static(path)

        def _app_icon(self, app_id: str):
            p = hub.apps.icon_path(app_id)  # only icons of installed apps
            if not p or not p.lower().endswith((".png", ".svg")):
                return self._send(404, b"", "text/plain")
            try:
                data = Path(p).read_bytes()
            except OSError:
                return self._send(404, b"", "text/plain")
            ctype = "image/svg+xml" if p.lower().endswith(".svg") else "image/png"
            self._send(200, data, ctype, {"Cache-Control": "max-age=86400",
                                          "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})

        # ---------------- POST ----------------
        def do_POST(self):
            if not (self._host_ok() and self._api_ok()):
                return
            try:
                body = self._body()
                if self.path == "/api/viz/keepalive":
                    hub.visualizer.touch()
                elif self.path == "/api/action":
                    if "button" in body:
                        hub.deck.press(str(body["button"]))
                    elif body.get("action") in ("open.editor", "open.settings"):
                        # open the editor / settings page in the PC's browser
                        page = "editor" if body["action"] == "open.editor" else "settings"
                        hub.deck.run({"type": "url", "url": f"http://localhost:{port}/{page}"})
                    else:
                        hub.actions.run(str(body.get("action", "")))
                elif self.path == "/api/deck":
                    saved = hub.deck.save(body.get("buttons"))
                    hub.poke()
                    return self._json({"ok": True, "buttons": saved})
                elif self.path == "/api/deck/reset":
                    saved = hub.deck.reset()
                    hub.poke()
                    return self._json({"ok": True, "buttons": saved})
                elif self.path == "/api/settings":
                    saved = hub.settings.update(body)
                    hub.plan.refresh_soon()
                    return self._json({"ok": True, "settings": saved})
                elif self.path == "/api/spotify/disconnect":
                    hub.spotify.disconnect()
                elif self.path == "/api/deck/test":
                    b = validate([{"label": "test", "action": body.get("action")}], hub.apps)[0]
                    hub.deck.run(b["action"])
                else:
                    return self._json({"error": "not found"}, 404)
                return self._json({"ok": True})
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
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

    hub = Hub(args.interval, args.port)
    threading.Thread(target=hub.run, daemon=True).start()
    hub.wait(0, timeout=5)

    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(hub, args.host, args.port))
    httpd.daemon_threads = True
    print(f"[phonedeck] kører på http://{args.host}:{args.port}  (Ctrl+C for at stoppe)")
    print(f"[phonedeck] knap-editor: http://localhost:{args.port}/editor")
    print(f"[phonedeck] indstillinger: http://localhost:{args.port}/settings")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
