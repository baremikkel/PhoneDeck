"use strict";
// FPS on the phone: a speedometer with a needle, and a graph of the last minute
(() => {
let fp = null;          // latest state from the PC
let shown = 0;          // needle position, eased towards fp.fps
let raf = 0;

const visible = (el) => el.isConnected && el.clientWidth > 0 && el.closest("section.page")?.id === PhoneDeck.currentPage();
const gauges = () => $$("canvas[data-fps-gauge]").filter(visible);
const charts = () => $$("canvas[data-fps-chart]").filter(visible);

function top() {
  if (!fp) return 144;
  if (fp.max) return fp.max;
  const hz = fp.refresh || 0;
  if (!hz) return 144;
  return [60, 75, 90, 120, 144, 165, 180, 240, 280, 360, 500].find((n) => n >= hz - 1) || 144;
}
function colour(v) {
  if (!fp || v == null) return css("--muted");
  return v < fp.low ? css("--hot") : v < fp.ok ? css("--warn") : css("--net");
}

// 270° sweep, from lower left (0) over the top to lower right (max)
const A0 = Math.PI * 0.75, SWEEP = Math.PI * 1.5;
function drawGauge(cv) {
  const [ctx, w, h] = prep(cv);
  if (!ctx) return;
  const max = top();
  const r = Math.max(10, Math.min(w / 2, h / 1.75) - 4);
  const cx = w / 2, cy = r + 4 + Math.max(0, (h - r * 1.75 - 4) / 2);
  const lw = Math.max(6, r * 0.11);
  const ang = (v) => A0 + SWEEP * Math.max(0, Math.min(1, v / max));
  const low = fp?.low ?? 30, ok = fp?.ok ?? 60;
  // track
  ctx.lineCap = "round";
  ctx.lineWidth = lw; ctx.strokeStyle = css("--line");
  ctx.beginPath(); ctx.arc(cx, cy, r - lw / 2, A0, A0 + SWEEP); ctx.stroke();
  // coloured zones (red / yellow / green) as a thin inner band
  ctx.lineCap = "butt";
  const band = Math.max(2, lw * 0.28), rb = r - lw - band;
  [[0, low, "--hot"], [low, ok, "--warn"], [ok, max, "--net"]].forEach(([a, b, c]) => {
    if (b <= a || a >= max) return;
    ctx.strokeStyle = css(c); ctx.globalAlpha = .55; ctx.lineWidth = band;
    ctx.beginPath(); ctx.arc(cx, cy, rb, ang(a), ang(Math.min(b, max))); ctx.stroke();
  });
  ctx.globalAlpha = 1;
  // the value itself as a lit arc
  if (fp?.fps != null && shown > 0.5) {
    ctx.lineCap = "round"; ctx.lineWidth = lw; ctx.strokeStyle = colour(shown);
    ctx.beginPath(); ctx.arc(cx, cy, r - lw / 2, A0, ang(shown)); ctx.stroke();
  }
  // ticks and numbers
  const step = max <= 75 ? 10 : max <= 180 ? 30 : max <= 300 ? 60 : 100;
  const font = Math.max(9, Math.min(16, r * 0.11));
  ctx.fillStyle = css("--muted"); ctx.strokeStyle = css("--muted"); ctx.lineWidth = 1.5; ctx.lineCap = "butt";
  ctx.font = `500 ${font}px system-ui, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const marks = [];
  for (let v = 0; v <= max + 0.1; v += step / 2) marks.push(v);
  if (max % (step / 2)) marks.push(max);  // e.g. 144 at the end of 0, 30 … 120
  for (const v of marks) {
    const a = ang(v), major = v === max || Math.abs(v / step - Math.round(v / step)) < 1e-6;
    if (v !== max && max - v < step * 0.45 && major) continue;  // too close to the end label
    const r1 = rb - band - 2, r2 = r1 - (major ? r * 0.09 : r * 0.05);
    ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1); ctx.lineTo(cx + Math.cos(a) * r2, cy + Math.sin(a) * r2); ctx.stroke();
    if (major && r > 60) {
      const rt = r2 - font * 0.9;
      ctx.fillText(String(Math.round(v)), cx + Math.cos(a) * rt, cy + Math.sin(a) * rt);
    }
  }
  // needle
  if (fp?.fps != null) {
    const a = ang(shown), len = r - lw - band - 4;
    ctx.strokeStyle = css("--text"); ctx.lineWidth = Math.max(2, r * 0.025); ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(cx - Math.cos(a) * r * 0.08, cy - Math.sin(a) * r * 0.08);
    ctx.lineTo(cx + Math.cos(a) * len, cy + Math.sin(a) * len); ctx.stroke();
    ctx.fillStyle = css("--text");
    ctx.beginPath(); ctx.arc(cx, cy, Math.max(4, r * 0.05), 0, Math.PI * 2); ctx.fill();
  }
}

function drawChart(cv) {
  const [ctx, w, h] = prep(cv);
  if (!ctx || !fp?.history?.length) return;
  const max = Math.max(top(), ...fp.history.filter((v) => v != null));
  const x = (i) => (i + 60 - fp.history.length) / 59 * w, y = (v) => h - (v / max) * (h - 4) - 2;
  // dashed guide lines at the red and green limits
  ctx.setLineDash([3, 4]); ctx.lineWidth = 1;
  [[fp.low, "--hot"], [fp.ok, "--net"]].forEach(([v, c]) => {
    if (v >= max) return;
    ctx.strokeStyle = css(c); ctx.globalAlpha = .5;
    ctx.beginPath(); ctx.moveTo(0, y(v)); ctx.lineTo(w, y(v)); ctx.stroke();
  });
  ctx.setLineDash([]); ctx.globalAlpha = 1;
  ctx.strokeStyle = css("--gpu"); ctx.lineWidth = 2; ctx.beginPath();
  let pen = false;
  fp.history.forEach((v, i) => {
    if (v == null) { pen = false; return; }
    if (pen) ctx.lineTo(x(i), y(v)); else { ctx.moveTo(x(i), y(v)); pen = true; }
  });
  ctx.stroke();
}

function animate() {
  raf = 0;
  const target = fp?.fps ?? 0;
  shown += (target - shown) * 0.18;
  if (Math.abs(target - shown) < 0.2) shown = target;
  gauges().forEach(drawGauge);
  if (shown !== target) raf = requestAnimationFrame(animate);
}

function render() {
  const on = fp?.fps != null;
  setText("fps.now", on ? String(Math.round(fp.fps)) : "–");
  setText("fps.unit", on ? "FPS" : fp?.status || "FPS");
  setText("fps.app", fp?.app || "");
  setText("fps.avg", fp?.avg == null ? "–" : String(Math.round(fp.avg)));
  setText("fps.min", fp?.min == null ? "–" : String(Math.round(fp.min)));
  setText("fps.hz", fp?.refresh ? String(Math.round(fp.refresh)) : "–");
  setText("fps.note", fp?.app || "");
  $$(".fps-read b").forEach((b) => { b.style.color = on ? colour(fp.fps) : ""; });
  charts().forEach(drawChart);
  if (!raf) raf = requestAnimationFrame(animate);
}

// the PC only measures while a speedometer is on screen: keep telling it
function keepAlive() {
  if (document.visibilityState === "visible" && (gauges().length || charts().length))
    PhoneDeck.action("fps", "watch").catch(() => {});
}
setInterval(keepAlive, 2000);

PhoneDeck.register("fps", {
  render(ext) { fp = ext || null; render(); },
  page() { keepAlive(); setTimeout(render, 50); },
  rebuilt() { keepAlive(); render(); },
});
})();
