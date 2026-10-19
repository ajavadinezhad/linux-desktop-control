"""Post-ARM readiness unit tests: no devices, portal, or input."""
import threading
import time
import unittest
import test_native_activity as legacy

m = legacy.m


class PostArmGateTests(unittest.TestCase):
    def make(self):
        events = []
        c = m.Controller(lambda: True, lambda: events.append('activity'),
                         lambda error: events.append('fault'), retain_sharing=True,
                         on_yield=lambda *args: events.append('yield'),
                         on_quiet=lambda *args: events.append('quiet'))
        c.helper_ready_at_monotonic = time.monotonic()
        c.calibration_verified = True
        c.post_arm_gate = True
        c.post_arm_state = 'waiting-motion'
        c.post_arm_deadline_monotonic = time.monotonic() + .15
        c._send = lambda token: None
        self.addCleanup(c.close)
        return c, events

    def test_no_post_arm_motion_never_becomes_ready(self):
        c, events = self.make()
        with self.assertRaises(m.NativeFailure):
            c._wait_post_arm()
        self.assertFalse(c.ready)
        self.assertFalse(c.post_arm_verified)
        self.assertEqual(c.post_arm_state, 'failed')
        self.assertEqual(events, [])

    def test_fresh_motion_quiet_ack_only_then_publish(self):
        c, events = self.make()
        c._consume('YIELDED_1')
        self.assertFalse(c.ready)
        c._consume('QUIET_1')
        c._send = lambda token: c._consume('ARMED_1')
        c._wait_post_arm()
        self.assertTrue(c.ready)
        self.assertTrue(c.post_arm_verified)
        self.assertEqual(c.post_arm_state, 'verified')
        self.assertEqual(events, [])

    def test_stale_quiet_cannot_supply_readiness(self):
        c, _ = self.make()
        c._consume('YIELDED_1')
        c._consume('QUIET_1')
        c._consume('YIELDED_2')
        with self.assertRaises(m.NativeFailure):
            c._consume('QUIET_1')
        self.assertFalse(c.ready)
        self.assertIsNone(c.quiet_epoch)

    def test_new_motion_during_resume_never_publishes(self):
        c, _ = self.make()
        c._consume('YIELDED_1')
        c._consume('QUIET_1')
        c._send = lambda token: c._consume('YIELDED_2') if token.startswith('RESUME') else None
        with self.assertRaises(m.PointerYielded):
            c._wait_post_arm()
        self.assertFalse(c.ready)
        self.assertFalse(c.post_arm_verified)

    def test_closed_or_revoked_gate_never_publishes(self):
        for close in (False, True):
            c, _ = self.make()
            if close:
                c.close()
            else:
                c.active = lambda: False
            with self.assertRaises(m.NativeFailure):
                c._wait_post_arm()
            self.assertFalse(c.ready)

    def test_late_ack_refused_even_with_motion_and_quiet(self):
        c, _ = self.make()
        c._consume('YIELDED_1')
        c._consume('QUIET_1')
        c.resume_pending = (1, time.monotonic() - 1)
        with self.assertRaises(m.NativeFailure):
            c._consume('ARMED_1')
        self.assertFalse(c.ready)

    def test_new_known_notice_gets_own_close_budget_without_hiding_old_id(self):
        c, _ = self.make()
        class Notice:
            def show(self, **kwargs):
                self.open = True
            def status(self):
                return {'request_acknowledged': True, 'request_active': self.open,
                        'delivery_unknown': False}
            def close(self):
                self.open = False
                return True
        c.notice = Notice()
        c.notice_close_attempts = 2
        c._show_notice(phase='post-arm-pointer')
        self.assertEqual(c.notice_close_attempts, 0)
        c._close_notice()
        self.assertFalse(c.notice_open)
        c.notice_phase = 'calibration'
        c.notice_open = True
        c.notice_active = True
        c.notice_close_attempts = 2
        with self.assertRaises(m.NativeFailure):
            c._show_notice(phase='post-arm-pointer')
        self.assertEqual(c.notice_close_attempts, 2)

    def test_reentrant_close_during_final_authorization_cannot_resurrect_ready(self):
        c, _ = self.make()
        c._consume('YIELDED_1')
        c._consume('QUIET_1')
        def send(token):
            if token.startswith('RESUME'):
                c._consume('ARMED_1')
                # Resume acknowledgement is complete; the next authorization
                # check must observe reentrant revocation even if it returns true.
                def revoked():
                    c.close()
                    return True
                c.active = revoked
        c._send = send
        with self.assertRaises(m.NativeFailure):
            c._wait_post_arm()
        self.assertTrue(c.closed)
        self.assertTrue(c.stop.is_set())
        self.assertFalse(c.ready)
        self.assertFalse(c.post_arm_verified)


if __name__ == '__main__':
    unittest.main()
