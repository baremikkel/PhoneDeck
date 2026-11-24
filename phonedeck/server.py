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
from .deck import Deck, hotkeys_available, validate
from .extensions import ExtensionManager
from .sensors import Sensors
from .settings import Settings

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 64 * 1024



# fixed types for our own files: on Windows mimetypes reads the registry, which can say
# text/plain for .js – and then the browser refuses to run the page
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
         ".woff2": "font/woff2", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json"}


def content_type(name: str) -> str:
    ext = name[name.rfind("."):].lower() if "." in name else ""
    return TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


class Hub:
    """Samples everything in a background thread and fans out to clients."""

    def __init__(self, interval: float = 1.0, port: int = 8765):
        self.interval = interval
        self.port = port
        self.settings = Settings()
        self.cond = threading.Condition()
        self.state: dict = {}
        self.version = 0
        self.running: set[str] = set()
        self._running_next = 0.0
        self._scan_next = 0.0
        self.sensors = Sensors()
        gpu_name = load_config().get("gpu", {}).get("name")
        if gpu_name and self.sensors.gpu:
            self.sensors.gpu.name = gpu_name
        self.extensions = ExtensionManager(self, port)
        self.actions = Actions(self.extensions)
        self.apps = Apps()
        self.deck = Deck(self.actions, self.apps)
        self.extensions.scan()
        self._ext_public = self.extensions.public()
        self._ext_rev = self.extensions.revision

    def _tick(self) -> None:
        now = time.time()
        if now >= self._scan_next:  # extension folders added / removed / changed?
            self.deck.reload_if_changed()  # also picks up hand edits of buttons.json
            try:
                self.extensions.scan()
            except Exception as e:
                print(f"[phonedeck] fejl ved scanning af udvidelser: {e}")
            if self.extensions.revision != self._ext_rev:
                self._ext_public = self.extensions.public()
                self._ext_rev = self.extensions.revision
            self._scan_next = now + 3

        if now >= self._running_next:  # which deck programs have a window open
            try:
                self.running = self.apps.running(self.deck.app_ids())
            except Exception:
                self.running = set()
            self._running_next = now + 4

        state = {
            "time": now,
            "hw": self.sensors.sample(),
            "audio": audio_state(),
            "buttons": self.deck.public(self.running),
            "ui": self.settings.public()["ui"],
            "extensions": self._ext_public,
            "ext": self.extensions.states(),
        }
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


class ExtRequest:
    """Handed to an extension's http_get() so it can answer without knowing the server."""

    def __init__(self, handler):
        self._h = handler
        self.headers = handler.headers

    def json(self, obj, code=200):
        self._h._json(obj, code)

    def send(self, code: int, body: bytes, ctype: str, headers: dict | None = None):
        self._h._send(code, body, ctype, headers)

    def redirect(self, url: str):
        self._h._send(302, b"", "text/plain", {"Location": url})

    def stream(self, events):
        """Server-sent events: `events` yields bytes/str payloads (one per message)."""
        h = self._h
        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream")
        h.send_header("Cache-Control", "no-cache")
        h.end_headers()
        try:
            for ev in events:
                data = ev if isinstance(ev, bytes) else str(ev).encode()
                h.wfile.write(b"data: " + data + b"\n\n")
                h.wfile.flush()
        except ConnectionError:  # client went away (Windows raises ConnectionAbortedError)
            pass
        h.close_connection = True


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
            if path == "/spotify/callback":  # compatibility: Redirect URI used before extensions
                path = "/ext/spotify/callback"
            if path.startswith("/ext/"):
                return self._ext_get(path, query)
            if path == "/api/extensions":
                if not self._api_ok():
                    return
                return self._json(hub.extensions.public(with_settings=True))
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
                return self._json({"settings": hub.extensions.mask(hub.settings.public()),
                                   "extensions": hub.extensions.public(with_settings=True)})
            if path == "/editor":
                path = "/editor.html"
            if path == "/settings":
                path = "/settings.html"
            return self._static(path)

        def _ext_get(self, path: str, query: dict):
            parts = path.split("/", 3)  # ["", "ext", "<id>", "<rest>"]
            ext_id, rest = (parts[2] if len(parts) > 2 else ""), (parts[3] if len(parts) > 3 else "")
            backend = hub.extensions.get(ext_id)
            if backend and hasattr(backend, "http_get"):
                try:
                    if backend.http_get(rest, query, ExtRequest(self)) is not False:
                        return
                except Exception as e:
                    return self._json({"error": str(e)}, 500)
            target = hub.extensions.static_file(ext_id, rest)
            if not target:
                return self._send(404, b"Not found", "text/plain")
            ctype = content_type(target.name)
            self._send(200, target.read_bytes(), ctype, {"Cache-Control": "no-cache"})

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
                if self.path.startswith("/api/ext/"):
                    # /api/ext/<id>/action/<name>
                    parts = self.path.split("/")
                    if len(parts) != 6 or parts[4] != "action":
                        return self._json({"error": "not found"}, 404)
                    result = hub.extensions.action(parts[3], parts[5], body)
                    return self._json({"ok": True, **(result or {})})
                elif self.path == "/api/action":
                    if "button" in body:
                        return self._json({"ok": True, **hub.deck.press(str(body["button"]))})
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
                    saved, changed = hub.settings.update(body, hub.extensions.validate_settings)
                    for ext_id in changed:
                        hub.extensions.settings_changed(ext_id)
                    return self._json({"ok": True, "settings": hub.extensions.mask(saved)})
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
            ctype = content_type(target.name)
            self._send(200, target.read_bytes(), ctype, {"Cache-Control": "no-cache"})

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
            except ConnectionError:  # client went away (Windows raises ConnectionAbortedError)
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
    finally:
        hub.extensions.stop_all()


if __name__ == "__main__":
    main()
