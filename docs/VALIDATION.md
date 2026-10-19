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
