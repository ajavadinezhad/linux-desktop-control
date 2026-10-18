import importlib.util,json,pathlib,threading,time,unittest,copy
import test_control
from test_control import m,Fake
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('window_guard_test',ROOT/'plugins/linux-desktop-control/window_guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
def context():return {'available':True,'window_id':'window-1','epoch':10,'kind':'window','rect':[0,0,1000,800]}
class Bridge:
 def __init__(self):self.value=context();self.armed=None;self.closed=False
 def context(self):return copy.deepcopy(self.value)
 def close(self):self.closed=True
class WindowGuardTests(unittest.TestCase):
 def test_switch_back_geometry_and_system_ui_invalidate_without_focus_reclaim(self):
  changes=[{'window_id':'window-2','epoch':11},{'epoch':12},{'rect':[1,0,1000,800]},{'rect':[0,1,1000,800]},{'rect':[0,0,1001,800]},{'rect':[0,0,1000,801]},{'available':False},{'window_id':'shell-overview','kind':'overview','epoch':11}]
  for change in changes:
   with self.subTest(change=change):
    b=Bridge();cancelled=threading.Event();w=g.WindowGuard(b,b.context(),cancelled.set);b.value.update(change)
    with self.assertRaisesRegex(RuntimeError,'Foreground'):w.check()
    self.assertTrue(cancelled.is_set());self.assertTrue(w.failed)
 def test_invalid_context_and_cross_window_coordinates_refused(self):
  for change in [{'epoch':True},{'rect':[0,0,float('nan'),100]},{'available':False}]:
   c=context();c.update(change)
   with self.assertRaises(RuntimeError):g.WindowGuard(Bridge(),c,lambda:None)
  b=Bridge();w=g.WindowGuard(b,b.context(),lambda:None)
  with self.assertRaises(ValueError):w.validate_points({'type':'drag','path':[[10,10],[1200,10]]})
  w.validate_points({'type':'click','x':-1280+10,'y':10},(1280,0))
 def backend(self):
  d=test_control.Tests.backend(self);d.keysym=lambda key:ord(key[0]);b=Bridge();d.window_guard=g.WindowGuard(b,b.context(),d.cancelled.set);return d,b
 def test_alt_tab_mid_move_typing_drag_and_scroll_cancels_remaining_events_and_releases(self):
  cases=[('move',{'type':'sequence','steps':[{'type':'click','x':50,'y':50},{'type':'move','x':400,'y':400,'seconds':.15},{'type':'scroll','x':400,'y':400,'dy':1}]},lambda method,args:method=='NotifyPointerMotionAbsolute' and args[-1]>60),('typing',{'type':'text','focus':{'x':50,'y':50},'text':'abc'},lambda method,args:method=='NotifyKeyboardKeysym' and args[-1]==1),('drag',{'type':'drag','path':[[50,50],[60,60],[70,70]]},lambda method,args:method=='NotifyPointerButton' and args[-1]==1),('scroll',{'type':'scroll','x':50,'y':50,'dy':5},lambda method,args:method=='NotifyPointerMotionAbsolute')]
  for name,action,trigger in cases:
   with self.subTest(name=name):
    d,b=self.backend();original=d.call;index=[]
    def call(iface,method,sig,args,**kw):
     original(iface,method,sig,args,**kw)
     if not index and trigger(method,args):index.append(len(d.events));b.value.update(window_id='other',epoch=11)
    d.call=call
    with self.assertRaises(RuntimeError):d.action(action)
    self.assertEqual(d.held,[]);self.assertTrue(d.cancelled.is_set())
    after=d.events[index[0]:]
    self.assertTrue(all(e[1] in ('NotifyPointerButton','NotifyKeyboardKeysym') and e[3][-1]==0 for e in after))
 def test_context_signal_interrupts_long_wait_and_invalid_signal_cannot_restore_guard(self):
  d,b=self.backend();threading.Timer(.02,lambda:d.window_guard.changed(11)).start();start=time.monotonic()
  with self.assertRaises(RuntimeError):d.wait_interruptibly(5)
  self.assertLess(time.monotonic()-start,.5);self.assertTrue(d.cancelled.is_set())
  d.cancelled.clear();b.value=context()
  with self.assertRaises(RuntimeError):d.window_guard.check()
 def test_deliberate_transition_cannot_hide_text_drag_scroll_or_batch(self):
  for action in [{'type':'text','text':'x'},{'type':'drag','path':[[1,1],[2,2]]},{'type':'scroll','x':1,'y':1},{'type':'sequence','steps':[{'type':'click','x':1,'y':1}]},{'type':'keys','keys':['Alt','Tab']},{'type':'click','x':1,'y':1,'count':2}]:
   with self.assertRaises(ValueError):g.validate_transition(action)
  for action in [{'type':'click','x':1,'y':1},{'type':'keys','keys':['Super']},{'type':'keys','keys':['Return']}]:g.validate_transition(action)
class WindowBackend(Fake):
 requires_window_guard=True
 def __init__(self):super().__init__();self.actions=0
 def action(self,a):self.actions+=1;self.window_guard.check();self.transaction_info={'input_events_attempted':1};self.bridge.value.update(window_id='foreign',epoch=11);self.window_guard.check()
class WindowServerTests(unittest.TestCase):
 def make(self):
  b=Bridge();s=m.Server(WindowBackend);s.indicator=b;s.call('desktop_start',{});s.backend.bridge=b;return s,b
 def test_mid_batch_loss_closes_and_invalidates_queue_without_retry(self):
  s,b=self.make();token=s.window_record['id'];old=s.generation
  result=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'window_observation_id':token,'action':{'type':'click','x':2,'y':2}}}})
  self.assertTrue(result['result']['isError']);self.assertFalse(s.status()['active']);self.assertTrue(b.closed);self.assertGreater(s.generation,old);self.assertEqual(s.backend.actions,1)
  s.request_epoch=old
  with self.assertRaises(RuntimeError):s.call('desktop_start',{})
 def test_stale_observation_after_alt_tab_back_refuses_before_first_event(self):
  s,b=self.make();token=s.window_record['id'];b.value['epoch']=12
  result=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'window_observation_id':token,'action':{'type':'click','x':2,'y':2}}}})
  self.assertTrue(result['result']['isError']);self.assertEqual(s.backend.actions,0);self.assertFalse(s.status()['active'])
 def test_focus_change_during_capture_never_publishes_image(self):
  s,b=self.make();original=s.backend.capture
  def capture():png=original();b.value['epoch']+=1;return png
  s.backend.capture=capture
  result=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_observe'}})
  self.assertTrue(result['result']['isError']);self.assertFalse(any(c['type']=='image' for c in result['result']['content']));self.assertFalse(s.status()['active'])
 def test_locked_or_modal_context_prevents_capture_and_input(self):
  s,b=self.make();called=[];s.backend.capture=lambda:called.append(True);b.value={'available':False,'reason':'system-ui'}
  result=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_observe'}})
  self.assertTrue(result['result']['isError']);self.assertEqual(called,[]);self.assertFalse(s.status()['active'])

class RevokedInputTests(unittest.TestCase):
 def test_portal_revocation_mid_drag_clears_held_state_without_later_motion(self):
  d=test_control.Tests.backend(self);original=d.call
  def call(iface,method,sig,args,**kw):
   original(iface,method,sig,args,**kw)
   if method=='NotifyPointerButton' and args[-1]==1:d.portal_closed=True;d.cancelled.set()
  d.call=call
  with self.assertRaises(RuntimeError):d.action({'type':'drag','path':[[50,50],[100,100],[150,150]]})
  self.assertEqual(d.held,[]);self.assertEqual(len(d.events),2)

class ObservationRaceTests(unittest.TestCase):
 def test_change_after_last_event_before_capture_is_not_published(self):
  helper=WindowServerTests();s,b=helper.make();token=s.window_record['id'];executed=[]
  s.backend.action=lambda action:executed.append(True)
  original=s.capture_result
  def capture(allowed,expected_window=None):
   if expected_window is not None:b.value['epoch']+=1
   return original(allowed,expected_window)
  s.capture_result=capture
  result=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'window_observation_id':token,'action':{'type':'click','x':2,'y':2}}}})
  self.assertEqual(executed,[True]);self.assertTrue(result['result']['isError']);self.assertFalse(any(c['type']=='image' for c in result['result']['content']));self.assertFalse(s.status()['active'])
 def test_missing_new_observer_is_rejected_before_personal_consent(self):
  class Backend(Fake):
   requires_window_guard=True
   def __init__(self):super().__init__();self.starts=0
   def start(self):self.starts+=1;super().start()
  s=m.Server(Backend)
  def unavailable():raise RuntimeError('updated observer unavailable')
  s.preflight_context=unavailable
  result=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_start'}})
  self.assertTrue(result['result']['isError']);self.assertEqual(s.backend.starts,0);self.assertFalse(s.status()['active'])

class PublicationWindowTests(unittest.TestCase):
 def test_change_after_capture_before_publication_discards_frame_and_token(self):
  s,b=WindowServerTests().make();content=s.call('desktop_observe',{});b.value['epoch']+=1
  result=s.fence_response({'id':1,'params':{'name':'desktop_observe'}},{'id':1,'result':{'content':content}})
  self.assertTrue(result['result']['isError']);self.assertFalse(any(c['type']=='image' for c in result['result']['content']));self.assertIsNone(s.window_record);self.assertFalse(s.status()['active'])

 def test_post_action_focus_race_preserves_uncertain_effects_without_observation_token(self):
  s,b=WindowServerTests().make();token=s.window_record['id']
  def action(_):s.backend.transaction_info={'input_events_attempted':1,'completed_steps':1}
  s.backend.action=action;content=s.call('desktop_action',{'window_observation_id':token,'action':{'type':'click','x':2,'y':2}})
  b.value['epoch']+=1
  result=s.fence_response({'id':1,'params':{'name':'desktop_action'}},{'id':1,'result':{'content':content}})
  self.assertTrue(result['result']['isError']);self.assertTrue(s.recovery.inspection_required);self.assertIsNone(s.recovery.observation_id);self.assertEqual(s.recovery.last['outcome'],'effects_uncertain');self.assertFalse(s.status()['active'])
