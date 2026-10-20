# Optional native physical-activity helper

> Historical design proposal. Use [the helper guide](README.md) for the current implementation and [release status](../docs/RELEASE_STATUS.md) for acceptance.

Status: implementation requirements and review boundary, not evidence of installed or
tested behavior. This component supplements the consented GNOME portal backend. It
does not replace GNOME sharing consent, application approvals, or explicit resume.

## Purpose and limits

While desktop automation is active, physical keyboard or pointer activity should
latch a takeover signal. The backend then interrupts its transaction, releases its
held inputs, stops capture, closes sharing, and enters human handoff. Activity in
the same application/window must count. No window identity or idle heuristic is
needed.

The kernel exposes raw event codes and values through evdev. The collector must
receive these internally to classify activity. The privacy promise is that key
codes, text, motion values, coordinates, event timestamps, and device identifiers
are never exported to the assistant, persisted, logged, or included in errors.
This is not a promise that raw events never enter process memory.

Detection and portal input dispatch are asynchronous. A synthetic event already
in flight may race with the human event. This helper cannot promise that human
input wins atomically, or that all human-input sources are covered. Remote desktop,
accessibility software, unusual hardware, and synthetic devices require explicit
compatibility evaluation. A compositor-level implementation would have a stronger
event-ordering boundary but requires a maintained Mutter integration.

## Deployment boundary

Prefer one short-lived, compiled C executable over an always-running root service.
There is no setuid bit. A separate administrator-reviewed installer copies the
executable and narrowly scoped polkit policy to root-owned locations. Runtime is
invoked through `pkexec` for the fixed executable only. No shell, plugin Python,
user-writable imports, command string, configuration file, device path, or executable
path is evaluated with privilege. The helper contains its policy decisions.

The polkit action must require administrator authentication for an active local
session, deny inactive/remote callers, and avoid retained authorization. The policy
and executable path must agree. Installation is separately approved; building a
workspace binary does not authorize installation or opening input devices.

Minimum elevated operation: validate the authorized requester and session,
enumerate the fixed physical-device policy, open eligible event nodes read-only,
and prepare a topology monitor. Do not add the user to `input`, change device ACLs,
change ownership/modes, request input grabs, open `/dev/uinput`, or inject input.

## Requester identity and channel

1. The backend creates a private local control channel before launching `pkexec`.
   Use a random-named socket in the user's runtime directory with mode 0600 and a
   directory owned by that user. Bound the pathname length and startup timeout.
2. The privileged helper validates directory/socket ownership without following
   attacker-controlled symlinks, connects once, and obtains `SO_PEERCRED`. The
   helper must cross-check that peer UID against the authorized original user
   (`PKEXEC_UID` is corroboration, not sufficient identity proof).
3. Bind the peer PID using `pidfd_open` before acting on it, then validate the
   requester's active local login session and seat using trusted logind data.
   Caller-provided PID, UID, session, or seat strings are not authorization.
   A pidfd/identity mismatch or unsupported identity check is a startup failure.
4. The backend validates that the connected helper is the expected root peer
   before sending its fixed protocol handshake. Authenticate the peer before
   privilege drop; do not infer current identity from credentials cached after
   drop. Permit one connection, no descriptor transfer, and no reconnection.
5. The protocol has fixed message sizes, a version, and finite deadlines. The
   unprivileged consumer gets only readiness, latched activity, or generic fault.
   It cannot request device enumeration, raw events, alternate FDs, commands,
   arbitrary paths, or continued monitoring after takeover.

Do not trust a filesystem socket name alone. If the concrete transport differs,
review equivalent mutual identity and parent-lifetime properties before use.

## Device allowlist and topology

The first implementation covers the whole eligible physical keyboard/pointer set
on the requester's active seat, rather than arbitrary caller-selected paths. It
must identify eligible event nodes using trusted udev/sysfs ancestry and input
capabilities. `ID_INPUT_*`, device names, bus names, or an event-node prefix alone
are insufficient. Exclude virtual/uinput/portal devices and non-keyboard/non-pointer
devices. Ambiguous classification fails startup rather than silently omitting a
possibly relevant keyboard or pointer. Record no device inventory in user-visible
logs.

For each admitted node, use `O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW`, confirm
with `fstat` that it is the intended character device, and revalidate the device
identity against enumeration. Never use `EVIOCGRAB`. Event values must not be
written back. No raw event FD may reach the backend or model process.

Set up a trusted udev input-subsystem topology monitor before enumeration and
check queued topology changes before reporting ready. `libudev.so.1` may be loaded
dynamically when development headers are absent; missing runtime library, monitor
setup failure, or unavailable required symbols means unavailable protection.
Never substitute a fake success. A deployment may choose ordinary libudev build
dependencies instead.

Any relevant add/remove/change, monitor overflow/disconnect, event FD EOF/error,
or `SYN_DROPPED` terminates protection with takeover/fault. Hotplug is not silently
ignored or reopened under retained privilege. Restart requires fresh validation
and administrator authorization. Physical device eligibility and actual portal
virtual-device exclusion must be tested on the target GNOME host before enabling
the feature by default.

## Privilege drop and collector

After opening the fixed allowlist and monitor/channel descriptors, clear all
supplementary groups and capabilities, set real/effective/saved GID and UID to the
selected unprivileged collector account, enable `PR_SET_NO_NEW_PRIVS`, and disable
dumpability. Check every result; a partial privilege drop is fatal. There must be
no privileged parent process left waiting for arbitrary requests.

A dedicated account is preferable. If this version uses `nobody`, disclose that
it shares an identity with unrelated software and therefore offers weaker
same-UID isolation. Set dumpability off after credential changes and prohibit
raw-FD export. Do not claim a dedicated sandbox from UID change alone.

After setup, install a tested seccomp allowlist for only the required read/poll,
fixed-channel write, close, monotonic time, memory/runtime, and exit operations.
Do not permit new sockets, exec, open/openat, device writes, arbitrary ioctl,
ptrace, or privilege changes. If library-based topology handling requires new
filesystem access after sandboxing, resolve that explicitly (for example prepare
the monitor FD before drop and parse bounded notifications) rather than silently
broadening permissions. This is a requirement to validate against actual syscalls,
not a claim that an untested filter is safe.

Use bounded buffers and no core dumps. Consume event packets promptly. Keyboard
press/repeat/release and meaningful pointer button/motion/wheel activity count;
`EV_SYN` alone does not. Unexpected supported-device event types, malformed
records, and lost events fail closed. Do not inspect key meanings, combine key
events into text, or accumulate pointer coordinates. On first activity, emit one
fixed takeover message and immediately close device FDs and exit.

## Lifecycle and backend gating

The broker is armed before any desktop action is permitted. A failed broker
startup must not fall back to a weaker detector while reporting protection.
Opening portal consent must remain an explicit user operation; avoid counting
the administrator/portal approval interaction as task-time activity by defining
and testing the arm boundary. Before arming, drain old events and require no held
physical input; inability to establish that boundary is a failure. Never delay
arming until after synthetic task input has begun.

The backend holds the channel only during the protected active portal session.
Every pause, stop, portal revocation, startup failure, or shutdown closes it.
Collector monitors socket EOF, requester pidfd death, session becoming inactive
or locked, topology/event failure, and a bounded lifetime/heartbeat deadline.
Any such condition closes all raw FDs and exits. Heartbeats are fixed liveness
messages, not permission to extend beyond an absolute maximum lifetime.

The helper must not claim independently verified portal ownership merely because
the backend says a portal exists. Its portal-close guarantee depends on backend
channel teardown, with requester death and finite expiry as independent bounds.
If independent portal subscription is implemented, verify its exact bus and
session identity rather than accepting arbitrary object paths.

Backend receives takeover/fault, immediately increments its transaction generation
and sets its stop event before awaiting cleanup. Pending input and capture replies
from older generations are rejected. Release held portal inputs and close capture
and the portal; expose cleanup uncertainty. Never resume automatically after idle
time, reconnect, activity quieting, or helper restart. Human explicitly requests
resume, approves required dialogs, and the assistant obtains a fresh observation.

## Required evidence before claiming support

- Parser/classifier tests using synthetic records, including SYN-only packets,
  physical activity, malformed input, `SYN_DROPPED`, virtual-device exclusion,
  topology changes, and bounded protocol handling.
- Privilege-drop and sandbox failure injection; no successful readiness after any
  failed identity, device, monitor, credential, or confinement check.
- Verify no raw-event bytes or device identifiers leave the collector in success,
  error, stdout/stderr, logs, core files, or protocol payloads.
- Lifecycle tests for requester exit, socket disconnect, timeout, portal close,
  handoff, and locked/inactive session. Verify FDs close and no helper remains.
- Live administrator-approved target-host tests: all physical keyboard/pointer
  sources latch same-window takeover; portal-generated motion/typing do not;
  monitor loss and hotplug stop automation; held synthetic input is released.
- Assistant-driven observe/action/takeover/fresh-resume test through actual loaded
  tools. Manual helper tests do not establish assistant tool integration.

Until these pass, report the feature as experimental or unavailable and keep the
existing explicit handoff/stop controls available. No Windows parity, perfect
physical-source coverage, zero-race input priority, or upstream support is implied.

## Primary references

- Linux evdev event semantics and lost-event handling:
  https://docs.kernel.org/input/event-codes.html
- Polkit privileged mechanism and authorization model:
  https://polkit.pages.freedesktop.org/polkit/polkit.8.html
- logind session/controller/device semantics (do not take GNOME's controller):
  https://github.com/systemd/systemd/blob/main/man/org.freedesktop.login1.xml

