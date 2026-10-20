"""Dedicated normalize-before-move fixtures; no window or settings mutation."""
import copy,unittest
from unittest.mock import patch
import test_monitor_window_move as relocation
import test_window_guard as guards
import test_control
m=guards.g

class NormalizeWindowTests(unittest.TestCase):
 def mapping(self):return relocation.MonitorWindowMoveTests().mapping()
 def context(self):return {'available':True,'window_id':'source','epoch':1,'kind':'window','rect':[1100,500,500,500]}
 def test_partial_source_admitted_only_for_normalize_not_move(self):
  mapping,bus=self.mapping();context=self.context()
  self.assertEqual(mapping.window_normalize_source(context),(1000,0,1000,800))
  with self.assertRaises(RuntimeError):mapping.window_move_direction(context,'Left')
  for changes in ({'rect':[900,100,500,400]},{'rect':[1100,600,500,500]},{'kind':'overview'},{'available':False},{'rect':[100,0,500,400]},{'rect':[1100,100,500,400]}):
   with self.subTest(changes=changes),self.assertRaises(RuntimeError):mapping.window_normalize_source(dict(context,**changes))
  bus.value[0]+=1
  with self.assertRaises(RuntimeError):mapping.window_normalize_source(context)
  original,bus=self.mapping();other=relocation.mapping_tests.m.MonitorMapping(bus,{'position':(1000,0),'size':(1000,800)})
  context['rect']=[100,100,1200,400]
  with self.assertRaises(RuntimeError):other.window_normalize_source(context)
 def test_only_configured_normalize_toggle_chord(self):
  m.validate_normalize_for_move({'type':'keys','keys':['Alt','F10']})
  for action in ({'type':'keys','keys':['Super','Up']},{'type':'keys','keys':['Super','Shift','Up']},{'type':'keys','keys':['Super','Up'],'focus':{}},{'type':'sequence','steps':[]}):
   with self.assertRaises(ValueError):m.validate_normalize_for_move(action)
 def test_modifier_cancellation_never_sends_f10_and_releases(self):
  d=test_control.Tests.backend(self);bridge=guards.Bridge();symbols={'Alt':0xffe9,'F10':0xffc7}
  d.keysym=lambda key:symbols[key];d.window_guard=m.WindowGuard(bridge,bridge.context(),d.cancelled.set)
  d.window_transition=True;d.transition_activation_key=symbols['F10'];activated=[];d.begin_transition=lambda:activated.append(True)
  original=d.call
  def call(iface,method,sig,args,**kw):
   result=original(iface,method,sig,args,**kw)
   if method=='NotifyKeyboardKeysym' and args[-1]==1:bridge.value['epoch']+=1
   return result
  d.call=call
  with self.assertRaises(RuntimeError):d.action({'type':'keys','keys':['Alt','F10']})
  self.assertFalse(activated);self.assertEqual(d.held,[])
  self.assertFalse(any(e[3][-2]==symbols['F10'] and e[3][-1]==1 for e in d.events))

 def test_changed_binding_at_activation_never_sends_f10(self):
  d=test_control.Tests.backend(self);symbols={'Alt':0xffe9,'F10':0xffc7};d.keysym=lambda key:symbols[key]
  d.window_transition=True;d.transition_activation_key=symbols['F10']
  def changed():raise RuntimeError('Binding changed')
  d.begin_transition=changed
  with self.assertRaisesRegex(RuntimeError,'Binding changed'):d.action({'type':'keys','keys':['Alt','F10']})
  self.assertEqual(d.held,[])
  self.assertFalse(any(e[3][-2]==symbols['F10'] and e[3][-1]==1 for e in d.events))
 def test_server_requires_same_window_contained_on_source_noop_protected_layout_fail(self):
  for result in ('success','noop','wrong-window','protected','topology'):
   server,bridge=guards.WindowServerTests().make();source=self.context();bridge.value=copy.deepcopy(source);server.window_record['context']=copy.deepcopy(source)
   mapping,bus=self.mapping();server.backend.monitor_mapping=mapping;server.backend.mapping_guard=mapping.check;server.backend.keysym=lambda key:1
   server.window_guard_module=lambda:m
   def action(value):
    bridge.value['epoch']+=1
    if result!='noop':bridge.value['rect']=[1000,0,1000,800]
    if result=='wrong-window':bridge.value['window_id']='wrong'
    if result=='protected':bridge.value['available']=False
    if result=='topology':bus.value[0]+=1
   server.backend.action=action
   with patch.object(m,'normalize_shortcut_configured',return_value=None):
    response=server.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'window_observation_id':server.window_record['id'],'focus_transition':True,'window_normalize_for_move':True,'action':{'type':'keys','keys':['Alt','F10']}}}})
   with self.subTest(result=result):
    self.assertEqual(any(item['type']=='image' for item in response['result']['content']),result=='success')
    self.assertEqual(bool(response['result'].get('isError')),result!='success')
    self.assertIsNone(server.backend.transition_activation_key)
