"""Permission-state replies are untrusted; malformed data never permits waiting."""
import json,unittest
from unittest.mock import patch
import test_indicator as fixture

class AuthBridgeTests(unittest.TestCase):
 def bridge(self):
  bridge=fixture.m.IndicatorBridge(lambda:{'active':True})
  bridge.bound=True;bridge.auth_wait_protocol=3
  return bridge
 def state(self):
  return {'auth_state':'visible','auth_available':True,'reason':'auth-prompt',
   'action_category':'system-authentication','attempt_id':'a'*32,'origin_window_id':'77',
   'dialog_phase':'opened','epoch':3}
 def read(self,bridge,value):
  with patch.object(bridge,'call',return_value=(json.dumps(value),)):
   return bridge.auth_state()
 def test_exact_states_and_no_arbitrary_fields(self):
  b=self.bridge();v=self.state();self.assertEqual(self.read(b,v),v)
  for phase in ('pending','closing'):
   pending=dict(v,auth_state='pending',dialog_phase=phase)
   self.assertEqual(self.read(b,pending),pending)
  none=dict(v,auth_state='none',auth_available=False,reason='none',action_category='none',dialog_phase='none')
  self.assertEqual(self.read(b,none),none)
  blocked=dict(none,auth_state='blocked',reason='locked',attempt_id=None,origin_window_id=None)
  self.assertEqual(self.read(b,blocked),blocked)
  for reason in ('polkit-dialog-unavailable','origin-unavailable','origin-changed','modal-mismatch'):
   self.assertEqual(self.read(b,dict(blocked,reason=reason))['reason'],reason)
  for change in ({'epoch':True},{'epoch':-1},{'attempt_id':'bad'},{'origin_window_id':''},
    {'auth_available':1},{'dialog_phase':'closing'},{'reason':'arbitrary-private-text'},
    {'action_category':'package-install'},{'action_category':'package-management'},{'action_category':'remove-package'},{'password':'secret'}):
   with self.subTest(change=change),self.assertRaisesRegex(RuntimeError,'Invalid permission'):
    self.read(b,dict(v,**change))
 def test_unsupported_closed_and_reply_time_closure_refuse(self):
  b=self.bridge();b.auth_wait_protocol=0
  with self.assertRaises(RuntimeError):self.read(b,self.state())
  b.auth_wait_protocol=3
  def reply(*args):b.closed.set();return (json.dumps(self.state()),)
  with patch.object(b,'call',side_effect=reply),self.assertRaisesRegex(RuntimeError,'ended'):b.auth_state()
 def test_boolean_capability_never_enables_auth_protocol(self):
  for capability,expected in ((True,0),(1,0),(2,0),(3,3),(None,0)):
   b=fixture.m.IndicatorBridge(lambda:{},fixture.Bus())
   original=b.call
   def call(method,*args):
    if method=='GetDiagnostics':return (json.dumps({'protocol_version':2,'pointer_snapshot':True,'auth_wait_protocol':capability}),)
    return original(method,*args)
   with patch.object(b,'call',side_effect=call):b.preflight()
   self.assertEqual(b.auth_wait_protocol,expected)

if __name__=='__main__':unittest.main()
