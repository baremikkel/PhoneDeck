"use strict";
// Home Assistant on the phone: one tile per entity – tap to switch, lights get a brightness bar
(() => {
Object.assign(ICONS, {
  haBulb: P("M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"),
  haPlug: P("M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4"),
  haScene: P("M5 19l14-14M8 5l1.5 1.5M15 15l1.5 1.5M5 9h2M17 15h2M9 17v2M15 5v2"),
  haGauge: P("M12 14l4-5M4.5 17a9 9 0 1 1 15 0"),
  haFan: '<circle cx="12" cy="12" r="1.8"/>' + P("M12 10.2C12 6 13.5 3.5 16 4s2 4-4 6.2zM13.8 12c4.2 0 6.7 1.5 6.2 4s-4 2-6.2-4zM12 13.8c0 4.2-1.5 6.7-4 6.2s-2-4 4-6.2zM10.2 12C6 12 3.5 10.5 4 8s4-2 6.2 4z"),
  haShade: P("M4 4h16M5 4v10h14V4M12 14v4M10 20h4"),
});
const ICON = { light: "haBulb", switch: "haPlug", input_boolean: "haPlug", fan: "haFan", cover: "haShade",
  scene: "haScene", script: "haScene", sensor: "haGauge", binary_sensor: "haGauge", climate: "haGauge", lock: "lock", media_player: "play" };
const ON = new Set(["on", "open", "opening", "playing", "unlocked", "heat", "cool"]);
const STATE_DA = { on: "Tændt", off: "Slukket", open: "Åben", closed: "Lukket", opening: "Åbner", closing: "Lukker",
  locked: "Låst", unlocked: "Ulåst", playing: "Spiller", paused: "Pause", idle: "Ledig", unavailable: "Ikke tilgængelig",
  home: "Hjemme", not_home: "Ude", heat: "Varme", cool: "Køl" };
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };

let ha = null, key = "";
function stateText(it) {
  if (it.domain === "scene" || it.domain === "script") return "Tryk for at køre";
  if (it.domain === "climate") return `${it.temp ?? "–"}° → ${it.target ?? "–"}°`;
  if (it.domain === "light" && it.state === "on" && it.brightness != null) return `Tændt · ${it.brightness} %`;
  if (it.domain === "sensor") return `${it.state}${it.unit ? " " + it.unit : ""}`;
  return STATE_DA[it.state] || it.state;
}
function render() {
  setText("ha.status", ha?.error ? "⚠ " + ha.error : ha?.items ? `${ha.items.length} enheder` : "");
  const k = JSON.stringify(ha?.items || ha?.error || "");
  if (k === key) return;
  key = k;
  const tiles = (ha?.items || []).map((it) => {
    const on = ON.has(it.state);
    const t = el(it.tap ? "button" : "div", { className: "ha-tile" + (on ? " on" : "") + (it.state === "unavailable" ? " off-line" : "") });
    t.dataset.haId = it.id;
    if (!it.tap) t.classList.add("ro");
    const ic = el("i", { className: "ic" }); drawIcon(ic, ICON[it.domain] || "star");
    t.append(ic, el("b", { textContent: it.name }), el("small", { textContent: stateText(it) }));
    if (it.domain === "light" && on && it.brightness != null) {
      const bar = el("div", { className: "ha-dim" }, el("i"));
      bar.firstChild.style.width = it.brightness + "%";
      bar.dataset.haDim = it.id;
      t.append(bar);
    }
    return t;
  });
  const empty = el("div", { className: "ha-empty", textContent: ha?.error || "Ingen enheder" });
  $$("[data-ha-grid]").forEach((g) => g.replaceChildren(...(tiles.length ? tiles.map((x) => x.cloneNode(true)) : [empty.cloneNode(true)])));
}
document.addEventListener("click", async (e) => {
  const dim = e.target.closest("[data-ha-dim]");
  const tile = e.target.closest("button.ha-tile");
  if (!dim && !tile) return;
  navigator.vibrate?.(10);
  let r;
  if (dim) {
    const b = dim.getBoundingClientRect();
    const value = Math.max(1, Math.min(100, Math.round(((e.clientX - b.left) / b.width) * 100)));
    r = await PhoneDeck.action("home-assistant", "brightness", { id: dim.dataset.haDim, value }).catch(() => null);
  } else {
    tile.classList.toggle("on");  // feels instant; the next update confirms it
    r = await PhoneDeck.action("home-assistant", "tap", { id: tile.dataset.haId }).catch(() => null);
  }
  if (r?.error) toast(r.error);
});
PhoneDeck.register("home-assistant", {
  render(ext) { ha = ext || null; render(); },
  rebuilt() { key = ""; render(); },
});
})();
