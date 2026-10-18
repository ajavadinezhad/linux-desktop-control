"""Injected calls only: never contact a real notification service."""
import importlib.util
import pathlib
import os
import sys
import types
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'plugins/linux-desktop-control/calibration_notice.py'
spec = importlib.util.spec_from_file_location('calibration_notice_test', SOURCE)
notice_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notice_module)


class CalibrationNoticeTests(unittest.TestCase):
    def test_gio_adapter_disables_service_activation_and_has_bounded_calls(self):
        calls = []
        class Connection:
            def is_closed(self): return False
            def set_exit_on_close(self, value): self.exit_on_close = value
            def close(self, *args): self.close_requested = args
            def call_sync(self, *args):
                calls.append(args)
                return types.SimpleNamespace(unpack=lambda: (41,) if args[3] == 'Notify' else ())
        connection = Connection()
        class Timer:
            def __init__(self, seconds, callback): self.seconds = seconds
            def start(self): pass
            def cancel(self): pass
        gio = types.SimpleNamespace(
            Cancellable=lambda: types.SimpleNamespace(cancel=lambda: None),
            DBusConnectionFlags=types.SimpleNamespace(AUTHENTICATION_CLIENT=1, MESSAGE_BUS_CONNECTION=2),
            DBusCallFlags=types.SimpleNamespace(NO_AUTO_START=8),
            DBusConnection=types.SimpleNamespace(new_for_address_sync=lambda *args: connection))
        glib = types.SimpleNamespace(Variant=lambda *args: args, VariantType=types.SimpleNamespace(new=lambda value: value))
        with patch.dict(sys.modules, {'gi.repository': types.SimpleNamespace(Gio=gio, GLib=glib)}), \
                patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/fixture/bus'}), \
                patch.object(notice_module.threading, 'Timer', Timer):
            notice = notice_module.CalibrationNotice()
            self.assertTrue(notice.show())
            self.assertTrue(notice.close())
        self.assertFalse(connection.exit_on_close)
        self.assertEqual(connection.close_requested, (None, None, None))
        for args, maximum in zip(calls, (500, 300)):
            self.assertEqual(args[:3], ('org.freedesktop.Notifications', '/org/freedesktop/Notifications', 'org.freedesktop.Notifications'))
            self.assertEqual(args[6], 8)  # NO_AUTO_START
            self.assertGreater(args[7], 0)
            self.assertLessEqual(args[7], maximum)

    def test_construction_is_passive_and_show_has_fixed_noninteractive_content(self):
        calls = []
        def call(*args):
            calls.append(args)
            return (17,)
        notice = notice_module.CalibrationNotice(call=call)
        self.assertEqual(calls, [])
        self.assertFalse(notice.status()['request_active'])
        self.assertTrue(notice.show())
        method, signature, arguments, timeout = calls[0]
        self.assertEqual((method, signature, timeout), ('Notify', '(susssasa{sv}i)', 500))
        self.assertEqual(arguments, ('Desktop control', 0, '', notice.SUMMARY, notice.BODY, [], {}, 30000))
        self.assertFalse(notice.status()['visible_verified'])

    def test_reset_replaces_same_request_and_close_is_bounded_and_idempotent(self):
        calls = []
        def call(method, signature, arguments, timeout):
            calls.append((method, signature, arguments, timeout))
            return (23,) if method == 'Notify' else ()
        notice = notice_module.CalibrationNotice(call=call)
        notice.show(); notice.show(reset=True)
        self.assertEqual(calls[1][2][1], 23)
        self.assertEqual(calls[1][2][4], notice.RESET_BODY)
        self.assertTrue(notice.close())
        self.assertEqual(calls[-1], ('CloseNotification', '(u)', (23,), 300))
        self.assertFalse(notice.status()['request_active'])
        self.assertTrue(notice.close())
        self.assertEqual(len(calls), 3)

    def test_unavailable_and_malformed_response_never_claim_visibility_or_leak_errors(self):
        for reply in ((0,), (True,), (2**32,), (), ('private secret',)):
            notice = notice_module.CalibrationNotice(call=lambda *args: reply)
            self.assertFalse(notice.show())
            self.assertEqual(notice.status()['warning'], notice.DELIVERY_WARNING)
            self.assertTrue(notice.status()['delivery_unknown'])
            self.assertFalse(notice.status()['request_active'])
            self.assertFalse(notice.close())
        def fail(*args): raise RuntimeError('private secret')
        notice = notice_module.CalibrationNotice(call=fail)
        self.assertFalse(notice.show())
        self.assertNotIn('private secret', str(notice.status()))

    def test_unknown_delivery_never_retries_or_claims_cleanup(self):
        calls = []
        def call(*args):
            calls.append(args)
            raise TimeoutError('delivered but acknowledgement missing')
        notice = notice_module.CalibrationNotice(call=call)
        self.assertFalse(notice.show())
        self.assertFalse(notice.show(reset=True))
        self.assertEqual(len(calls), 1)
        self.assertFalse(notice.close())
        self.assertTrue(notice.status()['delivery_unknown'])
        self.assertFalse(notice.status()['visible_verified'])

    def test_reset_reply_loss_does_not_erase_unknown_delivery_after_known_id_close(self):
        calls = []
        def call(method, *args):
            calls.append(method)
            if calls == ['Notify']: return (9,)
            if method == 'Notify': raise TimeoutError('reply missing')
            return ()
        notice = notice_module.CalibrationNotice(call=call)
        self.assertTrue(notice.show())
        self.assertFalse(notice.show(reset=True))
        self.assertFalse(notice.close())  # Known old ID closure cannot prove unknown replacement gone.
        self.assertTrue(notice.status()['delivery_unknown'])
        self.assertFalse(notice.status()['request_active'])

    def test_failed_close_keeps_request_for_cleanup_retry(self):
        fail_close = [True]
        def call(method, *args):
            if method == 'Notify': return (31,)
            if fail_close[0]: raise RuntimeError('private secret')
            return ()
        notice = notice_module.CalibrationNotice(call=call)
        notice.show()
        self.assertFalse(notice.close())
        self.assertTrue(notice.status()['request_active'])
        self.assertEqual(notice.status()['warning'], notice.CLOSE_WARNING)
        fail_close[0] = False
        self.assertTrue(notice.close())
        self.assertFalse(notice.status()['request_active'])

    def test_invalid_reset_argument_sends_nothing(self):
        calls = []
        notice = notice_module.CalibrationNotice(call=lambda *args: calls.append(args))
        with self.assertRaises(ValueError): notice.show(reset='Again')
        self.assertEqual(calls, [])
