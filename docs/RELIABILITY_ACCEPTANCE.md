# Reliability acceptance plan

This is a proposed release gate for the supervised GNOME/Wayland desktop service and its separate read-only local-model adapter. It is not a claim of perfect control, general desktop support, or automatic wake in ChatGPT or LM Studio's chat interface. Criteria apply to a named build, machine, input devices, model and task set; passing one combination does not certify another.

## Evidence already available

- The installed 0.8.41 controller baseline passed 671 controller/recorder tests; the unchanged helper retains its prior 86-check result. These results predate the latest adapter-only changes.
- The affected adapter, observer, notification and takeover suites passed 43 tests. They cover changed frames, reconnect ownership, delayed results, interruptions, timeout behavior and notification coalescing. Those 43 checks are a scoped checkpoint; the later combined 689-test baseline is recorded in [release status](RELEASE_STATUS.md). Later local Qwen-client work remains separate from that published baseline.
- Four generated Calculator screens passed twelve literal recognition checks. Independent model calls took approximately five to nine seconds. This is neither real-app action accuracy nor cross-frame memory.
- One separate read-only live adapter run completed notification → fresh image → model description → verified sharing closure. Inference took about 49 seconds and the result indicated newer frames existed.
- Earlier scoped live controller checks covered pointer takeover observation, explicit handback, settings navigation and Calculator. They do not cover the complete matrix below on the candidate build.

See [current release evidence](RELEASE_STATUS.md) and [observer and adapter contract](CONTINUOUS_OBSERVER.md). Historical evidence is useful context, not a substitute for candidate-build acceptance.

## Order and release blockers

1. **Authority and freshness:** no unauthorized input, stale-token action, post-Stop publication or delayed description presented as current. A single violation blocks release.
2. **Recovery and cleanup:** no replay, focus reclamation, held virtual input or unexplained terminal closure. Investigate every failure rather than treating retries as successful runs.
3. **Useful task accuracy:** measure completed real workflows against independent outcomes. A plausible model description is not proof of a successful action.
4. **Responsiveness:** measure the whole loop, then optimize the largest component. Accuracy gates stay in force when tuning speed.
5. **Installation and publication:** verify the reviewed candidate in a fresh client before publishing its scoped evidence and known limits.

Offline workers can run independent fixtures and analysis in parallel. Exactly one live operator owns the desktop; real-app workflows, human interventions and installation are sequential. The read-only model adapter must not be treated as an action agent. Autonomous action testing needs a separately reviewed harness and explicit bounded action authority.

## Proposed acceptance matrix

All quantities and timing targets below are **proposed**, not achieved results or product guarantees. Use non-private fixtures and disposable task files. Do not include checkout, public messages, account changes or credentials.

| Area | Candidate test | Proposed pass condition | Execution |
| --- | --- | --- | --- |
| Real-app workflows | Calculator arithmetic, local text editing with save/reopen, and navigation in a local browser fixture; ten attempts per workflow across at least three fresh consented sessions | At least 29/30 independently verified correct completions; no authority/freshness violation; any failure explained and reproducible before acceptance | One live operator; model may observe |
| Recognition and transitions | At least 20 labeled scenes across those apps, including dialogs, changed numbers, ambiguous layouts and two successive state changes | At least 95% of predefined task-critical fields correct; uncertainty/refusal counts as incomplete, not correct; no invented current-state claim after a newer frame | Generated fixtures first, then consented real-app frames |
| Physical takeover | Pointer movement, ordinary typing, held modifier, Alt+Tab, four-finger contact/swipe and partial finger release; three repeats per supported case | Input remains paused through all held contact; observation only when permitted; handback uses fresh state; no replay or forced switch back; no unexplained session loss | Human performs real contact; replay fixtures supplement it |
| Stale action prevention | Old observation, changed foreground, changed geometry, replaced stream, takeover during a queued batch and delayed model result; three repeats per case | Every invalid action refused before further input; delayed results labeled captured-frame-only or discarded when observation unavailable; no observation-only frame grants input tokens | Deterministic race fixtures plus scoped live checks |
| Stop and protected state | Stop during observation, model inference and a bounded input batch; manual Pause; authentication/protected context; revocation | Zero new input or server image publications after authority is invalidated; pending waits cancel; no automatic restart; adapter discards unavailable results | Offline faults first, then consented live Stop; never enter a real secret for testing |
| Fault and cleanup | Model timeout, malformed response, client disconnect, helper exit, capture failure and blocked notification output; three repeats each | Clear bounded failure; no replay or implicit lease renewal; portal closure confirmed when applicable; zero held virtual input; unresolved cleanup warning blocks acceptance | Injected fixtures; selected live disconnect checks |
| Long session | Three consented sessions exercising the supported 20-minute maximum, ordinary takeover and notification bursts; one full-duration expiry | No unexplained closure before deadline; no authority after expiry; no frame backlog; pending hints stay bounded; no continuing growth in retained objects or processes | Offline accelerated clocks plus sequential live sessions |
| Latency | At least 30 turns per workload, warm/cold model runs reported separately | Publish p50/p95 and maximum for each stage and end-to-end; proposed warm simple-frame p95 ≤10 s; record complex-frame failures against that target rather than claiming real-time behavior | Offline model runs can overlap code review; live timings single operator |
| Install and compatibility | Fresh direct client against installed candidate, runtime fingerprint, tool schemas, helper compatibility and current skill | Reviewed bytes match installed runtime; tool loading passes; one real workflow and clean closure pass; no unsupported client/desktop claim | After combined tests and review |

For long sessions, record memory/process samples at startup and one-minute intervals. Proposed resource gate: observer storage remains one frame, pending notification/model work remains at most one hint and one inference, no leaked child processes, and steady-state retained memory has no unexplained monotonic growth. Absolute resident-memory limits require a baseline because capture and model allocation are separate; do not count model weights as an observer leak.

Timing cannot be inferred from a unit-test timeout. Measure Stop-to-input-cancellation and Stop-to-cleanup separately. Proposed responsive-control target: cancellation p95 ≤500 ms and sharing cleanup p95 ≤3 s on the tested host; report blocked platform calls and maxima explicitly. An already submitted model image cannot be recalled, and an in-flight inference may outlast sharing. That is a documented boundary, not continued desktop authority.

## Measurement and evidence format

For every run record the candidate fingerprint, platform/device scope, model configuration, scenario, expected outcome, actual outcome, pass/fail, cleanup state and timings. Use monotonic timestamps for screen change, notice receipt, guarded frame publication, model request/response, action dispatch/completion and cleanup. Do not subtract clocks from separate processes unless their clock relationship is established. Report overlapping stages without double counting.

Keep machine-readable counts and concise failure categories. Preserve the first failure and its reproduction; retries remain separate attempts. Screenshots are opt-in evidence, not default logging. Store no raw input events, passwords, tokens or unrelated user content. Published evidence should include attempted runs, failures, exclusions and untested scope, not only successful examples.

## Completion checklist

- [ ] Confirm candidate version/fingerprint and test harness scope.
- [ ] Run full affected regression and schema/loading checks after final code changes.
- [ ] Complete authority, stale-action, terminal-state and cleanup gates with zero violations.
- [ ] Complete real-app and supported interruption matrix; fix and rerun failed scenarios.
- [ ] Complete long-session and full-duration expiry checks.
- [ ] Publish latency distributions with cold/warm and synthetic/live separation.
- [ ] Review combined changes; install and verify the candidate in a fresh client.
- [ ] Remove verified superseded probes/artifacts, preserving user media and active runtimes.
- [ ] Publish only verified changes, scoped results and remaining limitations.

Meeting these gates supports the statement “accepted for these supervised tasks on this tested configuration.” It does not establish universal reliability, unattended all-day operation or continuous model awareness in proprietary chat interfaces.

## Parallel review checkpoint — 2026-10-23

Three independent workers completed the acceptance matrix, adapter boundary review, and bounded observer stress work. The adapter now rejects invalid capture identity before inference and discards delayed descriptions when the stream is replaced or its revision regresses. Fourteen focused adapter tests pass.

The combined controller/recorder/adapter suite passed **689 tests in 34.759 seconds** with local socket access. The initial restricted run encountered socket permission failures; that run is not counted as passing. No native helper code changed in this checkpoint. [Stress evidence](OBSERVER_STRESS_RESULTS.md) records synthetic repetition counts and its limits.

One fresh direct session against installed 0.8.41 passed a scoped live check: observed launch of Calculator, 84/2 = 42, manual Pause (capture and input disabled; resource stream absent), explicit resume with a new stream identity and fresh image, then requested close. Cleanup confirmed portal closed, zero held input, no cleanup warning and helper exit 0. The arithmetic sequence input stage took 536 ms; its capture took 430 ms. These are backend stages, not end-to-end model latency. The session lasted about 104 seconds despite selecting a 1200-second lease; it is not a 20-minute soak result. Passive source coverage remained explicitly unverified.

The complete acceptance matrix remains open: this checkpoint did not run 30 real-app workflows, new human gesture repetitions, full-duration sessions, an autonomous action-model harness, or 30 latency samples. The adapter fix is source-only; installed controller bytes were unchanged and no publication was performed.
