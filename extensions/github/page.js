"use strict";
// Phone-side code for this extension (loaded by web/app.js)
(() => {
let heatKey = "";

function renderGitHub(gh) {
  if (gh?.error && !gh.days) setText("gh.user", gh.error);
  else if (gh?.user) setText("gh.user", "@" + gh.user);
  if (!gh?.days) return;
  setText("gh.total", String(gh.total));
  setText("gh.today", String(gh.today));
  setText("gh.streak", String(gh.streak));
  const key = JSON.stringify([gh.updated, layoutGen, window.innerWidth, window.innerHeight]);
  if (key === heatKey) return;  // only redraw when the data or the size changed
  heatKey = key;
  $$('canvas[data-heat="github"]').forEach((c) =>
    heatmap(c, gh.days[0].date, gh.days.map((d) => d.level), css("--gh")));
}

PhoneDeck.register("github", {
  render: renderGitHub,
  widgets: {
    github: `<div class="card heat" style="--accent: var(--gh)">
    <header><span class="label">GitHub</span><span class="sub"><b data-b="gh.total">–</b> bidrag · <b data-b="gh.streak">–</b> dage i træk</span></header>
    <canvas class="heatmap" data-heat="github"></canvas></div>`,
  },
});
})();
