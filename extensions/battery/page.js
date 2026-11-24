"use strict";
// Batterier on the phone: one row per device (and the phone itself), low ones in red
(() => {
Object.assign(ICONS, {
  batHeadset: P("M4 15v-3a8 8 0 0 1 16 0v3") + '<rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
  batMouse: '<rect x="6" y="3" width="12" height="18" rx="6"/>' + P("M12 3v6"),
  batPad: P("M7 8h10a5 5 0 0 1 4.8 6.3l-.8 3a2.5 2.5 0 0 1-4.4.8L15 16H9l-1.6 2.1a2.5 2.5 0 0 1-4.4-.8l-.8-3A5 5 0 0 1 7 8z") + P("M8 11v3M6.5 12.5h3M15.5 12h.01M17.5 13.5h.01"),
  batPhone: '<rect x="7" y="2.5" width="10" height="19" rx="2"/>' + P("M11 18.5h2"),
  batCell: '<rect x="3" y="7" width="16" height="10" rx="2"/>' + P("M21 10.5v3"),
});
const ICON = { headset: "batHeadset", mouse: "batMouse", keyboard: "keyboard", gamepad: "batPad", phone: "batPhone", battery: "batCell" };
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };

let bat = null, phone = null, key = "";
navigator.getBattery?.().then((b) => {
  const upd = () => { phone = { id: "phone", name: "Denne telefon", kind: "Telefon", icon: "phone",
    percent: Math.round(b.level * 100), state: b.charging ? "charging" : "discharging" }; render(); };
  ["levelchange", "chargingchange"].forEach((ev) => b.addEventListener(ev, upd));
  upd();
}).catch(() => {});

function render() {
  const warn = bat?.warn ?? 20;
  const list = [...(bat?.devices || []), ...(phone ? [phone] : [])];
  const low = list.filter((d) => d.percent <= warn && d.state !== "charging");
  setText("bat.low", low.length ? `⚠ ${low.map((d) => d.name).join(", ")} er ved at løbe tør` : "");
  const k = JSON.stringify([list, warn]);
  if (k === key) return;
  key = k;
  const rows = list.map((d) => {
    const ic = el("i", { className: "ic" }); drawIcon(ic, ICON[d.icon] || "batCell");
    const bar = el("div", { className: "bat-bar" }, el("i"));
    bar.firstChild.style.width = d.percent + "%";
    const row = el("div", { className: "bat-row" + (d.percent <= warn && d.state !== "charging" ? " low" : "") + (d.state === "charging" ? " charging" : "") },
      ic, el("div", { className: "bat-name" }, el("b", { textContent: d.name }), el("small", { textContent: d.kind + (d.state === "charging" ? " · lader" : "") })),
      el("span", { className: "bat-pct", textContent: (d.approx ? "~" : "") + d.percent + " %" }), bar);
    return row;
  });
  $$("[data-bat-list]").forEach((box) => box.replaceChildren(...(rows.length ? rows.map((r) => r.cloneNode(true))
    : [el("div", { className: "bat-empty", textContent: "Ingen enheder med batteri er forbundet" })])));
}
PhoneDeck.register("battery", {
  render(ext) { bat = ext || null; render(); },
  rebuilt() { key = ""; render(); },
});
})();
