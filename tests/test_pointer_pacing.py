"""Performance invariants on real input logic with fake compositor observations."""
import unittest
from unittest import mock
import test_control
m=test_control.m

class PacingTests(unittest.TestCase):
 def backend(self):
  d=test_control.Tests().backend();d.waits=[];d.reads=[]
  def wait(seconds):d.waits.append(seconds);d.check()
  def read():d.reads.append(d.observed_pointer);return d.observed_pointer
  d.wait_interruptibly=wait;d.pointer_reader=read
  return d
 def test_drag_confirms_each_arrival_twice_and_press_again_without_duplicate_path_pass(self):
  d=self.backend();path=[[20+i*4,30+i*2] for i in range(40)]
  d.action({'type':'drag','path':path})
  # Initial observation, then approach + two matches per point; an additional
  # pair immediately before down remains mandatory. No whole second pass.
  self.assertEqual(len(d.reads),1+3*len(path)+2)
  for point in map(tuple,path):self.assertGreaterEqual(d.reads.count(point),2)
  self.assertEqual(d.held,[])
  self.assertNotIn(.1,d.waits)
  self.assertIn('input_duration_ms',d.transaction_info)
 def test_direct_move_uses_only_its_position_confirmation(self):
  d=self.backend();d.pointer_position=None
  with mock.patch.object(d,'confirm_pointer_endpoint',wraps=d.confirm_pointer_endpoint) as confirm:
   d.move_to(40,50,0)
  self.assertEqual(confirm.call_count,1)
 def test_explicit_wait_does_not_add_a_second_unrequested_wait(self):
  d=self.backend();d.action({'type':'wait','seconds':.4})
  self.assertEqual(d.waits,[.4])
 def test_cancel_at_end_of_drag_still_releases_button(self):
  d=self.backend()
  def wait(seconds):
   if d.held:d.cancelled.set()
   d.check()
  d.wait_interruptibly=wait
  with self.assertRaises(RuntimeError):d.action({'type':'drag','path':[[20,30],[24,32]]})
  self.assertFalse(d.held)
  self.assertEqual(d.events[-1][3][-1],0)
