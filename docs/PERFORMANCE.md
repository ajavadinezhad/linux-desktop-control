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

## Scoped live touchpad drawing

Installed 0.8.18/helper 0.8.7 completed one uninterrupted Kleki bear redraw and GUI PNG save in approximately 4 minutes 25 seconds after startup. Both touchpad readiness gates passed. The user perceived faster operation, but no matched baseline establishes a percentage improvement. Example batches: five strokes 1785 ms input / 514 ms capture; six claw strokes 1565 ms input / approximately 600 ms capture; two scarf strokes 1201 ms input / approximately 500 ms capture. These counters exclude planning, tool transport and UI selection time. Their individual contributions were not measured. Cleanup confirmed portal closure, zero held input and no warning. No automatic replay or runtime modification occurred during the drawing.

## Adaptive inspection update — 0.8.19

Installed 0.8.19 adds an explicit stable-canvas drawing batch: one harmless observed single left focus click plus up to23 left drag strokes before the returned screenshot. Default sequences remain limited to8 steps. All points and step types validate before input; the10-second estimated and15-second actual budgets remain, so long paths may require smaller groups. No keys, text, scroll, wait, additional clicks, tool changes or right-button drags are admitted in the expanded path. Existing interruption, foreground, endpoint and release checks remain.

The installed skill also explains using existing bounded paragraph typing and ordinary predictable formatting groups, with inspection at meaningful UI transitions. The code cannot determine canvas semantics from coordinates; unchanged brush/colour/layout is an observed-use precondition. This update passes463 Python tests, independent review and seven-tool loading; all14 installed files match reviewed source. Sharing is closed with zero held input. A live speed gain from the larger batches has not been measured; the bear timing above predates this option. Helper0.8.7 is unchanged.

### Recorded larger-batch trial

A subsequent 0.8.19 touchpad session completed and saved a new bear through Kleki's GUI while a separate consented recorder ran. Actual drawing batches used9,10 and11 steps (8,9 and10 strokes plus focus), so three groups exceeded the previous8-step limit. Input durations were6929,3201 and4508ms with roughly550ms capture each. First drawing dispatch to finished image took200.6s; saving completed at approximately207s. Startup-to-close included about100s additional setup. The raw local recording is370.67s and passed full decode. These are scoped observations, not a controlled before/after benchmark. One mistaken brush-size shortcut was undone after inspection; the saved PNG was visually verified. A final cosmetic download-dismiss click hit the foreground capture fence after save; control closed with confirmed portal closure, zero held input and no warning. Recording then finalized successfully. The trial does not establish23-stroke live acceptance or a guaranteed percentage speedup.
