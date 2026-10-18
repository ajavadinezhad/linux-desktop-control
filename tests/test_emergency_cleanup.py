import json,time,unittest
from test_transport import Harness
import test_control
class EmergencyCleanupTests(unittest.TestCase):
 def wait_state(self,h,state):
  end=time.monotonic()+1
  while h.server.state!=state and time.monotonic()<end:time.sleep(.005)
  self.assertEqual(h.server.state,state)
 def test_idle_emergency_request_closes_backend_without_status_or_more_input(self):
  h=Harness()
  try:
   h.transport.request_emergency_stop();self.wait_state(h,'stopped')
   self.assertFalse(h.backend.active);self.assertIsNone(h.server.handoff)
  finally:h.finish()
 def test_emergency_cancels_held_drag_and_queued_input(self):
  h=Harness()
  try:
   h.begin('drag');h.send({'id':44,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{'type':'text'}}}})
   h.transport.request_emergency_stop();self.assertTrue(h.backend.finished.wait(1));self.wait_state(h,'stopped')
   self.assertTrue(h.backend.was_released);self.assertFalse(h.backend.active)
  finally:h.finish()
  replies={r['id']:r for r in map(json.loads,h.output.getvalue().splitlines())}
  self.assertTrue(replies[44]['result']['isError'])
 def test_pause_mid_typing_releases_and_invalidates_queued_action(self):
  h=Harness()
  try:
   h.begin('text');h.send({'id':44,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{'type':'drag'}}}})
   h.transport.panel_control('pause',expected_epoch=h.server.control_epoch)
   self.assertTrue(h.backend.finished.wait(1));self.wait_state(h,'paused')
   self.assertTrue(h.backend.was_released);self.assertFalse(h.backend.active)
  finally:h.finish()
  replies={r['id']:r for r in map(json.loads,h.output.getvalue().splitlines())}
  self.assertTrue(replies[44]['result']['isError'])
 def test_interrupted_modifier_chord_releases_all_pressed_keys(self):
  d=test_control.Tests.backend(self);d.held=[('key',0xffe3),('key',0xffe9),('button',272)];d.stopped.set()
  self.assertFalse(d.release());self.assertEqual(d.held,[])
  self.assertEqual([e[1] for e in d.events],['NotifyPointerButton','NotifyKeyboardKeysym','NotifyKeyboardKeysym'])
  self.assertTrue(all(e[3][-1]==0 for e in d.events))

 def test_capture_cleanup_failure_still_closes_portal_and_clears_pointer(self):
  d=test_control.Tests.backend(self);d.fd=None;d.closed_sub=None;d.pointer_position=(100,200)
  class BrokenPipeline:
   def set_state(self,state):raise RuntimeError('capture failure')
  d.pipeline=BrokenPipeline();d.close()
  self.assertTrue(d.portal_closed);self.assertIsNone(d.session);self.assertIsNone(d.pointer_position)
  self.assertIn('Capture shutdown failed',d.cleanup_warning)
  self.assertEqual(d.events[-1][0],'org.freedesktop.portal.Session')
 def test_fd_cleanup_failure_still_closes_portal(self):
  from unittest.mock import patch
  d=test_control.Tests.backend(self);d.fd=99;d.pipeline=None;d.closed_sub=None
  with patch.object(test_control.m.os,'close',side_effect=OSError('bad descriptor')):d.close()
  self.assertTrue(d.portal_closed);self.assertIsNone(d.fd);self.assertIsNone(d.session)
