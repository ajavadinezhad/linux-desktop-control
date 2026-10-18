# Privacy boundary

The optional collector reads raw kernel input events internally. Codes and
values enter its process memory. It does not interpret key meanings as text,
accumulate pointer coordinates, or export the raw stream. Saying that it never
reads raw input would be incorrect.

Only fixed readiness/calibration/reset, ARMED, activity/fault/ALIVE notifications and terminal calibration diagnostic bits leave the helper
over its private channel. No key codes, text, pointer deltas/coordinates, event
timestamps, device identifiers, or raw file descriptors are exported to the
backend or assistant. Event contents are not logged, persisted, or included in
fault messages. The client can send only the fixed arming, heartbeat, and close
commands; it cannot subscribe to events or request alternate devices.

Administrator approval happens in the system's own dialog after personal GNOME
portal consent. Monitoring is disarmed during authorization. No task screenshot
or automated input is allowed before successful ARMED. Passwords must not be
placed in chat or command arguments. The optional mode defaults to false; normal
control does not invoke this helper or its administrator prompt.

The fixed, root-owned executable opens covered devices read-only. Raw descriptors
remain inside that process after it removes supplementary groups/capabilities,
drops credentials to `nobody`, disables dumpability, enables `NO_NEW_PRIVS`, and
applies seccomp confinement. It does not grab devices, inject input, or change
device ACLs. `nobody` is shared with unrelated software and provides weaker
isolation than a dedicated account. These measures do not defend against a
compromised operating system or administrator.

The private connection is bound to peer credentials and requester lifetime with
`SO_PEERCRED` and a pidfd. After becoming `nobody`, the collector creates its own
system-bus connection to verify and watch the requesting logind session; it
does not retain a root bus connection. Session changes and loss of verification
fault conservatively. Monitored device-topology changes also fault.

HB/ALIVE exchanges occur every 0.2 seconds, with a one-second deadline. The
absolute 120-second lease is not extended by heartbeats. Channel loss, requester
death, expiry, activity, or fault ends monitoring and closes descriptors. The
backend must close its channel whenever sharing ends. The helper does not
independently attest portal ownership; channel lifetime, pidfd, and lease provide
separate bounds.

Eligible UHID/uinput events count. A stop signal therefore does not establish
human identity or physical provenance. GNOME portal virtual input creates no
evdev device, but actual deployment behavior remains to be tested live. GNOME's
own sharing stop remains independent of the helper.

The current evidence is a build and isolated tests. The helper is not yet
installed or live-verified; do not infer verified device coverage, live cleanup,
or assistant integration from these documents.

Activity kind is a fixed coarse enum: key/button, pointer, switch, metadata or held-state. It contains no event codes, identities, values or coordinates; key includes pointer/touch buttons. Terminal diagnostics contain only eight calibration booleans, sent after raw descriptors close. They cannot authorize control.
