"use strict";
// Phone-side code for this extension (loaded by web/app.js)
(() => {
let claudeLast = null;
let heatKey = "";

// ---------- Claude: donut with what is left of your own limits ----------
const clock = (iso) => iso ? new Date(iso).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }) : "";
const weekday = (iso) => iso ? new Date(iso).toLocaleDateString("da-DK", { weekday: "short" }) + " " + clock(iso) : "";

function renderDonut(c, budget, plan) {
  const used5 = c.block_used || 0;
  const usedW = c.last7d ? c.last7d.input + c.last7d.output + c.last7d.cache_write : 0;
  let rem5 = null, remW = null;
  const p5 = plan?.five_hour, pW = plan?.seven_day;
  if (p5) {
    // real numbers from the Claude plan (opt-in, via the Claude Code login)
    rem5 = Math.max(0, 1 - p5.used_pct / 100);
    remW = pW ? Math.max(0, 1 - pW.used_pct / 100) : null;
    setText("c.left", `${Math.round(rem5 * 100)} %`);
    setText("c.leftlbl", "tilbage");
    setText("c.fivetxt", `5 timer · ↻ ${clock(p5.resets_at)}`);
    // rough token estimate: what this computer used so far ÷ share of the limit used
    const est = p5.used_pct >= 3 ? used5 / (p5.used_pct / 100) : null;
    setText("c.blockof", est ? `≈ ${fmtTok(est - used5)} tilbage` : "tokens");
    if (pW) setText("c.weektxt", `uge ${Math.round(remW * 100)} % tilbage · ↻ ${weekday(pW.resets_at)}`);
  } else if (budget.budget_5h) {
    const b5 = budget.budget_5h;
    rem5 = Math.max(0, 1 - used5 / b5);
    setText("c.left", fmtTok(Math.max(0, b5 - used5)));
    setText("c.leftlbl", `tilbage · ${Math.round(rem5 * 100)} %`);
    setText("c.blockof", `/ ${fmtTok(b5)}`);
  } else {
    setText("c.left", "–");
    setText("c.leftlbl", plan?.error || "tryk: sæt grænse");
    setText("c.blockof", "tokens");
  }
  if (!p5 && budget.budget_week) {
    remW = Math.max(0, 1 - usedW / budget.budget_week);
    setText("c.weektxt", `uge ${Math.round(remW * 100)} % tilbage`);
  }
  // "Brugt"-mode (Indstillinger → Claude): show what is used instead of what is left
  const showUsed = budget.donut_mode === "used";
  if (showUsed && rem5 != null) {
    const usedPct = Math.round((1 - rem5) * 100);
    if (p5) {
      setText("c.left", `${usedPct} %`);
      setText("c.leftlbl", "brugt");
    } else {
      setText("c.left", fmtTok(used5));
      setText("c.leftlbl", `brugt · ${usedPct} %`);
    }
  }
  // Limit used up: the centre counts down to when new tokens arrive
  const resetIn = (iso, secs) => iso ? (new Date(iso) - Date.now()) / 1000 : secs;
  let blocked = null;
  if (rem5 != null && rem5 <= 0.001) blocked = resetIn(p5?.resets_at, c.block_reset_in);
  if (remW != null && remW <= 0.001) blocked = Math.max(blocked ?? 0, resetIn(pW?.resets_at, null) ?? 0);
  if (blocked != null && blocked > 0) {
    const h = Math.floor(blocked / 3600), m = Math.floor((blocked % 3600) / 60), sec = Math.floor(blocked % 60);
    setText("c.left", h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`);
    setText("c.leftlbl", "til nye tokens");
  }
  if (showUsed && remW != null) {
    const reset = pW ? ` · ↻ ${weekday(pW.resets_at)}` : "";
    setText("c.weektxt", `uge ${Math.round((1 - remW) * 100)} % brugt${reset}`);
  }
  $$("[data-week-legend]").forEach((el) => { el.hidden = remW == null; });
  $$("canvas[data-donut]").forEach((cv) => {
    const [ctx, w, h] = prep(cv);
    if (!ctx) return;
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 2;
    const ring = (r, width, frac, color) => {
      ctx.lineCap = "round";
      ctx.lineWidth = width;
      ctx.strokeStyle = css("--line");
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      if (frac == null) return;
      // remaining share, drawn clockwise from 12 o'clock
      const f = Math.max(0, Math.min(1, frac));
      if (f <= 0) return;
      ctx.strokeStyle = color;
      ctx.beginPath(); ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + f * Math.PI * 2); ctx.stroke();
    };
    const t = Math.max(6, R * 0.16);
    const remaining5 = rem5;
    const colour5 = remaining5 != null && remaining5 < 0.15 ? css("--hot")
      : remaining5 != null && remaining5 < 0.35 ? css("--warn") : css("--claude");
    // the colour always follows what is left; only the filled part flips
    const fill = (rem) => (rem == null ? null : showUsed ? 1 - rem : rem);
    ring(R - t / 2, t, fill(remaining5), colour5);
    if (remW != null) ring(R - t * 1.9, t * 0.55, fill(remW), css("--ram"));
  });
}
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-donut-wrap]") || claudeLast?.settings?.budget_5h || claudeLast?.plan?.five_hour) return;
  api("/api/action", { action: "open.settings" }).catch(() => {});
});

function renderClaude(c) {
  if (!c.available) { setText("c.block", "–"); setText("c.reset", c.error || "ingen data"); return; }
  const sum = (b) => b ? b.input + b.output + b.cache_write : null;
  setText("c.block", fmtTok(c.block_used ?? sum(c.last5h)));
  setText("c.today", fmtTok(sum(c.today)));
  setText("c.week", fmtTok(sum(c.last7d)));
  setText("c.out", fmtTok(c.today?.output));
  setText("c.msgs", (c.today?.messages ?? 0) + " svar");
  setText("c.b.in", fmtTok(c.last5h?.input));
  setText("c.b.out", fmtTok(c.last5h?.output));
  setText("c.b.cw", fmtTok(c.last5h?.cache_write));
  setText("c.b.cr", fmtTok(c.last5h?.cache_read));
  setText("c.reset", c.block_reset_in ? "↻ " + fmtDur(c.block_reset_in) : "intet aktivt vindue");
  setText("c.resetlong", c.block_reset_in ? "Vinduet nulstilles om " + fmtDur(c.block_reset_in) : "Intet aktivt vindue");

  const models = Object.entries(c.models || {});
  const total = models.reduce((a, [, v]) => a + v, 0) || 1;
  const key = JSON.stringify(models);
  $$("[data-models]").forEach((box) => {
    if (box.dataset.key === key) return;
    box.dataset.key = key;
    box.replaceChildren(...models.slice(0, 4).map(([name, v]) => {
      const row = document.createElement("div");
      const n = document.createElement("span"); n.textContent = name;
      const t = document.createElement("span"); t.textContent = fmtTok(v);
      const bar = document.createElement("div"); bar.className = "bar";
      const fill = document.createElement("i"); fill.style.width = (v / total) * 100 + "%";
      bar.append(fill); row.append(n, t, bar);
      return row;
    }));
  });
}

function drawClaude(ext) {
  $$('canvas[data-chart="claude"]').forEach((c) => {
    const [ctx, w, h] = prep(c);
    if (ctx) bars(ctx, w, h, ext?.usage?.hourly || [], css("--claude"));
  });
  const cd = ext?.usage?.daily;
  if (!cd) return;
  setText("ch.total", fmtTok(cd.total));
  setText("ch.active", String(cd.active_days));
  setText("ch.streak", String(cd.streak));
  const key = JSON.stringify([cd.counts, layoutGen, window.innerWidth, window.innerHeight]);
  if (key === heatKey) return;
  heatKey = key;
  $$('canvas[data-heat="claude"]').forEach((c) =>
    heatmap(c, cd.start, quartileLevels(cd.counts), css("--claude"), { counts: cd.counts, unit: "tokens" }));
}

PhoneDeck.register("claude-code", {
  render(ext) {
    claudeLast = ext || {};
    const usage = claudeLast.usage || {};
    renderClaude(usage);
    renderDonut(usage, claudeLast.settings || {}, claudeLast.plan);
    drawClaude(claudeLast);
  },
  widgets: {
    claude: `<div class="card" style="--accent: var(--claude)">
    <header><span class="label">Claude</span><span class="sub" data-b="c.reset"></span></header>
    <div class="big"><span data-b="c.block">–</span><small>tokens · 5 t</small></div>
    <div class="facts grid2" data-opt="facts" data-opt-name="I dag / 7 dage"><div><span data-b="c.today">–</span><small>i dag</small></div><div><span data-b="c.week">–</span><small>7 dage</small></div></div>
    <canvas class="bars" data-chart="claude" data-opt="graph" data-opt-name="Graf"></canvas></div>`,
    donut: `<div class="card donut-card" style="--accent: var(--claude)">
    <div class="donut" data-donut-wrap><canvas data-donut></canvas>
      <div class="donut-center"><b data-b="c.left">–</b><small data-b="c.leftlbl">tilbage</small></div></div>
    <div class="sub center" data-b="c.fivetxt" data-opt="caption" data-opt-name="Tekst under">Claude · 5 timer</div></div>`,
  },
});
})();
