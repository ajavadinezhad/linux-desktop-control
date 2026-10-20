# Release status

As reviewed on 19 October 2026: plugin **0.8.16**, optional native helper **0.8.6**. The repository is public; this remains a supervised beta, not a broadly verified release.

## Verified

- All 14 installed plugin files matched the reviewed source; a fresh provider loaded the expected seven tools and build.
- The frozen suite passed **443 Python tests** and loader/schema validation. The unchanged native helper has a **20-fixture** baseline.
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
