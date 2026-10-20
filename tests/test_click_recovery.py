"""Opt-in click recovery with fake native epochs and compositor only."""
import threading,time,unittest
from types import SimpleNamespace
import test_retained_pause as retained

class Native:
 def __init__(self):self.epoch=1;self.intervention_epoch=1;self.quiet=True;self.yielded=True;self.resumed=[]
 def status(self):return {'active':not self.yielded,'observer_alive':True,'yielded':self.yielded,'yield_epoch':self.epoch,'intervention_epoch':self.intervention_epoch}
 def is_current_yield(self,epoch,quiet=False):return self.yielded and epoch==self.epoch and (not quiet or self.quiet)
 def is_current_intervention(self,epoch,quiet=False):return self.intervention_epoch==epoch and self.is_current_yield(epoch,quiet)
 def resume_from_pause(self,epoch,timeout=1,click_return=False):
  if not click_return or not self.is_current_intervention(epoch,True):raise RuntimeError('wrong recovery authority')
  self.resumed.append(epoch);self.yielded=False;self.intervention_epoch=None
 def close(self):pass

class ClickRecoveryTests(unittest.TestCase):
 def test_click_policy_is_exposed_as_explicit_tool_option(self):
  start=next(tool for tool in retained.m.tools() if tool['name']=='desktop_start')
  option=start['inputSchema']['properties']['click_policy']
  self.assertEqual(option['enum'],['close','pause-return']);self.assertEqual(option['default'],'close')
 def make(self,point=False):
  f=retained.RetainedPauseTests();s,b,d=f.make();self.addCleanup(f.doCleanups)
  s.native_click_policy='pause-return';s.physical_takeover=True;s.consent_id='consent';s.native_startup_verification='passive'
  n=Native();s.own_observer('native_activity',n)
  if point:d.confirmed_pointer_record={'consent_id':s.consent_id,'session':d.session,'mapping':d.mapping_guard,'context':s.window_guard_module().WindowGuard.signature(b.context()),'point':(25,25)}
  return s,b,d,n
 def paused(self,s,n):
  s.physical_intervention(n,1);deadline=time.monotonic()+1
  while s.state!='paused' and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(s.state,'paused')
 def test_click_same_context_returns_once_and_never_replays_click(self):
  s,b,d,n=self.make(True);self.paused(s,n)
  self.assertTrue(s.return_after_quiet(n,1));self.assertEqual(s.return_state,'returned');self.assertEqual(n.resumed,[1])
  self.assertEqual((d.resumes,d.captures),(1,1));self.assertFalse(any(e[1]=='NotifyPointerButton' for e in d.events));self.assertAlmostEqual(b.value['pointer'][0],25)
  self.assertFalse(s.return_after_quiet(n,1));self.assertEqual(n.resumed,[1])
 def test_changed_ordinary_context_refreshes_only_without_old_point_or_focus(self):
  s,b,d,n=self.make(True);self.paused(s,n);b.value.update(window_id='new-window',epoch=11)
  self.assertTrue(s.return_after_quiet(n,1));self.assertEqual(s.return_state,'context-refreshed')
  self.assertEqual(d.events,[]);self.assertEqual((d.resumes,d.captures),(1,1));self.assertEqual(s.window_record['context']['window_id'],'new-window')
 def test_manual_pause_remains_sticky_and_no_quiet_no_resume(self):
  s,b,d,n=self.make();self.paused(s,n);s.begin_pause();s.finish_pause();self.assertFalse(s.return_after_quiet(n,1));self.assertFalse(n.resumed)
  s,b,d,n=self.make();n.quiet=False;self.paused(s,n);self.assertFalse(s.return_after_quiet(n,1));self.assertFalse(n.resumed)
 def test_protected_context_and_mapping_failure_are_terminal(self):
  for failure in ('protected','mapping'):
   s,b,d,n=self.make();self.paused(s,n)
   if failure=='protected':b.value.update(available=False,reason='system-ui')
   else:d.mapping_guard=lambda:(_ for _ in ()).throw(RuntimeError('mapping lost'))
   self.assertFalse(s.return_after_quiet(n,1));deadline=time.monotonic()+1
   while s.state!='closed' and time.monotonic()<deadline:time.sleep(.005)
   self.assertEqual(s.state,'closed');self.assertFalse(n.resumed);self.assertEqual(d.captures,0)
 def test_stale_owner_cannot_cancel_replacement_operation(self):
  s,b,d,n=self.make();old=Native();event=d.operation_cancelled;s.physical_intervention(old,1)
  self.assertFalse(event.is_set());self.assertEqual(s.state,'active')
 def test_foreground_signal_before_click_token_coalesces_without_terminal_cancel(self):
  s,b,d,n=self.make();n.intervention_epoch=None;n.yielded=False;b.value.update(window_id='clicked-window',epoch=11)
  s.foreground_lost(b);self.assertTrue(d.operation_cancelled.is_set());self.assertFalse(d.cancelled.is_set())
  n.intervention_epoch=1;n.yielded=True
  self.assertTrue(s.matched_click_context_loss());deadline=time.monotonic()+1
  while s.state!='paused' and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(s.state,'paused');self.assertFalse(d.cancelled.is_set());self.assertEqual(d.captures,0)
 def test_unmatched_or_protected_foreground_signal_closes_without_input(self):
  for protected in (False,True):
   s,b,d,n=self.make();n.intervention_epoch=None;n.yielded=False
   b.value.update(available=False,reason='system-ui') if protected else b.value.update(window_id='unmatched',epoch=11)
   s.foreground_lost(b);deadline=time.monotonic()+1
   while s.state!='closed' and time.monotonic()<deadline:time.sleep(.005)
   self.assertEqual(s.state,'closed');self.assertFalse(any(e[1].startswith('Notify') for e in d.events))
 def test_pending_classification_stops_pipeline_before_observation(self):
  s,b,d,n=self.make();n.intervention_epoch=None;n.yielded=False
  states=[];d.pipeline=SimpleNamespace(set_state=states.append);original=b.context;observed=threading.Event()
  def context():
   self.assertIsNone(d.pipeline);self.assertEqual(states,[retained.m.Gst.State.NULL]);self.assertEqual(d.captures,0);observed.set();return original()
  b.context=context;s.foreground_lost(b);self.assertTrue(observed.wait(1));self.assertEqual(d.captures,0)
 def test_late_coalescer_cannot_close_renewed_operation(self):
  s,b,d,n=self.make();n.intervention_epoch=None;n.yielded=False
  entered=threading.Event();release=threading.Event();original=b.context
  def context():entered.set();release.wait(1);return original()
  b.context=context;s.foreground_lost(b);self.assertTrue(entered.wait(1));record=s.click_context_pending
  # A successful recovery retires the correlation record before renewing input.
  s.click_context_pending=None;d.operation_cancelled=threading.Event();new=d.operation_cancelled
  release.set();self.assertTrue(record['done'].wait(1));self.assertFalse(d.cancelled.is_set());self.assertFalse(new.is_set());self.assertIsNotNone(d.session)
 def test_matching_click_never_masks_mapping_or_other_runtime_fault(self):
  s,b,d,n=self.make();s.matched_click_context_loss=lambda:True
  result=s.error_result(RuntimeError('Mapping changed'),'desktop_action')
  self.assertTrue(result['isError']);self.assertEqual(s.state,'closed');self.assertFalse(n.resumed)
 def test_only_typed_foreground_guard_can_retain_matched_click(self):
  s,b,d,n=self.make();s.matched_click_context_loss=lambda:True
  result=s.error_result(retained.m.ClickContextPending('foreground change'),'desktop_action')
  self.assertTrue(result['isError']);self.assertFalse(d.cancelled.is_set());self.assertIsNotNone(d.session)
