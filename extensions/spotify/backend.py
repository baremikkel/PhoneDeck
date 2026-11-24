"""Spotify via the Web API (PKCE): next song + queue, like, playlists, search, add to queue."""

import urllib.parse

from .spotify import Spotify


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.spotify = Spotify(lambda: ctx.settings().get("client_id") or "", ctx.port, ctx.stopped)
        self._last_title = None

    def state(self):
        # new song on the music player -> refresh the queue right away
        music = self.ctx.other("music")
        title = ((getattr(music, "_media_state", None) or {}).get("title")) if music else None
        if title != self._last_title:
            self._last_title = title
            self.spotify.refresh_soon()
        return self.spotify.state()

    def info(self):
        st = self.spotify.state()
        status = ("⚠ Forbind igen for at kunne like, se playlister og tilføje til kø" if st.get("connected") and st.get("reconnect") else
                  "✓ Forbundet" if st.get("connected") else
                  f"⚠ {st['error']}" if st.get("error") else
                  "Ikke forbundet" if st.get("configured") else "Ikke sat op endnu")
        return {"redirect_uri": self.spotify.redirect_uri, "status": status}

    def action(self, name, body):
        body = body or {}
        sp = self.spotify
        if name == "disconnect":
            sp.disconnect()
        elif name == "like":
            return sp.like_toggle()
        elif name == "search":
            return sp.search(str(body.get("q", "")))
        elif name == "playlists":
            return sp.playlists()
        elif name == "queue_add":
            return sp.add_to_queue(str(body.get("uri", "")))
        elif name == "play":
            return sp.play_context(str(body.get("uri", "")))
        else:
            raise ValueError(f"ukendt handling: {name}")

    def settings_changed(self):
        self.spotify.refresh_soon()

    def http_get(self, path, query, req):
        if path == "login":
            try:
                req.redirect(self.spotify.login_url())
            except ValueError as e:  # back to the settings page, which shows the message
                req.redirect(f"http://localhost:{self.ctx.port}/settings?msg=" + urllib.parse.quote(str(e)))
            return True
        if path == "callback":
            err = (query.get("error") or [""])[0]
            try:
                if err:
                    raise ValueError(f"Spotify afviste: {err}")
                self.spotify.callback((query.get("code") or [""])[0], (query.get("state") or [""])[0])
                msg = "Spotify er forbundet ✓"
            except Exception as e:
                msg = str(e)
            req.redirect(f"http://localhost:{self.ctx.port}/settings?msg=" + urllib.parse.quote(msg))
            return True
        return False
