# Desktop acceptance — 0.6.4

Tested 2026-10-17 on GNOME Shell 51, Wayland, one primary monitor. This is a private review candidate.

## Results

49 application/control assertions passed. The scratch GTK witness, localhost browser telemetry and exact saved/downloaded file bytes independently checked results; dispatch alone was not treated as success. Returned screenshots were inspected throughout.

| Surface | Confirmed behavior |
| --- | --- |
| GTK3 input lab | Single/double/right click, pointer drag/release, slider, wheel both directions, checkbox, dropdown, exact Latin/Greek/Persian/emoji input, selection, replacement, navigation, Delete/Backspace, single-line entry, Tab/Space and modal opening |
| Native GTK dialogs | Save and reopen exact multilingual 33-byte scratch file |
| Chrome 155, disposable profile | Exact multilingual input/apply, undo/redo, checkbox/dropdown, scrolling/end navigation, new tab/switch/close, exact download and native file input |
| Firefox 158, disposable profile | Exact multilingual input/apply, checkbox/dropdown, scrolling both directions, exact download and native file input |
| GNOME windows | Maximize, minimize/restore, title-bar move, keyboard resize and pointer-border resize |
| Files | Rename, create folder and drag file into destination; exact 31-byte content preserved |
| Physical toolbar | Human Pause, Continue with fresh GNOME consent, required fresh observation, and Emergency Stop; stopped input was refused |
| Capture recovery | A real stalled pipeline recovered through a single capture-only reconnection under existing consent |

The first GTK input assertions used the installed 0.6.3 assistant tools. Changed-code acceptance used the 0.6.4 backend through its public stdio MCP interface with personal GNOME consent. This does not establish that an already connected 0.6.3 assistant process refreshed itself. Historical GTK4/Text Editor acceptance remains in VALIDATION.md.

Final desktop_stop reported stopped, portal_closed_confirmed=true, with capture/control released and no cleanup warning. Emergency Stop was followed only by an explicit human request for a new sharing session.

## Failures found and reconciliation

- 0.6.3 could stop producing fresh frames after a second window opened. 0.6.4 reconnects only capture once on a frame timeout, preserving the consented portal and refusing to replay input. Frames still require a recent timestamp; normal capture retains its settling fence. The replacement pipeline begins after a cancellation-aware settling wait and uses drop-only videorate. A second timeout or other pipeline error propagates. Recovery can add several seconds of latency.
- A 40ms three-point file drag did not move the file. A gradual path with a short final hover did; the destination bytes were verified. Applications can require drag activation/hover time. Use a sufficiently paced path and verify the effect.
- A rapid dropdown-to-text sequence left the popup open. Reacquiring the visible choice and waiting before text entry resolved it. A bounded input sequence does not establish application readiness.
- A changing scratch directory moved chooser rows. Exact full paths or a clean single-file directory avoided stale row targeting. Initial wrong scratch selections were detected and corrected locally.
- A user reply brought ChatGPT forward during a browser chooser test. One scratch path entered the unsent chat draft. It was not sent; only the inserted text was cleared after inspection and the browser was reacquired. Visual focus acquisition is not a general window-identity guarantee.

## Remaining limits

Optional accessibility identity inspection returns D-Bus AccessDenied on this connection. No identity guard was claimed and permissions were not bypassed. Coordinate workflows require fresh visual inspection. Physical takeover is not automatically detected by the portal. Clipboard operations are absent. Qt, Electron, other desktops, other GNOME versions and multi-monitor configurations remain unverified. This evidence does not certify every application or privileged operation. No communications, purchases or personal-file edits were performed as tests.

Raw screenshots, local telemetry, profiles and recordings stay outside the source archive. A sanitized assertion list is included at tests/acceptance-0.6.4.json.
