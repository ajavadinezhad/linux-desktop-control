import time,unittest
from unittest.mock import patch
import test_window_guard as f

class LaunchArrivalTests(unittest.TestCase):
 def make(self):return f.WindowServerTests().make()
 def test_unchanged_origin_does_not_publish(self):
  s,b=self.make()
  try:
   origin=s.window_guard_module().WindowGuard.signature(b.context())
   with self.assertRaises(RuntimeError):s.capture_result(('active',),transition_settle=True,transition_origin=origin,transition_deadline=time.monotonic()+.18)
  finally:s.shutdown()
 def test_late_observer_is_rejected_before_stability_success(self):
  s,b=self.make();base=time.monotonic()
  try:
   with patch.object(s,'read_window_context',lambda *_:b.context()),patch.object(f.m.time,'monotonic',side_effect=[base,base,base+.05,base+.3]):
    with self.assertRaises(RuntimeError):s.stable_transition_context(base+.2)
  finally:s.shutdown()
 def test_observer_query_exceeding_budget_and_cancellation_refuse(self):
  for cancel in (False,True):
   s,b=self.make();original=b.context
   try:
    def context():
     if cancel:s.backend.cancelled.set()
     time.sleep(.02);return original()
    b.context=context
    with self.assertRaises(RuntimeError):s.read_window_context(.01)
   finally:s.shutdown()
 def test_changed_context_and_late_capture(self):
  for late in (False,True):
   s,b=self.make();original=s.backend.capture;origin=s.window_guard_module().WindowGuard.signature(b.context())
   try:
    b.value.update(window_id='launched-app',epoch=11)
    def capture():
     if late:time.sleep(.1)
     return original()
    s.backend.capture=capture
    if late:
     with self.assertRaises(RuntimeError):s.capture_result(('active',),transition_settle=True,transition_origin=origin,transition_deadline=time.monotonic()+.2)
    else:
     result=s.capture_result(('active',),transition_settle=True,transition_origin=origin,transition_deadline=time.monotonic()+1)
     self.assertTrue(any(c['type']=='image' for c in result));self.assertEqual(s.backend.actions,0)
   finally:s.shutdown()
 def test_protected_context_refused(self):
  s,b=self.make()
  try:
   b.value.update(available=False,reason='system-ui')
   with self.assertRaises(RuntimeError):s.capture_result(('active',),transition_settle=True,transition_origin=('old',),transition_deadline=time.monotonic()+1)
  finally:s.shutdown()
 def test_invalid_optin_rejected_before_input(self):
  for extra,action in [({'await_context_change':1},{'type':'click','x':50,'y':50}),({'await_context_change':True,'focus_transition':False},{'type':'click','x':50,'y':50}),({'await_context_change':True},{'type':'keys','keys':['Ctrl','s']}),({'await_context_change':True,'window_fit_shared':True},{'type':'keys','keys':['Return']})]:
   s,b=self.make()
   try:
    args={'window_observation_id':s.window_record['id'],'focus_transition':True,'action':action,**extra}
    response=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':args}})
    self.assertTrue(response['result']['isError']);self.assertEqual(s.backend.actions,0)
   finally:s.shutdown()
 def test_launch_return_sends_once_and_waits_for_new_context(self):
  s,b,d=f.FullTransitionTests().make();original=d.call;d.shutdown=lambda:None
  try:
   def call(iface,method,sig,args,**kw):
    original(iface,method,sig,args,**kw)
    if method=='NotifyKeyboardKeysym' and args[-1]==1:b.value.update(window_id='launched-app',epoch=11)
   d.call=call
   args={'window_observation_id':s.window_record['id'],'focus_transition':True,'await_context_change':True,'action':{'type':'keys','keys':['Return']}}
   request={'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':args}}
   response=s.fence_response(request,s.handle(request))
   self.assertFalse(response['result'].get('isError',False));self.assertEqual(s.window_record['context']['window_id'],'launched-app')
   self.assertEqual(sum(e[1]=='NotifyKeyboardKeysym' and e[-1][-1]==1 for e in d.events),1)
  finally:s.shutdown()
 def test_publication_deadline_never_publishes_late_image(self):
  s,b=self.make()
  try:
   content=s.capture_result(('active',),transition_settle=True)
   s.window_record['publication_deadline']=time.monotonic()-1
   response=s.fence_response({'id':1,'params':{'name':'desktop_action'}},{'id':1,'result':{'content':content}})
   self.assertTrue(response['result']['isError']);self.assertFalse(any(c['type']=='image' for c in response['result']['content']))
  finally:s.shutdown()
 def test_native_failure_during_wait_cancels_without_input(self):
  s,b=self.make();original=b.context
  try:
   def context():s.invalidate(warning='native');return original()
   b.context=context
   with self.assertRaises(RuntimeError):s.capture_result(('active',),transition_settle=True,transition_origin=('old',),transition_deadline=time.monotonic()+1)
   self.assertEqual(s.backend.actions,0);self.assertEqual(s.status()['closure_reason'],'native-observer-fault')
  finally:s.shutdown()
 def test_deadline_rechecked_after_both_publication_context_queries(self):
  for slow_query in (1,2):
   s,b=self.make()
   try:
    content=s.capture_result(('active',),transition_settle=True);original=b.context;calls=[]
    s.window_record['publication_deadline']=time.monotonic()+.01
    def context():
     calls.append(1)
     if len(calls)==slow_query:time.sleep(.02)
     return original()
    b.context=context
    response=s.fence_response({'id':1,'params':{'name':'desktop_action'}},{'id':1,'result':{'content':content}})
    self.assertTrue(response['result']['isError']);self.assertFalse(any(c['type']=='image' for c in response['result']['content']))
   finally:s.shutdown()
