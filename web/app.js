"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const k = (card, key) => $(`#${card} [data-k="${key}"]`);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------- formatting ----------
const fmtTok = (n) => n == null ? "–" : n >= 1e9 ? (n / 1e9).toFixed(1) + "B"
  : n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M"
  : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k" : String(Math.round(n));
const fmtBytes = (b) => b == null ? "–" : b >= 1e9 ? (b / 1e9).toFixed(1) + " GB"
  : b >= 1e6 ? (b / 1e6).toFixed(1) + " MB" : b >= 1e3 ? (b / 1e3).toFixed(0) + " kB" : Math.round(b) + " B";
const fmtRate = (b) => fmtBytes(b) + "/s";
const fmtTime = (s) => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const fmtDur = (s) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h} t ${m} m` : `${m} m`; };
const round = (v) => v == null ? "–" : Math.round(v);

function setTemp(el, t, warn = 75, hot = 88) {
  el.textContent = round(t);
  el.classList.toggle("warn", t != null && t >= warn && t < hot);
  el.classList.toggle("hot", t != null && t >= hot);
}

// ---------- canvas helpers ----------
function prep(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return [ctx, w, h];
}

function sparkline(canvas, data, color, max = 100) {
  const [ctx, w, h] = prep(canvas);
  const pts = data.map((v) => v ?? 0);
  if (pts.length < 2 || h < 4) return;
  const n = 90; // fixed slots so the line scrolls in from the right
  const step = w / (n - 1), x0 = w - (pts.length - 1) * step;
  const y = (v) => h - 2 - (Math.min(v, max) / max) * (h - 4);
  ctx.beginPath();
  pts.forEach((v, i) => i ? ctx.lineTo(x0 + i * step, y(v)) : ctx.moveTo(x0, y(v)));
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.stroke();
  ctx.lineTo(w, h); ctx.lineTo(x0, h); ctx.closePath();
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, color + "55"); g.addColorStop(1, color + "00");
  ctx.fillStyle = g; ctx.fill();
}

function bars(canvas, data, color) {
  const [ctx, w, h] = prep(canvas);
  const max = Math.max(...data, 1), gap = 2, bw = (w - gap * (data.length - 1)) / data.length;
  data.forEach((v, i) => {
    const bh = v ? Math.max(2, (v / max) * (h - 2)) : 1;
    ctx.fillStyle = v ? color : css("--line");
    ctx.beginPath();
    ctx.roundRect(i * (bw + gap), h - bh, bw, bh, [2, 2, 0, 0]);
    ctx.fill();
  });
}

// ---------- render ----------
let last = null;
let media = { pos: 0, len: 0, playing: false, at: 0 };

function render(s) {
  last = s;
  const hw = s.hw || {};

  // CPU
  const cpu = hw.cpu || {};
  k("cpu", "name").textContent = cpu.name || "";
  k("cpu", "load").textContent = round(cpu.load);
  setTemp(k("cpu", "temp"), cpu.temp);
  k("cpu", "freq").textContent = round(cpu.freq);
  sparkline(k("cpu", "spark"), hw.history?.cpu || [], css("--cpu"));

  // GPU
  const gpu = hw.gpu;
  if (gpu) {
    k("gpu", "name").textContent = gpu.name || "";
    k("gpu", "load").textContent = round(gpu.load);
    setTemp(k("gpu", "temp"), gpu.temp_hot ?? gpu.temp, 85, 100);
    k("gpu", "power").textContent = round(gpu.power);
    const vp = gpu.vram_total ? (gpu.vram_used / gpu.vram_total) * 100 : 0;
    k("gpu", "vram").style.width = vp + "%";
    k("gpu", "vramtxt").textContent = gpu.vram_total ? `VRAM ${fmtBytes(gpu.vram_used)} / ${fmtBytes(gpu.vram_total)}` : "";
    sparkline(k("gpu", "spark"), hw.history?.gpu || [], css("--gpu"));
  }

  // System strip
  if (hw.ram) k("sys", "ram").textContent = `${(hw.ram.used / 1e9).toFixed(1)} / ${(hw.ram.total / 1e9).toFixed(0)} GB`;
  if (hw.net) { k("sys", "down").textContent = fmtRate(hw.net.down); k("sys", "up").textContent = fmtRate(hw.net.up); }
  if (hw.disk) {
    k("sys", "disk").textContent = `${Math.round(hw.disk.used / hw.disk.total * 100)} % · ${fmtRate(hw.disk.read + hw.disk.write)}`;
    k("sys", "nvme").textContent = hw.disk.temps?.length ? hw.disk.temps.map((t) => Math.round(t) + "°").join(" ") : "–";
  }

  renderMedia(s.media);
  renderClaude(s.claude || {});
  renderButtons(s);
}

let artKey = null;
function renderMedia(m) {
  const img = k("media", "art");
  if (!m || m.error || !m.title) {
    k("media", "title").textContent = m?.error ? "Medie: " + m.error : "Intet afspilles";
    k("media", "artist").textContent = ""; k("media", "player").textContent = "";
    k("media", "pos").textContent = k("media", "len").textContent = "";
    k("media", "progress").style.width = "0";
    k("media", "playbtn").textContent = "▶";
    if (artKey !== null) { img.removeAttribute("src"); artKey = null; }
    media.playing = false;
    return;
  }
  k("media", "player").textContent = m.player;
  k("media", "title").textContent = m.title;
  k("media", "artist").textContent = [m.artist, m.album].filter(Boolean).join(" · ");
  k("media", "playbtn").textContent = m.status === "Playing" ? "⏸" : "▶";
  if (m.art_key !== artKey) {
    artKey = m.art_key;
    if (m.art) img.src = "/api/art?k=" + encodeURIComponent(m.art_key || "");
    else img.removeAttribute("src");
  }
  media = { pos: m.position, len: m.length, playing: m.status === "Playing", at: performance.now() };
  tickMedia();
}

function tickMedia() {
  if (!media.len) return;
  const pos = Math.min(media.len, media.pos + (media.playing ? (performance.now() - media.at) / 1000 : 0));
  k("media", "pos").textContent = fmtTime(pos);
  k("media", "len").textContent = fmtTime(media.len);
  k("media", "progress").style.width = (pos / media.len) * 100 + "%";
}

function renderClaude(c) {
  if (!c.available) { k("claude", "block").textContent = "–"; k("claude", "reset").textContent = c.error || "ingen data"; return; }
  const sum = (b) => b ? b.input + b.output + b.cache_write : null;
  k("claude", "block").textContent = fmtTok(sum(c.last5h));
  k("claude", "today").textContent = fmtTok(sum(c.today));
  k("claude", "week").textContent = fmtTok(sum(c.last7d));
  k("claude", "out").textContent = fmtTok(c.today?.output);
  k("claude", "msgs").textContent = c.today?.messages ?? "–";
  k("claude", "reset").textContent = c.block_reset_in ? "↻ " + fmtDur(c.block_reset_in) : "intet aktivt vindue";
  bars(k("claude", "hourly"), c.hourly || [], css("--claude"));
}

let buttonsKey = "";
function renderButtons(s) {
  const a = s.audio || {};
  const vol = k("buttons", "vol");
  vol.textContent = a.output?.muted ? "🔇" : (a.output?.volume ?? "–") + " %";
  vol.classList.toggle("on", !!a.output?.muted);
  k("buttons", "mic").classList.toggle("on", !!a.mic?.muted);

  const key = JSON.stringify(s.buttons || []);
  if (key === buttonsKey) return;
  buttonsKey = key;
  const box = $("#custom");
  box.replaceChildren(...(s.buttons || []).map((b) => {
    const el = document.createElement("button");
    el.dataset.action = b.id;
    const icon = document.createElement("b"); icon.textContent = b.icon;
    el.append(icon, b.label);
    return el;
  }));
}

// ---------- actions ----------
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  navigator.vibrate?.(12);
  try {
    await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: btn.dataset.action }) });
  } catch { /* offline banner covers this */ }
});

// Tap the clock: fullscreen + keep the screen awake
let wakeLock = null;
async function keepAwake() {
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { /* not allowed */ }
}
$("#clock").addEventListener("click", () => {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
  else document.exitFullscreen?.();
  keepAwake();
});
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && wakeLock) keepAwake(); });

// ---------- clock + burn-in protection ----------
function tickClock() {
  const d = new Date();
  k("sys", "time").textContent = d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
  k("sys", "date").textContent = d.toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" });
  tickMedia();
}
setInterval(tickClock, 1000); tickClock();

// Nudge everything a few pixels every minute so static UI doesn't burn into the AMOLED
setInterval(() => {
  const r = () => Math.round(Math.random() * 6 - 3);
  $("#deck").style.transform = `translate(${r()}px, ${r()}px)`;
}, 60_000);

// Dim at night (23–07)
setInterval(() => { const h = new Date().getHours(); document.body.classList.toggle("dim", h >= 23 || h < 7); }, 30_000);

// ---------- live data ----------
function connect() {
  const es = new EventSource("/api/stream");
  es.onmessage = (e) => { $("#offline").hidden = true; render(JSON.parse(e.data)); };
  es.onerror = () => { $("#offline").hidden = false; };
}
connect();
window.addEventListener("resize", () => last && render(last));
