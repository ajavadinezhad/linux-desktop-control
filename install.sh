#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
codex_bin=${CODEX_BIN:-/usr/lib/chatgpt/resources/codex}
if [ "$#" -gt 1 ]; then printf '%s\n' 'Usage: ./install.sh [--check]' >&2; exit 2; fi
case "${1:-}" in
  --check) exec /usr/bin/python3 "$root/check_environment.py" ;;
  "") ;;
  *) printf '%s\n' 'Usage: ./install.sh [--check]' >&2; exit 2 ;;
esac
# Fail before writing launch paths, copying extensions or changing user settings.
/usr/bin/python3 "$root/check_environment.py"
# The CLI copies this declaration into the versioned cache before starting the
# provider. Never launch an installed version from the mutable staging tree.
/usr/bin/python3 "$root/configure-runtime.py" "$root"
/usr/bin/python3 "$root/install-indicator.py"
"$codex_bin" plugin marketplace add "$root" --json
"$codex_bin" plugin add linux-desktop-control@local-linux-desktop --json
printf '%s\n' 'Installed Linux Desktop Control. The app must refresh its MCP tool catalog before use.'
