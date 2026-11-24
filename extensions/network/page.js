"use strict";
// Netværk on the phone: ping with a small graph, addresses, VPN switches
(() => {
let nw = null, vpnKey = "";
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };

function drawPing() {
  $$("canvas[data-nw-chart]").forEach((cv) => {
    const [ctx, w, h] = prep(cv);
    if (!ctx || !nw?.history?.length) return;
    const vals = nw.history, ok = vals.filter((v) => v != null);
    const max = Math.max(20, ...ok) * 1.15;
    const x = (i) => (i / Math.max(1, 59)) * w, y = (v) => h - (v / max) * (h - 4) - 2;
    ctx.strokeStyle = css("--net"); ctx.lineWidth = 2; ctx.beginPath();
    let pen = false;
    vals.forEach((v, i) => {
      const xi = x(i + 60 - vals.length);
      if (v == null) { // lost packet: a red tick
        ctx.save(); ctx.fillStyle = css("--hot"); ctx.fillRect(xi - 1.5, 0, 3, h); ctx.restore(); pen = false; return;
      }
      if (pen) ctx.lineTo(xi, y(v)); else { ctx.moveTo(xi, y(v)); pen = true; }
    });
    ctx.stroke();
  });
}

function render() {
  if (!nw) return;
  const p = nw.ping;
  setText("nw.ping", p == null ? "—" : p < 10 ? p.toFixed(1) : String(Math.round(p)));
  setText("nw.avg", nw.avg == null ? "–" : String(Math.round(nw.avg)));
  setText("nw.loss", nw.loss == null ? "–" : String(nw.loss));
  setText("nw.host", p == null && nw.history?.length ? `⚠ intet svar fra ${nw.host}` : nw.host);
  setText("nw.iface", nw.iface ? `Lokal · ${nw.iface}` : "Lokal");
  setText("nw.ip", nw.ip || "ikke forbundet");
  setText("nw.public", nw.public || "–");
  $$(".nw-ping").forEach((c) => c.style.setProperty("--accent", p == null ? "var(--hot)" : p > 80 ? "var(--warn)" : "var(--net)"));
  drawPing();
  const key = JSON.stringify(nw.vpns);
  if (key === vpnKey) return;
  vpnKey = key;
  const rows = (nw.vpns || []).map((v) => {
    const b = el("button", { className: "nw-vpn-row" + (v.on ? " on" : "") },
      el("span", { className: "nw-dot" }), el("b", { textContent: v.name }),
      el("small", { textContent: v.on ? `${v.kind} · forbundet${v.ip ? " · " + v.ip : ""}` : `${v.kind} · afbrudt` }));
    b.dataset.nwVpn = v.id;
    return b;
  });
  $$("[data-nw-vpns]").forEach((box) => box.replaceChildren(...(rows.length ? rows.map((r) => r.cloneNode(true))
    : [el("div", { className: "nw-empty", textContent: "Ingen VPN fundet (Tailscale, WireGuard eller VPN i NetworkManager)" })])));
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-nw-vpn]");
  if (!b) return;
  navigator.vibrate?.(10);
  b.classList.add("busy");
  const r = await PhoneDeck.action("network", "vpn", { id: b.dataset.nwVpn }).catch(() => null);
  b.classList.remove("busy");
  if (r?.error) toast(r.error, 3500);
  else if (r?.vpns) { nw.vpns = r.vpns; vpnKey = ""; render(); }
});

PhoneDeck.register("network", {
  render(ext) { nw = ext || null; render(); },
  rebuilt() { vpnKey = ""; render(); },
});
})();
