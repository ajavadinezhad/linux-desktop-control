"""Coarse persistent protocol tests; no sockets, devices, or administrator access."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_native_activity as legacy
m=legacy.m


class PersistentYieldTests(unittest.TestCase):
    def make(self, retain=True):
        events=[]
        controller=m.Controller(lambda:True,lambda:events.append('terminal'),lambda error:events.append('fault'),
            retain_sharing=retain,on_yield=lambda owner,epoch:events.append(('yield',epoch)),
            on_quiet=lambda owner,epoch:events.append(('quiet',epoch)))
        controller.helper_ready_at_monotonic=time.monotonic()
        controller.calibration_verified=True;controller.ready=True
        controller._send=lambda token:None
        self.addCleanup(controller.close)
        return controller,events

    def test_yield_quiet_do_not_grant_input_or_end_observation(self):
        c,events=self.make();c._consume('YIELDED_1');c._consume('QUIET_1')
        self.assertEqual(events,[('yield',1),('quiet',1)])
        self.assertFalse(c.status()['active']);self.assertTrue(c.status()['observer_alive'])
        self.assertTrue(c.is_current_yield(1,quiet=True));self.assertFalse(c.stop.is_set())

    def test_resume_has_one_mailbox_and_monitor_acknowledgement(self):
        c,events=self.make();c._consume('YIELDED_1');c._consume('QUIET_1');sent=[]
        def send(token):
            sent.append(token)
            worker=threading.Thread(target=lambda:c._consume('ARMED_1'));worker.start()
        c._send=send
        self.assertEqual(c.resume_from_pause(1),1)
        self.assertEqual(sent,['RESUME_1']);self.assertTrue(c.ready);self.assertFalse(c.yielded)
        self.assertIsNone(c.resume_pending)

    def test_movement_replaces_quiet_and_supersedes_pending_resume(self):
        c,events=self.make();c._consume('YIELDED_1');c._consume('QUIET_1')
        def send(token):c._consume('YIELDED_2')
        c._send=send
        with self.assertRaises(m.PointerYielded):c.resume_from_pause(1)
        self.assertTrue(c.is_current_yield(2));self.assertIsNone(c.quiet_epoch)
        self.assertFalse(c.stop.is_set());self.assertNotIn('fault',events)

    def test_stale_duplicate_malformed_or_unnegotiated_tokens_refused(self):
        for token in ('YIELDED_0','YIELDED_01','YIELDED_65','YIELDED_2','QUIET_1','ARMED_1','YIELDED_１'):
            c,_=self.make()
            with self.subTest(token=token),self.assertRaises(m.NativeFailure):c._consume(token)
        c,_=self.make(False)
        with self.assertRaises(m.NativeFailure):c._consume('YIELDED_1')
        c,_=self.make();c._consume('YIELDED_1')
        with self.assertRaises(m.NativeFailure):c._consume('YIELDED_1')

    def test_late_ack_never_publishes_ready(self):
        c,_=self.make();c._consume('YIELDED_1');c._consume('QUIET_1')
        c.resume_pending=(1,time.monotonic()-1)
        with self.assertRaises(m.NativeFailure):c._consume('ARMED_1')
        self.assertFalse(c.ready)

    def test_legacy_activity_remains_terminal_in_retained_mode(self):
        c,events=self.make();c._consume('YIELDED_1');c._consume('ACTIVITY_KEY')
        self.assertTrue(c.stop.is_set());self.assertIn('terminal',events)

    def test_mode_negotiation_requires_exact_new_helper_ack(self):
        for response in (None,'FAULT','READY','ALIVE','MODEYIELD_OK','MODEYIELD_OK extra','MODEYIELD2_OK extra','MODEYIELD2_ok'):
            c,_=self.make();sent=[];c._send=sent.append;c._read=lambda timeout:response
            with self.subTest(response=response),self.assertRaises(m.NativeFailure):c._negotiate_yield()
            self.assertEqual(sent,['MODEYIELD2'])
        c,_=self.make();c._read=lambda timeout:'MODEYIELD2_OK';c._negotiate_yield()

    def test_revocation_after_ack_cannot_publish_ready(self):
        c,_=self.make();c._consume('YIELDED_1');c._consume('QUIET_1')
        c.resume_pending=(1,time.monotonic()+1);c.active=lambda:False
        with self.assertRaises(m.NativeFailure):c._consume('ARMED_1')
        self.assertFalse(c.ready)

    def test_strict_mode_missing_coverage_cannot_arm_from_category_diagnostics(self):
        c,_=self.make();c.ready=False;c.calibration_verified=False;c.calibration_state='waiting'
        c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0)
        clock=[0.0];sent=[];report=[False]
        def send(token):
            sent.append(token)
            if token=='REPORT':report[0]=True
        def read(timeout):
            clock[0]+=.25
            # Both legacy keyboard/pointer categories are true. They cannot
            # substitute for the absent strict CALIBRATED result.
            return 'CAL_DIAG_11011000' if report[0] else 'ALIVE'
        c._send=send;c._read=read
        with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(m.NativeFailure,'challenge timed out'):c._wait_calibrated()
        self.assertIn('REPORT',sent);self.assertNotIn('ARM',sent)
        self.assertTrue(c.calibration_evidence['keyboard_seen'])
        self.assertTrue(c.calibration_evidence['pointer_seen'])
        self.assertFalse(c.calibration_verified);self.assertFalse(c.ready)


if __name__=='__main__':unittest.main()
