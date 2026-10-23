# Install Linux Desktop Control

This is a supervised beta licensed under [GPL-3.0-or-later](../LICENSE). See [licensing scope and third-party notices](../LICENSING.md). The repository is public.

## 1. Check requirements

- GNOME Shell **51**, running a **Wayland** session.
- Codex desktop with its local plugin CLI available.
- System Python 3 with PyGObject/Gio, GStreamer, PipeWire capture elements and libxkbcommon.
- GNOME desktop portals and PipeWire working in the logged-in session.

The preflight checks exact dependencies without requesting sharing or changing settings. From a terminal, get the repository and check it:

```sh
git clone https://github.com/ajavadinezhad/linux-desktop-control.git
cd linux-desktop-control
./install.sh --check
```

If the Codex executable is elsewhere, set `CODEX_BIN` to its actual installed path before running the check. Resolve reported missing dependencies using your distribution's packages. Do not bypass a failed GNOME-version check and assume support.

## 2. Install the local plugin

```sh
./install.sh
```

The installer configures machine-local launch paths, installs the read-only GNOME observer and cursor assets, and registers the local plugin marketplace. It does not start screen sharing. Optional cursor glow changes apply only when explicitly enabled for a session.

Refresh the app's tool catalog or open a fresh chat. The provider should expose seven tools: start, observe, action, status, pause, resume and close. Guarded input requires foreground-observer protocol 2. If GNOME has not loaded the extension, save your work and manually log out and back in; the installer does not restart your session.

## 3. Try a supervised task

Ask the agent to open a disposable document. In GNOME's own dialog, select exactly one monitor and allow keyboard and pointer control. Keep private windows off that screen. The agent must inspect a fresh capture before using apps.

Use GNOME's sharing control to stop whenever you want. A stopped or revoked session is not silently reopened. Start with short tasks; [compatibility](COMPATIBILITY.md) lists supported scope and limitations.

## 4. Optional: physical takeover and cursor return

Ordinary control does not require the native activity helper. For physical-input monitoring, separately review and build the [native helper](../native-activity/README.md). It needs administrator-approved installation and system authorization, and receives raw input internally. Enter administrator passwords only into the system's own dialog.

The default protected startup uses keyboard/pointer calibration. An explicitly selected supervised passive startup skips manual challenges while reporting source coverage as unverified; see [passive startup](PASSIVE_STARTUP.md). Retained-sharing mode adds a mouse-only readiness check before capture. Calibration lasts only while that observer stays alive. Do not cache a pass across new sessions or skip a failed check.

Default sessions last 120 seconds. Native-protected sessions may explicitly choose an initial 120–1200-second limit before calibration; pause and heartbeat do not renew it. Automatic cursor return is opt-in and limited to covered relative movement in the same verified context. See [retained sharing](RETAINED_SHARING.md).

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Preflight fails | Read the named requirement; verify GNOME/Wayland, system Python libraries and the Codex executable path |
| Tools are missing or old | Refresh the tool catalog/open a fresh chat; verify provider version and installed source match |
| Foreground observer unavailable | Check extension loading; manual logout/login may be needed after saving work |
| Calibration never completes | Release all keys/buttons; follow the current cue using the Linux devices; failure must not be bypassed |
| Window or pointer checks refuse input | Inspect current layout and window placement; do not replay the failed action blindly |
| Sharing keeps restarting | Invocation or safety faults can still close sessions; a longer lease does not fix those errors |

For validation commands, see [validation](VALIDATION.md). For data handling, see [privacy](PRIVACY.md). Do not delete a registered marketplace used by other projects while troubleshooting.

## Optional read-only local-model adapter

After installing the plugin, you can install the separate adapter without starting sharing:

```sh
install -Dm755 examples/notification_observer.py "$HOME/.local/share/linux-desktop-control/notification_observer.py"
```

Run that script with `--runtime` pointing to the reviewed installed `desktop.py` and `--model` naming your loaded local vision model. The default API is loopback-only. Each run still needs personal GNOME consent; it grants no mouse/keyboard actions and does not auto-start on login. See [the adapter contract](CONTINUOUS_OBSERVER.md#read-only-lm-studio-adapter) for bounds and limitations.
