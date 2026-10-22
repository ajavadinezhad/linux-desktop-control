"""Synthetic launch failures only; never runs pkexec or opens input devices."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zlib

from test_native_activity import m


class LaunchDiagnosticsTests(unittest.TestCase):
    def failure(self, payload):
        with tempfile.TemporaryDirectory() as runtime:
            os.chmod(runtime, 0o700)
            def launch(args, **kwargs):
                return subprocess.Popen([sys.executable, '-c',
                    'import os,zlib; os.write(2,zlib.decompress(' + repr(zlib.compress(payload)) + ')); raise SystemExit(127)'], **kwargs)
            controller = m.Controller(lambda: True, lambda: None, lambda error: None,
                runtime_dir=runtime, validator=lambda: None, launcher=launch, startup_timeout=2)
            with self.assertRaises(m.NativeFailure): controller.start()
            self.assertTrue(controller.closed)
            self.assertEqual(controller.status()['helper_exit_code'], 127)
            self.assertFalse(controller.status()['monitor_armed'])
            return controller

    def test_fixed_category_excludes_private_details(self):
        controller = self.failure(b'Error executing command /private/secret: account alice\n')
        status = controller.status()
        self.assertEqual(status['helper_launch_diagnostic'], 'execution-failed')
        self.assertNotIn('alice', repr(status))
        self.assertNotIn('/private/secret', repr(status))

    def test_unknown_stderr_does_not_invent_authorization_cause(self):
        controller = self.failure(b'private unknown failure\n')
        self.assertIsNone(controller.status()['helper_launch_diagnostic'])
        self.assertEqual(controller.status()['helper_launch_diagnostic_kind'], 'unavailable')

    def test_pipe_flood_cannot_block_startup_cleanup(self):
        started = time.monotonic()
        controller = self.failure(b'x' * 200000 + b'No authentication agent found\n')
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(controller.status()['helper_launch_diagnostic'], 'authentication-agent-unavailable')
        self.assertFalse(controller.stderr_thread.is_alive())

    def test_diagnostic_not_published_while_session_open(self):
        controller = m.Controller(lambda: True, lambda: None, lambda error: None)
        controller.launch_diagnostic = 'authorization-denied'
        controller.launch_diagnostic_complete = True
        self.assertIsNone(controller.status()['helper_launch_diagnostic'])
        controller.close()
        self.assertEqual(controller.status()['helper_launch_diagnostic'], 'authorization-denied')


if __name__ == '__main__': unittest.main()
