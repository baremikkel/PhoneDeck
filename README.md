# PhoneDeck

Give an old phone a new life as a **touch dashboard for your PC**: live hardware stats,
what's playing on Spotify, Claude Code token usage, and buttons that control the PC
(volume, microphone, your own shortcuts).

The phone is just a screen: the PC runs a small Python server, and the phone shows it
full-screen in a browser, connected over the **USB cable** (`adb reverse`). No Wi-Fi is
needed, latency is low, and the phone charges at the same time.

```
PC: python3 -m phonedeck ──(SSE over USB / adb reverse)──► Phone: http://localhost:8765
     ├─ CPU, GPU, RAM, network, disk (psutil + sysfs)
     ├─ Media (MPRIS: Spotify, browsers, VLC …)
     ├─ Claude Code usage (~/.claude/projects/*.jsonl)
     └─ Actions: volume, mute, microphone, your own buttons
```

Built for and tested on a OnePlus 8 Pro + Ubuntu (also tested on a Galaxy S23). Any
Android phone and Linux PC should work.

> The user interface is in Danish. Names of pages, buttons and settings below are given
> as they appear on screen, with an English explanation.

## Features

Swipe left and right between the pages. The dots at the bottom show where you are, and
the page you last looked at is remembered. Which pages are shown, and in which order, is
chosen under *Indstillinger → Sider* (Settings → Pages).

| Page | Contents |
|---|---|
| **Forside** (home) | Build it yourself on a fixed grid (4×2 to 8×4) with CPU, GPU, RAM, network, disk, music, Claude, donut, clock, GitHub heatmap and **shortcut buttons** from your Stream Deck. Default: CPU, GPU, music, Claude, a system bar and a **Menu button** in the bottom-right corner that opens settings and the editor on the PC. The Menu button is an ordinary element (under *System* in the editor), so it can be moved, resized, removed or put on your own pages |
| **System** | CPU with per-core load, GPU (hotspot/edge, power, clock, fan, VRAM), RAM, network and disk. The CPU/GPU charts show both load and temperature. The button in the corner of the CPU card places CPU and GPU side by side or on top of each other |
| **Musik** (music) | Large cover art, title/artist/album, playback controls, a volume slider that only changes the player, a **visualizer** that can be toggled, and **next song** at the bottom. Tap it to see the whole queue (requires the Spotify connection, see below) |
| **Claude** | A **donut** showing what's left of your plan limits (5 hours + week). It shows less detail the smaller it is, and a countdown to the reset once a limit is used up. Also tokens in the 5-hour window (input/output/cache), time to reset, today, 7 days, split per model, a 24-hour chart and a heatmap |
| **GitHub** | A GitHub-style contribution calendar for the last year. Tap a day to see its count |
| **Knapper** (buttons) | A **Stream Deck**: default buttons (volume, microphone, playback, full screen, lock screen, screenshot) plus your own, with optional colours and folders. Programs with an open window are marked **Aktiv** (active), and tapping them only shows a short message that the program is already open (see *Active marking* below). Edited in the browser on the PC |
| **Your own pages** | Up to 10 extra grid pages, built in the editor from the same elements as the home page |

Media uses MPRIS (Spotify, browsers, VLC …), so no API keys are needed. The music page can
be limited to Spotify only, or to everything except browsers.
The screen is kept on while the dashboard is open (Wake Lock API). If the phone isn't in
full screen after 10 seconds, PhoneDeck switches to full screen (or asks you to tap the
screen once, when the browser requires it).

Burn-in protection for AMOLED: pure black background, the whole layout shifts a few
pixels every minute, and the screen dims automatically at night (23–07 by default).

### Visualizer

The visualizer shows the real frequencies of the sound the PC is playing. The audio is
captured with PipeWire's `pw-record` and analysed with numpy. Everything happens locally,
and only the bar heights are sent to the phone, never the audio itself. The bars only
move while the music is playing, so other sounds (Discord, system sounds …) don't move
them when the music is paused. Capturing only runs while the visualizer is enabled
**and** the music page is open. The phone keeps sending an "I'm still watching" signal,
and without it the PC stops capturing within 4 seconds.

### GitHub and Claude heatmaps

- **GitHub** is read from your public contributions page, so no token is needed. Set your
  user name in the settings. Private contributions are only counted if
  *Private contributions* is enabled on your profile.
- **Claude Code** is counted from the local logs. Claude Code deletes old logs (after 30
  days by default), so PhoneDeck keeps the daily totals in
  `~/.cache/phonedeck/claude_daily.json`. The heatmap therefore fills up over time.

## Getting started (PC)

Requires Python 3.11+, `psutil` and PyGObject. The visualizer also needs `numpy` and
PipeWire (`pw-record`). On Ubuntu:

```bash
sudo apt install python3-psutil python3-gi python3-numpy pipewire-bin adb
```

```bash
git clone https://github.com/baremikkel/PhoneDeck.git && cd PhoneDeck
python3 -m phonedeck
```

Open <http://localhost:8765> on the PC to see the dashboard.

### Autostart

```bash
mkdir -p ~/.config/systemd/user && cp scripts/phonedeck.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now phonedeck
```

The service starts with your graphical session.

## The phone

1. **Enable developer options:** Settings → About phone → tap *Build number* 7 times.
2. **Enable USB debugging:** Settings → System → Developer options.
3. Connect the phone to the PC over USB and run:

   ```bash
   ./scripts/phone-connect.sh
   ```

   Accept "Allow USB debugging" on the phone the first time. The script sets up
   `adb reverse`, keeps the screen on while charging and opens the dashboard (reusing the
   same Chrome tab every time).
4. Tap the **clock** (or *Fuld skærm* on the buttons page) for full screen, or just wait
   10 seconds. In Chrome you can also choose *Add to Home screen*, so it opens as a
   full-screen app.

> `adb reverse` is reset when the cable is unplugged. Run the script again, or see the
> ideas below.

## Settings

Open **<http://localhost:8765/settings>** on the PC (or tap *Menu* on the phone).

- **Sider** (pages): turn pages on and off, and choose their order.
- **Visning** (display): night dimming (your own hours), pixel shifting against burn-in,
  automatic full screen and the number of buttons per row.
- **Extension settings**, grouped by the extension's category (AI, Musik, Udvikling …).
  For example:
  - **Spotify queue:** MPRIS doesn't expose the queue, so it's fetched from Spotify's Web
    API. Create a free app at
    [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) with the
    redirect URI `http://127.0.0.1:8765/spotify/callback`, paste the Client ID, and press
    *Forbind Spotify* (connect Spotify). PKCE is used (no client secret) with read-only
    access to the player. The login token is stored in
    `~/.config/phonedeck/spotify_token.json` (readable only by you).
  - **Claude limits:** the donut shows how much is left of the 5-hour window and the
    week. Two options:
    - **Use my Claude Code login (exact):** fetches your plan's real usage, the same
      percentages as `/usage` in Claude Code. The token is read locally from
      `~/.claude/.credentials.json`, is only sent to `api.anthropic.com`, and is never
      stored, refreshed or shown by PhoneDeck. The endpoint isn't officially documented
      and may stop working. Results are cached, and PhoneDeck backs off when rate limited.
    - **Own estimate:** set a limit in tokens per 5-hour window and optionally per week.
      The page shows your largest block in the last 30 days as a guide.

    A separate setting flips the donut to show used instead of remaining.

## Editor: pages and Stream Deck buttons

The editor (**<http://localhost:8765/editor>**) has two tabs, and below them a **live
preview** of the phone that updates while you edit, before you save.

### Sider (pages)

- Pick the page in the selector: **Forside** (home) or one of your own pages. Choose
  *+ Ny side …* to create a new one. Your own pages can be renamed and deleted here and
  reordered under Settings → Pages.
- Choose a grid size. **Drag across empty cells** to mark an area and pick what goes
  there, or **drag an element from the list** straight into the grid. Drag an element to
  move it, and drag its corner to resize it.
- The element list is **grouped by category** (System, AI, Musik, Udvikling, Andet), and
  the Stream Deck buttons by the folder they live in.
- **Elements from extensions:** every card on an extension's page (e.g. the music player,
  the Claude donut, the 24-hour chart and the GitHub heatmap) can be placed on the home
  page and your own pages. When you add an extension, its elements show up automatically.
  An extension marks a card with `data-widget="name"` and
  `data-widget-name="Display name"` in its `page.html`.

### Knapper (Stream Deck)

Open the editor on the PC, or tap *Redigér knapper* (edit buttons) on the phone to open
it on the computer. A button can:

- **Open a program:** choose from your installed programs (including Steam games and
  snaps). The icon and name are filled in automatically. If the program is already
  running, the button doesn't start a second copy but shows a short message on the phone.
- **Open a website** in the default browser, e.g. Messenger.
- **Send a keyboard shortcut**, e.g. Ctrl+Shift+T. Requires
  [`ydotool`](https://github.com/ReimuNotMoe/ydotool) with `ydotoold` running, because
  Wayland allows no other way.
- **Run a command or script**, e.g. `~/shortcut_scripts/my-script.sh`.
- **Built-in actions:** volume, mute, microphone, playback and full screen.
- **Folder** (*Mappe*): on the phone the folder opens with a back button. In the editor,
  double-click a folder to open it. Drag a button onto a folder to move it in, or onto
  *Tilbage* (back) to move it out. Folders can be nested up to 3 levels, and a folder can
  also be placed on the home page.
- **Go to page** (*Gå til side*): switches the phone to a given page, e.g. Musik, Claude
  or one of your own pages. Nothing runs on the PC; handy on the home page.

Drag buttons to reorder them, choose an emoji, built-in icon or program icon, and use
*Test på computeren* (test on the computer). When you press **Gem** (save), the phone
updates immediately. Buttons are stored in `~/.config/phonedeck/buttons.json`.

### Active marking

A program is **Aktiv** (active) when it has an open window, not merely when it runs in
the background:

- **XWayland programs** (Discord, Spotify, VS Code, Steam games …) are checked by
  PhoneDeck itself with `xdotool`.
- **Native Wayland programs** (e.g. Firefox) can't be seen by other programs under GNOME.
  Install the small extension in `gnome-extension/`, and PhoneDeck gets the answer from
  GNOME itself:

  ```bash
  ./scripts/install-gnome-helper.sh
  ```

  Then log out and back in. The extension does only one thing: it answers over D-Bus
  which programs have a window. Without it, Wayland programs count as active as long as
  they run.

## Extensions

Everything beyond the core (system, Stream Deck, home page, settings) is an
**extension**, and each one lives in its own folder:

```
extensions/
  music/         Musik      – player, own volume, visualizer
  spotify/       Musik      – next song + queue (Spotify Web API)
  claude-code/   AI         – usage, plan donut, heatmap
  github/        Udvikling  – contribution heatmap
```

- **Add** an extension by putting a folder in `extensions/` or in
  `~/.config/phonedeck/extensions/`. It shows up on the phone and in the settings within
  a few seconds, without a restart.
- **Remove** the folder, and the extension disappears again: its page, elements and
  settings.
- **Category:** `"category"` in `extension.json` groups extensions, so e.g. Claude Code
  and a ChatGPT extension both end up under *AI*. Without a category it goes under
  *Andet* (other). Settings and editor elements use the same categories.

An extension consists of:

| File | Contents |
|---|---|
| `extension.json` | name, category, description, page title, elements and settings (text, number, on/off, choice, info, status, buttons) |
| `backend.py` | optional: `class Extension` with `state()`, `action()`, `http_get()`, `info()`, `settings_changed()`, `stop()` |
| `page.html` | optional: a page on the phone |
| `page.js` | optional: `PhoneDeck.register("<id>", {render, tick, page, rebuilt, widgets})` |
| `page.css` | optional: styling |

See `examples/hello-extension/` for a small, commented example. The format is described
at the top of `phonedeck/extensions.py`.

## Configuration

```bash
mkdir -p ~/.config/phonedeck
cp config.example.toml ~/.config/phonedeck/config.toml
```

Here you can change the host, port, update interval and GPU name. Everything else is set
on the settings page and stored in `~/.config/phonedeck/settings.json`.

Buttons set up with `[[buttons]]` in `config.toml` (the old format) are moved into the
editor automatically the first time.

## Security

By default the server only listens on `127.0.0.1`, so it can only be reached from the PC
itself and from the phone over USB. Actions are a fixed list plus the buttons you define
yourself. The API rejects requests from other websites in your browser (every call needs
a special header and the right `Host`), so a malicious page can neither press buttons nor
create new ones.
Only set `host = "0.0.0.0"` if you trust your network, because then anyone on it can
control the buttons.

## Known limitations

- **Spotify as a snap:** the snap sandbox (AppArmor) only allows D-Bus calls from
  "ordinary" processes. Running PhoneDeck from a normal terminal or as a systemd service
  works. Started from inside another sandbox, the call is rejected.
- **Claude token numbers** come from Claude Code's local logs, i.e. usage from *this* PC.
  The plan donut is only exact with the Claude Code login option; otherwise the 5-hour
  window is an estimate.

## Ideas / roadmap

- [ ] Automatic `adb reverse` when the phone is plugged in (udev rule)
- [ ] Turn off/dim the screen when the PC is locked or asleep
- [ ] Battery protection (stop charging at ~60 % with ACC/Magisk)
- [ ] More pages (calendar, weather, Home Assistant …)
- [ ] Windows support (LibreHardwareMonitor)
- [ ] Minimal Android ROM (LineageOS without Google) in kiosk mode

## License

MIT
