# Strict relative-motion coverage — 0.8.9 candidate / helper 0.8.3

## Reproduced gap

The installed 0.8.8 third mouse-return trial reached calibration, ARM, a fresh primary-monitor image and the confirmed assistant endpoint. No native yield epoch was observed before the original native lease expired. The human subsequently confirmed physical mouse movement during the trial. Thus automatic mouse return failed live; it is not a passed feature. Sharing closed with zero held virtual input and no cleanup warning. The adjacent `release/LIVE_0_8_8_MOUSE_RETURN_ATTEMPT3.json` initially recorded the human answer as pending; the later confirmation supplies that timing evidence.

The old calibration accepted broad pointer-category evidence: a mouse button, aggregate held state, an absolute record or other relative axes could establish its pointer credit. The retained-sharing yield path, however, accepts only nonzero `EV_REL` `REL_X`/`REL_Y` from a verified pointer source. Synthetic fixtures reproduced activation with broad pointer credit but without any event from the path needed to yield. A calibration success therefore did not establish relative-motion delivery.

## Candidate correction

Retained-sharing controllers negotiate `MODEYIELD2` and require the exact `MODEYIELD2_OK` acknowledgement before calibration. They never fall back to the old handshake. Strict calibration additionally requires a fresh streamed nonzero REL_X/REL_Y event from a verified pointer-category descriptor, after the current calibration cue. Keyboard challenge, physical release, the existing quiet boundary, source validation, calibration deadline and ARM checks remain required. Resynchronization clears relative-motion credit along with all other calibration credit.

Aggregate held buttons, button stream records, EV_ABS, wheel/other relative axes, zero motion, stale timestamps and unverified categories cannot supply strict relative-motion credit. Broad legacy diagnostic pointer-category bits may still be true while this stricter requirement remains missing; those bits and READY/acknowledgement alone never authorize input. Legacy helper/controller behavior is historical compatibility, not evidence that strict mode is active.

This closes a false-activation gap. It does not repair event delivery, identify the user's particular mouse, prove all devices are covered, diagnose an exclusive grab, change device access or establish human provenance. No new privileges, input groups, ACLs or grab probes are introduced. If the challenged relative stream remains unavailable, startup must refuse before capture and input. No synthetic challenge, timeout extension, weaker calibration or automatic retry is permitted.

## Readiness

Verification passes all 378 Python tests, 14 native fixtures, the real seven-tool 0.8.9 loader/schema check and skill validation. The helper package was built and inspected: two root-owned payloads, no maintainer scripts, service, setuid or permission changes. Private candidate plugin 0.8.9 and helper package 0.8.3 are installed, and reviewed runtime files match. A fresh actual provider verified 0.8.9, the reviewed build, disk consistency and seven tools while sharing was closed with zero held input. Actual strict relative-stream delivery remains unverified; the prior live automatic-return failure is unresolved. Live automatic return remains blocked and unverified. The earlier 0.8.7 typing-stop and drag-release evidence remains valid only for its historical stop/cleanup scope. The retained-sharing rules, sticky manual pause, one-attempt return, no action replay, original 120-second lease and terminal privacy/session/device guards are unchanged. See [retained-sharing behavior](RETAINED_SHARING.md).


Legacy MODEYIELD compatibility does not gain the strict guarantee. Before requesting sharing, require a freshly connected server_version=0.8.9 with the reviewed matching source build; refuse older cached providers. MODEYIELD2/MODEYIELD2_OK then occurs after personal sharing/admin authorization and before calibration/capture/input. Do not use an old provider to exercise retained sharing against the new helper.
