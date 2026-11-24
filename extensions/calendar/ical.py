"""A small iCalendar (.ics) reader: events in a time range, including repeating ones.

Handles what calendar apps export: all-day and timed events, TZID / UTC / floating
times, DURATION, RRULE (DAILY/WEEKLY/MONTHLY/YEARLY with INTERVAL, COUNT, UNTIL, BYDAY,
BYMONTHDAY), EXDATE and moved single occurrences (RECURRENCE-ID).
"""

from __future__ import annotations

import functools
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MAX_STEPS = 5000   # safety limit when expanding a repeating event

# Windows time zone names (Outlook writes these as TZID, and Windows reports the PC's zone
# this way) -> IANA names with the same rules. The common ones, after CLDR windowsZones.
WINDOWS_ZONES = {
    "UTC": "Etc/UTC", "GMT Standard Time": "Europe/London", "Greenwich Standard Time": "Atlantic/Reykjavik",
    "W. Europe Standard Time": "Europe/Berlin", "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Budapest", "Central European Standard Time": "Europe/Warsaw",
    "W. Central Africa Standard Time": "Africa/Lagos", "GTB Standard Time": "Europe/Bucharest",
    "FLE Standard Time": "Europe/Kiev", "E. Europe Standard Time": "Europe/Chisinau",
    "Turkey Standard Time": "Europe/Istanbul", "Israel Standard Time": "Asia/Jerusalem",
    "Egypt Standard Time": "Africa/Cairo", "South Africa Standard Time": "Africa/Johannesburg",
    "Russian Standard Time": "Europe/Moscow", "Arabian Standard Time": "Asia/Dubai",
    "Arab Standard Time": "Asia/Riyadh", "Iran Standard Time": "Asia/Tehran",
    "Pakistan Standard Time": "Asia/Karachi", "India Standard Time": "Asia/Kolkata",
    "Bangladesh Standard Time": "Asia/Dhaka", "SE Asia Standard Time": "Asia/Bangkok",
    "China Standard Time": "Asia/Shanghai", "Singapore Standard Time": "Asia/Singapore",
    "Taipei Standard Time": "Asia/Taipei", "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul", "AUS Eastern Standard Time": "Australia/Sydney",
    "E. Australia Standard Time": "Australia/Brisbane", "Cen. Australia Standard Time": "Australia/Adelaide",
    "W. Australia Standard Time": "Australia/Perth", "New Zealand Standard Time": "Pacific/Auckland",
    "Hawaiian Standard Time": "Pacific/Honolulu", "Alaskan Standard Time": "America/Anchorage",
    "Pacific Standard Time": "America/Los_Angeles", "US Mountain Standard Time": "America/Phoenix",
    "Mountain Standard Time": "America/Denver", "Central Standard Time": "America/Chicago",
    "Central Standard Time (Mexico)": "America/Mexico_City", "Canada Central Standard Time": "America/Regina",
    "Eastern Standard Time": "America/New_York", "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns", "SA Pacific Standard Time": "America/Bogota",
    "E. South America Standard Time": "America/Sao_Paulo", "Argentina Standard Time": "America/Buenos_Aires",
    "Morocco Standard Time": "Africa/Casablanca", "E. Africa Standard Time": "Africa/Nairobi",
}


@functools.lru_cache(maxsize=1)
def local_zone():
    """The PC's time zone *with* its daylight-saving rules. (datetime.now().astimezone() only
    gives today's fixed offset, which puts summer events an hour off in winter.)"""
    name = os.environ.get("TZ", "")
    if not name and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation") as k:
                name = WINDOWS_ZONES.get(winreg.QueryValueEx(k, "TimeZoneKeyName")[0].strip("\0 "), "")
        except OSError:
            pass
    elif not name:
        try:
            with open("/etc/timezone", encoding="utf-8") as f:
                name = f.read().strip()
        except OSError:
            link = os.path.realpath("/etc/localtime")
            name = link.split("zoneinfo/", 1)[1] if "zoneinfo/" in link else ""
    try:
        return ZoneInfo(name) if name else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone().tzinfo


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _parse_line(line: str) -> tuple[str, dict, str]:
    # NAME;PARAM=a;PARAM2="b:c":value  (a colon inside quotes is not the separator)
    m = re.match(r'^([^:;]+)((?:;[^:;=]+=(?:"[^"]*"|[^:;]*))*):(.*)$', line)
    if not m:
        return line.upper(), {}, ""
    params = {k.upper(): v.strip('"') for k, v in re.findall(r';([^=;]+)=("[^"]*"|[^;:]*)', m.group(2))}
    return m.group(1).upper(), params, m.group(3)


def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _tz(name: str | None, local):
    if not name:
        return local
    try:
        return ZoneInfo(WINDOWS_ZONES.get(name, name))  # Outlook: "Romance Standard Time"
    except (ZoneInfoNotFoundError, ValueError):
        return local  # unknown name: assume the PC's zone


def _when(value: str, params: dict, local) -> tuple[datetime, bool]:
    """-> (aware datetime, all_day)"""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d.replace(tzinfo=local), True
    if value.endswith("Z"):
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc), False
    return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=_tz(params.get("TZID"), local)), False


def _duration(v: str) -> timedelta:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v.strip())
    if not m:
        return timedelta(0)
    sign = -1 if m.group(1) == "-" else 1
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    return sign * timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


def _add_months(dt: datetime, n: int) -> datetime | None:
    y, mo = divmod(dt.month - 1 + n, 12)
    try:
        return dt.replace(year=dt.year + y, month=mo + 1)
    except ValueError:
        return None  # e.g. 31st in a short month – skipped, like calendar apps do


def _occurrences(ev: dict, start: datetime, end: datetime, local):
    """Start times of an event (and its repeats) that overlap [start, end)."""
    first, length = ev["start"], ev["end"] - ev["start"]
    rule = ev.get("rrule")
    if not rule:
        if first < end and first + length > start:
            yield first
        return
    r = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    freq = r.get("FREQ", "DAILY")
    interval = max(1, int(r.get("INTERVAL", "1") or 1))
    count = int(r["COUNT"]) if r.get("COUNT", "").isdigit() else None
    until = None
    if r.get("UNTIL"):
        until, _ = _when(r["UNTIL"], {}, local)
        if len(r["UNTIL"]) == 8:
            until += timedelta(days=1)
    byday = [d[-2:] for d in r.get("BYDAY", "").split(",") if d]
    bymonthday = [int(x) for x in r.get("BYMONTHDAY", "").split(",") if x.lstrip("-").isdigit()]
    excluded = ev.get("exdates", set())

    # walk the repeats in the event's own time zone, so 09:00 stays 09:00 across DST
    base = first.astimezone(first.tzinfo)
    n = 0
    for step in range(MAX_STEPS):
        if freq == "DAILY":
            period = [base + timedelta(days=step * interval)]
        elif freq == "WEEKLY":
            week = base + timedelta(weeks=step * interval)
            monday = week - timedelta(days=week.weekday())
            days = byday or [WEEKDAYS[base.weekday()]]
            period = sorted(monday + timedelta(days=WEEKDAYS.index(d)) for d in days if d in WEEKDAYS)
        elif freq == "MONTHLY":
            m = _add_months(base.replace(day=1), step * interval)
            if bymonthday:
                period = []
                for md in bymonthday:
                    try:
                        period.append(m.replace(day=md))
                    except ValueError:
                        pass
            elif byday and r.get("BYDAY", "")[:-2].lstrip("+-").isdigit():
                # e.g. 2TU = second Tuesday, -1FR = last Friday
                nth = int(r["BYDAY"][:-2]); wd = WEEKDAYS.index(r["BYDAY"][-2:])
                days = [m + timedelta(days=i) for i in range(31) if (m + timedelta(days=i)).month == m.month
                        and (m + timedelta(days=i)).weekday() == wd]
                period = [days[nth - 1 if nth > 0 else nth]] if days and abs(nth) <= len(days) else []
            else:
                one = _add_months(base, step * interval)
                period = [one] if one else []
        elif freq == "YEARLY":
            one = _add_months(base, step * interval * 12)
            period = [one] if one else []
        else:
            return
        for occ in period:
            if occ < first:
                continue
            if until and occ >= until or count is not None and n >= count:
                return
            n += 1
            if occ >= end:
                return
            if occ + length > start and occ.astimezone(timezone.utc) not in excluded:
                yield occ


def events_between(text: str, start: datetime, end: datetime, local=None) -> list[dict]:
    local = local or local_zone()
    events, moved = [], {}
    cur = None
    for line in _unfold(text):
        name, params, value = _parse_line(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            cur = {"exdates": set()}
        elif name == "END" and value.upper() == "VEVENT" and cur is not None:
            if "start" in cur and cur.get("status") != "CANCELLED":
                if "end" not in cur:
                    cur["end"] = cur["start"] + (cur.pop("duration", None) or (timedelta(days=1) if cur["all_day"] else timedelta(0)))
                if "recurrence_id" in cur:
                    moved.setdefault(cur.get("uid"), set()).add(cur["recurrence_id"])
                events.append(cur)
            cur = None
        elif cur is not None:
            try:
                if name == "DTSTART":
                    cur["start"], cur["all_day"] = _when(value, params, local)
                elif name == "DTEND":
                    cur["end"], _ = _when(value, params, local)
                elif name == "DURATION":
                    cur["duration"] = _duration(value)
                elif name == "SUMMARY":
                    cur["title"] = _unescape(value)
                elif name == "LOCATION":
                    cur["location"] = _unescape(value)
                elif name == "UID":
                    cur["uid"] = value
                elif name == "STATUS":
                    cur["status"] = value.upper()
                elif name == "RRULE":
                    cur["rrule"] = value
                elif name == "EXDATE":
                    for v in value.split(","):
                        cur["exdates"].add(_when(v, params, local)[0].astimezone(timezone.utc))
                elif name == "RECURRENCE-ID":
                    cur["recurrence_id"] = _when(value, params, local)[0].astimezone(timezone.utc)
            except ValueError:
                continue  # one odd line shouldn't hide the whole calendar
    out = []
    for ev in events:
        skip = moved.get(ev.get("uid"), set()) if "rrule" in ev else set()
        ev["exdates"] |= skip
        for occ in _occurrences(ev, start, end, local):
            length = ev["end"] - ev["start"]
            out.append({"title": ev.get("title") or "(uden titel)", "location": ev.get("location", ""),
                        "start": occ, "end": occ + length, "all_day": ev.get("all_day", False)})
    out.sort(key=lambda e: (e["start"], not e["all_day"]))
    return out
