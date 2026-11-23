"""Now-playing info and playback control over MPRIS (D-Bus).

Works with Spotify and any other MPRIS-capable player (browsers, VLC, mpv …).
Needs PyGObject (``python3-gi``), which ships with most Linux desktops.
"""

from __future__ import annotations

import urllib.parse
import urllib.request

try:
    from gi.repository import Gio, GLib
except ImportError:  # pragma: no cover
    Gio = GLib = None

PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"


class Media:
    def __init__(self):
        self.bus = None
        self.error = None
        if Gio is None:
            self.error = "PyGObject (python3-gi) mangler"
            return
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            self.error = str(e)
        self._art_cache: tuple[str, bytes, str] | None = None
        self.current_art_url: str | None = None
        self.current_player: str | None = None

    def _call(self, dest, iface, method, args=None, sig=None):
        return self.bus.call_sync(dest, PATH if dest != "org.freedesktop.DBus" else "/org/freedesktop/DBus",
                                  iface, method, args, GLib.VariantType(sig) if sig else None,
                                  Gio.DBusCallFlags.NONE, 1000, None)

    def _players(self) -> list[str]:
        names = self._call("org.freedesktop.DBus", "org.freedesktop.DBus", "ListNames").unpack()[0]
        return [n for n in names if n.startswith(PREFIX)]

    def _props(self, name: str) -> dict:
        return self._call(name, "org.freedesktop.DBus.Properties", "GetAll",
                          GLib.Variant("(s)", (PLAYER,))).unpack()[0]

    def state(self) -> dict | None:
        if not self.bus:
            return {"error": self.error}
        try:
            players = []
            for name in self._players():
                try:
                    players.append((name, self._props(name)))
                except Exception:
                    continue  # player refused (e.g. AppArmor) or vanished
            if not players:
                self.current_player = None
                return None

            def rank(p):
                status = p[1].get("PlaybackStatus")
                return (status == "Playing", status == "Paused", "spotify" in p[0])
            name, props = max(players, key=rank)
            self.current_player = name
            meta = props.get("Metadata", {}) or {}
            art = meta.get("mpris:artUrl")
            self.current_art_url = art
            artists = meta.get("xesam:artist") or []
            return {
                "player": name[len(PREFIX):].split(".")[0],
                "status": props.get("PlaybackStatus"),
                "title": meta.get("xesam:title"),
                "artist": ", ".join(artists) if isinstance(artists, list) else artists,
                "album": meta.get("xesam:album"),
                "length": (meta.get("mpris:length") or 0) / 1e6,
                "position": (props.get("Position") or 0) / 1e6,
                "volume": round(props["Volume"] * 100) if isinstance(props.get("Volume"), float) else None,
                "art": bool(art),
                "art_key": art,
            }
        except Exception as e:
            return {"error": str(e)}

    def set_volume(self, delta: float) -> int:
        """Change only the player's own volume (MPRIS), not the whole PC."""
        if not (self.bus and self.current_player):
            raise ValueError("ingen afspiller")
        props = self._props(self.current_player)
        if not isinstance(props.get("Volume"), float):
            raise ValueError("afspilleren kan ikke styre sin lydstyrke")
        new = min(1.0, max(0.0, props["Volume"] + delta))
        self._call(self.current_player, "org.freedesktop.DBus.Properties", "Set",
                   GLib.Variant("(ssv)", (PLAYER, "Volume", GLib.Variant("d", new))))
        return round(new * 100)

    def command(self, method: str) -> None:
        if not (self.bus and self.current_player):
            return
        if method not in ("PlayPause", "Next", "Previous"):
            raise ValueError(method)
        self._call(self.current_player, PLAYER, method)

    def art(self) -> tuple[bytes, str] | None:
        """Album art for the *current* track only (never arbitrary URLs)."""
        url = self.current_art_url
        if not url:
            return None
        if self._art_cache and self._art_cache[0] == url:
            return self._art_cache[1], self._art_cache[2]
        try:
            if url.startswith("file://"):
                path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
                with open(path, "rb") as f:
                    data = f.read(8 * 1024 * 1024)
                ctype = "image/png" if path.lower().endswith(".png") else "image/jpeg"
            elif url.startswith("https://"):
                req = urllib.request.Request(url, headers={"User-Agent": "PhoneDeck"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    data = r.read(8 * 1024 * 1024)
                    ctype = r.headers.get_content_type() or "image/jpeg"
            else:
                return None
        except (OSError, ValueError):
            return None
        self._art_cache = (url, data, ctype)
        return data, ctype


