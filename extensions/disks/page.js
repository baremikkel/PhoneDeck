"use strict";
// Diske on the phone: space per partition, and SMART health per drive
(() => {
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
const gb = (b) => b >= 1e12 ? (b / 1e12).toFixed(1) + " TB" : Math.round(b / 1e9) + " GB";
const HEALTH = { ok: "Sund", warn: "Advarsel", bad: "Fejler", unknown: "Ukendt" };
let dk = null, key = "";

function render() {
  if (!dk) return;
  const free = (dk.parts || []).reduce((s, p) => s + p.total - p.used, 0);
  setText("dk.free", dk.parts?.length ? `${gb(free)} ledigt` : "");
  const bad = (dk.drives || []).filter((d) => d.health === "warn" || d.health === "bad");
  setText("dk.summary", bad.length ? `⚠ ${bad.length} drev kræver opmærksomhed` : dk.drives?.length ? "alle sunde" : "");
  const k = JSON.stringify(dk);
  if (k === key) return;
  key = k;
  const parts = (dk.parts || []).map((p) => {
    const bar = el("div", { className: "dk-bar" }, el("i"));
    bar.firstChild.style.width = p.percent + "%";
    return el("div", { className: "dk-part" + (p.percent >= dk.warn ? " full" : "") },
      el("div", { className: "dk-line" }, el("b", { textContent: p.mount }), el("span", { textContent: `${gb(p.total - p.used)} ledigt af ${gb(p.total)}` })),
      bar, el("small", { textContent: `${p.device} · ${p.fs} · ${p.percent} % brugt` }));
  });
  $$("[data-dk-parts]").forEach((b) => b.replaceChildren(...parts.map((x) => x.cloneNode(true))));
  const drives = (dk.drives || []).map((d) => {
    const facts = [];
    if (d.temp != null) facts.push(`${d.temp} °C`);
    if (d.wear != null) facts.push(`${d.wear} % slidt`);
    if (d.spare != null) facts.push(`${d.spare} % reserve`);
    if (d.hours != null) facts.push(`${d.hours.toLocaleString("da-DK")} timer`);
    if (d.written) facts.push(`${gb(d.written)} skrevet`);
    return el("div", { className: "dk-drive " + d.health },
      el("div", { className: "dk-line" }, el("b", { textContent: d.model }), el("span", { className: "dk-badge", textContent: HEALTH[d.health] || d.health })),
      el("small", { textContent: `${d.kind || ""} · ${gb(d.size)}${facts.length ? " · " + facts.join(" · ") : ""}` }),
      d.note ? el("div", { className: "dk-note", textContent: d.note }) : "");
  });
  $$("[data-dk-drives]").forEach((b) => b.replaceChildren(...(drives.length ? drives.map((x) => x.cloneNode(true))
    : [el("div", { className: "dk-empty", textContent: "SMART er ikke tilgængelig (kræver UDisks2 på Linux eller LibreHardwareMonitor på Windows)" })])));
}
PhoneDeck.register("disks", {
  render(ext) { dk = ext || null; render(); },
  rebuilt() { key = ""; render(); },
});
})();
