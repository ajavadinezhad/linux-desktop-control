# Validation

The reviewed 0.8.16 source passed 443 Python tests and the real seven-tool loader/schema check. Helper 0.8.6 retains its 20-native-fixture baseline. These checks run without opening real input devices or establishing live desktop acceptance.

From the repository root:

```sh
/usr/bin/python3 -m unittest discover -s tests
/usr/bin/python3 tests/check_loader.py
```

Native build and fixture instructions are in [the helper guide](../native-activity/README.md). Native fixture results require their compiler and library environment; they are not a replacement for physical-device checks.

Coverage includes malformed requests, session cancellation and stale callbacks, unresolved input release, startup/arming deadlines, foreground and display binding, pointer arrival, pause/resume, cursor return, and configured window shortcuts. See the test sources for individual cases.

The [release status](RELEASE_STATUS.md) separates live results from automated checks. The [beta checklist](BETA_ACCEPTANCE.md) lists unpassed physical scenarios. Historical investigations remain scoped to their recorded versions; neither counts nor installation alone prove all devices work.

Do not run a headless GNOME compositor against the user's active manager for testing. Use an isolated graphical test environment. Live tests need personal consent, disposable content, visible stop controls, and confirmed cleanup.
