## Installed helper 0.8.6: bounded initial lease selection

Default lease remains120seconds. One exact LEASE_nnn command (integer120–600) may be acknowledged before MODEYIELD/calibration while unarmed; duplicate, malformed, expired or later negotiation fails closed. The budget uses the original READY/session_time anchor, never negotiation time. Heartbeat remains1000ms and cannot renew the absolute cap. No new permissions or raw diagnostics are added. Installed binary/policy hashes match the reviewed package; 20 native fixtures and 438 Python tests pass. Initial live 600-second negotiation passed both readiness gates; complete ten-minute expiry is not yet verified.

## Installed helper 0.8.5: authorization-release settling

CALIBRATE may remain unarmed for at most 5000 ms while held authorization input releases and primary/topology/owner queues become empty. Draining grants no challenge credit. Only the clean released boundary emits CALIBRATING and starts fresh calibration. Session health and the original 120-second lease remain required; timeout/query failure is terminal. Strict relative-stream calibration and post-ARM behavior are unchanged. This startup-race fix does not repair or explain missing live mouse delivery.

# Optional native activity helper — 0.8.4 candidate

This helper stops a consented GNOME desktop session when activity arrives from
the covered kernel input devices, including activity in the same window. It is
off by default. Normal desktop control does not invoke it or request its
administrator authorization.

The historical native-helper candidate was installed with 255 passing Python tests. Current audit evidence is in [the scenario audit](../docs/SCENARIO_AUDIT.md). Live startup and browser input worked, but same-window typing interruption has not passed. The latest held-key attempt completed 960 characters without an activity signal; the user confirmed a one-second physical key hold while text grew. Drag interruption remains unverified. Automated tests do not establish live device coverage.

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
There is no automatic restart or lease extension. Only the explicitly negotiated retained-sharing mode below may resume after fresh quiet.

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

The backend can request a passive readiness notice from the existing GNOME notification service after portal consent and CALIBRATING. It uses fixed text, no actions or service activation, and bounded local calls. Requested visibility is not proof of display. An acknowledged or uncertain notice must be resolved before ARM; failed or unknown closure refuses control. This status UI does not capture the desktop or launch/focus a task application.


Terminal quiet diagnostics (helper package 0.8.1)

REPORT still closes every raw input descriptor before exporting anything. Its
first line remains the unchanged `CAL_DIAG_` plus eight literal bits. It appends
`CAL_IDLE_<kind><age><reason><input><topology><owner>\n` in the same single
34-byte report. Old controllers may consume only the first line. Neither line
establishes calibration success or permits ARM.

The fixed kind alphabet is N none, H held, K key/button, R nonzero relative,
Z zero relative, A absolute, S switch, C clock metadata, M other metadata.
Age is N none, R recent (less than the existing 1500 ms quiet requirement), or
S settled. Reason is M missing category, H held, R recent activity, Q queued
boundary, or Y ready. The final three literal bits identify pending input,
topology and owner queues at the last quiet check. These are cached coarse
states, not event logs; no key codes, values, coordinates, source identities,
counts or timestamps are exported. Clock metadata classification inspects only
the fixed event type/code internally. Relative classification inspects zero
versus nonzero internally; that value is never exported.

The added fields do not change quiet, calibration, source selection, ARM or
armed cancellation behavior. Metadata and zero relative records still prevent
quiet. They explain conservative refusal rather than filter it. A pending
queue can produce the same old quiet-blocked bit as recent metadata. The eight
old bits alone cannot distinguish those causes. A last-kind diagnostic does
not prove a human action or identify which physical device caused activity.

`test_quiet_diagnostics.py` includes the production collector in a synthetic
fixture. It distinguishes clock metadata, zero relative records, and each
pending queue class; verifies raw-descriptor closure before the combined report;
and retains armed cancellation for key, relative, absolute, switch and metadata
records. It opens no input device and does not establish live physical coverage.


## Optional persistent mouse-motion yield (package 0.8.2)

Historical helper package 0.8.2 was installed and reviewed; installed package 0.8.3 now supersedes it. The persistent motion-yield path is tested offline but has no live acceptance yet. Default protocol behavior is unchanged. An explicitly retained-sharing controller negotiates `MODEYIELD`/`MODEYIELD_OK` before calibration; calibration and ARM remain mandatory. Thereafter only covered nonzero EV_REL REL_X/REL_Y yields. All buttons/keys, wheel/other axes, EV_ABS, metadata/switch/unknown activity, held state and faults remain terminal.

The helper keeps observing and emits bounded `YIELDED_<epoch>` and `QUIET_<epoch>` tokens. After 1500 ms quiet, released input and empty boundary queues, `RESUME_<epoch>` is rechecked and acknowledged as `ARMED_<epoch>`. New motion invalidates quiet; epochs are bounded 1–64. Stale or invalid requests fail closed. No raw codes, values, coordinates or device identities are exported. The heartbeat, session/topology guards, privilege drop, confinement and original 120-second lease continue unchanged; pause/resume never renews authority.

The desktop controller separately invalidates work, releases virtual input and suspends capture. Automatic one-time return requires explicit pointer_motion_return opt-in and unchanged consent/mapping/foreground plus a saved confirmed point; it is not implemented by the privileged helper and never replays an action. Manual pause stays manual despite later motion/quiet. See [the complete controller contract](../docs/RETAINED_SHARING.md).


## Strict coverage negotiation (package 0.8.3 candidate)

New retained-sharing controllers require MODEYIELD2/MODEYIELD2_OK before calibration and never fall back. Strict mode requires a fresh streamed nonzero REL_X/REL_Y event from a verified pointer source in addition to keyboard credit and the existing released/quiet boundary. Held/button/absolute/other-axis evidence alone cannot establish that route; resynchronization clears strict credit. The legacy broad category diagnostic bits are not proof of the additional requirement. Package 0.8.3 is installed and its reviewed payload matches, but strict relative delivery and automatic return have no live acceptance.

The third installed 0.8.8 trial missed human-confirmed mouse movement despite calibration success; the old broad-calibration/yield-route mismatch is reproduced offline. The stricter contract prevents weak activation but does not repair delivery, identify the user's particular mouse or establish universal coverage. Device permissions, raw-event privacy, privilege drop and the original lease are unchanged. No grab probes or calibration bypasses are introduced. See [strict coverage evidence](../docs/STRICT_RELATIVE_COVERAGE.md).


## Terminal-only observation evidence (package 0.8.4 candidate)

The optional fixed OBS_DIAG_4bits line is appended after raw/lifecycle descriptors close. It reports only strict relative calibration credit, any primary record after ARM, eligible relative records after ARM, and successful YIELDED send. It exposes no event contents, coordinates, identities, counts or timestamps. Original CAL_DIAG/CAL_IDLE prefixes remain unchanged. Normal CLOSE sends best effort; unavailable optional evidence does not change clean close. The parser cannot use these booleans as activation authority, and stop callbacks run first.

Helper package 0.8.4 is installed and its reviewed payload matches. MODEYIELD2, its strict calibration route, quiet/held checks, confinement and original lease remain unchanged. Event delivery is unresolved and the update is diagnostic, not a live fix. See [contract and interpretation limits](../docs/STREAM_COVERAGE_DIAGNOSTICS.md).


A fresh actual 0.8.10 provider verified the expected build, matching disk sources and all seven tools with sharing closed and zero held input; the installed helper hash matches. No new sharing or live event-delivery trial was performed, and the root cause remains unresolved.


## Controller post-ARM gate (plugin 0.8.11 candidate; helper unchanged)

The helper remains installed package 0.8.4. The controller alone adds a retained MODEYIELD2 startup gate: after initial ARM it keeps ready false while requesting a fixed mouse-only notice and waiting at most 30 seconds for actual YIELDED/QUIET, then an epoch-matched RESUME/ARMED acknowledgement. The known notice must be closed before activation; unknown closure remains terminal. Initial calibration and the original helper lease still apply. Default close-policy startup is unchanged.

This does not repair source delivery or establish physical provenance. No new helper installation, permission/group/ACL change or grab probe is needed. Plugin 0.8.11 is installed with the same helper 0.8.4; live acceptance is unresolved. See [controller readiness contract](../docs/POST_ARM_READINESS.md).


A fresh actual 0.8.11 provider verified build `d9365aaf2ec194b81bb855405f8737bbb3a2e813779550309bc88fd17acf0eb9`, matching disk sources and all seven tools, with sharing closed, zero held input and capture/input disabled. All 411 Python tests, 16 native fixtures, loader/schema discovery and skill validation pass. No new live trial was performed; mouse-event delivery and automatic return remain unresolved.
