"""Physical keyboard opt-in reuses coarse intervention recovery, never pointer reclaim."""
import time,unittest
import test_click_controller as adapter
import test_click_recovery as recovery

class KeyboardAdapterTests(unittest.TestCase):
 def make(self):
  c,_=adapter.ClickControllerTests().controller();c.keyboard_policy='pause-recover';return c
 def test_exact_ack_and_rejection_of_older_helper(self):
  for reply,okay in [('KEYPAUSE1_OK',True),('CLICKPAUSE1_OK',False),('KEYPAUSE1_OK extra',False),(None,False)]:
   c=self.make();sent=[];c._send=sent.append;c._read=lambda _,reply=reply:reply
   if okay:c._negotiate_keyboard();self.assertTrue(c.keyboard_mode_acknowledged)
   else:
    with self.assertRaises(adapter.m.NativeFailure):c._negotiate_keyboard()
    self.assertFalse(c.keyboard_mode_acknowledged)
   self.assertEqual(sent,['KEYPAUSE1'])
 def test_no_click_ack_or_ended_lease_cannot_negotiate(self):
  for fault in ('click','lease'):
   c=self.make();sent=[];c._send=sent.append
   if fault=='click':c.click_mode_acknowledged=False
   else:c.helper_ready_at_monotonic=time.monotonic()-601
   with self.assertRaises(adapter.m.NativeFailure):c._negotiate_keyboard()
   self.assertEqual(sent,[])
 def test_constructor_rejects_implicit_click_widening(self):
  with self.assertRaises(ValueError):adapter.m.Controller(lambda:True,lambda:None,lambda _:None,retain_sharing=True,keyboard_policy='pause-recover')

class KeyboardRecoveryTests(recovery.ClickRecoveryTests):
 def test_keyboard_option_is_explicit(self):
  tool=next(t for t in recovery.retained.m.tools() if t['name']=='desktop_start')
  self.assertEqual(tool['inputSchema']['properties']['keyboard_policy']['enum'],['close','pause-recover'])
 def test_keyboard_recovery_never_reclaims_saved_point(self):
  s,b,d,n=self.make(True);s.native_keyboard_policy='pause-recover';self.paused(s,n)
  self.assertTrue(s.return_after_quiet(n,1));self.assertEqual(s.return_state,'context-refreshed')
  self.assertEqual(d.events,[]);self.assertEqual(n.resumed,[1]);self.assertEqual(d.captures,1)
 def test_closed_or_stale_context_record_cannot_mask_status(self):
  for fault in ('closed','replaced','cancelled'):
   s,b,d,n=self.make();record={'phase':'settling','backend':d,'native':n,'indicator':b,'consent':s.consent_id,'event':d.operation_cancelled}
   s.context_recovery=record
   self.assertEqual(s.startup_status_snapshot()['session_state'],'context-settling')
   if fault=='closed':s.invalidate();self.assertEqual(record['phase'],'cancelled')
   elif fault=='replaced':record['native']=object()
   else:d.cancelled.set()
   self.assertIsNone(s.startup_status_snapshot())

 def test_keyboard_alt_tab_race_refreshes_new_window_without_replay(self):
  s,b,d,n=self.make(True);s.native_keyboard_policy='pause-recover';n.intervention_epoch=None;n.yielded=False
  b.value.update(window_id='alt-tab-window',epoch=11)
  s.foreground_lost(b);self.assertTrue(d.operation_cancelled.is_set());self.assertFalse(d.cancelled.is_set())
  n.intervention_epoch=1;n.yielded=True
  self.assertTrue(s.matched_click_context_loss());deadline=time.monotonic()+1
  while s.state!='paused' and time.monotonic()<deadline:time.sleep(.005)
  self.assertTrue(s.return_after_quiet(n,1));self.assertEqual(d.events,[])
  self.assertEqual(s.window_record['context']['window_id'],'alt-tab-window')
 def test_keyboard_capability_cannot_be_claimed_by_older_adapter(self):
  s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';n.yielded=False
  with self.assertRaises(RuntimeError):s.require_native_ready()
 def test_physical_activity_reason_remains_specific_after_cleanup(self):
  s,b,d,n=self.make();s.native_activity_lost(n)
  self.assertEqual(s.closure_reason,'physical-activity');s.invalidate();self.assertEqual(s.closure_reason,'physical-activity')
