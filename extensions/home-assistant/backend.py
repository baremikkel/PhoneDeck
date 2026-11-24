"""Home Assistant: show and control lights, switches, scenes, scripts and sensors.

Uses the REST API with a long-lived access token. The token is a secret setting: it is
only sent to the Home Assistant address you entered, never back to a browser.
Only entities that are shown on the phone can be controlled, and only with a fixed set
of services per domain.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request

POLL = 5
ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
DEFAULT_DOMAINS = ("light", "switch", "scene", "script", "input_boolean", "fan", "cover")
SHOWN_DOMAINS = DEFAULT_DOMAINS + ("sensor", "binary_sensor", "climate", "lock", "media_player")
# what a tap does, per domain
TAP = {"light": "toggle", "switch": "toggle", "input_boolean": "toggle", "fan": "toggle",
       "cover": "toggle", "scene": "turn_on", "script": "turn_on", "lock": None}


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.data: dict = {}
        self.allowed: set[str] = set()
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def settings_changed(self):
        self._wake.set()

    # ---------- talking to Home Assistant ----------
    def _base(self) -> tuple[str, str]:
        s = self.ctx.settings()
        url, token = (s.get("url") or "").strip().rstrip("/"), s.get("token") or ""
        if not url or not token:
            raise LookupError("Sæt adresse og token under Indstillinger → Home Assistant")
        return url, token

    def _call(self, method: str, path: str, body: dict | None = None):
        url, token = self._base()
        req = urllib.request.Request(url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise ValueError({401: "Home Assistant afviste tokenet", 404: "Fandt ikke Home Assistant på adressen"}
                             .get(e.code, f"Home Assistant svarede {e.code}")) from None
        except (urllib.error.URLError, OSError) as e:
            raise ValueError(f"Kan ikke nå Home Assistant ({getattr(e, 'reason', e)})") from None
        return json.loads(raw) if raw else None

    def _wanted(self) -> list[str]:
        raw = self.ctx.settings().get("entities") or ""
        return [e.strip() for e in raw.replace(";", ",").split(",") if ENTITY_RE.match(e.strip())][:60]

    def _fetch(self) -> dict:
        states = self._call("GET", "/api/states") or []
        by_id = {s["entity_id"]: s for s in states if isinstance(s, dict) and "entity_id" in s}
        wanted = self._wanted()
        if wanted:
            chosen = [by_id[e] for e in wanted if e in by_id]
        else:
            chosen = sorted((s for s in by_id.values() if s["entity_id"].split(".")[0] in DEFAULT_DOMAINS),
                            key=lambda s: (DEFAULT_DOMAINS.index(s["entity_id"].split(".")[0]),
                                           (s.get("attributes") or {}).get("friendly_name", s["entity_id"]).lower()))[:40]
        items = []
        for s in chosen:
            eid = s["entity_id"]
            domain = eid.split(".")[0]
            if domain not in SHOWN_DOMAINS:
                continue
            a = s.get("attributes") or {}
            item = {"id": eid, "domain": domain, "name": a.get("friendly_name") or eid,
                    "state": s.get("state"), "unit": a.get("unit_of_measurement") or "",
                    "tap": TAP.get(domain) is not None}
            if domain == "light" and a.get("brightness") is not None:
                item["brightness"] = round(a["brightness"] / 255 * 100)
            if domain == "climate":
                item["temp"] = a.get("current_temperature"); item["target"] = a.get("temperature")
            if a.get("device_class"):
                item["class"] = a["device_class"]
            items.append(item)
        self.allowed = {i["id"] for i in items if i["tap"]}
        return {"items": items, "updated": time.time()}

    def _loop(self):
        while not self.ctx.stopped.is_set():
            try:
                self.data = self._fetch()
                wait = POLL
            except LookupError as e:
                self.data = {"setup": True, "error": str(e)}
                wait = 30
            except (ValueError, TypeError, KeyError) as e:
                self.data = dict(self.data, error=str(e)) if self.data.get("items") else {"error": str(e)}
                wait = 20
            self._wake.wait(wait)
            self._wake.clear()

    # ---------- phone ----------
    def state(self):
        return self.data

    def action(self, name, body):
        body = body or {}
        if name == "forget":
            self.ctx.clear_settings(["token"])
            self.data = {}
            self._wake.set()
            return {}
        if name not in ("tap", "brightness"):
            raise ValueError(f"ukendt handling: {name}")
        eid = str(body.get("id", ""))
        if not ENTITY_RE.match(eid) or eid not in self.allowed:
            raise ValueError("ukendt enhed")
        domain = eid.split(".")[0]
        if name == "tap":
            self._call("POST", f"/api/services/{domain}/{TAP[domain]}", {"entity_id": eid})
        else:
            if domain != "light":
                raise ValueError("kun lys kan dæmpes")
            pct = max(1, min(100, int(body.get("value", 50))))
            self._call("POST", "/api/services/light/turn_on", {"entity_id": eid, "brightness_pct": pct})
        self._wake.set()  # show the new state right away
        return {}

    def info(self):
        d = self.data
        if d.get("error"):
            return {"status": "⚠ " + d["error"]}
        if d.get("items") is not None:
            return {"status": f"✓ Forbundet · {len(d['items'])} enheder"}
        return {"status": "Forbinder …"}
