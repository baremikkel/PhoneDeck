"use strict";
// Udklip og skærmbilleder on the phone
(() => {
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
let cb = null, clipKey = "", shotKey = "";
function ago(t) {
  const s = Date.now() / 1000 - t;
  if (s < 60) return "lige nu";
  if (s < 3600) return `${Math.round(s / 60)} min`;
  if (s < 86400) return `${Math.round(s / 3600)} t`;
  return new Date(t * 1000).toLocaleDateString("da-DK", { day: "numeric", month: "short" });
}

// full-size viewer for a screenshot
document.body.append(el("div", { id: "shot-view", className: "sheet", hidden: true }));
$("#shot-view").innerHTML = `<div class="sheet-card shot-sheet">
  <header><span class="label" data-b="clip.shotname"></span>
    <button class="mini" data-shot-act="shot_copy">Kopiér</button><button class="mini" data-shot-act="shot_open">Åbn på PC</button>
    <button class="mini" data-shot-close aria-label="Luk"><i class="ic" data-icon="close"></i></button></header>
  <img class="shot-big" alt=""></div>`;  // static markup
$$("#shot-view [data-icon]").forEach((i) => drawIcon(i, i.dataset.icon));

function render() {
  const hist = cb?.history;
  const ck = JSON.stringify(hist) + Math.floor(Date.now() / 60000);
  if (ck !== clipKey) {
    clipKey = ck;
    const rows = hist == null
      ? [el("div", { className: "clip-empty", textContent: "Udklipshistorikken er slået fra (Indstillinger → Udklip)" })]
      : !cb.clip_ok ? [el("div", { className: "clip-empty", textContent: "Installer wl-clipboard (Wayland) eller xclip (X11)" })]
      : hist.length ? hist.map((i) => {
        const b = el("button", { className: "clip-row" }, el("span", { className: "clip-text", textContent: i.text.replace(/\s+/g, " ") + (i.long ? " …" : "") }),
          el("small", { textContent: ago(i.at) }));
        b.dataset.clipId = i.id;
        return b;
      }) : [el("div", { className: "clip-empty", textContent: "Kopiér noget på PC'en, så dukker det op her" })];
    $$("[data-clip-list]").forEach((box) => box.replaceChildren(...rows.map((r) => r.cloneNode(true))));
  }
  const shots = cb?.shots || [];
  setText("clip.shots", shots.length ? `${shots.length} nyeste` : "");
  const sk = JSON.stringify(shots.map((s) => s.name));
  if (sk === shotKey) return;
  shotKey = sk;
  const tiles = shots.map((s) => {
    const b = el("button", { className: "shot" }, el("img", { src: "/ext/clipboard/shot?name=" + encodeURIComponent(s.name), alt: "", loading: "lazy" }),
      el("small", { textContent: ago(s.at) }));
    b.dataset.shot = s.name;
    return b;
  });
  $$("[data-shot-grid]").forEach((g) => g.replaceChildren(...(tiles.length ? tiles.map((t) => t.cloneNode(true))
    : [el("div", { className: "clip-empty", textContent: "Ingen skærmbilleder fundet" })])));
}

let shown = null;
document.addEventListener("click", async (e) => {
  const row = e.target.closest("[data-clip-id]");
  const shot = e.target.closest("[data-shot]");
  const act = e.target.closest("[data-shot-act]");
  if (e.target.closest("[data-shot-close]") || e.target.id === "shot-view") { $("#shot-view").hidden = true; return; }
  if (shot) {
    shown = shot.dataset.shot;
    $("#shot-view .shot-big").src = "/ext/clipboard/shot?name=" + encodeURIComponent(shown);
    setText("clip.shotname", shown.replace(/\.(png|jpe?g|webp)$/i, ""));
    $("#shot-view").hidden = false;
    return;
  }
  if (!row && !act) return;
  navigator.vibrate?.(10);
  const r = row ? await PhoneDeck.action("clipboard", "copy", { id: row.dataset.clipId }).catch(() => null)
    : await PhoneDeck.action("clipboard", act.dataset.shotAct, { name: shown }).catch(() => null);
  if (r?.error) toast(r.error, 3000);
  else toast(row ? "Kopieret på PC'en" : act.dataset.shotAct === "shot_copy" ? "Billedet er kopieret på PC'en" : "Åbnet på PC'en");
});

PhoneDeck.register("clipboard", {
  render(ext) { cb = ext || null; render(); },
  rebuilt() { clipKey = shotKey = ""; render(); },
});
})();
