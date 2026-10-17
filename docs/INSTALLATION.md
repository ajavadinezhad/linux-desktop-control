# Read-only readiness check

Run `./install.sh --check` or `/usr/bin/python3 check_environment.py --json`. Neither opens sharing nor changes settings. Missing required dependencies stop normal installation before any launch files or extension settings are changed. Optional AT-SPI support is reported separately. Passing these checks does not replace the runtime toolbar/portal check.

# Installation details

The installer generates an ignored `.mcp.json` from `.mcp.template.json` with this checkout's local paths, registers the local marketplace/plugin, and installs/enables the user-scoped GNOME extension. It backs up an existing copy of the same extension UUID and preserves other enabled extensions. It does not install system packages or restart GNOME.

Use a stable checkout. System requirements are listed in the main README. First activation may require a human logout/login for GNOME to discover the extension. Refresh the app's MCP connection after changes; a new skill file alone does not prove a current tool catalog or runtime.

## Optional standing tool authorization

Only do this after reviewing and trusting this local integration. The host supports per-tool policy in `~/.codex/config.toml`:

```toml
[plugins."linux-desktop-control@local-linux-desktop".mcp_servers.linux_desktop.tools.desktop_status]
approval_mode = "approve"

[plugins."linux-desktop-control@local-linux-desktop".mcp_servers.linux_desktop.tools.desktop_observe]
approval_mode = "approve"

[plugins."linux-desktop-control@local-linux-desktop".mcp_servers.linux_desktop.tools.desktop_start]
approval_mode = "approve"

[plugins."linux-desktop-control@local-linux-desktop".mcp_servers.linux_desktop.tools.desktop_action]
approval_mode = "approve"

[plugins."linux-desktop-control@local-linux-desktop".mcp_servers.linux_desktop.tools.desktop_pause]
approval_mode = "approve"

[plugins."linux-desktop-control@local-linux-desktop".mcp_servers.linux_desktop.tools.desktop_resume]
approval_mode = "approve"

[plugins."linux-desktop-control@local-linux-desktop".mcp_servers.linux_desktop.tools.desktop_stop]
approval_mode = "approve"
```

Merge with existing tables rather than duplicating them. This approves those tools for future calls, including desktop input; it is a substantive trust choice. It does not change global tool approvals, shell sandboxing, other plugins, or GNOME's fresh sharing consent. Quit/reopen the app if an existing connection keeps its previous policy. Remove these entries to revert.

Tool annotations remain honest: only status/observe are read-only; input is not mislabeled to suppress approval.

Sources: [plugin-scoped server policy](https://developers.openai.com/plugins/build/plugins), [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
