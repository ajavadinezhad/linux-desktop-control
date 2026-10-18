# Architecture

The stdio MCP transport reads cancellation and session-closure requests independently while serializing desktop work. A generation fence prevents old queued input or images crossing a session closure. GNOME desktop portals own consent and virtual input. Capture is PipeWire/GStreamer; input is bounded and releases held state in finally blocks. Session closure releases the portal before bounded capture teardown.

Optional accessibility identity checks do not read field contents. The read-only foreground observer has Bind, Update, Unbind, GetDiagnostics and GetContext methods plus a context-change notification. It has no input injection APIs, custom control toolbar or shortcuts. A short owner heartbeat lease and D-Bus owner watch hide its passive text on loss. Guarded sessions require its read-only foreground context; discovery/status/cleanup do not.


The optional `SetPhysicalGuard(nonce, enabled)` method adds session-only source
metadata observation, disabled by default. `desktop_start(physical_takeover=true)`
checks capability before requesting portal consent, then authenticates the
method after active binding. The passive Clutter filter always propagates
input. Native device-node presence latches unavailable context and advances the
existing authenticated ContextChanged epoch. The bridge observes that state
also between actions and requests session closure; it does not replay input or
reclaim focus. Cleanup disables the local observer, attempts remote disarm,
unbinds ownership and closes the portal.

Protocol remains 2; normal operation works with the prior pointer-snapshot
helper. Optional metadata observation requires manually loaded helper revision
4. Tests cover source paths and cleanup, not actual physical-device event
coverage. Null/unknown provenance is unsupported, and source classification
cannot attest human input. See [same-window takeover](SAME_WINDOW_TAKEOVER.md).
