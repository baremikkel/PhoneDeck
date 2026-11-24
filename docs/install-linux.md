# Installing PhoneDeck on Linux

A step-by-step guide from a fresh PC to the dashboard running full-screen on your phone.
PhoneDeck is built for **GNOME on Wayland** (tested on Ubuntu). Other desktops work for
most things. GNOME is only needed for the *Aktiv* (active) marking of Wayland programs and
the *Skrivebord* (desktop) toggles.

For Windows, see [install-windows.md](install-windows.md).

## What you need

- A Linux PC with **Python 3.11 or newer** (`python3 --version`)
- An **Android phone** and a USB cable that carries data (not only power)
- About 10 minutes

## 1. Install the packages

The core needs `psutil` and PyGObject. `adb` connects the phone. Everything else is
optional and unlocks a single feature.

**Ubuntu / Debian / Pop!_OS / Mint**

```bash
sudo apt install git adb python3-psutil python3-gi python3-numpy pipewire-bin
```

**Fedora**

```bash
sudo dnf install git android-tools python3-psutil python3-gobject python3-numpy pipewire-utils
```

**Arch / Manjaro**

```bash
sudo pacman -S git android-tools python-psutil python-gobject python-numpy pipewire
```

### Optional extras

Install the ones you want. PhoneDeck works without them and hides or disables what it
can't do.

| Package / tool | Unlocks |
|---|---|
| `numpy` + PipeWire (`pw-record`) | the music **visualizer** (installed above) |
| `wireplumber` (`wpctl`) | the **Lyd** (audio) page: mixer, devices, push-to-talk |
| `xdotool` | *Aktiv* marking of XWayland programs (Discord, Spotify, Steam games …) |
| [`ydotool`](https://github.com/ReimuNotMoe/ydotool) with `ydotoold` running | Stream Deck buttons that send **keyboard shortcuts** |
| `wl-clipboard` (`wl-paste`/`wl-copy`) | the **clipboard history** on the Udklip page |
| `upower` | the **Batterier** (batteries) page |
| `udisks2` | SMART health on the **Diske** page (space works without it) |
| `network-manager` (`nmcli`) / `tailscale` | **VPN on/off** on the Netværk page |
| `nvidia-smi` (NVIDIA driver) | GPU stats on NVIDIA cards (AMD/Intel are read from sysfs) |

On Ubuntu, for example:

```bash
sudo apt install wireplumber xdotool ydotool wl-clipboard upower udisks2
```

## 2. Download PhoneDeck

```bash
mkdir -p ~/Documents/git-projects && cd ~/Documents/git-projects
git clone https://github.com/baremikkel/PhoneDeck.git
cd PhoneDeck
```

You can put it anywhere. `~/Documents/git-projects/PhoneDeck` is just the path the
autostart service expects by default (see step 6).

## 3. Start it and check it on the PC

```bash
python3 -m phonedeck
```

Open <http://localhost:8765> in a browser on the PC. You should see the dashboard with
live CPU and RAM numbers. Stop it again with `Ctrl+C`.

> **Port already in use?** Copy the config and change the port:
> `mkdir -p ~/.config/phonedeck && cp config.example.toml ~/.config/phonedeck/config.toml`

## 4. Prepare the phone (only once)

1. **Developer options:** *Settings → About phone →* tap **Build number** 7 times.
   (On some phones it's under *Software information*.)
2. **USB debugging:** *Settings → System → Developer options →* turn on **USB debugging**.
3. Optional, recommended: in Developer options, turn on **Stay awake** (the screen stays on
   while charging). The connect script tries to do this for you, but some phones refuse.

## 5. Connect the phone

With PhoneDeck running, plug in the phone and run:

```bash
./scripts/phone-connect.sh
```

The first time, the phone asks **"Allow USB debugging?"**. Tick *Always allow from this
computer* and tap *Allow*. The script then:

- forwards `localhost:8765` on the phone to the PC through the cable (`adb reverse`),
- keeps the screen on while charging,
- opens the dashboard in the phone's browser.

Tap the **clock** for full screen, or wait 10 seconds and tap once. In Chrome, *⋮ → Add to
Home screen* gives you an icon that opens PhoneDeck as a full-screen app.

> `adb reverse` is reset when the cable is unplugged or the phone restarts. Run
> `./scripts/phone-connect.sh` again.

**Troubleshooting**

- `no devices/emulators found` or the script keeps waiting: try another cable or USB port,
  and set the phone's USB mode to *File transfer*. Run `adb devices` to check.
- `unauthorized`: unlock the phone and accept the USB-debugging prompt. If it never shows
  up: *Developer options → Revoke USB debugging authorizations*, then plug in again.
- The page says it can't connect: check that `python3 -m phonedeck` is running on the PC.

### Without a cable (Wi-Fi, optional)

On Android 11 and newer you can use *Wireless debugging* instead of the cable:

1. *Developer options → Wireless debugging →* turn it on, then *Pair device with pairing
   code*.
2. On the PC: `adb pair <ip>:<pairing-port>` and type the code.
3. Then `adb connect <ip>:<port>` (the port shown on the *Wireless debugging* screen, not
   the pairing port), and run `./scripts/phone-connect.sh` as usual.

The phone and PC must be on the same network. The connection drops when the phone sleeps
for long or changes network, so the cable is more reliable.

## 6. Start automatically at login (optional)

PhoneDeck comes with a systemd user service that starts with your desktop session.

```bash
mkdir -p ~/.config/systemd/user
cp scripts/phonedeck.service ~/.config/systemd/user/
```

If you cloned PhoneDeck somewhere else than `~/Documents/git-projects/PhoneDeck`, point the
service at your folder:

```bash
sed -i "s|^WorkingDirectory=.*|WorkingDirectory=$PWD|" ~/.config/systemd/user/phonedeck.service
```

Then enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now phonedeck
```

Useful commands:

```bash
systemctl --user status phonedeck      # is it running?
journalctl --user -u phonedeck -f      # follow the log
systemctl --user restart phonedeck     # after updating
systemctl --user disable --now phonedeck   # turn autostart off
```

## 7. GNOME helper for "Aktiv" (optional)

Under Wayland, other programs can't see which windows are open. A tiny GNOME extension
tells PhoneDeck, so Stream Deck buttons for e.g. Firefox are marked *Aktiv* only while
the program has a window:

```bash
./scripts/install-gnome-helper.sh
```

**Log out and back in** afterwards. GNOME on Wayland only loads new extensions at login.
If the script says user extensions are disabled, turn on *Use extensions* in the
*Extensions* app.

## 8. Set it up

Open <http://localhost:8765/settings> on the PC (or tap *Menu* on the phone):

- **Sider** (pages): choose which pages to show and in which order.
- **Visning** (display): night dimming, pixel shifting against burn-in, auto full screen.
- **Extensions**: GitHub user name, weather town, calendar links, Spotify, Claude limits,
  Home Assistant …

The Stream Deck buttons and your home screen are edited at
<http://localhost:8765/editor>. See the [README](../README.md) for what every page and
setting does.

## Updating

```bash
cd ~/Documents/git-projects/PhoneDeck
git pull
systemctl --user restart phonedeck    # or stop and start python3 -m phonedeck
```

Your settings live in `~/.config/phonedeck/` and are kept when you update.

## Uninstalling

```bash
systemctl --user disable --now phonedeck
rm ~/.config/systemd/user/phonedeck.service
gnome-extensions disable phonedeck-helper@phonedeck
rm -r ~/.local/share/gnome-shell/extensions/phonedeck-helper@phonedeck
rm -r ~/.config/phonedeck ~/.cache/phonedeck     # settings and cached data
rm -r ~/Documents/git-projects/PhoneDeck
```

On the phone you can turn USB debugging off again under Developer options.
