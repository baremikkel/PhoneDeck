"""Vejr: current weather, the next 24 hours and 7 days from Open-Meteo (no key needed).

Only the place name (for the lookup) and its coordinates are sent to open-meteo.com.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
POLL = 15 * 60


def _get(url: str, params: dict) -> dict:
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "PhoneDeck"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.data: dict = {}
        self.place: dict | None = None   # {name, lat, lon, country}
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def settings_changed(self):
        self.place = None
        self._wake.set()

    def _lookup(self, name: str) -> dict:
        r = _get(GEO, {"name": name, "count": 1, "language": "da", "format": "json"})
        hit = (r.get("results") or [None])[0]
        if not hit:
            raise ValueError(f"Fandt ikke stedet \"{name}\"")
        return {"name": hit.get("name"), "country": hit.get("country", ""), "admin": hit.get("admin1", ""),
                "lat": hit["latitude"], "lon": hit["longitude"]}

    def _fetch(self) -> dict:
        s = self.ctx.settings()
        name = (s.get("place") or "").strip()
        if not name:
            return {"error": "Vælg et sted under Indstillinger → Vejr"}
        if not self.place or self.place.get("query") != name:
            self.place = dict(self._lookup(name), query=name)
        imperial = s.get("units") == "imperial"
        r = _get(FORECAST, {
            "latitude": self.place["lat"], "longitude": self.place["lon"], "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,"
                       "wind_direction_10m,precipitation,is_day",
            "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "precipitation_probability_max,sunrise,sunset,wind_speed_10m_max",
            "forecast_days": int(self.ctx.number("days", 7)),
            "forecast_hours": int(self.ctx.number("hours", 24)) + 1,  # +1: the graph shows both ends
            "temperature_unit": "fahrenheit" if imperial else "celsius",
            "wind_speed_unit": "mph" if imperial else "ms",
        })
        cur, hourly, daily = r.get("current") or {}, r.get("hourly") or {}, r.get("daily") or {}
        hours = [{"t": t, "temp": hourly["temperature_2m"][i], "pop": (hourly.get("precipitation_probability") or [None] * 99)[i],
                  "rain": hourly["precipitation"][i], "code": hourly["weather_code"][i], "day": hourly["is_day"][i]}
                 for i, t in enumerate(hourly.get("time") or [])]
        days = [{"date": d, "code": daily["weather_code"][i], "max": daily["temperature_2m_max"][i],
                 "min": daily["temperature_2m_min"][i], "rain": daily["precipitation_sum"][i],
                 "pop": daily["precipitation_probability_max"][i], "sunrise": daily["sunrise"][i],
                 "sunset": daily["sunset"][i], "wind": daily["wind_speed_10m_max"][i]}
                for i, d in enumerate(daily.get("time") or [])]
        return {
            "place": self.place["name"], "region": self.place.get("admin") or self.place.get("country"),
            "units": {"temp": "°F" if imperial else "°C", "wind": "mph" if imperial else "m/s"},
            "now": {"temp": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"),
                    "humidity": cur.get("relative_humidity_2m"), "code": cur.get("weather_code"),
                    "wind": cur.get("wind_speed_10m"), "wind_dir": cur.get("wind_direction_10m"),
                    "rain": cur.get("precipitation"), "day": cur.get("is_day")},
            "hours": hours, "days": days, "updated": time.time(),
        }

    def _loop(self):
        while not self.ctx.stopped.is_set():
            try:
                self.data = self._fetch()
                wait = self.ctx.number("poll_min", POLL / 60) * 60
            except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as e:
                msg = str(e.reason if isinstance(e, urllib.error.URLError) else e)
                self.data = dict(self.data, error=msg) if self.data.get("now") else {"error": msg}
                wait = 120
            self._wake.wait(wait)
            self._wake.clear()

    def state(self):
        return self.data

    def info(self):
        d = self.data
        if d.get("place") and not d.get("error"):
            return {"status": f"✓ {d['place']}, {d.get('region') or ''}".rstrip(", ")}
        return {"status": f"⚠ {d['error']}" if d.get("error") else "Henter …"}
