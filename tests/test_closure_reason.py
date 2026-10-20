import time,unittest
import test_window_guard as fixtures

class ClosureReasonTests(unittest.TestCase):
 def make(self):return fixtures.WindowServerTests().make()
 def test_async_foreground_loss_preserves_first_reason(self):
  s,b=self.make()
  try:
   content=s.capture_result(('active',),transition_settle=True)
   s.fence_response({'id':1,'params':{'name':'desktop_action'}},{'id':1,'result':{'content':content}})
   b.value.update(window_id='private-title',epoch=11);b.armed.changed(11)
   deadline=time.monotonic()+1
   while s.state!='closed' and time.monotonic()<deadline:time.sleep(.005)
   self.assertFalse(s.status()['active'])
   self.assertEqual(s.status()['closure_reason'],'foreground-context-changed')
   s.invalidate(warning='native');s.close_backend()
   self.assertEqual(s.status()['closure_reason'],'foreground-context-changed')
  finally:s.shutdown()
 def test_stale_observer_cannot_replace_current_reason(self):
  s,b=self.make()
  try:
   self.assertFalse(s.invalidate(expected_indicator=object(),reason='foreground-context-changed'))
   self.assertIsNone(s.status()['closure_reason'])
   s.call('desktop_close',{})
   self.assertEqual(s.status()['closure_reason'],'requested-close')
  finally:s.shutdown()
 def test_new_session_resets_and_unknown_text_not_exported(self):
  s,b=self.make()
  try:
   s.invalidate(reason='private arbitrary error');s.close_backend()
   self.assertEqual(s.status()['closure_reason'],'session-invalidated')
   s.call('desktop_start',{})
   self.assertIsNone(s.status()['closure_reason'])
  finally:s.shutdown()
