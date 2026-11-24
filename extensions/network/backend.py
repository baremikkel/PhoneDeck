"""Netværk: ping/latency, local + public IP, and VPNs (Tailscale, NetworkManager WireGuard/VPN)."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque

import psutil

WINDOWS = sys.platform == "win32"
HOST_RE = re.compile(r"^[A-Za-z0-9.:-]{1,100}$")
UUID_RE = re.compile(r"^[0-9a-f-]{36}$")


def _run(*args, timeout=5) -> str:
    try:
        kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def ping(host: str) -> float | None:
    """Round trip in ms, or None when there is no answer."""
    if not HOST_RE.match(host) or host.startswith("-"):
        return None
    out = _run("ping", "-n", "1", "-w", "1500", host) if WINDOWS else _run("ping", "-c", "1", "-W", "2", host)
    m = re.search(r"(?:time|tid)[=<]\s*([\d.,]+)\s*ms", out)
    return float(m.group(1).replace(",", ".")) if m else None


def local_ip() -> tuple[str | None, str | None]:
    """(interface, IPv4) of the route to the internet – no packet is sent."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 53))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        return None, None
    for name, addrs in psutil.net_if_addrs().items():
        if any(a.address == ip for a in addrs):
            return name, ip
    return None, ip


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.hist: deque = deque(maxlen=60)
        self.public: str | None = None
        self._public_at = 0.0
        self.vpns: list[dict] = []
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def settings_changed(self):
        self._public_at = 0
        self._wake.set()

    # ---------- VPNs ----------
    def _vpns(self) -> list[dict]:
        out = []
        if shutil.which("nmcli"):
            for line in _run("nmcli", "-t", "-f", "NAME,UUID,TYPE,ACTIVE", "connection", "show").splitlines():
                parts = re.split(r"(?<!\\):", line)
                if len(parts) == 4 and parts[2] in ("wireguard", "vpn"):
                    out.append({"id": parts[1], "name": parts[0].replace("\\:", ":"), "kind": "WireGuard" if parts[2] == "wireguard" else "VPN",
                                "on": parts[3] == "yes"})
        if shutil.which("tailscale"):
            try:
                st = json.loads(_run("tailscale", "status", "--json") or "{}")
                out.append({"id": "tailscale", "name": "Tailscale", "kind": "Tailscale",
                            "on": st.get("BackendState") == "Running",
                            "ip": (st.get("Self") or {}).get("TailscaleIPs", [None])[0]})
            except ValueError:
                pass
        return out

    def _loop(self):
        while not self.ctx.stopped.is_set():
            s = self.ctx.settings()
            self.hist.append(ping(s.get("host") or "1.1.1.1"))
            if s.get("public_ip", True) and time.time() - self._public_at > 900:
                self._public_at = time.time()
                try:
                    with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=6) as r:
                        self.public = json.load(r).get("ip")
                except (OSError, ValueError):
                    self._public_at = time.time() - 840  # try again in a minute
            elif not s.get("public_ip", True):
                self.public = None
            self.vpns = self._vpns()
            self._wake.wait(5)
            self._wake.clear()

    def state(self):
        hist = list(self.hist)
        ok = [h for h in hist if h is not None]
        iface, ip = local_ip()
        return {"ping": hist[-1] if hist else None, "history": hist,
                "loss": round(100 * (len(hist) - len(ok)) / len(hist)) if hist else None,
                "avg": round(sum(ok) / len(ok), 1) if ok else None,
                "host": self.ctx.settings().get("host") or "1.1.1.1",
                "iface": iface, "ip": ip, "public": self.public, "vpns": self.vpns}

    def action(self, name, body):
        if name != "vpn":
            raise ValueError(f"ukendt handling: {name}")
        vid = str((body or {}).get("id", ""))
        vpn = next((v for v in self.vpns if v["id"] == vid), None)
        if not vpn:
            raise ValueError("ukendt VPN")
        if vid == "tailscale":
            out = subprocess.run(["tailscale", "down" if vpn["on"] else "up"], capture_output=True, text=True, timeout=20)
            if out.returncode:
                raise ValueError((out.stderr.strip().splitlines() or ["Tailscale svarede med en fejl"])[-1][:140])
        elif UUID_RE.match(vid):
            out = subprocess.run(["nmcli", "connection", "down" if vpn["on"] else "up", "uuid", vid],
                                 capture_output=True, text=True, timeout=30)
            if out.returncode:
                raise ValueError((out.stderr.strip() or "nmcli svarede med en fejl")[:140])
        self.vpns = self._vpns()
        return {"vpns": self.vpns}
