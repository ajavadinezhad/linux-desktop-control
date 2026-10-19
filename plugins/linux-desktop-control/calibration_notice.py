"""Passive, fixed-text calibration notice. Importing performs no GI/UI work.

The caller must establish portal consent and the matching readiness stage
before show(), then close before activation or cleanup. A Notify acknowledgement never proves visibility.
Injected call(method, signature, arguments, timeout_ms) must return unpacked
D-Bus response tuples. No application is launched or activated by this module.
"""
import os
import threading
import time


class CalibrationNotice:
    SUMMARY = 'Desktop control calibration'
    BODY = 'Press and release Shift, move the mouse, then keep your hands still.'
    RESET_BODY = 'Again: press and release Shift, move the mouse, then keep your hands still.'
    POST_ARM_SUMMARY = 'Desktop control mouse readiness'
    POST_ARM_BODY = 'Move the mouse briefly, then keep your hands still. Do not press any keys or mouse buttons.'
    PHASES = ('calibration', 'post-arm-pointer')
    UNAVAILABLE = 'Calibration notice unavailable; follow the chat instructions.'
    CLOSE_WARNING = 'Calibration notice closure could not be confirmed.'
    DELIVERY_WARNING = 'Calibration notice delivery is uncertain; closure cannot be confirmed.'

    def __init__(self, call=None):
        self._injected_call = call
        self._connection = None
        self._id = None
        self._acknowledged = False
        self._warning = None
        self._delivery_unknown = False
        self._phase = None

    def _release_connection(self):
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                # Asynchronous transport closure adds no blocking time to the
                # bounded notification call. It does not establish UI closure.
                connection.close(None, None, None)
            except Exception:
                pass

    def _call(self, method, signature, arguments, timeout_ms):
        if self._injected_call is not None:
            return self._injected_call(method, signature, arguments, timeout_ms)
        # Explicit local bus only. Do not use bus_get(), whose missing-address
        # fallback can autolaunch a session bus. NO_AUTO_START also prevents
        # activation of a missing notification service.
        address = os.environ.get('DBUS_SESSION_BUS_ADDRESS', '')
        if not address.startswith('unix:') or ';' in address:
            raise RuntimeError('Local session bus unavailable')
        from gi.repository import Gio, GLib
        deadline = time.monotonic() + timeout_ms / 1000
        cancelled = Gio.Cancellable()
        timer = threading.Timer(timeout_ms / 1000, cancelled.cancel)
        timer.daemon = True
        timer.start()
        try:
            if self._connection is None or self._connection.is_closed():
                self._connection = Gio.DBusConnection.new_for_address_sync(
                    address,
                    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                    Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                    None, cancelled)
                self._connection.set_exit_on_close(False)
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                raise RuntimeError('Notification request deadline exceeded')
            result = self._connection.call_sync(
                'org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                'org.freedesktop.Notifications', method,
                GLib.Variant(signature, arguments),
                GLib.VariantType.new('(u)' if method == 'Notify' else '()'),
                Gio.DBusCallFlags.NO_AUTO_START, remaining, cancelled)
            return result.unpack()
        finally:
            timer.cancel()

    def show(self, reset=False, phase='calibration'):
        if type(reset) is not bool:
            raise ValueError('reset must be boolean')
        if type(phase) is not str or phase not in self.PHASES:
            raise ValueError('Unknown readiness notice phase')
        if phase=='post-arm-pointer' and reset:
            raise ValueError('Mouse readiness phase does not support reset')
        if self._delivery_unknown:
            self._warning = self.DELIVERY_WARNING
            return False  # Never create another unidentified notice.
        if phase != self._phase:self._acknowledged = False
        self._phase = phase
        summary=self.POST_ARM_SUMMARY if phase=='post-arm-pointer' else self.SUMMARY
        body=self.POST_ARM_BODY if phase=='post-arm-pointer' else (self.RESET_BODY if reset else self.BODY)
        try:
            reply = self._call('Notify', '(susssasa{sv}i)', (
                'Desktop control', self._id or 0, '', summary,
                body, [], {}, 30000), 500)
            if (not isinstance(reply, (tuple, list)) or len(reply) != 1 or
                    type(reply[0]) is not int or not 0 < reply[0] <= 0xffffffff):
                raise RuntimeError('Notification response invalid')
            self._id = reply[0]
            self._acknowledged = True
            self._warning = None
            return True
        except Exception:
            # A timeout/malformed reply can follow successful delivery. Without
            # a trustworthy ID, neither invisibility nor closure is established.
            self._delivery_unknown = True
            self._warning = self.DELIVERY_WARNING
            return False

    def close(self):
        if self._id is None:
            self._release_connection()
            if self._delivery_unknown:
                self._warning = self.DELIVERY_WARNING
            return not self._delivery_unknown
        try:
            reply = self._call('CloseNotification', '(u)', (self._id,), 300)
            if reply not in (None, ()):
                raise RuntimeError('Notification closure response invalid')
            self._id = None
            self._warning = self.DELIVERY_WARNING if self._delivery_unknown else None
            return not self._delivery_unknown
        except Exception:
            self._warning = self.CLOSE_WARNING
            return False
        finally:
            self._release_connection()

    def status(self):
        return {
            'phase': self._phase,
            'request_acknowledged': self._acknowledged,
            'request_active': self._id is not None,
            'visible_verified': False,
            'delivery_unknown': self._delivery_unknown,
            'warning': self._warning,
        }
