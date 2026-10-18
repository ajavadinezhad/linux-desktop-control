# Pointer incident and 0.6.5 source candidate

The user reported a locked, then jumpy pointer after the real Firefox demonstration. The cause is not established. Do not present these source changes as a verified fix for that host symptom.

## Host recovery performed

- The 0.6.4 native connection returned stopped, portal_closed_confirmed=true, capture/input off, cleanup_warning=null.
- Six then-existing desktop backend processes received emergency stop followed by graceful termination. No input/recording workers remained in that check. Host MCP discovery can later launch inactive backend processes; their presence alone does not establish injected input.
- The custom desktop-toolbar@local.codex extension was disabled using gnome-extensions and confirmed INACTIVE. The disposable Firefox profile was closed by stopping its independently verified systemd user scope; personal Firefox processes were not targeted. Direct SIGTERM was refused by the OS, so scoped service shutdown was used.
- Read-only checks found no remaining RemoteDesktop, ScreenCast or InputCapture child session objects; no recent pointer/portal error explained the symptom. Mouse/touchpad speed was 0.0, mouse acceleration profile default, and touchpad enabled. No device settings were changed. No raw keyboard/mouse event stream was collected.
- No session restart, logout, new sharing, synthetic input or live extension reenabling was performed during recovery. User confirmation of normal pointer behavior remains necessary.

## Source changes, not deployed

The pointer halo is an untracked, non-reactive St.Widget in Main.uiGroup. It observes global.get_pointer at 30Hz only while an owned visible active session exists. It does not call cursor-warp/hide, seat-grab, event-capture or input-injection APIs and does not reserve an input region or workarea. Bright blue means a running operation, dim blue means active/ready. Paused/stopped, consent/lock/overview suppression, closure warnings, owner loss and disable hide it. Pause/Stop requests hide it immediately, before backend acknowledgment; stale active updates cannot restore it.

Super+Alt+P requests the same authenticated Pause boundary as the human toolbar. Super+Alt+Escape requests Emergency Stop. Shortcuts exist only while the toolbar has an owner, remain available during a pause for Stop, and are removed on unbind/owner loss/disable. Conflicts are reported by takeover_shortcuts diagnostics; an unavailable shortcut must not be advertised as working. Successful registration is not physical keyboard acceptance.

The portal does not expose reliable human input provenance. Clutter event flags and device information do not by themselves establish whether portal-injected input is physical. Moving the mouse alone does not automatically pause. Explicit Pause cancels in-flight/queued work, releases held input and closes sharing; continuation still requires personal GNOME consent and a fresh inspected observation. Blocking OS calls can delay cleanup; never promise instantaneous interruption.

An independent source defect was found: SIGUSR1 previously set cancellation flags without reliably scheduling portal cleanup while idle. It now notifies an emergency worker that enqueues the full Stop boundary. Signal handling no longer acquires transport locks. Backend close now still attempts portal closure if capture teardown or descriptor closure fails, clears stale pointer state, and reports cleanup warnings. This defect has not been established as the cause of the user's symptom.

## Verification

171 unit tests pass, including interrupted typing/dragging, invalidated queued input, release of held modifiers/buttons, idle emergency cleanup, failure during capture/fd cleanup, shortcut conflicts/partial registration/removal and halo state policy.

17 real-extension assertions passed in isolation. The real extension is additionally exercised only in a private D-Bus + headless GNOME51 session. Host sharing and the installed extension remain off. The test checks non-reactive halo rendering, GNOME shortcut registration, no focus theft, pause/stop states and cleanup. A private broker is used on this host because dbus-run-session is unavailable. Physical shortcuts and new live-host behavior are still unverified.

GNOME API references: https://gnome.pages.gitlab.gnome.org/mutter/meta/method.Display.grab_accelerator.html and https://gnome.pages.gitlab.gnome.org/mutter/clutter/flags.EventFlags.html

Reproduce the isolated Shell test with `python3 tests/check_private_toolbar.py` when dbus-run-session is unavailable. It creates a temporary socket-activated D-Bus broker, runs the extension service and headless test only on that private bus, and terminates its owned processes afterward. No live host input is exercised.
