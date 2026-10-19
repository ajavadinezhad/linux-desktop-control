"""One verified relative return after a current native quiet epoch; no devices."""
import threading, unittest
import test_retained_pause as fixtures
m=fixtures.m

class Native:
 def __init__(self):self.yield_epoch=1;self.quiet_epoch=1;self.yielded=True;self.calls=[];self.closed=False
 def is_current_yield(self,epoch,quiet=False):return not self.closed and self.yielded and epoch==self.yield_epoch and (not quiet or self.quiet_epoch==epoch)
 def resume_from_pause(self,epoch,timeout=1):
  if not self.is_current_yield(epoch,quiet=True):raise RuntimeError('not quiet')
  self.calls.append(epoch);self.yielded=False
 def status(self):return {'active':not self.closed and not self.yielded,'observer_alive':not self.closed,'yield_epoch':self.yield_epoch,'quiet_epoch':self.quiet_epoch,'yielded':self.yielded}
 def close(self):self.closed=True

class PointerReturnTests(unittest.TestCase):
 def make(self):
  s,b,d=fixtures.RetainedPauseTests().make();self.addCleanup(s.close_backend)
  s.pointer_motion_return=True;s.consent_id='consent';d.consent_id=s.consent_id;d.endpoint_context=s.window_guard_module().WindowGuard.signature(b.value)
  s.native_activity=Native();s.physical_takeover=True
  # Production endpoint confirmation records the actual assistant destination.
  d.pointer_reader=lambda:tuple(b.value['pointer']);d.position(100,100);d.pointer_reader=None;d.endpoint_context=None
  saved=d.confirmed_pointer_record;self.assertEqual(saved['point'],(100.,100.));d.events.clear()
  s.begin_pause('pointer-motion',s.native_activity,1);s.finish_pause()
  b.value['pointer']=[140,130]
  return s,b,d,s.native_activity
 def motions(self,d):return [e for e in d.events if e[1]=='NotifyPointerMotion']
 def test_one_relative_return_same_context_then_fresh_capture_no_click_or_replay(self):
  s,b,d,n=self.make();old=d.operation_cancelled
  self.assertTrue(s.return_after_quiet(n,1));self.assertEqual(s.state,'active');self.assertEqual(n.calls,[1]);self.assertTrue(old.is_set())
  self.assertEqual(len(self.motions(d)),1);self.assertEqual(self.motions(d)[0][-1][-2:],(-40.,-30.))
  self.assertEqual(b.value['pointer'],[100.,100.]);self.assertEqual(d.captures,1);self.assertEqual(s.return_state,'returned')
  self.assertFalse(any(e[1] in ('NotifyPointerButton','NotifyKeyboardKeysym','NotifyPointerAxisDiscrete') for e in d.events))
  self.assertFalse(s.return_after_quiet(n,1));self.assertEqual(len(self.motions(d)),1)
 def test_no_saved_point_or_different_context_keeps_sharing_paused(self):
  for missing in (True,False):
   s,b,d,n=self.make()
   if missing:s.return_record=None
   else:b.value.update(window_id='human-other-app',epoch=11)
   self.assertFalse(s.return_after_quiet(n,1));self.assertEqual(s.state,'paused');self.assertFalse(d.cancelled.is_set());self.assertEqual(d.session,'/test');self.assertEqual(n.calls,[]);self.assertEqual(d.events,[])
 def test_outside_monitor_or_stale_epoch_never_sends_return(self):
  for stale in (True,False):
   s,b,d,n=self.make()
   if stale:n.yield_epoch=2;n.quiet_epoch=2
   else:b.value['pointer']=[2000,100]
   self.assertFalse(s.return_after_quiet(n,1));self.assertEqual(d.events,[]);self.assertEqual(n.calls,[]);self.assertFalse(d.cancelled.is_set())
 def test_new_motion_during_return_reyields_and_does_not_capture_or_correct(self):
  s,b,d,n=self.make();original=d.call
  def call(iface,method,sig,args,**kw):
   original(iface,method,sig,args,**kw)
   if method=='NotifyPointerMotion':
    n.yield_epoch=2;n.quiet_epoch=None;n.yielded=True
    s.begin_pause('pointer-motion',n,2)
  d.call=call
  self.assertFalse(s.return_after_quiet(n,1));s.finish_pause();self.assertEqual(s.state,'paused');self.assertFalse(d.cancelled.is_set());self.assertEqual(len(self.motions(d)),1);self.assertEqual(d.captures,0);self.assertEqual(n.calls,[1])
 def test_new_motion_during_native_resume_ack_cannot_enable_old_operation(self):
  s,b,d,n=self.make()
  def resume(epoch,timeout=1):
   n.calls.append(epoch);n.yield_epoch=2;n.quiet_epoch=None;n.yielded=True;s.begin_pause('pointer-motion',n,2)
  n.resume_from_pause=resume
  self.assertFalse(s.return_after_quiet(n,1));s.finish_pause();self.assertEqual(s.state,'paused');self.assertEqual(d.events,[]);self.assertEqual(d.captures,0)
 def test_pre_pause_and_paused_queue_generations_stay_discarded_after_auto_return(self):
  s,b,d,n=self.make();paused_generation=s.generation;self.assertTrue(s.return_after_quiet(n,1));events=list(d.events)
  for epoch in (paused_generation-1,paused_generation):
   s.request_epoch=epoch
   try:r=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{'type':'click','x':50,'y':50}}}})
   finally:s.request_epoch=None
   self.assertTrue(r['result']['isError']);self.assertEqual(s.state,'active');self.assertFalse(d.cancelled.is_set());self.assertEqual(d.events,events)

 def test_wrong_return_endpoint_closes_without_second_displacement(self):
  import time
  s,b,d,n=self.make();original=d.call
  def call(iface,method,sig,args,**kw):
   original(iface,method,sig,args,**kw)
   if method=='NotifyPointerMotion':b.value['pointer']=[120,115]
  d.call=call
  self.assertFalse(s.return_after_quiet(n,1));deadline=time.monotonic()+1
  while s.state!='closed' and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(s.state,'closed');self.assertEqual(len(self.motions(d)),1);self.assertEqual(d.captures,0)
 def test_native_resume_fault_or_changed_mapping_remains_terminal(self):
  import time
  for mapping_change in (True,False):
   s,b,d,n=self.make()
   if mapping_change:d.mapping_guard=lambda:None
   else:n.resume_from_pause=lambda epoch:(_ for _ in ()).throw(RuntimeError('native lease fault'))
   self.assertFalse(s.return_after_quiet(n,1));deadline=time.monotonic()+1
   while s.state!='closed' and time.monotonic()<deadline:time.sleep(.005)
   self.assertEqual(s.state,'closed');self.assertFalse(any(e[1].startswith('Notify') for e in d.events))
 def test_motion_during_fresh_capture_discards_image_and_keeps_new_pause(self):
  s,b,d,n=self.make();capture=d.capture
  def interrupted_capture():
   png=capture();n.yield_epoch=2;n.quiet_epoch=None;n.yielded=True;s.begin_pause('pointer-motion',n,2);return png
  d.capture=interrupted_capture
  self.assertFalse(s.return_after_quiet(n,1));s.finish_pause();self.assertEqual(s.state,'paused');self.assertFalse(d.cancelled.is_set());self.assertIsNone(s.window_record);self.assertEqual(len(self.motions(d)),1)

 def test_native_yield_callback_never_waits_for_publication_lock(self):
  s,b,d,n=self.make();self.assertTrue(s.return_after_quiet(n,1));n.yield_epoch=2;n.quiet_epoch=None;n.yielded=True
  finished=threading.Event()
  with s.state_lock:
   callback=threading.Thread(target=lambda:(s.pointer_yielded(n,2),finished.set()));callback.start()
   self.assertTrue(d.operation_cancelled.wait(.5));self.assertTrue(finished.wait(.5));self.assertFalse(d.cancelled.is_set())
  callback.join(1)
  import time
  deadline=time.monotonic()+1
  while s.state!='paused' and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(s.state,'paused')
 def test_quiet_can_admit_pause_if_suspend_worker_has_not_run_yet(self):
  s,b,d,n=self.make();self.assertTrue(s.return_after_quiet(n,1));d.events.clear()
  n.yield_epoch=2;n.quiet_epoch=2;n.yielded=True;d.operation_cancelled.set();b.value['pointer']=[150,140]
  self.assertTrue(s.return_after_quiet(n,2));self.assertEqual(len(self.motions(d)),1);self.assertEqual(s.return_state,'returned')

 def test_manual_pause_then_motion_and_quiet_stays_manual_until_explicit_resume(self):
  s,b,d,n=self.make();self.assertTrue(s.return_after_quiet(n,1));d.events.clear()
  s.begin_pause('manual');s.finish_pause();n.yield_epoch=2;n.quiet_epoch=2;n.yielded=True
  s.begin_pause('pointer-motion',n,2);s.finish_pause()
  self.assertEqual(s.pause_reason,'manual');self.assertTrue(s.manual_pause_requested)
  self.assertFalse(s.return_after_quiet(n,2));self.assertEqual(s.state,'paused');self.assertEqual(d.events,[])
  s.resume_sharing({'pause_id':s.pause_id});self.assertEqual(s.state,'active');self.assertEqual(n.calls,[1,2]);self.assertEqual(d.events,[])
 def test_manual_pause_overrides_existing_pointer_pause_and_pending_quiet(self):
  s,b,d,n=self.make();old_pause=s.pause_id;s.begin_pause('manual');s.finish_pause()
  self.assertEqual(s.pause_reason,'manual');self.assertNotEqual(s.pause_id,old_pause)
  self.assertFalse(s.return_after_quiet(n,1));self.assertEqual(s.state,'paused');self.assertEqual(d.events,[]);self.assertEqual(n.calls,[])
 def test_manual_pause_arriving_during_auto_resume_ack_forbids_return(self):
  s,b,d,n=self.make();resume=n.resume_from_pause
  def manual(epoch,timeout=1):
   resume(epoch,timeout);s.begin_pause('manual')
  n.resume_from_pause=manual
  self.assertFalse(s.return_after_quiet(n,1));s.finish_pause()
  self.assertEqual(s.pause_reason,'manual');self.assertEqual(s.state,'paused');self.assertEqual(d.events,[]);self.assertEqual(d.captures,0)

 def test_manual_intent_between_final_check_and_event_renewal_is_not_cleared(self):
  from unittest import mock
  s,b,d,n=self.make();event_factory=threading.Event;injected=[]
  def renew():
   event=event_factory()
   if s.state=='resuming' and not injected:
    injected.append(True);s.manual_pause_requested=True
   return event
  with mock.patch.object(m.threading,'Event',side_effect=renew):
   self.assertFalse(s.return_after_quiet(n,1))
  self.assertEqual(injected,[True]);self.assertTrue(s.manual_pause_requested);self.assertEqual(s.pause_reason,'manual');self.assertEqual(s.state,'paused');self.assertEqual(d.events,[]);self.assertEqual(d.captures,0)
 def test_manual_intent_after_return_forbids_automatic_capture(self):
  s,b,d,n=self.make();position=d.position
  def returned(x,y):position(x,y);s.manual_pause_requested=True
  d.position=returned
  self.assertFalse(s.return_after_quiet(n,1));self.assertTrue(s.manual_pause_requested);self.assertEqual(s.state,'paused');self.assertEqual(s.pause_reason,'manual');self.assertEqual(d.captures,0);self.assertEqual(len(self.motions(d)),1)

if __name__=='__main__':unittest.main()
