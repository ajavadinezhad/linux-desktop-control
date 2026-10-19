# Coordinate mapping investigation

## Observed scope

The 0.8.5 physical calibration and ARM handshake passed on the selected primary monitor at logical origin `(0,0)` with size `1920×1200`. The captured image was `3840×2400`. A guarded Super transition produced an overview observation with frame `(0,0,1920,1200)`.

One left click was requested at logical `(960,580)`, targeting the visible editor overview card. The returned image showed the desktop, but the foreground observation remained on the other monitor, frame `(1920,0,3440,1440)`. The editor was not established as the active target. No text or drag was sent.

Inspection of the original full-resolution image places the visible cursor tip near image pixel `(960,580)`, approximately logical `(480,290)` under the advertised conversion. This is a **visual estimate**, not an exact GNOME pointer snapshot. The result persists when viewing the original image rather than the smaller tool preview. The intended card center was approximately image pixel `(1920,1160)`, so the requested logical point followed the response's conversion rule.

The operator closed sharing instead of trying another target. Explicit close and subsequent status confirmed portal closure, zero held input, zero failed releases, no cleanup warning, and helper exit code zero. Sanitized structured evidence is in the adjacent release artifact `LIVE_0_8_5_STARTUP.json`; no screenshots are stored in this document.

## Local implementation

`desktop.py` chooses its public dimensions from stream `logical_size`, falling back to `size`. Its `position()` validates those public bounds and forwards the coordinates unchanged to portal `NotifyPointerMotionAbsolute`. Capture pixel dimensions are reported separately. A capture-to-logical ratio alone does not establish transport units or justify multiplying pointer coordinates.

## Upstream source chain

The installed package versions were GNOME Shell `51.0-2ubuntu3`, Mutter common `51.0-1ubuntu3`, xdg-desktop-portal `1.21.1+ds-1ubuntu6`, and its GNOME backend `51.0-0ubuntu1`.

- [Portal 1.21.1 remote-desktop.c](https://raw.githubusercontent.com/flatpak/xdg-desktop-portal/1.21.1/src/remote-desktop.c), `handle_notify_pointer_motion_absolute`, lines 873–930: validates the position, then forwards the same x and y to its implementation backend.
- [GNOME portal 51.0 remotedesktop.c](https://raw.githubusercontent.com/GNOME/xdg-desktop-portal-gnome/51.0/src/remotedesktop.c), lines 755–776: resolves the stream and forwards x and y unchanged to Mutter.
- [Mutter 51.0 meta-remote-desktop-session.c](https://raw.githubusercontent.com/GNOME/mutter/51.0/src/backends/meta-remote-desktop-session.c), lines 722–759: passes the stream coordinates through `meta_stream_transform_position` before emitting absolute motion.
- [Mutter 51.0 meta-stream-monitor.c](https://raw.githubusercontent.com/GNOME/mutter/51.0/src/backends/meta-stream-monitor.c), lines 100–122: the monitor transform divides stream coordinates by the logical monitor scale when stage views are scaled, then adds the monitor origin. At scale two this predicts the observed approximate half-distance endpoint.

This source chain supports a platform transport-unit mismatch as an explanation. It does not establish that every backend has those units, nor that the local Ubuntu packages are byte-for-byte identical to the upstream tags. No generic scaling workaround was applied.

## Stream metadata investigation

[GNOME portal current gnomescreencast.c](https://raw.githubusercontent.com/GNOME/xdg-desktop-portal-gnome/main/src/gnomescreencast.c), lines 209–251, emits stream `size`, `position`, source type, id and optional mapping id. The examined function does not export `logical_size` or a separately named transport size. Its stream construction reads Mutter's `size` parameter unchanged. This is the current main branch, **not verified release 51.0 source**: fetching that file at the release tag failed. It is therefore a lead rather than proof of the installed stream metadata.

The actual 0.8.5 session response did not retain the original stream property dictionary, so it cannot distinguish an explicit `logical_size` from the `size` fallback. The selected public dimensions and capture dimensions are established; the provenance of those public dimensions is not.

No local packaged source tree was identified. Network access from the shell was unavailable, and a distro patch comparison was not completed. The upstream source was inspected read-only; no external code was installed or executed.

## Requirements before a runtime correction

The portal frontend's `check_position` also validates requested absolute coordinates against the stream's advertised bounds before forwarding them. Blindly multiplying logical coordinates by capture scale can therefore produce coordinates outside those accepted bounds, especially on the right or bottom of the monitor. Even where such a request passes, acceptance does not establish correct target placement. A safe correction must resolve both the frontend bounds and downstream transform rather than treating a doubled coordinate as generally valid.

The diagnostic-only `stream_metadata.py` allowlists bounded `position`, `size`, `logical_size`, known source-type values, and whether a mapping id exists. It does not export the id, other properties, a scale inference, or control authority. Keeping both size fields distinct will establish which metadata the next consented session actually supplied without guessing their provenance.

Preserve the public logical coordinate system, observation guards and bounds. Establish the transport coordinate contract from explicit, validated metadata or an independently verified backend capability. Do not infer transport scale solely from screenshot dimensions: capture negotiation may resize images. A mismatched or ambiguous mapping must refuse target clicks before their activating press. Any correction needs isolated coverage for scaled, unscaled, nonzero-origin and malformed metadata cases, followed by a fresh consented live check. Same-window physical typing and held-button drag acceptance remain unverified.
