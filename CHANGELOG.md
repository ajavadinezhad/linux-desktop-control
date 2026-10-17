# Changes

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
