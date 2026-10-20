# Demo recorder

This directory contains the separate consent-based recorder used for the [bear demo](../docs/demo/README.md).

`record.py` defaults to 120 seconds and accepts up to 900. Recording does not grant desktop input authority or extend the control session. Use `--help` for recorder options.

Use disposable content and inspect full frames before sharing. Personal GNOME recording consent is required. Launch and operate apps through an observed, consented desktop session; do not prepare a scene through hidden app-control calls. See [the consent-first example](../examples/consent_first.py).

## Recording readiness

Start recording before creating demo content. `record.py` is silent by default. For music, explicitly select the actual playback source with `--system-audio-device <playback-source>.monitor`. The source must end in `.monitor`; the recorder never falls back to a microphone or default input if that source fails. Device names vary by host. A requested pipeline must reach PLAYING without a startup error and write output before it reports active recording.

Each run writes a private status sidecar with a recording identity, recorder process identity, boot identity, monotonic heartbeat, remaining time, output identity/progress, and explicit audio mode. Use the separate read-only checker before the first creative edit, after control recovery, and before each major milestone:

```sh
python3 demo/recording_guard.py --status-file /path/to/take.status.json \
  --output /path/to/take.webm --require-audio
```

On its first successful result, retain the returned `recording_id` and supply `--recording-id` on later checks so an unrelated new take cannot silently substitute. The checker refuses inactive, failed, finished, stale, malformed, stalled, mismatched, or nearly expired recordings. It requires private regular files and rejects final-component symlinks. It reads only the explicitly supplied output and status files; it does not execute or signal the reported process.

This is a **workflow readiness check**, not a desktop-input interlock. A successful check is momentary and does not prove that music is audible, content is private, or the final file plays correctly. The operator must actually run it and must stop creative input if it refuses. Finalize and decode-check the file before calling the recording complete.

Control and recording are separate sessions. A paused or closed control session does not prove recording stopped, and a failed recorder does not prove control stopped. Keep a healthy recorder running during recoverable control pauses; finalize it explicitly when the take ends. Preserve nonempty media on failure. Before any expected administrator-password interaction, stop and finalize owned recorders; do not capture that dialog. If production began unrecorded, say so and start a genuinely new take rather than representing existing work as recorded creation.
