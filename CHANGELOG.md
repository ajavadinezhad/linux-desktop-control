# Changes

## 0.6.4

- Recover a stalled capture stream once under existing consent, without replaying input or substituting cached images. Retain cancellation and frame age checks; drop-only rate limiting avoids duplicated frames.
- Add six capture recovery regressions; 159 automated tests pass.
- Complete 49 scoped real app/control assertions, including Chrome/Firefox multilingual workflows, Files, GNOME window controls and human Pause/Continue/Stop. Document focus and timing failures plus remaining limits in docs/ACCEPTANCE_0_6_4.md.

## 0.6.3

- Reject malformed tool arguments without disconnecting the backend.
- Ignore outdated Pause events before they can interrupt a newer session.
- Honor Emergency Stop even with an outdated toolbar epoch.
- Reject boolean input counts, wheel steps and durations, and non-string key names before input.
- 153 automated tests pass; new host live acceptance remains pending.

## 0.6.2

- Resolve a uniquely focused editable control across multiple reported active windows; retain ambiguity and password refusal.
- Refuse incomplete window enumeration and accessibility replies arriving after the inspection deadline.
- Check the supported environment and dependencies before installation makes changes; provide a read-only check command.
- Preserve the full monitor by default in the demo recorder, report remaining time and stop reasons in a private atomic sidecar, and clean up failed empty output reservations.
- 149 automated checks pass. Historical live app acceptance remains scoped to 0.6.1; new live acceptance is pending.

No GNOME consent, human toolbar controls or host approval policies were bypassed or changed.
