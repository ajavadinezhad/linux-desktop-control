# Waiting for trusted GNOME system authentication

> The version and installation claims below describe historical checkpoints. Consult [release status](RELEASE_STATUS.md) for the recorded published baseline and remaining checks.

Installed baseline: plugin 0.8.24 and helper 0.8.10. Candidate plugin 0.8.25 changes recognition to observer capability revision3 and is not installed or live verified. The loaded GNOME observer must advertise revision3; updating files alone does not establish that it is running.

The operator enables `allow_permission_wait=true` at startup with native physical observation and retained sharing. A later observed Install click uses `wait_for_permission=true`, `focus_transition=true`, and `recording_stopped=true`. The last field is an operator attestation: all recorders owned by that operator must actually be stopped and finalized before the click. The backend cannot establish the state of unrelated external recorders.

Before that one click, the backend suspends its capture pipeline, releases virtual input, and obtains the helper's permission-wait acknowledgement. The human alone enters the password and approves or cancels the dialog. Automated input and capture remain disabled during the recognized prompt. No click or interrupted action is replayed.

The observer recognizes the exact GNOME 51 Polkit agent dialog as the sole trusted modal, bound to the expected foreground origin and current attempt. It uses the fixed category `system-authentication` without reading or allowlisting the requested action name. This authorizes waiting only: it does not authorize the requested action or establish approval, installation, removal, or task success. Non-Polkit modals, lock screens, mismatched actors, and unavailable or unknown Shell internals remain terminal. It exports fixed states and a temporary attempt identifier, never the authentication message, cookie, usernames, or password fields. Its GNOME 51 implementation uses version-specific private Shell state. The window binding is contextual; it does not prove which process caused the request.

After the observed attempt ends, the controller requires the same foreground origin, released input, complete queues, quiet, valid monitor mapping, and a healthy native session before inspecting a fresh app image. A bounded path also handles an installation that produces no prompt, reporting that fact without claiming authorization. A dialog disappearing does not prove approval or installation success: inspect the app result.

Stop, revoked sharing, lock, unknown system UI, observer/helper failure, monitor change, and the original session deadline retain terminal handling. Permission waiting is capped at two minutes and cannot extend that deadline. No administrator approval is automated, and no persistent input permissions or services are added.

Installation must update both the helper and GNOME observer. Copying the observer files does not prove GNOME loaded them; the controller requires its advertised capability before requesting this mode. A manual logout/login may be needed, and the tool never restarts the user's session.

A missing trusted agent dialog is reported as `polkit-dialog-unavailable`, separately from a mismatched modal actor. A null MetaWindow focus is accepted only with the cached valid origin for the exact trusted dialog. A remembered closing dialog remains pending until it is hidden or closed. The first fixed failure reason and stage survive cleanup without exposing dialog contents.
