import json,unittest
from test_control import m
from test_handoff import Counting
from test_toolbar_bridge import bridge,Bus

class ToolbarSafetyTests(unittest.TestCase):
 def test_warning_after_failed_stop_stays_visible(self):
  for status in ({'cleanup_warning':'private error'},{'portal_closed_confirmed':False,'toolbar_session_ready':True}):
   view=bridge.toolbar_view(dict(control_state='stopped',**status))
   self.assertTrue(view['visible']);self.assertTrue(view['closure_warning']);self.assertFalse(view['can_continue'])
   self.assertNotIn('private',json.dumps(view))
 def test_consent_precedes_toolbar_and_capture(self):
  order=[]
  class Backend(Counting):
   def start(self):order.append('consent');super().start()
   def capture(self):order.append('capture');return super().capture()
  s=m.Server(Backend);s.prepare_toolbar=lambda:order.append('preflight')
  def show():
   self.assertTrue(s.toolbar_session_ready);self.assertEqual(s.state,'starting');order.append('toolbar')
  s.ensure_panel=show;s.call('desktop_start',{})
  self.assertEqual(order,['preflight','consent','toolbar','capture'])
 def test_missing_toolbar_does_not_open_permission(self):
  s=m.Server(Counting)
  def missing():raise RuntimeError('Enable after login')
  s.prepare_toolbar=missing
  with self.assertRaises(RuntimeError):s.call('desktop_start',{})
  self.assertEqual(s.backend.starts,0);self.assertEqual(s.state,'stopped');self.assertFalse(s.toolbar_session_ready)
 def test_human_toolbar_cannot_be_targeted_by_synthetic_input(self):
  s=m.Server(Counting);s.call('desktop_start',{})
  class Toolbar:
   def diagnostics(self):return {'visible':True,'rect':[900,650,350,45],'monitor_bounds':{'x':0,'y':0}}
  s.panel=Toolbar()
  for action in ({'type':'click','x':910,'y':660},{'type':'text','text':'no','focus':{'x':910,'y':660}},{'type':'drag','path':[[10,20],[910,660]]},{'type':'sequence','steps':[{'type':'click','x':910,'y':660}]}):
   with self.assertRaises(ValueError):s.call('desktop_action',{'action':action})
  self.assertEqual(s.backend.inputs,0)
 def test_hidden_toolbar_refuses_input(self):
  s=m.Server(Counting);s.call('desktop_start',{})
  class Toolbar:
   def diagnostics(self):return {'visible':False}
  s.panel=Toolbar()
  with self.assertRaises(RuntimeError):s.call('desktop_action',{'action':{'type':'click','x':1,'y':1}})
  self.assertEqual(s.backend.inputs,0)
 def test_toolbar_geometry_uses_monitor_offset(self):
  s=m.Server(Counting);s.call('desktop_start',{});s.backend.props={'position':(1280,0)}
  class Toolbar:
   def diagnostics(self):return {'visible':True,'rect':[2200,650,350,45],'monitor_bounds':{'x':1280,'y':0}}
  s.panel=Toolbar()
  with self.assertRaises(ValueError):s.protect_toolbar({'type':'click','x':930,'y':660})
  self.assertEqual(s.toolbar_geometry['excluded_rect'],[920,650,350,45])
 def test_read_only_preflight_does_not_bind_or_show(self):
  bus=Bus();b=bridge.ToolbarBridge(lambda:{},lambda e:None,bus)
  b.preflight()
  self.assertEqual([c[3] for c in bus.calls],['GetDiagnostics']);self.assertFalse(b.bound)
 def test_stale_human_pause_cannot_restore_context_after_stop(self):
  from test_transport import Harness
  h=Harness()
  try:
   epoch=h.server.control_epoch;h.server.begin_boundary('desktop_stop',{})
   h.server.state='stopped';h.transport.panel_control('pause',expected_epoch=epoch)
   self.assertEqual(h.server.state,'stopped');self.assertIsNone(h.server.handoff)
  finally:h.finish()
