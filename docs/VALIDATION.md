# Validation

For recorded release-specific results, see [release status](RELEASE_STATUS.md). The published 0.8.41 checkpoint recorded 689 combined tests and the unchanged helper's prior 86 native checks. Those results predate later local Qwen-client and documentation changes; they are not a claim that the present working tree has just passed the full suite. Automated checks do not establish live desktop acceptance.

From the repository root:

```sh
/usr/bin/python3 -m unittest discover -s tests
/usr/bin/python3 tests/check_loader.py
```

Native build and fixture instructions are in [the helper guide](../native-activity/README.md). Native fixture results require their compiler and library environment; they are not a replacement for physical-device checks.

Coverage includes malformed requests, session cancellation and stale callbacks, unresolved input release, startup/arming deadlines, foreground and display binding, pointer arrival, pause/resume, cursor return, and configured window shortcuts. See the test sources for individual cases.

The [release status](RELEASE_STATUS.md) separates live results from automated checks. The [reliability acceptance plan](RELIABILITY_ACCEPTANCE.md) lists the broader remaining scenarios; the [older beta checklist](archive/BETA_ACCEPTANCE.md) preserves its version-specific evidence. Historical investigations remain scoped to their recorded versions; neither counts nor installation alone prove all devices work.

Do not run a headless GNOME compositor against the user's active manager for testing. Use an isolated graphical test environment. Live tests need personal consent, disposable content, visible stop controls, and confirmed cleanup.
