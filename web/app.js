"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
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
const round = (v) => v == null ? "–" : String(Math.round(v));

// ---------- binding helpers: one value can appear on several pages ----------
const setText = (key, v) => $$(`[data-b="${key}"]`).forEach((el) => { if (el.textContent !== v) el.textContent = v; });
const setWidth = (key, pct) => $$(`[data-w="${key}"]`).forEach((el) => { el.style.width = Math.max(0, Math.min(100, pct || 0)) + "%"; });
const setOn = (key, on) => $$(`[data-on="${key}"]`).forEach((el) => el.classList.toggle("on", !!on));
function setTemp(key, t, warn, hot) {
  $$(`[data-temp="${key}"]`).forEach((el) => {
    el.classList.toggle("warn", t != null && t >= warn && t < hot);
    el.classList.toggle("hot", t != null && t >= hot);
  });
}

// ---------- icons (inline SVG, so they look the same everywhere – no emoji) ----------
const P = (d, fill) => `<path d="${d}"${fill ? ' fill="currentColor" stroke="none"' : ""}/>`;
const SPEAKER = P("M4 9.5h3.5L12 5.5v13l-4.5-4H4a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1z", true);
const ICONS = {
  play: P("M8 5.2v13.6a1 1 0 0 0 1.53.85l10.9-6.8a1 1 0 0 0 0-1.7L9.53 4.35A1 1 0 0 0 8 5.2z", true),
  pause: P("M7 4.5h3a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1zM14 4.5h3a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1z", true),
  prev: P("M19 6.1v11.8a1 1 0 0 1-1.55.83L9 13.2a1.45 1.45 0 0 1 0-2.4l8.45-5.53A1 1 0 0 1 19 6.1zM5 5.5a1 1 0 0 1 2 0v13a1 1 0 0 1-2 0z", true),
  next: P("M5 6.1v11.8a1 1 0 0 0 1.55.83L15 13.2a1.45 1.45 0 0 0 0-2.4L6.55 5.27A1 1 0 0 0 5 6.1zM17 5.5a1 1 0 0 1 2 0v13a1 1 0 0 1-2 0z", true),
  minus: P("M5 12h14"),
  plus: P("M12 5v14M5 12h14"),
  volDown: SPEAKER + P("M15.5 9.5a3.5 3.5 0 0 1 0 5"),
  volMute: SPEAKER + P("M15.5 9.5a3.5 3.5 0 0 1 0 5") + P("M18.5 7a7 7 0 0 1 0 10"),
  volUp: SPEAKER + P("M15.5 9.5a3.5 3.5 0 0 1 0 5") + P("M18.5 7a7 7 0 0 1 0 10") + P("M21 4.5a10.5 10.5 0 0 1 0 15"),
  volOff: SPEAKER + P("M16 9.5l5 5M21 9.5l-5 5"),
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/>' + P("M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6"),
  micOff: '<rect x="9" y="3" width="6" height="11" rx="3"/>' + P("M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6M3.5 3.5l17 17"),
  viz: P("M5 20v-6M9.5 20V8M14 20v-9M18.5 20V4"),
  fullscreen: P("M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"),
};
const svg = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
function drawIcon(el, name) {
  if (el.dataset.drawn === name) return;
  el.dataset.drawn = name;
  el.innerHTML = svg(name);  // static markup from ICONS only
}
const setIcon = (key, name) => $$(`[data-ib="${key}"]`).forEach((el) => drawIcon(el, name));
$$("[data-icon]").forEach((el) => drawIcon(el, el.dataset.icon));

// ---------- canvas ----------
function prep(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return [null, 0, 0];
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return [ctx, w, h];
}

function line(ctx, w, h, data, color, max, fill = true) {
  const pts = data.map((v) => v ?? 0);
  if (pts.length < 2) return;
  const n = 90, step = w / (n - 1), x0 = w - (pts.length - 1) * step;
  const y = (v) => h - 2 - (Math.min(v, max) / max) * (h - 4);
  ctx.beginPath();
  pts.forEach((v, i) => i ? ctx.lineTo(x0 + i * step, y(v)) : ctx.moveTo(x0, y(v)));
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.stroke();
  if (!fill) return;
  ctx.lineTo(w, h); ctx.lineTo(x0, h); ctx.closePath();
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, color + "55"); g.addColorStop(1, color + "00");
  ctx.fillStyle = g; ctx.fill();
}

// Same history drawn as vertical bars (one per sample)
function colBars(ctx, w, h, data, color, max) {
  const n = 90, slot = w / n, x0 = w - data.length * slot;
  ctx.fillStyle = color;
  data.forEach((v, i) => {
    const bh = Math.max(1, (Math.min(v ?? 0, max) / max) * (h - 2));
    ctx.fillRect(x0 + i * slot + 0.5, h - bh, Math.max(1, slot - 1.5), bh);
  });
}

function bars(ctx, w, h, data, color) {
  const max = Math.max(...data, 1), gap = 2, bw = (w - gap * (data.length - 1)) / data.length;
  data.forEach((v, i) => {
    const bh = v ? Math.max(2, (v / max) * (h - 2)) : 1;
    ctx.fillStyle = v ? color : css("--line");
    ctx.beginPath();
    ctx.roundRect(i * (bw + gap), h - bh, bw, bh, [2, 2, 0, 0]);
    ctx.fill();
  });
}

function drawCharts(s) {
  const hist = s.hw?.history || {};
  $$("canvas[data-chart]").forEach((c) => {
    const [ctx, w, h] = prep(c);
    if (!ctx) return;
    switch (c.dataset.chart) {
      case "cpu":
      case "gpu": {
        const draw = prefs[`chart.${c.dataset.chart}`] === "bars" ? colBars : line;
        return draw(ctx, w, h, hist[c.dataset.chart] || [], css(`--${c.dataset.chart}`), 100);
      }
      case "ram": return line(ctx, w, h, hist.ram || [], css("--ram"), 100);
      case "net": {
        const max = Math.max(1024, ...(hist.net_down || []), ...(hist.net_up || []));
        line(ctx, w, h, hist.net_down || [], css("--net"), max);
        return line(ctx, w, h, hist.net_up || [], css("--disk"), max, false);
      }
      case "claude": return bars(ctx, w, h, s.claude?.hourly || [], css("--claude"));
    }
  });
}

// ---------- heat maps (GitHub-style, weeks as columns, Monday on top) ----------
const DAY = 86400000;
const parseDay = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];

function quartileLevels(counts) {
  const nz = counts.filter((c) => c > 0).sort((a, b) => a - b);
  if (!nz.length) return counts.map(() => 0);
  const q = (p) => nz[Math.min(nz.length - 1, Math.floor(p * nz.length))];
  const [a, b, c] = [q(0.25), q(0.5), q(0.75)];
  return counts.map((v) => v <= 0 ? 0 : v <= a ? 1 : v <= b ? 2 : v <= c ? 3 : 4);
}

function heatmap(canvas, startIso, levels, color) {
  const [ctx, w, h] = prep(canvas);
  if (!ctx || !startIso) return;
  const start = parseDay(startIso);
  const offset = (start.getDay() + 6) % 7;            // Monday = 0
  const weeks = Math.ceil((levels.length + offset) / 7);
  const top = 13, gap = 2;
  const cell = Math.max(2, Math.min((w - gap * (weeks - 1)) / weeks, (h - top - gap * 6) / 7));
  const x0 = (w - (weeks * cell + (weeks - 1) * gap)) / 2;
  const empty = css("--line");
  const alpha = ["", "40", "73", "b0", ""];
  ctx.font = `10px system-ui, sans-serif`;
  ctx.fillStyle = css("--muted");
  let lastMonth = -1;
  levels.forEach((lvl, i) => {
    const day = new Date(start.getTime() + i * DAY + 3600000 * 3);  // +3h: DST-safe
    const k = i + offset, col = Math.floor(k / 7), row = k % 7;
    const x = x0 + col * (cell + gap), y = top + row * (cell + gap);
    if (row === 0 && day.getDate() <= 7 && day.getMonth() !== lastMonth && col < weeks - 1) {
      lastMonth = day.getMonth();
      ctx.fillStyle = css("--muted");
      ctx.fillText(MONTHS[lastMonth], x, 9);
    }
    ctx.fillStyle = lvl ? color + alpha[lvl] : empty;
    ctx.beginPath();
    ctx.roundRect(x, y, cell, cell, Math.min(3, cell / 4));
    ctx.fill();
  });
}

let heatKey = "";
function renderActivity(gh, cd) {
  if (gh?.error && !gh.days) setText("gh.user", gh.error);
  else if (gh?.user) setText("gh.user", "@" + gh.user);
  if (gh?.days) {
    setText("gh.total", String(gh.total));
    setText("gh.today", String(gh.today));
    setText("gh.streak", String(gh.streak));
  }
  if (cd) {
    setText("ch.total", fmtTok(cd.total));
    setText("ch.active", String(cd.active_days));
    setText("ch.streak", String(cd.streak));
  }
  // only redraw when the data or the size changed
  const key = JSON.stringify([gh?.updated, cd?.counts, window.innerWidth, window.innerHeight]);
  if (key === heatKey) return;
  heatKey = key;
  $$("canvas[data-heat]").forEach((c) => {
    if (c.dataset.heat === "github" && gh?.days?.length)
      heatmap(c, gh.days[0].date, gh.days.map((d) => d.level), css("--gh"));
    if (c.dataset.heat === "claude" && cd)
      heatmap(c, cd.start, quartileLevels(cd.counts), css("--claude"));
  });
}

// ---------- render ----------
let last = null;
let media = { pos: 0, len: 0, playing: false, at: 0 };

function render(s) {
  last = s;
  const hw = s.hw || {};

  const cpu = hw.cpu || {};
  setText("cpu.name", cpu.name || "");
  setText("cpu.load", round(cpu.load));
  setText("cpu.temp", round(cpu.temp)); setTemp("cpu", cpu.temp, 75, 88);
  setText("cpu.freq", round(cpu.freq));
  renderCores(cpu.cores || []);

  const gpu = hw.gpu;
  if (gpu) {
    const t = gpu.temp_hot ?? gpu.temp;
    setText("gpu.name", gpu.name || "");
    setText("gpu.load", round(gpu.load));
    setText("gpu.temp", round(t)); setTemp("gpu", t, 85, 100);
    setText("gpu.edge", round(gpu.temp));
    setText("gpu.power", round(gpu.power));
    setText("gpu.clock", round(gpu.clock));
    setText("gpu.fan", round(gpu.fan));
    setWidth("gpu.vram", gpu.vram_total ? (gpu.vram_used / gpu.vram_total) * 100 : 0);
    setText("gpu.vramtxt", gpu.vram_total ? `VRAM ${fmtBytes(gpu.vram_used)} / ${fmtBytes(gpu.vram_total)}` : "");
  }

  if (hw.ram) {
    setText("ram.txt", `${(hw.ram.used / 1e9).toFixed(1)} / ${(hw.ram.total / 1e9).toFixed(0)} GB`);
    setText("ram.used", (hw.ram.used / 1e9).toFixed(1));
    setText("ram.total", `/ ${(hw.ram.total / 1e9).toFixed(0)} GB`);
    setText("ram.pcttxt", Math.round(hw.ram.percent) + " % brugt");
    setWidth("ram.pct", hw.ram.percent);
  }
  if (hw.net) { setText("net.down", fmtRate(hw.net.down)); setText("net.up", fmtRate(hw.net.up)); }
  if (hw.disk) {
    const pct = hw.disk.used / hw.disk.total * 100;
    setText("disk.txt", `${Math.round(pct)} % · ${fmtRate(hw.disk.read + hw.disk.write)}`);
    setText("disk.usage", `${fmtBytes(hw.disk.used)} / ${fmtBytes(hw.disk.total)}`);
    setText("disk.io", fmtRate(hw.disk.read + hw.disk.write));
    setWidth("disk.pct", pct);
    setText("nvme", hw.disk.temps?.length ? hw.disk.temps.map((t) => Math.round(t) + "°").join(" ") : "–");
  }
  if (hw.uptime) setText("uptime", "oppe " + fmtDur(hw.uptime));

  renderActivity(s.github, s.claude?.daily);
  renderMedia(s.media);
  renderClaude(s.claude || {});
  renderAudio(s.audio || {});
  renderButtons(s.buttons || []);
  drawCharts(s);
}

function renderCores(cores) {
  $$("[data-cores]").forEach((box) => {
    if (box.children.length !== cores.length) box.replaceChildren(...cores.map(() => document.createElement("i")));
    box.classList.toggle("horizontal", prefs.cores === "horizontal");
    cores.forEach((c, i) => { box.children[i].style.setProperty("--v", Math.max(3, c) + "%"); });
  });
}

let artKey;
function renderMedia(m) {
  if (!m || m.error || !m.title) {
    setText("m.title", m?.error ? "Medie: " + m.error : "Intet afspilles");
    ["m.artist", "m.album", "m.player", "m.pos", "m.len"].forEach((k) => setText(k, ""));
    setWidth("m.progress", 0);
    setIcon("m.play", "play");
    if (artKey !== null) { $$("img[data-art]").forEach((i) => i.removeAttribute("src")); artKey = null; }
    media.playing = false; media.len = 0;
    return;
  }
  setText("m.player", m.player);
  setText("m.title", m.title);
  setText("m.artist", m.artist || "");
  setText("m.album", m.album || "");
  setIcon("m.play", m.status === "Playing" ? "pause" : "play");
  if (m.art_key !== artKey) {
    artKey = m.art_key;
    $$("img[data-art]").forEach((img) => {
      if (m.art) img.src = "/api/art?k=" + encodeURIComponent(m.art_key || "");
      else img.removeAttribute("src");
    });
  }
  media = { pos: m.position, len: m.length, playing: m.status === "Playing", at: performance.now() };
  tickMedia();
}

function tickMedia() {
  if (!media.len) return;
  const pos = Math.min(media.len, media.pos + (media.playing ? (performance.now() - media.at) / 1000 : 0));
  setText("m.pos", fmtTime(pos));
  setText("m.len", fmtTime(media.len));
  setWidth("m.progress", (pos / media.len) * 100);
}

function renderClaude(c) {
  if (!c.available) { setText("c.block", "–"); setText("c.reset", c.error || "ingen data"); return; }
  const sum = (b) => b ? b.input + b.output + b.cache_write : null;
  setText("c.block", fmtTok(sum(c.last5h)));
  setText("c.today", fmtTok(sum(c.today)));
  setText("c.week", fmtTok(sum(c.last7d)));
  setText("c.out", fmtTok(c.today?.output));
  setText("c.msgs", (c.today?.messages ?? 0) + " svar");
  setText("c.b.in", fmtTok(c.last5h?.input));
  setText("c.b.out", fmtTok(c.last5h?.output));
  setText("c.b.cw", fmtTok(c.last5h?.cache_write));
  setText("c.b.cr", fmtTok(c.last5h?.cache_read));
  setText("c.reset", c.block_reset_in ? "↻ " + fmtDur(c.block_reset_in) : "intet aktivt vindue");
  setText("c.resetlong", c.block_reset_in ? "Vinduet nulstilles om " + fmtDur(c.block_reset_in) : "Intet aktivt vindue");

  const models = Object.entries(c.models || {});
  const total = models.reduce((a, [, v]) => a + v, 0) || 1;
  const key = JSON.stringify(models);
  $$("[data-models]").forEach((box) => {
    if (box.dataset.key === key) return;
    box.dataset.key = key;
    box.replaceChildren(...models.slice(0, 4).map(([name, v]) => {
      const row = document.createElement("div");
      const n = document.createElement("span"); n.textContent = name;
      const t = document.createElement("span"); t.textContent = fmtTok(v);
      const bar = document.createElement("div"); bar.className = "bar";
      const fill = document.createElement("i"); fill.style.width = (v / total) * 100 + "%";
      bar.append(fill); row.append(n, t, bar);
      return row;
    }));
  });
}

function renderAudio(a) {
  const out = a.output || {}, mic = a.mic || {};
  setText("vol.txt", out.muted ? "Lyd fra" : (out.volume ?? "–") + " %");
  setIcon("vol.icon", out.muted ? "volOff" : "volMute");
  setIcon("mic.icon", mic.muted ? "micOff" : "mic");
  setWidth("vol.pct", out.volume);
  setOn("vol.muted", out.muted);
  setText("mic.txt", mic.muted ? "Mikrofon fra" : "Mikrofon");
  setOn("mic.muted", mic.muted);
}

let buttonsKey = "";
function renderButtons(list) {
  const key = JSON.stringify(list);
  if (key === buttonsKey) return;
  buttonsKey = key;
  const box = $("[data-tiles]");
  $$("[data-custom]", box).forEach((el) => el.remove());
  list.forEach((b) => {
    const el = document.createElement("button");
    el.className = "tile"; el.dataset.action = b.id; el.dataset.custom = "";
    const icon = document.createElement("b"); icon.textContent = b.icon;
    el.append(icon, b.label);
    box.append(el);
  });
}

// ---------- per-device preferences ----------
const prefs = (() => { try { return JSON.parse(localStorage.getItem("phonedeck.prefs") || "{}"); } catch { return {}; } })();
const savePrefs = () => { try { localStorage.setItem("phonedeck.prefs", JSON.stringify(prefs)); } catch { /* ignore */ } };

// Tap a CPU/GPU graph: line <-> vertical bars. Tap the core bars: vertical <-> horizontal.
document.addEventListener("click", (e) => {
  const chart = e.target.closest('canvas[data-chart="cpu"], canvas[data-chart="gpu"]');
  if (chart) {
    const k = `chart.${chart.dataset.chart}`;
    prefs[k] = prefs[k] === "bars" ? "line" : "bars";
  } else if (e.target.closest("[data-cores]")) {
    prefs.cores = prefs.cores === "horizontal" ? "vertical" : "horizontal";
  } else return;
  savePrefs();
  navigator.vibrate?.(8);
  if (last) render(last);
});

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

// Fullscreen on tap (clock or the tile)
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-fullscreen]")) return;
  if (!document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
  else document.exitFullscreen?.();
  keepAwake();
});

// Keep the screen on for as long as the dashboard is visible. The browser drops
// the lock whenever the page is hidden, so grab it again every time it comes back.
let wakeLock = null;
async function keepAwake() {
  if (!("wakeLock" in navigator) || document.visibilityState !== "visible" || (wakeLock && !wakeLock.released)) return;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
    wakeLock.addEventListener("release", () => setTimeout(keepAwake, 1000));
  } catch { /* not allowed right now – retried on next tap / visibility change */ }
}
keepAwake();
document.addEventListener("visibilitychange", keepAwake);
document.addEventListener("pointerdown", keepAwake, { passive: true });
setInterval(keepAwake, 30_000);

// ---------- pages ----------
const pager = $("#pager");
const pages = $$(".page");
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
let current = 0;

$("#dots").replaceChildren(...pages.map((p, i) => {
  const b = document.createElement("button");
  b.setAttribute("aria-label", p.dataset.title);
  b.append(document.createElement("i"));
  b.addEventListener("click", () => goTo(i));
  return b;
}));

function goTo(i, smooth = true) {
  pager.scrollTo({ left: i * pager.clientWidth, behavior: smooth ? "smooth" : "instant" });
}
function updateDots() {
  const i = Math.round(pager.scrollLeft / Math.max(1, pager.clientWidth));
  if (i === current && $("#dots .on")) return;
  current = i;
  $$("#dots button").forEach((b, j) => b.classList.toggle("on", j === i));
  store.set("phonedeck.page", String(i));
}
pager.addEventListener("scroll", updateDots, { passive: true });
window.addEventListener("resize", () => { goTo(current, false); if (last) render(last); });

const saved = Number(store.get("phonedeck.page"));
requestAnimationFrame(() => { goTo(Number.isInteger(saved) && saved < pages.length ? saved : 0, false); updateDots(); });

// ---------- clock + burn-in protection ----------
function tickClock() {
  const d = new Date();
  setText("time", d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }));
  setText("date", d.toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" }));
  tickMedia();
}
setInterval(tickClock, 1000); tickClock();

// Nudge everything a few pixels every minute so static UI doesn't burn into the AMOLED
setInterval(() => {
  const r = () => Math.round(Math.random() * 6 - 3);
  pager.style.transform = `translate(${r()}px, ${r()}px)`;
}, 60_000);

// Dim at night (23–07)
const dim = () => { const h = new Date().getHours(); document.body.classList.toggle("dim", h >= 23 || h < 7); };
setInterval(dim, 30_000); dim();

// ---------- music visualizer ----------
// Only listens while it is switched on AND the music page is on screen.
let vizSource = null;
const vizCanvas = $("canvas[data-viz]");
const musicIndex = pages.findIndex((p) => p.id === "p-music");

function drawViz(levels) {
  const [ctx, w, h] = prep(vizCanvas);
  if (!ctx) return;
  const n = levels.length, gap = 4, bw = (w - gap * (n - 1)) / n;
  const g = ctx.createLinearGradient(0, h, 0, 0);
  g.addColorStop(0, css("--media"));
  g.addColorStop(1, css("--media") + "10");
  ctx.fillStyle = g;
  levels.forEach((v, i) => {
    const bh = Math.max(2, (v / 100) * h * 0.7);
    ctx.beginPath();
    ctx.roundRect(i * (bw + gap), h - bh, bw, bh, [Math.min(4, bw / 2), Math.min(4, bw / 2), 0, 0]);
    ctx.fill();
  });
}

function updateViz() {
  const want = prefs.viz && current === musicIndex && document.visibilityState === "visible";
  $$("[data-viz-toggle]").forEach((b) => b.classList.toggle("on", !!prefs.viz));
  vizCanvas.hidden = !prefs.viz;
  if (want && !vizSource) {
    vizPing();  // the PC only listens while this page keeps pinging
    vizSource = new EventSource("/api/spectrum");
    vizSource.onmessage = (e) => drawViz(JSON.parse(e.data));
  } else if (!want && vizSource) {
    vizSource.close();
    vizSource = null;
    drawViz(new Array(36).fill(0));
  }
}
const vizPing = () => fetch("/api/viz/keepalive", { method: "POST" }).catch(() => {});
setInterval(() => { if (vizSource) vizPing(); }, 1500);
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-viz-toggle]")) return;
  prefs.viz = !prefs.viz;
  savePrefs();
  updateViz();
});
document.addEventListener("visibilitychange", updateViz);
pager.addEventListener("scroll", () => requestAnimationFrame(updateViz), { passive: true });
setTimeout(updateViz, 300);

// ---------- live data ----------
const es = new EventSource("/api/stream");
es.onmessage = (e) => { $("#offline").hidden = true; render(JSON.parse(e.data)); };
es.onerror = () => { $("#offline").hidden = false; };
