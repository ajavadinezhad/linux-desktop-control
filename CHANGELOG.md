# Changes

Current status: see [release status](docs/RELEASE_STATUS.md). Older entries below are checkpoint records.

## 0.8.17 — reduce pointer-action overhead

- Remove duplicate post-displacement endpoint passes while preserving two fresh samples for every point and a separate check immediately before button-down.
- Remove blanket trailing waits after drag, move, scroll and explicit wait; keep click/key/text pacing and the screenshot settling fence.
- Recheck exact typed display state against its validated binding without re-deriving unchanged geometry. Fresh owner/state/owner queries remain mandatory.
- Report coarse input and capture durations; recommend bounded observed batches instead of unnecessary observation calls.
- 450 isolated Python tests and loader/schema validation pass. Live speedup has not been measured; native helper is unchanged.


## 0.8.16 candidate — fit oversized window on shared monitor

- Dedicated single Alt+F10 resize toggle with center/titlebar midpoint and uniquely largest overlap identifying the shared monitor. Same identity and whole shared containment required around capture; no retry, focus reclaim or automatic follow-up.
- Five new targeted tests and independent review pass; full suite pending. Not installed/live accepted; helper0.8.6 and native duration are unchanged.

## 0.8.15 installed — validation and scoped live startup

- All 14 reviewed plugin files match; fresh actual provider build/disk/seven-tool verification passed. Helper 0.8.6 binary matches and policy is unchanged.
- Frozen validation: 438 Python tests (21.303s), 20 native fixtures (16.061s), loader/schema pass.
- Initial 600-second live lease negotiation and both gates succeeded, reaching a new blank Impress presentation with about 560 seconds remaining. This is not full ten-minute expiry or a completed demo; no existing personal deck was edited.

### Earlier preparation notes

## 0.8.15 candidate — bounded initial native duration

- Select an initial native lease of 120–600 seconds (default120), exactly acknowledged by helper0.8.6 before calibration. Original READY anchor and heartbeat remain unchanged; no active renewal or long-request fallback.
- Recorder maximum900 seconds, unchanged default120; recording does not grant input authority.
- New lease Python8/native2 and recorder6 targeted tests pass; full suite pending, not installed/live accepted. Prior14 normalization+relocation is scoped live accepted, not completion of the five-slide demo.

## 0.8.14 candidate — normalize before a separate monitor move

- One dedicated Alt+F10 resize toggle for a partly off-screen focused window on the other of two verified monitors; actual binding stays read only. Requires same identity and full source containment afterward. Existing move remains strict and separate; no retry or maximize-state claim.
- Five new normalization tests pass; full suite pending. No native/helper change; normalization is not live accepted.

## 0.8.13 candidate — explicit current-window monitor move

- Dedicated opt-in, single Super+Shift+Arrow GUI transition; two verified monitors and unchanged default binding only. Foreground remains fenced through modifiers, then same-window arrival wholly on the shared monitor is required around capture. No retry or unseen-content claim.
- Frozen behavior suite passes 424 Python tests; native/helper 0.8.5 is unchanged (18-fixture baseline). Not installed or live accepted.

## 0.8.12 — bounded authorization-release settling

- Installed plugin 0.8.12/helper 0.8.5; all 14 reviewed plugin files match. Frozen verification passes 419 Python tests, 18 native fixtures, seven-tool loader/schema discovery and skill validation. No new live trial.

- Helper 0.8.5 waits at most five seconds for held authorization input to release and source queues to drain before CALIBRATING. Drained authorization events grant no calibration credit.
- The controller waits at most six seconds with heartbeat, cancellation and original-lease checks; read-only startup status exposes `settling` without capture/input or challenge notice.
- Strict MODEYIELD2 calibration and retained post-ARM readiness remain unchanged. This fixes a reproduced startup race, not the unresolved live event-delivery cause or automatic-return behavior.


## 0.8.11 candidate

- Frozen offline verification: 411 Python tests, 16 native fixtures, real seven-tool loader/schema discovery and skill validation pass; this is not physical delivery acceptance.

- Retained MODEYIELD2 startup requires a separate post-ARM mouse-only YIELDED/QUIET/RESUME/ARMED exchange, bounded by its original 30-second budget and helper lease, before ready/capture/input. Default close policy and helper 0.8.4 remain unchanged.
- Add fixed allowlisted mouse-only notice, distinct startup stage/verified flag/coarse remaining seconds, per-known-notice bounded cleanup and explicit startup capture/publication checks. No arbitrary notification text/actions, activation or new permissions.
- Prevent false READY; event-delivery cause and live automatic return remain unresolved. Plugin is installed; no live trial or helper reinstall.

## 0.8.10 candidate

- Frozen verification: 385 Python tests and 15 native fixtures pass. This is not live event-delivery acceptance.

- Add optional terminal-only OBS_DIAG four-boolean evidence after raw/lifecycle descriptor closure. Preserve original report prefixes and first terminal outcome; callbacks precede bounded best-effort parsing. No raw keys/values/coordinates/identities/counts/timestamps are exported.
- Normal CLOSE diagnostics may be unavailable; failed optional export does not change successful close. Strict MODEYIELD2 activation and lease/input guards remain unchanged. Diagnostic-only candidate is installed and file-matched, but does not repair event delivery or establish live automatic return. No device permission change or grab probe.

## 0.8.9 candidate

- Verification: 378 Python tests, 14 native fixtures, the real seven-tool loader/schema check and skill validation pass; live automatic return remains blocked/unverified.

- Require MODEYIELD2/strict acknowledgement for retained sharing and fresh streamed nonzero REL_X/REL_Y calibration credit before activation. Held/button/absolute/other-axis evidence alone no longer suffices; resynchronization clears strict credit. No legacy negotiation fallback.
- Reproduce the prior false-coverage gap offline and record the human-confirmed 0.8.8 live motion-detection failure. This prevents weak activation, not missing event delivery. This strict-activation safeguard was subsequently installed; live automatic return remains blocked/unverified. No new permissions or grab probes.

## 0.8.8 candidate

- Add explicit retained-sharing pause/resume, independent operation cancellation, raw virtual-input release and capture suspension without reopening the portal. New generations discard queued actions and old observation tokens. Default behavior remains close.
- Optional native-protected mouse return yields only on covered nonzero REL_X/REL_Y. After 1.5 seconds of observed quiet and an epoch-bound resume handshake, return once to the last confirmed point in unchanged foreground/mapping, verify arrival, and capture freshly. Never replay input or reclaim focus.
- Helper package 0.8.2 negotiates persistent motion/quiet/resume tokens; raw event privacy and the original 120-second lease remain unchanged. Keys/buttons/wheel/ABS/unknown activity and terminal session/device/privacy failures still close.
- 376 Python tests pass, including fake-channel native-controller-to-production-pointer-return integration. Candidate automatic return and persistent native motion observation remain unverified live.

## 0.8.0

- Accept known kernel output/configuration feedback without treating it as human activity; preserve unknown/lost-stream refusal and add distinct drain failure codes.

- Replace the failed optional Clutter filter with a separately authorized native device-activity helper. Missing or untrusted helper refuses before sharing. Default control needs no helper or administrator authorization.
- Split portal consent from capture: administrator approval and native ARM acknowledgment precede screenshots/input. Activity and faults invalidate pending work independently of foreground tracking.
- Add root-owned optional helper package: read-only input descriptors, UID/capability drop, private fixed-token channel, peer pidfd, topology/session monitors, heartbeat expiry and seccomp confinement. No persistent service, setuid installation, input-group change or device ACL change.
- Require a fresh keyboard/pointer calibration before protected capture/input; refuse on missing activity rather than treating handshake readiness as device coverage. Split heartbeat, lease and clock failure exit diagnostics.
- The earlier same-window typing test failed; no live success is claimed for the replacement until separate typing and dragging tests pass.

## 0.7.6

- Bound cursor-watchdog heartbeat writes; recover safely after owner/worker failure, settings errors and journal failures. Preserve later user choices.
- Reject protected foreground contexts and invalid monitor-coordinate mappings. Add negative-origin and fractional logical-coordinate coverage.
- Add disabled-by-default native device-source activity cancellation candidate. Explicit physical_takeover opt-in requires helper revision 4; manual helper reload and physical acceptance remain outstanding. Unknown sources are unsupported; device-source classification does not attest human provenance.
- Preserve previous live evidence separately from isolated tests and hardware-dependent checks.

## 0.7.5

An expired matching observation with unchanged foreground returns a fresh image and explicit action_refused with zero input, avoiding a new portal session for read-only refresh. Context/generation mismatch and protected UI still close. No automatic action replay. Live 0.7.4 verified Save/Open native dialog transitions and actual themed cursor glow/restoration; file reopen and physical takeover remain pending.

## 0.7.4

- Keep approach/modifiers guarded until the activating press of one explicit transition; allow Save/Open chords with releases only afterward.
- Settle only no-foreground-window, require a stable read-only context, retain publication fences and never replay input. Keep a signal guard armed between published observations.
- Add disabled-by-default actual Xcursor glow with validated Yaru-derived assets, explicit desktop-wide scope, separate watchdog, durable original/unset journal, compare-and-restore and startup recovery. Preserve later user preferences.
- New helper reload is not required. Live acceptance is documented separately.

## 0.7.3

The live Save Page As click exposed an available-to-available foreground change during capture. For explicit single transitions only, discard that image and allow one capture-only retry within the existing two-second deadline. Never repeat the gesture. Unavailable/protected context and the final publication fence still close immediately. No helper change or GNOME logout is required. Live save/reopen remains pending.

## 0.7.2

The first live 0.7.1 GUI-launch trial closed safely during transient foreground unavailability, before the human Alt+Tab test. Add a bounded read-only settling wait after an explicit single transition gesture only. No input replay or focus reclamation; ordinary batch fences remain immediate. The backend settling correction keeps protocol 2. Fresh pointer capability from helper revision 3 is now required before consent. First movement uses the current authorized pointer snapshot, validated monitor mapping and elapsed-time interpolation instead of a warp or stale cached position. Historical context signals do not cancel newer observations; newer epochs still cancel. Helper revision 3 additionally keeps the passive label visible in the normal app overview; loading that separate helper change requires a manual GNOME extension reload/login. A lost heartbeat now invalidates work and closes sharing instead of silently losing the helper. Live Alt+Tab acceptance remains pending.

## 0.7.1

- Require consent and fresh visual inspection before any app launch/focus; GUI-only live orchestration example.
- Bind each input batch to a single-use foreground observation, geometry and monotonic context epoch. Cancel on unexpected target loss, release held input, invalidate queued work and close sharing.
- Remove accessibility focus reclamation. Intentional focus changes are single gestures requiring fresh inspection. No claim of physical takeover detection or atomic OS dispatch.
- No live acceptance of the new guard; protocol 2 must actually load before any future input test.

## 0.7.0

Simplify to five core desktop operations and an optional passive pointer label. Retain consent, input release, cancellation, target guards, fresh-frame checks and uncertain-input recovery. Close virtual input before bounded capture teardown. The system cursor is unchanged; no ring or duplicate cursor is drawn. No live 0.7.0 input test has been performed.


Installation verification: plugin 0.8.13 is installed, and all 14 reviewed plugin files match canonical source. A fresh actual provider verified the expected build, matching disk sources, all seven tools and the window_move_to_shared schema. Sharing is closed with confirmed portal closure, zero held input and capture/input disabled. The real monitor move has not been tested live. Earlier candidate installation statements above describe the pre-install checkpoint.
