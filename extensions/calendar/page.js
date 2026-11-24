"use strict";
// Kalender on the phone: the next event with a countdown, and the agenda grouped by day
(() => {
let cal = null, listKey = "";
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
const hm = (t) => new Date(t * 1000).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
function dayName(t) {
  const d = new Date(t * 1000), today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((new Date(d).setHours(0, 0, 0, 0) - today) / 86400000);
  if (diff === 0) return "I dag";
  if (diff === 1) return "I morgen";
  const s = d.toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "short" });
  return s[0].toUpperCase() + s.slice(1);
}
function until(sec) {
  if (sec < 60) return "nu";
  const m = Math.round(sec / 60);
  if (m < 60) return `om ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `om ${h} t ${m % 60 ? (m % 60) + " m" : ""}`.trim();
  const d = Math.round(h / 24);
  return `om ${d} dag${d > 1 ? "e" : ""}`;
}

function renderNext() {
  const now = Date.now() / 1000;
  const evs = cal?.events || [];
  // the next one that hasn't started yet, or the one going on right now (not all-day)
  const ev = evs.find((e) => !e.all_day && e.end > now) || evs.find((e) => e.start > now);
  if (!ev) {
    setText("cal.nexttitle", cal?.setup ? "Sæt en kalender op under Indstillinger" : "Ingen kommende begivenheder");
    ["cal.nextin", "cal.nexttime", "cal.nextloc", "cal.nextcal"].forEach((k) => setText(k, ""));
    return;
  }
  setText("cal.nexttitle", ev.title);
  setText("cal.nextin", ev.start <= now ? `i gang · slutter ${hm(ev.end)}` : until(ev.start - now));
  setText("cal.nexttime", ev.all_day ? dayName(ev.start) : `${dayName(ev.start)} ${hm(ev.start)}–${hm(ev.end)}`);
  setText("cal.nextloc", ev.location || "");
  setText("cal.nextcal", ev.cal);
  $$(".cal-next").forEach((c) => c.style.setProperty("--accent", ev.colour));
}

function renderList() {
  const now = Date.now() / 1000;
  setText("cal.status", cal?.errors?.length ? "⚠ " + cal.errors[0] : cal?.setup ? "" : `${cal?.days || 7} dage`);
  const evs = (cal?.events || []).filter((e) => e.end > now);
  const key = JSON.stringify(evs.map((e) => [e.title, e.start, e.end])) + Math.floor(now / 60);
  if (key === listKey) return;
  listKey = key;
  const rows = [];
  let lastDay = "";
  for (const e of evs) {
    const day = dayName(Math.max(e.start, now));
    if (day !== lastDay) { rows.push(el("div", { className: "cal-day", textContent: day })); lastDay = day; }
    const row = el("div", { className: "cal-ev" + (e.start <= now ? " now" : "") });
    row.style.setProperty("--c", e.colour);
    row.append(el("span", { className: "cal-time", textContent: e.all_day ? "hele dagen" : hm(e.start) }),
      el("span", { className: "cal-title" }, e.title, e.location ? el("small", { textContent: " · " + e.location }) : ""));
    rows.push(row);
  }
  if (!rows.length) rows.push(el("div", { className: "cal-empty", textContent: cal?.setup ? "Indsæt et ICS-link under Indstillinger → Kalender" : "Ingen begivenheder" }));
  $$("[data-cal-list]").forEach((box) => box.replaceChildren(...rows.map((r) => r.cloneNode(true))));
}

PhoneDeck.register("calendar", {
  render(ext) { cal = ext || null; renderNext(); renderList(); },
  rebuilt() { listKey = ""; renderList(); renderNext(); },
});
})();
