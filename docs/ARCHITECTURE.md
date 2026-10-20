# Architecture

The local MCP server exposes seven tools for starting, observing, acting, checking status, pausing, resuming and closing a desktop session. GNOME's RemoteDesktop portal owns consent and virtual input; PipeWire/GStreamer supplies capture.

A read-only GNOME extension supplies foreground identity, window geometry, context epochs, pointer snapshots and a passive control label. It does not inject input. The failed experimental Clutter activity filter is not enabled by the backend.

Before input, the controller checks fresh observations, foreground ownership, selected-monitor binding and pointer arrival. Session generations prevent old queued work and callbacks from crossing into replacements. Cancellation is read independently of serialized desktop work. Cleanup releases held input and the portal; uncertain releases remain tracked.

Optional physical takeover uses a separate administrator-approved native helper. It retains raw device access inside its confined process and exports fixed activity/fault messages. Calibration and, in retained mode, a separate post-ARM mouse readiness check must pass before capture or input. See [native architecture](../native-activity/docs/ARCHITECTURE.md).

Covered relative mouse movement can pause capture/input while retaining the consented session. Quiet can permit one checked cursor return; no old action is replayed. Stop, revocation, faults and expiry remain terminal. See [retained sharing](RETAINED_SHARING.md).

Relative movement uses fresh compositor coordinates with endpoint verification. Monitor layout, ownership, scale and window identity remain bound to the selected session. Explicit resize and move actions use configured shortcuts and require same-window containment afterward. No correction loop or unseen-window content is assumed.
