"""Source identity and stale-provider refusal without portal or input operations."""
import importlib.util
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'plugins/linux-desktop-control'
spec = importlib.util.spec_from_file_location('build_desktop', RUNTIME/'desktop.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
build = desktop._runtime_build


class RuntimeBuildTests(unittest.TestCase):
    def test_path_independent_stamp_covers_each_official_source(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in build.RUNTIME_FILES:
                shutil.copyfile(RUNTIME/name, pathlib.Path(directory)/name)
            self.assertEqual(build.fingerprint(directory), desktop.SERVER_BUILD)
            for name in build.RUNTIME_FILES:
                path = pathlib.Path(directory)/name
                original = path.read_bytes()
                path.write_bytes(original+b'\n')
                self.assertNotEqual(build.fingerprint(directory), desktop.SERVER_BUILD, name)
                path.write_bytes(original)

    def test_status_stamp_frozen_with_read_only_disk_match(self):
        server = desktop.Server(mock.Mock())
        stamp = server.status()['server_build']
        self.assertRegex(stamp, r'^[0-9a-f]{64}$')
        with mock.patch.object(build, 'fingerprint', return_value='0'*64):
            status = server.status()
            self.assertEqual(status['server_build'], stamp)
            self.assertFalse(status['server_disk_match'])
        self.assertTrue(server.status()['server_disk_match'])

    def test_stale_start_refused_before_backend_portal_or_notice(self):
        factory = mock.Mock()
        server = desktop.Server(factory)
        with mock.patch.object(build, 'fingerprint', return_value='0'*64), \
             mock.patch.object(server, 'preflight_physical_guard') as preflight, \
             mock.patch.object(server, 'enable_physical_guard') as enable:
            with self.assertRaisesRegex(RuntimeError, 'restart the provider'):
                server.call('desktop_start', {'physical_takeover':True})
        factory.assert_not_called()
        preflight.assert_not_called()
        enable.assert_not_called()

    def test_stale_action_and_observe_close_existing_backend(self):
        for tool in ('desktop_action','desktop_observe'):
            with self.subTest(tool=tool):
                server=desktop.Server()
                backend=mock.Mock()
                server.backend=backend
                server.state='active'
                with mock.patch.object(build,'fingerprint',side_effect=OSError), \
                     mock.patch.object(server,'close_backend') as close:
                    with self.assertRaisesRegex(RuntimeError,'restart the provider'):
                        server.call(tool,{})
                backend.cancelled.set.assert_called()
                close.assert_called_once()
                self.assertEqual(server.state,'closing')

    def test_nonregular_source_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/build.RUNTIME_FILES[0]
            path.symlink_to(RUNTIME/build.RUNTIME_FILES[0])
            with self.assertRaisesRegex(RuntimeError,'Invalid desktop runtime source'):
                build.fingerprint(directory)

    def test_change_during_calibration_refuses_capture_start(self):
        from test_physical_guard import PhysicalGuardTests
        fixture=PhysicalGuardTests()
        server,bridge,events,_=fixture.make()
        original=server.enable_physical_guard
        changed=False
        def calibrate():
            nonlocal changed
            original()
            changed=True
        server.enable_physical_guard=calibrate
        def stamp(*args):
            return '0'*64 if changed else desktop.SERVER_BUILD
        # Fixture uses its own separately loaded backend module.
        import test_control
        try:
            with mock.patch.object(test_control.m._runtime_build,'fingerprint',side_effect=stamp):
                with self.assertRaisesRegex(RuntimeError,'restart the provider'):
                    server.call('desktop_start',{'physical_takeover':True})
            self.assertNotIn('capture-start',events)
            self.assertNotIn('capture',events)
            self.assertIn('portal-close',events)
            self.assertFalse(server.backend.active)
        finally:fixture.doCleanups()

    def test_lazy_import_stale_refuses_and_closes_before_loading(self):
        for method in ('native_activity_module','calibration_notice_module','window_guard_module','preflight_context','show_indicator'):
            with self.subTest(method=method):
                server=desktop.Server()
                with mock.patch.object(build,'fingerprint',return_value='0'*64), \
                     mock.patch.object(desktop.importlib.util,'spec_from_file_location') as load, \
                     mock.patch.object(server,'close_backend') as close:
                    with self.assertRaisesRegex(RuntimeError,'restart the provider'):
                        getattr(server,method)()
                load.assert_not_called()
                close.assert_called_once()

    def test_change_during_context_settle_refuses_capture(self):
        server=desktop.Server()
        backend=mock.Mock(requires_window_guard=True)
        server.backend=backend;server.state='active'
        changed=False
        def context(*args):
            nonlocal changed
            changed=True
            return {'available':True}
        server.read_window_context=context
        with mock.patch.object(build,'fingerprint',side_effect=lambda *a:'0'*64 if changed else desktop.SERVER_BUILD), \
             mock.patch.object(server,'close_backend') as close:
            with self.assertRaisesRegex(RuntimeError,'restart the provider'):
                server.capture_result(('active',))
        backend.capture.assert_not_called()
        close.assert_called_once()
