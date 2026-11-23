"use strict";
// Phone-side code for this extension (loaded by web/app.js)
(() => {
let spLast = null;

// add the next-song bar to the music page (if the music extension is installed)
// and the queue sheet to the page
const musicPage = $("#p-music");
if (musicPage) {
  const t = document.createElement("template");
  t.innerHTML = `<button class="card next-bar" data-queue-open>
        <img data-next-art alt="" hidden>
        <span class="next-txt"><small data-b="q.lbl">Næste</small><span data-b="q.next">–</span></span>
        <i class="ic" data-icon="queue"></i>
      </button>`;
  musicPage.prepend(t.content.firstElementChild);
}
{
  const t = document.createElement("template");
  t.innerHTML = `<div id="queue" class="sheet" hidden>
    <div class="sheet-card">
      <header><span class="label">Kø</span><span class="sub grow right" data-b="q.count"></span><button class="mini" data-queue-close aria-label="Luk"><i class="ic" data-icon="close"></i></button></header>
      <ol class="queue-list" data-queue></ol>
    </div>
  </div>`;
  document.body.append(t.content.firstElementChild);
}

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
    if (!spLast?.connected) { api("/api/action", { action: "open.settings" }).catch(() => {}); return; }
    $("#queue").hidden = false;
  } else if (e.target.closest("[data-queue-close]") || e.target.id === "queue") {
    $("#queue").hidden = true;
  }
});

PhoneDeck.register("spotify", {
  render(ext) {
    spLast = ext;
    if ($("img[data-next-art]")) renderSpotify(ext);
  },
});
})();
