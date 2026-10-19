# Fresh scenario audit

This audit restarts from the current source and prior failed evidence. Passing isolated tests does not establish physical input coverage, universal application support, or every possible timing interleaving. No live sharing was started during this code audit.

Final verification: **304 Python tests and eight native fixture tests pass**. The real plugin loader discovers version **0.8.4** and all five tools. The installed native helper binary matches its reviewed 0.8.0 package; no native package update or administrator grant was needed for these Python repairs.

| Area | Scenarios checked | Evidence / result |
| --- | --- | --- |
| Consent and discovery | Missing helper, cancelled/denied portal, administrator rejection, no screenshot/input before calibration, stale providers | Existing isolated consent, loader, physical-guard and runtime tests; historical live timeouts retained |
| Action validation | Invalid coordinates, NaN, booleans, focus fields, nested sequences, text/Unicode budget, partial execution | Fresh focus-object injection reproduced and fixed; regression rejects entire malformed batch before input |
| Native arming | Calibration timeout, late ARM reply, cancellation/revocation/close during reply, lost acknowledgment | Fresh late/cancelled ARM acknowledgment defects reproduced and repaired with post-read and synchronized publication fences |
| Input cleanup | Release failure, portal-close failure, partially confirmed releases, retry, already-closed portal | Fresh unresolved-held-state loss reproduced and repaired; unresolved inputs remain tracked until release or portal closure is confirmed |
| Session lifecycle | Overlapping cleanup, delayed native cleanup, fresh start, stale observer callbacks | Fresh cross-session cleanup race reproduced; lifecycle serialization and per-session owner cancellation repaired |
| Transport | Queued requests, cancellation, EOF, malformed messages, duplicate request IDs, blocked status/main output | Startup-status, cancellation, disconnect and publication tests; duplicate IDs must preserve original cancellation ownership; no live authority from status snapshots |
| Window and target fences | Focus away/back, window resize, geometry/epoch change, protected UI, stale/reused observation, editable identity | Existing window, transition, target, recovery and display mapping tests |
| Capture | Timeout, one capture-only reconnect, stale frame, foreground loss around publication | Existing capture recovery and transition tests; effects already delivered cannot be undone |
| Cursor and notifications | Startup cancellation, readiness after revocation, crash/watchdog, settings changed by user, unknown notification reply | Fresh cursor startup/close defects reproduced; startup cancellation repaired; notification uncertainty remains fail-closed |
| Native confinement | Descriptor remapping at many device counts, seccomp, terminal descriptor closure, session watch, malformed protocol, topology/lease/heartbeat loss | Eight native fixture tests pass with extracted compiler/headers; fixtures do not open real input devices |
| Installation | Versioned cache, custom Codex home, stale disk build, discovery of five tools | Existing isolated installer/runtime tests and real loader check; current chat can retain an older provider |

## Live acceptance still required

1. Both keyboard and pointer categories calibrated successfully in one consented 0.8.4 trial, followed by ARM and a fresh screenshot. This establishes those challenged source categories at that moment, not every device or reliable takeover. Earlier missing-keyboard evidence remains historical.
2. A physical key during same-window automated typing must cancel the remaining batch and confirm release/closure. Previous live typing failed; it is not converted into a pass by this audit.
3. Physical activity during a held-button drag must cancel remaining movement and confirm release/closure.
4. A real two-monitor setup exposed a setup limitation: GNOME overview is fenced to the primary display while the shared chat display was secondary. Control was closed before clicking/typing. Select the actual primary launcher display for the next test; do not expand bounds to bypass the guard. Broader multi-monitor/mixed-DPI behavior remains unverified.

## Explicit coverage limits

Calibration establishes at least one source in each category, not every enumerated device. An exclusive evdev grab can suppress primary records; held-state polling can miss a complete tap between samples and cannot detect button-free relative motion on a grabbed pointer. Kernel activity is not proof of human provenance. No atomic input arbitration, zero-event race, universal app support or hard end-to-end cancellation latency is claimed.

A release claiming universal physical takeover is blocked by these limits and by the unpassed host typing/drag tests.


## Diagnostic update 0.8.5

The latest primary-display 0.8.4 trial detected both challenged input categories but timed out waiting for quiet. The human confirmed full release and hands off. The final held state was false. No task capture/input occurred; portal closure was confirmed with zero held virtual input and no cleanup warning. This does not identify the cause or establish takeover acceptance.

Version 0.8.5 adds fixed coarse terminal idle diagnostics; helper package 0.8.1 appends a backward-compatible report after closing raw descriptors. No keys, coordinates, device identities or exact event timestamps are exported. Calibration, classifiers, timing and armed cancellation requirements are unchanged. Isolated fixtures reproduce metadata-only and pending-queue quiet blockers, without establishing the live cause.

Verification: 309 Python tests, nine native fixtures and the five-tool loader check pass. Plugin 0.8.5 and helper 0.8.1 are installed. Fresh actual provider reports matching disk sources, closed sharing, capture/input disabled and zero held input. Installed helper/policy bytes match the reviewed package. Live same-window typing and held-button dragging takeover remain unverified; public distribution remains blocked. Source remains private and reuse licensing is deferred.


The installed 0.8.5 live trial successfully calibrated both categories, acknowledged ARM and returned an inspected primary-display screenshot (logical1920x1200, pixels3840x2400). A guarded Super transition reached primary overview. A single observed click did not activate the intended editor card; the subsequent foreground frame remained on the other monitor. A pointer endpoint estimate came from a resized preview and is not precise evidence of a scaling defect. The portal contract specifies logical coordinates, matching the current sender. Work stopped before any text or drag; explicit closure confirmed zero held input, no release failures, no cleanup warning and helper exit0. Calibration now has successful live evidence; typing and held-button drag takeover remain unverified. Detailed local evidence: release/LIVE_0_8_5_STARTUP.json (outside the source repository).


## Endpoint safety candidate 0.8.6

Pointer dispatch no longer counts as observed arrival. The backend requires two fresh compositor endpoint samples before click/button or scroll effects, after moves, and along held-button drag paths. Missing/invalid/mismatched endpoints cancel without coordinate compensation or replay; held virtual input is released. The 350ms acceptance budget is checked around observer reads; it is not a hard wall-time bound on an in-flight D-Bus call. This adds protection against the observed targeting mismatch but does not fix or establish scaled-display mapping. Status exposes validated stream geometry for the next consented diagnostic. Independent source cross-review found no blocking defect. No new live acceptance is inferred.

Verification of the endpoint safety update: all320 Python regression tests and the real five-tool loader check pass. Version0.8.6 is installed. The native helper remains0.8.1; its nine native fixtures were already passed with no subsequent native code changes. Scaled pointer mapping and real same-window typing/held-button dragging remain open.


## Relative transport candidate 0.8.7

The current GNOME absolute-motion path exposes logical stream bounds but divides coordinates by monitor scale downstream. The replacement sends a single relative logical displacement from a freshly observed pointer inside the consented monitor, then requires endpoint confirmation before any further displacement or effect. There is no absolute fallback, coordinate multiplication, clamping, correction retry or cross-monitor approach.

Every consented startup binds the selected stream geometry to GNOME DisplayConfig ownership and the full normalized display state before capture. Each input rechecks that binding. Changed or ambiguous geometry, display ownership/layout/mode/scale changes, physical layout mode, rotation and mirroring refuse input. Scope is logical monitor layout with unrotated, unmirrored outputs. Status remains cached and read-only; raw release cleanup remains available after mapping invalidation. The new runtime modules are included in the frozen source fingerprint.

A separate read-only host check successfully matched primary logical rectangle[0,240,1920,1200] at scale2. This is metadata validation, not live transport or physical takeover acceptance. The most recent0.8.6 trial closed before ARM with no kernel input records despite successful state queries; no task capture/input occurred and explicit cleanup confirmed portal closure, zero held input and no warning. Live relative targeting, same-window typing and held-button dragging remain required.

Version0.8.7 is installed. Verification:333 Python tests and the five-tool loader check pass; native helper0.8.1 is unchanged from its nine passing fixtures. No live relative-transport or takeover acceptance is claimed.


Latest installed0.8.7 physical startup trial: pointer calibration credit was observed, keyboard credit was not. Terminal diagnostics reported missing-category, settled relative motion, no held input and no pending input/topology/owner records. This was not an idle-wait blocker. It timed out before mapping construction, capture or task input; no app launch/click/text/drag occurred. Explicit cleanup confirmed closed portal, zero held input and no warning. This does not establish whether the human performed the keyboard challenge, nor a keyboard failure cause. Evidence: adjacent release/LIVE_0_8_7_CALIBRATION_MISSING_KEYBOARD.json. New transport and takeover acceptance remain unverified; no automatic restart.


## Live typing takeover — scoped pass

Installed0.8.7 calibrated and armed successfully on primary logical rectangle[0,240,1920,1200], with the DisplayConfig scale2 binding. Guarded relative overview targeting, editor activation and a new unsaved public scratch tab passed; a41-character public cue rendered exactly. No personal document was edited.

A392-character ASCII typing request was interrupted after209 completed characters and423 attempted input events, before its first step completed. The native helper reported activity/held and exited0. No window-loss reason was reported. Explicit cleanup confirmed portal closure, zero held input, one release attempted and confirmed, zero failed releases, and no cleanup warning. The human confirmed a physical letter keypress while text was still growing. This is a scoped successful same-window typing interruption, not universal device coverage or a measured hard stop bound. Final text rendering was not inspected after closure; no replay occurred. Adjacent release evidence:LIVE_0_8_7_TYPING_NATIVE_STOP.json. Held-button drag acceptance is still pending.


The first drag startup timed out before capture/input or a virtual button press. The live operator identified a caller-orchestration defect: the initial asynchronous desktop_start wrapper yielded after the default30seconds, so status polling and the human cue arrived near the calibration deadline. No actual drag occurred and a release count inherited from the typing session is not new drag evidence. Explicit cleanup confirmed portal closure, zero held input and no warning. The next explicitly authorized trial must yield desktop_start after one second, promptly poll the independent startup-status lane, and relay waiting/acknowledged readiness immediately; no backend calibration requirement is weakened. Evidence:adjacent release/LIVE_0_8_7_DRAG_CALIBRATION_TIMEOUT.json.
