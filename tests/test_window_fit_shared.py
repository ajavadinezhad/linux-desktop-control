"""Oversized selected-monitor fit admission; fake geometry, no GUI calls."""
import copy,unittest
from unittest.mock import patch
import test_monitor_mapping as geometry
import test_window_guard as guards
import test_window_normalize_for_move as normalize
m=guards.g
class FitSharedTests(unittest.TestCase):
 def mapping(self):
  state=geometry.state(scale=1.,origin=(0,240),size=(1920,1200));identity=('second','v','p','s')
  state[1].append([identity,[['active',3440,1440,60.,1.,[1.],{'is-current':True}]],{}])
  state[2].append([1920,0,1.,0,False,[identity],{}])
  bus=geometry.Bus(state);return geometry.m.MonitorMapping(bus,{'position':(0,240),'size':(1920,1200)}),bus
 def context(self):return {'available':True,'window_id':'firefox-fixture','epoch':1,'kind':'window','rect':[-323,276,2872,1037]}
 def test_actual_frame_admitted_without_origin_inside(self):
  mapping,bus=self.mapping();self.assertEqual(mapping.window_fit_shared(self.context()),(0,240,1920,1200))
  with self.assertRaises(RuntimeError):mapping.window_normalize_source(self.context())
 def test_center_titlebar_tie_already_fit_protected_and_layout_refused(self):
  for change in ({'rect':[1500,276,2872,1037]},{'rect':[-323,100,2872,1300]},{'rect':[-200,276,4040,1000]},{'rect':[0,240,1920,1200]},{'available':False},{'kind':'overview'}):
   mapping,bus=self.mapping()
   with self.subTest(change=change),self.assertRaises(RuntimeError):mapping.window_fit_shared(dict(self.context(),**change))
  mapping,bus=self.mapping();bus.value[0]+=1
  with self.assertRaises(RuntimeError):mapping.window_fit_shared(self.context())
 def test_server_full_arrival_only_and_config_topology_fail_closed(self):
  for outcome in ('success','noop','wrong','protected','topology','config'):
   server,bridge=guards.WindowServerTests().make();source=self.context();bridge.value=copy.deepcopy(source);server.window_record['context']=copy.deepcopy(source)
   mapping,bus=self.mapping();server.backend.monitor_mapping=mapping;server.backend.mapping_guard=mapping.check;server.backend.keysym=lambda key:1;server.window_guard_module=lambda:m;actions=[]
   def action(value):
    actions.append(value);bridge.value['epoch']+=1
    if outcome!='noop':bridge.value['rect']=[0,240,1920,1100]
    if outcome=='wrong':bridge.value['window_id']='other'
    if outcome=='protected':bridge.value['available']=False
    if outcome=='topology':bus.value[0]+=1
   server.backend.action=action
   with patch.object(m,'normalize_shortcut_configured',side_effect=RuntimeError('binding changed') if outcome=='config' else None):
    response=server.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'window_observation_id':server.window_record['id'],'focus_transition':True,'window_fit_shared':True,'action':{'type':'keys','keys':['Alt','F10']}}}})
   with self.subTest(outcome=outcome):
    self.assertEqual(any(item['type']=='image' for item in response['result']['content']),outcome=='success')
    self.assertEqual(bool(response['result'].get('isError')),outcome!='success')
    self.assertIsNone(server.backend.transition_activation_key)
    if outcome=='config':self.assertFalse(actions)
 def test_mutually_exclusive_flags_refused_without_action(self):
  server,bridge=guards.WindowServerTests().make();actions=[];server.backend.action=actions.append
  response=server.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'window_observation_id':server.window_record['id'],'focus_transition':True,'window_fit_shared':True,'window_normalize_for_move':True,'action':{'type':'keys','keys':['Alt','F10']}}}})
  self.assertTrue(response['result']['isError']);self.assertFalse(actions)
 def test_modifier_loss_and_changed_binding_release_without_f10(self):
  # The fit path uses the same exact chord and final-F10 activation mechanism.
  fixture=normalize.NormalizeWindowTests()
  fixture.test_modifier_cancellation_never_sends_f10_and_releases()
  fixture.test_changed_binding_at_activation_never_sends_f10()
