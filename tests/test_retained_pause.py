"""Retained consent and discarded operations, without GUI or devices."""
import json, threading, time, unittest
from types import SimpleNamespace
import test_control, test_window_guard, test_transition_transport
m=test_control.m

class RetainedPauseTests(unittest.TestCase):
 def make(self):
  s,b,d=test_window_guard.FullTransitionTests().make();s.interruption_policy='retain-sharing'
  d.operation_cancelled=threading.Event();d.resumes=0;d.captures=0
  def resume():d.check();d.resumes+=1
  def capture():d.check();d.captures+=1;return test_control.Fake.capture(d)
  d.resume_capture=resume;d.capture=capture;self.addCleanup(s.close_backend)
  return s,b,d
 def request(self,s,name,args=None,epoch=None):
  q={'id':1,'method':'tools/call','params':{'name':name,'arguments':args or {}}}
  if epoch is not None:q['_generation']=epoch;s.request_epoch=epoch
  try:return s.fence_response(q,s.handle(q))['result']
  finally:s.request_epoch=None
 def test_pause_releases_hold_preserves_portal_and_refuses_capture_or_input(self):
  s,b,d=self.make();old=d.operation_cancelled;d.held=[('button',272)];generation=s.generation
  r=self.request(s,'desktop_pause');self.assertFalse(r.get('isError',False),r)
  self.assertEqual(s.state,'paused');self.assertEqual(s.generation,generation+1)
  self.assertTrue(old.is_set());self.assertFalse(d.cancelled.is_set());self.assertEqual(d.session,'/test');self.assertEqual(d.held,[])
  self.assertEqual(d.events[-1][1],'NotifyPointerButton');self.assertEqual(d.events[-1][-1][-1],0)
  for name,args in [('desktop_observe',{}),('desktop_start',{}),('desktop_action',{'action':{'type':'keys','keys':['a']}})]:
   r=self.request(s,name,args);self.assertTrue(r['isError']);self.assertEqual(s.state,'paused');self.assertEqual(d.session,'/test')
  self.assertEqual(d.captures,0);status=s.status();self.assertTrue(status['sharing_active']);self.assertFalse(status['input_allowed']);self.assertFalse(status['capture_allowed'])
 def test_resume_new_event_fresh_image_and_tokens_without_replay(self):
  s,b,d=self.make();self.request(s,'desktop_pause');pause_id=s.pause_id;old=d.operation_cancelled;generation=s.generation
  self.assertTrue(self.request(s,'desktop_resume',{'pause_id':'0'*32})['isError']);self.assertEqual(s.state,'paused')
  r=self.request(s,'desktop_resume',{'pause_id':pause_id},generation);self.assertFalse(r.get('isError',False),r)
  self.assertEqual(s.state,'active');self.assertTrue(old.is_set());self.assertIsNot(old,d.operation_cancelled);self.assertFalse(d.operation_cancelled.is_set())
  self.assertEqual(d.events,[]);self.assertEqual((d.resumes,d.captures),(1,1));self.assertEqual(s.window_record['generation'],s.generation);self.assertIsNone(s.pause_id)
 def test_old_queued_work_cannot_input_or_close_resumed_session(self):
  s,b,d=self.make();generation=s.generation;self.request(s,'desktop_pause');self.request(s,'desktop_resume',{'pause_id':s.pause_id})
  for name in ('desktop_action','desktop_start','desktop_observe'):
   r=self.request(s,name,{'action':{'type':'click','x':10,'y':10}} if name=='desktop_action' else {},generation)
   self.assertTrue(r['isError']);self.assertEqual(s.state,'active');self.assertFalse(d.cancelled.is_set());self.assertEqual(d.events,[])
 def test_terminal_native_fault_while_paused_closes(self):
  s,b,d=self.make();self.request(s,'desktop_pause');owner=SimpleNamespace(close=lambda:None,status=lambda:{'active':False});s.own_observer('native_activity',owner)
  s.native_activity_lost(owner,'fault');deadline=time.monotonic()+1
  while s.state!='closed' and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(s.state,'closed');self.assertTrue(d.cancelled.is_set());self.assertIsNone(d.session)
  self.assertTrue(self.request(s,'desktop_resume',{'pause_id':'0'*32})['isError']);self.assertEqual(d.resumes,0)
 def test_revocation_or_capture_resume_failure_closes(self):
  for revoked in (True,False):
   s,b,d=self.make();self.request(s,'desktop_pause');pause_id=s.pause_id
   if revoked:d.on_session_closed(None,None,d.session,None,None,None,None)
   else:d.resume_capture=lambda:(_ for _ in ()).throw(RuntimeError('capture failed'))
   self.assertTrue(self.request(s,'desktop_resume',{'pause_id':pause_id})['isError']);self.assertEqual(s.state,'closed');self.assertTrue(d.cancelled.is_set())
 def test_pause_cancels_before_waiting_for_publication_lock(self):
  s,b,d=self.make();finished=threading.Event()
  with s.state_lock:
   worker=threading.Thread(target=lambda:(s.begin_pause(),finished.set()));worker.start()
   self.assertTrue(d.operation_cancelled.wait(.5));self.assertFalse(d.cancelled.is_set());self.assertFalse(finished.is_set())
  worker.join(1);self.assertTrue(finished.is_set());s.finish_pause()
 def test_default_policy_pause_closes(self):
  s,b,d=self.make();s.interruption_policy='close';self.request(s,'desktop_pause');self.assertEqual(s.state,'closed');self.assertIsNone(d.session)
 def test_discarded_image_cannot_close_paused_sharing(self):
  s,b,d=self.make();r={'id':1,'result':{'content':[m.text({}),m.image(test_control.Fake.capture(d))]}};s.begin_pause()
  result=s.fence_response({'id':1,'params':{'name':'desktop_observe'}},r)
  self.assertTrue(result['result']['isError']);self.assertFalse(any(v['type']=='image' for v in result['result']['content']));self.assertFalse(d.cancelled.is_set());s.finish_pause()

 def test_capture_pipeline_stops_and_mapping_and_consent_remain_owned(self):
  s,b,d=self.make();states=[];pipeline=SimpleNamespace(set_state=states.append)
  d.pipeline=pipeline;mapping=d.mapping_guard
  self.assertFalse(self.request(s,'desktop_pause').get('isError',False))
  self.assertEqual(states,[m.Gst.State.NULL]);self.assertIsNone(d.pipeline)
  self.assertIs(d.mapping_guard,mapping);self.assertEqual(d.session,'/test')
 def test_capture_suspension_failure_is_terminal(self):
  s,b,d=self.make()
  d.pipeline=SimpleNamespace(set_state=lambda state:(_ for _ in ()).throw(RuntimeError('stop failed')))
  self.assertTrue(self.request(s,'desktop_pause')['isError']);self.assertEqual(s.state,'closed');self.assertTrue(d.cancelled.is_set());self.assertIsNone(d.session)
 def test_opt_in_is_bound_to_new_consent_session_and_default_remains_close(self):
  s=m.Server(test_control.Fake);self.addCleanup(s.close_backend)
  s.call('desktop_start',{});self.assertEqual(s.interruption_policy,'close');s.call('desktop_close',{})
  s.call('desktop_start',{'interruption_policy':'retain-sharing'});self.assertEqual(s.interruption_policy,'retain-sharing')
  self.assertIsInstance(s.backend.operation_cancelled,threading.Event)

 def test_lock_or_mapping_failure_while_paused_is_terminal(self):
  for locked in (True,False):
   s,b,d=self.make();self.request(s,'desktop_pause');pause_id=s.pause_id
   if locked:b.value={'available':False,'reason':'locked'}
   else:d.mapping_guard=lambda:(_ for _ in ()).throw(RuntimeError('layout changed'))
   self.assertFalse(s.check_pause_health(pause_id,d,b));self.assertEqual(s.state,'closed');self.assertIsNone(d.session)
 def test_retired_pause_health_failure_cannot_close_resumed_session(self):
  s,b,d=self.make();self.request(s,'desktop_pause');pause_id=s.pause_id
  self.request(s,'desktop_resume',{'pause_id':pause_id});b.value={'available':False,'reason':'locked'}
  self.assertFalse(s.check_pause_health(pause_id,d,b));self.assertEqual(s.state,'active');self.assertFalse(d.cancelled.is_set())

class RetainedTransportTests(unittest.TestCase):
 def test_pause_interrupts_drag_discards_queued_click_and_keeps_portal(self):
  h=test_transition_transport.Harness();h.server.interruption_policy='retain-sharing';h.backend.operation_cancelled=threading.Event();h.backend.resume_capture=lambda:None
  entered=threading.Event();original=h.backend.call
  def call(iface,method,sig,args,**kw):
   original(iface,method,sig,args,**kw)
   if method=='NotifyPointerButton' and args[-1]==1:
    entered.set()
    if not h.backend.operation_cancelled.wait(2):raise RuntimeError('pause did not interrupt')
  h.backend.call=call
  try:
   h.send(1,'desktop_action',{'window_observation_id':h.observation_id,'action':{'type':'drag','path':[[40,40],[60,60]]}});self.assertTrue(entered.wait(1))
   h.send(2,'desktop_action',{'window_observation_id':h.observation_id,'action':{'type':'click','x':50,'y':50}});h.send(3,'desktop_pause')
   self.assertTrue(h.output.reply(1)['result']['isError']);self.assertTrue(h.output.reply(2)['result']['isError']);self.assertFalse(h.output.reply(3)['result'].get('isError',False))
   self.assertEqual(h.server.state,'paused');self.assertFalse(h.backend.cancelled.is_set());self.assertEqual(h.backend.session,'/test');self.assertEqual(h.backend.held,[])
   self.assertEqual([e[-1][-1] for e in h.backend.events if e[1]=='NotifyPointerButton'],[1,0])
  finally:h.close()

if __name__=='__main__':unittest.main()
