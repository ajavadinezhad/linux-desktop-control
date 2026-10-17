# Licensing review — decision pending

This is a dependency inventory and set of unresolved distribution questions, not a license or a legal opinion. The owner wants compensation when others make money using the project. No MIT, BSD, Apache, GPL, commercial-use grant, royalty percentage or copyright-holder identity has been assigned to this project during preparation. Keep this repository private pending that decision.

## What this tree contains

The tree contains the project's Python backend/helpers/tests, custom GNOME Shell extension, local plugin manifests, a disposable HTML fixture and demo scripts. It does not vendor GNOME Shell, PyGObject, GTK, AT-SPI, GStreamer, PipeWire, libxkbcommon, the Codex executable, or codec libraries. Those are separately installed system dependencies. The source scan found no existing third-party attribution/license headers to preserve; this is not proof of original authorship or complete rights clearance. The owner and any contributors must confirm rights before licensing.

## Dependency constraints

| Component | Integration | Relevant license information |
| --- | --- | --- |
| GNOME Shell | Extension imports Shell JS modules and runs inside Shell | GNOME states Shell is GPL-2.0-or-later and derived extensions must be distributed under compatible terms. This is the principal obstacle to putting a commercial-use royalty restriction over the complete extension package. |
| PyGObject / GTK / GLib / Gio / AT-SPI | System Python GI bindings and public D-Bus APIs | Primarily LGPL-family libraries; individual packages contain additional license notices. Runtime use is different from copying/bundling their code. Modified/bundled libraries need their own compliance review. |
| GStreamer | System pipeline elements; no bundled library | GStreamer is LGPL. Upstream documents use from proprietary applications subject to LGPL obligations. Additional plugins/codecs can have separate dependencies; inventory the actual distributed set if packaging binaries. |
| PipeWire / libxkbcommon | System public services/shared library | Separate system dependencies; not relicensed by this project. Preserve and review upstream notices if redistributing them. |
| Codex desktop executable | Existing separately installed host launches stdio server | Not included or relicensed. This is an independent integration with no implied OpenAI endorsement. |

The local package copyright files corroborate GPL-family Shell and LGPL-family PyGObject/GStreamer dependencies. They contain mixed file-level licenses and are not a single universal license for this bundle.

## Consequences for the owner's goal

- Standard MIT/BSD/Apache grants allow royalty-free commercial reuse; adding a payment condition would no longer be the unchanged standard license.
- GPL permits selling copies/support, but recipients retain GPL freedoms. It does not create a right to collect a royalty from everyone who later makes money using GPL-covered software.
- A possible model to evaluate is a GPL-compatible Shell extension plus a separately licensed backend/service/support offering. Whether the particular split is legally independent needs review; the current D-Bus process boundary alone does not settle that question.
- Noncommercial/research source access plus a separate paid commercial license is a possible direction only for code the owner can license that way. It cannot override a third party's GPL obligations or automatically cover a derived Shell extension.
- Dual licensing requires sufficient rights in all relevant code. It does not let this project sell exceptions to someone else's GPL rights.

Before distribution, decide precisely what activity triggers payment (commercial use, redistribution, paid product integration or another event), who owns the relevant rights, what components are covered, and how existing copyleft obligations are met. A tailored commercial license requires qualified legal review. No custom enforceable terms are invented here.

## Primary sources

- [GNOME extension licensing requirements](https://gjs.guide/extensions/review-guidelines/review-guidelines.html#licensing)
- [GNOME Shell COPYING](https://github.com/GNOME/gnome-shell/blob/main/COPYING)
- [PyGObject COPYING](https://github.com/GNOME/pygobject/blob/main/COPYING)
- [GStreamer application/plugin licensing](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html)
- [GNU license FAQ, fees and redistribution](https://www.gnu.org/licenses/gpl-faq.en.html#DoesTheGPLAllowRequireFee)
- [GNU explanation of selling license exceptions](https://www.gnu.org/philosophy/selling-exceptions.html)
