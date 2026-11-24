"""Diske: free space per drive (psutil) and SMART health (UDisks2 over D-Bus, no root)."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time

import psutil

SKIP_FS = {"squashfs", "tmpfs", "devtmpfs", "overlay", "efivarfs", "proc", "sysfs", "fuse.portal", "ramfs", "nsfs"}
UD = "org.freedesktop.UDisks2"


def _busctl(*args) -> object:
    try:
        out = subprocess.run(["busctl", "--system", "--json=short", "call", UD, *args],
                             capture_output=True, text=True, timeout=8).stdout
        return json.loads(out)["data"] if out else None
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
        return None


def _v(props: dict, name: str, default=None):
    p = props.get(name)
    return p.get("data", default) if isinstance(p, dict) else default


def _bytes_str(v) -> str:
    """UDisks sends paths as zero-terminated byte arrays."""
    return bytes(v[:-1] if v and v[-1] == 0 else v).decode(errors="replace") if isinstance(v, list) else str(v or "")


def partitions() -> list[dict]:
    seen, out = set(), []
    for p in psutil.disk_partitions(all=False):
        if p.fstype in SKIP_FS or p.mountpoint.startswith(("/snap", "/boot/efi", "/var/snap", "/run")):
            continue
        if p.device in seen:  # bind mounts, btrfs subvolumes
            continue
        seen.add(p.device)
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        if u.total < 1024 ** 3:  # tiny partitions (EFI, recovery …)
            continue
        out.append({"device": p.device, "mount": p.mountpoint, "fs": p.fstype,
                    "used": u.used, "total": u.total, "percent": round(u.percent)})
    return out


def drives() -> list[dict]:
    if not shutil.which("busctl"):
        return []
    objs = _busctl("/org/freedesktop/UDisks2", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    if not objs:
        return []
    objs = objs[0]
    dev_of = {}  # drive path -> [/dev/… of its block devices]
    for path, ifaces in objs.items():
        b = ifaces.get(f"{UD}.Block")
        if b:
            dev_of.setdefault(_v(b, "Drive"), []).append(_bytes_str(_v(b, "Device")))
    out = []
    for path, ifaces in objs.items():
        d = ifaces.get(f"{UD}.Drive")
        if not d or _v(d, "Size", 0) == 0 or _v(d, "Optical", False):
            continue
        item = {"id": path.rsplit("/", 1)[-1], "model": _v(d, "Model") or _v(d, "Vendor") or "Drev",
                "size": _v(d, "Size", 0), "removable": _v(d, "Removable", False),
                "rotational": (_v(d, "RotationRate", 0) or 0) > 0, "devices": dev_of.get(path, []),
                "health": "unknown"}
        nvme = ifaces.get(f"{UD}.NVMe.Controller")
        ata = ifaces.get(f"{UD}.Drive.Ata")
        if nvme:
            item["kind"] = "NVMe"
            item["temp"] = round(_v(nvme, "SmartTemperature", 0) - 273.15) if _v(nvme, "SmartTemperature") else None
            item["hours"] = _v(nvme, "SmartPowerOnHours")
            warnings = _v(nvme, "SmartCriticalWarning", []) or []
            attrs = _busctl(path, f"{UD}.NVMe.Controller", "SmartGetAttributes", "a{sv}", "0")
            a = attrs[0] if attrs else {}
            item["wear"] = _v(a, "percent_used")
            item["spare"] = _v(a, "avail_spare")
            item["media_errors"] = _v(a, "media_errors")
            item["written"] = _v(a, "total_data_written")
            spare_thresh = _v(a, "spare_thresh", 10) or 10
            if warnings:
                item["health"], item["note"] = "bad", "Disken melder kritisk advarsel: " + ", ".join(warnings)
            elif (item["media_errors"] or 0) > 0 or (item["spare"] is not None and item["spare"] <= spare_thresh * 2) \
                    or (item["wear"] or 0) >= 90:
                why = []
                if item["media_errors"]:
                    why.append(f"{item['media_errors']} mediefejl (data der ikke kunne læses)")
                if item["spare"] is not None and item["spare"] <= spare_thresh * 2:
                    why.append(f"kun {item['spare']} % reserve tilbage")
                if (item["wear"] or 0) >= 90:
                    why.append(f"{item['wear']} % slidt")
                item["health"], item["note"] = "warn", " · ".join(why) + " – tag backup"
            else:
                item["health"] = "ok"
        elif ata and _v(ata, "SmartSupported", False):
            item["kind"] = "SSD" if not item["rotational"] else "HDD"
            item["temp"] = round(_v(ata, "SmartTemperature", 0) - 273.15) if _v(ata, "SmartTemperature") else None
            secs = _v(ata, "SmartPowerOnSeconds")
            item["hours"] = round(secs / 3600) if secs else None
            bad = _v(ata, "SmartNumBadSectors", 0) or 0
            item["media_errors"] = bad
            if _v(ata, "SmartFailing", False):
                item["health"], item["note"] = "bad", "SMART siger, at disken er ved at gå i stykker"
            elif bad > 0 or (_v(ata, "SmartNumAttributesFailing", 0) or 0) > 0:
                item["health"], item["note"] = "warn", f"{bad} dårlige sektorer – tag backup"
            else:
                item["health"] = "ok"
        else:
            item["kind"] = "USB" if item["removable"] else "Disk"
        out.append(item)
    out.sort(key=lambda d: (d["removable"], d["model"]))
    return out


class Extension:
    def __init__(self, ctx):
        self.ctx = ctx
        self.drives: list[dict] = []
        self.parts: list[dict] = []
        self._at = 0.0
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self.ctx.stopped.is_set():
            self.parts = partitions()
            if time.time() - self._at > 600:  # SMART changes slowly
                self._at = time.time()
                self.drives = drives()
            self.ctx.stopped.wait(30)

    def state(self):
        return {"drives": self.drives, "parts": self.parts, "warn": int(self.ctx.settings().get("warn") or 90)}
