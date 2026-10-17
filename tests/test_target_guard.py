import importlib.util,json,pathlib,time,threading,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from test_control import m
import test_control
from test_recovery import Partial
p=pathlib.Path(m.__file__).with_name('target_guard.py');spec=importlib.util.spec_from_file_location('target_test',p);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
A=NS(DEFunct='defunct',DEFUNCT='defunct',VISIBLE='visible',SHOWING='showing',ACTIVE='active',FOCUSED='focused',EDITABLE='editable')
TEXT=NS(value_nick='text');PASSWORD=NS(value_nick='password-text')
class States:
 def __init__(self,values):self.values=values
 def contains(self,value):return value in self.values
class Node:
 def __init__(self,path,states,children=()):
  self.path=path;self.app=NS(bus_name=':1.44');self.values=set(states);self.children=list(children);self.role=TEXT;self.bounds=[0,0,100,20];self.focuses=0
 def get_process_id(self):return 42
 def get_role(self):return self.role
 def clear_cache_single(self):pass
 def get_state_set(self):return States(self.values)
 def get_component_iface(self):return self
 def get_extents(self,coord):return NS(**dict(zip(('x','y','width','height'),self.bounds)))
 def grab_focus(self):self.focuses+=1;self.values.add(A.FOCUSED);return True
 def get_child_count(self):return len(self.children)
 def get_child_at_index(self,i):return self.children[i]
class ProviderTests(unittest.TestCase):
 def make(self):
  node=Node('/field',(A.VISIBLE,A.SHOWING,A.FOCUSED,A.EDITABLE));win=Node('/window',(A.VISIBLE,A.SHOWING,A.ACTIVE),(node,));app=Node('/app',(),(win,));root=Node('/root',(),(app,));api=NS(StateType=A,Role=NS(PASSWORD_TEXT=PASSWORD),CoordType=NS(WINDOW=1),get_desktop=lambda i:root)
  provider=g.AtspiProvider.__new__(g.AtspiProvider);provider.api=api;return provider,win,node
 def test_snapshot_uses_only_identity_and_states_no_values(self):
  provider,w,n=self.make();t=provider.snapshot(lambda:None);self.assertEqual(t.identity,(':1.44','/field','/window',42));self.assertEqual(t.describe()['role'],'text');self.assertFalse(t.describe()['text_values_read']);t.acquire();self.assertEqual(n.focuses,0);n.values.discard(A.FOCUSED);t.acquire();self.assertEqual(n.focuses,1)
 def test_already_focused_control_does_not_require_optional_grab_focus(self):
  p,w,n=self.make();t=p.snapshot(lambda:None)
  def unsupported():raise RuntimeError('org.freedesktop.DBus.Error.NotSupported')
  n.grab_focus=unsupported;t.acquire();t.check()
  n.values.discard(A.FOCUSED)
  with self.assertRaisesRegex(RuntimeError,'NotSupported'):t.acquire()
 def test_vanished_dialog_fails_before_focus(self):
  p,w,n=self.make();t=p.snapshot(lambda:None);w.values.remove(A.SHOWING)
  with self.assertRaisesRegex(g.TargetUnavailable,'vanished'):t.acquire()
  self.assertEqual(n.focuses,0)
 def test_same_object_becoming_password_or_noneditable_fails(self):
  for change in ('password','editable'):
   p,w,n=self.make();t=p.snapshot(lambda:None)
   if change=='password':n.role=PASSWORD
   else:n.values.remove(A.EDITABLE)
   with self.assertRaisesRegex(g.TargetUnavailable,'protected'):t.check()
 def test_focus_window_and_geometry_changes_fail(self):
  for change in ('focus','active','geometry'):
   p,w,n=self.make();t=p.snapshot(lambda:None)
   if change=='focus':n.values.remove(A.FOCUSED)
   elif change=='active':w.values.remove(A.ACTIVE)
   else:n.bounds[0]=2
   with self.assertRaises(g.TargetUnavailable):t.check()
 def test_password_snapshot_and_ambiguous_active_window_fail(self):
  p,w,n=self.make();n.role=PASSWORD
  with self.assertRaisesRegex(g.TargetUnavailable,'Password'):p.snapshot(lambda:None)
  p,w,n=self.make();root=p.api.get_desktop(0);root.children[0].children.append(Node('/other',(A.VISIBLE,A.SHOWING,A.ACTIVE),(Node('/other-field',(A.VISIBLE,A.SHOWING,A.FOCUSED,A.EDITABLE)),)))
  with self.assertRaisesRegex(g.TargetUnavailable,'unique focused'):p.snapshot(lambda:None)
 def test_multiple_active_windows_resolve_only_unique_focused_editor(self):
  p,w,n=self.make();other=Node('/other',(A.VISIBLE,A.SHOWING,A.ACTIVE))
  p.api.get_desktop(0).children[0].children.insert(0,other)
  self.assertEqual(p.snapshot(lambda:None).identity[1],'/field')
 def test_focused_protected_control_in_other_active_window_refuses(self):
  p,w,n=self.make();field=Node('/password',(A.VISIBLE,A.SHOWING,A.FOCUSED));field.role=PASSWORD
  p.api.get_desktop(0).children[0].children.append(Node('/other',(A.VISIBLE,A.SHOWING,A.ACTIVE),(field,)))
  with self.assertRaisesRegex(g.TargetUnavailable,'Password'):p.snapshot(lambda:None)
 def test_hidden_or_inactive_window_cannot_supply_target(self):
  for state in ((A.VISIBLE,A.SHOWING),(A.ACTIVE,A.VISIBLE),(A.DEFUNCT,A.VISIBLE,A.SHOWING,A.ACTIVE)):
   p,w,n=self.make();n.values.discard(A.FOCUSED)
   other=Node('/other',state,(Node('/other-field',(A.VISIBLE,A.SHOWING,A.FOCUSED,A.EDITABLE)),))
   p.api.get_desktop(0).children[0].children.append(other)
   with self.assertRaisesRegex(g.TargetUnavailable,'unique focused'):p.snapshot(lambda:None)
 def test_window_enumeration_never_silently_truncates(self):
  p,w,n=self.make();app=p.api.get_desktop(0).children[0];app.children.extend(Node('/w'+str(i),()) for i in range(16))
  with self.assertRaisesRegex(g.TargetUnavailable,'Application windows'):p.snapshot(lambda:None)
 def test_negative_child_count_refused(self):
  p,w,n=self.make();p.api.get_desktop(0).get_child_count=lambda:-1
  with self.assertRaisesRegex(g.TargetUnavailable,'bounded'):p.snapshot(lambda:None)
 def test_inspection_rejects_reply_that_exceeds_deadline(self):
  p,w,n=self.make();clock=[0.0];old=p.api.get_desktop
  def late(i):clock[0]=2;return old(i)
  p.api.get_desktop=late
  with patch.object(g.time,'monotonic',lambda:clock[0]):
   with self.assertRaisesRegex(g.TargetUnavailable,'budget'):p.snapshot(lambda:None)
 def test_deadline_and_pause_checked_after_provider_reply(self):
  p,w,n=self.make();t=p.snapshot(lambda:None);t.deadline=time.monotonic()-1
  with self.assertRaisesRegex(g.TargetUnavailable,'budget'):t.call(lambda:True)
  paused=[False]
  def gate():
   if paused[0]:raise RuntimeError('paused')
  t.gate=gate;t.deadline=time.monotonic()+1
  def reply():paused[0]=True;return True
  with self.assertRaisesRegex(RuntimeError,'paused'):t.call(reply)

class TargetBridgeTests(unittest.TestCase):
 def make(self):
  s=m.Server(Partial);s.call('desktop_start',{});p,w,n=ProviderTests().make();s.target_provider=p;return s,w,n
 def observe(self,s):return json.loads(s.call('desktop_observe',{'inspect_target':True})[0]['text'])
 def test_single_use_token_rejected_after_any_action_and_pause(self):
  s,w,n=self.make();meta=self.observe(s);token=meta['target']['target_id'];self.assertEqual(len(token),32)
  s.call('desktop_action',{'target_id':token,'action':{'type':'click','x':1,'y':1}})
  with self.assertRaisesRegex(RuntimeError,'expired'):s.call('desktop_action',{'target_id':token,'action':{'type':'click','x':1,'y':1}})
  self.assertEqual(s.recovery.last['outcome'],'failed_before_input');self.assertEqual(s.backend.actions,1)
  self.observe(s);s.begin_boundary('desktop_pause',{'reason':'Review','task_summary':'Scratch'});self.assertIsNone(s.target_record)
 def test_unavailable_is_explicit_and_no_guard_fallback(self):
  s,w,n=self.make();n.values.remove(A.FOCUSED);meta=self.observe(s);self.assertFalse(meta['target']['available']);self.assertTrue(meta['target']['no_fallback']);self.assertIsNone(s.target_record)
  with self.assertRaises(RuntimeError):s.call('desktop_action',{'target_id':'x'*32,'action':{'type':'click','x':1,'y':1}})
  self.assertEqual(s.backend.actions,0)
 def test_late_paused_traversal_and_suppressed_image_cannot_publish_token(self):
  s,w,n=self.make()
  class Late:
   def snapshot(self,gate):
    s.begin_boundary('desktop_pause',{'reason':'Review','task_summary':'Scratch'});gate()
  s.target_provider=Late()
  with self.assertRaises(RuntimeError):self.observe(s)
  self.assertIsNone(s.target_record)
  s,w,n=self.make();content=s.call('desktop_observe',{'inspect_target':True});self.assertIsNotNone(s.target_record)
  s.cancel_token=threading.Event();s.cancel_token.set();response=s.fence_response({'params':{'name':'desktop_observe'}},{'result':{'content':content}})
  self.assertTrue(response['result']['isError']);self.assertIsNone(s.target_record)
 def test_plain_observation_invalidates_target_and_expiry_blocks_input(self):
  s,w,n=self.make();self.observe(s);s.call('desktop_observe',{});self.assertIsNone(s.target_record)
  token=self.observe(s)['target']['target_id'];s.target_record['issued']-=61
  with self.assertRaisesRegex(RuntimeError,'expired'):s.call('desktop_action',{'target_id':token,'action':{'type':'click','x':1,'y':1}})
  self.assertEqual(s.backend.actions,0)

class DispatchTests(unittest.TestCase):
 def make(self):
  d=test_control.Tests().backend();d.pause=lambda seconds:None;d.keysym=lambda k:ord(k[0]);p,w,n=ProviderTests().make();d.target_guard=p.snapshot(d.check);return d,w,n
 def test_guarded_keyboard_can_acquire_exact_control_without_pointer(self):
  d,w,n=self.make();d.action({'type':'text','text':'ok'});self.assertEqual(n.focuses,0);self.assertTrue(d.events);self.assertTrue(all(e[1]=='NotifyKeyboardKeysym' for e in d.events))
 def test_focus_loss_during_text_blocks_next_press_and_releases_held(self):
  d,w,n=self.make();original=d.call
  def call(interface,method,sig,args,**kw):
   original(interface,method,sig,args,**kw)
   if method=='NotifyKeyboardKeysym' and args[-1]==1:n.values.discard(A.FOCUSED)
  d.call=call
  with self.assertRaisesRegex(g.TargetUnavailable,'focus'):d.action({'type':'text','text':'ab'})
  presses=[e for e in d.events if e[1]=='NotifyKeyboardKeysym' and e[3][-1]==1]
  self.assertEqual(len(presses),1);self.assertFalse(d.held)
 def test_dialog_vanishes_after_focus_click_no_keys_dispatched(self):
  d,w,n=self.make();original=d._primitive
  def primitive(a):
   original(a)
   if a['type']=='click':w.values.discard(A.SHOWING)
  d._primitive=primitive
  with self.assertRaisesRegex(g.TargetUnavailable,'vanished'):d.action({'type':'text','focus':{'x':10,'y':10},'text':'never'})
  self.assertFalse(any(e[1]=='NotifyKeyboardKeysym' for e in d.events));self.assertFalse(d.held)
 def test_guarded_batch_limit_rejects_before_focus_click(self):
  d,w,n=self.make()
  with self.assertRaisesRegex(ValueError,'32characters'):d.action({'type':'text','focus':{'x':10,'y':10},'text':'x'*33})
  self.assertFalse(d.events)
 def test_slow_guard_honestly_bounds_partial_character_progress(self):
  d=test_control.Tests().backend();d.pause=lambda seconds:None;d.keysym=lambda k:ord(k[0]);clock=[0.0]
  class Slow:
   def live(self):pass
   def acquire(self):pass
   def check(self):clock[0]+=5.1
  d.target_guard=Slow()
  with patch.object(m.time,'monotonic',lambda:clock[0]):
   with self.assertRaisesRegex(RuntimeError,'15 seconds'):d.action({'type':'text','text':'abcd'})
  self.assertEqual(d.transaction_info['input_characters_completed'],1)
  self.assertEqual(len([e for e in d.events if e[1]=='NotifyKeyboardKeysym' and e[3][-1]==1]),1)
  self.assertFalse(d.held)
 def test_modals_require_new_observation_and_pointer_workflows_stay_separate(self):
  d,w,n=self.make();old=d._primitive
  def primitive(a):
   old(a)
   if a['type']=='keys':w.values.discard(A.ACTIVE)
  d._primitive=primitive
  with self.assertRaises(g.TargetUnavailable):d.action({'type':'sequence','steps':[{'type':'keys','keys':['x']},{'type':'text','text':'never'}]})
  d,w,n=self.make()
  with self.assertRaises(ValueError):d.action({'type':'scroll','x':1,'y':1,'dy':1})
  self.assertFalse(d.events)

class DirectTransportTests(unittest.TestCase):
 def test_direct_rpc_allowlist_excludes_text_values_names_and_cache(self):
  client=g.DirectClient.__new__(g.DirectClient);client.Gio=m.Gio;client.GLib=m.GLib;client.roles=lambda x:x
  class Bus:
   def __init__(self):self.calls=[]
   def is_closed(self):return False
   def call_sync(self,*args):
    self.calls.append(args)
    class Reply:
     def unpack(self):return (7,)
    return Reply()
  client.bus=Bus()
  for interface,method,signature,args in [('org.a11y.atspi.Text','GetText','(ii)',(0,-1)),('org.a11y.atspi.Value','GetCurrentValue','()',()),('org.a11y.atspi.Cache','GetItems','()',()),('org.freedesktop.DBus.Properties','Get','(ss)',(g.DirectNode.ACCESSIBLE,'Name'))]:
   with self.assertRaises(g.TargetUnavailable):client.call(':1.1','/field',interface,method,signature,args)
  self.assertEqual(client.bus.calls,[])
  self.assertEqual(client.call(':1.1','/field',g.DirectNode.ACCESSIBLE,'GetRole','()',()),(7,))
  self.assertEqual(client.bus.calls[0][-2],150)
 def test_accessibility_close_failure_does_not_retain_rpc_client(self):
  client=g.DirectClient.__new__(g.DirectClient);client.Gio=m.Gio
  class Bus:
   def is_closed(self):return False
   def close_sync(self,cancellable):raise RuntimeError('connection already shutting down')
  client.bus=Bus();self.assertFalse(client.close());self.assertIsNone(client.bus)
 def test_close_is_cancellable_within_bounded_budget(self):
  client=g.DirectClient.__new__(g.DirectClient);client.Gio=m.Gio;cancelled=threading.Event()
  class Bus:
   def is_closed(self):return False
   def close_sync(self,token):
    token.connect(lambda *args:cancelled.set())
    if not cancelled.wait(1):raise AssertionError('close did not receive cancellation')
    raise RuntimeError('cancelled')
  client.bus=Bus();started=time.monotonic();self.assertFalse(client.close());self.assertLess(time.monotonic()-started,.8);self.assertTrue(cancelled.is_set());self.assertIsNone(client.bus)
 def test_provider_cleanup_failure_preserves_closed_portal_and_disables_target(self):
  s=m.Server(Partial);s.call('desktop_start',{})
  class Provider:
   def close(self):raise RuntimeError('timed out')
  s.target_provider=Provider();s.call('desktop_stop',{})
  self.assertEqual(s.status()['control_state'],'stopped');self.assertFalse(s.status()['input_allowed']);self.assertIsNone(s.target_provider)
  self.assertIn('unconfirmed',s.status()['accessibility_cleanup_warning'])
 def test_state_bits_and_pause_close_connection_without_queries(self):
  state=g.DirectStates([1<<12,1<<8]);self.assertTrue(state.contains(12));self.assertTrue(state.contains(40));self.assertFalse(state.contains(39))
  s=m.Server(Partial);s.call('desktop_start',{});closed=[]
  class Provider:
   def close(self):closed.append(True)
   def snapshot(self,gate):raise AssertionError('must never inspect during pause')
  s.target_provider=Provider();s.call('desktop_pause',{'reason':'Review','task_summary':'Scratch'})
  self.assertEqual(closed,[True]);self.assertIsNone(s.target_provider)
  with self.assertRaises(RuntimeError):s.call('desktop_observe',{'inspect_target':True})

if __name__=='__main__':unittest.main()
