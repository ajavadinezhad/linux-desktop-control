import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'configure-runtime.py'
spec = importlib.util.spec_from_file_location('configure_runtime_test', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RuntimeConfigurationTests(unittest.TestCase):
    def prepare(self, root, version='0.8.1'):
        plugin = root / 'plugins/linux-desktop-control'
        (plugin / '.codex-plugin').mkdir(parents=True)
        (plugin / '.codex-plugin/plugin.json').write_text(json.dumps({
            'name': 'linux-desktop-control', 'version': version}))
        (plugin / '.mcp.template.json').write_text(json.dumps({'mcpServers': {'linux_desktop': {
            'command': '/usr/bin/python3', 'args': ['desktop.py'], 'tool_timeout_sec': 150,
            'env_vars': ['DBUS_SESSION_BUS_ADDRESS']}}}))
        return plugin

    def test_generated_launch_uses_versioned_cache_and_honors_codex_home(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base / 'mutable-staging'
            plugin = self.prepare(root); home = base / 'custom codex home'
            with patch.dict(os.environ, {'CODEX_HOME': str(home)}):
                result = module.configure_runtime(root)
            config = json.loads((plugin / '.mcp.json').read_text())['mcpServers']['linux_desktop']
            expected = home / 'plugins/cache/local-linux-desktop/linux-desktop-control/0.8.1'
            self.assertEqual(config['args'], [str(expected / 'desktop.py')])
            self.assertEqual(config['cwd'], str(expected))
            self.assertNotIn(str(root), config['args'][0])
            self.assertEqual(result['manifest_version'], '0.8.1')
            self.assertFalse(expected.exists())  # No install/provider launch side effect.
            self.assertEqual(config['tool_timeout_sec'], 150)
            self.assertEqual(config['env_vars'], ['DBUS_SESSION_BUS_ADDRESS'])

    def test_changing_manifest_version_selects_a_distinct_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); plugin = self.prepare(base / 'staging', '0.8.0')
            old = module.configure_runtime(base / 'staging', base / 'home')
            (plugin / '.codex-plugin/plugin.json').write_text(json.dumps({
                'name': 'linux-desktop-control', 'version': '0.8.1'}))
            new = module.configure_runtime(base / 'staging', base / 'home')
            self.assertNotEqual(old['runtime_root'], new['runtime_root'])
            self.assertTrue(new['runtime_root'].endswith('/0.8.1'))

    def test_missing_override_uses_standard_home_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); self.prepare(base / 'staging')
            with patch.dict(os.environ, {}, clear=True), patch.object(module.Path, 'home', return_value=base / 'user'):
                result = module.configure_runtime(base / 'staging')
            self.assertEqual(result['runtime_root'], str(base / 'user/.codex/plugins/cache/local-linux-desktop/linux-desktop-control/0.8.1'))

    def test_invalid_manifest_version_cannot_escape_cache_directory(self):
        for version in ('../mutable', '', None, '0.8.1/../../other'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); plugin = self.prepare(root, version)
                with self.assertRaises(ValueError): module.configure_runtime(root, root / 'home')
                self.assertFalse((plugin / '.mcp.json').exists())
