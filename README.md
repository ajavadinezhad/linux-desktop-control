# Linux Desktop Control

Version **0.7.0** is a private local MCP integration using GNOME Wayland's public desktop portal. It is an independent project, not an official OpenAI product.

Five tools: `desktop_start`, `desktop_observe`, `desktop_action`, `desktop_status`, `desktop_close`. The final tool releases session resources. Each new session needs personal GNOME monitor/keyboard/pointer consent. GNOME's native sharing control remains available independently.

An optional indicator-only GNOME extension displays **Mouse is being controlled by ChatGPT** below the pointer while the assistant session is active. It is passive, non-focusable and untracked by the Shell input-region/workarea manager. It disappears on closure, disconnection, lease expiry or disable. It never moves or hides the cursor, captures input or registers shortcuts. The real cursor remains unchanged: a safe public API for directly applying a glow to the hardware cursor has not been established. No surrounding ring or duplicate cursor is drawn.

Core control has no extension prerequisite. `indicator_warning` explicitly reports an unavailable label. Loading a newly installed GNOME extension can require a manual logout/login; the installer never restarts the session. No live input acceptance of 0.7.0 has been performed.

## Install

Run `./install.sh --check` for read-only environment checks, then `./install.sh` to prepare paths, copy the optional indicator and install the local plugin. Refresh the app's MCP connection after updating; already connected chats can retain an older catalog. The optional indicator installer is `python3 install-indicator.py`. Remove only that indicator with `python3 uninstall-indicator.py`.

## Use

Inspect each fresh screenshot before input. Coordinates use logical monitor units. Keyboard/text input must acquire focus in the same call. Bounded sequences allow 1–8 steps and begin with an observed click or a visible focus shortcut. Discrete wheel steps and paced Unicode composition are supported; clipboard access is absent. Initial pointer motion can jump because the portal exposes no reliable pointer position; the label's position is not a tool observation. Dispatch does not prove semantic success.

After uncertain input, obtain and inspect `desktop_observe` and pass its recovery token before further input. Never replay automatically. Optional accessibility identities are single-use and refuse ambiguous/protected/stale controls without fallback. Some connections return AccessDenied.

Call `desktop_close` on completion or error and check `portal_closed_confirmed` and `cleanup_warning`. Cancellation, client disconnection, process termination and idle expiry also close the session. Portal closure is attempted before bounded capture teardown. Blocking OS calls can still delay cleanup; use GNOME's native sharing control if closure cannot be confirmed. The portal does not reliably distinguish human from synthetic input; moving the physical mouse alone is not an automatic cancellation signal.

## Verify

`/usr/bin/python3 -m unittest discover -s tests` checks input validation, release/cancellation/disconnect behavior, fresh capture recovery, target identity and uncertain-input reconciliation without sharing. `python3 tests/check_loader.py` checks the real app loader and all five schemas in a temporary Codex home. The indicator bridge has isolated transport tests; the new extension has no live-host acceptance. Do not run a headless GNOME compositor on a live user manager: it can change activation display settings even with a private D-Bus bus. Use a separate test environment for graphical tests.

Source remains private; reuse licensing is deferred. No compensation or distribution terms are assigned. See docs/LICENSING_REVIEW.md.
