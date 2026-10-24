# Supervised Qwen desktop actions

`examples/qwen_desktop_agent.py` is an explicit action-capable client, separate from the read-only notification observer. It reuses the existing stdio transport and loopback-only API validation. The read-only client's tool allowlist remains unchanged; the action subclass adds `desktop_action` and supervisor-only `desktop_resume`, never arbitrary tools, shell execution or automatic resume.

The local model receives a resized screenshot and the authorized LMMS task. It returns a schema-constrained plan through LM Studio's `/v1/chat/completions`. The supervisor must inspect the saved frame and proposed intent/action, then approve its exact digest through stdin. Rejection supplies feedback and obtains a new frame/plan; no refused or uncertain action is automatically replayed. Proposals older than 50 seconds refuse input. Backend observation-token, foreground, native, mapping, consent and lease checks still apply.

Model coordinates are screenshot pixels; the client validates and converts them to controller logical coordinates. Actions are bounded to eight steps; selected system shortcuts and command-like text are refused. Text paths are restricted to the explicitly assigned new project path. These checks are not an independent application-identity or sandbox guarantee: the supervisor must refuse interaction with unrelated apps, private content, terminal commands, existing-file overwrite and unsaved-work dialogs. The client does not prove musical quality or hear playback.

## Run

Requires system Python/Pillow, loaded local vision model, installed matching 0.8.42 controller/native helper, GNOME observer and fresh personal GNOME/Polkit approval. No recording is started.

```sh
python3 examples/qwen_desktop_agent.py \
  --runtime /home/aj/.codex/plugins/cache/local-linux-desktop/linux-desktop-control/0.8.42/desktop.py \
  --model desktop-observer-local \
  --project '/home/aj/Documents/Qwen Music Session 20261023.mmp' \
  --work /tmp/new-private-qwen-session \
  --max-turns 40
```

Both project and work location must be new; the project parent must already exist. Work directory is private (0700), with per-turn screenshots (0600); do not publish those images without review. The run prints `planning`, then `review` with the exact action and digest. Supervisor responses are one JSON line:

```json
{"approve":true,"digest":"the-exact-proposal-digest"}
```

Or reject with `{"approve":false,"feedback":"Describe the visible mistake"}`, or stop with `{"stop":true}`. Approval is task review, not permission to automate GNOME/Polkit dialogs. Ctrl+C also requests cleanup. A new session requires fresh user readiness and personal sharing consent. Inference has a 48-second request timeout; native sharing has its original 1200-second lease. Final `cleanup_verified` reports portal closure, held input and cleanup diagnostics.

## Evidence and remaining acceptance

Fifteen isolated action-client tests and fifteen read-only adapter tests pass. These cover coordinate mapping, authority binding, out-of-bounds/nonfinite points, shortcut/text/path restrictions, separated transitions, bounded batches, explicit approval and stale-plan rejection, read-only isolation, JSON-schema transport and incomplete response refusal.

The first live attempt started consented capture but the free-form model reply failed JSON parsing; no desktop input was sent and sharing closed with cleanup verified. The client was changed to LM Studio's documented JSON-schema completion endpoint. A subsequent generated-image format test produced a parseable plan in 24.73 seconds; no action was dispatched. That result is format evidence only, not correct targeting or live musical acceptance. A subsequent live supervised run dispatched a Qwen-proposed Super key transition (two input events, 147 ms input stage), and the returned screenshot showed the GNOME launcher. Invalid bundled actions and out-of-image coordinates were refused before dispatch. One guessed window click and one incorrect search-field focus proposal were rejected by the supervisor. During testing, physical pointer takeover was initially mistaken for a terminal observation failure by the new client; the client now waits for explicit current-pause handback instead of auto-resuming or replaying input. Live LMMS composition and saved-project acceptance remain pending. No music project was created at this checkpoint.

Reference: https://lmstudio.ai/docs/developer/openai-compat/structured-output

When the run emits `handoff-required`, it retains sharing without capture/input until the supervisor supplies `{"resume":true,"pause_id":"the-current-pause-id"}` after the user explicitly hands back control. It never resumes merely because the model asks. Stop and expired/closed sharing still terminate; leases are not renewed. The user's real activity may invalidate a plan even when the model produced valid JSON.
