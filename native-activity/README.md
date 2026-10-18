# Optional native activity helper — 0.8.0

This helper stops a consented GNOME desktop session when activity arrives from
the covered kernel input devices, including activity in the same window. It is
off by default. Normal desktop control does not invoke it or request its
administrator authorization.

The implementation is installed and 237 Python tests pass. Live startup and browser input worked, but same-window typing interruption has not passed. The latest held-key attempt completed 960 characters without an activity signal; the user confirmed a one-second physical key hold while text grew. Drag interruption remains unverified. Automated tests do not establish live device coverage.

## Consent and operation

Missing helper installation is reported before GNOME sharing is requested. For
each new protected session, the user first personally approves GNOME screen,
keyboard, and pointer sharing. A separate system dialog then requests
administrator approval for the fixed helper. Enter the password only in that
dialog; the assistant neither enters nor receives it.

No task screenshot or automated input is allowed until the helper completes
READY → CALIBRATE → CALIBRATING → CALIBRATED → ARM → ARMED. Before control, the human must press/release a keyboard key and move the pointer. The helper requires fresh activity from both source categories followed by released input and a quiet boundary. Missing activity closes sharing; no synthetic challenge or automatic bypass is allowed. Calibration covers only the challenged sources at that moment. READY alone does not enable control. Authorization input
is discarded while disarmed; ARM checks that no keys/buttons remain held and
that no activity or topology change is queued. There is no post-arm grace
window. Failed authorization or arming closes sharing instead of silently
falling back while claiming protection.

The collector receives raw kernel event codes and values internally. It reduces
them locally to fixed activity/fault signals and does not export raw events or
raw file descriptors. See [Privacy](docs/PRIVACY.md).

Eligible UHID/uinput devices are included conservatively. ACTIVITY means device
activity, not proof of human identity or physical origin. GNOME portal virtual
input does not create evdev devices; deployed separation still needs live
verification. Detection and input dispatch are asynchronous: an event already
in flight can race with a stop. Zero-race priority and universal coverage are
not promised. GNOME's sharing indicator remains an independent stop.

The client sends HB every 0.2 seconds and the helper replies ALIVE. A one-second
heartbeat deadline and absolute 120-second lease bound monitoring. Session
changes, topology changes, channel failure, requester death, or expiry end it.
There is no automatic restart, lease extension, or resume after quiet input.

## Reviewable installation package

The package contains exactly two root-owned payload files:

- `/usr/libexec/codex-desktop-activity` — fixed executable, mode 0755, no setuid.
- `/usr/share/polkit-1/actions/org.codex.desktop-activity.policy` — policy, mode 0644.

The policy action `org.codex.desktop-activity.monitor` requires `auth_admin`
for an active local session, denies other sessions, and does not retain approval.
The package has no maintainer script, service, input-group change, or device ACL
change. Building it does not install or authorize it.

From this directory, the build-only entry point is:

```sh
python3 build-package.py --cc /path/to/cc --include /path/to/headers --output /path/to/helper.deb
```

`--include` is optional when the compiler already finds the required headers.
The current package targets amd64 and links the system libudev and libsystemd
runtime libraries. Before administrator-approved installation, inspect the
package manifest, policy, executable, and build result; confirm the two payload
paths above and absence of maintainer scripts. No installation is performed by
the build script.

After opening read-only input descriptors, the helper removes groups and
capabilities, becomes `nobody`, disables dumpability, enables `NO_NEW_PRIVS`, and
applies seccomp confinement. The shared `nobody` identity is not a dedicated
sandbox account. See [Architecture](docs/ARCHITECTURE.md).

`DESIGN.md` is an earlier design record. Where its proposed device exclusions
differ, the concrete policy above includes eligible UHID/uinput devices.

## Held-state fallback

The collector samples aggregate held-key/button state using a separately opened client for each device; duplicating the event descriptor would share the client and flush queued keys. Event streams remain the primary observation route. The snapshot bitmap and raw records stay inside the helper. Polling can miss complete taps between samples, and an exclusively grabbed relative pointer has no held bit for button-free motion. The nominal 20 ms poll interval is not a hard end-to-end cancellation bound. The replacement has not passed typing or dragging acceptance yet.

Calibration timeout diagnostics contain only eight fixed booleans (keyboard/pointer category seen, stream/query/held presence, current held/quiet/stale flags). The helper closes input descriptors before returning them; diagnostics never authorize capture or input. The controller emits a fixed readiness marker after CALIBRATING so the challenge is not requested before its actual start. A physical coverage pass remains required.

Before arming, a delayed clock-switch loss marker may trigger bounded resynchronization: clear all calibration credit, discard through SYN_REPORT, require released input and a clean boundary, then request the challenge again. At most two resets fit within the original30second calibration deadline; no capture/input is allowed. Clock setup now occurs immediately after opening each primary client. Bulk reads reduce per-record overhead. Once armed, SYN_DROPPED remains an immediate terminal fault. Live success remains unverified.

Calibration accepts fresh absolute pointer-source samples because those same source records cause cancellation once armed. This proves source delivery, not actual changed position, button delivery, or human identity. The pre-arm quiet period is1.5seconds; afterARM there is no grace. Terminal activity category is only key/button, pointer, switch, metadata or held-state, with no raw codes or coordinates.
