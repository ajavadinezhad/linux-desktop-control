# Beta acceptance — 2026-10-19

Current build: plugin 0.8.12 (`cd15c911aab846b0e04cbdddd8b845bddd7439211b779bd9dd492ebd58c7b249`), helper 0.8.5. Offline validation remains 419 Python tests and 18 native fixtures. This document records existing evidence and future checks; it authorizes no additional live trial.

On the tested host, strict calibration and the post-ARM mouse gate passed; motion after capture yielded with sharing retained. No saved point kept the first session paused until explicit resume. With a confirmed saved endpoint in a second session, observed quiet led to one automatic cursor return and a fresh image in the same foreground context. The user confirmed physical movement and seeing the return. No action replay, lease renewal or session restart occurred; both sessions closed cleanly with zero held input and helper exit 0.

| Device/app scenario | Current evidence | Remaining beta check |
| --- | --- | --- |
| Current host, tested physical mouse, observed foreground | One human-confirmed saved-point automatic return; separate no-point explicit resume | Repeat short movement/quiet/return across several consented sessions and ordinary apps |
| Current build typing interruption | Historical 0.8.7 typing stop evidence only | Repeat typing takeover on 0.8.12; verify prompt cancellation, no queued replay and clean closure |
| Current build held-button drag interruption | Historical 0.8.7 endpoint interruption/release evidence only | Repeat on 0.8.12; verify virtual button release and terminal handling |
| GNOME privacy Stop / emergency stop | Guard and offline coverage; this acceptance did not exercise live Stop | Repeat during active input and retained pause; verify closure and refusal of later work |
| Second physical mouse/keyboard or transport | No general coverage established | Separately verify strict calibration, post-ARM delivery and interruption; do not infer coverage from USB/Bluetooth labels |
| Mixed-scale/multiple displays | Prior geometry/endpoint guards; current return is scoped to the selected monitor/context | Verify monitor origins, scale and layout changes; mismatched mapping must refuse input/return |
| Disconnect, lock, revocation and native lease expiry | Offline guards and historical closure evidence | Repeat relevant current-build terminal paths; verify no retained authority or stale queued action |
| Foreground change while paused / pointer outside shared monitor | Offline guards | Confirm no focus reclaim, return or action replay; use the documented refusal/terminal behavior |

Earlier failed delivery trials are retained in the release history. This success does not prove their unique root cause, universal hardware support, all-app behavior or physical-input provenance. Only covered relative motion may yield; keyboard/button/wheel/absolute activity and other terminal guards retain their existing semantics. Further acceptance requires a separately authorized, scoped live check.

Evidence: `LIVE_0_8_12_PRECAPTURE_DELIVERY.json` (local evidence, outside this repository), `LIVE_0_8_12_AUTOMATIC_RETURN.json` (local evidence, outside this repository). See [release status](RELEASE_STATUS.md) and [validation history](VALIDATION.md).
