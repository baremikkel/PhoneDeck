"use strict";
// Lyd: volume per program, output/input device, microphone meter and push-to-talk
(() => {
let mx = null;
const act = (name, body) => PhoneDeck.action("mixer", name, body)
  .then((r) => { if (r?.error) toast(r.error); else if (r?.apps) { mx = { ...mx, ...r }; draw(true); } })
  .catch(() => {});

function el(tag, props = {}, ...kids) {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
}
function icon(name) { const i = el("i", { className: "ic" }); drawIcon(i, name); return i; }

// one row: name, mute, −, bar (tap to set), +, %
function volumeRow(n, sub) {
  const row = el("div", { className: "mix-row" + (n.muted ? " muted" : "") });
  row.dataset.id = n.id;
  const bar = el("div", { className: "mix-bar" + ((n.volume ?? 0) > 100 ? " over" : "") }, el("i"));
  bar.dataset.mxBar = "";
  bar.firstChild.style.width = Math.min(100, ((n.volume ?? 0) / (mx?.max || 150)) * 100) + "%";
  const mute = el("button", { ariaLabel: "Lyd fra/til" }, icon(n.muted ? "volOff" : "volUp"));
  mute.dataset.mxMute = "";
  const down = el("button", { ariaLabel: "Lavere" }, icon("minus"));
  down.dataset.mxStep = "-1";
  const up = el("button", { ariaLabel: "Højere" }, icon("plus"));
  up.dataset.mxStep = "1";
  row.append(el("div", { className: "nm" }, n.name, sub ? el("small", { textContent: " " + sub }) : ""),
    el("span", { className: "pct", textContent: n.volume == null ? "–" : n.volume + " %" }),
    el("div", { className: "ctl" }, mute, bar, down, up));
  return row;
}

let drawnKey = "";
function draw(force) {
  if (!mx) return;
  const key = JSON.stringify([mx.apps, mx.outputs, mx.inputs]);
  if (!force && key === drawnKey) return;
  drawnKey = key;
  $$("[data-mix-apps]").forEach((box) => {
    const apps = mx.apps || [];
    box.replaceChildren(...(apps.length ? apps.map((a) => volumeRow(a, a.media && a.media !== a.name ? a.media : ""))
      : [el("div", { className: "mix-empty", textContent: mx.error || "Ingen programmer spiller lyd lige nu" })]));
  });
  const devices = (list, sel) => $$(sel).forEach((box) => {
    const def = (list || []).find((d) => d.default);
    box.replaceChildren(
      ...(def ? [volumeRow({ ...def, name: "Lydstyrke" })] : []),
      ...(list || []).map((d) => {
        const b = el("button", { className: "mix-dev" + (d.default ? " cur" : "") },
          el("i", { className: "dot" }), el("span", { textContent: d.name }), el("b", { textContent: d.volume == null ? "" : d.volume + " %" }));
        b.dataset.mxDefault = d.id;
        return b;
      }));
  });
  devices(mx.outputs, "[data-mix-outputs]");
  devices(mx.inputs, "[data-mix-inputs]");
  const mic = (mx.inputs || []).find((d) => d.default);
  setText("mx.micstate", !mic ? "ingen mikrofon" : mx.ptt ? "taler …" : mic.muted ? "slået fra" : "tændt");
  $$("[data-mic-meter]").forEach((m) => m.classList.toggle("muted", !!mic?.muted));
}

// taps (rows are rebuilt, so listen on the document)
document.addEventListener("click", (e) => {
  const row = e.target.closest(".mix-row");
  const step = e.target.closest("[data-mx-step]");
  const mute = e.target.closest("[data-mx-mute]");
  const bar = e.target.closest("[data-mx-bar]");
  const dev = e.target.closest("[data-mx-default]");
  if (dev) { navigator.vibrate?.(10); act("default", { id: +dev.dataset.mxDefault }); return; }
  if (!row) return;
  const id = +row.dataset.id;
  navigator.vibrate?.(10);
  if (step) act("step", { id, delta: +step.dataset.mxStep * (mx?.step || 5) });
  else if (mute) act("mute", { id });
  else if (bar) {
    const r = bar.getBoundingClientRect();
    const max = mx?.max || 150;  // the bar goes to the max volume set under Indstillinger
    const v = Math.round(((e.clientX - r.left) / r.width) * max / 5) * 5;
    act("volume", { id, value: Math.max(0, Math.min(max, v)) });
  }
});

// ---------- push-to-talk: unmuted only while held (the PC re-mutes if we go quiet) ----------
let pttTimer = null;
function pttDown(e) {
  const b = e.target.closest("[data-ptt]");
  if (!b || pttTimer) return;
  e.preventDefault();
  navigator.vibrate?.(20);
  $$("[data-ptt]").forEach((x) => x.classList.add("talking"));
  act("ptt_down");
  pttTimer = setInterval(() => act("ptt_down"), 1000);
}
function pttUp() {
  if (!pttTimer) return;
  clearInterval(pttTimer);
  pttTimer = null;
  $$("[data-ptt]").forEach((x) => x.classList.remove("talking"));
  act("ptt_up");
}
document.addEventListener("pointerdown", pttDown);
["pointerup", "pointercancel"].forEach((t) => document.addEventListener(t, pttUp));
document.addEventListener("visibilitychange", () => { if (document.hidden) pttUp(); });
document.addEventListener("contextmenu", (e) => { if (e.target.closest("[data-ptt]")) e.preventDefault(); });

// ---------- microphone meter: only listens while a meter is on screen ----------
let micSource = null;
function meterVisible() {
  const cur = PhoneDeck.currentPage();
  return document.visibilityState === "visible" &&
    $$("[data-mic-meter]").some((m) => m.closest(".page")?.id === cur);
}
function updateMeter() {
  const want = meterVisible();
  if (want && !micSource) {
    micPing();
    micSource = new EventSource("/ext/mixer/miclevel");
    micSource.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d.error) { setText("mx.micstate", d.error); return; }
      $$("[data-mic-meter] i").forEach((i) => { i.style.width = d.level + "%"; });
    };
  } else if (!want && micSource) {
    micSource.close();
    micSource = null;
    $$("[data-mic-meter] i").forEach((i) => { i.style.width = "0"; });
  }
}
const micPing = () => PhoneDeck.action("mixer", "mic_keepalive").catch(() => {});
setInterval(() => { if (micSource) micPing(); }, 1500);
document.addEventListener("visibilitychange", updateMeter);

PhoneDeck.register("mixer", {
  render(ext) { mx = ext || null; draw(false); },
  page: updateMeter,
  rebuilt() { drawnKey = ""; draw(false); updateMeter(); },
});
setTimeout(updateMeter, 300);
})();
