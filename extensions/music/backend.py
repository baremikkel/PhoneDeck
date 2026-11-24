"""Music: now playing via MPRIS, playback control, player volume and visualizer."""

import json

import sys

if sys.platform == "win32":
    from .media_win import Media
else:
    from .media import Media
from .visualizer import Visualizer


# the visualizer takes the colour of the program that is playing (MPRIS name contains the key)
APP_COLOURS = [
    ("spotif", "#1ed760"),      # Spotify, Spotifast, spotifyd
    ("firefox", "#ff7139"),
    ("chrom", "#4c8bf5"),       # Chrome, Chromium
    ("brave", "#fb542b"),
    ("edge", "#33c3f0"),
    ("opera", "#ff1b2d"),
    ("vivaldi", "#ef3939"),
    ("vlc", "#ff8800"),
    ("mpv", "#b05ee6"),
    ("rhythmbox", "#e6b422"),
    ("strawberry", "#e8455a"),
    ("tidal", "#e8e8e8"),
    ("deezer", "#a238ff"),
    ("youtube", "#ff3b3b"),
    ("discord", "#5865f2"),
    ("plexamp", "#ebaf00"),
    ("lollypop", "#3d9ae8"),
]


def app_colour(player: str | None) -> str | None:
    p = (player or "").lower()
    return next((c for key, c in APP_COLOURS if key in p), None)


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.media = Media()
        self.viz = Visualizer()
        self._media_state = None
        # only show bars while the player is actually playing (not Discord, system sounds …)
        self.viz.gate = lambda: (self._media_state or {}).get("status") == "Playing"

    def state(self):
        self.media.source = self.ctx.settings().get("source") or "spotify"
        self._media_state = self.media.state()
        m = self._media_state or {}
        colour = app_colour(m.get("player")) if self.ctx.settings().get("viz_colour", "app") == "app" else None
        return {"media": self._media_state, "viz_colour": colour}

    def action(self, name, body):
        if name in ("playpause", "next", "previous"):
            self.media.command({"playpause": "PlayPause", "next": "Next", "previous": "Previous"}[name])
        elif name in ("volume_up", "volume_down"):
            step = (self.ctx.settings().get("volume_step") or 5) / 100
            return {"volume": self.media.set_volume(step if name == "volume_up" else -step)}
        elif name == "viz_keepalive":
            self.viz.touch()
        else:
            raise ValueError(f"ukendt handling: {name}")

    def http_get(self, path, query, req):
        if path == "art":
            art = self.media.art()
            if not art:
                req.send(404, b"", "text/plain")
            else:
                req.send(200, art[0], art[1], {"Cache-Control": "max-age=86400"})
            return True
        if path == "spectrum":
            req.stream(self._spectrum())
            return True
        return False

    def _spectrum(self):
        viz = self.viz
        if not viz.available:
            yield json.dumps({"error": viz.error})
            return
        viz.touch()
        frame = -1
        while viz.alive() and not self.ctx.stopped.is_set():  # ends when the page stops pinging
            frame, bands = viz.wait(frame)
            yield json.dumps(bands, separators=(",", ":"))
