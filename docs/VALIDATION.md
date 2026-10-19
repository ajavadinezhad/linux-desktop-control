# Validation

## Fresh 0.8.4 audit

See [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) for the current scenario inventory, reproduced defects, fixes and release blockers. Historical counts below describe their respective builds. No current physical typing or held-button drag acceptance is claimed.

## 0.8.0 native helper candidate

The replacement uses a separately installed administrator-authorized native helper, not the failed Clutter input filter. The 204-test isolated suite and real five-tool loader passed before adding four release-evidence tests; those four targeted tests pass. Native C collector, session watcher and confinement fixtures compile and pass separately with an extracted local GCC toolchain. Unix-socket fixture tests need a host run when the sandbox disallows socket binding. No real devices are opened by those fixtures.

The optional helper package contains only a root-owned executable and polkit policy. Live startup and browser input succeeded after descriptor cleanup. The user-confirmed one-second held-key attempt failed: 960 characters completed without cancellation (result0e2c7f56251f467c87cfde4c071a34a7). Held-button dragging remains unverified. The complete Python suite passes228tests. Live calibration failed; a diagnostic trial also timed out without a report. Final race/diagnostic fixes pass isolated C collector tests, including actual seccomp and sockets, but have not passed live acceptance. Tests are not evidence of universal coverage or atomic input arbitration.

## Historical 0.7.6 candidate

The combined isolated suite passes 194 tests. The real application loader confirms version 0.7.6 and exactly five tools: desktop_start, desktop_observe, desktop_action, desktop_status and desktop_close. Loader assertions include the explicit, default-off physical_takeover option. Tests use fake settings and isolated subprocesses for crash/recovery checks; no live sharing or preference activation is needed.

Canonical source, installation staging and the installed cache match for desktop.py, indicator_bridge.py, window_guard.py, cursor_glow_service.py and cursor_theme.py. Installed helper files match revision 4. Cursor assets are installed but not activated. The new device-source observation candidate still requires the updated helper to be loaded manually and real live acceptance; automated tests and copied helper files do not establish that acceptance.

## Historical 0.7.1 verification

Automated tests cover core input, exact argument validation, held-input release, cancellation, disconnect, stale publication fences, capture recovery, target identity and recovery tokens. The real app loader checks five tool schemas without sharing. Indicator bridge tests exercise owner binding, active state publication and cleanup with an isolated fake transport. The indicator extension uses no pointer mutation, event capture, key grabs or reactive actors. No live-host acceptance of 0.7.1 is claimed.

Historical development evidence is preserved in version-control history. Earlier headless tests changed user-manager activation display variables; those values were restored and the unsafe fallback harness was removed. The current suite does not launch graphical compositors on the live desktop.

Historical result: 120 unit tests pass; real loader and installed-backend discovery each confirm exactly five tools at version 0.7.1. Installed source/skill hashes and scoped tool rules match. No sharing request or live input was used for this verification.

Version 0.7.1 input requires loaded foreground-observer protocol 2 and a fresh window_observation_id. No live guard acceptance yet. See FOCUS_GUARD_0_7_1.md.


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
