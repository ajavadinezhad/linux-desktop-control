# Privacy

Screen capture and input require personal GNOME consent. Screenshots can show personal data; only capture within the authorized task. Optional accessibility reads identity/state/geometry, not field values or clipboard. The helper reads pointer coordinates for passive label rendering and returns fresh pointer snapshots to the backend for mapping movement to the selected monitor. Context is in memory. Session close, error, disconnect and idle expiry release virtual input and the portal. Use GNOME native sharing controls if cleanup is unconfirmed.

The foreground guard reads a stable window sequence, frame geometry, context kind and monotonic epoch through the helper. Window titles, app text, clipboard and physical key/mouse event contents are not read. These context observations fence input but do not establish physical-input provenance.


Optional `desktop_start(physical_takeover=true)` expands observation to global
source-device metadata during that consented active session. Default false
registers no event listener. The helper tests only source-device presence and
whether its native device-node field is nonempty; it never reads key contents,
buttons, event coordinates or device names, and does not export or log device
paths. It exports a latched cancellation state through the existing context
channel. Owner/lease loss, closure and protected UI remove the listener.

This candidate needs helper revision 4 and real-device acceptance. Capability
presence is not readiness. Unknown sources are unsupported; native device
activity is not proof that a human supplied it. Physical activity which leaves
the foreground context unchanged is not a reliable cancellation mechanism in
the default mode. See [same-window takeover](SAME_WINDOW_TAKEOVER.md).
