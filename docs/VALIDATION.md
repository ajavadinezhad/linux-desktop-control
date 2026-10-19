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


## Live typing takeover — scoped pass

Installed0.8.7 calibrated and armed successfully on primary logical rectangle[0,240,1920,1200], with the DisplayConfig scale2 binding. Guarded relative overview targeting, editor activation and a new unsaved public scratch tab passed; a41-character public cue rendered exactly. No personal document was edited.

A392-character ASCII typing request was interrupted after209 completed characters and423 attempted input events, before its first step completed. The native helper reported activity/held and exited0. No window-loss reason was reported. Explicit cleanup confirmed portal closure, zero held input, one release attempted and confirmed, zero failed releases, and no cleanup warning. The human confirmed a physical letter keypress while text was still growing. This is a scoped successful same-window typing interruption, not universal device coverage or a measured hard stop bound. Final text rendering was not inspected after closure; no replay occurred. Adjacent release evidence:LIVE_0_8_7_TYPING_NATIVE_STOP.json. Held-button drag acceptance is still pending.


The first drag startup timed out before capture/input or a virtual button press. The live operator identified a caller-orchestration defect: the initial asynchronous desktop_start wrapper yielded after the default30seconds, so status polling and the human cue arrived near the calibration deadline. No actual drag occurred and a release count inherited from the typing session is not new drag evidence. Explicit cleanup confirmed portal closure, zero held input and no warning. The next explicitly authorized trial must yield desktop_start after one second, promptly poll the independent startup-status lane, and relay waiting/acknowledged readiness immediately; no backend calibration requirement is weakened. Evidence:adjacent release/LIVE_0_8_7_DRAG_CALIBRATION_TIMEOUT.json.


## Held-button drag interruption — guard evidence

With corrected one-second startup yielding, the next0.8.7 trial calibrated and armed, verified the primary monitor binding, inspected the prior scratch text without replay, and prepared a100-point text-selection drag within the same editor. The virtual left button was pressed and the path partly progressed;39 input events were attempted before the pointer-endpoint mismatch guard cancelled the remaining action. No final capture was taken after closure. Explicit cleanup confirmed portal closure, zero held input, zero failed releases and no warning. Release counters increased from1 attempted/confirmed to2 attempted/confirmed, demonstrating one new successful virtual-button release during this drag.

The native helper did not report pointer activity first; its terminal reason was session-ended during cleanup. This establishes endpoint-guard interruption and button release, not native pointer-activity acceptance. Human confirmation of physical mouse movement during selection growth is pending. No retry or automatic restart occurred. Evidence:adjacent release/LIVE_0_8_7_DRAG_ENDPOINT_STOP.json. Confirmed typing takeover remains a scoped pass.


Human timing confirmation: the human confirmed physical mouse movement while the scratch selection was still growing. This establishes a scoped same-window drag interruption by the endpoint guard with a confirmed virtual-button release. Together with confirmed typing interruption, the requested same-window typing and dragging scenarios have both demonstrated stop-and-cleanup behavior on this host. The mechanisms differ: typing was interrupted by native held-input activity; dragging was interrupted by endpoint mismatch. Native pointer-activity-only cancellation, universal devices/apps, a hard stop-latency bound and final post-stop rendering remain unverified. This is a private candidate with scoped acceptance, not a universal readiness claim.


## Retained-sharing candidate 0.8.8 / helper package 0.8.2

Offline coverage now joins persistent fixed-epoch native yield/quiet/resume with per-operation cancellation, real virtual-UP cleanup, pipeline suspension, stale request/observation fencing and one production relative pointer return. Cases include no confirmed point, changed foreground, off-monitor pointer, new movement during acknowledgement/return/capture, terminal endpoint or native failure, blocked response publication, and sticky manual pause in both event orderings. The default remains terminal closure. No helper raw keys, coordinates or descriptors cross its channel.

The corrected full suite passes all 376 Python tests. All 12 native fixtures, the real seven-tool 0.8.8 loader/schema check and skill validation pass. Passing synthetic collector/controller/portal fixtures does not establish live hardware coverage. Plugin 0.8.8 and helper 0.8.2 are installed and their reviewed files matched. A fresh connected provider and live automatic-return acceptance remain unverified. The prior 0.8.7 human-confirmed typing stop and drag release remain scoped historical evidence only. See [retained-sharing contract](RETAINED_SHARING.md).


## Strict relative-coverage candidate 0.8.9 / helper 0.8.3

The third installed 0.8.8 mouse-return trial completed calibration/ARM and a confirmed cursor endpoint but observed no native yield before lease expiry. The human later confirmed movement; automatic return therefore failed live. Cleanup confirmed portal closure, zero held virtual input and no warning. Existing isolated pass counts did not establish that event route.

Offline reproduction demonstrated broad held/button/absolute pointer credit could pass the old calibration without the positional relative stream used for yielding. The replacement requires exact MODEYIELD2 acknowledgement and fresh streamed nonzero REL_X/REL_Y coverage, retaining the keyboard challenge and original release/quiet/deadline/ARM guards. It prevents weak activation and refuses missing evidence; it does not repair event delivery or prove a particular mouse is covered. No permission, ACL, device-group or grab-probe change is made. Plugin 0.8.9/helper 0.8.3 are installed and reviewed runtime files match. A fresh actual 0.8.9 provider verified the reviewed build, matching disk sources and all seven tools, with sharing closed and zero held input. The installed 0.8.3 helper package/payload hashes match. Live automatic return remains failed/unresolved pending event-delivery evidence; no new sharing trial was performed. See [strict coverage](STRICT_RELATIVE_COVERAGE.md). The frozen candidate passes all 378 Python tests, 14 native fixtures, the real seven-tool 0.8.9 loader/schema check and skill validation. The reviewed helper package contains only its two root-owned payload files, with no maintainer scripts or new service. Legacy MODEYIELD compatibility does not gain the strict guarantee. Before requesting sharing, require a freshly connected server_version=0.8.9 with the reviewed matching source build; refuse older cached providers. MODEYIELD2/MODEYIELD2_OK then occurs after personal sharing/admin authorization and before calibration/capture/input. Do not use an old provider to exercise retained sharing against the new helper.


## Terminal stream diagnostics candidate 0.8.10 / helper 0.8.4

This diagnostic-only update adds four optional fixed booleans after raw/lifecycle descriptor closure. They distinguish strict calibration credit, any primary record after ARM, eligible relative records after ARM and a successful YIELDED send. They contain no event codes, values, coordinates, device identities, counts or timestamps. A primary record can be metadata/synchronization rather than motion. Missing evidence is not proof of human stillness.

The first terminal reason and stop callback precede optional parsing. Bounded reads do not extend the original report deadline or change activation authority. Legacy report prefixes remain intact; malformed, missing or late detail is optional, including normal CLOSE. An undeliverable optional CLOSE report preserves successful shutdown. MODEYIELD2 and all strict relative-stream activation requirements remain unchanged. Installed 0.8.9 is the prior baseline. Diagnostic candidate 0.8.10/helper 0.8.4 is now installed; all 14 plugin files match canonical source and the helper payload matches. Event delivery/live automatic return remain unresolved. No live trial, permission change or grab probe is part of this update. See [terminal evidence contract](STREAM_COVERAGE_DIAGNOSTICS.md).

Frozen diagnostic-candidate verification: all 385 Python tests and 15 native fixtures pass. These include terminal descriptor closure, fixed booleans, split/coalesced frames, callback-before-read ordering, malformed/missing/late evidence and undeliverable normal-CLOSE diagnostics. This does not establish live source delivery.

The real seven-tool 0.8.10 loader/schema check, skill validator and package inspection also pass. The package contains exactly the root-owned helper/policy payloads with no maintainer scripts or permission change.


A fresh actual 0.8.10 provider verified the expected build, matching disk sources and all seven tools with sharing closed and zero held input; the installed helper hash matches. No new sharing or live event-delivery trial was performed, and the root cause remains unresolved.


## Post-ARM readiness candidate 0.8.11 / unchanged helper 0.8.4

Retained MODEYIELD2 startup now remains unready after initial ARM. A distinct 30-second mouse-only armed-path YIELDED/QUIET/RESUME/ARMED challenge and resolved fixed notice must precede capture/input. Snapshots expose an allowlisted stage, separate verified flag and coarse remaining budget without backend queries or authority mutation. Default close-policy startup and helper bytes are unchanged.

Offline coverage includes fixed content/phase allowlisting, uncertain notice ownership and separate bounded close budgets, expired cue budgets, missing/false readiness proof, source activity before/during capture and before publication, suppressed normal startup callbacks, actual fake-peer armed-path exchange, cancellation and reentrant owner/session closure. This is a false-readiness repair; physical event delivery and live automatic return remain unresolved. No helper install, permission change, grab probe or live sharing trial is performed. Frozen verification passes all 411 Python tests, 16 native fixtures, the real seven-tool 0.8.11 loader/schema check and skill validation. Native helper package/bytes remain unchanged at 0.8.4. See [gate contract](POST_ARM_READINESS.md).


A fresh actual 0.8.11 provider verified build `d9365aaf2ec194b81bb855405f8737bbb3a2e813779550309bc88fd17acf0eb9`, matching disk sources and all seven tools, with sharing closed, zero held input and capture/input disabled. All 411 Python tests, 16 native fixtures, loader/schema discovery and skill validation pass. No new live trial was performed; mouse-event delivery and automatic return remain unresolved.

## 0.8.12 authorization-release settling scope

New offline fixtures cover the actual collector mainloop withholding CALIBRATING while authorization input is held, then emitting a fresh cue after release; no drained authorization credit; queued boundary, stale events, duplicate command rejection, five-second timeout, query failure and original 120-second lease refusal. Adapter fixtures cover six-second acknowledgement bounds, heartbeat, silent/dead peer, cancellation, revoked authorization, late/unexpected tokens and lease expiry. The desktop snapshot regression accepts `settling` only as an opening state with no challenge notice, calibration readiness, capture or input. Strict post-ARM readiness remains required. Frozen validation passed 419 Python tests in 19.613 seconds, 18 native fixtures in 15.478 seconds, seven-tool loader/schema discovery and skill validation. Plugin 0.8.12 and helper 0.8.5 installed successfully; all 14 plugin files match canonical source. Helper package SHA256: `571350f65cf0ab0439cea6657a9f04339f4505980827971edd085d1c6743ddd3`. These fixtures do not establish live mouse delivery.

A fresh actual 0.8.12 provider verified build `cd15c911aab846b0e04cbdddd8b845bddd7439211b779bd9dd492ebd58c7b249`, matching disk sources and all seven tools, with the portal closed, zero held input and capture/input disabled. Installed helper 0.8.5 binary and policy hashes match the reviewed package. This read-only verification is not live event-delivery or automatic-return acceptance; no new sharing trial was performed.
