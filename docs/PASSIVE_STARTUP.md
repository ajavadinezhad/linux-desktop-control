# Supervised startup without a manual challenge

> The version and installation claims below describe historical checkpoints. Consult [release status](RELEASE_STATUS.md) for the recorded published baseline and remaining checks.

Plugin 0.8.20 and helper 0.8.8 are installed. All 472 controller tests and 33 native fixtures pass. A fresh matching provider completed passive startup with no manual challenge; device coverage correctly remained unverified. The subsequent App Center launch closed unexpectedly, so completed native-task acceptance is still pending a separate transition repair.

Use `startup_verification="passive"` together with native physical observation and retained sharing when the user wants supervised operation without repeated keyboard/touchpad calibration. The existing challenge path remains the default and can be selected for diagnostics. Neither mode silently falls back to the other.

GNOME sharing and administrator approval remain personal system dialogs. Passive startup waits briefly for released input, quiet, empty queues, and a healthy session. It does not ask for Shift or a pointer gesture, and does not prove that all input streams are delivering events. Status therefore reports `readiness_kind="passive-unverified"`, `coverage_verified=false`, and both calibration and post-ARM verification false. Active observation and source coverage are separate facts.

The helper continues monitoring admitted sources. Pointer activity may pause capture/input while keeping sharing open. Automatic return additionally requires actual movement from the selected source in the current pause, followed by the existing quiet/resume checks and unchanged foreground, monitor and confirmed destination. A contact-only pause does not earn movement evidence; explicit resume remains available after released/quiet checks. No queued or interrupted action is replayed.

Stop, revoked consent, keys/buttons, unsupported activity, monitor/observer/heartbeat faults, and expiry retain terminal handling. The original session deadline is not renewed. No new device permissions, services, groups or approval policy are introduced.

The update also fixes a reproduced challenge-mode quiet-timer defect: empty synchronization frames and known inactive touchpad metadata no longer reset the quiet timer or earn motion credit. Active contacts and incomplete frames still block activation; real contact/motion/release events remain guarded. This is a reproduced defect, not a uniquely established explanation for every earlier live failure.
