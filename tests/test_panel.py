import json,threading,time,unittest
from test_transport import Harness
from test_control import m

class ToolbarControlTests(unittest.TestCase):
 def test_emergency_stop_interrupts_drag_and_queued_capture(self):
  h=Harness()
  try:
   h.begin('drag');h.send({'id':44,'method':'tools/call','params':{'name':'desktop_observe'}})
   h.transport.panel_control('stop')
   self.assertTrue(h.backend.finished.wait(1));self.assertTrue(h.backend.was_released)
   end=time.monotonic()+1
   while h.server.state!='stopped' and time.monotonic()<end:time.sleep(.005)
   self.assertEqual(h.server.state,'stopped');self.assertIsNone(h.server.handoff)
  finally:h.finish()
  replies=list(map(json.loads,h.output.getvalue().splitlines()))
  self.assertFalse(any(r.get('id') is None for r in replies))
  self.assertFalse(any(c.get('type')=='image' for r in replies for c in r.get('result',{}).get('content',[])))
 def test_panel_pause_then_stop_supersedes_context(self):
  h=Harness()
  try:
   h.begin('text');h.transport.panel_control('pause');h.transport.panel_control('stop')
   self.assertTrue(h.backend.finished.wait(1))
   end=time.monotonic()+1
   while h.server.state!='stopped' and time.monotonic()<end:time.sleep(.005)
   self.assertEqual(h.server.state,'stopped');self.assertIsNone(h.server.handoff)
  finally:h.finish()
 def test_stop_interrupts_wait_for_consent(self):
  h=Harness();entered=threading.Event()
  def start():
   entered.set();h.backend.stopped.wait(2)
   raise RuntimeError('consent interrupted')
  h.backend.start=start;h.backend.active=False;h.server.state='stopped'
  try:
   h.send({'id':42,'method':'tools/call','params':{'name':'desktop_start'}})
   self.assertTrue(entered.wait(1));h.transport.panel_control('stop')
   end=time.monotonic()+1
   while h.server.state!='stopped' and time.monotonic()<end:time.sleep(.005)
   self.assertEqual(h.server.state,'stopped');self.assertTrue(h.backend.stopped.is_set())
  finally:h.finish()
 def test_panel_pause_preserves_task_intent(self):
  h=Harness();h.server.task_summary='Save the disposable note after review'
  try:
   h.transport.panel_control('pause')
   end=time.monotonic()+1
   while h.server.state!='paused' and time.monotonic()<end:time.sleep(.005)
   self.assertEqual(h.server.handoff['task_summary'],'Save the disposable note after review')
  finally:h.finish()
 def test_blank_summary_cannot_break_pause(self):
  from test_control import Fake
  s=m.Server(Fake)
  for summary in ('','   '):
   with self.assertRaises(ValueError):s.call('desktop_start',{'task_summary':summary})
