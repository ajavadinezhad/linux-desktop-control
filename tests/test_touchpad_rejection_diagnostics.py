"""Optional coarse parser failure labels never create input authority or export raw text."""
import time,unittest
from unittest.mock import patch
import test_touchpad_protocol as fixture
m=fixture.m

class TouchpadRejectionTests(unittest.TestCase):
 def make(self,tail):
  c=fixture.TouchpadProtocolTests().controller();c.notified=True;c.ready=False
  replies=iter(['OBS_TPAD_1011',tail]);c._read=lambda _:next(replies)
  return c
 def test_fixed_labels_are_terminal_detail_only(self):
  for label in ('invalid-configuration','frame-invalid','tool-cardinality','contact-state','contact-limit','contact-count','coordinate-without-contact','unsupported-key','unsupported-event-type','unsupported-axis','invalid-value','duplicate-state','axis-range','slot-range','tracking-range','contact-without-slot','duplicate-contact','contact-release'):
   c=self.make('TP_REJECT_'+label);c._read_observation_report()
   self.assertEqual(c.touchpad_rejection,label);self.assertEqual(c.touchpad_rejection_report_kind,'received');self.assertFalse(c.ready);self.assertIsNone(c.intervention_epoch);self.assertIsNone(c.motion_epoch)
 def test_missing_optional_line_keeps_legacy_report_valid(self):
  c=self.make(None);c._read_observation_report()
  self.assertEqual(c.observation_report_kind,'received');self.assertIsNone(c.touchpad_rejection);self.assertEqual(c.touchpad_rejection_report_kind,'missing')
 def test_unknown_or_raw_detail_is_never_retained(self):
  for message in ('TP_REJECT_secret-raw-value','TP_REJECT_axis-range extra','TP_REJECT_12345','TP_REJECT_AXIS_RANGE',{},True):
   c=self.make(message);c._read_observation_report()
   self.assertEqual(c.observation_report_kind,'received');self.assertIsNone(c.touchpad_rejection);self.assertEqual(c.touchpad_rejection_report_kind,'malformed');self.assertNotIn('secret-raw-value',str(c.status()))
 def test_expired_optional_read_does_not_publish_late_label(self):
  c=self.make('TP_REJECT_axis-range')
  c._read=lambda _: 'TP_REJECT_axis-range'
  with patch.object(m.time,'monotonic',side_effect=[1,3]):c._read_touchpad_rejection(2)
  self.assertIsNone(c.touchpad_rejection);self.assertEqual(c.touchpad_rejection_report_kind,'timeout')
 def test_live_monitor_never_accepts_diagnostic_as_authority(self):
  c=self.make(None);c.ready=True;c.notified=False;sent=[];c._read=lambda _:sent.append(True)
  c._read_touchpad_rejection(time.monotonic()+1)
  self.assertEqual(sent,[]);self.assertIsNone(c.touchpad_rejection);self.assertEqual(c.touchpad_rejection_report_kind,'request-skipped')
  with self.assertRaises(m.NativeFailure):c._consume('TP_REJECT_axis-range')
 def test_split_terminal_wire_stops_before_reading_diagnostic(self):
  wire=b'OBS_TPAD_1011\nTP_REJECT_contact-count\n'
  class Connection:
   def __init__(self,chunks):self.chunks=chunks
   def recv(self,_):return self.chunks.pop(0)
  for split in range(1,len(wire)):
   events=[];c=fixture.TouchpadProtocolTests().controller();c.connection=Connection([wire[:split],wire[split:]])
   c.on_fault=lambda _:events.append('stop');c.close=lambda:events.append('close')
   with patch.object(m.select,'select',side_effect=lambda r,w,e,t:(r,w,[])):c._notify(error='Native observer fault')
   self.assertEqual(events,['stop','close']);self.assertEqual(c.touchpad_rejection,'contact-count');self.assertFalse(c.ready)
