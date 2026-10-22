# Release status

Current installed release: plugin **0.8.36**, native helper **0.8.17**. Fresh pointer/foreground queries and role checks are consolidated, a redundant 100ms click wait is removed, and active skill guidance is shortened. Explicit initial sessions support up to 1200 seconds; defaults and shorter safety timers are unchanged. All625 controller/recorder tests,83 native checks and tool loading pass. Installed source matches the reviewed build and1200-second startup succeeded. Full-duration expiry and controlled overall speed comparison remain unverified. Recording remains capped at900 seconds.

**Preview, GNOME-only:** currently targets GNOME Shell 51 on Wayland. Other platforms are planned and are not yet supported.

Previous installed update: plugin **0.8.35** skips the cosmetic200ms pointer approach for routine clicks and positioned scrolls. Two arrival observations and independent pre-effect endpoint confirmation remain. All616 controller/recorder tests, seven focused pacing tests and the seven-tool loader check pass. The installed provider reports the expected version and matching source fingerprint; A scoped live Calculator test completed six clicks in one batch and visibly produced12+34=46: input1793ms, final capture412ms. This establishes live operation of the new pacing, not a controlled before/after comparison. A fake-compositor benchmark using real waits measured median click input453ms before and243ms after (five trials each); this is not a live end-to-end result.

Previous source update: plugin **0.8.34** reduces the routine screenshot settling fence from350ms to200ms and makes direct live operation the documented default in both skill and tool guidance. Stop, input release, context, monitor mapping and password protection remain unchanged. The native helper stays0.8.16 and the GNOME observer remains unchanged. All613 controller/recorder tests, focused capture/control checks, skill validation and the seven-tool loader check pass. Live end-to-end speed improvement is not yet measured.

Previous update: plugin **0.8.33**, native helper **0.8.16**, GNOME authentication observer protocol **3** unchanged. The live0.8.32 diagnostic preserved unsupported-axis; read-only advertised capabilities isolated ABS_MT_TOOL_TYPE as the sole unsupported axis. This update handles active-slot finger metadata and inert palm intervention without raw input export or motion credit. Independent review, **83 native checks**, and the fresh seven-tool loader check passed. Controller behavior is unchanged apart from release identity; its613-test regression result is retained. A scoped live check on this machine passed both stationary four-finger contact and a four-finger workspace swipe: capture paused with sharing retained, recovery refreshed the current context after all fingers lifted, and fresh images were inspected. Cleanup confirmed explicit closure, no held input and no warning. No cart changes or automated task input occurred. This does not establish universal gesture/device coverage.

The preceding diagnostic update passed613 controller/recorder tests,77 native checks and loader validation. One input-free diagnostic trial identified the parser category; it was not a gesture acceptance test. See the [kernel tool-type protocol](https://docs.kernel.org/input/multi-touch-protocol.html).

The preceding0.8.31 passed607 controller/recorder tests,73 native checks and loader validation, but the live four-finger contact check failed in the parser after an intervention. Sharing closed cleanly with no held input. The exact rejected case was not preserved, so four-finger and workspace gesture acceptance remain unresolved.

The preceding0.8.30 passed600 controller/recorder tests and loader validation. A live Alt+Tab cycle retained sharing, recovered into the selected window, and allowed a subsequent harmless pointer action. A later four-finger gesture hit the helper’s unsupported contact path and closed sharing. The keyboard result is scoped; workspace gesture acceptance was not established.

The preceding0.8.29 passed590 controller/recorder tests,68 native checks, and loader validation, but its live Alt+Tab check failed because a physical pause still encountered a strict foreground checker. It is not recorded as live accepted. The same update fixed stale settling status masking a terminal closure and introduced exact native keyboard-recovery negotiation.

The preceding0.8.28 update passed569 controller/recorder tests,61 native checks, and loader validation. A scoped live two-finger test observed capture paused with sharing retained, automatic recovery, a successful subsequent pointer action, and clean explicit closure. This does not establish broad device or keyboard coverage.

The preceding two-finger update demonstrated an intervention and automatic return with retained sharing, but a later closure means full live acceptance is qualified. See [two-finger scope](TWO_FINGER_PAUSE.md).

New opt-in behavior includes supervised startup without manual calibration, ordinary click recovery, trusted human-only password waiting, and bounded recovery through ordinary window changes. Recovery cancels pending input and requires a fresh inspected screen; it never replays interrupted work. Passive startup honestly reports input coverage as unverified. Stop, revoked consent, protected screens, faults, and the original session deadline remain terminal.

Scoped live checks on this machine confirmed a package-install password wait and an LMMS tempo-dialog recovery without closing sharing. A later recorded LMMS take created and saved a short piano/cello/drum sketch and exported a WAV. This does not establish universal application or device support. The recorder readiness check verifies a live recording and advancing output with explicit system audio; operators must run it before creative edits and after recovery.

See [startup](PASSIVE_STARTUP.md), [click recovery](CLICK_RETURN.md), [permission waiting](PERMISSION_WAIT.md), and [recording workflow](../demo/README.md). The README leads with the privacy-edited native music video, followed by the bear demo. Raw private recordings remain local.

### Earlier drawing checkpoint

Plugin **0.8.19** passed **463 Python tests** and a scoped recorded bear trial with groups of 8–10 strokes per capture. Drawing through saving took approximately 207 seconds; this was not a controlled speed comparison. See [performance](PERFORMANCE.md).

### Earlier performance checkpoint

Installed performance update: plugin **0.8.17**, optional native helper **0.8.6** unchanged. The repository is public; this remains a supervised beta, not a broadly verified release.

The performance update passes 450 isolated regression checks and seven-tool loader validation. All 14 installed plugin files match reviewed source; a fresh provider confirmed the expected build and matching disk sources. Live speed measurement remains unperformed. See [performance measurements](PERFORMANCE.md). The live workflows below were recorded with earlier versions.

## Verified

- All 14 installed plugin files matched the reviewed source; a fresh provider loaded the expected seven tools and build.
- The frozen suite passed **450 Python tests** and loader/schema validation. The unchanged native helper has a **20-fixture** baseline.
- Firefox fitting and window relocation worked in the tested two-monitor GNOME setup.
- Five slides were created and saved through Impress, including a separate five-slide PowerPoint copy.
- The [4:39 bear demo](demo/README.md) shows actual browser opening and GUI painting. The edit removes setup waits, labels its resumed session, and hides unrelated tabs. It is not an uninterrupted session.
- A scoped 0.8.12 trial demonstrated physical mouse yielding, retained sharing, and one human-confirmed cursor return. Earlier 0.8.7 trials demonstrated typing interruption and drag interruption with button release; the drag used the endpoint guard rather than native motion detection.

## Still limited

Current-build physical typing, held-drag and human Emergency Stop repeats remain separate checks. Broader hardware, apps, lock/revocation/disconnect paths, display changes, and full ten-minute live expiry need further acceptance. Passing fixtures does not establish universal device coverage or a hard stop-latency bound.

Sessions default to 120 seconds; native-protected sessions may explicitly select up to 1200 seconds before calibration. No heartbeat or pause renews the deadline. A live session exceeded the old two-minute cap, but did not test full ten-minute expiry.

Routine invocation errors can still close sharing and require new consent. Calibration cannot be reused after its observer closes. Earlier missed mouse-delivery trials do not have a uniquely proven root cause.

The demo sessions ended with confirmed portal closure, zero held input and no cleanup warning. GPL-3.0-or-later now covers original code; third-party notices remain applicable. The owner made the repository public.

See [beta acceptance](BETA_ACCEPTANCE.md), [validation](VALIDATION.md), and [compatibility](COMPATIBILITY.md). Earlier results remain in version-specific documents and Git history.

## Live performance attempt

A first startup attempt delivered its calibration cue late because of an operator orchestration error. A corrected retry delivered the cue promptly but did not obtain strict relative-motion calibration credit despite coarse keyboard and pointer evidence. Both attempts closed before capture or task input, with confirmed portal closure, zero held input and no cleanup warning. No bear was drawn and no live speed comparison is claimed.

## Touchpad candidate

Plugin 0.8.18/helper 0.8.7 is installed. The controller passes 457 regression tests, the native helper passes 25 fixtures, and isolated seven-tool loading and independent review pass. All 14 installed plugin files and both helper payloads match reviewed source/package. A read-only installed-runtime check reports sharing closed and zero held input. Explicit touchpad source selection requires exact helper acknowledgement and does not fall back to mouse coverage. One scoped live touchpad pause/automatic-return check passed: movement paused capture/input while retaining sharing, finger release allowed return to the confirmed point, and a fresh image and user confirmation agreed. Cleanup confirmed portal closure, zero held input, and no warning. Other touchpad gestures and typing/drag interruption remain untested. See [touchpad scope](TOUCHPAD.md).
