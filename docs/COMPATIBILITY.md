# Compatibility and display validation

This is a scoped GNOME Wayland desktop-control implementation, not a guarantee
for every Linux desktop, display arrangement or application. Personal portal
consent for exactly one monitor and keyboard/pointer remains required.

| Configuration or behavior | Evidence | Limit |
| --- | --- | --- |
| Current GNOME desktop, Firefox and native Save/Open chooser | Live 0.7.5 workflow, saved article reopened | See LIVE_0_7_5.md for exact evidence; other apps and dialog timings remain unverified |
| Human Alt+Tab during guarded wait | Live 0.7.5, zero input events after task cancellation | Held-input interruption is isolated-test coverage, not live coverage |
| Secondary display left/above primary; negative and positive origins | Isolated mapping and window-bound tests | No physical multi-monitor acceptance run |
| Fractional logical coordinates and 1x/1.25x/1.5x/2x raster densities | Isolated logical mapping contract | No live mixed-DPI or fractional-scaling acceptance run |
| Pointer outside selected monitor or missing monitor origin | Refused by mapping validation | The backend does not move the pointer onto the shared monitor automatically |
| Window movement, resize and scale/context epoch change | Isolated foreground fence tests | Monitor hotplug/rotation/resolution changes are not live accepted |
| Protected/unavailable foreground | Isolated immediate refusal and capture suppression | Only explicit transitions may settle through temporary no-foreground state; protected UI is refused |
| Themed cursor glow | Live Firefox/native chooser and restoration | Custom application cursors may ignore the theme; not universal coverage |

## Coordinate contract

Input coordinates use the selected monitor's logical width and height. GNOME
pointer positions and window rectangles use global logical coordinates. Mapping
subtracts the portal's selected-monitor origin exactly once. Window bounds add
that origin exactly once. Display edges are half-open: zero is valid, width and
height themselves are outside. Screenshot raster dimensions do not alter this
logical mapping; callers must convert observed raster positions using the
reported logical_size/pixel_size ratio.

The portal must provide an accurate monitor position and logical stream size.
The backend currently accepts portal `size` when `logical_size` is absent. This
fallback has not been validated on mixed-DPI physical hardware. Isolated tests
cannot establish that a compositor reports those properties in the expected
units. Do not infer fractional-scaling support from arithmetic tests alone.

Monitor topology is captured from portal session properties. Hotplug or changed
monitor geometry while a session is active needs separate hardware acceptance;
window/epoch fences do not independently prove current monitor topology. Close
sharing before changing display configuration, then start a newly consented
session. Do not claim seamless display reconfiguration.

Same-window physical pointer activity is not reliably identified as human
takeover. Foreground checks also have an unavoidable check-to-dispatch race.
See FOCUS_GUARD_0_7_1.md and LIVE_0_7_5.md for the precise boundary.
