# Related work and defensible differences

Reviewed October 19, 2026. This is a targeted source comparison, not an exhaustive novelty search or a comparative security/performance benchmark. No competing software was installed or executed. Missing behavior in the examined paths is not proof it is absent from an entire project.

## Finding

AI-driven GNOME/Wayland screenshots, typing, clicking and dragging already exist. Consent, status indicators, stop switches and releasing pressed inputs on cancellation are also established features. Our implementation is substantial engineering work, but these capabilities alone do not establish a new invention or commercial demand.

The strongest candidate distinction is the combination of a single-use foreground observation for each action, strict closure on target/context loss, owner-scoped cancellation and recovery metadata, and an optional separately authorized physical-activity helper. The helper has not passed real same-window typing/drag acceptance. This is a design difference to evaluate, not a demonstrated safety advantage.

## Comparison

| Area | Our audited 0.8.4 candidate | Existing work examined |
| --- | --- | --- |
| Desktop automation | Screenshots, input and bounded actions through MCP | All three projects below already provide basic desktop automation. |
| Consent and control backend | GNOME portal consent for input/capture; observer extension; optional administrator-authorized activity helper | GNOME Desktop MCP uses compositor virtual devices and extension consent/enabled state. portal-use uses portal capture and libei with saved restore tokens. wayhand offers an isolated sandbox and a real-desktop uinput path. |
| Observation binding | Single-use action token tied to foreground identity, geometry and epoch; expiry does not replay the refused action | The examined GNOME and portal-use handlers accept actions without this token. wayhand tracks screenshot dimensions and an injection budget; that is a different contract. |
| Stop and cleanup | Input release, cancellation and session closure; unresolved releases remain tracked; stale owners cannot cancel replacements | wayhand already documents and implements pressed-input release on cancellation/errors and serialized action plans. A kill switch is also documented by GNOME Desktop MCP. These broad ideas are not new here. |
| Reconnection policy | No automatic sharing restart after interruption; a new authorized request and consent are required | portal-use's examined ensure_session path reinitializes a missing/dead session, and its portal layer stores restore tokens. This is a concrete policy difference, with a convenience tradeoff. |
| Physical takeover | Optional native observer, category calibration, fixed coarse signals, bounded heartbeat/lease; live acceptance incomplete | No equivalent calibrated physical-activity observer was identified in the examined action paths. wayhand explicitly asks users not to touch the real desktop during actions. This is not an exhaustive absence claim. |
| Text | GNOME Unicode composition by default, without replacing the clipboard; application support still needs verification | GNOME Desktop MCP already has Unicode-oriented injection. portal-use's examined text method uses a finite key map and rejects unsupported characters. wayhand documents a clipboard fallback outside its US-keyboard path. Unicode support itself is not new. |

## Sources and review scope

- **GNOME Desktop MCP**, source snapshot `dd18c43415b3fe6c55a1ddb0558910f7a72bf0b1`: [project README](https://github.com/sbuysse/gnome-desktop-mcp/blob/dd18c43415b3fe6c55a1ddb0558910f7a72bf0b1/README.md), [input implementation](https://github.com/sbuysse/gnome-desktop-mcp/blob/dd18c43415b3fe6c55a1ddb0558910f7a72bf0b1/extension/desktop-automation%40gnomemcp.github.io/input.js), [D-Bus dispatch](https://github.com/sbuysse/gnome-desktop-mcp/blob/dd18c43415b3fe6c55a1ddb0558910f7a72bf0b1/extension/desktop-automation%40gnomemcp.github.io/dbus.js), extension and consent modules. Reviewed handlers check enabled state and dispatch to compositor input; this is not a whole-project security assessment.
- **portal-use**, source snapshot `27fcfdf2288087db9b534aad7018ef4b9b023e3b`: [server](https://github.com/johnohhh1/portal_use/blob/27fcfdf2288087db9b534aad7018ef4b9b023e3b/server.py), [session](https://github.com/johnohhh1/portal_use/blob/27fcfdf2288087db9b534aad7018ef4b9b023e3b/portal/session.py), [input](https://github.com/johnohhh1/portal_use/blob/27fcfdf2288087db9b534aad7018ef4b9b023e3b/portal/input.py). In particular, server lines128–141 cover reconnection, lines345–361 cover drag dispatch, and input lines454–488 cover key-map text.
- **wayhand-mcp**, source snapshot `fd81f11c1a33fb0e905955bff7bf72337f4b817d`: [README](https://github.com/TimLai666/wayhand-mcp/blob/fd81f11c1a33fb0e905955bff7bf72337f4b817d/README.md), [safety budget](https://github.com/TimLai666/wayhand-mcp/blob/fd81f11c1a33fb0e905955bff7bf72337f4b817d/src/safety.rs), [server](https://github.com/TimLai666/wayhand-mcp/blob/fd81f11c1a33fb0e905955bff7bf72337f4b817d/src/server.rs), and entry point. These establish existing screenshot budgeting, cancellation/release behavior and sandbox support; its reported demonstration results were not independently reproduced.

Our source basis is the 0.8.4 audit in [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md), including 304 isolated Python tests and eight native fixtures. These counts are not comparative proof of reliability.

## What would strengthen the claim

Complete physical keyboard and held-button drag acceptance, then compare the same public scratch workflows across projects on comparable machines. Measure unintended continuation after takeover, foreground-change handling, held-input cleanup, false stops, setup effort and supported configurations. Record failures as well as passes. Until then, describe this as an independent GNOME desktop-control implementation with explicit observation-bound safety contracts and an experimental physical-activity guard.
