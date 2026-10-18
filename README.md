# Linux Desktop Control

Version **0.7.6** is a private local MCP integration using GNOME Wayland's public desktop portal. It is an independent project, not an official OpenAI product.

Five tools: `desktop_start`, `desktop_observe`, `desktop_action`, `desktop_status`, `desktop_close`. The final tool releases session resources. Each new session needs personal GNOME monitor/keyboard/pointer consent. GNOME's native sharing control remains available independently.

The read-only GNOME observer extension displays **Mouse is being controlled by ChatGPT** below the pointer while the assistant session is active. It is passive, non-focusable and untracked by the Shell input-region/workarea manager. It disappears on closure, disconnection, lease expiry or disable. It never moves or hides the cursor, injects input or registers shortcuts. Default operation registers no input-event observer; an explicitly selected candidate can observe session-only source-device metadata as described below. An optional opt-in changes the actual Xcursor pixels to a glow theme for the active session; it temporarily affects the desktop-wide cursor preference and custom application cursors may ignore it. A separate watchdog restores the original preference on cleanup or owner loss and preserves a later user choice. It draws no ring or duplicate cursor. See [cursor glow](docs/CURSOR_GLOW.md).

Guarded input requires the updated read-only foreground observer (protocol 2); status/cleanup tools remain available without an active observer. `indicator_warning` explicitly reports an unavailable label. Loading a newly installed GNOME extension can require a manual logout/login; the installer never restarts the session. The historical 0.7.1 trial ended safely before browser acceptance; later live 0.7.5 evidence is linked below.

## Install

Run `./install.sh --check` for read-only environment checks, then `./install.sh` to prepare paths, copy the foreground observer and install the local plugin. Refresh the app's MCP connection after updating; already connected chats can retain an older catalog. The observer installer is `python3 install-indicator.py`. Remove only that indicator with `python3 uninstall-indicator.py`.

## Use

Inspect each fresh screenshot before input. Coordinates use logical monitor units. Keyboard/text input must acquire focus in the same call. Bounded sequences allow 1–8 steps and begin with an observed click or a visible focus shortcut. Discrete wheel steps and paced Unicode composition are supported; clipboard access is absent. Pointer movement starts from a fresh, read-only GNOME pointer snapshot mapped to the selected monitor; missing mapping or an off-monitor pointer refuses input. Dispatch does not prove semantic success.

After uncertain input, obtain and inspect `desktop_observe` and pass its recovery token before further input. Never replay automatically. Optional accessibility identities are single-use and refuse ambiguous/protected/stale controls without fallback. Some connections return AccessDenied.

Call `desktop_close` on completion or error and check `portal_closed_confirmed` and `cleanup_warning`. Cancellation, client disconnection, process termination and idle expiry also close the session. Portal closure is attempted before bounded capture teardown. Blocking OS calls can still delay cleanup; use GNOME's native sharing control if closure cannot be confirmed. The portal does not reliably distinguish human from synthetic input. With default settings, moving the physical mouse alone is not an automatic cancellation signal.

## Verify

[Live 0.7.5 evidence](docs/LIVE_0_7_5.md) records the native dialog save/reopen workflow, actual themed glow/restoration and a human-confirmed Alt+Tab during a guarded wait.

`/usr/bin/python3 -m unittest discover -s tests` checks input validation, release/cancellation/disconnect behavior, fresh capture recovery, target identity and uncertain-input reconciliation without sharing. `python3 tests/check_loader.py` checks the real app loader and all five schemas in a temporary Codex home. The indicator bridge has isolated transport tests; current live outcomes and remaining acceptance gaps are documented in docs/RELEASE_STATUS.md. Do not run a headless GNOME compositor on a live user manager: it can change activation display settings even with a private D-Bus bus. Use a separate test environment for graphical tests.

Source remains private; reuse licensing is deferred. No compensation or distribution terms are assigned. See docs/LICENSING_REVIEW.md.

## Consent and foreground target

Do not launch/focus apps through command runners before consent. Start sharing, inspect its image, then use the observed GUI. Each action uses window_observation_id from that image. Focus/geometry/context changes interrupt ordinary batches and close the session; no automatic focus reclaim, retry or restart occurs. An intentional GUI launch is one explicit focus_transition gesture, with fresh inspection afterward. See docs/FOCUS_GUARD_0_7_1.md for exact guarantees and limitations.


Optional `desktop_start(physical_takeover=true)` expands observation to global
source-device metadata for the active consented session. It reads no key
contents, buttons, event positions or device names, and exports no device paths.
Native source activity requests cancellation; unknown sources are unsupported,
and source classification is not human attestation. Default false registers no
listener. Preflight refuses this option unless helper revision 4 is manually
loaded. This candidate still needs real same-window mouse/keyboard acceptance;
API availability and isolated tests do not establish that it works on the live
compositor. See [takeover scope and checks](docs/SAME_WINDOW_TAKEOVER.md).
