// PhoneDeck helper – reports which apps have at least one open window.
//
// Wayland doesn't let ordinary programs see other programs' windows, so this tiny
// extension answers one read-only D-Bus call for PhoneDeck:
//   org.phonedeck.Helper.WindowApps() -> array of desktop ids, e.g. ["spotifast.desktop"]

import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const IFACE = `
<node>
  <interface name="org.phonedeck.Helper">
    <method name="WindowApps">
      <arg type="as" direction="out" name="ids"/>
    </method>
  </interface>
</node>`;

export default class PhoneDeckHelper extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, '/org/phonedeck/Helper');
        this._nameId = Gio.bus_own_name_on_connection(Gio.DBus.session, 'org.phonedeck.Helper',
            Gio.BusNameOwnerFlags.NONE, null, null);
    }

    disable() {
        if (this._nameId) {
            Gio.bus_unown_name(this._nameId);
            this._nameId = 0;
        }
        this._dbus?.unexport();
        this._dbus = null;
    }

    WindowApps() {
        return Shell.AppSystem.get_default().get_running()
            .filter(app => app.get_windows().some(w => !w.skip_taskbar))
            .map(app => app.get_id());
    }
}
