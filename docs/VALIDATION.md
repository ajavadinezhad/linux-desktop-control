# Validation

## 0.7.6 release candidate

The combined isolated suite passes 194 tests. The real application loader confirms version 0.7.6 and exactly five tools: desktop_start, desktop_observe, desktop_action, desktop_status and desktop_close. Loader assertions include the explicit, default-off physical_takeover option. Tests use fake settings and isolated subprocesses for crash/recovery checks; no live sharing or preference activation is needed.

Canonical source, installation staging and the installed cache match for desktop.py, indicator_bridge.py, window_guard.py, cursor_glow_service.py and cursor_theme.py. Installed helper files match revision 4. Cursor assets are installed but not activated. The new device-source observation candidate still requires the updated helper to be loaded manually and real live acceptance; automated tests and copied helper files do not establish that acceptance.

## Historical 0.7.1 verification

Automated tests cover core input, exact argument validation, held-input release, cancellation, disconnect, stale publication fences, capture recovery, target identity and recovery tokens. The real app loader checks five tool schemas without sharing. Indicator bridge tests exercise owner binding, active state publication and cleanup with an isolated fake transport. The indicator extension uses no pointer mutation, event capture, key grabs or reactive actors. No live-host acceptance of 0.7.1 is claimed.

Historical development evidence is preserved in version-control history. Earlier headless tests changed user-manager activation display variables; those values were restored and the unsafe fallback harness was removed. The current suite does not launch graphical compositors on the live desktop.

Historical result: 120 unit tests pass; real loader and installed-backend discovery each confirm exactly five tools at version 0.7.1. Installed source/skill hashes and scoped tool rules match. No sharing request or live input was used for this verification.

Version 0.7.1 input requires loaded foreground-observer protocol 2 and a fresh window_observation_id. No live guard acceptance yet. See FOCUS_GUARD_0_7_1.md.
