# LM Studio connection on GNOME

The controller exposes seven MCP tools over stdio. Supply the current desktop-control skill and current-modes reference to the agent as well as connecting the server. Tool availability does not establish compatible model behavior or successful desktop startup.

## A restricted desktop client

On the tested machine, LM Studio's `bionic` process and its directly spawned MCP process had `NoNewPrivs: 1`. The helper is started with `pkexec`, which cannot acquire its required privileges under that restriction. A no-op reproduction returned 127 with the fixed message `pkexec must be setuid root`. That exit code alone is not a universal diagnosis.

An explicitly chosen user-service connection runs the MCP provider through the existing systemd user manager. This leaves the client restriction unchanged and preserves the helper's separate Polkit administrator authorization and personal GNOME portal approval. It requires a working user manager in the same logged-in desktop account; do not disable client sandbox settings or change helper ownership/permissions.

Use `/usr/bin/systemd-run` as the MCP command, with these individual arguments:

```text
--user
--quiet
--pipe
--wait
--collect
--service-type=exec
/usr/bin/python3
/absolute/path/to/the/installed/desktop.py
```

Use a real absolute installed path for the final argument. Do not put a shell command into an argument or run this as a system/root service. The controller cleans up on stdio disconnect; transient services are collected after exit.

The tested connection loaded seven tools from a restricted parent, kept sharing inactive, ran the provider without the inherited restriction, and exited cleanly on stdin closure. Live helper startup remains a separate acceptance step. Native helper 0.8.18 additionally handles supported metadata during the initial passive-release boundary; do not treat a launch fix as proof of complete input-device coverage.

## Startup results

`session_state: closed` with `sharing_active: false` only establishes that no session is open. It does not justify restarting services or changing system sharing settings. Begin a new, authorized `desktop_start` attempt and let the user approve the portal and administrator dialogs manually.

If it fails, preserve the actual status, helper exit code and fixed launch-diagnostic category. Do not automatically retry or invent a cause. Raw authentication text, account names and private paths must not be reported.
