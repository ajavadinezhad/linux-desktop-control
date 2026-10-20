"""Physical keyboard opt-in reuses coarse intervention recovery, never pointer reclaim."""
import time,unittest,threading
from unittest.mock import patch
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

 def test_switcher_private_context_waits_without_capture_until_ordinary_window(self):
  for reason in ('no-foreground-window','system-ui'):
   s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n)
   b.value={'available':False,'epoch':12,'reason':reason}
   self.assertTrue(s.check_pause_health(s.pause_id,d,b));self.assertEqual(d.captures,0);self.assertEqual(d.events,[])
 def test_locked_or_auth_context_never_uses_switcher_wait(self):
  for reason in ('locked','greeter','auth-prompt','unavailable','device-source-activity'):
   s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n)
   b.value={'available':False,'epoch':12,'reason':reason}
   self.assertFalse(s.check_pause_health(s.pause_id,d,b));self.assertEqual(d.captures,0)

 def test_real_watch_retries_quiet_once_after_popup_empty_workspace_and_window(self):
  s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n)
  ordinary=dict(b.value);b.value={'available':False,'epoch':12,'reason':'system-ui'}
  with patch.object(recovery.retained.m,'CONTEXT_RECOVERY_QUIET',.03):
   start=time.monotonic();self.assertFalse(s.return_after_quiet(n,1));self.assertLess(time.monotonic()-start,.1)
   self.assertEqual(d.captures,0)
   time.sleep(.24);self.assertEqual(s.state,'paused')
   b.value={'available':False,'epoch':13,'reason':'no-foreground-window'}
   time.sleep(.24);self.assertEqual(s.state,'paused');self.assertEqual(d.captures,0)
   b.value=ordinary;b.value.update(window_id='workspace-two',epoch=14)
   deadline=time.monotonic()+1.5
   while s.state!='active' and time.monotonic()<deadline:time.sleep(.01)
   self.assertEqual(s.state,'active');self.assertEqual(n.resumed,[1]);self.assertEqual(d.captures,1);self.assertEqual(d.events,[])
 def test_overview_is_inert_and_deadline_not_renewed(self):
  s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n)
  b.value.update(kind='overview',window_id='shell-overview')
  original=s.keyboard_wait_deadline;self.assertFalse(s.return_after_quiet(n,1));self.assertTrue(s.check_pause_health(s.pause_id,d,b))
  self.assertEqual(s.keyboard_wait_deadline,original);self.assertEqual(d.captures,0)
  s.keyboard_wait_deadline=time.monotonic()-1
  self.assertFalse(s.check_pause_health(s.pause_id,d,b));self.assertEqual(s.closure_reason,'intervention-wait-expired')
 def test_private_wait_rejects_malformed_metadata(self):
  for payload in ({'available':None,'epoch':1,'reason':'system-ui'},{'available':False,'epoch':True,'reason':'system-ui'},{'available':False,'epoch':-1,'reason':'system-ui'},{'available':False,'epoch':1,'reason':'system-ui','extra':True}):
   s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n);b.value=payload
   self.assertFalse(s.check_pause_health(s.pause_id,d,b));self.assertEqual(d.captures,0)
 def test_new_input_and_manual_pause_prevent_private_wait_auto_resume(self):
  for manual in (False,True):
   s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n);ordinary=dict(b.value)
   b.value={'available':False,'epoch':12,'reason':'system-ui'};self.assertFalse(s.return_after_quiet(n,1))
   if manual:s.begin_pause();s.finish_pause()
   else:n.quiet=False
   b.value=ordinary
   with patch.object(recovery.retained.m,'CONTEXT_RECOVERY_QUIET',0):
    self.assertTrue(s.check_pause_health(s.pause_id,d,b));self.assertTrue(s.check_pause_health(s.pause_id,d,b));time.sleep(.03)
   self.assertEqual(s.state,'paused');self.assertEqual(n.resumed,[]);self.assertEqual(d.captures,0)
 def test_context_signal_before_keyboard_token_hands_off_inert_popup(self):
  s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';n.intervention_epoch=None;n.yielded=False
  b.value={'available':False,'epoch':12,'reason':'system-ui'}
  s.foreground_lost(b);time.sleep(.02);n.intervention_epoch=1;n.yielded=True
  self.assertTrue(s.matched_click_context_loss());deadline=time.monotonic()+.5
  while s.state!='paused' and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(s.state,'paused');self.assertFalse(d.cancelled.is_set());self.assertEqual(d.captures,0)
 def test_duplicate_quiet_and_explicit_resume_cannot_skip_stability(self):
  s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n);ordinary=dict(b.value)
  b.value={'available':False,'epoch':12,'reason':'system-ui'};self.assertFalse(s.return_after_quiet(n,1))
  with self.assertRaises(recovery.retained.m.RetainedPause):s.resume_sharing({'pause_id':s.pause_id})
  b.value=ordinary;self.assertTrue(s.check_pause_health(s.pause_id,d,b))
  self.assertFalse(s.return_after_quiet(n,1))
  with self.assertRaises(recovery.retained.m.RetainedPause):s.resume_sharing({'pause_id':s.pause_id})
  self.assertEqual(d.captures,0);self.assertEqual(n.resumed,[])
 def test_private_wait_does_not_hold_stop_locks_and_cannot_revive_closed_session(self):
  s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n)
  b.value={'available':False,'epoch':12,'reason':'system-ui'};self.assertFalse(s.return_after_quiet(n,1))
  self.assertTrue(s.execution_lock.acquire(timeout=.05));s.execution_lock.release()
  self.assertTrue(s.lifecycle_lock.acquire(timeout=.05));s.lifecycle_lock.release()
  s.invalidate(reason='requested-close');s.close_backend();self.assertFalse(s.return_after_quiet(n,1));self.assertEqual(d.captures,0)
 def test_stop_finishes_while_watcher_context_query_is_stalled(self):
  s,b,d,n=self.make();s.native_keyboard_policy='pause-recover';self.paused(s,n);s.pause_watch_stop.set()
  original=b.context;entered=threading.Event();release=threading.Event();result=[]
  def blocked():entered.set();release.wait(1);return original()
  b.context=blocked;pause_id=s.pause_id
  worker=threading.Thread(target=lambda:result.append(s.check_pause_health(pause_id,d,b)));worker.start();self.assertTrue(entered.wait(.5))
  start=time.monotonic();s.invalidate(reason='requested-close');s.close_backend();self.assertLess(time.monotonic()-start,.1)
  release.set();worker.join(.5);self.assertEqual(result,[False]);self.assertEqual(d.captures,0);self.assertEqual(n.resumed,[]);self.assertIsNone(s.keyboard_context_wait)
