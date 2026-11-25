"""Website icons for Stream Deck buttons that open a website.

The editor asks the PC to fetch a site's icon once (POST /api/siteicon). The icon is
stored in the cache folder, and the phone shows it from GET /api/siteicon?site=<origin>,
which only ever serves icons that are already cached – it never fetches anything itself.

Which icon: the largest one the page links to, preferring ``apple-touch-icon`` (usually a
crisp 180×180 PNG made for home screens), then ``<link rel="icon">``, then /favicon.ico.
"""

from __future__ import annotations

import hashlib
import html.parser
import os
import re
import threading
import urllib.parse
import urllib.request

from . import paths

DIR = paths.cache("siteicons")
MAX_ICON = 512 * 1024
MAX_HTML = 512 * 1024
TIMEOUT = 6
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 PhoneDeck"
ORIGIN_RE = re.compile(r"^https?://[a-z0-9.\-\[\]:]{1,200}$")
_lock = threading.Lock()


def origin(url: str) -> str | None:
    """'https://www.Messenger.com/t/123' -> 'https://www.messenger.com'"""
    try:
        u = urllib.parse.urlsplit(str(url).strip())
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    host = u.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    try:
        port = u.port
    except ValueError:
        return None
    if port == {"http": 80, "https": 443}[u.scheme]:
        port = None
    o = f"{u.scheme}://{host}" + (f":{port}" if port else "")
    return o if ORIGIN_RE.match(o) else None


def _file(site: str) -> str:
    return os.path.join(DIR, hashlib.sha1(site.encode()).hexdigest()[:20])


def _kind(data: bytes) -> str | None:
    """Content type from the first bytes – never trust the server's header for this."""
    head = data[:256].lstrip()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith((b"<svg", b"<?xml")) and b"<svg" in data[:2048]:
        return "image/svg+xml"
    return None


def cached(site: str) -> tuple[bytes, str] | None:
    if not ORIGIN_RE.match(site or ""):
        return None
    try:
        with open(_file(site), "rb") as f:
            data = f.read(MAX_ICON + 1)
    except OSError:
        return None
    kind = _kind(data)
    return (data, kind) if kind and len(data) <= MAX_ICON else None


class _Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons: list[tuple[int, str]] = []  # (score, href)
        self.base: str | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]
        if tag != "link" or not a.get("href"):
            return
        rel = a.get("rel", "").lower().split()
        if "mask-icon" in rel or not any(r in ("icon", "apple-touch-icon", "apple-touch-icon-precomposed") for r in rel):
            return
        size = 0
        for s in a.get("sizes", "").lower().split():
            if s == "any":
                size = max(size, 256)  # scalable (SVG)
            m = re.match(r"(\d+)x(\d+)", s)
            if m:
                size = max(size, int(m.group(1)))
        if not size:
            size = 180 if "apple-touch-icon" in " ".join(rel) else 32
            if a["href"].lower().split("?")[0].endswith(".svg"):
                size = 256
        # big enough for a phone tile beats huge; apple-touch-icon gets a small bonus (opaque, made for tiles)
        score = min(size, 256) + (20 if any(r.startswith("apple-touch-icon") for r in rel) else 0)
        self.icons.append((score, a["href"]))


def _get(url: str, limit: int) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,image/*,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read(limit + 1), r.geturl()


def fetch(url: str) -> str:
    """Fetch and cache the icon for the site of `url`. Returns its origin, or raises
    ValueError with a Danish message."""
    site = origin(url)
    if not site:
        raise ValueError("adressen skal starte med http:// eller https://")
    candidates: list[str] = []
    base = site + "/"
    # the page itself first (a sub-site can have its own icon), then the front page
    for page_url in dict.fromkeys([url.strip(), site + "/"]):
        try:
            page, final = _get(page_url, MAX_HTML)
            p = _Links()
            p.feed(page[:MAX_HTML].decode("utf-8", "replace"))
        except (OSError, ValueError):
            continue  # some sites refuse scripts; /favicon.ico may still work
        base = urllib.parse.urljoin(final, p.base or "")
        candidates = [urllib.parse.urljoin(base, h) for _, h in sorted(p.icons, key=lambda x: -x[0])]
        if candidates:
            break
    candidates.append(urllib.parse.urljoin(base, "/favicon.ico"))
    if site + "/favicon.ico" not in candidates:
        candidates.append(site + "/favicon.ico")
    for c in list(dict.fromkeys(candidates))[:6]:
        if not c.startswith(("http://", "https://")):
            continue
        try:
            data, _ = _get(c, MAX_ICON)
        except (OSError, ValueError):
            continue
        if len(data) <= MAX_ICON and _kind(data):
            with _lock:
                os.makedirs(DIR, exist_ok=True)
                tmp = _file(site) + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, _file(site))
            return site
    raise ValueError("fandt intet ikon på siden")


def ensure(sites: list[str]) -> None:
    """Fetch icons that are missing (e.g. buttons copied from another PC), in the background."""
    missing = [s for s in dict.fromkeys(sites) if ORIGIN_RE.match(s) and not cached(s)]
    if not missing:
        return

    def run():
        for s in missing:
            try:
                fetch(s + "/")
            except ValueError:
                pass
    threading.Thread(target=run, daemon=True, name="siteicons").start()
