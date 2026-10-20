# Demo recorder

This directory contains the separate consent-based recorder used for the [bear demo](../docs/demo/README.md).

`record.py` defaults to 120 seconds and accepts up to 900. Recording does not grant desktop input authority or extend the control session. Use `--help` for recorder options.

Use disposable content and inspect full frames before sharing. Personal GNOME recording consent is required. Launch and operate apps through an observed, consented desktop session; do not prepare a scene through hidden app-control calls. See [the consent-first example](../examples/consent_first.py).
