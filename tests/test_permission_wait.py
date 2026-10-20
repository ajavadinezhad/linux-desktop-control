import copy,json,threading,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_window_guard as fixture

class PermissionWaitTests(unittest.TestCase):
 def make(self,states=None):
  s,b,d=fixture.FullTransitionTests().make();d.shutdown=lambda:None
  events=[];auth={'waiting':False};s.native_allow_permission_wait=True;s.interruption_policy="retain-sharing";b.auth_wait_protocol=3
  def begin():events.append('auth-begin');auth['waiting']=True;return 1
  def end(epoch):self.assertEqual(epoch,1);events.append('auth-end');auth['waiting']=False;return 1
  s.native_activity=SimpleNamespace(status=lambda:{'active':True,'auth_wait_supported':True},begin_auth_wait=begin,end_auth_wait=end,close=lambda:None)
  none={'auth_state':'none','origin_window_id':'window-1','attempt_id':None,'action_category':'none'}
  values=list(states if states is not None else [none,dict(none,auth_state='visible',attempt_id='a'*32,action_category='system-authentication'),dict(none,attempt_id='a'*32)])
  last=[none]
  def auth_state():
   if values:last[0]=values.pop(0)
   return copy.deepcopy(last[0])
  b.auth_state=auth_state;d.pause_input=lambda:events.append('capture-off');d.resume_capture=lambda:events.append('capture-on');d.mapping_guard=lambda:None
  capture=d.capture
  def checked_capture():self.assertFalse(auth['waiting']);events.append('capture');return capture()
  d.capture=checked_capture
  original=d.call
  def call(iface,method,sig,args,**kw):
   if method=='NotifyPointerButton' and args[-1]==1:self.assertTrue(auth['waiting']);self.assertIn('capture-off',events);events.append('click')
   return original(iface,method,sig,args,**kw)
  d.call=call
  return s,b,d,events,auth
 def action(self,s,**updates):
  args={'window_observation_id':s.window_record['id'],'focus_transition':True,'wait_for_permission':True,'recording_stopped':True,'action':{'type':'click','x':50,'y':50},**updates}
  request={'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':args}}
  return s.fence_response(request,s.handle(request))
 def test_one_click_capture_off_during_human_wait_then_fresh_image(self):
  s,b,d,events,auth=self.make()
  try:
   result=self.action(s);self.assertFalse(result['result'].get('isError',False),result)
   self.assertEqual(events[:3],['capture-off','auth-begin','click']);self.assertEqual(events.count('click'),1)
   self.assertLess(events.index('auth-end'),events.index('capture-on'));self.assertEqual(events.count('capture'),1)
   self.assertEqual(s.permission_wait_stage,'prompt-observed');self.assertEqual(s.state,'active')
  finally:s.shutdown()
 def test_no_prompt_grace_does_not_claim_approval_or_wait_full_timeout(self):
  none={'auth_state':'none','origin_window_id':'window-1','attempt_id':None,'action_category':'none'}
  s,b,d,events,auth=self.make([none])
  try:
   with patch.object(fixture.m,'PERMISSION_NO_PROMPT_GRACE',0):result=self.action(s)
   self.assertFalse(result['result'].get('isError',False),result);self.assertEqual(s.permission_wait_stage,'prompt-not-observed')
   self.assertEqual(events.count('click'),1);self.assertEqual(events.count('capture'),1)
  finally:s.shutdown()
 def test_blocked_changed_attempt_origin_and_pending_disappearance_never_capture(self):
  none={'auth_state':'none','origin_window_id':'window-1','attempt_id':None,'action_category':'none'}
  visible=dict(none,auth_state='visible',attempt_id='a'*32,action_category='system-authentication')
  for value in [dict(none,auth_state='blocked'),dict(visible,origin_window_id='other'),dict(visible,action_category='unknown')]:
   s,b,d,events,auth=self.make([none,value])
   try:
    result=self.action(s);self.assertTrue(result['result']['isError']);self.assertNotIn('capture',events);self.assertEqual(events.count('click'),1)
   finally:s.shutdown()
  s,b,d,events,auth=self.make([none,dict(visible,auth_state='pending'),dict(none,attempt_id='a'*32)])
  try:
   self.assertTrue(self.action(s)['result']['isError']);self.assertNotIn('capture',events)
  finally:s.shutdown()
 def test_invalid_flags_refuse_before_click(self):
  for updates in [{'recording_stopped':False},{'wait_for_permission':1},{'focus_transition':False},{'await_context_change':True},{'action':{'type':'keys','keys':['Return']}}]:
   s,b,d,events,auth=self.make()
   try:self.assertTrue(self.action(s,**updates)['result']['isError']);self.assertNotIn('click',events);self.assertNotIn('capture',events)
   finally:s.shutdown()
 def test_wait_snapshot_is_read_only_and_cancellation_stops_without_capture(self):
  s,b,d,events,auth=self.make()
  try:
   record=s.prepare_permission_wait(b.context());snapshot=s.startup_status_snapshot()
   self.assertEqual(snapshot['snapshot_kind'],'permission-wait-read-only');self.assertFalse(snapshot['capture_allowed']);self.assertFalse(snapshot['input_allowed'])
   s.backend.cancelled.set()
   with self.assertRaises(RuntimeError):s.finish_permission_wait(record)
   self.assertNotIn('capture',events)
  finally:s.shutdown()
 def test_slow_auth_query_or_owner_loss_prevents_capture(self):
  for cause in ('late','owner','native','lease'):
   s,b,d,events,auth=self.make()
   try:
    record=s.prepare_permission_wait(b.context());original=b.auth_state
    def query():
     if cause=='late':time.sleep(.02)
     elif cause=='owner':s.consent_id='replacement'
     elif cause=='native':s.native_activity.status=lambda:{'active':False}
     else:s.native_activity._yield_authorized=lambda:False
     return original()
    b.auth_state=query
    if cause=='late':record['deadline']=time.monotonic()+.01
    with self.assertRaises(RuntimeError):s.finish_permission_wait(record)
    self.assertNotIn('capture',events)
   finally:s.shutdown()
 def test_auth_reappearing_before_publication_suppresses_image(self):
  s,b,d,events,auth=self.make()
  try:
   result=self.action(s);self.assertFalse(result['result'].get('isError',False))
   b.auth_state=lambda:{'auth_state':'visible','origin_window_id':'window-1','attempt_id':'b'*32,'action_category':'system-authentication'}
   result=s.fence_response({'id':2,'params':{'name':'desktop_action'}},result)
   self.assertTrue(result['result']['isError']);self.assertFalse(any(c['type']=='image' for c in result['result']['content']))
  finally:s.shutdown()

 def test_layout_changed_during_capture_prevents_publication(self):
  s,b,d,events,auth=self.make();original=d.capture;invalid=[False]
  try:
   def mapping():
    if invalid[0]:raise RuntimeError('layout changed')
   def capture():
    result=original();invalid[0]=True;return result
   d.mapping_guard=mapping;d.capture=capture
   result=self.action(s);self.assertTrue(result['result']['isError']);self.assertFalse(any(c['type']=='image' for c in result['result']['content']))
  finally:s.shutdown()
