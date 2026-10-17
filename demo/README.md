# Reproducible clean demo

Use only the included disposable fixture. Never open personal documents or accounts for a demonstration. A recording is real screen footage, not evidence that every toolkit or safety property works.

## Scene

1. Run `/usr/bin/python3 demo/app.py --work-dir /tmp/linux-desktop-demo` from the repository. It opens a maximized GTK4 scratch window with no document/account connections.
2. Keep the demo window above unrelated applications. Move the pointer away from the dock. The recording must be stopped before the demo window is closed or any other application is shown.
3. If recording, use the separate `demo/record.py` helper: `/usr/bin/python3 demo/record.py --output recordings/demo.webm --stop-file /tmp/linux-demo-stop --seconds 120`. Choose fresh output/stop paths each time. It opens a normal GNOME ScreenCast consent dialog; personally choose the primary monitor. It records silent WebM through PipeWire/GStreamer, without keyboard or mouse permission. It does not bypass GNOME consent and stops after at most 180 seconds or when its stop file appears.
4. Start desktop control normally and personally approve its separate keyboard/pointer sharing dialog. Do not automate any consent or human toolbar button.

**The recorder is separate from the desktop-control session. Pause/Stop closes assistant capture/input but does not stop the intentional demo recording. Keep only public scratch content visible throughout.** The output is local and ignored by Git until reviewed.

## 45–90 second shot list

- Establish the clean demo scene and visible real toolbar.
- Assistant inspects the image, acquires an editable target, types `Hello from GNOME. α`, and verifies the actual visible result.
- Assistant edits the scratch selection and opens the included scratch Save dialog. Acquire a fresh target and enter `demo.txt`; save and compare the actual UTF-8 bytes in the scratch directory.
- Human clicks **Pause**. Show paused toolbar; assistant status confirms closed sharing and no capture/input. No assistant screenshot or input is performed while paused.
- Human clicks **Continue** and personally approves fresh sharing. Assistant inspects fresh pixels and acknowledges the recovery token before appending one short final line.
- Human clicks **Stop**. Assistant reads status to confirm closure. Stop the separate recorder immediately; only then close the scratch window.

Record enough time for the human steps; do not manufacture button clicks or fake consent footage. No need for a racing countdown. If a dialog or target differs, stop and inspect instead of replaying uncertain input.

## Review before publication

Decode and inspect the start, each transition and end, then review the entire video. Reject any clip showing private applications, notifications, paths, account names, chats or credentials. Do not upload unreviewed footage. Label cuts and captions honestly; never present isolated/synthetic button tests as human host interactions.

Recording API: [XDG ScreenCast portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html). GNOME also provides a [native screenshot/screencast UI](https://help.gnome.org/gnome-help/screen-shot-record.html).

## Current private video

The first reviewed 15-second clip shows real assistant-driven visual typing of Greek/Latin text and a scratch Save, with a magnified crop of the actual line and opaque chat-panel redaction. It does not contain a physical Pause/Continue/Stop sequence and is not a guarded-target demonstration: this custom fixture did not expose a unique active accessible window. Historical guarded acceptance used GNOME Text Editor instead. The separate recorder and desktop-control session were stopped before closing the fixture.

## Extended feature take

The 59-second private part-one cut adds actual GTK4 guarded replacement, Latin/Greek/Persian/emoji entry, pointer movement, wheel scrolling to the end marker, exact4,520-byte save and native file reopening. Private opening frames and a chooser transition are cut; headers and the floating chat panel are opaque-redacted. The complete toolbar stays in frame. No physical Pause event was received during the take; a second recording consent request timed out. The human Pause/Continue/Stop segment remains pending, so this is not the completed full demonstration. All recording and control sharing was stopped and toolbar ownership released.

## Cross-application demonstration

The cross-app clip uses a fresh temporary folder in GNOME Files, opens a public scratch note in Text Editor, performs a guarded multilingual edit and saves exactly40 UTF-8 bytes, then visibly switches to an isolated local Chrome page. Actual button clicks and wheel scrolling create a28-byte download. Returning to Files shows the new artifact; double-clicking it reopens the result in Text Editor.

`cross-app-report.html` is a standalone, local-only fixture with no external resources. For reproduction, copy it into a fresh scratch directory, launch Chrome with a new temporary `--user-data-dir`, and set that disposable profile's download directory to the same scratch folder. Do not use a personal browser profile. Prepare the windows first; the visible app transitions, editing, clicking, download and reopening must be driven through actual desktop tools and inspected images. After an app switch, typing requires fresh inspected editor identity. No human Pause/Continue/Stop sequence is claimed by this clip.

The system editor adds an implicit terminal newline. Exact byte comparison caught an extra blank line; a guarded edit removed that line before final verification. The record includes genuine actions, with only idle time removed and private floating chat/volume labels redacted. The full desktop scene and toolbar remain visible.

## Recorder status and full-desktop framing (0.6.2)

The recorder now defaults to the entire selected monitor, including its top panel, at up to 3440 pixels wide. Cropping or downscaling requires explicit options. Keep only public scratch apps on a clean workspace; do not switch to personal windows during capture.

The private atomic sidecar `<output>.status.json` reports `awaiting_consent`, `recording` with remaining seconds, `finished` with a stop reason (including `time_limit`), or `failed`. Check it before every new scene: do not perform an action assuming it is being recorded after the timer ended. The sidecar is not a screenshot and cannot replace visual verification of the actual recorded source. A failed initialization removes only its own empty reserved video; nonempty partial footage is preserved for private inspection.
