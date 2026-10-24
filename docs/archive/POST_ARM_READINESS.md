# Post-ARM mouse readiness — 0.8.11 candidate

> Version-specific investigation record. Status statements below describe that checkpoint. See [current release status](../RELEASE_STATUS.md) for installed versions and later acceptance.

This candidate adds a readiness gate in the desktop controller for retained MODEYIELD2 sessions. It does not change helper package 0.8.4, device permissions, calibration, stream delivery or the original 120-second helper lease. Default close-policy startup is unchanged. Event delivery and live automatic return remain unresolved; this prevents a false READY claim rather than repairing the underlying cause.

## Two distinct challenge stages

Initial calibration still requires the human's keyboard and relative-pointer challenge, released input, quiet and the initial ARM acknowledgement. For retained sharing, that initial ARMED acknowledgement no longer makes the controller ready or permit capture/input.

A separate, original 30-second post-ARM budget then requires actual armed-path `YIELDED_<epoch>` followed by `QUIET_<same epoch>` and a matching `RESUME_<epoch>` / `ARMED_<epoch>` acknowledgement. Normal retained-sharing yield/return callbacks remain suppressed during startup. No task screenshot, cursor move or task input is used to generate the challenge. Missing motion, stale epochs, expiry, revocation, helper faults and failed closure refuse startup. Neither calibration success nor diagnostic booleans can replace this check.

The post-ARM instruction is mouse-only: “Move the mouse briefly, then keep your hands still. Do not press any keys or mouse buttons.” Keys/buttons remain terminal because the native helper is already armed. The readiness notice uses only fixed allowlisted content through the existing GNOME notification service, without actions, application activation, arbitrary text or extra permissions. A notification acknowledgement does not prove visibility. Unknown delivery or unresolved closure never grants activation. A newly known post-ARM notice owns its own bounded close-attempt budget; an unresolved older notice is never replaced or forgotten.

## Read-only startup status and cue timing

While `desktop_start` is still pending, the independent snapshot keeps active/capture/input disabled. `calibration_verified` describes only the initial stage. Separate fields are `post_arm_required`, `post_arm_state`, `post_arm_verified`, `post_arm_remaining_seconds`, and `readiness_stage`. The notice reports its allowlisted phase.

A post-ARM human cue is timely only when readiness_stage and notice phase are `post-arm-pointer`, post_arm_state is `waiting-motion`, request acknowledgement is known, delivery is not uncertain and the coarse remaining-seconds value is positive. Never reuse the earlier Shift/key cue for this stage. Zero, missing or expired remaining time does not justify prompting after the deadline. `waiting-quiet` asks for stillness; `resuming`, `verified` or `failed` does not request more motion. Snapshot fields are descriptive and never provide capture/input authority.

Only a current native-ready result with post_arm_verified=true and post_arm_state=verified can pass the retained startup capture gate. The server rechecks before finish_start, before/after capture and before startup image publication. A new yield after gate completion invalidates startup/capture rather than publishing false readiness. Ordinary retained-sharing operation still requires fresh observed tokens after activation; no queued action or interrupted gesture is replayed.

## Validation and scope

Offline tests cover fixed mouse-only content, phase allowlisting, uncertain-notice ownership, coarse deadline expiry, distinct startup states, missing/false post-ARM proof, and yield before/during capture or before publication. Fake-peer integration exercises the actual YIELDED/QUIET/RESUME/ARMED exchange without devices or GUI. All 411 Python tests, 16 native fixtures, the real seven-tool 0.8.11 loader/schema check and skill validation pass on the frozen source. The helper package and installed native binary are unchanged at 0.8.4.

Plugin 0.8.11 is installed with unchanged helper 0.8.4 and has no live acceptance. The previous human-confirmed movement miss remains unresolved. A successful synthetic handshake cannot establish physical hardware coverage or a hard race-free dispatch guarantee. No new sharing trial or helper installation is part of this preparation.


A fresh actual 0.8.11 provider verified build `d9365aaf2ec194b81bb855405f8737bbb3a2e813779550309bc88fd17acf0eb9`, matching disk sources and all seven tools, with sharing closed, zero held input and capture/input disabled. All 411 Python tests, 16 native fixtures, loader/schema discovery and skill validation pass. No new live trial was performed; mouse-event delivery and automatic return remain unresolved.
