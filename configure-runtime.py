#!/usr/bin/env python3
"""Prepare an ignored MCP declaration for the versioned installed cache.

This writes configuration only. The subsequent Codex plugin installation copies
the declaration and source into that cache before the provider starts. No code
is installed, executed, or copied by this helper.
"""
import json
import os
from pathlib import Path
import re
import sys
import tempfile


def configure_runtime(root, codex_home=None):
    root = Path(root).resolve()
    plugin = root / 'plugins/linux-desktop-control'
    manifest = json.loads((plugin / '.codex-plugin/plugin.json').read_text())
    version = manifest.get('version')
    if (manifest.get('name') != 'linux-desktop-control' or not isinstance(version, str)
            or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?', version)):
        raise ValueError('Plugin manifest must provide a valid fixed version')
    home = Path(codex_home or os.environ.get('CODEX_HOME') or (Path.home() / '.codex')).expanduser().resolve()
    runtime = home / 'plugins/cache/local-linux-desktop/linux-desktop-control' / version
    config = json.loads((plugin / '.mcp.template.json').read_text())
    server = config['mcpServers']['linux_desktop']
    server['args'] = [str(runtime / 'desktop.py')]
    server['cwd'] = str(runtime)
    target = plugin / '.mcp.json'
    descriptor, temporary = tempfile.mkstemp(prefix='.mcp-', suffix='.tmp', dir=plugin)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(config, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'configuration_path': str(target), 'runtime_root': str(runtime),
            'manifest_version': version}


if __name__ == '__main__':
    if len(sys.argv) > 2:
        raise SystemExit('Usage: configure-runtime.py [marketplace-root]')
    print(json.dumps(configure_runtime(sys.argv[1] if len(sys.argv) == 2 else Path(__file__).parent)))
