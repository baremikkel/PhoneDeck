// PhoneDeck helper – the bits of GNOME that Wayland hides from ordinary programs.
//
// A tiny extension that answers a few D-Bus calls from PhoneDeck (session bus, your
// own user only):
//   WindowApps() -> as        desktop ids of apps with an open window ("Aktiv" on the deck)
//   SendKeys(au keys)         press a key combo for a Stream Deck button, e.g. [29, 46] =
//                             Ctrl+C (Linux key codes) – replaces ydotool and its daemon
//   Fps() -> (d fps, d hz, s app)
//                             frames GNOME showed on screen in the last second, the
//                             monitor's refresh rate and the focused program's name –
//                             for the FPS speedometer. Counting only runs while PhoneDeck
//                             asks, and stops 5 seconds after the last call.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const IFACE = `
<node>
  <interface name="org.phonedeck.Helper">
    <method name="WindowApps">
      <arg type="as" direction="out" name="ids"/>
    </method>
    <method name="SendKeys">
      <arg type="au" direction="in" name="keys"/>
    </method>
    <method name="Fps">
      <arg type="d" direction="out" name="fps"/>
      <arg type="d" direction="out" name="refresh"/>
      <arg type="s" direction="out" name="app"/>
    </method>
    <property name="Version" type="u" access="read"/>
  </interface>
</node>`;

const MAX_KEY = 248;      // KEY_MICMUTE; same limit as PhoneDeck's editor
const IDLE_STOP_MS = 5000;

export default class PhoneDeckHelper extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, '/org/phonedeck/Helper');
        this._nameId = Gio.bus_own_name_on_connection(Gio.DBus.session, 'org.phonedeck.Helper',
            Gio.BusNameOwnerFlags.NONE, null, null);
        this._frames = new Map();  // stage view -> [timestamps in ms]
        this._presentedId = 0;
        this._lastAsk = 0;
        this._idleId = 0;
    }

    disable() {
        this._stopCounting();
        if (this._nameId) {
            Gio.bus_unown_name(this._nameId);
            this._nameId = 0;
        }
        this._dbus?.unexport();
        this._dbus = null;
        this._keyboard = null;
    }

    get Version() {
        return 2;
    }

    WindowApps() {
        return Shell.AppSystem.get_default().get_running()
            .filter(app => app.get_windows().some(w => !w.skip_taskbar))
            .map(app => app.get_id());
    }

    SendKeys(keys) {
        keys = keys.filter(k => k > 0 && k <= MAX_KEY).slice(0, 6);
        if (!keys.length)
            return;
        if (!this._keyboard) {
            const seat = Clutter.get_default_backend().get_default_seat();
            this._keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        }
        // press in order, release in reverse (evdev key codes, like ydotool)
        let t = GLib.get_monotonic_time();
        for (const k of keys)
            this._keyboard.notify_key(t++, k, Clutter.KeyState.PRESSED);
        for (const k of [...keys].reverse())
            this._keyboard.notify_key(t++, k, Clutter.KeyState.RELEASED);
    }

    Fps() {
        this._lastAsk = Date.now();
        this._startCounting();
        const now = GLib.get_monotonic_time() / 1000;
        let fps = 0, hz = 0;
        for (const [view, stamps] of this._frames) {
            while (stamps.length && stamps[0] < now - 1000)
                stamps.shift();
            // the busiest monitor is where the game is
            if (stamps.length > fps) {
                fps = stamps.length;
                hz = view.get_refresh_rate?.() ?? 0;
            }
        }
        if (!hz) {
            const views = global.stage.peek_stage_views?.() ?? [];
            hz = Math.max(0, ...views.map(v => v.get_refresh_rate?.() ?? 0));
        }
        const win = global.display.get_focus_window();
        let app = '';
        if (win) {
            app = Shell.WindowTracker.get_default().get_window_app(win)?.get_name() ?? '';
            app = app || win.get_wm_class() || '';
        }
        return [fps, hz, app];
    }

    _startCounting() {
        if (this._presentedId)
            return;
        // "presented" fires once per frame that reaches the screen – also for full-screen
        // games shown directly (unredirected / direct scanout)
        this._presentedId = global.stage.connect('presented', (stage, view) => {
            let stamps = this._frames.get(view);
            if (!stamps)
                this._frames.set(view, stamps = []);
            stamps.push(GLib.get_monotonic_time() / 1000);
            if (stamps.length > 1000)
                stamps.splice(0, stamps.length - 1000);
        });
        this._idleId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
            if (Date.now() - this._lastAsk < IDLE_STOP_MS)
                return GLib.SOURCE_CONTINUE;
            this._idleId = 0;
            this._stopCounting();
            return GLib.SOURCE_REMOVE;
        });
    }

    _stopCounting() {
        if (this._presentedId) {
            global.stage.disconnect(this._presentedId);
            this._presentedId = 0;
        }
        if (this._idleId) {
            GLib.source_remove(this._idleId);
            this._idleId = 0;
        }
        this._frames.clear();
    }
}
