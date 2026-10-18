# Privacy

Screen capture and input require personal GNOME consent. Screenshots can show personal data; only capture within the authorized task. Optional accessibility reads identity/state/geometry, not field values or clipboard. The passive label reads pointer coordinates only for rendering and never sends them to the backend. Context is in memory. Session close, error, disconnect and idle expiry release virtual input and the portal. Use GNOME native sharing controls if cleanup is unconfirmed.

The foreground guard reads a stable window sequence, frame geometry, context kind and monotonic epoch through the helper. Window titles, app text, clipboard and physical key/mouse event contents are not read. These context observations fence input but do not establish physical-input provenance.
