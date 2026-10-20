import threading,time,unittest
import test_native_activity as fixture

class PermissionControllerTests(unittest.TestCase):
 def controller(self):
  c=fixture.m.Controller(lambda:True,lambda:None,lambda e:None,retain_sharing=True,allow_permission_wait=True)
  c.ready=True;c.auth_mode_acknowledged=True;c.helper_ready_at_monotonic=time.monotonic();return c
 def test_begin_end_use_monitor_consumer_and_never_read_socket(self):
  c=self.controller();sent=[]
  c._read=lambda *_:self.fail('concurrent socket read')
  def send(token):
   sent.append(token)
   c._consume('AUTHWAIT_1_OK' if token=='AUTHWAIT_1' else 'AUTHREADY_1')
  c._send=send
  self.assertEqual(c.begin_auth_wait(),1);self.assertTrue(c.auth_waiting)
  self.assertEqual(c.end_auth_wait(1),1);self.assertFalse(c.auth_waiting)
  self.assertEqual(sent,['AUTHWAIT_1','AUTHEND_1']);self.assertFalse(c.calibration_verified);self.assertFalse(c.post_arm_verified)
 def test_unknown_duplicate_late_epoch_ack_refuses(self):
  for reply in ['AUTHWAIT_01_OK','AUTHWAIT_2_OK','AUTHREADY_1']:
   c=self.controller();c._send=lambda token:c._consume(reply)
   with self.assertRaises(fixture.m.NativeFailure):c.begin_auth_wait()
  c=self.controller()
  with self.assertRaises(fixture.m.NativeFailure):c._consume('AUTHWAIT_1_OK')
 def test_wait_is_woken_by_monitor_thread_and_owner_loss_refuses(self):
  c=self.controller();entered=threading.Event();result=[];c._send=lambda _:entered.set()
  thread=threading.Thread(target=lambda:result.append(c.begin_auth_wait()));thread.start();self.assertTrue(entered.wait(1))
  c._consume('AUTHWAIT_1_OK');thread.join(1);self.assertEqual(result,[1])
  c.active=lambda:False
  with self.assertRaises(fixture.m.NativeFailure):c.end_auth_wait(1)
 def test_mode_negotiation_is_explicit_exact_and_prearm(self):
  c=self.controller();c.auth_mode_acknowledged=False;sent=[];c._send=sent.append;c._read=lambda _: 'AUTHMODE1_OK'
  c._negotiate_auth();self.assertTrue(c.auth_mode_acknowledged);self.assertEqual(sent,['AUTHMODE1'])
  c=self.controller();c.auth_mode_acknowledged=False;c._send=lambda _:None;c._read=lambda _: 'ARMED'
  with self.assertRaises(fixture.m.NativeFailure):c._negotiate_auth()
  self.assertFalse(c.auth_mode_acknowledged)

 def test_pointer_epoch_cannot_authorize_during_auth_wait(self):
  c=self.controller();c._send=lambda _:c._consume('AUTHWAIT_1_OK');c.begin_auth_wait()
  for token in ('MOTION_1','YIELDED_1','QUIET_1','ARMED_1'):
   with self.assertRaises(fixture.m.NativeFailure):c._consume(token)
  self.assertFalse(c.yielded)
