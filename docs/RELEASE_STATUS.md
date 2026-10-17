# Private review status — 0.6.3

Prepared 2026-10-17. This is a private technical review candidate, not a general availability release.

## Confirmed

- 153 automated tests pass; real Codex loader discovers all seven tools.
- Read-only preflight passes on the development host.
- Actual 0.6.3 host visual workflow: multilingual scratch input, exact 75-byte save, reopen in GNOME Text Editor, and window switching.
- Historical GTK4/Chrome and human controls evidence is scoped in VALIDATION.md.
- Private source archives exclude raw screenshots, recordings, credentials, generated machine-specific configuration and scratch documents.
- Owner chose to keep source private and defer a reuse license. No distribution rights or commercial terms are assigned.

## Still required

- Current-version physical Pause/Continue and Emergency Stop acceptance.
- Resolve or document connection-specific accessibility D-Bus AccessDenied; guarded multi-window live acceptance remains incomplete.
- Private GitHub repository must exist and be accessible to the connected account before upload. Verify private visibility before writing.
- Choose an outreach recipient and sending account. Outreach remains an unsent draft.
- Confirm authorship and dependency obligations before licensing or broader distribution. See LICENSING_REVIEW.md.

## Review materials

The source archive and 63-second silent demonstration are prepared separately. The video is edited historical scratch-workflow evidence, excludes physical Pause/Continue, and is not a recording of 0.6.3 acceptance. Keep it private; review footage for unintended visible information before any wider release.

Supported host evidence is limited to GNOME Shell 51, Wayland and the primary monitor. Other desktops, Shell versions and untested toolkits are not certified.
