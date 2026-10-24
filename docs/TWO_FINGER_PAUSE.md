# Two-finger contact pause

> The version and installation claims below describe historical checkpoints. Consult [release status](RELEASE_STATUS.md) for the recorded published baseline and remaining checks.

The 0.8.27 preview with helper 0.8.11 adds a bounded recovery path for ordinary two-finger touchpad contact. Enable native touchpad observation, retained sharing, and the existing pause-return click policy.

Resting two fingers pauses capture and input, cancels remaining queued work, and retains sharing. Lifting only one finger does not resume automation. After both lift and the existing quiet interval passes, recovery requires a fresh view of the current window. It never replays interrupted actions or claims contact is pointer movement.

This covers consistent single- and two-contact indirect touchpad records during ordinary armed control. It does not generalize to arbitrary gestures. Default policy, calibration and password waiting remain unchanged. Malformed or dropped records, three or more contacts, unsupported events, Stop, revoked sharing, and faults still stop control.

The triggering live session closed with a native parser fault after the user reported resting two fingers. Exact raw input is not collected or exported. Synthetic regression results and live acceptance are reported separately in the release status.

The0.8.28/helper0.8.12 update also rechecks an inconsistent touch/tool snapshot at most three times, retaining pause and no motion credit. Persistent inconsistency and unrelated input remain faults. One scoped live intervention returned under retained sharing, but a later closure prevents claiming complete live acceptance.
