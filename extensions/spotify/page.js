"use strict";
// Spotify on the phone: next song bar, a sheet with Kø / Søg / Playlister, and ❤ for the current song
(() => {
let spLast = null;
const act = (name, body) => PhoneDeck.action("spotify", name, body);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
const icon = (name) => { const i = el("i", { className: "ic" }); drawIcon(i, name); return i; };

// next-song bar and ❤ on the music page (if the music extension is installed)
const musicPage = $("#p-music");
if (musicPage) {
  const t = document.createElement("template");
  t.innerHTML = `<button class="card next-bar" data-queue-open>
        <img data-next-art alt="" hidden>
        <span class="next-txt"><small data-b="q.lbl">Næste</small><span data-b="q.next">–</span></span>
        <i class="ic" data-icon="queue"></i>
      </button>`;
  musicPage.prepend(t.content.firstElementChild);
  const controls = $(".big-media .controls", musicPage);
  if (controls) {
    const like = el("button", { className: "sp-like", ariaLabel: "Like sangen (Spotify)", hidden: true }, icon("heart"));
    like.dataset.spLike = "";
    controls.append(like);
  }
}
document.body.append(el("div", { id: "queue", className: "sheet", hidden: true }));
$("#queue").innerHTML = `
    <div class="sheet-card sp-sheet">
      <header>
        <nav class="sp-tabs">
          <button data-sp-tab="queue" class="cur"><i class="ic" data-icon="queue"></i>Kø</button>
          <button data-sp-tab="search"><i class="ic" data-icon="search"></i>Søg</button>
          <button data-sp-tab="playlists"><i class="ic" data-icon="list"></i>Playlister</button>
        </nav>
        <span class="sub grow right" data-b="q.count"></span>
        <button class="mini" data-queue-close aria-label="Luk"><i class="ic" data-icon="close"></i></button>
      </header>
      <div class="sp-reconnect" hidden>Forbind Spotify igen under Indstillinger for at kunne like, se playlister og tilføje til kø.</div>
      <ol class="queue-list" data-sp-panel="queue" data-queue></ol>
      <div class="sp-panel" data-sp-panel="search" hidden>
        <input type="search" class="sp-q" placeholder="Søg efter en sang …" enterkeyhint="search" autocomplete="off">
        <ol class="queue-list" data-sp-results></ol>
      </div>
      <ol class="queue-list" data-sp-panel="playlists" data-sp-playlists hidden></ol>
    </div>`;  // static markup
$$("#queue [data-icon]").forEach((i) => drawIcon(i, i.dataset.icon));

function trackRow(t, i, extra) {
  const art = t.art ? el("img", { src: t.art, alt: "", loading: "lazy" }) : el("span", { className: "noimg" });
  const txt = el("div", { className: "t" }, el("b", { textContent: t.title || t.name || "" }),
    el("span", { textContent: t.artist ?? (t.owner ? `${t.owner}${t.count != null ? " · " + t.count + " sange" : ""}` : "") }));
  return el("li", {}, el("small", { textContent: i == null ? "" : String(i + 1) }), art, txt, extra);
}

// ---------- next song + queue ----------
let queueKey = "";
function renderSpotify(sp) {
  const img = $("img[data-next-art]");
  const like = $("[data-sp-like]");
  $(".sp-reconnect").hidden = !(sp?.connected && sp.reconnect);
  if (!sp || !sp.connected) {
    setText("q.lbl", "Næste sang");
    setText("q.next", sp?.configured ? "Tryk for at forbinde Spotify på computeren"
      : "Tryk for at sætte Spotify-køen op på computeren");
    if (img) img.hidden = true;
    if (like) like.hidden = true;
    return;
  }
  if (like) {
    like.hidden = !(sp.current?.uri || "").startsWith("spotify:track:");
    like.classList.toggle("liked", !!sp.liked);
    drawIcon(like.querySelector(".ic"), sp.liked ? "heartFill" : "heart");
  }
  const n = sp.next;
  setText("q.lbl", `Næste · ${sp.queue?.length || 0} i kø`);
  setText("q.next", n ? `${n.title} – ${n.artist}` : "Køen er tom");
  if (img) { if (n?.art) { if (img.getAttribute("src") !== n.art) img.src = n.art; img.hidden = false; } else img.hidden = true; }
  setText("q.count", tab === "queue" ? `${sp.queue?.length || 0} sange` : "");
  const key = JSON.stringify(sp.queue);
  if (key === queueKey) return;
  queueKey = key;
  $("[data-queue]").replaceChildren(...(sp.queue || []).map((t, i) =>
    trackRow(t, i, el("small", { textContent: fmtTime(t.duration) }))));
}

// ---------- tabs ----------
let tab = "queue";
function showTab(name) {
  tab = name;
  $$("[data-sp-tab]").forEach((b) => b.classList.toggle("cur", b.dataset.spTab === name));
  $$("[data-sp-panel]").forEach((p) => { p.hidden = p.dataset.spPanel !== name; });
  setText("q.count", name === "queue" ? `${spLast?.queue?.length || 0} sange` : "");
  if (name === "playlists") loadPlaylists();
  if (name === "search") setTimeout(() => $(".sp-q").focus(), 50);
}

// ---------- search ----------
let searchTimer, searchSeq = 0;
$(".sp-q").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => search(e.target.value), 400);
});
$(".sp-q").addEventListener("keydown", (e) => { if (e.key === "Enter") { clearTimeout(searchTimer); search(e.target.value); e.target.blur(); } });
async function search(q) {
  const seq = ++searchSeq;
  const box = $("[data-sp-results]");
  if (!q.trim()) { box.replaceChildren(); return; }
  try {
    const r = await act("search", { q });
    if (seq !== searchSeq) return;  // an older search answered late
    if (r.error) { box.replaceChildren(el("li", { className: "sp-msg", textContent: r.error })); return; }
    box.replaceChildren(...(r.tracks || []).map((t) => {
      const add = el("button", { className: "sp-add", ariaLabel: "Tilføj til kø" }, icon("plus"));
      add.dataset.spQueue = t.uri;
      return trackRow(t, null, add);
    }));
    if (!r.tracks?.length) box.replaceChildren(el("li", { className: "sp-msg", textContent: "Ingen resultater" }));
  } catch { /* offline */ }
}

// ---------- playlists ----------
let playlistsLoaded = 0;
async function loadPlaylists() {
  if (Date.now() - playlistsLoaded < 60_000) return;
  const box = $("[data-sp-playlists]");
  box.replaceChildren(el("li", { className: "sp-msg", textContent: "Henter …" }));
  try {
    const r = await act("playlists");
    if (r.error) { box.replaceChildren(el("li", { className: "sp-msg", textContent: r.error })); return; }
    playlistsLoaded = Date.now();
    box.replaceChildren(...(r.playlists || []).map((p) => {
      const play = el("button", { className: "sp-add", ariaLabel: "Afspil" }, icon("play"));
      play.dataset.spPlay = p.uri;
      return trackRow(p, null, play);
    }));
  } catch { /* offline */ }
}

// ---------- taps ----------
document.addEventListener("click", async (e) => {
  const t = e.target;
  if (t.closest("[data-queue-open]")) {
    if (!spLast?.connected) { api("/api/action", { action: "open.settings" }).catch(() => {}); return; }
    $("#queue").hidden = false;
    return;
  }
  if (t.closest("[data-queue-close]") || t.id === "queue") { $("#queue").hidden = true; return; }
  const tabBtn = t.closest("[data-sp-tab]");
  if (tabBtn) { showTab(tabBtn.dataset.spTab); return; }
  const like = t.closest("[data-sp-like]");
  const q = t.closest("[data-sp-queue]");
  const play = t.closest("[data-sp-play]");
  if (!like && !q && !play) return;
  navigator.vibrate?.(10);
  try {
    const r = like ? await act("like") : q ? await act("queue_add", { uri: q.dataset.spQueue })
      : await act("play", { uri: play.dataset.spPlay });
    if (r.error) { toast(r.error, 3500); return; }
    if (like) {
      like.classList.toggle("liked", r.liked);
      drawIcon(like.querySelector(".ic"), r.liked ? "heartFill" : "heart");
      toast(r.liked ? "Tilføjet til Liked Songs" : "Fjernet fra Liked Songs");
    } else if (q) {
      q.classList.add("done");
      drawIcon(q.querySelector(".ic"), "check");
      toast("Tilføjet til køen");
    } else {
      toast("Afspiller playlisten");
      $("#queue").hidden = true;
    }
  } catch { toast("Kunne ikke nå PC'en"); }
});

PhoneDeck.register("spotify", {
  render(ext) {
    spLast = ext;
    renderSpotify(ext);
  },
});
})();
