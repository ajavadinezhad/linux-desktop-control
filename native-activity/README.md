# Optional native activity helper

Helper **0.8.7** adds physical-input monitoring to explicitly protected sessions. It is off by default and is separate from ordinary portal control. See [release status](../docs/RELEASE_STATUS.md) for scoped live evidence and unpassed checks.

## Consent and startup

The user approves GNOME screen/keyboard/pointer sharing, then authorizes the fixed helper in the system administrator dialog. Passwords belong only in that dialog.

Before task capture/input, the helper must acknowledge readiness, complete fresh keyboard/pointer calibration, reach released/quiet state, and arm. Retained-sharing sessions require strict streamed movement coverage for the selected source and a separate post-ARM pointer-only readiness check. Mouse mode uses MODEYIELD2; explicit touchpad mode uses MODEYIELD3 and accepts only verified indirect single-finger devices. Contact alone never earns movement credit; a resting finger blocks resume until lifted. Missing evidence closes startup; no synthetic challenge or fallback claims protection.

Authorization input may settle for at most five seconds before calibration begins; it grants no calibration credit. Calibration is not reusable after the observer closes.

## Runtime behavior

The collector receives raw kernel codes and values internally and exports only fixed activity, fault, readiness and diagnostic messages. It never exports raw descriptors or input contents. See [privacy](docs/PRIVACY.md) and [confinement](docs/ARCHITECTURE.md).

Covered movement may yield under explicitly negotiated retained-sharing mode. In touchpad mode contact immediately pauses automation and blocks quiet until released; unselected mouse movement remains terminal. Keys, buttons, unsupported activity, faults and lifecycle loss remain terminal. The controller, not this helper, owns capture suspension and checked cursor return. It never replays an interrupted action. See [the mode contract](../docs/RETAINED_SHARING.md).

Heartbeats use a one-second deadline. The absolute session budget defaults to 120 seconds and may be selected once, from 120–600, before calibration. Negotiation, heartbeat, pause and resume do not renew its original anchor. Device activity does not prove human identity; monitoring and input dispatch remain asynchronous.

## Build and review

From this directory:

```sh
python3 build-package.py --output /tmp/codex-desktop-activity.deb
```

The build needs a C compiler, development headers for libudev/libsystemd and the packaging tools used by the script. Optional `--cc` and `--include` select a compiler/header directory. The current package targets amd64. Building does not install or authorize it.

Inspect the package before installation:

```sh
dpkg-deb --contents /tmp/codex-desktop-activity.deb
dpkg-deb --info /tmp/codex-desktop-activity.deb
```

It contains exactly two root-owned payloads: `/usr/libexec/codex-desktop-activity` (0755, no setuid) and `/usr/share/polkit-1/actions/org.codex.desktop-activity.policy` (0644). It has no service, maintainer scripts, input-group changes or device ACL changes. After reviewing these privileged components, install through your distribution's package installer with administrator approval.

The policy requires fresh administrator authorization for an active local session. After opening covered read-only descriptors, the helper drops groups/capabilities and credentials, enables `NO_NEW_PRIVS`, and applies seccomp. The shared `nobody` identity is weaker isolation than a dedicated account.

## Verification

The reviewed helper baseline passed 20 isolated native fixtures without opening physical input devices. Fixture scripts live alongside the source. They do not establish coverage of a new keyboard, mouse or transport. Follow the [beta checklist](../docs/BETA_ACCEPTANCE.md) for separate live acceptance.

The old preopened-descriptor prototype has been removed; the production collector retains raw device access inside its own boundary. Earlier design tradeoffs remain in [DESIGN.md](DESIGN.md), explicitly as historical context.
