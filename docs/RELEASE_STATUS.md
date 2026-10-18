# 0.6.5 source candidate — not installed

Live control and the installed toolbar remain off following the reported pointer incident. The symptom is unresolved; do not reenable or start until the user explicitly says ready. See [diagnosis, source changes and isolated verification](POINTER_RECOVERY_0_6_5.md).

# Private review status — 0.6.4

Prepared 2026-10-17. Private technical review candidate.

- 159 automated tests pass; real Codex loader discovers seven tools.
- 49 real application/control assertions passed across GTK3, Chrome 155, Firefox 158, Files and GNOME windows. Historical GTK4/Text Editor evidence remains separately scoped.
- Human Pause/Continue and Emergency Stop passed; final sharing is confirmed closed.
- Capture timeout recovery reconnects capture once under existing consent without replaying input.
- See [acceptance and remaining limits](ACCEPTANCE_0_6_4.md). Optional accessibility inspection returns AccessDenied; focus changes, app timing, other toolkits and other host configurations remain limitations.
- Source backup: https://github.com/ajavadinezhad/linux-desktop-control (private). Archives exclude raw screenshots, recordings, credentials, generated machine configuration and scratch files.
- Owner chose to keep source private and defer reuse licensing. No distribution rights or commercial terms are assigned. See LICENSING_REVIEW.md before wider distribution.

The separate 63-second edited historical demonstration does not record current acceptance or physical controls. Keep it private. Updating an installed plugin does not refresh already connected assistant processes; confirm server_version after reconnecting.
