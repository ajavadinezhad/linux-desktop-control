# Validation — 0.7.0

Automated tests cover core input, exact argument validation, held-input release, cancellation, disconnect, stale publication fences, capture recovery, target identity and recovery tokens. The real app loader checks five tool schemas without sharing. Indicator bridge tests exercise owner binding, active state publication and cleanup with an isolated fake transport. The indicator extension uses no pointer mutation, event capture, key grabs or reactive actors. No live-host acceptance of 0.7.0 is claimed.

Historical development evidence is preserved in version-control history. Earlier headless tests changed user-manager activation display variables; those values were restored and the unsafe fallback harness was removed. The current suite does not launch graphical compositors on the live desktop.

Current result: 99 unit tests pass; real loader and installed-backend discovery each confirm exactly five tools at version 0.7.0. Installed source/skill hashes and scoped tool rules match. No sharing request or live input was used for this verification.
