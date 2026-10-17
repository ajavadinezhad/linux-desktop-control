# Privacy and control boundaries

- One monitor is shared through a personally approved GNOME portal session. Use the primary monitor workflow. No unattended consent or persistent portal grant is requested.
- The normal backend returns screenshots in memory to the MCP client. The hosting app may retain them in chat history. Do not share sensitive desktop content casually.
- Pause and Stop close the backend's capture/control portal and release held input. Confirm `portal_closed_confirmed=true` and no cleanup warning before sensitive human work.
- A separate screen recorder, if you explicitly run one, has its own sharing session. Desktop Pause does not stop that recorder. The demo instructions restrict it to a clean disposable scene and require stopping it before leaving that scene.
- Accessibility inspection reads only identity, role, state, child count and geometry using bounded public calls. It excludes protected controls and does not read names, text, values, selection or clipboard. A guarded action never silently falls back to coordinate-only input.
- Generic pointer actions remain coordinate-based. Physical human takeover is not automatically detected. Guard checks and dispatch are not atomic.
- If closure is uncertain, use GNOME's independent sharing indicator to stop sharing and reconnect the backend. Do not automatically restart or resume.
- This public source bundle excludes local screenshots, raw test logs, personal paths, chat/session identifiers, private scratch files and credentials. Do not commit recording output until reviewed frame by frame.

Report defects through the repository's issue tracker using disposable reproduction data. Do not include secrets, private desktop images, or conversation exports.
