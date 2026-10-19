"""Unarmed calibration acknowledgement fences; fake clock and peer only."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_native_activity as legacy
m=legacy.m

class CalibrationSettlingTests(unittest.TestCase):
 def make(self, replies):
  c=m.Controller(lambda:True,lambda:None,lambda e:None)
  c.helper_ready_at_monotonic=10;c.process=SimpleNamespace(poll=lambda:None)
  clock=[10.0];sent=[];c._send=sent.append;items=iter(replies)
  def read(timeout):
   value=next(items,None)
   if isinstance(value,tuple):clock[0]+=value[0];return value[1]
   clock[0]+=.02;return value
  c._read=read
  return c,clock,sent
 def run_wait(self,c,clock):
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):c._wait_calibration_start()
 def test_old_helper_immediate_ack_no_extra_command_or_credit(self):
  c,clock,sent=self.make(['CALIBRATING']);self.run_wait(c,clock)
  self.assertEqual(sent,[]);self.assertEqual(c.calibration_state,'settling')
  self.assertFalse(c.ready);self.assertFalse(c.calibration_verified);self.assertFalse(c.notice_requested)
 def test_release_after_heartbeats_accepts_fresh_ack(self):
  c,clock,sent=self.make([(.25,'ALIVE')]*16+['CALIBRATING']);self.run_wait(c,clock)
  self.assertGreater(len(sent),10);self.assertEqual(set(sent),{'HB'});self.assertFalse(c.ready)
 def test_sustained_wait_timeout_even_if_peer_alive(self):
  c,clock,_=self.make([(.25,'ALIVE')]*30)
  with self.assertRaises(m.NativeFailure):self.run_wait(c,clock)
  self.assertFalse(c.calibration_verified);self.assertFalse(c.notice_requested)
 def test_fault_and_unexpected_success_tokens_never_authorize(self):
  for token in ('FAULT','CALIBRATED','ARMED','CALIBRATION_RESET','YIELDED_1'):
   c,clock,_=self.make([token])
   with self.subTest(token=token),self.assertRaises(m.NativeFailure):self.run_wait(c,clock)
   self.assertFalse(c.ready);self.assertFalse(c.calibration_verified)
 def test_late_ack_cannot_cross_deadline(self):
  c,clock,_=self.make([(6,'CALIBRATING')])
  with self.assertRaises(m.NativeFailure):self.run_wait(c,clock)
 def test_cancel_during_read_and_lease_expiry_fence_ack(self):
  for cancel in ('stop','authorization','lease'):
   c,clock,_=self.make([])
   def read(timeout):
    if cancel=='stop':c.stop.set()
    elif cancel=='authorization':c.active=lambda:False
    else:clock[0]=130
    return 'CALIBRATING'
   c._read=read
   with self.subTest(cancel=cancel),self.assertRaises(m.NativeFailure):self.run_wait(c,clock)
   self.assertFalse(c.ready);self.assertFalse(c.notice_requested)
 def test_silent_peer_and_exited_helper_refuse(self):
  c,clock,_=self.make([(1.01,None)])
  with self.assertRaises(m.NativeFailure):self.run_wait(c,clock)
  c,clock,_=self.make([None]);c.process.poll=lambda:46
  with self.assertRaises(m.NativeFailure):self.run_wait(c,clock)
