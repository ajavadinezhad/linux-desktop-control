"""One fresh bound observer reply per pointer sample; no cross-sample cache."""
import copy
import threading
import unittest
from unittest.mock import patch

import test_control
import test_window_guard as wg
import test_target_guard as tg
g=wg.g


class BoundPointerTests(unittest.TestCase):
 def make(self):
  s,b=wg.WindowServerTests().make()
  b.value['pointer']=[40,50]
  window=g.WindowGuard(b,b.context(),s.backend.cancelled.set)
  return s,b,window
 def test_pointer_and_signature_use_same_single_fresh_reply(self):
  s,b,w=self.make();original=b.context;calls=[]
  def reply():calls.append(True);return original()
  b.context=reply
  self.assertEqual(s.read_bound_pointer(w,{'x':0,'y':0,'width':1000,'height':800},g.pointer_local),(40,50))
  self.assertEqual(len(calls),1)
  b.value['pointer']=[60,70]
  self.assertEqual(s.read_bound_pointer(w,{'x':0,'y':0,'width':1000,'height':800},g.pointer_local),(60,70))
  self.assertEqual(len(calls),2)
 def test_changed_signature_never_supplies_pointer(self):
  for change in ({'window_id':'other'},{'epoch':11},{'rect':[1,0,1000,800]},{'available':False}):
   with self.subTest(change=change):
    s,b,w=self.make();b.value.update(change)
    with self.assertRaises(RuntimeError):s.read_bound_pointer(w,{'x':0,'y':0,'width':1000,'height':800},g.pointer_local)
    self.assertTrue(s.backend.cancelled.is_set())
 def test_context_signal_during_reply_cannot_publish_old_pointer(self):
  s,b,w=self.make();old=copy.deepcopy(b.value)
  def reply():w.changed(11);return old
  b.context=reply
  with self.assertRaises(RuntimeError):s.read_bound_pointer(w,{'x':0,'y':0,'width':1000,'height':800},g.pointer_local)
 def test_request_cancellation_during_reply_refuses_pointer(self):
  s,b,w=self.make();s.cancel_token=threading.Event();old=copy.deepcopy(b.value)
  def reply():s.cancel_token.set();return old
  b.context=reply
  with self.assertRaisesRegex(RuntimeError,'cancelled'):s.read_bound_pointer(w,{'x':0,'y':0,'width':1000,'height':800},g.pointer_local)
 def test_outer_mapping_fences_still_run_before_and_after_sample(self):
  s,b,w=self.make();d=test_control.Tests().backend();calls=[];snapshots=[];original=b.context
  def reply():snapshots.append(True);return original()
  b.context=reply
  d.window_guard=w
  d.pointer_reader=lambda:s.read_bound_pointer(w,{'x':0,'y':0,'width':1000,'height':800},g.pointer_local)
  d.mapping_guard=lambda:calls.append('mapping')
  self.assertEqual(d.observe_pointer(),(40,50))
  self.assertEqual(calls,['mapping','mapping'])
  # The two outer foreground fences remain independent of the pointer reply.
  self.assertEqual(len(snapshots),3)
  def failed_mapping():raise RuntimeError('mapping owner changed')
  d.mapping_guard=failed_mapping
  with self.assertRaisesRegex(RuntimeError,'owner changed'):d.observe_pointer()
  self.assertTrue(d.cancelled.is_set())


class TargetRoleSampleTests(unittest.TestCase):
 def test_each_live_validation_gets_one_fresh_role(self):
  p,w,n=tg.ProviderTests().make();target=p.snapshot(lambda:None)
  with patch.object(n,'get_role',wraps=n.get_role) as role:
   target.check();self.assertEqual(role.call_count,1)
   target.check();self.assertEqual(role.call_count,2)


if __name__=='__main__':unittest.main()
