# Linux Desktop Control

Installed version **0.8.12** is a private local MCP integration using GNOME Wayland's public desktop portal. It is an independent project, not an official OpenAI product.

Seven tools: `desktop_start`, `desktop_observe`, `desktop_action`, `desktop_status`, `desktop_pause`, `desktop_resume`, `desktop_close`. The final tool releases session resources. Each new session needs personal GNOME monitor/keyboard/pointer consent. GNOME's native sharing control remains available independently.

The read-only GNOME observer extension displays **Mouse is being controlled by ChatGPT** below the pointer while the assistant session is active. It is passive, non-focusable and untracked by the Shell input-region/workarea manager. It disappears on closure, disconnection, lease expiry or disable. It never moves or hides the cursor, injects input or registers shortcuts. The backend never enables the failed extension input-filter candidate. Optional native activity monitoring is described below. An optional opt-in changes the actual Xcursor pixels to a glow theme for the active session; it temporarily affects the desktop-wide cursor preference and custom application cursors may ignore it. A separate watchdog restores the original preference on cleanup or owner loss and preserves a later user choice. It draws no ring or duplicate cursor. See [cursor glow](docs/CURSOR_GLOW.md).

Guarded input requires the updated read-only foreground observer (protocol 2); status/cleanup tools remain available without an active observer. `indicator_warning` explicitly reports an unavailable label. Loading a newly installed GNOME extension can require a manual logout/login; the installer never restarts the session. The historical 0.7.1 trial ended safely before browser acceptance; later live 0.7.5 evidence is linked below.

## Current live acceptance — 2026-10-19

Installed 0.8.12/helper 0.8.5 passed a scoped, human-confirmed mouse test on the current host: native motion paused automation while retaining sharing, quiet triggered one return to the confirmed assistant cursor point, and a fresh image verified the unchanged scratch foreground. No click, key or interrupted action was replayed. Sharing closed cleanly. Earlier failed trials remain historical evidence; their unique cause is not established. This does not establish coverage across devices or applications. See [current release status](docs/RELEASE_STATUS.md) and [beta acceptance matrix](docs/BETA_ACCEPTANCE.md). Older candidate notes below describe their state at the time.

## Authorization-release settling candidate

Installed plugin 0.8.12/helper 0.8.5 bounds a reproduced startup race: authorization input still held when CALIBRATE arrives is drained without credit, with at most five seconds to reach a released, clean boundary. The controller allows six seconds for the actual CALIBRATING acknowledgement while maintaining cancellation, heartbeat and the original lease. Startup `settling` grants no cue, calibration credit, capture or input. Strict relative calibration and the separate post-ARM gate remain unchanged. This repairs startup fragility; missing live mouse delivery and automatic return remain unresolved. See [authorization-release settling](docs/CALIBRATION_RELEASE_SETTLING.md).

## Post-ARM readiness candidate

Candidate 0.8.11 keeps helper package 0.8.4 unchanged. Retained MODEYIELD2 startup no longer advertises readiness after initial ARM alone: a separate 30-second mouse-only YIELDED/QUIET/RESUME/ARMED exchange must pass, with the fixed notice closed, before capture/input. Read-only startup status distinguishes the stage and exposes a coarse remaining budget. The notice says not to press keys or mouse buttons because native observation is already armed. Default close-policy startup is unchanged. This fixes false readiness, not missing event delivery; plugin 0.8.11 is installed with unchanged helper 0.8.4, and live mouse return remains unresolved. See [post-ARM readiness](docs/POST_ARM_READINESS.md).

## Prior diagnostic-only baseline

Candidate 0.8.10/helper 0.8.4 adds four optional terminal booleans showing whether strict relative calibration, a primary record after ARM, an eligible relative record after ARM and a sent yield token were observed. They are exported only after raw descriptors close and cannot enable control. Optional reads never delay cancellation callbacks; missing detail, including normal close, is valid. Plugin 0.8.10/helper 0.8.4 are installed and reviewed files match. Strict MODEYIELD2 activation remains unchanged. USB/Bluetooth hardware type alone does not establish delivery. This is diagnostic evidence, not an event-delivery fix or live automatic-return acceptance. See [terminal stream evidence](docs/STREAM_COVERAGE_DIAGNOSTICS.md).

## Install

Run `./install.sh --check` for read-only environment checks, then `./install.sh` to prepare paths, copy the foreground observer and install the local plugin. Refresh the app's MCP connection after updating; already connected chats can retain an older catalog. The observer installer is `python3 install-indicator.py`. Remove only that indicator with `python3 uninstall-indicator.py`.

## Use

Inspect each fresh screenshot before input. Coordinates use logical monitor units. Keyboard/text input must acquire focus in the same call. Bounded sequences allow 1–8 steps and begin with an observed click or a visible focus shortcut. Discrete wheel steps and paced Unicode composition are supported; clipboard access is absent. Pointer movement starts from a fresh, read-only GNOME pointer snapshot mapped to the selected monitor; missing mapping or an off-monitor pointer refuses input. Dispatch does not prove semantic success.

After uncertain input, obtain and inspect `desktop_observe` and pass its recovery token before further input. Never replay automatically. Optional accessibility identities are single-use and refuse ambiguous/protected/stale controls without fallback. Some connections return AccessDenied.

Call `desktop_close` on completion or error and check `portal_closed_confirmed` and `cleanup_warning`. Cancellation, client disconnection, process termination and idle expiry also close the session. Portal closure is attempted before bounded capture teardown. Blocking OS calls can still delay cleanup; use GNOME's native sharing control if closure cannot be confirmed. The portal does not reliably distinguish human from synthetic input. With default settings, moving the physical mouse alone is not an automatic cancellation signal.

## Retained sharing and mouse return

Default interruptions still close sharing. With explicit authorization, start a new native-protected session with `physical_takeover=true`, `interruption_policy="retain-sharing"`, and `pointer_motion_return=true`. Covered nonzero relative mouse motion pauses input, releases virtual held input and stops backend capture while preserving the existing portal consent. After 1.5 seconds of observed quiet, the backend can make one verified relative return to the last confirmed assistant point in the same foreground and monitor layout, then take a fresh screenshot. It never replays the interrupted action or queued work.

A missing confirmed point, changed foreground or pointer outside the shared monitor keeps control paused. `desktop_pause` provides a manual pause under retained-sharing policy; `desktop_resume(pause_id=...)` requires the current status token and returns a fresh image and new observation tokens. Inspect a new `desktop_observe` result after automatic return before deciding the next action. Keys, buttons, wheel/absolute/unknown activity, native faults, endpoint mismatch, lock, privacy Stop, revocation, topology changes, disconnection and expiry remain terminal. Only covered `REL_X`/`REL_Y` motion yields; this is not universal pointer support or human-provenance proof. The original 120-second native lease is never extended.

Installed 0.8.8/helper 0.8.2 failed the third live mouse-return trial: the human confirmed movement, but no native motion yield arrived. Candidate 0.8.9/helper 0.8.3 requires strict streamed REL_X/REL_Y calibration through MODEYIELD2 before activation. This prevents weaker activation; it does not repair event delivery. Plugin 0.8.9/helper 0.8.3 are installed and reviewed runtime files match. A fresh actual 0.8.9 provider reports the expected build, matching disk sources, seven tools, closed sharing and zero held input. Live automatic return remains failed/unresolved pending event-delivery evidence. See [strict coverage](docs/STRICT_RELATIVE_COVERAGE.md). See [retained-sharing contract](docs/RETAINED_SHARING.md).

## Verify

[Live 0.7.5 evidence](docs/LIVE_0_7_5.md) records the native dialog save/reopen workflow, actual themed glow/restoration and a human-confirmed Alt+Tab during a guarded wait.

`/usr/bin/python3 -m unittest discover -s tests` checks input validation, release/cancellation/disconnect behavior, fresh capture recovery, target identity and uncertain-input reconciliation without sharing. `python3 tests/check_loader.py` checks the real app loader and all seven schemas in a temporary Codex home. The indicator bridge has isolated transport tests; current live outcomes and remaining acceptance gaps are documented in docs/RELEASE_STATUS.md. Do not run a headless GNOME compositor on a live user manager: it can change activation display settings even with a private D-Bus bus. Use a separate test environment for graphical tests.

Source remains private; reuse licensing is deferred. No compensation or distribution terms are assigned. See docs/LICENSING_REVIEW.md.

## Consent and foreground target

Do not launch/focus apps through command runners before consent. Start sharing, inspect its image, then use the observed GUI. Each action uses window_observation_id from that image. Focus/geometry/context changes interrupt ordinary batches and close the session; no automatic focus reclaim, retry or restart occurs. An intentional GUI launch is one explicit focus_transition gesture, with fresh inspection afterward. See docs/FOCUS_GUARD_0_7_1.md for exact guarantees and limitations.


Optional `desktop_start(physical_takeover=true)` requires a separately installed root-owned native helper. After personal screen-sharing consent, GNOME asks for administrator authorization before screenshots or virtual input begin. The helper receives kernel keyboard/pointer events internally and reduces them to activity/fault signals; raw event payloads and descriptors are never exported to the assistant or desktop backend. It drops privileges, uses a private authenticated channel and watches session/device lifecycle. Default false launches no native monitor and needs no administrator prompt. This is kernel activity classification, not human attestation or atomic priority over already delivered input. See [native helper](native-activity/README.md) and [live status](docs/RELEASE_STATUS.md).


A fresh actual 0.8.10 provider verified the expected build, matching disk sources and all seven tools with sharing closed and zero held input; the installed helper hash matches. No new sharing or live event-delivery trial was performed, and the root cause remains unresolved.


A fresh actual 0.8.11 provider verified build `d9365aaf2ec194b81bb855405f8737bbb3a2e813779550309bc88fd17acf0eb9`, matching disk sources and all seven tools, with sharing closed, zero held input and capture/input disabled. All 411 Python tests, 16 native fixtures, loader/schema discovery and skill validation pass. No new live trial was performed; mouse-event delivery and automatic return remain unresolved.
