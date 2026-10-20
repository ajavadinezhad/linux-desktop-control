"""A late physical yield discards publication without terminating retained consent."""
import threading, unittest
from types import SimpleNamespace
import test_retained_pause as retained
import test_control
m=retained.m

class PausePublicationRaceTests(unittest.TestCase):
 def make(self):
  f=retained.RetainedPauseTests();s,b,d=f.make();self.addCleanup(f.doCleanups)
  return s,b,d
 def response(self,s,d):
  return {'id':1,'result':{'content':[m.text({}),m.image(test_control.Fake.capture(d))]}}
 def assert_retained(self,s,d,r):
  self.assertTrue(r['result']['isError']);self.assertFalse(any(c['type']=='image' for c in r['result']['content']))
  self.assertIsNone(s.recovery.observation_id);self.assertFalse(d.cancelled.is_set());self.assertEqual(d.session,'/test')
  self.assertEqual(d.events,[]);self.assertIsNone(s.closure_reason)
 def test_yield_while_reading_publication_context_keeps_portal_and_discards_frame(self):
  s,b,d=self.make();r=self.response(s,d);original=b.context
  def context():
   # Native callback cancels the operation before its suspension worker obtains
   # the publication/state lock. The post-query backend.check must propagate
   # the typed pause, even though Server.state is still active here.
   d.operation_cancelled.set();return original()
  b.context=context
  q={'id':1,'params':{'name':'desktop_action'}}
  r=s.fence_response(q,r);self.assert_retained(s,d,r)
  self.assertTrue(d.operation_cancelled.is_set())
 def test_yield_in_final_window_guard_keeps_typed_pause_instead_of_generic_fault(self):
  s,b,d=self.make();r=self.response(s,d)
  def make_guard(*_args):
   def check():
    d.operation_cancelled.set();d.check()
   return SimpleNamespace(check=check)
  s.make_window_guard=make_guard
  r=s.fence_response({'id':1,'params':{'name':'desktop_observe'}},r)
  self.assert_retained(s,d,r);self.assertTrue(d.operation_cancelled.is_set())
 def test_true_fault_or_revocation_in_same_context_boundary_is_still_terminal(self):
  for failure in ('observer','revocation'):
   with self.subTest(failure=failure):
    s,b,d=self.make();r=self.response(s,d)
    def context():
     if failure=='revocation':d.cancelled.set()
     raise RuntimeError('private observer failure')
    b.context=context
    r=s.fence_response({'id':1,'params':{'name':'desktop_action'}},r)
    self.assertTrue(r['result']['isError']);self.assertEqual(s.state,'closed');self.assertIsNone(d.session)
    self.assertFalse(any(c['type']=='image' for c in r['result']['content']))
    self.assertEqual(s.closure_reason,'publication-foreground-fault')
    s.invalidate(warning='native');self.assertEqual(s.closure_reason,'publication-foreground-fault')
 def test_default_policy_does_not_retain_typed_pause(self):
  s,b,d=self.make();s.interruption_policy='close';r=self.response(s,d)
  def context():raise m.RetainedPause('operation paused')
  b.context=context
  r=s.fence_response({'id':1,'params':{'name':'desktop_observe'}},r)
  self.assertTrue(r['result']['isError']);self.assertEqual(s.state,'closed');self.assertIsNone(d.session)
