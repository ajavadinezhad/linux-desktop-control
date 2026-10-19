"""Fixed postmortem protocol only; fake connections, no devices or privileges."""
import time
import unittest
from unittest.mock import patch
import test_native_activity as legacy
m=legacy.m


class ObservationDiagnosticTests(unittest.TestCase):
    def make(self):
        events=[]
        c=m.Controller(lambda:True,lambda:events.append('stop'),lambda error:events.append('fault'))
        c.ready=True;c.calibration_verified=True
        def close():events.append('close');c.stop.set();c.ready=False
        c.close=close
        return c,events

    def test_terminal_first_then_split_or_coalesced_detail_is_not_lost(self):
        wire=b'ACTIVITY_POINTER\nOBS_DIAG_1111\n'
        class Connection:
            def __init__(self,chunks):self.chunks=chunks
            def recv(self,size):return self.chunks.pop(0)
        for split in range(1,len(wire)):
            with self.subTest(split=split):
                c,events=self.make();c.connection=Connection([wire[:split],wire[split:]])
                with patch.object(m.select,'select',side_effect=lambda r,w,e,t:(r,w,[])):
                    c._consume(c._read(.1))
                self.assertEqual(events,['stop','close'])
                self.assertEqual(c.terminal_reason,'activity')
                self.assertEqual(c.observation_report_kind,'received')
                self.assertEqual(set(c.observation_evidence.values()),{True})
                self.assertFalse(c.status()['active'])

    def test_stop_callback_precedes_optional_read_and_diagnostic_publication(self):
        c,events=self.make()
        def read(timeout):
            self.assertEqual(events,['stop']);self.assertFalse(c.ready)
            self.assertIsNone(c.status()['observation_evidence'])
            self.assertLessEqual(timeout,.05);return 'OBS_DIAG_1010'
        c._read=read;c._consume('ACTIVITY_POINTER')
        self.assertEqual(c.observation_evidence,{
            'relative_calibration_seen':True,'primary_record_after_arm':False,
            'eligible_relative_after_arm':True,'yielded_token_sent':False})

    def test_missing_malformed_or_closed_detail_preserves_terminal_cause(self):
        for value,kind in ((None,'missing'),('OBS_DIAG_111','malformed'),
                ('OBS_DIAG_11111','malformed'),('OBS_DIAG_111x','malformed'),
                ('OBS_DIAG_1111 extra','malformed'),('CALIBRATED','malformed')):
            c,events=self.make();c._read=lambda timeout:value;c._consume('ACTIVITY_POINTER')
            self.assertEqual(c.observation_report_kind,kind)
            self.assertEqual(c.terminal_reason,'activity');self.assertIsNone(c.observation_evidence)
            self.assertEqual(events,['stop','close']);self.assertFalse(c.ready)
        c,events=self.make()
        def closed(timeout):raise m.NativeFailure('transport-closed','closed')
        c._read=closed;c._notify(error='fixed failure',reason='helper-fault')
        self.assertEqual(c.observation_report_kind,'unavailable')
        self.assertEqual(c.terminal_reason,'helper-fault');self.assertEqual(events,['fault','close'])

    def test_active_or_unrequested_detail_cannot_supply_authority(self):
        c,_=self.make();c._read=lambda timeout:self.fail('must not read while active')
        c._read_observation_report();self.assertEqual(c.observation_report_kind,'request-skipped')
        self.assertIsNone(c.observation_evidence);self.assertTrue(c.ready)
        c.ready=False;c._read_observation_report()
        self.assertEqual(c.observation_report_kind,'request-skipped')

    def test_late_optional_detail_is_discarded_under_fifty_ms_deadline(self):
        c,events=self.make();clock=[0.0]
        def read(timeout):clock[0]=.051;return 'OBS_DIAG_1111'
        c._read=read
        with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
            c._consume('ACTIVITY_POINTER')
        self.assertEqual(c.observation_report_kind,'timeout');self.assertIsNone(c.observation_evidence)
        self.assertEqual(events,['stop','close']);self.assertEqual(c.terminal_reason,'activity')

    def test_terminal_calibration_report_appends_optional_detail_without_arming(self):
        c,_=self.make();c.ready=False;c.calibration_verified=False;c.calibration_state='waiting'
        messages=iter(('CAL_DIAG_11011000','CAL_IDLE_NNM000','OBS_DIAG_1000'));sent=[]
        c._send=sent.append;c._read=lambda timeout:next(messages)
        c._request_calibration_report()
        self.assertEqual(sent,['REPORT']);self.assertEqual(c.calibration_report_kind,'received')
        self.assertEqual(c.calibration_idle_report_kind,'received')
        self.assertEqual(c.observation_report_kind,'received')
        self.assertFalse(c.ready);self.assertFalse(c.calibration_verified)

    def test_legacy_calibration_detail_remains_compatible(self):
        c,_=self.make();c.ready=False;c.calibration_verified=False;c.calibration_state='waiting'
        messages=iter(('CAL_DIAG_11011000','CAL_IDLE_NNM000',None))
        c._send=lambda token:None;c._read=lambda timeout:next(messages)
        c._request_calibration_report()
        self.assertEqual(c.calibration_report_kind,'received')
        self.assertEqual(c.calibration_idle_report_kind,'received')
        self.assertEqual(c.observation_report_kind,'missing');self.assertIsNone(c.observation_evidence)


if __name__=='__main__':unittest.main()
