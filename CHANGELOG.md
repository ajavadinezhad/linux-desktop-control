# Changes

## 0.7.1

- Require consent and fresh visual inspection before any app launch/focus; GUI-only live orchestration example.
- Bind each input batch to a single-use foreground observation, geometry and monotonic context epoch. Cancel on unexpected target loss, release held input, invalidate queued work and close sharing.
- Remove accessibility focus reclamation. Intentional focus changes are single gestures requiring fresh inspection. No claim of physical takeover detection or atomic OS dispatch.
- No live acceptance of the new guard; protocol 2 must actually load before any future input test.

## 0.7.0

Simplify to five core desktop operations and an optional passive pointer label. Retain consent, input release, cancellation, target guards, fresh-frame checks and uncertain-input recovery. Close virtual input before bounded capture teardown. The system cursor is unchanged; no ring or duplicate cursor is drawn. No live 0.7.0 input test has been performed.
