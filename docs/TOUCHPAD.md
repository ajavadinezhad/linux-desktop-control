# Touchpad support candidate

Plugin 0.8.18 and helper 0.8.7 are installed. The existing mouse protocol remains unchanged. Touchpad support has passed isolated tests and review plus one scoped live pause/automatic-return check on this setup.

The new startup option selects a touchpad explicitly and requires native takeover monitoring with retained sharing. It negotiates a separate helper protocol and refuses older helpers rather than falling back to mouse coverage.

The intended scope is verified, indirect, single-finger touchpads. Actual movement must pass calibration; touching the surface alone does not count. A resting finger keeps automation paused. Lift the finger to allow the quiet check. Physical clicks, keyboard input, unsupported gestures, observer faults, and consent revocation remain terminal.

Raw touch coordinates, pressure, tracking identifiers, and device identities remain inside the helper. Only coarse activity and diagnostic flags leave it. Calibration is session-specific.

The combined controller passes 457 regression tests, the native helper passes 25 fixtures, and isolated loading and independent review pass. All 14 installed plugin files and both helper payloads match the reviewed package/source. Before claiming live support, a live check must prove movement detection, stationary-contact pause, release-to-quiet behavior, automatic return, and click interruption on the user's device.

## Scoped live acceptance

Both initial and post-ARM touchpad readiness checks passed. After one confirmed pointer move, physical touchpad movement produced a pause with sharing retained, capture/input disabled, and zero held virtual input. Finger release allowed quiet/resume and automatic return to the same confirmed point. A fresh image and the user independently confirmed return. Cleanup confirmed portal closure, zero held input, no warning, and successful helper exit. No clicks or files changed during this check. This does not establish other gestures, typing/drag interruption, universal devices, or an end-to-end drawing speedup.
