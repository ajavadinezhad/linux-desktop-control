# Architecture

The stdio MCP transport reads cancellation and session-closure requests independently while serializing desktop work. A generation fence prevents old queued input or images crossing a session closure. GNOME desktop portals own consent and virtual input. Capture is PipeWire/GStreamer; input is bounded and releases held state in finally blocks. Session closure releases the portal before bounded capture teardown.

Optional accessibility identity checks do not read field contents. The read-only foreground observer has Bind, Update, Unbind, GetDiagnostics and GetContext methods plus a context-change notification. It has no human control signals or input APIs. A short owner heartbeat lease and D-Bus owner watch hide its passive text on loss. Guarded sessions require its read-only foreground context; discovery/status/cleanup do not.
