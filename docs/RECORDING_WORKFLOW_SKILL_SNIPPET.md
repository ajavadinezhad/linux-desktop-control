# Proposed operator guidance: recorded desktop tasks

When the user requests a recorded workflow, start the recorder and verify it before the first creative edit. For music, select explicit system playback-monitor audio; silent recording does not satisfy that request. GNOME recording consent remains human-only. Do not create content while consent, pipeline startup, or output progress is unconfirmed.

Run the canonical `demo/recording_guard.py` checker with the explicit output/status paths and `--require-audio` for music. Retain the successful recording identity and bind subsequent checks with `--recording-id`. Recheck after control recovery and at meaningful production milestones. A refusal stops creative work until recording is restored or the user changes scope. This helper is an operator workflow check; it does not enforce or grant desktop action authority.

Do not equate the screen-recording indicator with a live input-control session. Report each status accurately. A healthy recording can continue through recoverable control pauses, but it cannot renew control consent or expiry. Finalize the recorder explicitly at take completion, preserve partial nonempty evidence, and verify final playback. Never record expected password prompts; stop and finalize owned recorders before that action.

If the user asks to start over, begin a new composition after recording is verified. Existing unrecorded material may be preserved separately, but do not pass its playback or later edits off as recorded creation.
