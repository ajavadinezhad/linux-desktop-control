"""Touchpad protocol admission; no device or desktop access."""
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_native_activity as legacy
import test_control
m=legacy.m

class TouchpadProtocolTests(unittest.TestCase):
    def controller(self, **kwargs):
        c=m.Controller(lambda:True,lambda:None,lambda error:None,
                       retain_sharing=True,pointer_source='touchpad',**kwargs)
        c.helper_ready_at_monotonic=time.monotonic()
        self.addCleanup(c.close)
        return c

    def test_requires_exact_touchpad_ack_without_mouse_fallback(self):
        for reply in (None,'MODEYIELD_OK','MODEYIELD2_OK','MODEYIELD3_OK extra','MODEYIELD3_ok'):
            c=self.controller();sent=[];c._send=sent.append;c._read=lambda timeout:reply
            with self.subTest(reply=reply),self.assertRaises(m.NativeFailure):c._negotiate_yield()
            self.assertEqual(sent,['MODEYIELD3'])
        c=self.controller();c._send=lambda token:None;c._read=lambda timeout:'MODEYIELD3_OK'
        c._negotiate_yield()
        self.assertEqual(c.status()['pointer_source'],'touchpad')

    def test_contact_mode_cannot_be_selected_without_retained_sharing(self):
        for source in (None,True,{},'tablet',''):
            with self.subTest(source=source),self.assertRaises(ValueError):
                m.Controller(lambda:True,lambda:None,lambda error:None,pointer_source=source)
        with self.assertRaises(ValueError):
            m.Controller(lambda:True,lambda:None,lambda error:None,pointer_source='touchpad')

    def test_source_selection_requires_native_retained_session(self):
        for args in ({'pointer_source':'touchpad'},
                     {'pointer_source':'touchpad','physical_takeover':True},
                     {'pointer_source':'tablet'}, {'pointer_source':True}):
            server=test_control.m.Server(test_control.Fake)
            with self.subTest(args=args),self.assertRaises(ValueError):server.call('desktop_start',args)

    def test_touchpad_postmortem_cannot_mislabel_relative_evidence(self):
        c=self.controller();c.notified=True;c._read=lambda timeout:'OBS_TPAD_1011'
        c._read_observation_report()
        self.assertEqual(c.observation_report_kind,'received')
        self.assertTrue(c.observation_evidence['touchpad_calibration_seen'])
        self.assertNotIn('relative_calibration_seen',c.observation_evidence)
        c._read=lambda timeout:'OBS_DIAG_1111';c._read_observation_report()
        self.assertEqual(c.observation_report_kind,'malformed')

    def test_late_or_revoked_touchpad_ack_never_authorizes(self):
        for reason in ('late','revoked','closed'):
            c=self.controller();sent=[];clock=[10.0];c.helper_ready_at_monotonic=10
            c._send=sent.append
            def read(timeout):
                if reason=='late':clock[0]=11.0
                elif reason=='revoked':c.active=lambda:False
                else:c.closed=True
                return 'MODEYIELD3_OK'
            c._read=read
            with self.subTest(reason=reason),patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),self.assertRaises(m.NativeFailure):
                c._negotiate_yield()
            self.assertEqual(sent,['MODEYIELD3'])
            self.assertFalse(c.ready)

    def test_server_forwards_touchpad_selection_and_matching_notice(self):
        server=test_control.m.Server(test_control.Fake)
        server.ensure_backend();server.backend.start();server.state='opening'
        server.interruption_policy='retain-sharing';server.native_pointer_source='touchpad'
        calls=[];notice=SimpleNamespace()
        controller=SimpleNamespace(start=lambda:None,status=lambda:{'active':True,'post_arm_verified':True,'post_arm_state':'verified'})
        def factory(**kwargs):calls.append(kwargs);return controller
        server.native_activity_module=lambda:SimpleNamespace(Controller=factory)
        server.calibration_notice_module=lambda:SimpleNamespace(CalibrationNotice=lambda:notice)
        server.enable_physical_guard()
        self.assertEqual(calls[0]['pointer_source'],'touchpad')
        self.assertIn('lift',notice.POST_ARM_BODY)
        self.assertIn('touchpad',notice.BODY)

    def test_active_source_cannot_change(self):
        server=test_control.m.Server(test_control.Fake);server.call('desktop_start',{})
        server.preflight_physical_guard=lambda:None
        with self.assertRaisesRegex(ValueError,'cannot be changed'):
            server.call('desktop_start',{'physical_takeover':True,'interruption_policy':'retain-sharing','pointer_source':'touchpad'})
        self.assertEqual(server.native_pointer_source,'mouse')
