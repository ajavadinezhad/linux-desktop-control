// No event capture, cursor mutation, screenshots or input injection in this module.
export function feedbackFor(state, activity, ownedAndVisible, pending, warning) {
    if (state !== 'active' || !ownedAndVisible || pending || warning)
        return {visible: false, mode: 'hidden', opacity: 0};
    return {visible: true, mode: activity === 'working' ? 'working' : 'ready',
        opacity: activity === 'working' ? 230 : 110};
}

export class ShortcutRegistry {
    constructor(display, wm, meta, shell, control) {
        Object.assign(this, {display, wm, meta, shell, control});
        this.bindings = new Map(); this.signal = 0;
        this.available = {pause: false, stop: false}; this.cleanupFailed = false;
    }
    register() {
        this.clear();
        if (this.cleanupFailed) return;
        try {
            this.signal = this.display.connect('accelerator-activated', (_display, action) => {
                const binding = this.bindings.get(action);
                if (binding) this.control(binding.event);
            });
            for (const [event, accelerator] of [['pause', '<Super><Alt>p'], ['stop', '<Super><Alt>Escape']]) {
                const action = this.display.grab_accelerator(accelerator, this.meta.KeyBindingFlags.NONE);
                if (action === this.meta.KeyBindingAction.NONE) continue;
                const name = this.meta.external_binding_name_for_action(action);
                this.bindings.set(action, {name, event});
                if (typeof name !== 'string') throw new Error('Unavailable binding name');
                this.wm.allowKeybinding(name, this.shell.ActionMode.ALL);
                this.available[event] = true;
            }
        } catch (_) { this.clear(); }
    }
    diagnostics() { return {...this.available, cleanup_failed: this.cleanupFailed, pause_accelerator: 'Super+Alt+P', stop_accelerator: 'Super+Alt+Escape'}; }
    clear() {
        this.cleanupFailed = false;
        if (this.signal) {
            try { this.display.disconnect(this.signal); this.signal = 0; }
            catch (_) { this.cleanupFailed = true; }
        }
        for (const [action, binding] of this.bindings) {
            try { this.display.ungrab_accelerator(action); this.bindings.delete(action); }
            catch (_) { this.cleanupFailed = true; }
            try { this.wm.allowKeybinding(binding.name, this.shell.ActionMode.NONE); }
            catch (_) { this.cleanupFailed = true; }
        }
        this.available = {pause: false, stop: false};
    }
}
