# Live 0.7.5 acceptance

The human approved personal GNOME sharing before app input, after disclosure that optional actual cursor glow temporarily changes the desktop-wide theme. Five current tools were discovered on server 0.7.5. No app launch or focus occurred before consent; all app work used the observed GUI. No recorder was used.

## Native windows and saved file

Firefox reached the public Mozilla Support article “How to save a web page” in a new test tab. The explicit Ctrl+s transition opened a stable native Save dialog; the agent selected Downloads, typed a unique demo filename and saved. The browser download panel visually reported Completed. Its completed item opened a native Open With dialog. Selecting Firefox and Open returned a stable browser window rendering the local article from `$HOME/Downloads/codex-075-demo.html`. These app/dialog transitions did not close sharing.

The file was independently read after sharing closed: 91,534 bytes, article title present, SHA-256 `8482e491d607174513b1cdb04e576edaeb978f3bc994fe99ae875355e1e3d157`. Reopen result: `b42a81dd26d34ee6ae2e62e79e407103`. An earlier /tmp attempt failed and is not counted as success. Existing personal tabs were left untouched.

## Actual themed glow

Cyan glow was visible on the actual themed pointer in Firefox and native chooser scenes. No overlay, ring, duplicate pointer, pointer hiding or focus grab was used. The independent worker reported active during consented operation. Closure restored original effective theme Yaru, with restored=true, worker_running=false, restoration_pending=false and no glow error. GNOME settings independently confirmed Yaru after cleanup. Client-provided custom cursors can ignore themes; this is not universal cursor coverage.

## Physical takeover

The browser displayed “Switch now - press Alt+Tab.” The human personally confirmed “I pressed Alt+Tab.” During the ordinary guarded five-second wait, the tool returned `Desktop session closed`, result `76a59bd74c1e4160845b953db2aab837`, failed step 1, completed steps 0, input events attempted 0, characters 0. It published no image after target loss, reclaimed no focus and did not restart sharing or replay input.

This is live evidence of cancellation on a human app switch during a guarded wait. Held-key/button release and interruption during text/drag are covered by isolated tests, not claimed as live-tested here. Physical movement that keeps the same window/context remains outside the provenance guarantee; an unavoidable check-to-dispatch race remains.

## Final cleanup

Explicit cleanup plus read-only checks confirmed portal_closed_confirmed=true, capture/input disabled, no cleanup warning, label inactive/hidden/unowned, theme restored and watchdog stopped. The backend bridge then exited. No automatic restart followed takeover.

160 isolated tests and the real five-tool loader passed before this live check. This scoped acceptance does not establish support for every application, every dialog timing, every display configuration or every crash.
