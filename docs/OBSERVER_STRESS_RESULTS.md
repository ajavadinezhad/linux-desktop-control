# Bounded offline observer stress

## Scope and result

The four tests in `tests/test_observer_stress.py` passed once in 0.188 seconds, then passed 30 consecutive repetitions (120 test executions) in 5.413 seconds on the development machine. These elapsed times describe this synthetic run, not desktop reaction or model inference latency.

Each repetition exercises:

| Scenario | Work per repetition | Assertions |
| --- | --- | --- |
| Slow consumer after a frame burst | 20,000 distinct synthetic frames | One retained frame, final payload returned, 19,999 overwrites, pixels erased on close |
| Capture lifecycle replacement | 50 fresh observer instances | Unique stream identities, no retained pixels at startup, old identities rejected, old worker stopped and pixels cleared |
| Close under updates | 20 runs with a waiting consumer and 200 queued source frames | Close wakes the blocked reader with a stopped result, joins both workers, and clears pixels |
| Subscription-like ownership turnover | 1,000 owner replacements and 20 coalesced revisions each | In-flight obsolete owner rejected by final callback, latest revision retained, absent ownership resets state, no sends after close |

Across the repeated run this covers 600,000 frame publications, 1,500 capture lifecycle replacements, 600 close races, and 30,000 simulated ownership replacements. The source fixture intentionally queues producer frames; the observer itself retains only its latest frame. The notifier fixture models the transport's final ownership recheck; it does not establish real portal or subscription correctness independently of integration tests.

## Reproduce

From the maintained release source:

```sh
python3 -m unittest discover -s tests -p test_observer_stress.py -v
```

No desktop, user media, local model, network, installation, or publication is involved. No core modules were changed for this stress suite. No disposable probes or generated result files are retained.

## Limits

This is bounded offline concurrency coverage. It is not a 20-minute live session, memory-leak measurement, real compositor/portal interruption test, model accuracy test, or proof that this chat receives unsolicited model updates. Input permission is synthetic; actual consent, authentication, foreground mapping, and helper recovery still require their integration and live acceptance checks. Close latency has a generous one-second waiter bound to detect deadlock rather than claim a precise performance target.
