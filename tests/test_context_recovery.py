"""Ordinary application swaps never replay input or grant unseen authority."""
import threading,time,unittest
from unittest.mock import patch
import test_control,test_retained_pause
m=test_control.m
class Native:
 def __init__(self):self.healthy=True;self.yielded=False
 def status(self):return {'active':self.healthy and not self.yielded,'observer_alive':self.healthy,'yielded':self.yielded,'yield_epoch':1}
 def _yield_authorized(self):return self.healthy
 def is_current_yield(self,e,quiet=False):return self.yielded and e==1
 def is_current_intervention(self,e,quiet=False):return False
 def close(self):self.healthy=False
class ContextRecoveryTests(unittest.TestCase):
 request=test_retained_pause.RetainedPauseTests.request
 def make(self):
  s,b,d=test_retained_pause.RetainedPauseTests.make(self);s.context_change_policy='pause-recover';s.native_activity=Native()
  return s,b,d
 def settle(self,s):
  end=time.monotonic()+2
  while time.monotonic()<end:
   r=s.context_recovery
   if r and r['phase'] in ('complete','failed','manual','handed-off'):return r['phase']
   time.sleep(.005)
  self.fail('recovery did not settle')
 def test_swap_cancels_old_work_releases_hold_and_requires_new_image(self):
  s,b,d=self.make();old=d.operation_cancelled;d.held=[('button',272)];b.value=dict(b.value,window_id='replacement',epoch=11)
  with patch.object(m,'CONTEXT_RECOVERY_QUIET',.02):
   s.foreground_lost(b);self.assertTrue(old.wait(.5));self.assertEqual(self.settle(s),'complete')
  self.assertFalse(d.cancelled.is_set());self.assertEqual(d.held,[]);self.assertIsNot(old,d.operation_cancelled)
  self.assertTrue(s.context_observation_required);self.assertFalse(s.status()['input_allowed'])
  r=self.request(s,'desktop_action',{'action':{'type':'click','x':1,'y':1}});self.assertTrue(r['isError']);self.assertEqual(s.state,'active')
  r=self.request(s,'desktop_observe');self.assertFalse(r.get('isError',False),r);self.assertFalse(s.context_observation_required)
 def test_protected_and_mapping_faults_remain_terminal(self):
  for protected in (True,False):
   s,b,d=self.make()
   if protected:b.value={'available':False,'reason':'locked'}
   else:d.mapping_guard=lambda:(_ for _ in ()).throw(RuntimeError('layout'))
   s.foreground_lost(b);self.assertEqual(self.settle(s),'failed');self.assertEqual(s.state,'closed')
 def test_unavailable_gap_can_settle_without_restarting_portal(self):
  s,b,d=self.make();old=b.value;b.value={'available':False,'reason':'no-foreground-window'}
  with patch.object(m,'CONTEXT_RECOVERY_QUIET',.02):
   s.foreground_lost(b);time.sleep(.03);b.value=old;self.assertEqual(self.settle(s),'complete')
  self.assertEqual(d.session,'/test')
 def test_slow_query_past_original_deadline_cannot_resume(self):
  s,b,d=self.make();original=b.context
  def slow():time.sleep(.05);return original()
  b.context=slow
  with patch.object(m,'CONTEXT_RECOVERY_SECONDS',.02):s.foreground_lost(b);self.assertEqual(self.settle(s),'failed')
  self.assertEqual(d.resumes,0)
 def test_stale_worker_cannot_cancel_replacement(self):
  s,b,d=self.make();entered=threading.Event();release=threading.Event();original=b.context
  def slow():entered.set();release.wait(1);return original()
  b.context=slow;s.foreground_lost(b);self.assertTrue(entered.wait(1));old=s.context_recovery
  s.consent_id='replacement';release.set();time.sleep(.1)
  self.assertFalse(d.cancelled.is_set());self.assertIs(s.context_recovery,old)
 def test_default_guard_failure_remains_terminal(self):
  s,b,d=self.make();s.context_change_policy='close';s.foreground_lost(b)
  end=time.monotonic()+1
  while s.state!='closed' and time.monotonic()<end:time.sleep(.005)
  self.assertEqual(s.state,'closed')
 def test_mid_drag_change_releases_button_and_discards_remaining_steps(self):
  s,b,d=self.make();original=d.call;presses=[]
  def call(iface,method,sig,args,**kw):
   original(iface,method,sig,args,**kw)
   if method=='NotifyPointerButton' and args[-1]==1:
    presses.append(True)
    if len(presses)==2:b.value.update(epoch=11,window_id='new-main')
  d.call=call;token=s.window_record['id']
  with patch.object(m,'CONTEXT_RECOVERY_QUIET',.02):
   r=self.request(s,'desktop_action',{'window_observation_id':token,'action':{'type':'sequence','steps':[{'type':'click','x':50,'y':50},{'type':'drag','path':[[50,50],[60,60],[70,70]]},{'type':'keys','keys':['a']}]}})
   self.assertTrue(r['isError']);self.assertEqual(self.settle(s),'complete')
  self.assertEqual(d.held,[]);self.assertFalse(d.cancelled.is_set())
  self.assertFalse(any(e[1]=='NotifyKeyboardKeysym' for e in d.events))
 def test_status_snapshot_does_not_wait_for_context_query(self):
  s,b,d=self.make();entered=threading.Event();release=threading.Event();original=b.context
  def slow():entered.set();release.wait(1);return original()
  b.context=slow;s.foreground_lost(b);self.assertTrue(entered.wait(1))
  start=time.monotonic();snapshot=s.startup_status_snapshot();self.assertLess(time.monotonic()-start,.05)
  self.assertEqual(snapshot['snapshot_kind'],'context-recovery-read-only');self.assertFalse(snapshot['input_allowed']);self.assertFalse(snapshot['capture_allowed'])
  d.cancelled.set();release.set()
 def test_manual_pause_during_settling_stays_paused(self):
  s,b,d=self.make();b.value={'available':False,'reason':'no-foreground-window'}
  s.foreground_lost(b);time.sleep(.03);s.manual_pause_requested=True
  self.assertEqual(self.settle(s),'manual');self.assertEqual(s.pause_reason,'manual');self.assertTrue(d.operation_cancelled.is_set());self.assertEqual(d.resumes,0)
 def test_capture_fault_does_not_hide_behind_completed_recovery(self):
  s,b,d=self.make()
  with patch.object(m,'CONTEXT_RECOVERY_QUIET',.02):s.foreground_lost(b);self.assertEqual(self.settle(s),'complete')
  d.capture=lambda:(_ for _ in ()).throw(RuntimeError('capture unavailable'))
  self.assertTrue(self.request(s,'desktop_observe')['isError']);self.assertEqual(s.state,'closed')
 def test_native_yield_during_capture_restart_hands_to_exact_epoch_pause(self):
  s,b,d=self.make();n=s.native_activity
  def resume():n.yielded=True;d.operation_cancelled.set();d.check()
  d.resume_capture=resume
  with patch.object(m,'CONTEXT_RECOVERY_QUIET',.02):
   s.foreground_lost(b);self.assertEqual(self.settle(s),'handed-off')
  end=time.monotonic()+1
  while s.pause_reason!='pointer-motion' and time.monotonic()<end:time.sleep(.005)
  self.assertEqual(s.pause_reason,'pointer-motion');self.assertFalse(d.cancelled.is_set());self.assertTrue(d.operation_cancelled.is_set());self.assertTrue(s.context_observation_required)
 def test_close_cancels_while_slow_query_cannot_resurrect(self):
  s,b,d=self.make();entered=threading.Event();release=threading.Event();original=b.context
  def slow():entered.set();release.wait(1);return original()
  b.context=slow;s.foreground_lost(b);self.assertTrue(entered.wait(1))
  # Transport's immediate terminal cancellation precedes lifecycle teardown.
  d.cancelled.set();release.set();time.sleep(.1)
  self.assertEqual(d.resumes,0);self.assertTrue(d.operation_cancelled.is_set())
 def test_invalid_zero_input_transition_returns_fresh_image_without_portal_restart(self):
  s,b,d=self.make();token=s.window_record['id']
  r=self.request(s,'desktop_action',{'window_observation_id':token,'focus_transition':True,'action':{'type':'keys','keys':['Return'],'focus':{'x':10,'y':10}}})
  self.assertFalse(r.get('isError',False),r);self.assertEqual(d.events,[]);self.assertEqual(s.state,'active');self.assertFalse(d.cancelled.is_set())
  self.assertTrue(any(v['type']=='image' for v in r['content']));self.assertNotEqual(token,s.window_record['id'])
 def test_invalid_identity_and_concurrent_mapping_fault_stay_terminal(self):
  for stale in (True,False):
   s,b,d=self.make();token=s.window_record['id']
   if not stale:d.mapping_guard=lambda:(_ for _ in ()).throw(RuntimeError('layout changed'))
   r=self.request(s,'desktop_action',{'window_observation_id':'stale' if stale else token,'focus_transition':True,'action':{'type':'keys','keys':['Return'],'focus':{'x':10,'y':10}}})
   self.assertTrue(r['isError']);self.assertEqual(s.state,'closed');self.assertFalse(any(v['type']=='image' for v in r['content']))
 def test_reader_latched_manual_pause_before_context_callback_remains_manual(self):
  s,b,d=self.make();s.manual_pause_requested=True;s.foreground_lost(b)
  self.assertEqual(self.settle(s),'manual');self.assertEqual(s.pause_reason,'manual');self.assertEqual(s.state,'paused');self.assertFalse(d.cancelled.is_set());self.assertEqual(d.resumes,0)
 def test_manual_pause_during_final_mapping_check_stays_manual(self):
  s,b,d=self.make();original=d.mapping_guard;post=[]
  def mapping():
   original()
   if d.resumes:
    post.append(True)
    if len(post)==2:s.manual_pause_requested=True;d.operation_cancelled.set()
  d.mapping_guard=mapping
  with patch.object(m,'CONTEXT_RECOVERY_QUIET',.02):s.foreground_lost(b);self.assertEqual(self.settle(s),'manual')
  self.assertEqual(s.state,'paused');self.assertEqual(s.pause_reason,'manual');self.assertFalse(d.cancelled.is_set());self.assertTrue(d.operation_cancelled.is_set())
