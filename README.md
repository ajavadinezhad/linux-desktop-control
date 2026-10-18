# Linux Desktop Control

**0.6.5 candidate files installed; live test blocked.** GNOME still caches the old extension and refuses hot reload. The extension is disabled; save work and manually log out/in before testing. The reported pointer issue is not established as resolved. See [pointer incident and source changes](docs/POINTER_RECOVERY_0_6_5.md).

Consent-based desktop tools for **GNOME 51 on Wayland**, with a small human-operated **Pause · Continue · Stop** toolbar.

Version **0.6.5** is an independent local MCP integration for the Codex desktop app. It uses the public XDG Desktop Portal, PipeWire and a user-scoped GNOME extension. It is not an official OpenAI product, and it does not provide universal Linux desktop support.

## What it does

- Observes one personally selected primary monitor and operates keyboard/pointer input.
- Keeps a visible human control toolbar outside assistant-clickable space.
- Closes capture and input on Pause; Continue requires fresh personal sharing consent and a fresh assistant observation.
- Stops queued work, releases held input, closes sharing and clears the in-memory handoff on Stop.
- Optionally binds keyboard input to a short-lived, single-use accessible control identity. Changed, protected or unsupported targets are refused when a guard is requested. Multiple reported active windows are accepted only when exactly one focused editable control is found.

**No root input devices, remote listener, clipboard access, unattended consent, or private GNOME Shell Eval.**

## Compatibility

Validated environment: Ubuntu GNOME Shell **51**, Wayland, system Python 3 with PyGObject/Gio/GLib/GStreamer, PipeWire, GNOME's desktop portal, and libxkbcommon. The GStreamer elements `pipewiresrc`, `queue`, `videorate`, `videoconvert`, `pngenc` and `appsink` must be available. GTK fixture tests additionally use GTK3/GTK4 and Pillow.

Actual assistant tests passed GNOME Text Editor multilingual editing/save/reopen and separate windows, human Pause/Continue reconciliation, and Chrome 155 local ASCII form/scroll/download workflows. Version 0.6.1 passed guarded typing in a GTK4 editor and Save filename field, an exact 20-byte saved file, and stale-token rejection with zero delivered events. Other GNOME versions, other desktops, browser Unicode/native browser dialogs, Firefox, Qt and Electron are unverified. See [validation and limitations](docs/VALIDATION.md).

## Install

Keep this checkout in a stable folder, then run:

```sh
./install.sh
```

Run `./install.sh --check` first for read-only environment checks. Normal installation also refuses missing requirements before any changes. The installer resolves the local server path, installs the user-scoped extension `desktop-toolbar@local.codex`, and registers the local plugin marketplace. It preserves other enabled extensions. Set `CODEX_BIN` if your Codex executable is not `/usr/lib/chatgpt/resources/codex`.

First extension discovery may require you to save your work and log out/in. The installer never restarts your desktop. Refresh the app's MCP connection after installation. Check that `desktop_status` reports version 0.6.5 and that the optional `inspect_target` / `target_id` arguments are present.

Ask the assistant to perform a disposable task. Personally select one primary monitor and enable keyboard/pointer control in GNOME. The assistant must never approve that sharing dialog or click Pause/Continue/Stop for you.

## Tools

| Tool | Purpose |
| --- | --- |
| `desktop_status` | State metadata without capture; bounded foreground state waiting |
| `desktop_start` | New personal GNOME sharing session and first image |
| `desktop_observe` | Fresh image; optional editable-control identity |
| `desktop_action` | One bounded, interruptible input transaction and fresh image |
| `desktop_pause` | Close sharing and retain a nonsecret task handoff |
| `desktop_resume` | Resume only after explicit human readiness and new consent |
| `desktop_stop` | Release input, close sharing and clear handoff |

Inspect every returned image. A dispatched transaction is not proof of semantic app success. After uncertain partial input, inspect a new observation and acknowledge its recovery token before deciding the next action. Never automatically replay an uncertain save/send. Input batches are interruptible, not atomic or reversible transactions.

Continue can restore sharing for an active foreground assistant waiting on status. **It cannot wake an assistant turn that has already ended.** Send a new chat message in that case.

## Repeated host approvals

App tool approval and GNOME sharing consent are separate. The host supports persisted approval for individual plugin tools in the user config; installation does not silently grant this permission. See [configuration](docs/INSTALLATION.md#optional-standing-tool-authorization) for an explicit opt-in scoped to the seven existing tools. A post-app-restart test completed eight actual tool calls without host approval prompts; GNOME consent remained required.

## Demo and privacy

[Demo instructions](demo/README.md) use only disposable text and an optional consented, silent WebM recorder. No personal footage or historic desktop screenshots are included in this repository. The recorder is independent of desktop control; stop it before leaving the clean demo window.

The backend normally keeps images in memory and returns them to the MCP host. The host's conversation history may retain those images. Accessibility checks read identity/state/geometry, not accessible names, text values, selections, passwords or clipboard contents. See [privacy](docs/PRIVACY.md) and [architecture](docs/ARCHITECTURE.md).

## Test

```sh
/usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
/usr/bin/python3 tests/check_loader.py
```

The unit suite contains 172 tests. The loader test uses a temporary Codex home, loads the real installed client, checks all seven tool schemas, and never requests desktop sharing. Isolated toolbar rendering can be tested with `dbus-run-session -- /usr/bin/python3 tests/check_toolbar_shell.py`; this refuses an existing GNOME Shell bus. On a dbus-broker host without dbus-run-session, use `python3 tests/check_private_toolbar.py`. JavaScript feedback regressions use Node.js (`NODE_BIN` can select its path). Live human acceptance is separate from unit and isolated rendering tests.

## Remove

Stop sharing first. Then:

```sh
/usr/bin/python3 uninstall-toolbar.py
/usr/lib/chatgpt/resources/codex plugin remove linux-desktop-control@local-linux-desktop
```

Use your configured `CODEX_BIN` path if different. Remove any standing approval entries you added. This removes only this extension/plugin; it leaves your source checkout and other extensions intact.

## License

A license has not yet been selected by the project owner. No license grant is implied by this private release preparation. The owner intends compensation for commercial use; terms are pending. Dependencies retain their own licenses. See [licensing review](docs/LICENSING_REVIEW.md), especially the GNOME Shell extension constraint.
