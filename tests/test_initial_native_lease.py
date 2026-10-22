"""Initial native lease protocol and admission; no helper/portal launch."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_native_activity as legacy
import test_control
m=legacy.m
class InitialNativeLeaseTests(unittest.TestCase):
 def controller(self,seconds=1200):
  c=m.Controller(lambda:True,lambda:None,lambda e:None,session_seconds=seconds)
  c.helper_ready_at_monotonic=10;return c
 def test_exact_integer_bounds(self):
  for value in (True,False,119,1201,1200.,'1200',None):
   with self.subTest(value=value),self.assertRaises(ValueError):self.controller(value)
  self.assertEqual(self.controller(120).session_seconds,120)
  for seconds in (600,999,1000,1200):self.assertEqual(self.controller(seconds).requested_session_seconds,seconds)
 def test_exact_ack_changes_budget_once_without_resetting_anchor(self):
  c=self.controller();sent=[];c._send=sent.append;c._read=lambda timeout:'LEASE_1200_OK'
  with patch.object(m.time,'monotonic',return_value=10.5):c._negotiate_lease()
  self.assertEqual(sent,['LEASE_1200']);self.assertEqual(c.session_seconds,1200);self.assertEqual(c.helper_ready_at_monotonic,10)
  with self.assertRaises(m.NativeFailure):c._negotiate_lease()
  with patch.object(m.time,'monotonic',return_value=1209.9):self.assertTrue(c._yield_authorized())
  with patch.object(m.time,'monotonic',return_value=1210):self.assertFalse(c._yield_authorized());self.assertEqual(c.status()['lease_remaining_seconds'],0)
 def test_missing_mismatched_legacy_and_late_ack_never_extend(self):
  for reply in (None,'FAULT','ALIVE','READY','LEASE_120_OK','LEASE_01200_OK','LEASE_600_OK'):
   c=self.controller();c._send=lambda token:None;c._read=lambda timeout:reply
   with self.subTest(reply=reply),patch.object(m.time,'monotonic',return_value=10.5),self.assertRaises(m.NativeFailure):c._negotiate_lease()
   self.assertEqual(c.session_seconds,120)
  c=self.controller();c._send=lambda token:None;clock=[10.]
  def read(timeout):clock[0]=11;return 'LEASE_1200_OK'
  c._read=read
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),self.assertRaises(m.NativeFailure):c._negotiate_lease()
  self.assertEqual(c.session_seconds,120)
 def test_cancel_revocation_and_original_expiry_fence_ack(self):
  for reason in ('cancel','revoke','expired'):
   c=self.controller();c._send=lambda token:None;clock=[10.]
   def read(timeout):
    if reason=='cancel':c.stop.set()
    if reason=='revoke':c.active=lambda:False
    if reason=='expired':clock[0]=130
    return 'LEASE_1200_OK'
   c._read=read
   with self.subTest(reason=reason),patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),self.assertRaises(m.NativeFailure):c._negotiate_lease()
   self.assertEqual(c.session_seconds,120)
 def test_server_validation_precedes_any_portal_or_helper(self):
  for args in ({'session_seconds':1200},{'physical_takeover':True,'session_seconds':True},{'physical_takeover':True,'session_seconds':1201},{'physical_takeover':True,'session_seconds':119},{'physical_takeover':True,'session_seconds':1200.}):
   server=test_control.m.Server(test_control.Fake);calls=[];server.preflight_physical_guard=lambda:calls.append('helper')
   with self.subTest(args=args),self.assertRaises(ValueError):server.call('desktop_start',args)
   self.assertFalse(calls);self.assertIsNone(server.backend)
 def test_server_forwards_selected_limit_without_changing_default_api(self):
  for seconds in (120,600,999,1000,1200):
   server=test_control.m.Server(test_control.Fake);server.ensure_backend();server.backend.start();server.state='opening';server.native_session_seconds=seconds;calls=[]
   controller=SimpleNamespace(start=lambda:None,status=lambda:{'active':True})
   def factory(**kwargs):calls.append(kwargs);return controller
   server.native_activity_module=lambda:SimpleNamespace(Controller=factory)
   server.calibration_notice_module=lambda:SimpleNamespace(CalibrationNotice=lambda:None)
   server.enable_physical_guard()
   if seconds==120:self.assertNotIn('session_seconds',calls[0])
   else:self.assertEqual(calls[0]['session_seconds'],seconds)

 def test_active_server_cannot_change_selected_limit(self):
  server=test_control.m.Server(test_control.Fake);server.call('desktop_start',{})
  server.preflight_physical_guard=lambda:None
  with self.assertRaisesRegex(ValueError,'cannot be changed'):
   server.call('desktop_start',{'physical_takeover':True,'session_seconds':1200})
  self.assertEqual(server.native_session_seconds,120)
 def test_local_negotiation_after_calibration_refused_before_command(self):
  c=self.controller();sent=[];c._send=sent.append;c.calibration_state='waiting'
  with self.assertRaises(m.NativeFailure):c._negotiate_lease()
  self.assertFalse(sent)

 def test_every_supported_digit_boundary_negotiates_exactly(self):
  for seconds in (120,600,999,1000,1200):
   c=self.controller(seconds);sent=[];c._send=sent.append;c._read=lambda timeout:'LEASE_'+str(seconds)+'_OK'
   with self.subTest(seconds=seconds),patch.object(m.time,'monotonic',return_value=10.5):c._negotiate_lease()
   self.assertEqual(sent,['LEASE_'+str(seconds)]);self.assertEqual(c.session_seconds,seconds)
   self.assertEqual(c.helper_ready_at_monotonic,10)
