"use strict";
// Shared icon set for the dashboard and the editor.

// ---------- icons (inline SVG, so they look the same everywhere – no emoji) ----------
const P = (d, fill) => `<path d="${d}"${fill ? ' fill="currentColor" stroke="none"' : ""}/>`;
const SPEAKER = P("M4 9.5h3.5L12 5.5v13l-4.5-4H4a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1z", true);
const ICONS = {
  play: P("M8 5.2v13.6a1 1 0 0 0 1.53.85l10.9-6.8a1 1 0 0 0 0-1.7L9.53 4.35A1 1 0 0 0 8 5.2z", true),
  pause: P("M7 4.5h3a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1zM14 4.5h3a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1z", true),
  prev: P("M19 6.1v11.8a1 1 0 0 1-1.55.83L9 13.2a1.45 1.45 0 0 1 0-2.4l8.45-5.53A1 1 0 0 1 19 6.1zM5 5.5a1 1 0 0 1 2 0v13a1 1 0 0 1-2 0z", true),
  next: P("M5 6.1v11.8a1 1 0 0 0 1.55.83L15 13.2a1.45 1.45 0 0 0 0-2.4L6.55 5.27A1 1 0 0 0 5 6.1zM17 5.5a1 1 0 0 1 2 0v13a1 1 0 0 1-2 0z", true),
  minus: P("M5 12h14"),
  plus: P("M12 5v14M5 12h14"),
  volDown: SPEAKER + P("M15.5 9.5a3.5 3.5 0 0 1 0 5"),
  volMute: SPEAKER + P("M15.5 9.5a3.5 3.5 0 0 1 0 5") + P("M18.5 7a7 7 0 0 1 0 10"),
  volUp: SPEAKER + P("M15.5 9.5a3.5 3.5 0 0 1 0 5") + P("M18.5 7a7 7 0 0 1 0 10") + P("M21 4.5a10.5 10.5 0 0 1 0 15"),
  volOff: SPEAKER + P("M16 9.5l5 5M21 9.5l-5 5"),
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/>' + P("M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6"),
  micOff: '<rect x="9" y="3" width="6" height="11" rx="3"/>' + P("M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6M3.5 3.5l17 17"),
  viz: P("M5 20v-6M9.5 20V8M14 20v-9M18.5 20V4"),
  stacked: '<rect x="4" y="4" width="16" height="7" rx="1.5"/><rect x="4" y="13" width="16" height="7" rx="1.5"/>',
  sideBySide: '<rect x="4" y="4" width="7" height="16" rx="1.5"/><rect x="13" y="4" width="7" height="16" rx="1.5"/>',
  globe: '<circle cx="12" cy="12" r="9"/>' + P("M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"),
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/>' + P("M7 9l3 3-3 3M13 15h4"),
  keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2"/>' + P("M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"),
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/>' + P("M8 11V8a4 4 0 0 1 8 0v3"),
  folder: P("M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"),
  star: P("M12 3.5l2.6 5.3 5.9.9-4.25 4.1 1 5.8L12 16.8 6.75 19.6l1-5.8L3.5 9.7l5.9-.9z"),
  bolt: P("M13 3L5 13.5h6L10 21l8-10.5h-6z"),
  queue: P("M4 6h12M4 12h12M4 18h8M18 15v6l4-3z"),
  close: P("M6 6l12 12M18 6L6 18"),
  fullscreen: P("M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"),
};
const svg = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
function drawIcon(el, name) {
  if (el.dataset.drawn === name) return;
  el.dataset.drawn = name;
  el.innerHTML = svg(name);  // static markup from ICONS only
}
