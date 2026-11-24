"use strict";
// Skrivebord on the phone: night light, do-not-disturb and dark theme as big switches
(() => {
Object.assign(ICONS, {
  deskMoon: P("M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"),
  deskBell: P("M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5h4") ,
  deskBellOff: P("M6 16V11a6 6 0 0 1 9-5.2M18 11v5l1.5 2H8M10 20.5h4M4 4l16 16"),
  deskTheme: '<circle cx="12" cy="12" r="8"/>' + P("M12 4a8 8 0 0 0 0 16z", true),
});
let dk = null;
function render() {
  if (!dk) return;
  if (dk.ok === false) { setText("desk.night", "kræver GNOME"); return; }
  const set = (id, on, txt) => {
    $$(`[data-desk="${id}"]`).forEach((b) => b.classList.toggle("on", !!on));
    setText("desk." + id, txt);
  };
  set("night", dk.night, dk.night ? "Tændt" : "Slukket");
  set("dnd", dk.dnd, dk.dnd ? "Ingen notifikationer" : "Slukket");
  set("dark", dk.dark, dk.dark ? "Mørkt" : "Lyst");
  $$('[data-desk="dnd"] .ic').forEach((i) => drawIcon(i, dk.dnd ? "deskBellOff" : "deskBell"));
  // warmth: 4700 K = 0 %, 1700 K = 100 %
  const pct = dk.warmth ? Math.round(((4700 - dk.warmth) / 3000) * 100) : 0;
  $$("[data-desk-warmth] i").forEach((i) => { i.style.width = pct + "%"; });
  $$(".desk-warm").forEach((w) => w.classList.toggle("off", !dk.night));
}
document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-desk]");
  const w = e.target.closest("[data-desk-warmth]");
  if (!t && !w) return;
  navigator.vibrate?.(10);
  let r;
  if (w) {
    const b = w.getBoundingClientRect();
    r = await PhoneDeck.action("desktop", "warmth", { value: Math.round(((e.clientX - b.left) / b.width) * 100) }).catch(() => null);
  } else {
    t.classList.toggle("on");  // instant feedback; the answer confirms it
    r = await PhoneDeck.action("desktop", t.dataset.desk).catch(() => null);
  }
  if (r?.error) toast(r.error);
  else if (r) { dk = r; render(); }
});
PhoneDeck.register("desktop", {
  render(ext) { dk = ext || null; render(); },
  rebuilt() { $$(".desk-card [data-icon]").forEach((i) => drawIcon(i, i.dataset.icon)); render(); },
});
$$(".desk-card [data-icon]").forEach((i) => drawIcon(i, i.dataset.icon));
})();
