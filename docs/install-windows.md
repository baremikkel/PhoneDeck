# Installing PhoneDeck on Windows

A step-by-step guide from a fresh PC to the dashboard running full-screen on your phone.

> Windows support is new. It has been tested in a simulated Windows environment, not yet
> on a real Windows PC. If something doesn't work, please
> [open an issue](https://github.com/baremikkel/PhoneDeck/issues).

For Linux, see [install-linux.md](install-linux.md).

## What you need

- Windows 10 or 11
- An **Android phone** and a USB cable that carries data (not only power)
- About 15 minutes

## 1. Install Python

1. Download **Python 3.11 or newer** from
   [python.org/downloads](https://www.python.org/downloads/).
2. In the installer, keep **Use admin privileges when installing py.exe** ticked (it
   installs the `py` launcher used below). Ticking **Add python.exe to PATH** is optional.

Or from a terminal: `winget install Python.Python.3.13` (this does not add `python` to
PATH, but `py` works, and that is all this guide uses).

Check it in a new PowerShell window:

```powershell
py --version
```

## 2. Download PhoneDeck

**With Git** (`winget install Git.Git`):

```powershell
cd $HOME\Documents
git clone https://github.com/baremikkel/PhoneDeck.git
cd PhoneDeck
```

**Without Git:** on the [GitHub page](https://github.com/baremikkel/PhoneDeck), choose
*Code → Download ZIP*, unpack it (e.g. to `Documents\PhoneDeck`) and open PowerShell in
that folder (*Shift + right-click → Open in Terminal*).

## 3. Install the Python packages

```powershell
py -m pip install -r requirements-windows.txt
```

This installs everything, including the optional packages:

| Package | Unlocks |
|---|---|
| `psutil`, `tzdata` | the core: CPU, RAM, network, disk, and time zones for the calendar |
| `numpy`, `soundcard` | the music **visualizer** |
| `pycaw` | microphone mute and reading the volume level |
| `winrt-…` | "now playing": title, artist and cover art |

If one of the optional packages fails to install, PhoneDeck still works without it.

> With **Smart App Control** turned on (*Windows Security → App & browser control*),
> Windows may refuse to load the `winrt` packages even though they installed fine. The music
> card then says *"Windows blokerede winrt"* and shows no title or cover. Play/pause and
> next/previous still work through the media keys.

## 4. Start it and check it on the PC

```powershell
py -m phonedeck
```

Open <http://localhost:8765> in a browser on the PC. You should see the dashboard with
live CPU and RAM numbers. Leave the window open while you set up the phone (stop it
later with `Ctrl+C`).

> If Windows Firewall asks, you can click *Cancel*. PhoneDeck only listens on the PC
> itself, and the phone reaches it through the USB cable.

## 5. Temperatures and GPU (optional, recommended)

Windows doesn't expose temperatures to normal programs. PhoneDeck reads them from
**LibreHardwareMonitor**:

1. Download it from
   [github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases),
   unpack it and run `LibreHardwareMonitor.exe` **as administrator**.
2. Turn on *Options → Remote Web Server → Run* (port **8085**).
3. To have it start with Windows: tick *Options → Run On Windows Startup* and
   *Start Minimized*.

Without it you still get CPU load, RAM, network and disk. NVIDIA graphics cards also work
through `nvidia-smi`, which comes with the NVIDIA driver.

## 6. Connect the phone

### Prepare the phone (only once)

1. **Developer options:** *Settings → About phone →* tap **Build number** 7 times.
   (On some phones it's under *Software information*.)
2. **USB debugging:** *Settings → System → Developer options →* turn on **USB debugging**.
3. Optional, recommended: in Developer options, turn on **Stay awake** (the screen stays on
   while charging).

### Install adb

```powershell
winget install Google.PlatformTools
```

Close and reopen PowerShell afterwards, so `adb` is found.

> Some phones (older Samsung, Xiaomi …) also need their USB driver on Windows to show up
> in adb. Google's [OEM USB drivers](https://developer.android.com/studio/run/oem-usb)
> page links to them.

### Connect

With PhoneDeck running, plug in the phone and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\phone-connect.ps1
```

The first time, the phone asks **"Allow USB debugging?"**. Tick *Always allow from this
computer* and tap *Allow*. The script then:

- forwards `localhost:8765` on the phone to the PC through the cable (`adb reverse`),
- keeps the screen on while charging,
- opens the dashboard in the phone's browser.

Tap the **clock** for full screen, or wait 10 seconds and tap once. In Chrome, *⋮ → Add to
Home screen* gives you an icon that opens PhoneDeck as a full-screen app.

> `adb reverse` is reset when the cable is unplugged or the phone restarts. Run the
> connect script again.

**Troubleshooting**

- The script keeps waiting: try another cable or USB port, set the phone's USB mode to
  *File transfer*, and check with `adb devices`.
- `unauthorized`: unlock the phone and accept the USB-debugging prompt. If it never shows
  up: *Developer options → Revoke USB debugging authorizations*, then plug in again.
- `adb` is not recognized: open a new PowerShell window after installing Platform-Tools.
- The page says it can't connect: check that `py -m phonedeck` is running on the PC.

## 7. Start automatically at login (optional)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-autostart-windows.ps1
```

This puts a shortcut in your Startup folder that runs PhoneDeck in the background, without
a console window, every time you log in. Start it right away with `pyw -m phonedeck`
(from the PhoneDeck folder) or by logging out and in.

To remove the autostart again:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-autostart-windows.ps1 -Remove
```

> Running in the background, PhoneDeck has no window to close. To stop it, end
> **pythonw.exe** in Task Manager.

## 8. Set it up

Open <http://localhost:8765/settings> on the PC (or tap *Menu* on the phone):

- **Sider** (pages): choose which pages to show and in which order.
- **Visning** (display): night dimming, pixel shifting against burn-in, auto full screen.
- **Extensions**: GitHub user name, weather town, calendar links, Spotify, Claude limits,
  Home Assistant …

The Stream Deck buttons and your home screen are edited at
<http://localhost:8765/editor>.

### What differs from Linux

- The **Lyd** (mixer), **Batterier** and **Skrivebord** pages are Linux-only and hidden.
- The player's own volume isn't available; use the Windows volume mixer.
- *Diske* shows space per drive, but no SMART health.
- Programs come from your Start menu. *Aktiv* means the program has a visible window.

See the [README](../README.md#windows) for the full list.

## Updating

```powershell
cd $HOME\Documents\PhoneDeck
git pull
py -m pip install -r requirements-windows.txt
```

Then restart PhoneDeck (end `pythonw.exe` in Task Manager and log out and in, or run
`pyw -m phonedeck`). If you downloaded the ZIP, download it again and replace the
folder.

Your settings live in `%APPDATA%\PhoneDeck` and are kept when you update.

## Uninstalling

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-autostart-windows.ps1 -Remove
Remove-Item -Recurse "$env:APPDATA\PhoneDeck", "$env:LOCALAPPDATA\PhoneDeck"
```

Then delete the PhoneDeck folder. Python, adb and LibreHardwareMonitor can be uninstalled
under *Settings → Apps*. On the phone you can turn USB debugging off again under
Developer options.
