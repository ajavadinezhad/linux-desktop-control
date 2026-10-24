# Privacy

GNOME asks you to approve one screen plus keyboard and pointer sharing. Screenshots may contain personal information, so use only the screen and content intended for the task. GNOME's sharing control remains available independently of the assistant.

The foreground extension reports window identity, geometry, context state and pointer positions. It does not read document text, field values or the clipboard. Screenshots themselves can contain visible text. Context and cursor-return points are held in memory for the session.

## Optional physical-input monitoring

The optional native helper needs separate administrator approval. It receives raw Linux input event codes and values internally; claiming it never reads raw input would be incorrect. It reduces them to fixed readiness, activity, quiet and fault signals. Raw events, key meanings, coordinates, device identities and raw file descriptors are not exported to the assistant or desktop backend, logged or persisted.

It opens covered devices read-only, drops privileges and applies confinement. It does not grab input or change device ACLs. Device activity is not proof of human identity. See [the native privacy boundary](../native-activity/docs/PRIVACY.md).

Manual Pause stops backend capture and input while keeping the existing portal consent alive. With explicit observation-during-takeover enabled, ordinary physical takeover pauses automated input while allowing guarded read-only observation; no action tokens are issued. Protected UI and authentication waiting still suspend observation. Closing, privacy Stop, revocation, lock, faults and expiry end control. The default native budget is 120 seconds, optionally selected up to 1200 at startup; it cannot be renewed during the session.

Recordings are separate artifacts and require their own consent. Review them before sharing. The published bear edit hides unrelated tab titles; original recordings remain local.
