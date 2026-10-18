import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import {feedbackFor, ShortcutRegistry} from './feedback.js';
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
        this._activity = 'waiting_executor'; this._takeoverPending = false;
        this._shortcuts = new ShortcutRegistry(global.display, Main.wm, Meta, Shell, event => this._emitControl(event));
        this._halo = new St.Widget({name: 'codex-pointer-halo', style_class: 'codex-pointer-halo',
            reactive: false, can_focus: false, visible: false, width: 64, height: 64});
        // Untracked, non-reactive overlay: never adds an input region or strut.
        Main.uiGroup.add_child(this._halo);
        this._haloTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 33, () => {
            try { this._refreshHalo(); }
            catch (_) { this._halo?.hide(); this._emitControl('stop'); this._haloTimer = 0; return GLib.SOURCE_REMOVE; }
            return GLib.SOURCE_CONTINUE;
        });
        this._state = 'stopped'; this._requestedVisible = false; this._lastUpdate = 0;
        this._workarea = null; this._baseArea = null; this._warning = false; this._lost = false;
        this._bar = new St.BoxLayout({name: 'codex-desktop-toolbar',
            style_class: 'codex-desktop-toolbar', reactive: true, can_focus: false,
            visible: false, y_align: Clutter.ActorAlign.CENTER});
        this._label = new St.Label({text: 'Desktop', style_class: 'codex-desktop-toolbar-status',
            y_align: Clutter.ActorAlign.CENTER});
        this._label.set_width(118);
        this._bar.add_child(this._label);
        this._pause = this._button('Pause', 'Pause desktop control (Super+Alt+P)', 'pause');
        this._continue = this._button('Continue', 'Continue with fresh sharing consent', 'continue');
        this._stop = this._button('Stop', 'Emergency stop desktop control (Super+Alt+Escape)', 'stop');
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
            this._shortcuts.register(); this._takeoverPending = false;
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
            if (data.epoch > this._epoch || data.state !== 'active') this._takeoverPending = false;
            this._state = data.state; this._epoch = data.epoch;
            this._activity = data.activity;
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
            this._position(); this._refreshVisibility(); this._refreshHalo();
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
            pointer_halo: {visible: this._halo.visible, reactive: this._halo.reactive, mode: this._haloMode ?? 'hidden'},
            takeover_shortcuts: this._shortcuts.diagnostics(), automatic_physical_takeover: false,
            reserves_bottom_strip: this._chrome.visible, fullscreen_respects_strut: false, lost_connection: this._lost});
    }

    _emitControl(event) {
        if (!this._owner) {
            // A dead backend cannot receive controls; retain an honest warning.
            return;
        }
        if (event === 'continue' && !this._canContinue) return;
        if (event === 'pause' && (this._state !== 'active' || this._takeoverPending)) return;
        if (event === 'pause' || event === 'stop') {
            this._takeoverPending = true; this._halo.hide(); this._haloMode = 'hidden';
            this._label.text = event === 'pause' ? 'Pausing…' : 'Stopping…';
        }
        this._sequence++;
        Gio.DBus.session.emit_signal(this._owner, PATH, IFACE, 'Control',
            new GLib.Variant('(ssuu)', [this._nonce, event, this._epoch, this._sequence]));
        // Disable duplicate Continue immediately, before backend acknowledges.
        if (event === 'continue') { this._canContinue = false; this._continue.reactive = false; }
    }

    _refreshHalo() {
        if (this._disabled || !this._halo) return;
        const suppressed = Main.modalCount > 0 || Main.overview.visible ||
            Main.sessionMode.isLocked || Main.sessionMode.isGreeter;
        const feedback = feedbackFor(this._state, this._activity, Boolean(this._owner) && this._chrome.visible,
            this._takeoverPending || suppressed, this._warning);
        this._haloMode = feedback.mode;
        if (!feedback.visible) { this._halo.hide(); return; }
        // Observation only: never warp/hide the cursor, capture events or grab a seat.
        const [x, y] = global.get_pointer();
        this._halo.set_position(x - 32, y - 32);
        this._halo.opacity = feedback.opacity; this._halo.show();
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
        this._shortcuts?.clear(); this._halo?.hide(); this._haloMode = 'hidden';
        this._takeoverPending = false; this._state = 'stopped';
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
        // One cleanup failure must not strand the halo or other registrations.
        const cleanup = (label, fn) => {
            try { fn(); } catch (_) { console.error(`Desktop toolbar cleanup failed: ${label}`); }
        };
        cleanup('stop notification', () => this._emitControl('stop'));
        cleanup('shortcuts', () => this._shortcuts?.clear());
        if (this._shutdown) cleanup('shutdown signal', () => global.disconnect(this._shutdown));
        if (this._haloTimer) cleanup('halo timer', () => GLib.source_remove(this._haloTimer));
        if (this._halo) {
            cleanup('halo actor', () => this._halo.destroy());
        }
        if (this._watch) cleanup('owner watch', () => Gio.bus_unwatch_name(this._watch));
        if (this._timer) cleanup('state timer', () => GLib.source_remove(this._timer));
        if (this._monitors) cleanup('monitor signal', () => Main.layoutManager.disconnect(this._monitors));
        if (this._workareas) cleanup('workarea signal', () => global.display.disconnect(this._workareas));
        cleanup('D-Bus export', () => this._export?.unexport());
        if (this._chrome && !this._destroyed) {
            cleanup('toolbar chrome', () => Main.layoutManager.removeChrome(this._chrome));
            cleanup('toolbar actor', () => this._chrome.destroy());
        }
        this._bar = null; this._chrome = null; this._halo = null; this._export = null;
        this._owner = null; this._nonce = null; this._shutdown = 0; this._haloTimer = 0;
        this._watch = 0; this._timer = 0; this._monitors = 0; this._workareas = 0;
    }
}
