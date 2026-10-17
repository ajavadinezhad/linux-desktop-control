import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const PATH = '/org/codex/DesktopToolbar';
const IFACE = 'org.codex.DesktopToolbar';
const XML = `<node><interface name="${IFACE}">
<method name="Bind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
<method name="Update"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
<method name="Unbind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
<method name="GetDiagnostics"><arg type="s" direction="out"/></method>
<signal name="Control"><arg type="s"/><arg type="s"/><arg type="u"/><arg type="u"/></signal>
</interface></node>`;
const STATES = new Set(['starting','active','paused','pausing','resuming','stopping','stopped']);

export default class DesktopToolbar extends Extension {
    enable() {
        this._disabled = false; this._destroyed = false;
        this._shutdown = global.connect('shutdown', () => this.disable());
        this._owner = null; this._nonce = null; this._epoch = 0; this._sequence = 0;
        this._state = 'stopped'; this._requestedVisible = false; this._lastUpdate = 0;
        this._workarea = null; this._baseArea = null; this._warning = false; this._lost = false;
        this._bar = new St.BoxLayout({name: 'codex-desktop-toolbar',
            style_class: 'codex-desktop-toolbar', reactive: true, can_focus: false,
            visible: false, y_align: Clutter.ActorAlign.CENTER});
        this._label = new St.Label({text: 'Desktop', style_class: 'codex-desktop-toolbar-status',
            y_align: Clutter.ActorAlign.CENTER});
        this._label.set_width(118);
        this._bar.add_child(this._label);
        this._pause = this._button('Pause', 'Pause desktop control', 'pause');
        this._continue = this._button('Continue', 'Continue with fresh sharing consent', 'continue');
        this._stop = this._button('Stop', 'Emergency stop desktop control', 'stop');
        this._stop.add_style_class_name('codex-desktop-toolbar-stop');
        this._chrome = new St.Widget({name: 'codex-desktop-toolbar-chrome', reactive: false, visible: false});
        this._chrome.add_child(this._bar);
        this._chrome.connect('destroy', () => { this._destroyed = true; });
        this._bar.visible = true;
        // Reserve the bottom strip while visible so ordinary maximized content
        // is not underneath the toolbar. This does not override fullscreen.
        Main.layoutManager.addChrome(this._chrome, {affectsStruts: false,
            trackFullscreen: false});
        this._allocation = this._chrome.connect('notify::allocation', () => this._position());
        this._monitors = Main.layoutManager.connect('monitors-changed', () => {this._baseArea = null; this._position();});
        this._workareas = global.display.connect('workareas-changed', () => this._position());
        this._export = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._export.export(Gio.DBus.session, PATH);
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
            if (this._owner && GLib.get_monotonic_time() - this._lastUpdate > 3000000) {
                this._emitControl('stop'); this._dropOwner(true);
            }
            this._refreshVisibility();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _button(label, accessibleName, event) {
        const button = new St.Button({label, accessible_name: accessibleName,
            style_class: 'codex-desktop-toolbar-button', can_focus: true, reactive: true});
        button.connect('clicked', () => this._emitControl(event));
        this._bar.add_child(button);
        return button;
    }

    _authorized(nonce, invocation) {
        return this._owner === invocation.get_sender() && nonce === this._nonce;
    }

    BindAsync([nonce], invocation) {
        const sender = invocation.get_sender();
        let accepted = typeof nonce === 'string' && /^[a-f0-9]{32}$/.test(nonce);
        if (this._owner && (this._owner !== sender || this._nonce !== nonce)) accepted = false;
        if (accepted && !this._owner) {
            this._owner = sender; this._nonce = nonce; this._sequence = 0; this._epoch = 0;
            this._lost = false; this._stop.reactive = true; this._stop.can_focus = true; this._stop.opacity = 255; this._lastUpdate = GLib.get_monotonic_time();
            this._watch = Gio.bus_watch_name_on_connection(Gio.DBus.session, sender,
                Gio.BusNameWatcherFlags.NONE, null, () => this._dropOwner(true));
        }
        invocation.return_value(new GLib.Variant('(b)', [accepted]));
    }

    UpdateAsync([nonce, serialized], invocation) {
        let accepted = this._authorized(nonce, invocation);
        let data;
        try {
            if (serialized.length > 2048) throw new Error('Oversized state');
            data = JSON.parse(serialized);
            if (!STATES.has(data.state) || !Number.isInteger(data.epoch) ||
                data.epoch < this._epoch || data.epoch > 0xffffffff) accepted = false;
        } catch (_) { accepted = false; }
        if (accepted) {
            this._state = data.state; this._epoch = data.epoch;
            this._requestedVisible = data.visible === true;
            this._warning = data.closure_warning === true;
            this._canContinue = data.can_continue === true && this._state === 'paused';
            this._monitor = data.monitor ?? null;
            this._lastUpdate = GLib.get_monotonic_time();
            const activityLabels = {working: 'Working', observe: 'Inspect screen',
                plan_ack: 'Planning next step', waiting_executor: 'Waiting for task'};
            const labels = {active: activityLabels[data.activity] ?? 'Waiting for task',
                paused: 'Paused', pausing: 'Pausing…', resuming: 'Waiting for sharing',
                stopping: 'Stopping…', starting: 'Starting', stopped: 'Finished'};
            this._label.text = this._warning ? 'Check sharing' : labels[this._state];
            this._pause.reactive = this._state === 'active';
            this._pause.can_focus = this._pause.reactive;
            this._continue.reactive = this._canContinue;
            this._continue.can_focus = this._canContinue;
            this._pause.opacity = this._pause.reactive ? 255 : 110;
            this._continue.opacity = this._canContinue ? 255 : 110;
            this._position(); this._refreshVisibility();
        }
        invocation.return_value(new GLib.Variant('(b)', [accepted]));
    }

    UnbindAsync([nonce], invocation) {
        const accepted = this._authorized(nonce, invocation);
        if (accepted) this._dropOwner(false);
        invocation.return_value(new GLib.Variant('(b)', [accepted]));
    }

    GetDiagnostics() {
        const [x, y] = this._bar.get_transformed_position();
        return JSON.stringify({visible: this._chrome.visible && this._bar.mapped,
            actors: this._chrome.visible ? 1 : 0, rect: [x, y, this._bar.width, this._bar.height],
            workarea: this._workarea, monitor_bounds: this._monitorBounds, base_workarea: this._baseArea, state: this._state, epoch: this._epoch,
            can_continue: this._canContinue === true, owner: this._owner,
            reserves_bottom_strip: this._chrome.visible, fullscreen_respects_strut: false, lost_connection: this._lost});
    }

    _emitControl(event) {
        if (!this._owner) {
            // A dead backend cannot receive controls; retain an honest warning.
            return;
        }
        if (event === 'continue' && !this._canContinue) return;
        if (event === 'pause' && this._state !== 'active') return;
        this._sequence++;
        Gio.DBus.session.emit_signal(this._owner, PATH, IFACE, 'Control',
            new GLib.Variant('(ssuu)', [this._nonce, event, this._epoch, this._sequence]));
        // Disable duplicate Continue immediately, before backend acknowledges.
        if (event === 'continue') { this._canContinue = false; this._continue.reactive = false; }
    }

    _position() {
        if (this._disabled || this._destroyed || this._positioning || !this._chrome) return;
        let monitor = Main.layoutManager.primaryMonitor;
        if (!monitor) return;
        if (this._monitor && Number.isFinite(this._monitor.x) && Number.isFinite(this._monitor.y)) {
            monitor = Main.layoutManager.monitors.find(m => m.x === this._monitor.x &&
                m.y === this._monitor.y && m.width === this._monitor.width &&
                m.height === this._monitor.height) ?? monitor;
        }
        this._positioning = true;
        try {
            const index = Main.layoutManager.monitors.indexOf(monitor);
            const area = Main.layoutManager.getWorkAreaForMonitor(index);
            this._workarea = {x: area.x, y: area.y, width: area.width, height: area.height};
            this._monitorBounds = {x: monitor.x, y: monitor.y, width: monitor.width, height: monitor.height};
            // Capture external reservations before our own strut is enabled.
            // Keep it stable while visible to avoid a self-strut feedback loop.
            if (!this._baseArea) this._baseArea = {...this._workarea};
            const width = Math.min(this._bar.get_preferred_width(-1)[1], monitor.width - 24);
            this._bar.set_width(width);
            const height = this._bar.get_preferred_height(width)[1];
            const x = Math.min(monitor.x + monitor.width, this._baseArea.x + this._baseArea.width) - width - 12;
            const y = this._baseArea.y + this._baseArea.height - height;
            this._chrome.set_position(x, y);
            // Transparent space below the bar reaches the actual monitor edge;
            // GNOME can reserve the strip without covering an existing dock.
            this._chrome.set_size(width, monitor.y + monitor.height - y);
            this._bar.set_position(0, 0); this._bar.set_height(height);
        } finally { this._positioning = false; }
    }

    _refreshVisibility() {
        if (this._disabled || this._destroyed || !this._chrome) return;
        // GNOME consent/lock/overview surfaces always take priority.
        const suppressed = Main.modalCount > 0 || Main.overview.visible ||
            Main.sessionMode.isLocked || Main.sessionMode.isGreeter;
        const show = (this._requestedVisible || this._lost) && !suppressed;
        if (show !== this._chrome.visible) {
            if (show) { this._baseArea = null; this._position(); }
            Main.layoutManager.untrackChrome(this._chrome);
            Main.layoutManager.trackChrome(this._chrome, {affectsStruts: show, trackFullscreen: false});
            this._chrome.visible = show;
            if (!show) this._baseArea = null;
        }
    }

    _dropOwner(lost) {
        if (this._watch) { Gio.bus_unwatch_name(this._watch); this._watch = 0; }
        this._owner = null; this._nonce = null; this._requestedVisible = false;
        this._canContinue = false; this._lost = lost;
        this._pause.reactive = false; this._continue.reactive = false;
        this._stop.reactive = !lost; this._stop.can_focus = !lost; this._stop.opacity = lost ? 110 : 255;
        if (lost) this._label.text = 'Check sharing';
        this._refreshVisibility();
    }

    disable() {
        if (this._disabled) return;
        this._disabled = true;
        if (this._shutdown) { global.disconnect(this._shutdown); this._shutdown = 0; }
        this._emitControl('stop');
        if (this._watch) Gio.bus_unwatch_name(this._watch);
        if (this._timer) GLib.source_remove(this._timer);
        if (this._monitors) Main.layoutManager.disconnect(this._monitors);
        if (this._workareas) global.display.disconnect(this._workareas);
        this._export?.unexport();
        if (this._chrome && !this._destroyed) { Main.layoutManager.removeChrome(this._chrome); this._chrome.destroy(); }
        this._bar = null; this._chrome = null; this._export = null; this._owner = null; this._nonce = null;
        this._watch = 0; this._timer = 0; this._monitors = 0; this._workareas = 0;
    }
}
