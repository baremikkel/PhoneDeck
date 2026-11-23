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

function line(ctx, w, h, data, color, max, fill = true, width = 2) {
  const pts = data.map((v) => v ?? 0);
  if (pts.length < 2) return;
  const n = 90, step = w / (n - 1), x0 = w - (pts.length - 1) * step;
  const y = (v) => h - 2 - (Math.min(v, max) / max) * (h - 4);
  ctx.beginPath();
  pts.forEach((v, i) => i ? ctx.lineTo(x0 + i * step, y(v)) : ctx.moveTo(x0, y(v)));
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineJoin = "round"; ctx.stroke();
  if (!fill) return;
  ctx.lineTo(w, h); ctx.lineTo(x0, h); ctx.closePath();
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, color + "55"); g.addColorStop(1, color + "00");
  ctx.fillStyle = g; ctx.fill();
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
        // load (filled, 0–100 %) + temperature (thin warm line, 20–100 °C)
        const k = c.dataset.chart;
        line(ctx, w, h, hist[k] || [], css(`--${k}`), 100);
        const temps = (hist[`${k}_temp`] || []).map((t) => t == null ? null : Math.max(0, t - 20));
        line(ctx, w, h, temps, css("--temp"), 80, false, 1.5);
        return;
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

// ---------- Claude: donut with what is left of your own limits ----------
function renderDonut(c, budget) {
  const used5 = c.block_used || 0;
  const usedW = c.last7d ? c.last7d.input + c.last7d.output + c.last7d.cache_write : 0;
  const b5 = budget.budget_5h, bw = budget.budget_week;
  if (b5) {
    const left = Math.max(0, b5 - used5);
    setText("c.left", fmtTok(left));
    setText("c.leftlbl", `tilbage · ${Math.round((left / b5) * 100)} %`);
    setText("c.blockof", `/ ${fmtTok(b5)}`);
  } else {
    setText("c.left", "–");
    setText("c.leftlbl", "tryk: sæt grænse");
    setText("c.blockof", "tokens");
  }
  $$("[data-week-legend]").forEach((el) => { el.hidden = !bw; });
  if (bw) setText("c.weektxt", `uge ${Math.round(Math.max(0, 1 - usedW / bw) * 100)} % tilbage`);
  $$("canvas[data-donut]").forEach((cv) => {
    const [ctx, w, h] = prep(cv);
    if (!ctx) return;
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 2;
    const ring = (r, width, frac, color) => {
      ctx.lineCap = "round";
      ctx.lineWidth = width;
      ctx.strokeStyle = css("--line");
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      if (frac == null) return;
      // remaining share, drawn clockwise from 12 o'clock
      const f = Math.max(0, Math.min(1, frac));
      if (f <= 0) return;
      ctx.strokeStyle = color;
      ctx.beginPath(); ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + f * Math.PI * 2); ctx.stroke();
    };
    const t = Math.max(6, R * 0.16);
    const remaining5 = b5 ? 1 - used5 / b5 : null;
    const colour5 = remaining5 != null && remaining5 < 0.15 ? css("--hot")
      : remaining5 != null && remaining5 < 0.35 ? css("--warn") : css("--claude");
    ring(R - t / 2, t, remaining5, colour5);
    if (bw) ring(R - t * 1.9, t * 0.55, 1 - usedW / bw, css("--ram"));
  });
}
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-donut-wrap]") || last?.claude_budget?.budget_5h) return;
  api("/api/action", { action: "open.settings" }).catch(() => {});
});

// ---------- Spotify: next song + queue ----------
let queueKey = "";
function renderSpotify(sp) {
  const img = $("img[data-next-art]");
  if (!sp || !sp.connected) {
    setText("q.lbl", "Næste sang");
    setText("q.next", sp?.configured ? "Tryk for at forbinde Spotify på computeren"
      : "Tryk for at sætte Spotify-køen op på computeren");
    img.hidden = true;
    return;
  }
  const n = sp.next;
  setText("q.lbl", `Næste · ${sp.queue?.length || 0} i kø`);
  setText("q.next", n ? `${n.title} – ${n.artist}` : "Køen er tom");
  if (n?.art) { if (img.getAttribute("src") !== n.art) img.src = n.art; img.hidden = false; } else img.hidden = true;
  setText("q.count", `${sp.queue?.length || 0} sange`);
  const key = JSON.stringify(sp.queue);
  if (key === queueKey) return;
  queueKey = key;
  $("[data-queue]").replaceChildren(...(sp.queue || []).map((t, i) => {
    const li = document.createElement("li");
    const num = Object.assign(document.createElement("small"), { textContent: String(i + 1) });
    const art = t.art ? Object.assign(document.createElement("img"), { src: t.art, alt: "", loading: "lazy" })
      : Object.assign(document.createElement("span"), { className: "noimg" });
    const txt = document.createElement("div");
    txt.className = "t";
    txt.append(Object.assign(document.createElement("b"), { textContent: t.title }),
      Object.assign(document.createElement("span"), { textContent: t.artist }));
    const dur = Object.assign(document.createElement("small"), { textContent: fmtTime(t.duration) });
    li.append(num, art, txt, dur);
    return li;
  }));
}
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-queue-open]")) {
    if (!last?.spotify?.connected) { api("/api/action", { action: "open.settings" }).catch(() => {}); return; }
    $("#queue").hidden = false;
  } else if (e.target.closest("[data-queue-close]") || e.target.id === "queue") {
    $("#queue").hidden = true;
  }
});

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
  renderDonut(s.claude || {}, s.claude_budget || {});
  renderSpotify(s.spotify);
  renderAudio(s.audio || {});
  renderButtons(s.buttons || []);
  drawCharts(s);
}

function renderCores(cores) {
  $$("[data-cores]").forEach((box) => {
    if (box.children.length !== cores.length) box.replaceChildren(...cores.map(() => document.createElement("i")));
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
  setText("c.block", fmtTok(c.block_used ?? sum(c.last5h)));
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

// ---------- Stream Deck (buttons come from the PC; edit them at /editor) ----------
// Built-ins with live state get bindings so they show volume, mute, play/pause …
const LIVE = {
  "volume.mute": { icon: "vol.icon", label: "vol.txt", on: "vol.muted" },
  "mic.mute": { icon: "mic.icon", label: "mic.txt", on: "mic.muted" },
  "media.playpause": { icon: "m.play" },
};

function makeIcon(icon) {
  if (icon?.kind === "app") {
    const img = document.createElement("img");
    img.className = "appicon"; img.alt = ""; img.loading = "lazy";
    img.src = "/api/appicon?id=" + encodeURIComponent(icon.value);
    return img;
  }
  if (icon?.kind === "builtin") {
    const i = document.createElement("i");
    i.className = "ic";
    drawIcon(i, icon.value);
    return i;
  }
  const b = document.createElement("b");
  b.textContent = icon?.value || "⭐";
  return b;
}

let buttonsKey = "";
function renderButtons(list) {
  const key = JSON.stringify(list);
  if (key === buttonsKey) return;
  buttonsKey = key;
  const tiles = list.map((b) => {
    const el = document.createElement("button");
    el.className = "tile";
    if (b.builtin === "ui.fullscreen") el.dataset.fullscreen = "";
    else el.dataset.button = b.id;
    const icon = makeIcon(b.icon);
    const label = document.createElement("span");
    label.textContent = b.label;
    const live = LIVE[b.builtin];
    if (live) {
      if (live.icon && icon.classList.contains("ic")) { icon.dataset.ib = live.icon; delete icon.dataset.drawn; }
      if (live.label) label.dataset.b = live.label;
      if (live.on) el.dataset.on = live.on;
    }
    el.append(icon, label);
    return el;
  });
  const add = document.createElement("button");
  add.className = "tile add"; add.dataset.action = "open.editor";
  add.append(makeIcon({ kind: "builtin", value: "plus" }), "Redigér knapper");
  $("[data-tiles]").replaceChildren(...tiles, add);
  if (last) { renderAudio(last.audio || {}); renderMedia(last.media); }
}

// ---------- per-device preferences ----------
const prefs = (() => { try { return JSON.parse(localStorage.getItem("phonedeck.prefs") || "{}"); } catch { return {}; } })();
const savePrefs = () => { try { localStorage.setItem("phonedeck.prefs", JSON.stringify(prefs)); } catch { /* ignore */ } };

// CPU and GPU cards: side by side or on top of each other (button in the CPU header)
const applyLayout = () => {
  document.body.classList.toggle("stack", prefs.layout === "stack");
  $$("[data-layout-toggle]").forEach((b) => drawIcon(b.querySelector(".ic"), prefs.layout === "stack" ? "sideBySide" : "stacked"));
};
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-layout-toggle]")) return;
  prefs.layout = prefs.layout === "stack" ? "side" : "stack";
  savePrefs();
  navigator.vibrate?.(8);
  applyLayout();
  heatKey = "";
  if (last) render(last);
});
applyLayout();

// ---------- actions ----------
const api = (path, body) => fetch(path, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-PhoneDeck": "1" },
  body: JSON.stringify(body || {}),
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-action], [data-button]");
  if (!btn) return;
  navigator.vibrate?.(12);
  btn.classList.add("pressed");
  setTimeout(() => btn.classList.remove("pressed"), 180);
  try {
    await api("/api/action", btn.dataset.button ? { button: btn.dataset.button } : { action: btn.dataset.action });
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
const vizPing = () => api("/api/viz/keepalive").catch(() => {});
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
