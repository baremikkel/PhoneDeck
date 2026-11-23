"use strict";
// Phone-side code for this extension (loaded by web/app.js)
(() => {
let media = { pos: 0, len: 0, playing: false, at: 0 };

let artKey;
function renderMedia(m) {
  if (!m || m.error || !m.title) {
    setText("m.title", m?.error ? "Medie: " + m.error : "Intet afspilles");
    ["m.artist", "m.album", "m.player", "m.pos", "m.len"].forEach((k) => setText(k, ""));
    setWidth("m.progress", 0);
    setIcon("m.play", "play");
    if (artKey !== null) { $$("img[data-art]").forEach((i) => i.removeAttribute("src")); artKey = null; }
    media.playing = false; media.len = 0;
    return;
  }
  setText("m.player", m.player);
  setText("m.title", m.title);
  setText("m.artist", m.artist || "");
  setText("m.album", m.album || "");
  setIcon("m.play", m.status === "Playing" ? "pause" : "play");
  if (m.art_key !== artKey) {
    artKey = m.art_key;
    $$("img[data-art]").forEach((img) => {
      if (m.art) img.src = "/ext/music/art?k=" + encodeURIComponent(m.art_key || "");
      else img.removeAttribute("src");
    });
  }
  media = { pos: m.position, len: m.length, playing: m.status === "Playing", at: performance.now() };
  tickMedia();
}

function tickMedia() {
  if (!media.len) return;
  const pos = Math.min(media.len, media.pos + (media.playing ? (performance.now() - media.at) / 1000 : 0));
  setText("m.pos", fmtTime(pos));
  setText("m.len", fmtTime(media.len));
  setWidth("m.progress", (pos / media.len) * 100);
}

// volume of the player itself (MPRIS) – not the whole computer
function renderVolume(m) {
  const v = m?.volume;
  setText("mv.txt", v == null ? "–" : v + " %");
  setWidth("mv.pct", v ?? 0);
}

// ---------- visualizer ----------
// Only listens while it is switched on AND the music page is on screen.
let vizSource = null;
const vizCanvas = $("canvas[data-viz]");

function drawViz(levels) {
  const [ctx, w, h] = prep(vizCanvas);
  if (!ctx) return;
  const n = levels.length, gap = 4, bw = (w - gap * (n - 1)) / n;
  const g = ctx.createLinearGradient(0, h, 0, 0);
  g.addColorStop(0, css("--media"));
  g.addColorStop(1, css("--media") + "10");
  ctx.fillStyle = g;
  levels.forEach((v, i) => {
    const bh = Math.max(2, (v / 100) * h * 0.7);
    ctx.beginPath();
    ctx.roundRect(i * (bw + gap), h - bh, bw, bh, [Math.min(4, bw / 2), Math.min(4, bw / 2), 0, 0]);
    ctx.fill();
  });
}

function updateViz() {
  const want = prefs.viz && PhoneDeck.currentPage() === "p-music" && document.visibilityState === "visible";
  $$("[data-viz-toggle]").forEach((b) => b.classList.toggle("on", !!prefs.viz));
  vizCanvas.hidden = !prefs.viz;
  if (want && !vizSource) {
    vizPing();  // the PC only listens while this page keeps pinging
    vizSource = new EventSource("/ext/music/spectrum");
    vizSource.onmessage = (e) => drawViz(JSON.parse(e.data));
  } else if (!want && vizSource) {
    vizSource.close();
    vizSource = null;
    drawViz(new Array(36).fill(0));
  }
}
const vizPing = () => PhoneDeck.action("music", "viz_keepalive").catch(() => {});
setInterval(() => { if (vizSource) vizPing(); }, 1500);
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-viz-toggle]")) return;
  prefs.viz = !prefs.viz;
  savePrefs();
  updateViz();
});
setTimeout(updateViz, 300);
document.addEventListener("visibilitychange", updateViz);

PhoneDeck.register("music", {
  render(ext) { renderMedia(ext?.media); renderVolume(ext?.media); },
  tick: tickMedia,
  rebuilt() { artKey = undefined; },  // new <img> elements on the home page need the cover again
  page: updateViz,
  widgets: {
    media: `<div class="card media">
    <div class="art"><img data-art alt=""><div class="noart">♪</div></div>
    <div class="info"><div class="title" data-b="m.title">Intet afspilles</div><div class="artist" data-b="m.artist"></div>
      <div class="progress"><i data-w="m.progress"></i></div>
      <div class="controls"><button data-action="media.previous" aria-label="Forrige"><i class="ic" data-icon="prev"></i></button>
        <button data-action="media.playpause" class="primary" aria-label="Afspil/pause"><i class="ic" data-icon="play" data-ib="m.play"></i></button>
        <button data-action="media.next" aria-label="Næste"><i class="ic" data-icon="next"></i></button></div></div></div>`,
  },
});
})();
