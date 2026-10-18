# Private review status — 0.7.2

Core desktop tools and a passive text indicator are prepared. No custom interactive controls or keyboard shortcuts are included. The real system cursor is unchanged, and a direct cursor glow is not claimed. The prior pointer jitter symptom is not established as fixed. No live mouse test or sharing request was performed for this version. Refresh old connected tool catalogs. Source remains private and licensing is deferred.

Current 0.7.1 input requires loaded foreground-observer protocol 2 and a fresh window_observation_id. No live guard acceptance yet. See FOCUS_GUARD_0_7_1.md.

## 0.7.2 correction, awaiting live acceptance

132 isolated tests pass. The first consent-first 0.7.1 trial reached the GNOME overview and Firefox search, then its single launch click dispatched three input events before unavailable foreground context closed sharing. No Firefox screenshot or human Alt+Tab acceptance was reached. Result 05aec8bc14ee4c99acdfc85459cd2a98 had uncertain effects; closure was confirmed without cleanup warnings.

The new transition settling loop sends no input: only after an explicit single transition gesture it waits at most two seconds for an available context. Cancellation/revocation still aborts; ordinary batches remain immediately fenced.

The label was intentionally hidden in the app overview in helper revision 2, which matches the observed workflow; the old helper has no timestamped hide-reason history, so the exact moment of the reported fade cannot be reconstructed. Revision 3 permits the normal overview while retaining lock/greeter/foreign-modal hiding. A heartbeat failure now invalidates outstanding work and closes sharing. The new backend requires the fresh-pointer capability before requesting consent. Activating helper revision 3 needs a manual reload/login; the current helper has not been reloaded. No automatic reload, login, sharing or input occurs.

The deterministic first-move jump is corrected in source: each pointer action reads the authorized GNOME pointer snapshot and maps it to the selected monitor, then interpolates using elapsed monotonic time. Missing, invalid or off-monitor positions refuse input. Pointer coordinates are excluded from context signatures/epochs; no stale cross-call cache is used. Isolated tests cover the first move, secondary monitor offsets, absent mapping and no-input failure. Live smoothness remains unverified. Delayed historical focus epochs are ignored; newer epochs still cancel. There is no evidence yet of a scaling fault, conflicting physical/virtual motion, or lingering devices. Whether human pointer jitter persists with all portal sessions closed is unknown. Current status confirms closure; GNOME diagnostics reports no helper owner, active=false, visible=false, failed=false. Actual cursor glow remains unimplemented; the system cursor is unchanged. No universal-app or production-ready claim is made.

## Live 0.7.2 result

After the user logged back in, actual helper protocol 2 with fresh-pointer capability loaded. Personal portal consent preceded all GUI input. A one-second move dispatched 52 pointer events and returned an observed endpoint; the label was visible in both the application and normal GNOME overview. This establishes dispatch and endpoint/label visibility, not subjective smoothness or freedom from physical pointer jitter. No recording was made.

GUI Firefox search completed seven characters. Capture reconnected once without input replay. The single GUI app-launch click dispatched 15 events including interpolation, then foreground unavailability closed sharing with uncertain effects (result 1eb140282ad74143bdfa6e556203c0b9). No browser image or human Alt+Tab trial was reached. The exact failing capture/context phase was not instrumented, so a specific timing cause is not established. No automatic retry occurred. Explicit cleanup and read-only diagnostics confirmed the portal closed, input/capture disabled, no cleanup warning, and helper unowned/inactive/hidden. Further launch-transition correction and live acceptance remain required.
