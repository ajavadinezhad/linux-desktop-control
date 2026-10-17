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
# This client requires resolved local paths in compatibility MCP declarations.
/usr/bin/python3 - "$root" <<'PYCONFIG'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1])/'plugins/linux-desktop-control'
p=root/'.mcp.json'
config=json.loads((root/'.mcp.template.json').read_text())
server=config['mcpServers']['linux_desktop']
server['args']=[str(root/'desktop.py')]
server['cwd']=str(root)
p.write_text(json.dumps(config,indent=2)+'\n')
PYCONFIG
/usr/bin/python3 "$root/install-toolbar.py"
"$codex_bin" plugin marketplace add "$root" --json
"$codex_bin" plugin add linux-desktop-control@local-linux-desktop --json
printf '%s\n' 'Installed Linux Desktop Control. The app must refresh its MCP tool catalog before use.'
