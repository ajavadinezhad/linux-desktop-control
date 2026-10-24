# ZapZap startup diagnosis

> Version-specific investigation record. Status statements below describe that checkpoint. See [current release status](../RELEASE_STATUS.md) for installed versions and later acceptance.

Inspection and consented live startup verification on 2026-10-18. No account
setup, chat inspection, message sending or application-data deletion occurred.
A reversible user-only launcher override was installed after visible startup.

## Observed evidence

- Installed snap reports version 7.5.1, strict confinement, core24 base.
- The application's command is `usr/bin/zapzap-wrapper`; the desktop launcher
  invokes `/snap/bin/zapzap %u`.
- The wrapper sets architecture-specific library paths and `PULSE_SERVER`, then
  executes ZapZap. It contains no desktop helper invocation, Wayland socket
  mapping, or `XDG_RUNTIME_DIR` setup.
- Both Qt Wayland plugins and `libqxcb.so` are present in its platform-plugin
  directory. A missing platform-plugin file is therefore not established.
- The compositor socket exists at `/run/user/1000/wayland-0`. The app-specific
  `/run/user/1000/snap.zapzap` directory exists and is empty, with no Wayland
  socket or compatibility link.
- Earlier visually initiated startup was reported to fail with
  `Failed to create wl_display (No such file or directory)` and Qt's failure
  to initialize its found Wayland plugin. This review did not reproduce it.

## Inference and limit

The strongest explanation is that the app resolves the relative
`WAYLAND_DISPLAY=wayland-0` within its snap-specific runtime directory, where
the socket is missing. It is not yet a directly observed in-process environment
or syscall result. Connected interfaces alone do not create the expected path.

Ubuntu's desktop-helper source explicitly handles this layout by linking the
parent compositor socket into the snap runtime directory. ZapZap's inspected
wrapper does not contain that setup. See the [official helper source](https://raw.githubusercontent.com/ubuntu/snapcraft-desktop-helpers/master/common/desktop-exports)
around its Wayland compatibility setup and [Snap environment documentation](https://snapcraft.io/docs/explanation/how-snaps-work/parallel-installs/).

## Observed live startup

After personal sharing consent, the operator opened an observed GNOME Terminal
through the GUI and visibly typed:

```sh
env QT_QPA_PLATFORM=xcb /snap/bin/zapzap
```

This changes the Qt platform selection for this process only. It preserves the
snap launcher and confinement, does not change global display settings, and
does not alter saved account data. Qt documents the `QT_QPA_PLATFORM` override
in [Qt Platform Abstraction](https://doc.qt.io/qt-6/qpa.html).

The Return action receipt was `dd122dec8d9e4b499074edc6aa4e6fac`. A delayed
window change closed the foreground guard. No focus reclaim or automatic
sharing restart followed. After explicit fresh human readiness and new consent,
the operator observed ZapZap in the dock and explicitly clicked it (receipt
`f2d64265e46c4eb4ace0a3592a49cb55`).

The resulting screenshot showed the **Welcome to ZapZap** language/appearance
window in a 1040 × 740 frame. This verifies startup under the process-only X11
fallback. No account, login or setup action was taken. Final portal closure was
confirmed with no cleanup warning. Authentication and private conversation
content were not required to establish this result.

If X11 cannot connect or a dependency fails, retain the exact startup error and
stop; do not disable sandboxing or clear application data. The app's shipped
Qt WebEngine sandbox flags are existing package metadata, not an instruction to
add more flags.

## Reversible user-only launcher override

After visible startup, an override was written at
`~/.local/share/applications/zapzap_zapzap.desktop`. No existing user override
was present. It retains the desktop ID and metadata while changing `Exec` to:

```ini
Exec=env QT_QPA_PLATFORM=xcb /snap/bin/zapzap %u
```

The original snap desktop entry and wrapper remain untouched. Global Qt
environment, network/proxy settings and account data were not changed.

To roll back, delete only the newly created user override at
`~/.local/share/applications/zapzap_zapzap.desktop`; GNOME can then use the
original snap desktop entry again. No previous user override needs restoration.

The app remained open after this check, so a cold relaunch through the persisted
launcher is still pending. The verified result is the visible startup window,
not account login, message delivery, complete app functionality or a guarantee
that every application can be controlled.
