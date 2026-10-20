"""Monitor relocation admission and modifier fences; no desktop operations."""
import copy,unittest
from unittest.mock import patch
import test_monitor_mapping as mapping_tests
import test_window_guard as guards
import test_control
m=guards.g

class MonitorWindowMoveTests(unittest.TestCase):
 def mapping(self):
  state=mapping_tests.state(scale=1.,origin=(0,0),size=(1000,800))
  identity=('second','v','p','s')
  state[1].append([identity,[['active',1000,800,60.,1.,[1.],{'is-current':True}]],{}])
  state[2].append([1000,0,1.,0,False,[identity],{}])
  bus=mapping_tests.Bus(state)
  return mapping_tests.m.MonitorMapping(bus,{'position':(0,0),'size':(1000,800)}),bus
 def context(self):return {'available':True,'window_id':'source','epoch':1,'kind':'window','rect':[1100,100,500,400]}
 def test_two_monitor_direction_and_destination(self):
  mapping,bus=self.mapping();self.assertEqual(mapping.window_move_direction(self.context(),'Left'),(0,0,1000,800))
  for direction in ('Right','Up','Down'):
   with self.assertRaises(RuntimeError):mapping.window_move_direction(self.context(),direction)
 def test_source_shared_straddling_and_layout_change_refused(self):
  for rect in ([100,100,500,400],[900,100,500,400],[1100,100,0,400]):
   mapping,bus=self.mapping();context=self.context();context['rect']=rect
   with self.assertRaises(RuntimeError):mapping.window_move_direction(context,'Left')
  mapping,bus=self.mapping();bus.value[0]+=1
  with self.assertRaises(RuntimeError):mapping.window_move_direction(self.context(),'Left')
 def test_strict_chord_and_arrival_identity_geometry(self):
  for direction in ('Left','Right','Up','Down'):self.assertEqual(m.validate_monitor_move({'type':'keys','keys':['Super','Shift',direction]}),direction)
  for action in ({'type':'keys','keys':['Super','Left']},{'type':'keys','keys':['Shift','Super','Left']},{'type':'keys','keys':['Super','Shift','Left'],'focus':{}},{'type':'sequence','steps':[]}):
   with self.assertRaises(ValueError):m.validate_monitor_move(action)
  context=self.context()
  for changes in ({},{'window_id':'other','rect':[0,0,500,400]},{'rect':[900,0,500,400]},{'kind':'overview','rect':[0,0,500,400]}):
   value=dict(context,**changes)
   with self.assertRaises(RuntimeError):m.validate_monitor_arrival(value,'source',(0,0,1000,800))
  context['rect']=[0,0,500,400];m.validate_monitor_arrival(context,'source',(0,0,1000,800))
 def test_modifiers_fenced_until_arrow_and_cancellation_releases(self):
  for fail_at in (None,'Super','Shift'):
   d=test_control.Tests.backend(self);bridge=guards.Bridge()
   symbols={'Super':0xffeb,'Shift':0xffe1,'Left':0xff51};d.keysym=lambda key:symbols[key]
   d.window_guard=m.WindowGuard(bridge,bridge.context(),d.cancelled.set)
   d.window_transition=True;d.transition_activation_key=symbols['Left'];activated=[]
   d.begin_transition=lambda:activated.append(len(d.events))
   original=d.call
   def call(iface,method,sig,args,**kw):
    result=original(iface,method,sig,args,**kw)
    if fail_at and method=='NotifyKeyboardKeysym' and args[-1]==1 and args[-2]==symbols[fail_at]:bridge.value['epoch']+=1
    return result
   d.call=call
   if fail_at:
    with self.assertRaises(RuntimeError):d.action({'type':'keys','keys':['Super','Shift','Left']})
    self.assertEqual(activated,[]);self.assertFalse(any(e[3][-2]==symbols['Left'] and e[3][-1]==1 for e in d.events));self.assertEqual(d.held,[])
   else:
    d.action({'type':'keys','keys':['Super','Shift','Left']});self.assertEqual(activated,[2]);self.assertEqual(d.held,[])

 def test_server_no_arrival_or_other_window_never_publishes_image(self):
  for arrived in (False,True,'other','topology'):
   server,bridge=guards.WindowServerTests().make()
   source=self.context();bridge.value=copy.deepcopy(source);server.window_record['context']=copy.deepcopy(source)
   mapping,bus=self.mapping();server.backend.monitor_mapping=mapping;server.backend.mapping_guard=mapping.check
   server.backend.keysym=lambda key:1;server.window_guard_module=lambda:m
   def action(value):
    bridge.value['epoch']+=1
    if arrived:bridge.value['rect']=[100,100,500,400]
    if arrived=='other':bridge.value['window_id']='wrong-window'
   server.backend.action=action
   if arrived=='topology':
    original_capture=server.backend.capture
    def changed_capture():
     image=original_capture();bus.value[0]+=1;return image
    server.backend.capture=changed_capture
   with patch.object(m,'monitor_shortcut_configured',return_value=None):
    response=server.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'window_observation_id':server.window_record['id'],'focus_transition':True,'window_move_to_shared':True,'action':{'type':'keys','keys':['Super','Shift','Left']}}}})
   contents=response['result']['content']
   self.assertEqual(any(item['type']=='image' for item in contents),arrived is True)
   self.assertEqual(bool(response['result'].get('isError')),arrived is not True)
