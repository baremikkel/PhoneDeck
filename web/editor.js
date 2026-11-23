"use strict";
// PhoneDeck – Stream Deck editor (runs in the PC's browser)

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const api = async (path, body) => {
  const res = await fetch(path, body === undefined
    ? { headers: { "X-PhoneDeck": "1" } }
    : { method: "POST", headers: { "Content-Type": "application/json", "X-PhoneDeck": "1" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
};

// Linux input key codes (what ydotool sends), keyed by KeyboardEvent.code – physical keys,
// so it works the same on a Danish or US layout.
const KEYCODES = {
  Escape: 1, Digit1: 2, Digit2: 3, Digit3: 4, Digit4: 5, Digit5: 6, Digit6: 7, Digit7: 8, Digit8: 9, Digit9: 10,
  Digit0: 11, Minus: 12, Equal: 13, Backspace: 14, Tab: 15, KeyQ: 16, KeyW: 17, KeyE: 18, KeyR: 19, KeyT: 20,
  KeyY: 21, KeyU: 22, KeyI: 23, KeyO: 24, KeyP: 25, BracketLeft: 26, BracketRight: 27, Enter: 28,
  KeyA: 30, KeyS: 31, KeyD: 32, KeyF: 33, KeyG: 34, KeyH: 35, KeyJ: 36, KeyK: 37, KeyL: 38, Semicolon: 39,
  Quote: 40, Backquote: 41, Backslash: 43, KeyZ: 44, KeyX: 45, KeyC: 46, KeyV: 47, KeyB: 48, KeyN: 49,
  KeyM: 50, Comma: 51, Period: 52, Slash: 53, NumpadMultiply: 55, Space: 57, CapsLock: 58,
  F1: 59, F2: 60, F3: 61, F4: 62, F5: 63, F6: 64, F7: 65, F8: 66, F9: 67, F10: 68, NumLock: 69, ScrollLock: 70,
  Numpad7: 71, Numpad8: 72, Numpad9: 73, NumpadSubtract: 74, Numpad4: 75, Numpad5: 76, Numpad6: 77,
  NumpadAdd: 78, Numpad1: 79, Numpad2: 80, Numpad3: 81, Numpad0: 82, NumpadDecimal: 83, IntlBackslash: 86,
  F11: 87, F12: 88, NumpadEnter: 96, NumpadDivide: 98, PrintScreen: 99, Home: 102, ArrowUp: 103, PageUp: 104,
  ArrowLeft: 105, ArrowRight: 106, End: 107, ArrowDown: 108, PageDown: 109, Insert: 110, Delete: 111, Pause: 119,
  ContextMenu: 127,
};
const MODS = { 29: "Ctrl", 97: "Ctrl", 42: "Shift", 54: "Shift", 56: "Alt", 100: "AltGr", 125: "Super", 126: "Super" };
const MOD_CODES = { ControlLeft: 29, ControlRight: 97, ShiftLeft: 42, ShiftRight: 54, AltLeft: 56, AltRight: 100, MetaLeft: 125, MetaRight: 126 };
const SPECIAL = [
  ["Print Screen", 99], ["Pause", 119], ["Lyd fra/til", 113], ["Lydstyrke ned", 114], ["Lydstyrke op", 115],
  ["Afspil/pause", 164], ["Næste nummer", 163], ["Forrige nummer", 165],
  ...Array.from({ length: 12 }, (_, i) => [`F${13 + i}`, 183 + i]),
];
const NAMES = Object.fromEntries([
  ...Object.entries(KEYCODES).map(([code, k]) => [k, code.replace(/^Key|^Digit/, "").replace("Arrow", "Pil ")]),
  ...SPECIAL.map(([n, k]) => [k, n]),
  [57, "Mellemrum"], [28, "Enter"], [1, "Esc"], [111, "Delete"], [14, "Backspace"],
]);
const comboText = (keys) => keys.map((k) => MODS[k] || NAMES[k] || `#${k}`).join(" + ");

const COLORS = ["", "#ff5c5c", "#ff9f43", "#f5c84c", "#1ed760", "#2ec4b6", "#4cc2ff", "#7c6cff", "#b18cff", "#ff6bb5", "#9aa0a6"];
const EMOJI = ["💬", "🌐", "📁", "🎮", "🎵", "📷", "🔒", "⌨️", "🖥️", "📝", "📧", "📅", "⚡", "⭐", "🔧", "🧪", "🚀", "☕", "🎧", "📺"];
const BUILTIN_ICONS = ["globe", "terminal", "keyboard", "lock", "folder", "star", "bolt", "fullscreen", "play", "next", "prev", "volUp", "mic"];

let deck = [];
let path = [];  // folders opened in the editor, outermost first
const level = () => (path.length ? path[path.length - 1].buttons : deck);
const allButtons = (list = deck) => list.flatMap((b) => [b, ...(b.action?.type === "folder" ? allButtons(b.buttons || []) : [])]);
let builtins = {};
let apps = [];
let selected = -1;
let dirty = false;

// ---------- helpers ----------
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = err ? "err" : "";
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 2600);
}
function setDirty(v = true) {
  dirty = v;
  $("#save").disabled = !v;
  $("#save").textContent = v ? "Gem ændringer" : "Gemt ✓";
}
function iconEl(icon) {
  if (icon?.kind === "app") {
    const img = document.createElement("img");
    img.alt = "";
    img.src = "/api/appicon?id=" + encodeURIComponent(icon.value);
    img.onerror = () => img.replaceWith(Object.assign(document.createElement("b"), { textContent: "📦" }));
    return img;
  }
  if (icon?.kind === "builtin") {
    const i = document.createElement("i");
    i.className = "ic";
    drawIcon(i, icon.value);
    return i;
  }
  return Object.assign(document.createElement("b"), { textContent: icon?.value || "⭐" });
}
function tileContent(el, b) {
  if (b.color) el.style.setProperty("--btn", b.color); else el.style.removeProperty("--btn");
  const label = document.createElement("span");
  label.textContent = b.label || "Ny knap";
  el.replaceChildren(iconEl(b.icon), label);
}

// ---------- deck grid (drag & drop to reorder) ----------
let dragFrom = -1;
function renderDeck() {
  const tiles = level().map((b, i) => {
    const el = document.createElement("div");
    el.className = "tile" + (i === selected ? " sel" : "");
    el.draggable = true;
    el.tabIndex = 0;
    tileContent(el, b);
    el.addEventListener("click", () => select(i));
    if (b.action?.type === "folder") {
      el.classList.add("folder");
      el.dataset.count = (b.buttons || []).length;
      el.addEventListener("dblclick", () => openFolder(b));
    }
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") select(i); });
    el.addEventListener("dragstart", (e) => { dragFrom = i; el.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
    el.addEventListener("dragend", () => { el.classList.remove("dragging"); $$(".drop-before").forEach((x) => x.classList.remove("drop-before")); });
    el.addEventListener("dragover", (e) => { e.preventDefault(); $$(".drop-before").forEach((x) => x.classList.remove("drop-before")); el.classList.add("drop-before"); });
    el.addEventListener("drop", (e) => {
      e.preventDefault();
      // dropping onto a folder puts the button inside it
      if (b.action?.type === "folder" && dragFrom !== i) moveTo(dragFrom, b.buttons || (b.buttons = []));
      else move(dragFrom, i);
    });
    return el;
  });
  const add = document.createElement("div");
  add.className = "tile add";
  add.append(iconEl({ kind: "builtin", value: "plus" }), Object.assign(document.createElement("span"), { textContent: "Ny knap" }));
  add.addEventListener("click", addButton);
  add.addEventListener("dragover", (e) => e.preventDefault());
  add.addEventListener("drop", (e) => { e.preventDefault(); move(dragFrom, level().length); });
  if (path.length) {
    const back = document.createElement("div");
    back.className = "tile back";
    back.append(iconEl({ kind: "builtin", value: "prev" }), Object.assign(document.createElement("span"), { textContent: "Tilbage" }));
    back.addEventListener("click", () => { path.pop(); select(-1); });
    // drop on "Tilbage" = move the button out of this folder
    back.addEventListener("dragover", (e) => e.preventDefault());
    back.addEventListener("drop", (e) => { e.preventDefault(); moveTo(dragFrom, path.length > 1 ? path[path.length - 2].buttons : deck); });
    tiles.unshift(back);
  }
  $("#deck").replaceChildren(...tiles, add);
  renderCrumbs();
  sendPreview();
}
function move(from, to) {
  if (from < 0 || from === to) return;
  const [b] = level().splice(from, 1);
  const target = to > from ? to - 1 : to;
  level().splice(target, 0, b);
  if (selected === from) selected = target;
  else if (selected > from && selected <= target) selected--;
  else if (selected < from && selected >= target) selected++;
  setDirty();
  renderDeck();
}
function openFolder(f) {
  f.buttons = f.buttons || [];
  path.push(f);
  select(-1);
}
function reopen() {  // keep the same folders open after the list was reloaded from the server
  const ids = path.map((f) => f.id);
  path = [];
  let list = deck;
  for (const id of ids) {
    const f = list.find((b) => b.id === id && b.action?.type === "folder");
    if (!f) break;
    path.push(f);
    list = f.buttons;
  }
}
function moveTo(from, target) {
  if (from < 0) return;
  const [b] = level().splice(from, 1);
  if (b === path[path.length - 1] || target === b.buttons) { level().splice(from, 0, b); return; }
  target.push(b);
  selected = -1;
  setDirty();
  select(-1);
  toast(`"${b.label}" er flyttet`);
}
function renderCrumbs() {
  const crumbs = [Object.assign(document.createElement("a"), { textContent: "Alle knapper", href: "#deck" })];
  crumbs[0].onclick = (e) => { e.preventDefault(); path = []; select(-1); };
  path.forEach((f, i) => {
    const a = Object.assign(document.createElement("a"), { textContent: f.label, href: "#deck" });
    a.onclick = (e) => { e.preventDefault(); path = path.slice(0, i + 1); select(-1); };
    crumbs.push(document.createTextNode(" › "), a);
  });
  $("#crumbs").replaceChildren(...crumbs);
}

function addButton() {
  level().push({ label: "Ny knap", icon: { kind: "emoji", value: "⭐" }, action: { type: "app", app: "" } });
  setDirty();
  select(level().length - 1);
  $("#label").select();
}

// ---------- form ----------
function select(i) {
  selected = i;
  renderDeck();
  $("#form").hidden = i < 0;
  $("#empty").hidden = i >= 0;
  if (i < 0) return;
  const b = level()[i];
  $("#label").value = b.label;
  showType(b.action.type);
  $("#url").value = b.action.type === "url" ? b.action.url : "";
  $("#command").value = b.action.type === "command" ? commandText(b.action.argv) : "";
  $("#builtin").value = b.action.type === "builtin" ? b.action.name : Object.keys(builtins)[0];
  renderApps();
  renderHotkey();
  renderIcon();
  renderColors();
  $("#test-msg").textContent = "";
}
const cur = () => level()[selected];
function update(fn) { fn(cur()); setDirty(); renderPreview(); renderDeck(); }
function renderPreview() { tileContent($("#preview"), cur()); sendPreview(); }

function commandText(argv) {
  if (!argv) return "";
  return argv[0] === "sh" && argv[1] === "-c" && argv.length === 3 ? argv[2] : argv.map((a) => /\s/.test(a) ? JSON.stringify(a) : a).join(" ");
}

function showType(type) {
  $$("#types button").forEach((b) => b.classList.toggle("on", b.dataset.type === type));
  $$(".type-panel").forEach((p) => p.classList.toggle("on", p.dataset.panel === type));
  // which icon kinds make sense
  $('#icon-kinds [data-kind="app"]').hidden = type !== "app";
}

$("#types").addEventListener("click", (e) => {
  const t = e.target.closest("button")?.dataset.type;
  if (!t) return;
  update((b) => {
    if (t === "url") b.action = { type: "url", url: $("#url").value || "https://" };
    if (t === "app") b.action = { type: "app", app: "" };
    if (t === "hotkey") b.action = { type: "hotkey", keys: [] };
    if (t === "command") b.action = { type: "command", argv: ["sh", "-c", $("#command").value || ""] };
    if (t === "folder") {
      b.action = { type: "folder" };
      b.buttons = b.buttons || [];
      if (b.icon.kind === "app") b.icon = { kind: "builtin", value: "folder" };
    }
    if (t === "builtin") {
      const n = $("#builtin").value || Object.keys(builtins)[0];
      b.action = { type: "builtin", name: n };
      b.icon = { kind: "builtin", value: builtins[n][1] };
    }
    if (b.icon.kind === "app" && t !== "app") b.icon = { kind: "emoji", value: t === "url" ? "🌐" : t === "hotkey" ? "⌨️" : "⚡" };
    if (t !== "folder" && b.buttons?.length && !confirm(`Mappen indeholder ${b.buttons.length} knap(per), som slettes. Fortsæt?`)) {
      b.action = { type: "folder" };
      return;
    }
    if (t !== "folder") delete b.buttons;
  });
  showType(t);
  renderIcon();
});

$("#label").addEventListener("input", (e) => update((b) => { b.label = e.target.value; }));
$("#url").addEventListener("input", (e) => update((b) => { b.action = { type: "url", url: e.target.value.trim() }; }));
$("#command").addEventListener("input", (e) => update((b) => { b.action = { type: "command", argv: ["sh", "-c", e.target.value] }; }));
$("#builtin").addEventListener("change", (e) => update((b) => {
  b.action = { type: "builtin", name: e.target.value };
  b.label = builtins[e.target.value][0];
  b.icon = { kind: "builtin", value: builtins[e.target.value][1] };
  $("#label").value = b.label;
  renderIcon();
}));

// ---------- programs ----------
function renderApps() {
  const q = $("#app-search").value.trim().toLowerCase();
  const chosen = cur()?.action.type === "app" ? cur().action.app : "";
  const list = apps.filter((a) => !q || a.name.toLowerCase().includes(q)).slice(0, 200);
  $("#app-list").replaceChildren(...list.map((a) => {
    const row = document.createElement("button");
    row.className = a.id === chosen ? "on" : "";
    const img = document.createElement("img");
    img.alt = ""; img.loading = "lazy";
    img.src = "/api/appicon?id=" + encodeURIComponent(a.id);
    img.onerror = () => img.replaceWith(Object.assign(document.createElement("span"), { className: "noicon" }));
    row.append(img, a.name);
    row.addEventListener("click", () => {
      update((b) => {
        const wasDefault = !b.label || b.label === "Ny knap" || apps.some((x) => x.name === b.label);
        b.action = { type: "app", app: a.id };
        b.icon = { kind: "app", value: a.id };
        if (wasDefault) b.label = a.name;
      });
      $("#label").value = cur().label;
      renderApps();
      renderIcon();
    });
    return row;
  }));
}
$("#app-search").addEventListener("input", renderApps);

// ---------- hotkeys ----------
function hotkeyKeys() { return cur()?.action.type === "hotkey" ? cur().action.keys : []; }
function setHotkey(keys) {
  update((b) => { b.action = { type: "hotkey", keys, text: comboText(keys) }; });
  renderHotkey();
}
function renderHotkey() {
  const keys = hotkeyKeys();
  const mods = new Set(keys.filter((k) => MODS[k]));
  $$("#mods button").forEach((b) => b.classList.toggle("on", mods.has(Number(b.dataset.mod))));
  const main = keys.filter((k) => !MODS[k]);
  $("#record").textContent = keys.length ? comboText(keys) : "Klik her og tryk på en tast …";
  $("#record").classList.remove("listening");
  if (!main.length && keys.length) $("#record").textContent += "  + …";
}
$("#mods").addEventListener("click", (e) => {
  const m = Number(e.target.closest("button")?.dataset.mod);
  if (!m) return;
  const keys = hotkeyKeys();
  const mods = keys.filter((k) => MODS[k]);
  const main = keys.filter((k) => !MODS[k]);
  const next = mods.includes(m) ? mods.filter((k) => k !== m) : [...mods, m];
  setHotkey([...next, ...main]);
});
$("#record").addEventListener("click", () => {
  $("#record").textContent = "Tryk på din genvej nu …";
  $("#record").classList.add("listening");
  $("#record").focus();
});
$("#record").addEventListener("keydown", (e) => {
  if (!$("#record").classList.contains("listening")) return;
  e.preventDefault();
  if (MOD_CODES[e.code]) return;  // wait for the real key
  const code = KEYCODES[e.code];
  if (!code) { toast("Den tast kan ikke bruges – vælg den evt. på listen", true); return; }
  const mods = [];
  if (e.ctrlKey) mods.push(29);
  if (e.shiftKey) mods.push(42);
  if (e.altKey && !e.getModifierState("AltGraph")) mods.push(56);
  if (e.getModifierState("AltGraph")) mods.push(100);
  if (e.metaKey) mods.push(125);
  // keep modifiers toggled with the buttons too
  const existing = hotkeyKeys().filter((k) => MODS[k]);
  const all = [...new Set([...existing, ...mods])];
  setHotkey([...all, code]);
});
$("#special").addEventListener("change", (e) => {
  const k = Number(e.target.value);
  if (!k) return;
  const mods = hotkeyKeys().filter((x) => MODS[x]);
  setHotkey([...mods, k]);
  e.target.value = "";
});

// ---------- icon ----------
function renderIcon() {
  const b = cur();
  $$("#icon-kinds button").forEach((x) => x.classList.toggle("on", x.dataset.kind === b.icon.kind));
  $("#emoji").hidden = b.icon.kind !== "emoji";
  $("#emoji").value = b.icon.kind === "emoji" ? b.icon.value : "";
  const picks = b.icon.kind === "builtin"
    ? BUILTIN_ICONS.map((n) => { const x = document.createElement("button"); x.append(iconEl({ kind: "builtin", value: n })); x.title = n; x.onclick = () => update((bb) => { bb.icon = { kind: "builtin", value: n }; }); return x; })
    : b.icon.kind === "emoji"
      ? EMOJI.map((em) => { const x = document.createElement("button"); x.textContent = em; x.onclick = () => { update((bb) => { bb.icon = { kind: "emoji", value: em }; }); $("#emoji").value = em; }; return x; })
      : [];
  $("#emoji-picks").replaceChildren(...picks);
  renderPreview();
}
$("#icon-kinds").addEventListener("click", (e) => {
  const k = e.target.closest("button")?.dataset.kind;
  if (!k) return;
  update((b) => {
    if (k === "app" && b.action.type === "app" && b.action.app) b.icon = { kind: "app", value: b.action.app };
    if (k === "builtin") b.icon = { kind: "builtin", value: b.action.type === "builtin" ? builtins[b.action.name][1] : "star" };
    if (k === "emoji") b.icon = { kind: "emoji", value: "⭐" };
  });
  renderIcon();
});
$("#emoji").addEventListener("input", (e) => update((b) => { b.icon = { kind: "emoji", value: e.target.value || "⭐" }; }));

// ---------- colour ----------
function renderColors() {
  const curColor = cur().color || "";
  $("#colors").replaceChildren(...COLORS.map((c) => {
    const b = document.createElement("button");
    b.className = (c ? "" : "none ") + (c === curColor ? "on" : "");
    b.title = c || "Ingen farve";
    if (c) b.style.background = c;
    b.onclick = () => { update((x) => { x.color = c; }); renderColors(); };
    return b;
  }));
}

// ---------- test / delete / save / reset ----------
$("#test").addEventListener("click", async () => {
  $("#test-msg").textContent = "";
  try {
    await api("/api/deck/test", { action: cur().action });
    $("#test-msg").textContent = "Kørt ✓";
  } catch (err) {
    $("#test-msg").textContent = err.message;
  }
});
$("#open-folder").addEventListener("click", () => openFolder(cur()));
$("#delete").addEventListener("click", () => {
  const n = cur().buttons?.length || 0;
  if (!confirm(n ? `Slet mappen "${cur().label}" og de ${n} knapper i den?` : `Slet knappen "${cur().label}"?`)) return;
  level().splice(selected, 1);
  setDirty();
  select(-1);
});
$("#save").addEventListener("click", async () => {
  try {
    const r = await api("/api/deck", { buttons: deck });
    deck = r.buttons;
    reopen();
    setDirty(false);
    renderDeck();
    toast("Gemt – telefonen er opdateret");
  } catch (err) {
    toast(err.message, true);
  }
});
$("#reset").addEventListener("click", async () => {
  if (!confirm("Erstat alle knapper med standardknapperne?")) return;
  try {
    const r = await api("/api/deck/reset", {});
    deck = r.buttons;
    path = [];
    setDirty(false);
    select(-1);
    toast("Nulstillet til standard");
  } catch (err) {
    toast(err.message, true);
  }
});
window.addEventListener("beforeunload", (e) => { if (dirty || homeDirty) { e.preventDefault(); e.returnValue = ""; } });
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (dirty) $("#save").click(); }
});

// ================= home page layout =================
// core widgets; installed extensions add theirs when the editor loads
const WIDGETS = {
  cpu: ["CPU", "bolt"], gpu: ["GPU", "bolt"], ram: ["RAM", "folder"], net: ["Netværk", "globe"],
  disk: ["Disk", "folder"], sys: ["Systemlinje (RAM, net, disk, ur)", "keyboard"], clock: ["Ur", "lock"],
};
let home = null, homeDirty = false, selItem = -1, selStart = null;
let editing = "home";          // "home" or the id of one of your own pages
let homeLayout = null;         // the saved home page (kept while a custom page is edited)
let customPages = [];          // [{id, title, cols, rows, items}]
const isHome = () => editing === "home";

function homeSetDirty(v = true) {
  homeDirty = v;
  $("#home-save").disabled = !v;
  $("#home-save").textContent = v ? (isHome() ? "Gem forside" : "Gem side") : "Gemt ✓";
}
function occupied(except = -1) {
  const m = new Set(isHome() ? [`${home.cols - 1},${home.rows - 1}`] : []);  // locked menu button (home only)
  home.items.forEach((it, i) => {
    if (i === except) return;
    for (let x = it.x; x < it.x + it.w; x++) for (let y = it.y; y < it.y + it.h; y++) m.add(`${x},${y}`);
  });
  return m;
}
function fits(it, except) {
  if (it.x < 0 || it.y < 0 || it.w < 1 || it.h < 1 || it.x + it.w > home.cols || it.y + it.h > home.rows) return false;
  const occ = occupied(except);
  for (let x = it.x; x < it.x + it.w; x++) for (let y = it.y; y < it.y + it.h; y++) if (occ.has(`${x},${y}`)) return false;
  return true;
}
function widgetLabel(it) {
  if (it.type === "button") {
    const b = allButtons().find((x) => x.id === it.button);
    return b ? [b.label, b.icon] : ["(slettet knap)", { kind: "emoji", value: "⚠️" }];
  }
  const [name, icon] = WIDGETS[it.type] || [`${it.type} (udvidelse ikke installeret)`, "star"];
  return [name, { kind: "builtin", value: icon }];
}
function renderHomeGrid() {
  const g = $("#home-grid");
  g.style.gridTemplateColumns = `repeat(${home.cols}, 1fr)`;
  g.style.gridTemplateRows = `repeat(${home.rows}, 1fr)`;
  const occ = occupied();
  const els = [];
  for (let y = 0; y < home.rows; y++) for (let x = 0; x < home.cols; x++) {
    if (occ.has(`${x},${y}`)) continue;
    const c = document.createElement("div");
    c.className = "cell" + (selStart && selStart.x === x && selStart.y === y ? " sel" : "");
    c.style.gridColumn = `${x + 1}`; c.style.gridRow = `${y + 1}`;
    c.dataset.x = x; c.dataset.y = y;
    els.push(c);
  }
  const lock = document.createElement("div");
  lock.className = "w locked";
  lock.title = "Låst: åbner indstillinger og editor";
  lock.style.gridColumn = `${home.cols}`; lock.style.gridRow = `${home.rows}`;
  if (!isHome()) lock.hidden = true;
  lock.append(iconEl({ kind: "builtin", value: "gear" }), Object.assign(document.createElement("span"), { textContent: "Menu" }),
    Object.assign(document.createElement("small"), { textContent: "🔒 låst" }));
  els.push(lock);
  home.items.forEach((it, i) => {
    const w = document.createElement("div");
    w.className = "w" + (i === selItem ? " on" : "");
    w.style.gridColumn = `${it.x + 1} / span ${it.w}`; w.style.gridRow = `${it.y + 1} / span ${it.h}`;
    const [name, icon] = widgetLabel(it);
    if (it.type === "button") { const b = allButtons().find((x) => x.id === it.button); if (b?.color) w.style.setProperty("--btn", b.color); w.classList.add("tile"); }
    w.append(iconEl(icon), Object.assign(document.createElement("span"), { textContent: name }),
      Object.assign(document.createElement("small"), { textContent: `${it.w}×${it.h}` }));
    w.dataset.i = i;
    w.title = "Træk for at flytte · træk i hjørnet for at ændre størrelse";
    const handle = Object.assign(document.createElement("span"), { className: "resize", title: "Træk for at ændre størrelse" });
    w.append(handle);
    els.push(w);
  });
  g.replaceChildren(...els);
  sendPreview();
}
function cellClick(x, y) {
  selItem = -1;
  if (!selStart) { selStart = { x, y }; $("#home-hint").textContent = "Klik på et andet tomt felt for at gøre området større – eller vælg en widget nu."; }
  else {
    const it = { x: Math.min(selStart.x, x), y: Math.min(selStart.y, y), w: Math.abs(x - selStart.x) + 1, h: Math.abs(y - selStart.y) + 1 };
    if (!fits(it)) { toast("Området overlapper et andet felt", true); selStart = null; renderHomeGrid(); showPanel(); return; }
    selStart = it;
  }
  renderHomeGrid(); showPanel();
  // highlight the whole pending rectangle
  if (selStart?.w) $$("#home-grid .cell").forEach((c) => {
    const cx = +c.style.gridColumn - 1, cy = +c.style.gridRow - 1;
    if (cx >= selStart.x && cx < selStart.x + selStart.w && cy >= selStart.y && cy < selStart.y + selStart.h) c.classList.add("sel");
  });
}
// ---------- mouse: drag to move, drag the corner to resize, drag over empty cells to select ----------
function cellAt(e) {
  const r = $("#home-grid").getBoundingClientRect();
  const x = Math.floor(((e.clientX - r.left) / r.width) * home.cols);
  const y = Math.floor(((e.clientY - r.top) / r.height) * home.rows);
  return { x: Math.max(0, Math.min(home.cols - 1, x)), y: Math.max(0, Math.min(home.rows - 1, y)) };
}
let drag = null;  // {mode: "move"|"resize"|"select", i, start, off, el, next}
$("#home-grid").addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  const w = e.target.closest(".w[data-i]");
  const cell = e.target.closest(".cell");
  const at = cellAt(e);
  if (w) {
    const i = +w.dataset.i, it = home.items[i];
    const mode = e.target.closest(".resize") ? "resize" : "move";
    drag = { mode, i, start: at, off: { x: at.x - it.x, y: at.y - it.y }, el: w, next: { ...it }, moved: false };
    w.classList.add("dragging");
  } else if (cell) {
    drag = { mode: "select", start: at, next: { x: at.x, y: at.y, w: 1, h: 1 }, moved: false };
    markSelection(drag.next);
  } else return;
  $("#home-grid").setPointerCapture(e.pointerId);
  e.preventDefault();
});
$("#home-grid").addEventListener("pointermove", (e) => {
  if (!drag) return;
  const at = cellAt(e);
  if (at.x !== drag.start.x || at.y !== drag.start.y) drag.moved = true;
  if (drag.mode === "select") {
    drag.next = { x: Math.min(drag.start.x, at.x), y: Math.min(drag.start.y, at.y),
                  w: Math.abs(at.x - drag.start.x) + 1, h: Math.abs(at.y - drag.start.y) + 1 };
    markSelection(drag.next, !fits(drag.next));
    return;
  }
  const it = home.items[drag.i];
  const next = drag.mode === "move"
    ? { ...it, x: Math.max(0, Math.min(home.cols - it.w, at.x - drag.off.x)), y: Math.max(0, Math.min(home.rows - it.h, at.y - drag.off.y)) }
    : { ...it, w: Math.max(1, at.x - it.x + 1), h: Math.max(1, at.y - it.y + 1) };
  const ok = fits(next, drag.i);
  drag.el.classList.toggle("bad", !ok);
  if (ok) drag.next = next;
  // live preview
  drag.el.style.gridColumn = `${(ok ? next : drag.next).x + 1} / span ${(ok ? next : drag.next).w}`;
  drag.el.style.gridRow = `${(ok ? next : drag.next).y + 1} / span ${(ok ? next : drag.next).h}`;
  const small = drag.el.querySelector("small");
  if (small) small.textContent = `${drag.next.w}×${drag.next.h}`;
});
$("#home-grid").addEventListener("pointerup", () => {
  if (!drag) return;
  const d = drag;
  drag = null;
  if (d.mode === "select") {
    if (!fits(d.next)) { toast("Området overlapper et andet felt", true); selStart = null; renderHomeGrid(); showPanel(); return; }
    selItem = -1;
    selStart = d.next;
    renderHomeGrid(); showPanel(); markSelection(selStart);
    $("#home-hint").textContent = "Vælg hvad der skal stå i det markerede område – eller træk et element fra listen herind.";
    return;
  }
  if (d.moved) {
    home.items[d.i] = d.next;
    homeSetDirty();
  }
  selItem = d.i;  // a click (no movement) just selects it
  selStart = null;
  renderHomeGrid(); showPanel();
});
function markSelection(r, bad = false) {
  $$("#home-grid .cell").forEach((c) => {
    const cx = +c.dataset.x, cy = +c.dataset.y;
    const inside = cx >= r.x && cx < r.x + r.w && cy >= r.y && cy < r.y + r.h;
    c.classList.toggle("sel", inside && !bad);
    c.classList.toggle("bad", inside && bad);
  });
}
// drop an element from the list onto an empty cell (or onto a marked area)
$("#home-grid").addEventListener("dragover", (e) => {
  if (e.dataTransfer.types.includes("text/phonedeck-widget")) { e.preventDefault(); markSelection(dropArea(e)); }
});
$("#home-grid").addEventListener("dragleave", () => markSelection({ x: -1, y: -1, w: 0, h: 0 }));
$("#home-grid").addEventListener("drop", (e) => {
  const raw = e.dataTransfer.getData("text/phonedeck-widget");
  if (!raw) return;
  e.preventDefault();
  const w = JSON.parse(raw);
  const area = dropArea(e);
  if (!fits(area)) { toast("Der er ikke plads her", true); renderHomeGrid(); return; }
  home.items.push({ type: w.type, ...(w.button ? { button: w.button } : {}), ...area });
  selStart = null; selItem = home.items.length - 1;
  homeSetDirty(); renderHomeGrid(); showPanel();
});
function dropArea(e) {
  // dropped inside the marked area -> fill it; otherwise 2×1 if there is room, else 1×1
  const at = cellAt(e);
  if (selStart?.w && at.x >= selStart.x && at.x < selStart.x + selStart.w && at.y >= selStart.y && at.y < selStart.y + selStart.h) return { ...selStart };
  const wide = { x: at.x, y: at.y, w: 2, h: 1 };
  return fits(wide) ? wide : { x: at.x, y: at.y, w: 1, h: 1 };
}

function showPanel() {
  $("#home-pick").hidden = !selStart;
  $("#home-sel").hidden = selItem < 0;
  $("#home-empty").hidden = !!selStart || selItem >= 0;
  if (selItem >= 0) $("#sel-name").textContent = widgetLabel(home.items[selItem])[0];
  if (!selStart) $("#home-hint").textContent = "Træk hen over tomme felter for at markere et område – eller træk et element fra listen ind i gitteret.";
}
function addWidget(type, button) {
  const r = selStart.w ? selStart : { ...selStart, w: 1, h: 1 };
  const it = { type, x: r.x, y: r.y, w: r.w, h: r.h };
  if (button) it.button = button;
  home.items.push(it);
  selStart = null; selItem = home.items.length - 1;
  homeSetDirty(); renderHomeGrid(); showPanel();
}
function renderPickers() {
  $("#widget-list").replaceChildren(...Object.entries(WIDGETS).map(([t, [name, icon]]) => {
    const b = document.createElement("button");
    b.append(iconEl({ kind: "builtin", value: icon }), name);
    b.onclick = () => addWidget(t);
    b.draggable = true;
    b.ondragstart = (e) => { e.dataTransfer.setData("text/phonedeck-widget", JSON.stringify({ type: t })); };
    return b;
  }));
  $("#button-list").replaceChildren(...allButtons().map((d) => {
    const b = document.createElement("button");
    b.append(iconEl(d.icon), d.label);
    b.onclick = () => addWidget("button", d.id);
    b.draggable = true;
    b.ondragstart = (e) => { e.dataTransfer.setData("text/phonedeck-widget", JSON.stringify({ type: "button", button: d.id })); };
    return b;
  }));
}
$("#pick-cancel").onclick = () => { selStart = null; renderHomeGrid(); showPanel(); };
$("#sel-remove").onclick = () => { home.items.splice(selItem, 1); selItem = -1; homeSetDirty(); renderHomeGrid(); showPanel(); };
$$("[data-mv], [data-sz]").forEach((btn) => btn.addEventListener("click", () => {
  const it = home.items[selItem];
  const [dx, dy] = (btn.dataset.mv || btn.dataset.sz).split(",").map(Number);
  const next = btn.dataset.mv ? { ...it, x: it.x + dx, y: it.y + dy } : { ...it, w: it.w + dx, h: it.h + dy };
  if (!fits(next, selItem)) { toast("Der er ikke plads", true); return; }
  home.items[selItem] = next; homeSetDirty(); renderHomeGrid();
}));
$("#grid").onchange = (e) => {
  const [c, r] = e.target.value.split("x").map(Number);
  const kept = home.items.filter((it) => it.x + it.w <= c && it.y + it.h <= r
    && !(isHome() && it.x <= c - 1 && c - 1 < it.x + it.w && it.y <= r - 1 && r - 1 < it.y + it.h));
  if (kept.length < home.items.length && !confirm(`${home.items.length - kept.length} felt(er) passer ikke i det nye gitter og bliver fjernet. Fortsæt?`)) {
    e.target.value = `${home.cols}x${home.rows}`; return;
  }
  home = { cols: c, rows: r, items: kept }; selItem = -1; selStart = null;
  homeSetDirty(); renderHomeGrid(); showPanel();
};
$("#home-save").onclick = async () => {
  try {
    if (isHome()) {
      const r = await api("/api/settings", { ui: { home } });
      home = homeLayout = r.settings.ui.home;
    } else {
      const pages = customPages.map((p) => (p.id === editing ? { ...p, ...home } : p));
      const r = await api("/api/settings", { ui: { custom_pages: pages } });
      customPages = r.settings.ui.custom_pages;
      home = structuredClone(customPages.find((p) => p.id === editing));
    }
    homeSetDirty(false); renderHomeGrid();
    toast("Forsiden er gemt – telefonen er opdateret");
  } catch (err) { toast(err.message, true); }
};
// ---------- your own pages ----------
function renderPageSelect() {
  const sel = $("#page-select");
  sel.replaceChildren(
    Object.assign(document.createElement("option"), { value: "home", textContent: "Forside" }),
    ...customPages.map((p) => Object.assign(document.createElement("option"), { value: p.id, textContent: p.title })),
    Object.assign(document.createElement("option"), { value: "__new", textContent: "+ Ny side …" }));
  sel.value = editing;
  $("#page-rename").hidden = $("#page-delete").hidden = isHome();
  $("#home-reset").hidden = !isHome();
}
function switchTo(id) {
  if (homeDirty && !confirm("Du har ændringer, der ikke er gemt. Skift alligevel?")) { renderPageSelect(); return; }
  editing = id;
  home = structuredClone(isHome() ? homeLayout : customPages.find((p) => p.id === id));
  $("#grid").value = `${home.cols}x${home.rows}`;
  selItem = -1; selStart = null;
  homeSetDirty(false); renderPageSelect(); renderHomeGrid(); showPanel();
}
async function saveCustomPages(pages, msg) {
  const r = await api("/api/settings", { ui: { custom_pages: pages } });
  customPages = r.settings.ui.custom_pages;
  toast(msg);
}
$("#page-select").onchange = async (e) => {
  if (e.target.value !== "__new") return switchTo(e.target.value);
  const title = (prompt("Navn på den nye side:", "Min side") || "").trim();
  if (!title) { renderPageSelect(); return; }
  const id = Math.random().toString(36).slice(2, 8);
  try {
    await saveCustomPages([...customPages, { id, title, cols: 6, rows: 3, items: [] }], `Siden "${title}" er oprettet`);
    homeDirty = false;
    switchTo(id);
  } catch (err) { toast(err.message, true); renderPageSelect(); }
};
$("#page-rename").onclick = async () => {
  const p = customPages.find((x) => x.id === editing);
  const title = (prompt("Nyt navn:", p.title) || "").trim();
  if (!title) return;
  try { await saveCustomPages(customPages.map((x) => (x.id === editing ? { ...x, title } : x)), "Omdøbt"); renderPageSelect(); }
  catch (err) { toast(err.message, true); }
};
$("#page-delete").onclick = async () => {
  const p = customPages.find((x) => x.id === editing);
  if (!confirm(`Slet siden "${p.title}"?`)) return;
  try {
    await saveCustomPages(customPages.filter((x) => x.id !== editing), "Siden er slettet");
    homeDirty = false;
    switchTo("home");
  } catch (err) { toast(err.message, true); }
};

$("#home-reset").onclick = () => {
  if (!confirm("Erstat forsiden med standardforsiden?")) return;
  home = { cols: 8, rows: 4, items: [
    { type: "cpu", x: 0, y: 0, w: 2, h: 3 }, { type: "gpu", x: 2, y: 0, w: 2, h: 3 },
    { type: "media", x: 4, y: 0, w: 2, h: 3 }, { type: "claude", x: 6, y: 0, w: 2, h: 3 },
    { type: "sys", x: 0, y: 3, w: 7, h: 1 }] };
  $("#grid").value = "8x4"; selItem = -1; selStart = null;
  homeSetDirty(); renderHomeGrid(); showPanel();
};

function showTab() {
  const tab = location.hash === "#home" ? "home" : "deck";
  document.body.className = "tab-" + tab;
  $$(".tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === tab));
  if (tab === "home" && home) { renderPickers(); renderHomeGrid(); showPanel(); }
  sendPreview();
}
window.addEventListener("hashchange", showTab);

// ---------- live preview (the real dashboard in an iframe) ----------
function sizePreview() {
  const [w, h] = $("#preview-size").value.split("x").map(Number);
  const box = $("#preview-box"), frame = $("#preview-frame");
  const scale = Math.min(1, box.clientWidth / w);
  frame.style.width = w + "px"; frame.style.height = h + "px";
  frame.style.transform = `scale(${scale})`;
  frame.style.left = Math.max(0, (box.clientWidth - w * scale) / 2) + "px";  // centred in the frame
  box.style.height = h * scale + "px";
}
new ResizeObserver(sizePreview).observe($("#preview-box"));
$("#preview-size").onchange = () => { sizePreview(); sendPreview(); };

// the phone wants buttons in its own (public) format
function toPublic(list) {
  return (list || []).map((b, i) => ({
    id: b.id || `draft${i}`, label: b.label || "Ny knap", icon: b.icon, color: b.color || "",
    type: b.action?.type, builtin: b.action?.type === "builtin" ? b.action.name : undefined,
    buttons: b.action?.type === "folder" ? toPublic(b.buttons) : undefined,
  }));
}
let previewTimer;
function sendPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    const frame = $("#preview-frame")?.contentWindow;
    if (!frame || !home) return;
    const msg = { type: "phonedeck-preview" };
    if (location.hash !== "#home") {
      msg.page = "p-buttons";
      msg.buttons = toPublic(deck);
      msg.folder = path.map((f) => f.id).filter(Boolean);
    } else if (isHome()) {
      msg.page = "p-overview";
      msg.home = home;
    } else {
      const meta = customPages.find((p) => p.id === editing) || {};
      msg.page = "p-custom-" + editing;
      msg.custom = { id: editing, title: meta.title || "Side", cols: home.cols, rows: home.rows, items: home.items };
    }
    frame.postMessage(msg, location.origin);
  }, 120);
}
$("#preview-frame").addEventListener("load", () => setTimeout(sendPreview, 1500));

// ---------- start ----------
(async () => {
  try {
    const [d, a] = await Promise.all([api("/api/deck"), api("/api/apps")]);
    deck = d.buttons;
    builtins = d.builtins;
    apps = a;
    $("#hotkey-missing").hidden = d.hotkeys;
    $("#builtin").replaceChildren(...Object.entries(builtins).map(([n, [label]]) => Object.assign(document.createElement("option"), { value: n, textContent: label })));
    $("#special").append(...SPECIAL.map(([n, k]) => Object.assign(document.createElement("option"), { value: k, textContent: n })));
    setDirty(false);
    select(-1);
    const st = await api("/api/settings");
    for (const ext of st.extensions || []) {
      for (const w of ext.widgets || []) WIDGETS[w.type] = [`${w.name} (${ext.name})`, w.icon || "star"];
    }
    home = homeLayout = st.settings.ui.home;
    customPages = st.settings.ui.custom_pages || [];
    renderPageSelect();
    $("#grid").value = `${home.cols}x${home.rows}`;
    homeSetDirty(false);
    showTab();
  } catch (err) {
    toast("Kunne ikke hente knapperne: " + err.message, true);
  }
})();
