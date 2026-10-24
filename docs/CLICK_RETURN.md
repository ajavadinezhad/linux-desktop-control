# Automatic continuation after an ordinary click

> The version and installation claims below describe historical checkpoints. Consult [release status](RELEASE_STATUS.md) for the recorded published baseline and remaining checks.

Plugin 0.8.23 and helper 0.8.10 are installed, with all 14 plugin files matching reviewed source. All 527 controller tests, 51 native fixtures, and the seven-tool loader check pass. Live click-recovery acceptance is still pending. The update lets supervised retained sharing pause on an ordinary left, right, or middle click instead of closing. Keys, scrolling, unsupported buttons, protected system UI, revoked sharing, and observer faults retain terminal handling outside the separate expected-permission wait.

Select `click_policy="pause-return"` with native physical observation and retained sharing at startup. The default remains `"close"`. The helper must acknowledge the new click protocol; no fallback treats an older helper as compatible.

Physical click activity cancels the current operation, discards queued work, releases virtual input, and suspends capture while keeping consent. Held clicks and continued movement keep the pause busy. After released input, complete queues, and 1.5 seconds of quiet, a separate click-aware resume handshake becomes eligible. The original session deadline continues throughout.

Recovery checks the current ordinary foreground context and monitor mapping. If the saved context and confirmed destination still match, the controller may perform one guarded pointer return. If the click selected another ordinary window, it resumes capture there without moving focus or returning to the old point. A fresh image and new observation tokens are required before deciding the next task action. Interrupted clicks, typing, and other queued work are never replayed.

Foreground changes can arrive before the native click notification. Under this explicit policy only, a bounded correlation period cancels input and suspends capture while waiting for matching click evidence. A missing match, protected context, or changed session owner closes the session. This does not establish causal proof of which event changed focus, nor universal takeover coverage.

An explicit manual Pause remains sticky and does not automatically resume. Stop and revoked sharing are final. Isolated checks and live device acceptance must be reported separately.
