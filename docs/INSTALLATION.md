# Installation

Use install.sh --check before installation. install.sh resolves the local MCP declaration, copies the read-only observer extension and installs the local marketplace plugin. The app must refresh its MCP catalog. The observer UUID is desktop-indicator@local.codex. GNOME may need a manual logout/login to discover it; no session restart is automated. The indicator has no shortcuts or reactive controls. Input/capture sessions require foreground-observer protocol 2; status and cleanup work without it.

Current 0.7.1 input requires loaded foreground-observer protocol 2 and a fresh window_observation_id. No live guard acceptance yet. See FOCUS_GUARD_0_7_1.md.
