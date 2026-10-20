# Release status

**Preview, GNOME-only:** currently targets GNOME Shell 51 on Wayland. Other platforms are planned and are not yet supported.

Current update: plugin **0.8.26**, native helper **0.8.10**, GNOME authentication observer protocol **3**. The frozen build passed **565 controller/recorder tests**, the seven-tool loader check, and independent review. The helper's latest separate run passed **51 native checks**. Installed plugin files match the reviewed source.

New opt-in behavior includes supervised startup without manual calibration, ordinary click recovery, trusted human-only password waiting, and bounded recovery through ordinary window changes. Recovery cancels pending input and requires a fresh inspected screen; it never replays interrupted work. Passive startup honestly reports input coverage as unverified. Stop, revoked consent, protected screens, faults, and the original session deadline remain terminal.

Scoped live checks on this machine confirmed a package-install password wait and an LMMS tempo-dialog recovery without closing sharing. A later recorded LMMS take created and saved a short piano/cello/drum sketch and exported a WAV. This does not establish universal application or device support. The recorder readiness check verifies a live recording and advancing output with explicit system audio; operators must run it before creative edits and after recovery.

See [startup](PASSIVE_STARTUP.md), [click recovery](CLICK_RETURN.md), [permission waiting](PERMISSION_WAIT.md), and [recording workflow](../demo/README.md). The existing privacy-edited bear demo remains unchanged. Music recordings are local and are not published here.

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

Sessions default to 120 seconds; native-protected sessions may select 120–600 seconds before calibration. No heartbeat or pause renews the deadline. A live session exceeded the old two-minute cap, but did not test full ten-minute expiry.

Routine invocation errors can still close sharing and require new consent. Calibration cannot be reused after its observer closes. Earlier missed mouse-delivery trials do not have a uniquely proven root cause.

The demo sessions ended with confirmed portal closure, zero held input and no cleanup warning. GPL-3.0-or-later now covers original code; third-party notices remain applicable. The owner made the repository public.

See [beta acceptance](BETA_ACCEPTANCE.md), [validation](VALIDATION.md), and [compatibility](COMPATIBILITY.md). Earlier results remain in version-specific documents and Git history.

## Live performance attempt

A first startup attempt delivered its calibration cue late because of an operator orchestration error. A corrected retry delivered the cue promptly but did not obtain strict relative-motion calibration credit despite coarse keyboard and pointer evidence. Both attempts closed before capture or task input, with confirmed portal closure, zero held input and no cleanup warning. No bear was drawn and no live speed comparison is claimed.

## Touchpad candidate

Plugin 0.8.18/helper 0.8.7 is installed. The controller passes 457 regression tests, the native helper passes 25 fixtures, and isolated seven-tool loading and independent review pass. All 14 installed plugin files and both helper payloads match reviewed source/package. A read-only installed-runtime check reports sharing closed and zero held input. Explicit touchpad source selection requires exact helper acknowledgement and does not fall back to mouse coverage. One scoped live touchpad pause/automatic-return check passed: movement paused capture/input while retaining sharing, finger release allowed return to the confirmed point, and a fresh image and user confirmation agreed. Cleanup confirmed portal closure, zero held input, and no warning. Other touchpad gestures and typing/drag interruption remain untested. See [touchpad scope](TOUCHPAD.md).
