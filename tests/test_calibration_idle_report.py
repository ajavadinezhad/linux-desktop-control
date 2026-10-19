"""Fixed terminal diagnostic parsing; no helper launch, socket or input devices."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

source=Path(__file__).resolve().parents[1]/'plugins/linux-desktop-control/native_activity.py'
spec=importlib.util.spec_from_file_location('idle_report_controller',source)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class CalibrationIdleReportTests(unittest.TestCase):
    def controller(self,messages):
        c=m.Controller(lambda:True,lambda:None,lambda error:None)
        self.addCleanup(c.close)
        c.calibration_state='waiting'
        replies=iter(messages);sent=[];timeouts=[]
        c._send=sent.append
        def read(timeout):
            timeouts.append(timeout)
            return next(replies,None)
        c._read=read
        return c,sent,timeouts

    def test_extended_report_exports_only_local_coarse_enums(self):
        c,sent,timeouts=self.controller(['CAL_DIAG_11111010','CAL_IDLE_CRR100'])
        c._request_calibration_report()
        self.assertEqual(c.calibration_report_kind,'received')
        self.assertEqual(c.calibration_idle_report_kind,'received')
        self.assertEqual(c.calibration_idle_evidence,{
            'last_activity_kind':'clock-metadata','last_activity_age':'recent',
            'quiet_reason':'recent-activity','input_queue_pending':True,
            'topology_pending':False,'owner_pending':False})
        self.assertLessEqual(timeouts[-1],.05)
        self.assertEqual(sent,['REPORT'])
        self.assertFalse(c.ready);self.assertFalse(c.calibration_verified)

    def test_legacy_report_is_preserved_when_detail_is_absent(self):
        c,sent,_=self.controller(['CAL_DIAG_11111010'])
        c._request_calibration_report()
        self.assertEqual(c.calibration_report_kind,'received')
        self.assertEqual(c.calibration_idle_report_kind,'missing')
        self.assertIsNone(c.calibration_idle_evidence)
        self.assertEqual(sent,['REPORT'])

    def test_untrusted_detail_never_overwrites_base_or_leaks_content(self):
        for message in ('CAL_IDLE_private-secret','CAL_IDLE_XRR000',
                        'CAL_IDLE_CXR000','CAL_IDLE_CRX000','CAL_IDLE_CRR002',
                        'CAL_IDLE_CRR000extra',False,b'CAL_IDLE_CRR000'):
            with self.subTest(message=message):
                c,_,_=self.controller(['CAL_DIAG_11111010',message])
                c._request_calibration_report()
                self.assertEqual(c.calibration_report_kind,'received')
                self.assertEqual(c.calibration_idle_report_kind,'malformed')
                self.assertIsNone(c.calibration_idle_evidence)
                self.assertNotIn('private-secret',str(c.status()))

    def test_optional_transport_failure_keeps_received_legacy_report(self):
        c,_,_=self.controller(['CAL_DIAG_11111010'])
        original=c._read;calls=[0]
        def read(timeout):
            calls[0]+=1
            if calls[0]>1:raise m.NativeFailure('transport-closed','private detail')
            return original(timeout)
        c._read=read;c._request_calibration_report()
        self.assertEqual(c.calibration_report_kind,'received')
        self.assertEqual(c.calibration_idle_report_kind,'unavailable')
        self.assertIsNone(c.calibration_idle_evidence)

    def test_detail_never_extends_terminal_deadline_or_authorizes_arm(self):
        c,sent,_=self.controller(['CAL_DIAG_11111010','CAL_IDLE_CRR000'])
        with patch.object(m.time,'monotonic',side_effect=[0,0,2]):
            c._request_calibration_report()
        self.assertEqual(c.calibration_report_kind,'received')
        self.assertEqual(c.calibration_idle_report_kind,'timeout')
        self.assertEqual(sent,['REPORT']);self.assertFalse(c.ready)


if __name__=='__main__':unittest.main()
