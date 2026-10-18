import threading,unittest,json
from test_control import m,Fake
import test_control
class SessionCleanupTests(unittest.TestCase):
 def test_core_discovery_and_start_require_no_extension(self):
  self.assertEqual({t['name'] for t in m.tools()},{'desktop_start','desktop_observe','desktop_action','desktop_status','desktop_close'})
  s=m.Server(Fake);s.call('desktop_start',{});self.assertTrue(s.status()['active']);s.call('desktop_close',{});self.assertFalse(s.status()['active'])
 def test_portal_closes_before_capture_teardown_even_when_pipeline_fails(self):
  d=test_control.Tests.backend(self);d.fd=None;d.closed_sub=None;order=[];orig=d.call
  def call(*args,**kw):order.append('portal');return orig(*args,**kw)
  d.call=call
  class Pipeline:
   def set_state(self,state):order.append('capture');raise RuntimeError('failed')
  d.pipeline=Pipeline();d.close();self.assertEqual(order,['portal','capture']);self.assertTrue(d.portal_closed);self.assertIsNone(d.session);self.assertIn('teardown incomplete',d.cleanup_warning)
 def test_stale_queued_start_cannot_reopen_after_closure(self):
  s=m.Server(Fake);generation=s.generation;s.invalidate();s.call('desktop_close',{});s.request_epoch=generation
  with self.assertRaisesRegex(RuntimeError,'invalidated'):s.call('desktop_start',{})
 def test_failing_indicator_does_not_create_an_extension_prerequisite(self):
  s=m.Server(Fake);s.call('desktop_start',{});self.assertTrue(s.status()['input_allowed']);s.call('desktop_close',{})

 def test_tool_error_closes_resources_and_indicator(self):
  s=m.Server(Fake);s.call('desktop_start',{});closed=[]
  class Indicator:
   def close(self):closed.append(True)
  s.indicator=Indicator()
  result=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{'type':'fail'}}}})
  self.assertTrue(result['result']['isError']);self.assertFalse(s.status()['active']);self.assertEqual(closed,[True])

 def test_unconfirmed_portal_remains_retryable_and_blocks_new_consent(self):
  d=test_control.Tests.backend(self);d.fd=None;d.pipeline=None;d.closed_sub=None;d.portal_closed=False
  def fail(*args,**kw):raise RuntimeError('portal unavailable')
  d.call=fail;d.close();self.assertEqual(d.session,'/test');self.assertFalse(d.portal_closed)
  with self.assertRaisesRegex(RuntimeError,'unconfirmed'):d.start()
