"""Explicit unverified startup, epoch-bound motion and real local protocol tests."""
import os,socket,tempfile,threading,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_native_activity as legacy
import test_control
import test_pointer_return
m=legacy.m

class PassiveTests(unittest.TestCase):
 def controller(self):
  c=m.Controller(lambda:True,lambda:None,lambda error:None,retain_sharing=True,startup_verification='passive')
  c.helper_ready_at_monotonic=time.monotonic();c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0)
  c._send=lambda token:None;self.addCleanup(c.close);return c
 def test_passive_ack_never_manufactures_calibration_or_notice(self):
  c=self.controller();sent=[];c._send=sent.append;c._read=lambda timeout:'PASSIVE_ARMED'
  c._show_notice=lambda *a,**k:self.fail('No challenge notice in passive startup')
  with patch.object(m.threading,'Thread'):c._start_passive()
  s=c.status();self.assertTrue(s['active']);self.assertTrue(s['monitor_armed']);self.assertTrue(s['passive_acknowledged'])
  self.assertFalse(s['coverage_verified']);self.assertFalse(s['calibration_verified']);self.assertFalse(s['post_arm_verified'])
  self.assertEqual(s['readiness_kind'],'passive-unverified');self.assertEqual(sent[0],'ARM_PASSIVE')
  self.assertNotIn('CALIBRATE',sent);self.assertNotIn('ARM',sent)
 def test_missing_legacy_malformed_ack_cannot_arm(self):
  for response in ('ARMED','CALIBRATED','PASSIVE_ARMED extra','FAULT'):
   c=self.controller();c._read=lambda timeout:response
   with self.subTest(response=response),self.assertRaises(m.NativeFailure):c._start_passive()
   self.assertFalse(c.ready);self.assertFalse(c.passive_acknowledged)
 def test_late_revoked_or_closed_ack_refused(self):
  for reason in ('late','revoked','closed'):
   c=self.controller();clock=[10.];c.helper_ready_at_monotonic=10
   def read(timeout):
    if reason=='late':clock[0]=16.
    elif reason=='revoked':c.active=lambda:False
    else:c.closed=True
    return 'PASSIVE_ARMED'
   c._read=read
   with self.subTest(reason=reason),patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),self.assertRaises(m.NativeFailure):c._start_passive()
   self.assertFalse(c.ready)
 def armed(self):
  c=self.controller();c.monitor_armed=c.passive_acknowledged=c.ready=True;return c
 def test_motion_is_current_epoch_only_and_never_contact_credit(self):
  c=self.armed();c._consume('YIELDED_1');self.assertIsNone(c.motion_epoch)
  c._consume('MOTION_1');self.assertEqual(c.motion_epoch,1)
  with self.assertRaises(m.NativeFailure):c._consume('MOTION_1')
  c._consume('QUIET_1');c.resume_pending=(1,time.monotonic()+1);c._consume('ARMED_1')
  self.assertIsNone(c.motion_epoch);c._consume('YIELDED_2');self.assertIsNone(c.motion_epoch)
  with self.assertRaises(m.NativeFailure):c._consume('MOTION_1')
 def test_unsolicited_malformed_late_and_challenge_motion_refused(self):
  for message in ('MOTION_0','MOTION_01','MOTION_65','MOTION_１','MOTION_2'):
   c=self.armed();c._consume('YIELDED_1')
   with self.subTest(message=message),self.assertRaises(m.NativeFailure):c._consume(message)
  c=self.armed()
  with self.assertRaises(m.NativeFailure):c._consume('MOTION_1')
  c._consume('YIELDED_1');c._consume('QUIET_1')
  with self.assertRaises(m.NativeFailure):c._consume('MOTION_1')
  c=self.armed();c.startup_verification='challenge';c._consume('YIELDED_1')
  with self.assertRaises(m.NativeFailure):c._consume('MOTION_1')
 def test_passive_selection_requires_native_retained_session(self):
  for args in ({'startup_verification':'passive'},{'startup_verification':'passive','physical_takeover':True},{'startup_verification':True}):
   s=test_control.m.Server(test_control.Fake)
   with self.subTest(args=args),self.assertRaises(ValueError):s.call('desktop_start',args)
   self.assertIsNone(s.backend)
 def test_server_requires_exact_explicit_passive_authority_fields(self):
  s=test_control.m.Server(test_control.Fake);s.native_startup_verification='passive'
  state=dict(active=True,startup_verification='passive',readiness_kind='passive-unverified',passive_acknowledged=True,monitor_armed=True,calibration_verified=False,post_arm_verified=False)
  s.native_activity=SimpleNamespace(status=lambda:state)
  s.require_native_ready()
  for key in tuple(state):
   bad=dict(state);bad.pop(key);s.native_activity=SimpleNamespace(status=lambda:bad)
   with self.subTest(missing=key),self.assertRaises(RuntimeError):s.require_native_ready()
 def test_contact_only_and_stale_epoch_never_return(self):
  for proof in (None,0,2,True):
   s,b,d,n=test_pointer_return.PointerReturnTests().make();self.addCleanup(s.close_backend)
   s.native_startup_verification='passive';n.motion_epoch=proof
   self.assertFalse(s.return_after_quiet(n,1));self.assertFalse(d.events);self.assertEqual(n.calls,[])
  s,b,d,n=test_pointer_return.PointerReturnTests().make();self.addCleanup(s.close_backend)
  s.native_startup_verification='passive';n.motion_epoch=1
  self.assertTrue(s.return_after_quiet(n,1))

class PassiveBroker(legacy.FakeBroker):
 def __init__(self,args,ack=b'PASSIVE_ARMED\n',**kwargs):self.ack=ack;super().__init__(args,**kwargs)
 def run(self):
  try:
   p=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.connection=p;p.settimeout(3);p.connect(self.args[3]);stream=p.makefile('rb');p.sendall(b'READY\n');selected=False
   while not self.done.is_set():
    line=stream.readline().decode().strip();self.commands.append(line)
    if not line or line=='CLOSE':break
    if line=='MODEYIELD2' and not selected:selected=True;p.sendall(b'MODEYIELD2_OK\n')
    elif line=='ARM_PASSIVE' and selected:p.sendall(self.ack)
    elif line=='HB':p.sendall(b'ALIVE\n')
    else:break
   stream.close()
  except OSError as error:self.error=type(error).__name__
  finally:
   if self.connection:self.connection.close()
   self.returncode=0;self.done.set()

class PassiveSocketTests(unittest.TestCase):
 def test_full_startup_without_challenge_and_legacy_refusal(self):
  for ack in (b'PASSIVE_ARMED\n',b'ARMED\n'):
   with self.subTest(ack=ack),tempfile.TemporaryDirectory() as directory:
    os.chmod(directory,0o700);brokers=[]
    def launch(args,**kwargs):b=PassiveBroker(args,ack=ack,**kwargs);brokers.append(b);return b
    c=m.Controller(lambda:True,lambda:None,lambda error:None,retain_sharing=True,startup_verification='passive',runtime_dir=directory,launcher=launch,validator=lambda:None,credentials=lambda peer:(123,0,0),startup_timeout=1)
    try:
     if ack==b'PASSIVE_ARMED\n':c.start();self.assertTrue(c.status()['active']);self.assertFalse(c.calibration_verified)
     else:
      with self.assertRaises(m.NativeFailure):c.start()
     self.assertIn('ARM_PASSIVE',brokers[0].commands);self.assertNotIn('CALIBRATE',brokers[0].commands)
    finally:c.close()
