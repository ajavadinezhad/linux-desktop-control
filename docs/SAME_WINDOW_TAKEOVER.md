# Same-window physical takeover boundary

Research and optional source integration, 2026-10-18. No live compositor
callback, settings change, or live input was activated by this work.

## Current supported claim

The current context guard detects foreground-window/geometry/context changes.
Its pointer snapshot has coordinates, not event provenance. With the default
`physical_takeover=false`, motion or typing which leaves that context unchanged
is not detected by a device-source observer. The new optional observer awaits
manual helper reload and real-device acceptance; reliable same-window takeover
is not yet a verified claim. A successful Alt+Tab test cannot establish it.

## What GNOME 51 exposes

Installed `Clutter-51.typelib` introspection confirms:

- `Clutter.Event.get_source_device()` and `get_flags()`;
- `Clutter.InputDevice.get_device_node()`, bus/type/name metadata;
- `Clutter.event_add_filter(stage, callback)` and removal;
- inherited `Clutter.Actor::captured-event` on the stage;
- no public `InputDevice.is_virtual()` or `get_device_mode()` in this typelib.

These were enumerated with Python GI without initializing a display, connecting
to the Shell, or observing any user's events.

[GNOME's event API](https://mutter.gnome.org/clutter/method.Event.get_source_device.html)
returns a source device or null. The
[official native backend implementation](https://raw.githubusercontent.com/GNOME/mutter/main/src/backends/native/meta-input-device-native.c)
sets a device-node property for libinput devices, while its compositor-created
virtual-device constructor omits that property. This is a native-backend
implementation distinction, not a stable public human/automation attestation.

The [remote desktop backend](https://raw.githubusercontent.com/GNOME/mutter/main/src/backends/meta-remote-desktop-session.c)
dispatches NotifyPointer operations through virtual input devices. Those
events therefore cannot safely be identified by excluding only events marked
synthetic: the [Clutter event source](https://raw.githubusercontent.com/GNOME/mutter/main/clutter/clutter/clutter-event.c)
describes the synthetic flag for event-queue insertion, and exposes event
filters before signal delivery. A filter which always propagates can observe
without grabbing input. Merely finding a stage signal is not proof that all
client-window input reaches that signal on the actual compositor.

## Why this is not ready to claim

The optional observer expands observation to global source-device metadata
while explicitly enabled for a consented session. It exports cancellation
state, never key contents or device identifiers. It is implemented in source
but disabled by default and has not passed real-device acceptance.

A device node alone does not prove a human: kernel virtual devices can look
like ordinary libinput sources. A null source is ambiguous. Another remote
client or accessibility injector need not be this session's virtual device.
Device names, pointer-coordinate differences, timing, or comparisons with the
last commanded position are insufficient provenance checks. Own movement may
be delayed/coalesced and physical motion may coincide with an expected point.

The default session keeps the prior observation scope. Explicit opt-in is
required for the new listener. API presence alone establishes neither event
coverage nor accurate device classification. Keep those limitations visible;
do not replace them with a motion heuristic or claim human provenance.

## Required live acceptance for the optional observer

First establish event coverage and source classification on the actual native
GNOME 51 compositor with a session-only metadata probe. Require explicit scope
review. Retain only event category, monotonic timestamp and a boolean source
classification; never key contents, coordinates, device paths or names in
persisted logs. Remove the callback on every close/error/owner loss, and always
propagate human events. An unavailable/ambiguous classifier must fail closed
or explicitly report unsupported, never silently exclude activity.

Then use a public disposable scratch editor with the same window focused:

1. Prove own portal motion, scroll and typing do not self-cancel.
2. During paced harmless motion, have the user move the physical mouse without
   changing windows; verify remaining virtual events cancel and never reclaim.
3. During harmless typing, have the user press a safe key in that window;
   verify subsequent virtual key-down events stop and held virtual input releases.
4. Repeat with touchpad, button/scroll and drag, distinguishing the user's
   input effect from already-dispatched virtual effects.
5. Verify portal closure, no queued replay, label hidden and original cursor
   theme restored. Do not restart automatically after any interruption.

The operator must record actual event cutoff/release evidence. A fake test of
the classifier, empty batch, or Alt+Tab before dispatch is not this acceptance.
No asynchronous detector can undo already-dispatched input or promise atomic
OS-level arbitration between simultaneous devices.


## Optional source integration (disabled by default; live acceptance pending)

The helper source now contains an optional `SetPhysicalGuard(nonce, bool)` D-Bus
method. Protocol remains 2; metadata revision is 4. Default operation is
unchanged: no event filter is registered. `desktop_start` now accepts
`physical_takeover=true` as explicit opt-in and describes its observation scope.
Before requesting consent, the backend checks the helper capability and refuses
an unsupported request. After consent, active binding and an active update, it
authenticates `SetPhysicalGuard` using that owner nonce. Cleanup attempts
disarm, unbind and portal closure, including when the enable reply is lost.
Capability diagnostics distinguish API presence, opt-in state and an activity
latch; they do not assert classifier coverage or live acceptance. Older protocol
2 helpers remain usable with the default option.

After authenticated opt-in, an active owner registers the verified public
`Clutter.event_add_filter(global.stage, callback)` API. The callback reads only
source-device presence and whether `get_device_node()` is nonempty. It never
reads key contents, buttons, event coordinates or device names, and never emits
or logs the node. Every path returns `Clutter.EVENT_PROPAGATE`, including
exceptions. A nonempty source node latches activity, removes the filter,
advances the context epoch once and publishes the existing authenticated
ContextChanged signal. Context then reports unavailable until owner cleanup.
This is native device-source activity detection, not human attestation.

Null source and node-less compositor virtual input are ignored by the
candidate. Unknown provenance therefore remains unsupported. The candidate
removes its filter on inactivity, opt-out, owner loss, lease expiry, unbind,
protected UI and extension disable. Lock/protected UI also disarms opt-in;
there is no automatic rearm after unlocking. Callback/API/removal errors latch
helper failure, making subsequent context unavailable and refusing a rebind
until helper reload. A callback left behind by a failed removal is inert after
failure or ownership cleanup and still propagates input.

Five new Node fake tests verify disabled default, authentication, null-source
handling, passive propagation, one-shot epoch advance, lifecycle cleanup,
missing API refusal, error latching and metadata non-disclosure. These do not
prove actual compositor event coverage or physical takeover. Seven backend
tests cover default inactivity, pre-consent capability refusal, authenticated
ordering, invalid options, unbound refusal and failure cleanup. Activation
still needs manual helper reload, clear observation-scope disclosure and the
real-device checks above. No live helper reload was performed by this work.
