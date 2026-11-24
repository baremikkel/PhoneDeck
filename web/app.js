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
  // only the core charts – extensions draw their own canvases
  $$('canvas[data-chart="cpu"], canvas[data-chart="gpu"], canvas[data-chart="ram"], canvas[data-chart="net"]').forEach((c) => {
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

// GitHub-style calendar: weeks as columns (Monday on top), newest week on the right.
// Fills the width: shows as many recent weeks as fit at a readable cell size.
// opts: {palette: [5 colours] | null, counts: [...], unit: "bidrag"} – tap a day to see it.
const GH_PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"];
const DAYS = ["Man", "", "Ons", "", "Fre", "", ""];
function heatmap(canvas, startIso, levels, color, opts = {}) {
  const [ctx, w, h] = prep(canvas);
  if (!ctx || !startIso || !levels.length) return;
  const start = parseDay(startIso);
  const offset = (start.getDay() + 6) % 7;            // Monday = 0
  const totalWeeks = Math.ceil((levels.length + offset) / 7);
  const gap = Math.max(2, Math.min(3, h / 70));
  const MIN_CELL = 8;
  // the whole year if it fits at a readable size (like GitHub) – otherwise the latest weeks
  const fitH = (h - 14 - gap * 6) / 7;
  let labelW = Math.min(fitH, 99) >= 9 ? 26 : 0;
  let cell = Math.min(fitH, (w - labelW - gap * (totalWeeks - 1)) / totalWeeks);
  let weeks = totalWeeks;
  if (cell < MIN_CELL) {
    cell = Math.max(3, Math.min(fitH, MIN_CELL));
    weeks = Math.max(1, Math.min(totalWeeks, Math.floor((w - labelW + gap) / (cell + gap))));
  }
  if (cell < 9) labelW = 0;
  const firstWeek = totalWeeks - weeks;
  const gridW = weeks * cell + (weeks - 1) * gap;
  const x0 = labelW + Math.max(0, (w - labelW - gridW) / 2);
  const top = 14 + Math.max(0, (h - 14 - (7 * cell + 6 * gap)) / 2);  // centred vertically
  const palette = opts.palette || [css("--line"), color + "40", color + "73", color + "b0", color];
  ctx.font = `${Math.min(11, Math.max(9, cell * 0.8))}px system-ui, sans-serif`;
  ctx.textBaseline = "middle";
  ctx.fillStyle = css("--muted");
  if (labelW) DAYS.forEach((d, row) => { if (d) ctx.fillText(d, 0, top + row * (cell + gap) + cell / 2); });
  const todayIdx = Math.round((new Date().setHours(12) - start.setHours(12)) / DAY);
  start.setHours(0);
  let lastMonth = -1;
  const hits = [];
  levels.forEach((lvl, i) => {
    const k = i + offset, col = Math.floor(k / 7) - firstWeek, row = k % 7;
    if (col < 0) return;
    const x = x0 + col * (cell + gap), y = top + row * (cell + gap);
    const day = new Date(start.getTime() + i * DAY + 3600000 * 3);  // +3h: DST-safe
    if (row === 0 && day.getDate() <= 7 && day.getMonth() !== lastMonth && col < weeks - 1) {
      lastMonth = day.getMonth();
      ctx.fillStyle = css("--muted");
      ctx.fillText(MONTHS[lastMonth], x, top - 8);
    }
    ctx.fillStyle = palette[Math.max(0, Math.min(4, lvl))];
    ctx.beginPath();
    ctx.roundRect(x, y, cell, cell, Math.min(3, cell / 4));
    ctx.fill();
    if (i === todayIdx) {  // today
      ctx.strokeStyle = css("--text");
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    hits.push([x, y, day, opts.counts?.[i]]);
  });
  canvas._heat = { hits, cell, unit: opts.unit };
}
// tap a day -> "12. nov.: 5 bidrag"
document.addEventListener("click", (e) => {
  const c = e.target.closest("canvas.heatmap");
  if (!c?._heat) return;
  const r = c.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
  const hit = c._heat.hits.find(([x, y]) => px >= x - 1 && px <= x + c._heat.cell + 1 && py >= y - 1 && py <= y + c._heat.cell + 1);
  if (!hit) return;
  const [, , day, count] = hit;
  const label = day.toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" });
  toast(count == null ? label : `${label}: ${typeof count === "number" && count >= 1000 ? fmtTok(count) : count} ${c._heat.unit || ""}`.trim());
});

// ---------- preview inside the editor (/?preview) ----------
// The editor embeds the dashboard and posts its unsaved drafts here, so you see the
// result before pressing Gem. Only messages from our own origin are accepted.
const PREVIEW = new URLSearchParams(location.search).has("preview");
let previewDraft = {};
if (PREVIEW) {
  document.documentElement.classList.add("preview");
  window.addEventListener("message", (e) => {
    if (e.origin !== location.origin || e.data?.type !== "phonedeck-preview") return;
    const d = e.data;
    previewDraft = { home: d.home, custom: d.custom, buttons: d.buttons };
    if (Array.isArray(d.folder)) folderPath = d.folder;
    uiKey = ""; homeKey = ""; customKey = ""; buttonsKey = "";
    if (last) render(last);
    requestAnimationFrame(() => {
      const i = pages.findIndex((p) => p.id === d.page);
      if (i >= 0) { goTo(i, false); updateDots(); }
    });
  });
}

// ---------- extensions (phone side) ----------
// Every extension folder may ship page.html / page.js / page.css. page.js calls
// PhoneDeck.register(id, {render(extState, fullState), tick(), page(pageId), widgets: {type: html}}).
let layoutGen = 0;  // bumped when the layout changes, so canvases redraw
const PhoneDeck = {
  renderers: new Map(),
  widgets: {},
  register(id, r) {
    this.renderers.set(id, r);
    Object.assign(this.widgets, r.widgets || {});
  },
  each(hook, ...args) {
    for (const [id, r] of this.renderers) {
      try { r[hook]?.(...args); } catch (e) { console.error(`[${id}]`, e); }
    }
  },
  render(s) {
    for (const [id, r] of this.renderers) {
      try { r.render?.(s.ext?.[id], s); } catch (e) { console.error(`[${id}]`, e); }
    }
  },
  action: (ext, name, body) => api(`/api/ext/${ext}/action/${name}`, body).then((r) => r.json()),
  currentPage: () => pages[current]?.id,
  // the editor reads this through its preview to offer each element's display options
  widgetHTML: (type) => WIDGET_HTML[type] || PhoneDeck.widgets[type] || "",
};
window.PhoneDeck = PhoneDeck;

let extKey = null;
async function loadExtensions() {
  let list = [];
  try { list = await (await fetch("/api/extensions", { headers: { "X-PhoneDeck": "1" } })).json(); } catch { /* offline */ }
  extKey = JSON.stringify(list.map((e) => [e.id, e.rev]));
  // 1) all pages first, so every script finds the elements it needs
  for (const e of list) {
    if (e.has_style) document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href: `/ext/${e.id}/page.css?v=${e.rev}` }));
    if (!e.page) continue;
    const sec = document.createElement("section");
    sec.className = "page";
    sec.id = "p-" + e.id;
    sec.dataset.title = e.page.title;
    sec.dataset.category = e.category;
    sec.innerHTML = await (await fetch(`/ext/${e.id}/page.html?v=${e.rev}`)).text();
    // every card marked data-widget can also be placed on the home page / your own pages
    sec.querySelectorAll("[data-widget]").forEach((card) => {
      PhoneDeck.widgets[`${e.id}.${card.dataset.widget}`] = card.outerHTML;
    });
    pager.insertBefore(sec, $("#p-buttons"));
  }
  // 2) then the scripts, in order
  for (const e of list.filter((x) => x.has_script)) {
    await new Promise((done) => {
      const sc = Object.assign(document.createElement("script"), { src: `/ext/${e.id}/page.js?v=${e.rev}` });
      sc.onload = sc.onerror = done;
      document.body.append(sc);
    });
  }
  $$("[data-icon]").forEach((el) => drawIcon(el, el.dataset.icon));
  pages = $$(".page").filter((p) => !p.hidden);
  buildDots();
}
// a folder was added/removed/changed on the PC -> load the new set of extensions
function checkExtensions(list) {
  if (!list || extKey === null) return;
  if (JSON.stringify(list.map((e) => [e.id, e.rev])) !== extKey) location.reload();
}
// generic buttons for extension actions: data-ext="<id>:<action>"
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ext]");
  if (!b) return;
  const [ext, name] = b.dataset.ext.split(":");
  navigator.vibrate?.(10);
  PhoneDeck.action(ext, name).then((r) => { if (r?.error) toast(r.error); }).catch(() => {});
});

// ---------- render ----------
let last = null;

function render(s) {
  last = s;
  applyUi(s.ui);
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

  checkExtensions(s.extensions);
  renderAudio(s.audio || {});
  PhoneDeck.render(s);
  renderButtons(s.buttons || []);
  drawCharts(s);
}

function renderCores(cores) {
  $$("[data-cores]").forEach((box) => {
    if (box.children.length !== cores.length) box.replaceChildren(...cores.map(() => document.createElement("i")));
    cores.forEach((c, i) => { box.children[i].style.setProperty("--v", Math.max(3, c) + "%"); });
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
    img.onerror = () => img.replaceWith(Object.assign(document.createElement("b"), { textContent: "📦" }));  // no icon (e.g. Windows)
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

function makeTile(b) {
    const el = document.createElement("button");
    el.className = "tile" + (b.running ? " running" : "");
    if (b.color) el.style.setProperty("--btn", b.color);
    if (b.type === "folder") {
      el.dataset.folder = b.id;  // opened on the phone, nothing runs on the PC
      el.classList.add("folder");
      el.dataset.count = (b.buttons || []).length;
    } else if (b.type === "page") {
      el.dataset.goto = b.page;  // switches page on the phone, nothing runs on the PC
    } else if (b.builtin === "ui.fullscreen") el.dataset.fullscreen = "";
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
    // display options from the editor: hide name / icon / frame, or invisible (still pressable)
    for (const h of b.hide || []) el.classList.add("hide-" + h);
    if (b.invisible) { el.classList.add("invisible"); el.setAttribute("aria-label", b.label); }
    return el;
}

// ---------- folders: the Knapper page shows one folder at a time ----------
let folderPath = [];  // ids of the opened folders, outermost first
const findButton = (list, id) => {
  for (const b of list || []) {
    if (b.id === id) return b;
    const inner = b.type === "folder" && findButton(b.buttons, id);
    if (inner) return inner;
  }
  return null;
};

let buttonsKey = "";
function renderButtons(list) {
  if (PREVIEW && previewDraft.buttons) list = previewDraft.buttons;
  const key = JSON.stringify([list, folderPath]);
  if (key === buttonsKey) return;
  buttonsKey = key;
  // walk down the opened folders (a folder that was deleted on the PC closes itself)
  let level = list, trail = [];
  for (const id of folderPath) {
    const f = level.find((b) => b.id === id && b.type === "folder");
    if (!f) break;
    trail.push(f);
    level = f.buttons || [];
  }
  folderPath = trail.map((f) => f.id);
  const tiles = level.map(makeTile);
  if (trail.length) {
    const back = document.createElement("button");
    back.className = "tile back";
    back.dataset.folderBack = "";
    back.append(makeIcon({ kind: "builtin", value: "prev" }),
      Object.assign(document.createElement("span"), { textContent: trail.length > 1 ? trail[trail.length - 2].label : "Tilbage" }));
    tiles.unshift(back);
  }
  const add = document.createElement("button");
  add.className = "tile add"; add.dataset.action = "open.editor";
  add.append(makeIcon({ kind: "builtin", value: "plus" }), "Redigér knapper");
  setText("deck.path", trail.map((f) => f.label).join(" › "));
  $("[data-tiles]").replaceChildren(...tiles, ...(trail.length ? [] : [add]));
  fillHomeButtons(list);
  if (last) { renderAudio(last.audio || {}); PhoneDeck.render(last); }
}

// ---------- customisable home page: a fixed grid of widgets (set up at /editor#home) ----------
// Static markup only – every value is filled in through the same data-b bindings as elsewhere.
const WIDGET_HTML = {
  menu: `<button class="tile home-menu" data-menu-open><i class="ic" data-icon="gear"></i><span>Menu</span></button>`,
  cpu: `<div class="card" style="--accent: var(--cpu)">
    <header><span class="label">CPU</span><span class="sub grow right" data-b="cpu.name"></span></header>
    <div class="row"><div class="big"><span data-b="cpu.load">–</span><small>%</small></div>
      <div class="facts" data-opt="facts" data-opt-name="Temperatur og takt"><div><span data-b="cpu.temp" data-temp="cpu">–</span><small>°C</small></div><div><span data-b="cpu.freq">–</span><small>MHz</small></div></div></div>
    <canvas class="spark" data-chart="cpu" data-opt="graph" data-opt-name="Graf"></canvas></div>`,
  gpu: `<div class="card" style="--accent: var(--gpu)">
    <header><span class="label">GPU</span><span class="sub grow right" data-b="gpu.name"></span></header>
    <div class="row"><div class="big"><span data-b="gpu.load">–</span><small>%</small></div>
      <div class="facts" data-opt="facts" data-opt-name="Temperatur og strøm"><div><span data-b="gpu.temp" data-temp="gpu">–</span><small>°C</small></div><div><span data-b="gpu.power">–</span><small>W</small></div></div></div>
    <div class="bar" data-opt="bar" data-opt-name="VRAM-bjælke"><i data-w="gpu.vram"></i></div>
    <canvas class="spark" data-chart="gpu" data-opt="graph" data-opt-name="Graf"></canvas></div>`,
  ram: `<div class="card" style="--accent: var(--ram)">
    <header><span class="label">RAM</span><span class="sub" data-b="ram.pcttxt"></span></header>
    <div class="big"><span data-b="ram.used">–</span><small data-b="ram.total"></small></div>
    <div class="bar" data-opt="bar" data-opt-name="Bjælke"><i data-w="ram.pct"></i></div><canvas class="spark" data-chart="ram" data-opt="graph" data-opt-name="Graf"></canvas></div>`,
  net: `<div class="card" style="--accent: var(--net)">
    <header><span class="label">Netværk</span></header>
    <div class="kv"><div><small>↓ Ned</small><span data-b="net.down">–</span></div><div><small>↑ Op</small><span data-b="net.up">–</span></div></div>
    <canvas class="spark" data-chart="net" data-opt="graph" data-opt-name="Graf"></canvas></div>`,
  disk: `<div class="card" style="--accent: var(--disk)">
    <header><span class="label">Disk</span><span class="sub" data-b="nvme"></span></header>
    <div class="kv"><div><small>Brugt</small><span data-b="disk.usage">–</span></div><div data-opt="io" data-opt-name="I/O"><small>I/O</small><span data-b="disk.io">–</span></div></div>
    <div class="bar" data-opt="bar" data-opt-name="Bjælke"><i data-w="disk.pct"></i></div></div>`,
  sys: `<div class="card strip">
    <div data-opt="ram" data-opt-name="RAM"><small>RAM</small><span data-b="ram.txt">–</span></div>
    <div data-opt="down" data-opt-name="Net ned"><small>↓ Net</small><span data-b="net.down">–</span></div>
    <div data-opt="up" data-opt-name="Net op"><small>↑ Net</small><span data-b="net.up">–</span></div>
    <div class="hide-narrow" data-opt="disk" data-opt-name="Disk"><small>Disk</small><span data-b="disk.txt">–</span></div>
    <div class="clock" data-fullscreen data-opt="clock" data-opt-name="Ur"><span data-b="time">–</span><small data-b="date"></small></div></div>`,
  clock: `<div class="card clock-card" data-fullscreen><b data-b="time">–</b><span data-b="datelong" data-opt="date" data-opt-name="Dato"></span></div>`,
};

// display options chosen in the editor: "header", "frame", "label"/"icon" (buttons),
// or any part an element marks with data-opt="key" (e.g. the graph or the cover)
function applyOptions(el, it) {
  const hide = it.hide || [];
  if (el.classList.contains("home-btn")) {  // buttons: applied to the tile (see fillHomeButtons / goto)
    if (hide.length) el.dataset.hide = hide.join(" ");
    if (it.invisible) el.dataset.invisible = "1";
    const tile = el.querySelector(".tile");
    if (tile) { hide.forEach((h) => tile.classList.add("hide-" + h)); if (it.invisible) tile.classList.add("invisible"); }
    return;
  }
  if (el.classList.contains("tile")) {  // the Menu button
    hide.forEach((h) => el.classList.add("hide-" + h));
    if (it.invisible) el.classList.add("invisible");
    return;
  }
  for (const h of hide) {
    if (h === "header" || h === "frame") el.classList.add("hide-" + h);
    else el.querySelectorAll(`[data-opt~="${h}"]`).forEach((p) => p.classList.add("opt-hidden"));
  }
}

// one grid builder for the home page and your own pages
function buildGrid(page, layout) {
  page.classList.add("grid-page");
  page.style.gridTemplateColumns = `repeat(${layout.cols}, 1fr)`;
  page.style.gridTemplateRows = `repeat(${layout.rows}, 1fr)`;
  page.replaceChildren(...layout.items.map((it) => {
    let el;
    if (it.type === "button") {
      el = document.createElement("div");
      el.className = "home-btn";
      el.dataset.homeButton = it.button;
    } else if (it.type === "goto") {
      // "Gå til side": label and icon are filled in by fillGotoTiles() once the pages exist
      el = document.createElement("div");
      el.className = "home-btn";
      const b = Object.assign(document.createElement("button"), { className: "tile goto" });
      b.dataset.goto = it.page;
      b.append(Object.assign(document.createElement("i"), { className: "ic" }), document.createElement("span"));
      el.append(b);
    } else {
      const html = WIDGET_HTML[it.type] || PhoneDeck.widgets[it.type];
      if (!html) return null;  // element from an extension that isn't installed
      const t = document.createElement("template");
      t.innerHTML = html;  // static strings from core / installed extensions
      el = t.content.firstElementChild;
      el.removeAttribute("data-widget");
    }
    el.classList.add("w-" + it.type.replace(".", "_"));
    applyOptions(el, it);
    if (it.w * it.h <= 2) el.classList.add("small");
    if (it.w === 1) el.classList.add("narrow");
    el.style.gridColumn = `${it.x + 1} / span ${it.w}`;
    el.style.gridRow = `${it.y + 1} / span ${it.h}`;
    return el;
  }).filter(Boolean));
  $$("[data-icon]", page).forEach((el) => drawIcon(el, el.dataset.icon));
  fillGotoTiles();
  layoutGen++;
  PhoneDeck.each("rebuilt");  // a grid was rebuilt – extensions refresh their elements
  if (last) fillHomeButtons(last.buttons || []);
}

let homeKey = "";
function renderHome(home) {
  if (!home) return;
  const key = JSON.stringify(home);
  if (key === homeKey) return;
  homeKey = key;
  buildGrid($("#p-overview"), home);
}

// your own pages (made in the editor) – one <section> each, id "p-custom-<id>"
let customKey = "";
function renderCustomPages(list) {
  const key = JSON.stringify(list);
  if (key === customKey) return;
  customKey = key;
  const ids = new Set(list.map((cp) => "p-custom-" + cp.id));
  $$(".page[data-custom]").forEach((sec) => { if (!ids.has(sec.id)) sec.remove(); });
  for (const cp of list) {
    let sec = $("#p-custom-" + cp.id);
    if (!sec) {
      sec = document.createElement("section");
      sec.className = "page";
      sec.id = "p-custom-" + cp.id;
      sec.dataset.custom = "";
      pager.insertBefore(sec, $("#p-buttons"));
    }
    sec.dataset.title = cp.title;
    buildGrid(sec, cp);
  }
}
function fillHomeButtons(list) {
  $$("[data-home-button]").forEach((slot) => {
    let b = findButton(list, slot.dataset.homeButton);
    // the element's own display options come on top of the button's
    if (b && (slot.dataset.hide || slot.dataset.invisible)) {
      b = { ...b, hide: [...(b.hide || []), ...(slot.dataset.hide || "").split(" ").filter(Boolean)],
            invisible: b.invisible || !!slot.dataset.invisible };
    }
    slot.replaceChildren(b ? makeTile(b) : Object.assign(document.createElement("div"), { className: "tile missing", textContent: "Knap slettet" }));
  });
}

document.addEventListener("click", (e) => {
  if (e.target.closest("[data-menu-open]")) { renderMenuPages(); $("#menu").hidden = false; return; }
  const item = e.target.closest("[data-menu-go]");
  if (item) {
    api("/api/action", { action: item.dataset.menuGo }).catch(() => {});
    item.classList.add("pressed");
    setTimeout(() => { $("#menu").hidden = true; item.classList.remove("pressed"); }, 300);
  } else if (e.target.closest("[data-menu-close]") || e.target.id === "menu") {
    $("#menu").hidden = true;
  }
});

// the Menu lists every visible page, so you can jump straight to one
const PAGE_ICONS = { overview: "grid", system: "bolt", buttons: "keyboard", music: "play", "claude-code": "star", github: "globe", spotify: "queue" };
function renderMenuPages() {
  $("#menu-pages").replaceChildren(...pages.map((p, i) => {
    const id = p.id.replace(/^p-/, "");
    const b = document.createElement("button");
    b.className = "tile" + (i === current ? " here" : "");
    b.dataset.goto = id;
    const ic = Object.assign(document.createElement("i"), { className: "ic" });
    drawIcon(ic, pageIcon(id));
    b.append(ic, Object.assign(document.createElement("span"), { textContent: p.dataset.title || id }));
    return b;
  }));
}

// short pop-up message at the bottom of the screen
function toast(msg, ms = 2200) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  t.classList.remove("show"); void t.offsetWidth; t.classList.add("show");
  clearTimeout(toast.timer);
  if (ms) toast.timer = setTimeout(() => { t.hidden = true; }, ms);
}

// ---------- automatic fullscreen ----------
// After 10 s outside fullscreen we try to enter it. Browsers only allow that from a tap,
// so if the attempt is refused we show a notice and the next tap anywhere does it.
let notFullFor = 0, fsArmed = false;
function enterFullscreen() {
  return document.documentElement.requestFullscreen?.({ navigationUI: "hide" }) ?? Promise.reject();
}
// "click" (not pointerdown): on touch screens the browser only counts the tap as a user
// gesture once the finger is lifted
document.addEventListener("click", () => {
  if (!fsArmed) return;
  fsArmed = false;
  enterFullscreen().then(() => { $("#toast").hidden = true; keepAwake(); }).catch(() => {});
}, { capture: true });
setInterval(() => {
  if (PREVIEW || ui.auto_fullscreen === false || document.fullscreenElement || document.visibilityState !== "visible") {
    notFullFor = 0;
    return;
  }
  notFullFor += 1;
  if (notFullFor === 10) {
    enterFullscreen().catch(() => {
      fsArmed = true;
      toast("Fuld skærm – tryk hvor som helst på skærmen", 0);
    });
  }
}, 1000);

document.addEventListener("click", (e) => {
  const open = e.target.closest("[data-folder]");
  const back = e.target.closest("[data-folder-back]");
  if (!open && !back) return;
  navigator.vibrate?.(10);
  if (back) folderPath.pop();
  else {
    // a folder placed on the home page opens on the Knapper page
    const fromHome = !!open.closest("#p-overview");
    const trail = fromHome ? pathTo(last?.buttons || [], open.dataset.folder) : [...folderPath, open.dataset.folder];
    folderPath = trail || [open.dataset.folder];
    if (fromHome) goTo(pages.findIndex((p) => p.id === "p-buttons"));
  }
  if (last) renderButtons(last.buttons || []);
});
// "Gå til side"-buttons (Stream Deck, home page and the Menu)
document.addEventListener("click", (e) => {
  const go = e.target.closest("[data-goto]");
  if (!go) return;
  navigator.vibrate?.(10);
  $("#menu").hidden = true;
  const i = pages.findIndex((p) => p.id === "p-" + go.dataset.goto);
  if (i < 0) toast("Siden er skjult eller findes ikke længere");
  else goTo(i);
});
function pathTo(list, id, trail = []) {
  for (const b of list) {
    if (b.type !== "folder") continue;
    if (b.id === id) return [...trail, b.id];
    const inner = pathTo(b.buttons || [], id, [...trail, b.id]);
    if (inner) return inner;
  }
  return null;
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
  layoutGen++;
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
    const res = await api("/api/action", btn.dataset.button ? { button: btn.dataset.button } : { action: btn.dataset.action });
    const data = await res.json().catch(() => ({}));
    if (data.notice) toast(data.notice);
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
  if (PREVIEW || !("wakeLock" in navigator) || document.visibilityState !== "visible" || (wakeLock && !wakeLock.released)) return;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
    wakeLock.addEventListener("release", () => setTimeout(keepAwake, 1000));
  } catch { /* not allowed right now – retried on next tap / visibility change */ }
}
keepAwake();
document.addEventListener("visibilitychange", keepAwake);
document.addEventListener("pointerdown", keepAwake, { passive: true });
setInterval(keepAwake, 30_000);

// ---------- pages (order, visibility and display options come from the PC's settings) ----------
const pager = $("#pager");
let pages = $$(".page");
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
let current = 0;
let ui = { dim: true, dim_from: 23, dim_to: 7, pixel_shift: true };
let uiKey = "";

function pageIcon(id) { return PAGE_ICONS[id] || (id.startsWith("custom-") ? "grid" : "star"); }
function fillGotoTiles() {  // names come from the page sections, which may arrive after the grid
  $$(".tile.goto").forEach((b) => {
    const id = b.dataset.goto, title = $("#p-" + id)?.dataset.title || id;
    const span = b.querySelector("span"), ic = b.querySelector(".ic");
    if (span.textContent !== title) span.textContent = title;
    if (ic.dataset.page !== id) { ic.dataset.page = id; drawIcon(ic, pageIcon(id)); }
  });
}
function buildDots() {
  fillGotoTiles();
  $("#dots").replaceChildren(...pages.map((p, i) => {
    const b = document.createElement("button");
    b.setAttribute("aria-label", p.dataset.title);
    b.append(document.createElement("i"));
    b.addEventListener("click", () => goTo(i));
    return b;
  }));
}
function goTo(i, smooth = true) {
  pager.scrollTo({ left: i * pager.clientWidth, behavior: smooth ? "smooth" : "instant" });
}
function updateDots() {
  const i = Math.round(pager.scrollLeft / Math.max(1, pager.clientWidth));
  if (i === current && $("#dots .on")) return;
  current = i;
  $$("#dots button").forEach((b, j) => b.classList.toggle("on", j === i));
  if (pages[i] && uiKey && !PREVIEW) store.set("phonedeck.page", pages[i].id);  // not before the saved page is restored
  PhoneDeck.each("page", pages[i]?.id);
}
function applyUi(next) {
  if (!next) return;
  if (PREVIEW) {  // unsaved drafts from the editor win over the saved layout
    next = { ...next, hidden: [] };
    if (previewDraft.home) next.home = previewDraft.home;
    if (previewDraft.custom) {
      const others = (next.custom_pages || []).filter((p) => p.id !== previewDraft.custom.id);
      next.custom_pages = [...others, previewDraft.custom];
    }
  }
  const key = JSON.stringify(next);
  if (key === uiKey) return;
  const firstTime = !uiKey;
  uiKey = key;
  const keepId = firstTime ? store.get("phonedeck.page") : pages[current]?.id;
  ui = next;
  renderCustomPages(next.custom_pages || []);
  for (const name of next.pages) {
    const el = $("#p-" + name);
    if (!el) continue;
    pager.append(el);  // re-order
    el.hidden = next.hidden.includes(name);
  }
  // pages from newly added extensions (not in the saved order yet) go last
  $$(".page").filter((p) => !next.pages.includes(p.id.slice(2))).forEach((p) => pager.append(p));
  pages = $$(".page").filter((p) => !p.hidden);
  buildDots();
  document.documentElement.style.setProperty("--deck-cols", next.deck_cols || 5);
  if (!next.pixel_shift) pager.style.transform = "";
  renderHome(next.home);
  dim();
  const idx = Math.max(0, pages.findIndex((p) => p.id === keepId));
  requestAnimationFrame(() => { goTo(idx, false); current = -1; updateDots(); });
}
pager.addEventListener("scroll", updateDots, { passive: true });
window.addEventListener("resize", () => { goTo(current, false); if (last) render(last); });
buildDots();
requestAnimationFrame(updateDots);

// ---------- clock + burn-in protection ----------
function tickClock() {
  const d = new Date();
  setText("time", d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }));
  setText("date", d.toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" }));
  setText("datelong", d.toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long" }));
  PhoneDeck.each("tick");
}
setInterval(tickClock, 1000); tickClock();

// Nudge everything a few pixels every minute so static UI doesn't burn into the AMOLED
setInterval(() => {
  if (!ui.pixel_shift) return;
  const r = () => Math.round(Math.random() * 6 - 3);
  pager.style.transform = `translate(${r()}px, ${r()}px)`;
}, 60_000);

// Dim at night (hours from the settings; may wrap past midnight)
function dim() {
  const h = new Date().getHours(), f = ui.dim_from, t = ui.dim_to;
  const night = f > t ? (h >= f || h < t) : (h >= f && h < t);
  document.body.classList.toggle("dim", !!ui.dim && f !== t && night);
}
setInterval(dim, 30_000); dim();

// ---------- live data ----------
// Only stay connected while this tab is visible: browsers allow just 6 connections per
// server, so forgotten background tabs must not hog them.
let es = null;
function connect() {
  if (es || document.visibilityState !== "visible") return;
  es = new EventSource("/api/stream");
  es.onmessage = (e) => { $("#offline").hidden = true; render(JSON.parse(e.data)); };
  es.onerror = () => { $("#offline").hidden = false; };
}
function disconnect() { if (es) { es.close(); es = null; } }
document.addEventListener("visibilitychange", () => (document.visibilityState === "visible" ? connect() : disconnect()));
window.addEventListener("pagehide", disconnect);
loadExtensions().then(connect);
