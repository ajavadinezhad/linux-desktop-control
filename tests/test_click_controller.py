"""Click recovery is explicitly negotiated and cannot use ordinary auto-return."""
import threading,time,unittest
from unittest.mock import patch
import test_native_activity as fixture
m=fixture.m

class ClickControllerTests(unittest.TestCase):
 def controller(self):
  calls=[]
  c=m.Controller(lambda:True,lambda:None,lambda e:None,retain_sharing=True,
      startup_verification='passive',click_policy='pause-return',on_intervention=lambda owner,epoch:calls.append((owner,epoch)))
  c.ready=c.monitor_armed=c.passive_acknowledged=c.click_mode_acknowledged=True
  c.helper_ready_at_monotonic=time.monotonic();c._send=lambda _:None
  return c,calls
 def test_negotiation_requires_exact_timely_live_ack(self):
  c,_=self.controller();c.click_mode_acknowledged=False;sent=[];c._send=sent.append;c._read=lambda _:'CLICKPAUSE1_OK'
  c._negotiate_click();self.assertEqual(sent,['CLICKPAUSE1']);self.assertTrue(c.click_mode_acknowledged)
  for reply in ('MODEYIELD2_OK','CLICKPAUSE1_OK extra',None):
   c,_=self.controller();c.click_mode_acknowledged=False;c._read=lambda _:reply
   with self.subTest(reply=reply),self.assertRaises(m.NativeFailure):c._negotiate_click()
   self.assertFalse(c.click_mode_acknowledged)
 def test_click_current_epoch_callback_and_exact_tokens(self):
  c,calls=self.controller();c._consume('YIELDED_1');c._consume('CLICKED_1')
  self.assertEqual(calls,[(c,1)]);self.assertTrue(c.is_current_intervention(1));self.assertFalse(c.ready)
  for token in ('CLICKED_1','CLICKED_0','CLICKED_01','CLICKED_2','CLICKED_１'):
   with self.subTest(token=token),self.assertRaises(m.NativeFailure):c._consume(token)
  c._consume('QUIET_1');self.assertTrue(c.is_current_intervention(1,quiet=True))
  c._consume('YIELDED_2')
  with self.assertRaises(m.NativeFailure):c._consume('QUIET_2')
  c._consume('CLICKED_2');c._consume('QUIET_2');self.assertTrue(c.is_current_intervention(2,quiet=True))
 def test_click_aware_resume_is_distinct_and_no_coverage_credit(self):
  c,_=self.controller();c._consume('YIELDED_1');c._consume('CLICKED_1');c._consume('QUIET_1');sent=[]
  c._send=lambda token:(sent.append(token),c._consume('ARMED_1'))
  self.assertEqual(c.resume_from_pause(1,click_return=True),1)
  self.assertEqual(sent,['RESUMECLICK_1']);self.assertIsNone(c.intervention_epoch)
  self.assertTrue(c.ready);self.assertFalse(c.calibration_verified);self.assertFalse(c.post_arm_verified)
 def test_ordinary_resume_cannot_resume_click_pause(self):
  c,_=self.controller();c._consume('YIELDED_1');c._consume('CLICKED_1');c._consume('QUIET_1');sent=[];c._send=sent.append
  with patch.object(c,'_notify'),self.assertRaises(m.NativeFailure):c.resume_from_pause(1)
  self.assertEqual(sent,[]);self.assertTrue(c.yielded)
 def test_resume_waits_for_independent_monitor_and_owner_loss_refuses(self):
  c,_=self.controller();c._consume('YIELDED_1');c._consume('CLICKED_1');c._consume('QUIET_1')
  sent=threading.Event();c._send=lambda _:sent.set();result=[]
  c._read=lambda *_:self.fail('Caller must never read the monitor socket')
  worker=threading.Thread(target=lambda:result.append(c.resume_from_pause(1,click_return=True)))
  worker.start();self.assertTrue(sent.wait(1));self.assertTrue(worker.is_alive())
  c._consume('ARMED_1');worker.join(1);self.assertEqual(result,[1])
  c,_=self.controller();c._consume('YIELDED_1');c._consume('CLICKED_1');c._consume('QUIET_1');c.active=lambda:False
  with patch.object(c,'_notify'),self.assertRaises(m.NativeFailure):c.resume_from_pause(1,click_return=True)
 def test_unsolicited_auth_and_legacy_click_tokens_refuse(self):
  c,_=self.controller()
  with self.assertRaises(m.NativeFailure):c._consume('CLICKED_1')
  c._consume('YIELDED_1');c.auth_waiting=True
  with self.assertRaises(m.NativeFailure):c._consume('CLICKED_1')
  c,_=self.controller();c.click_mode_acknowledged=False;c._consume('YIELDED_1')
  with self.assertRaises(m.NativeFailure):c._consume('CLICKED_1')
  for args in ({'click_policy':'pause-return'},{'click_policy':True},{'click_policy':'pause'}):
   with self.assertRaises(ValueError):m.Controller(lambda:True,lambda:None,lambda e:None,**args)

if __name__=='__main__':unittest.main()
