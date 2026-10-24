# Compatibility

**Preview:** GNOME Shell 51 on Wayland is the only currently supported target. Support for other platforms is planned, with no release date or compatibility guarantee.

The installation preflight currently requires **GNOME Shell 51 on Wayland**. Other desktops and GNOME versions are not validated. Consent must select exactly one monitor and allow keyboard and pointer control.

| Area | Evidence and limits |
| --- | --- |
| Applications | Scoped Firefox, native Save/Open and LibreOffice Impress workflows; not every app or dialog |
| Displays | Tested primary screen in a two-monitor layout with scale 2 and a vertical offset; not general mixed-DPI acceptance |
| Window fitting/moving | Explicit configured shortcuts; same window must fully arrive; ambiguous layouts refuse |
| Physical takeover | Host-specific keyboard interruption, endpoint-based drag cleanup, and native relative-mouse yield/return trials across recorded versions; no universal device coverage |
| Reconfiguration | Layout, mode, scale, rotation, mirroring, ownership or topology mismatch refuses input; no seamless hotplug claim |

## Coordinates

Actions use selected-monitor logical coordinates. Screenshot pixels must be converted using the reported logical and pixel sizes. The controller binds portal geometry to GNOME DisplayConfig, observes the current global pointer, sends a relative displacement, and verifies arrival before effects. It does not multiply coordinates blindly or retry a missed endpoint.

Rotation, mirroring and unsupported layout modes are refused. A pointer outside the selected monitor is not automatically reclaimed. Foreground and dispatch checks are asynchronous and cannot guarantee atomic priority over an event already sent.

See [current status](RELEASE_STATUS.md) and [remaining physical checks](archive/BETA_ACCEPTANCE.md).
