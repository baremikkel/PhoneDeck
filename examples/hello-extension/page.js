"use strict";
// Phone side of the example. Helpers like setText() come from PhoneDeck's app.js.
PhoneDeck.register("hello", {
  render(ext) {
    setText("hello.greeting", ext?.greeting || "–");
    setText("hello.uptime", String(ext?.uptime ?? "–"));
  },
  widgets: {
    hello: `<div class="card hello-card"><div class="big" data-b="hello.greeting">–</div></div>`,
  },
});
