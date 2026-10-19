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
