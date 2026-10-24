# Continuous observation and portability

## Product boundary

Build an AI-client-independent desktop service. The service owns observation, consent, precise input, intervention handling and recovery; model clients own reasoning, memory and task policy. A continuous stream is not proof that a model can understand video or act faster.

## Implementation sequence

1. **Portable observer core:** one ephemeral latest-frame slot, change revision, bounded waits and cancellation. No GNOME, GStreamer, MCP, model SDK or filesystem dependencies. Drop outdated frames instead of building a backlog.
2. **Existing capture adapter:** read the consented PipeWire/GStreamer stream continuously through one sample consumer. Preserve the existing fresh-frame settling fence and guarded screenshot publication. Stop and clear observation on pause, closure or capture failure. Keep recording independent.
3. **Client delivery:** retain the seven-tool MCP interface. Add an explicitly selected continuous-observer mode and optional bounded change waiting to observation. Return a stream identity and byte-change revision as metadata; neither is an input-authority token. Existing screenshots and action observation tokens remain necessary.
4. **Measure:** benchmark frame arrival to change detection, bounded cancellation and slow-client backlog. Separately measure event-to-model-decision and action completion in a real client. Report synthetic versus live results explicitly.
5. **Richer scene state:** add capability-based window/accessibility event adapters and adaptive frame selection. Changes in encoded image bytes are not semantic events; do not claim an animation or cursor movement represents task progress. Never infer trusted instructions from visible content.
6. **Additional desktops:** implement one compositor adapter at a time against the same contract and replay fixtures. Advertise supported capabilities instead of assuming GNOME semantics. Keep unsupported input/control features unavailable until their authority and recovery behavior are established.

## Prefer established interfaces

- Use XDG Desktop Portal RemoteDesktop/ScreenCast and PipeWire where the selected desktop backend implements them. Probe actual capabilities; Wayland alone does not guarantee support.
- Keep logical monitor geometry, scale and timestamps explicit at adapter boundaries. Never treat screenshot pixels as input coordinates automatically.
- Use accessibility through an adapter where supported; accessibility availability alone is not reliable target identity.
- Keep GNOME Shell context/authentication inspection isolated from the portable observer. Other compositors need equivalent verified adapters, not emulation through shell commands or forced focus.
- Keep the native physical-input helper as a separately advertised capability. Do not assume its admission rules or administrator setup are portable to another OS or every device.

## Privacy, authority and lifecycle

The first implementation is opt-in under an existing personally approved session. It neither launches at login nor grants always-on access. No raw frames are written to disk or uploaded by the observer. The model receives images only through the existing guarded publication path. Protected contexts and intervention still pause capture; Stop, revoked consent, native/observer faults and expiry remain enforced.

Every pipeline gets a new stream identity. Old identities cannot subscribe to a replacement stream, and old callbacks cannot populate it. Pause/close clear buffered pixels. A callback arriving after cancellation must be discarded. Change waits do not replay actions or renew consent, lease or idle deadlines. A failure must not silently revert to an unguarded capture path.

MCP change waiting is pull-based and may occupy the serialized tool worker. It is not unsolicited delivery to a model while that model is generating. A client integration or later event transport is required for model-side push; do not claim it is already available.

## Acceptance

- Fake frames demonstrate single-slot storage, no backlog, matching-content revision stability, timestamp validation, pause/close clearing and no post-cancel publication.
- Stop and disconnect interrupt bounded waits. Stale stream identities and revisions are rejected without granting input.
- GStreamer adapter fixtures verify a single sample consumer, frame freshness, reconnect ownership and clearing on teardown.
- Existing context, permission, native health, mapping, intervention and screenshot-publication tests remain green.
- A fresh consented live session must verify actual capture, intervention and closure before installed live behavior is called accepted. No broader desktop support or end-to-end speed gain is established by unit tests alone.

## Observation during physical takeover

The optional startup flag `observe_during_takeover:true` requires continuous observation and its retained native context modes. It separates read-only frame permission from input permission. Physical takeover keeps input cancellation set and releases virtual input. A single capture owner may retain fresh frames only while the native lease, consent, mapping and ordinary foreground checks remain valid. Paused `desktop_observe` returns explicitly observation-only images without action/target/recovery tokens, and binds publication to the same pause, generation, stream and foreground. A stale publication is discarded.

Explicit Pause still clears the buffer and stops capture. Stop, protected/system UI, authentication waiting, expiry and faults remain excluded. Returning to input restarts capture with a new stream and requires normal fresh observation. This flag does not extend session/recovery deadlines, continuously deliver frames to a model, or recognize every sensitive field within an ordinary application.

## Scoped cleanup audit

Reviewed the affected capture/pause paths and scanned Python test bodies for exact duplication. One identical pair exercises different fixtures (post-ARM startup versus an already-ready retained controller), so both remain. Default/manual pause-clears-capture tests remain current alongside the new opt-in behavior. The existing capture fallback serves clients that do not enable continuous observation; it is not dead code. Historical contract references and both benchmarks retain callers or documentation purposes. No user media or installed runtime was retired. This is a scoped dependency review, not proof that the entire repository is free of unused code.

## Local change subscriptions (0.8.41)

The existing seven tools remain. MCP initialization now advertises `resources.subscribe`; `resources/list` exposes one JSON metadata resource, `desktop://observation/changes`. After an explicitly consented continuous session starts, a capable client calls `resources/subscribe` with that URI. The server emits standard `notifications/resources/updated` messages without a preceding observe request. The message contains only the fixed URI. A client may read the resource for session state, current stream/revision, age of the last published observation and whether that observation may be outdated. No pixels, titles, coordinates, raw input, model prompts or action tokens are delivered by notifications or resource reads.

Updates are capped at one per second, coalesced to current state without a backlog. Byte changes are not semantic changes: clocks, cursor labels and animations can trigger notices. Subscriptions are explicit and bound to the existing backend/consent; they cannot start capture, renew a lease or survive a new consent. Unsubscribe, disconnect, Stop, revocation and expiry suppress later delivery. Manual Pause/authentication waiting expose no stream metadata. A pending notice rechecks subscription ownership after acquiring the output lock. A slow notification writer holds no server state/lifecycle locks; the reader can still cancel input and revoke subscriptions.

Client integration contract: consume notices in the client receive loop while the model is idle; replace older pending hints; schedule at most one authorized observation/reasoning turn; fetch and inspect a fresh guarded image; keep new hints coalesced while that turn runs. This repository supplies the server side, not a modification to the proprietary host event loop. A notification is not itself a model wake or permission to act.

OpenAI's documented MCP Events wake integration currently describes webhook delivery in Work cloud chats and dots, requiring MCP 2.0, callback verification, durable subscription state and authenticated HTTPS. It does not establish a local-stdio wake integration for this chat. No cloud webhook, public endpoint, credential or outbound desktop upload was added. See https://developers.openai.com/plugins/build/mcp-events . The local resource-subscription feature is separate from MCP Events and does not claim that protocol's capability.

## Read-only LM Studio adapter

`examples/notification_observer.py` supplies a separate bounded client for LM Studio's local `/api/v1/chat` endpoint. It does not modify the ChatGPT or LM Studio chat UI. After personal GNOME consent, it subscribes to change notices, obtains a fresh guarded screenshot and requests a description from an explicitly selected local vision model. Notifications received during inference collapse into one pending hint; model calls are sequential. The result is labeled as a description of a captured frame, with a newer-frame indicator. A result is discarded if the final resource check no longer permits observation, including a missing stream during manual pause or authentication, a replaced stream, or a regressed revision. Missing/malformed capture identity is rejected before model inference.

This adapter allows only status/start/observe/close MCP tools; model output is never interpreted as commands. It sends no model tool integrations and sets chat storage off for its API request. Images are not written to disk by the adapter, although the local model service may maintain its own diagnostics. Only explicit literal loopback HTTP endpoints with a port are accepted; environment proxies and redirects are disabled. Authentication, if configured, comes from `LM_API_TOKEN` without being logged. It sends no screenshots to a cloud service.

The default run is three summaries or 60 seconds of listening, within a 120-second native lease. Each in-flight local model request has a separate 60-second timeout; the listening bound does not abort an already-submitted model request. Stop still closes desktop authority independently, and an already-submitted frame cannot be recalled from the model. Protected/Pause/Stop behavior remains controlled by the desktop server. This is an observation prototype, not an autonomous action agent or permanent login monitor.

Use a matching installed runtime and a loaded vision model, for example:

```sh
python3 examples/notification_observer.py \
  --runtime /absolute/path/to/installed/desktop.py \
  --model your-local-vision-model --max-turns 1 --seconds 30
```

The local API can receive image input and return model messages as documented at https://lmstudio.ai/docs/developer/rest/chat . A successful API image test is separate from live notification-triggered desktop acceptance.

### Scoped adapter acceptance

A one-turn run on 2026-10-23 subscribed after fresh personal consent, received an automatic notice, obtained a fresh desktop frame and sent it to the locally loaded Qwen3.5 9B vision variant through loopback. It returned a description of the visible development/chat layout in 49.47 seconds. `newer_frame_available:true` correctly avoided presenting that result as a current live view. The run closed with `cleanup_verified:true`. Five isolated adapter tests pass. This proves the separate read-only adapter path, not automatic wake in the original ChatGPT/LM Studio UI, continuous comprehension, or acceptable real-time latency. The earlier non-private repository-image API smoke test also passed.

### Repeatable synthetic vision check (2026-10-23)

`demo/vision_accuracy_benchmark.py` creates two in-memory Calculator fixtures and sends them only to the selected loopback model. Pillow and DejaVu Sans are required. Run it with `--model` and optionally `--api`; it never captures the desktop or sends input. It exits nonzero on API failure or a failed literal recognition check.

The local Qwen model recognized Calculator, the displayed number, and automation state in both fixtures: 135/paused in 7.78 seconds and 42/active in 7.88 seconds. Six literal checks passed. These two simple fixtures do not measure general desktop accuracy, complex layout understanding, or action correctness. The earlier 49.47-second live result used a different image and workload, so these numbers do not establish a speed improvement. Seven isolated adapter tests now pass, including delayed-result suppression for unavailable states and manual pause without a stream. Core runtime files are unchanged.

### Expanded transition checks (2026-10-23)

The expanded run recognized all three requested facts (Calculator, number, automation state) in four generated screens: 135/paused, 42/active, 126/paused, and 15/active. Twelve literal checks passed; model request wall times were 4.53, 5.71, 8.55, and 8.89 seconds. See [machine-readable results](vision-benchmark-2026-10-23.json). Each API call is independent: this does not establish cross-frame memory or real-time tracking.

The affected adapter, change-notification, frame-observer and takeover-observation suites pass 43 tests. New adapter coverage includes unchanged-frame freshness, stream replacement with the same revision, fresh image delivery on a subsequent turn, timeout propagation without input/retry, and coalescing 1,000 notices before disconnect. The synthetic model tests and deterministic controller tests are complementary; no live desktop intervention was performed for this run. The adapter changes remain source-only.
