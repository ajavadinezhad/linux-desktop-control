# Experimental preopened-fd activity reader — not a working takeover backend

This isolated prototype is outside the installed plugin. It demonstrates bounded Linux `input_event` framing using pipe fixtures. It does not open any device, obtain elevated privileges, install a service, change permissions/group membership, connect to a portal, watch a live desktop, or integrate with desktop control. No real device access or live acceptance has been performed.

`reader.py` accepts an explicitly inherited, nonblocking fd numbered 3 or higher. The caller must be its only reader. It supports the native 64-bit Linux 24-byte `input_event` ABI, consumes at most 4096 records or three seconds by default, reads event **type** plus the EV_SYN synchronization code solely to detect SYN_DROPPED, and discards timestamps, key/button codes and all values without decoding/logging them. EV_KEY, EV_REL or EV_ABS produces one coarse activity result and exit. SYN/MSC and other types do not. EOF, timeout, partial records, oversized chunks, exhausted budgets, read errors and SYN_DROPPED fail closed. There is no quiet/false-success result and no resynchronization/replay after loss. Even an otherwise idle timeout means unavailable monitoring, so the desktop task must cancel. Even a key release conservatively counts as activity.

The stdout protocol contains only newline-delimited fixed tokens:

- `READY` after transport/ABI validation; this is not proof of device access or human provenance.
- `ACTIVITY` for a matching input event, then exit 0.
- `FAULT` for unavailable/failed monitoring, then exit 2. Startup errors emit FAULT without READY.

A consumer must treat missing READY, EOF, unexpected tokens, dropped IPC or loss of its own deadline as FAULT and cancel the desktop task. READY is not a heartbeat or an authorization to inject input. There are no device names, event types, timestamps, key codes, values or coordinates in the protocol. This is source activity, never proof of a human: privileged software can create kernel virtual devices too.

Tests (no input devices):

```
python3 -m unittest discover -s experimental/native-activity
```

Ten tests cover split framing, key/motion/absolute events, ignored synchronization/metadata records, SYN_DROPPED, partial EOF, budgets, timeouts, fd ownership, rejection of regular/blocking fds, and real subprocess fixtures checking READY/ACTIVITY/FAULT, startup errors, EOF, partial records and unavailable timeouts. No sample key codes/values are exported.

## Missing privilege boundary

A preopened evdev fd grants access to the full raw event stream even when this reader elects not to decode it. The raw fd MUST NEVER reach the assistant process or desktop backend. Passing it there would be a broader privilege grant than coarse activity notification. This prototype MUST NOT be wired into the plugin or installed as a privileged launcher.

A future separately reviewed broker should retain the raw fd inside a small, root-owned, least-privilege process, discard event contents there, and export only authenticated READY/ACTIVITY/FAULT notifications to the authorized active session, with fault causing immediate cancellation. It needs explicit administrator installation/authorization and an authenticated local IPC contract, tightly selected device nodes, no event/node logging, a bounded active lease, owner-loss cleanup, lock/greeter/session restrictions, hotplug/revocation handling, and tests that synthetic injection cannot masquerade as an exempt input source. The assistant must not modify udev ACLs or input group membership, acquire/force the compositor's logind control, or install/setuid a launcher as a workaround. Those privileges are not currently available or configured. No broker or installer is provided here.

udev supplies device discovery/hotplug metadata, not keystroke/motion activity; libinput still needs authorized device fds. logind TakeDevice is for the exclusive session controller, not a second passive monitor alongside GNOME. RemoteDesktop EIS authorizes sending emulated input, not observing native activity. InputCapture diverts activated input and uses compositor-triggered barriers; it is not passive takeover detection.

The previous Clutter filter candidate failed the actual client-input trial. Function availability alone was insufficient: older Mutter filters can consume client events before the later extension filter. Do not promote this reader's passing pipe tests into a claim that same-window takeover works.
