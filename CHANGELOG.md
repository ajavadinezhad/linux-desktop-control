# Changes

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
