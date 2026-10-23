# Release status

## Current notification update

Plugin **0.8.41** adds consent-scoped, explicit MCP resource subscriptions. Automatic notices contain only a fixed URI. The metadata resource reports current stream/revision and the age of the last published observation; it does not claim the model inspected that image. Notices are coalesced to at most one per second without a frame backlog and grant no capture or input authority.

Ten notification checks cover automatic delivery without observe requests, burst coalescing, no private frame content, pending unsubscribe, consent/lease expiry, publication freshness and invalid resource requests. Seven-tool loading and skill validation pass. The original notification checkpoint passed 671 controller/recorder tests; the latest combined controller/recorder/adapter regression passes **689 tests**. The native helper is unchanged at **0.8.18**, retaining its prior **86-check** result.

A separate **read-only LM Studio API adapter** now completes the notification-to-fresh-frame-to-model loop. Fourteen focused adapter checks and one scoped live model run pass; the model took 49.47 seconds, returned an explicitly stale-if-newer description, and cleanup verified closure. The current adapter also discards descriptions across stream replacement or revision regression and rejects invalid capture identity before inference. Four synthetic screens passed twelve literal recognition checks. These checks do not establish broad application accuracy. See [adapter contract and limits](CONTINUOUS_OBSERVER.md#read-only-lm-studio-adapter).

Automatic model wake in this local chat is **not implemented**. The documented OpenAI MCP Events webhook integration is a separate cloud feature; no webhook, public endpoint, outbound desktop upload or credential was added. See [continuous observer design and client integration](CONTINUOUS_OBSERVER.md).

The reviewed plugin files match installed 0.8.41, the current read-only adapter is installed separately as a local application script, and seven-tool loading passes. It is not started automatically. [Acceptance criteria](RELIABILITY_ACCEPTANCE.md) distinguish completed evidence from the remaining real-app and long-session matrix. [Bounded stress results](OBSERVER_STRESS_RESULTS.md) cover synthetic concurrency, not a real-time or full-duration guarantee.

## Scoped live acceptance

A fresh 0.8.41 session completed Calculator 84/2 = 42, manual Pause with no capture/input and no resource stream, explicit resume with a new stream identity, then clean requested closure. Portal closure, zero held input, no cleanup warning and helper exit 0 were confirmed. This approximately 104-second run did not test sharing revocation or full-duration expiry.


The preceding **0.8.40** build passed **661 controller/recorder tests**. Physical pointer movement paused input while a fresh read-only image remained available; explicit handback resumed control. App settings navigation and a Calculator handoff completed without sharing loss. Cleanup confirmed portal closure, zero held input and no warning. The combined direct-call workflow also returned action results and screenshots in one orchestration step. These are scoped checks, not proof of all takeover cases or an overall speed improvement.

The **0.8.39** synthetic 200-frame observer benchmark measured notification p50 0.014 ms and p95 0.024 ms with one-frame buffering. It excludes capture, model and transport delays. Both observer modes remain opt-in; pixels are ephemeral, not a recording or native video stream into the model.

## Supported scope and remaining checks

This is a supervised GNOME Shell 51 / Wayland preview. The portable observer core does not establish support for another desktop. Broad hardware/app coverage, lock/revocation/disconnect paths, display changes, held-input/Emergency Stop repeats and full-duration live expiry remain separate acceptance work. Passing fixtures are not a hard latency guarantee.

Sessions default to 120 seconds; native sessions may explicitly choose up to 1200 seconds at startup. Pause, heartbeat and notification subscriptions never renew that deadline. Recording has a separate 900-second maximum. Manual Pause, protected UI, authentication waiting, Stop, revocation and real faults retain their existing capture/input rules.

The README preserves both privacy-edited demo videos, with music first. Personal recordings and music projects remain local. Historical version evidence remains in [the changelog](../CHANGELOG.md), [performance measurements](PERFORMANCE.md), [touchpad scope](TOUCHPAD.md), [validation](VALIDATION.md), [beta acceptance](BETA_ACCEPTANCE.md) and [compatibility](COMPATIBILITY.md). Superseded installed-version paragraphs were removed from this current-status document; tests, user media and active installed runtimes were preserved.
