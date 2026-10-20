# Performance pass — 0.8.17

The goal is less waiting between visible actions without removing consent, cancellation, foreground, mapping, endpoint or screenshot checks.

## Measured offline

A synthetic 40-point drag exercises the production pointer/action methods with a fake compositor. The path and injected waits are identical between versions.

| Counter | 0.8.16 | 0.8.17 |
| --- | ---: | ---: |
| Pointer reads | 201 | 123 |
| Mapping checks | 442 | 286 |
| Requested waits | 2.160 s | 1.436 s |

These are about 39% fewer pointer reads, 35% fewer mapping checks and 34% less requested waiting. They are not live wall-clock or end-to-end speed measurements. A separate 250-check, 151-mode fake-display fixture fell from about 0.327 s to 0.235 s on this host; all 750 owner/state/owner calls remain. Timing varies with environment.

Run the current fixture from the repository root:

```sh
/usr/bin/python3 tests/benchmark_pointer_pacing.py
```

## What changed

`position()` already obtains two fresh matching endpoint samples. Smooth movement and drag loops no longer repeat that full confirmation immediately afterward. A fresh confirmation still runs before button-down; every later drag point is checked, and mismatch/cancellation still releases input.

Pointer-only primitives no longer add an unconditional trailing 100 ms wait. Explicit waits now wait for the requested duration. Click/key/text pacing and the 350 ms post-settle capture fence remain unchanged.

Mapping checks still query owner/state/owner every time. They compare the complete typed state with the fully validated initial binding, including cached geometry and portal properties, rather than re-deriving all unchanged display modes. Any change or malformed value still latches refusal.

Coarse `input_duration_ms` and `capture_duration_ms` fields distinguish backend input from capture time. They exclude model reasoning and tool transport time and grant no control authority.

## Operator pacing

Use each action's returned image directly rather than making a second observation call. Short sequences can group already-observed strokes when the tool and canvas remain unchanged, within the existing 1–8-step and time limits. Start with a harmless observed focus click; do not leave an unwanted canvas mark. Inspect between dialogs, uncertain state and layout changes. Never replay interrupted work.

The frozen suite passed 450 Python tests. Endpoint mismatch, cancellation/release, typed-state changes and unchanged-query invariants have regression coverage. No live speedup, universal device support or new safety acceptance is claimed.

Installation verification: all 14 reviewed plugin files match the installed 0.8.17 cache; a fresh provider confirms the expected source build and seven tools. Two live startup attempts ended before capture/input, so these measurements remain offline only. See [release status](RELEASE_STATUS.md).
