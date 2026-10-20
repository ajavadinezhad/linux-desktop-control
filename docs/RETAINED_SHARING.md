# Retained sharing and cursor return

Opt-in behavior, with scoped mouse-yield and return evidence on the tested host. See [current status](RELEASE_STATUS.md) for versions, live evidence and limits.

## Opt-in and consent

A new session chooses:

```json
{"physical_takeover":true,"interruption_policy":"retain-sharing","pointer_motion_return":true}
```

Default `interruption_policy="close"` remains unchanged. `retain-sharing` without `pointer_motion_return` supports explicit pause/resume and native motion yielding without automatic return. Automatic return additionally requires native monitoring; supervised mode does not pretend to detect physical movement.

Personal GNOME sharing approval, the separate administrator authorization, physical calibration and ARM are still required. No password or approval dialog is automated. A pause keeps that original consent and observer alive; it neither creates a new portal nor renews the original selected native lease (120 seconds by default, up to 600 chosen before calibration). GNOME privacy Stop, lock, revocation and closure always remain terminal. A later new session needs new personal consent.

## Motion, quiet and return

Only covered nonzero `EV_REL` `REL_X`/`REL_Y` positional mouse records yield. Wheel, buttons/keys, absolute pointer records, switch/metadata/unknown activity, held physical input, stream loss and faults remain terminal. This deliberately narrow first implementation does not promise all touchpads, devices, applications or physical-input provenance.

On a qualifying motion epoch, the server cancels the current operation independently from the sharing lifetime, invalidates queued requests and old observation tokens, releases its held virtual input and stops the backend capture pipeline. The portal remote remains open. Status reports `sharing_active=true`, but `capture_allowed=false` and `input_allowed=false` while paused. Read-only foreground, mapping and native lifecycle checks continue.

The helper continuously observes without exporting raw keys or coordinates. After 1.5 seconds of observed quiet, released physical input and clean queues, an epoch-bound `RESUME`/`ARMED` acknowledgement can authorize one return attempt. The original lease is not extended. A stale or interrupted handshake grants no input.

The destination is the last assistant pointer endpoint that passed two fresh compositor observations. It remains only in memory, bound to the consent identity, portal session, monitor mapping and foreground signature. Automatic return requires those bindings unchanged and a freshly observed pointer inside the shared monitor. No confirmed point, a valid changed foreground or an off-monitor pointer leaves sharing paused. There is no app focus acquisition or cross-monitor reclamation.

The return sends one observed relative displacement, followed by the existing endpoint verification. It performs no click, key, text, scroll, old path or interrupted step. It never corrects a mismatch or replays queued work. Fresh capture and new generation/observation tokens follow success. Obtain and inspect `desktop_observe` before choosing further input; automatic cursor return does not resume an old batch.

New motion during the handshake, return or capture cancels that operation and yields again. Endpoint mismatch and other errors remain terminal. Source detection, compositor checks and OS dispatch are asynchronous; this is not atomic priority over an already delivered event or a hard cancellation-latency guarantee.

## Manual pause and resume

`desktop_pause` retains consent only with retained-sharing policy; under default policy it closes. Manual pause is sticky: later mouse movement and quiet never convert it to automatic return. It remains paused until an explicit `desktop_resume` with the current `pause.pause_id` from `desktop_status`.

`desktop_resume` revalidates current runtime, consent, mapping, native quiet/ready state and foreground observation, then returns a fresh screenshot and new tokens. It does not return the pointer or replay input. Wrong or stale tokens leave sharing paused. A new movement epoch invalidates an in-progress resume.

Native faults, heartbeat/lease expiry, topology/layout/owner changes, protected foreground, privacy Stop, revocation, disconnection and cleanup failures remain terminal. `desktop_close` still closes resources independently of this mode. Reopening stopped sharing is never automatic.
