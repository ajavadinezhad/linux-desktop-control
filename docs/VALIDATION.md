# Validation scope

## Automated and loader checks

The release source passes 153 automated tests covering portal/toolbar ordering, queue cancellation, key release, image publication fences, partial-input recovery, target-token lifetime/state changes, bounded accessibility transport, foreground status waiting, and toolbar nonce/sender/sequence validation. A real bundled Codex loader test checks all seven current schemas without a model or live desktop consent.

## Actual assistant acceptance on the development host

- GNOME Text Editor: exact multilingual file bytes (Latin accents, Greek, Persian and emoji), selection replacement, wheel scrolling, native save/open, close/reopen, and a separate second window.
- Physical human Pause during input: portal closure, new human Continue and consent, fresh observation, and repair of only the unfinished line without duplicate prior content.
- Chrome 155: disposable profile and local fixture; ASCII edit/replace/apply, real scrolling and exact downloaded bytes. No account or external service was used.
- Version 0.6.1 keyboard guard: GTK4 editor and Save filename input passed, with an exact 20-byte saved file. A target invalidated by an intervening action was refused before input. This case proves token invalidation, not independent detection of a widget disappearing without intervening tool input.
- Persisted host permission policy: after app restart, eight actual tool calls completed without a host 'Allow Linux Desktop' prompt. One new GNOME sharing session still required personal consent. Stop confirmed capture/input off and no cleanup warning.
- Isolated GNOME 51: real toolbar rendering, bottom placement, dock clearance, focus retention, button signals and lifecycle were tested on a separate private desktop. Synthetic isolated button tests are not human host-button proof.

Raw host evidence stays private because screenshots/logs can contain unrelated visible content. This is a scope summary, not a claim that all independent reviewers can reproduce every host setup without personal consent.

## Known limitations

- Only GNOME Shell 51 / Wayland / primary monitor has host acceptance. Other distributions, desktop environments and Shell versions are unverified.
- Browser Unicode and native browser dialogs, Firefox, Qt and Electron are unverified.
- Accessibility support varies. GTK4 may not support `Component.GrabFocus`; an already focused exact control is accepted after fresh validation, while unavailable focus acquisition is refused.
- Identity checks are not atomic with keyboard delivery. Initial visual focus clicks can have effects before a subsequent guard rejects input; no rollback is promised.
- A first pointer move may jump, smooth pixel scroll is unsupported, and changing docks/fullscreen can affect toolbar geometry.
- Transient file dialogs can disappear. Prefer bounded same-call focus acquisition and inspect every result. Never type into a disappeared chooser using old coordinates.
- Guarded input can be partial on a slow application. Read completed event/character metadata and reconcile fresh pixels; do not retry blindly.
- Continue does not wake an ended assistant turn. OS calls may delay cleanup. Already delivered input and already published images cannot be undone.

## Version 0.6.2 hardening

New regression checks cover uniquely focused editors across multiple active-window reports, ambiguous/protected/hidden candidates, complete bounded window enumeration and late accessibility replies. Installer tests cover unsupported sessions, missing dependencies and timeouts before changes. Recorder tests cover full-monitor defaults, constructor failure cleanup, partial-file preservation and private atomic status reporting. The current host passes the read-only installation preflight. New multi-window live acceptance and recording-sidecar live acceptance have not been run; historical live results above belong to 0.6.1 and earlier.

The attempted isolated headless GTK4 lifecycle check did not pass: that test environment did not expose a uniquely active accessible window. It is not counted among the 149 passing automated checks. The experimental harness/logs remain private; this release does not claim new live acceptance from it.

## Version 0.6.3 host check (2026-10-17)

The actual assistant connection reports server_version 0.6.3. Consented visual input entered Latin accents, Greek, Persian and emoji into the disposable GTK4 fixture, used its scratch Save dialog, and produced an exact 75-byte UTF-8 file. The saved file was reopened and visually verified in GNOME Text Editor; app and same-app window switching were exercised. These are real host checks, separate from the automated suite.

Optional target inspection returned D-Bus AccessDenied on this assistant connection. No target identity was issued or claimed, and no access policy was changed. Guarded multi-window host acceptance therefore remains incomplete. Physical Pause/Continue and Emergency Stop checks for this version are still pending; historical results above do not substitute for them.

Malformed tool-call arguments, stale Pause events, stale-epoch Emergency Stop and invalid numeric/key input have automated regression coverage. The real Codex loader discovered all seven tools at version 0.6.3, and environment preflight passed.
