# Native activity architecture — 0.8.0

## Components and trust

`opener.c` is the privileged entry point and includes the collector in `broker.c`.
This is one fixed compiled executable, not a privileged launcher for a Python
script or arbitrary command. The package installs only the root-owned executable
at `/usr/libexec/codex-desktop-activity` and the policy at
`/usr/share/polkit-1/actions/org.codex.desktop-activity.policy`. There is no service,
maintainer script, setuid bit, input-group membership, or device ACL modification.

`pkexec` invokes the fixed path. Policy action `org.codex.desktop-activity.monitor`
uses nonretained `auth_admin` for active local callers and denies inactive/other
callers. Each new protected session requires approval. The optional backend flag
defaults to false. Missing installation is refused before requesting sharing.

## Startup and arming

1. Preflight the installed fixed helper and required integration.
2. Obtain personal GNOME portal consent while capture/input remain gated.
3. Present the separate system administrator prompt before binding task-time
   foreground guards. This expected modal must not invalidate its own startup.
4. Authenticate the private Unix channel using `SO_PEERCRED` and `SO_PEERPIDFD`.
   Check the requester against the active local Wayland logind session and
   fixed `seat0` policy. Caller-provided identity alone grants no access.
5. Enumerate eligible kernel input nodes and open them read-only with identity
   checks. Prepare topology monitoring. No raw descriptor is passed outside the
   helper. Do not grab devices or inject input.
6. Remove supplementary groups and capabilities; set real/effective/saved UID
   and GID to `nobody` (65534), disable dumpability, and set `NO_NEW_PRIVS`.
   Establish the separate unprivileged system-bus session watch, verify unlocked
   state, then apply the seccomp allowlist. READY follows successful confinement.
7. Require ARM → successful ARMED before any task screenshot or automated input.
   ARM drains authorization-phase events, verifies released keys/buttons and
   rechecks queued activity, topology, and session health. There is no ignored
   activity grace after arming. Bind normal foreground protection and obtain a
   fresh valid application context before proceeding.

READY is not equivalent to ARMED. Denial, cancellation, bad handshake, held input,
or failed confinement closes sharing instead of claiming weaker protection.

## Data and event boundary

The private protocol reports only READY, ARMED, ACTIVITY, FAULT, and ALIVE.
Commands are fixed ARM, HB, CLOSE, and fault handling; there is no public filter,
raw-event subscription, alternate-device request, command execution, or raw-FD
transfer. Buffers, commands, and deadlines are bounded.

Raw event codes/values are received inside the collector and reduced to activity
or fault. No text, coordinates, event timestamps, or device inventory leave it
or appear in logs. Eligible UHID/uinput devices count conservatively. ACTIVITY
does not attest human identity. Portal virtual input does not create evdev
devices; live separation and device coverage still require verification.

## Lifetime and failure

`session_watch.h` creates its own system-bus connection after the UID drop, pins
the logind owner, verifies Active/LockedHint/Remote, and watches the requesting
session. Session-property changes, session removal, logind owner loss, or bus
failure latch FAULT. No root bus connection is inherited by this watcher.

Any monitored input-topology change, device failure/lost events, requester pidfd
death, or channel loss faults. The backend sends HB every 0.2 seconds and expects
ALIVE; the collector enforces a one-second heartbeat deadline. Its absolute
120-second lease starts at readiness and cannot be extended by heartbeats.
Activity/fault/expiry terminates the helper and closes its descriptors.

The backend invalidates transaction generations and gates further input/capture
before cleanup. It rejects queued old work and stale image replies, releases
held synthetic input, and closes sharing. Cleanup uncertainty must be reported.
The helper depends on channel teardown for portal-end notification; it does not
independently verify portal ownership. GNOME's sharing indicator remains an
independent stop. No removed toolbar or shortcut is reintroduced.

An already-dispatched synthetic event can race with takeover. This design cannot
retract it or promise atomic human priority. No automatic restart, lease renewal,
or resume occurs after activity becomes quiet.

## Evidence and remaining validation

The component is built and isolated tests have run. It is not installed or
verified with live input devices or an assistant-driven protected session.
Remaining evidence includes administrator approval/denial, same-window activity,
kernel-device coverage, portal-input separation, session/topology faults, lease
and heartbeat expiry, requester loss, descriptor cleanup, and stale work/image
rejection through the actual assistant tools.
