# Terminal stream evidence — 0.8.10 candidate / helper 0.8.4

> Version-specific investigation record. Status statements below describe that checkpoint. See [current release status](RELEASE_STATUS.md) for installed versions and later acceptance.

Diagnostic-only plugin 0.8.10/helper 0.8.4 is installed and reviewed files match. The strict MODEYIELD2 requirement introduced by 0.8.9/helper 0.8.3 stays in force. Mouse-event delivery is unresolved; no live test, permission change, input grab probe or activation fallback is part of this update. A physical USB/Bluetooth device description does not establish that its records reach the selected evdev reader.

## Evidence contract

After closing raw input and lifecycle descriptors, the helper appends one fixed `OBS_DIAG_` line containing four literal bits. The controller may expose only these booleans:

- `relative_calibration_seen`: strict calibration observed the eligible primary REL_X/REL_Y route.
- `primary_record_after_arm`: a primary input stream supplied a record after ARM; the record may be metadata, synchronization or other non-motion activity.
- `eligible_relative_after_arm`: a covered nonzero REL_X/REL_Y record reached the armed classifier.
- `yielded_token_sent`: a YIELDED token was successfully sent.

These bits distinguish coarse internal stages. They do not export or retain event codes, raw values, coordinates, device identities, counts or timestamps. They do not identify a human, prove the user's specific mouse is covered, establish a missing-event cause or repair delivery. A false bit can mean that no evidence was observed before the terminal condition; it is not proof that the human remained still.

The base terminal reason wins first. Normal CLOSE detail is optional and often unavailable because the controller has already stopped its reader/closed the connection; a failed optional CLOSE send preserves clean exit. Stopping/cancellation must not wait for optional detail. Reads use a bounded optional interval and never extend the existing terminal-report deadline. Missing, malformed, late or concurrently unavailable detail remains absent with a local report-kind label; valid base evidence remains intact. Diagnostic data never sets calibration success, readiness, ARM or resume authority.

## Offline review and tests

Producer fixtures must distinguish no-primary/snapshot-only evidence, primary records, eligible relative records and successfully sent yields. Verify credit resets with calibration resynchronization. Terminal export must follow closure of every raw stream, snapshot, topology, peer and session-watch descriptor. The prior CAL_DIAG/CAL_IDLE content and strict MODEYIELD2 classifier, release, quiet, deadline and lease checks must remain unchanged.

Parser fixtures must reject wrong prefixes, lengths and nonliteral bits, preserve valid base reports when detail is missing/malformed/late, and enforce the original deadline. Terminal callbacks run before optional reads, and contradictory later data cannot replace the first terminal reason. Tests must demonstrate that all-false or all-true diagnostic fields cannot authorize input or synthesize calibration success.

No new live acceptance is inferred from these tests. The earlier human-confirmed 0.8.8 movement miss and reproduced broad-calibration gap remain the known evidence: 0.8.9 prevents weak activation, while this candidate only helps locate where observations stop. See [strict coverage](STRICT_RELATIVE_COVERAGE.md) and [release status](RELEASE_STATUS.md).


Implementation review confirms a bounded payload below 128 bytes, with the original CAL_DIAG/CAL_IDLE first 34 bytes preserved and an optional 14-byte OBS_DIAG line appended. The exact parser accepts only its prefix, length and four literal bits. Terminal callbacks precede optional reads; cleanup remains in a finally block even when callbacks fail. Optional reads use at most 50 ms, capped by the original calibration-report deadline. Existing MODEYIELD2, calibration, ARM, lease, yield and resume checks remain unchanged. Frozen verification passes all 385 Python tests and 15 native fixtures; the real seven-tool loader/schema check, skill validation and the two-root-owned-payload package inspection also pass. No live result is inferred.


A fresh actual 0.8.10 provider verified the expected build, matching disk sources and all seven tools with sharing closed and zero held input; the installed helper hash matches. No new sharing or live event-delivery trial was performed, and the root cause remains unresolved.
