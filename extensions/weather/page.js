"use strict";
// Vejr on the phone: now, the next 24 hours (temperature line + rain bars) and 7 days
(() => {
// weather icons (line style like the rest of PhoneDeck)
const SUN = '<circle cx="12" cy="12" r="4"/>' + P("M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4");
const CLOUD = P("M7 18h10a4 4 0 0 0 .6-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 18z");
Object.assign(ICONS, {
  wxSun: SUN,
  wxMoon: P("M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"),
  wxPartly: '<circle cx="8.5" cy="8.5" r="3"/>' + P("M8.5 2.5v1.2M2.5 8.5h1.2M4.3 4.3l.9.9M12.7 4.3l-.9.9") + P("M9 20h8.5a3.3 3.3 0 0 0 .5-6.6 4.6 4.6 0 0 0-8.8 1.2A2.7 2.7 0 0 0 9 20z"),
  wxCloud: CLOUD,
  wxFog: P("M4 9h16M3 13h18M5 17h14"),
  wxRain: P("M7 15h10a4 4 0 0 0 .6-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 15z") + P("M8 18l-1 3M12 18l-1 3M16 18l-1 3"),
  wxSnow: P("M7 15h10a4 4 0 0 0 .6-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 15z") + P("M8 19h.01M12 21h.01M16 19h.01M10 21.5h.01M14 21.5h.01"),
  wxThunder: P("M7 15h10a4 4 0 0 0 .6-8 5.5 5.5 0 0 0-10.6 1.5A3.3 3.3 0 0 0 7 15z") + P("M12.5 13l-2 4h3l-2 4"),
});

// WMO weather codes -> icon + Danish text
function wx(code, day = 1) {
  if (code === 0) return [day ? "wxSun" : "wxMoon", "Klart"];
  if (code <= 2) return [day ? "wxPartly" : "wxMoon", code === 1 ? "Mest klart" : "Delvist skyet"];
  if (code === 3) return ["wxCloud", "Overskyet"];
  if (code <= 48) return ["wxFog", "Tåge"];
  if (code <= 57) return ["wxRain", "Støvregn"];
  if (code <= 67) return ["wxRain", code >= 65 ? "Kraftig regn" : "Regn"];
  if (code <= 77) return ["wxSnow", "Sne"];
  if (code <= 82) return ["wxRain", "Byger"];
  if (code <= 86) return ["wxSnow", "Snebyger"];
  return ["wxThunder", "Torden"];
}
const round = (v) => (v == null ? "–" : Math.round(v));
const DAYS = ["Søn", "Man", "Tirs", "Ons", "Tors", "Fre", "Lør"];

let last = null, daysKey = "";
function render(d) {
  last = d;
  if (!d || d.error && !d.now) {
    setText("wx.place", "Vejr");
    setText("wx.desc", d?.error || "Henter …");
    setText("wx.temp", "–");
    return;
  }
  const u = d.units, n = d.now, today = d.days?.[0];
  const [icon, desc] = wx(n.code, n.day);
  setText("wx.place", d.place);
  setText("wx.updated", d.error ? "⚠ " + d.error : "opdateret " + new Date(d.updated * 1000).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }));
  setText("wx.temp", `${round(n.temp)}°`);
  setText("wx.desc", desc);
  setText("wx.feels", `${round(n.feels)}°`);
  setText("wx.wind", `${round(n.wind)} ${u.wind}`);
  setText("wx.humidity", `${round(n.humidity)} %`);
  setText("wx.today", today ? `${round(today.min)}° / ${round(today.max)}°` : "–");
  $$("[data-wx-icon]").forEach((i) => drawIcon(i, icon));
  // 7 days
  const key = JSON.stringify(d.days);
  if (key !== daysKey) {
    daysKey = key;
    const lo = Math.min(...d.days.map((x) => x.min)), hi = Math.max(...d.days.map((x) => x.max));
    $$("[data-wx-days]").forEach((box) => box.replaceChildren(...d.days.map((day, i) => {
      const row = document.createElement("div");
      row.className = "wx-day";
      const ic = Object.assign(document.createElement("i"), { className: "ic" });
      drawIcon(ic, wx(day.code)[0]);
      const range = document.createElement("div");
      range.className = "wx-range";
      const bar = document.createElement("i");
      bar.style.left = ((day.min - lo) / Math.max(1, hi - lo)) * 100 + "%";
      bar.style.right = (100 - ((day.max - lo) / Math.max(1, hi - lo)) * 100) + "%";
      range.append(bar);
      const name = i === 0 ? "I dag" : DAYS[new Date(day.date + "T12:00").getDay()];
      row.append(Object.assign(document.createElement("b"), { textContent: name }), ic,
        Object.assign(document.createElement("small"), { className: "wx-pop", textContent: day.pop ? `${day.pop} %` : "" }),
        Object.assign(document.createElement("span"), { className: "wx-min", textContent: `${round(day.min)}°` }), range,
        Object.assign(document.createElement("span"), { className: "wx-max", textContent: `${round(day.max)}°` }));
      return row;
    })));
  }
  drawHours();
}

// next 24 hours: temperature line with labels, rain chance as bars underneath
function drawHours() {
  const d = last;
  $$("canvas[data-wx-hours]").forEach((cv) => {
    const [ctx, w, h] = prep(cv);
    if (!ctx || !d?.hours?.length) return;
    const hours = d.hours.slice(0, 25);
    const temps = hours.map((x) => x.temp);
    const lo = Math.min(...temps) - 1, hi = Math.max(...temps) + 1;
    const top = 16, bottom = h - 16, rainH = Math.min(30, (bottom - top) * 0.3);
    const x = (i) => 8 + (i / (hours.length - 1)) * (w - 16);
    const y = (t) => top + (1 - (t - lo) / (hi - lo)) * (bottom - top - rainH - 6);
    // rain chance
    ctx.fillStyle = css("--cpu") + "55";
    hours.forEach((hr, i) => {
      const bh = ((hr.pop ?? 0) / 100) * rainH;
      if (bh > 0) ctx.fillRect(x(i) - 3, bottom - bh, 6, bh);
    });
    // temperature
    ctx.strokeStyle = css("--warn");
    ctx.lineWidth = 2;
    ctx.beginPath();
    hours.forEach((hr, i) => (i ? ctx.lineTo(x(i), y(hr.temp)) : ctx.moveTo(x(i), y(hr.temp))));
    ctx.stroke();
    // labels every 3 hours (fewer on narrow boxes)
    const every = w < 260 ? 6 : 3;
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "center";
    hours.forEach((hr, i) => {
      if (i % every) return;
      ctx.fillStyle = css("--text");
      ctx.fillText(`${round(hr.temp)}°`, x(i), y(hr.temp) - 5);
      ctx.fillStyle = css("--muted");
      ctx.fillText(i === 0 ? "nu" : hr.t.slice(11, 13), x(i), h - 3);
    });
  });
}

PhoneDeck.register("weather", {
  render(ext) { render(ext); },
  rebuilt() { daysKey = ""; if (last) render(last); },
  page() { if (last) drawHours(); },
});
window.addEventListener("resize", () => { if (last) drawHours(); });
})();
