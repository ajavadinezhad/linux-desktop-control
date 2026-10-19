"""Injected notices and read-only startup snapshots; no real notification calls."""
import math
import types
import unittest
from unittest.mock import patch
import test_calibration_notice as notice_fixtures
import test_control
import test_physical_guard
n=notice_fixtures.notice_module
m=test_control.m

class PostArmNoticeTests(unittest.TestCase):
 def test_post_arm_phase_fixed_mouse_only_without_actions(self):
  calls=[]
  def call(*args):calls.append(args);return (71,) if args[0]=='Notify' else ()
  notice=n.CalibrationNotice(call=call)
  self.assertTrue(notice.show(phase='post-arm-pointer'))
  method,signature,arguments,timeout=calls[0]
  self.assertEqual((method,signature,timeout),('Notify','(susssasa{sv}i)',500))
  self.assertEqual(arguments,('Desktop control',0,'',n.CalibrationNotice.POST_ARM_SUMMARY,n.CalibrationNotice.POST_ARM_BODY,[],{},30000))
  self.assertIn('Do not press any keys or mouse buttons',arguments[4])
  self.assertEqual(notice.status()['phase'],'post-arm-pointer');self.assertFalse(notice.status()['visible_verified'])
  self.assertTrue(notice.close());self.assertEqual(calls[-1],('CloseNotification','(u)',(71,),300))
 def test_phase_allowlist_rejects_arbitrary_content_or_reset_before_call(self):
  calls=[];notice=n.CalibrationNotice(call=lambda *args:calls.append(args))
  for phase in ('private arbitrary text','',None,True,[],'POST-ARM-POINTER'):
   with self.subTest(phase=phase),self.assertRaises(ValueError):notice.show(phase=phase)
  with self.assertRaises(ValueError):notice.show(reset=True,phase='post-arm-pointer')
  self.assertEqual(calls,[])
 def test_new_phase_does_not_erase_uncertain_notice_ownership(self):
  calls=[]
  def fail(*args):calls.append(args);raise TimeoutError('private text')
  notice=n.CalibrationNotice(call=fail);self.assertFalse(notice.show())
  self.assertFalse(notice.show(phase='post-arm-pointer'));self.assertEqual(len(calls),1)
  self.assertEqual(notice.status()['phase'],'calibration');self.assertTrue(notice.status()['delivery_unknown']);self.assertFalse(notice.close())

 def test_new_phase_cannot_reuse_old_acknowledgement_after_failed_delivery(self):
  notices=[]
  def call(method,*args):
   if method=='CloseNotification':return ()
   notices.append(True)
   if len(notices)==1:return (7,)
   raise TimeoutError('unknown new delivery')
  notice=n.CalibrationNotice(call=call);self.assertTrue(notice.show());self.assertTrue(notice.close())
  self.assertFalse(notice.show(phase='post-arm-pointer'));self.assertFalse(notice.status()['request_acknowledged']);self.assertTrue(notice.status()['delivery_unknown'])

class PostArmSnapshotTests(unittest.TestCase):
 def server(self,**fields):
  s=m.Server(test_control.Fake);s.state='opening'
  s.backend=types.SimpleNamespace(status=lambda:self.fail('snapshot must not call backend'))
  baseline=dict(retain_sharing=True,calibration_state='verified',calibration_verified=True,post_arm_state='waiting-motion',post_arm_verified=False,post_arm_deadline_monotonic=130.,notice_phase='post-arm-pointer',notice_requested=True,notice_acknowledged=True,notice_active=True)
  baseline.update(fields);s.native_activity=types.SimpleNamespace(**baseline);return s
 def test_post_arm_cue_has_distinct_stage_coarse_deadline_and_no_authority(self):
  s=self.server()
  with patch.object(m.time,'monotonic',return_value=105.25):snapshot=s.startup_status_snapshot()
  native=snapshot['native_activity'];self.assertEqual(native['readiness_stage'],'post-arm-pointer');self.assertEqual(native['post_arm_remaining_seconds'],25)
  self.assertTrue(native['calibration_verified']);self.assertTrue(native['post_arm_required']);self.assertFalse(native['post_arm_verified']);self.assertEqual(native['calibration_notice']['phase'],'post-arm-pointer')
  self.assertFalse(snapshot['active']);self.assertFalse(snapshot['capture_allowed']);self.assertFalse(snapshot['input_allowed']);self.assertEqual(s.state,'opening')
 def test_expired_or_invalid_deadlines_cannot_claim_positive_remaining_time(self):
  for deadline,expected in ((99.,0),(math.nan,None),(math.inf,None),(True,None),(None,None)):
   with self.subTest(deadline=deadline),patch.object(m.time,'monotonic',return_value=100.):
    s=self.server(post_arm_deadline_monotonic=deadline);self.assertEqual(s.startup_status_snapshot()['native_activity']['post_arm_remaining_seconds'],expected)
 def test_unknown_stage_and_nonretained_mode_never_claim_verified_gate(self):
  for fields in ({'post_arm_state':'private text','post_arm_verified':True},{'retain_sharing':False,'post_arm_state':'verified','post_arm_verified':True}):
   s=self.server(**fields);native=s.startup_status_snapshot()['native_activity'];self.assertFalse(native['post_arm_verified']);self.assertNotIn('private text',str(native))
 def test_retained_ready_without_post_arm_proof_never_starts_capture(self):
  s,b,events,closed=test_physical_guard.PhysicalGuardTests().make();self.addCleanup(s.close_backend)
  with self.assertRaisesRegex(RuntimeError,'Post-ARM mouse readiness'):
   s.call('desktop_start',{'physical_takeover':True,'interruption_policy':'retain-sharing'})
  self.assertNotIn('capture-start',events);self.assertNotIn('capture',events);self.assertIn('portal-close',events)
 def test_explicit_verified_stage_required_even_when_boolean_true(self):
  s=m.Server(test_control.Fake);s.interruption_policy='retain-sharing'
  for status in ({'active':True,'post_arm_verified':True,'post_arm_state':'waiting-motion'},{'active':True,'post_arm_verified':False,'post_arm_state':'verified'}):
   s.native_activity=types.SimpleNamespace(status=lambda:status)
   with self.assertRaises(RuntimeError):s.require_native_ready()
  s.native_activity=types.SimpleNamespace(status=lambda:{'active':True,'post_arm_verified':True,'post_arm_state':'verified'})
  s.require_native_ready()

 def test_new_native_yield_during_startup_capture_never_publishes_or_activates(self):
  for when in ('before','during','publication'):
   with self.subTest(when=when):
    s=m.Server(test_control.Fake);s.backend=test_control.Fake();s.backend.start();self.addCleanup(s.close_backend)
    s.state='opening';s.interruption_policy='retain-sharing';s.physical_takeover=True
    status={'active':True,'post_arm_verified':True,'post_arm_state':'verified'}
    s.native_activity=types.SimpleNamespace(status=lambda:status,close=lambda:None)
    captures=[];capture=s.backend.capture
    def interrupted():
     captures.append(True);png=capture()
     if when=='during':status['active']=False
     return png
    s.backend.capture=interrupted
    if when=='before':status['active']=False
    if when=='publication':
     content=s.capture_result(('opening',));status['active']=False
     result=s.fence_response({'id':1,'params':{'name':'desktop_start'}},{'id':1,'result':{'content':content}})
     self.assertTrue(result['result']['isError']);self.assertFalse(any(c['type']=='image' for c in result['result']['content']));self.assertEqual(s.state,'closed')
    else:
     with self.assertRaisesRegex(RuntimeError,'did not arm'):s.capture_result(('opening',))
     self.assertEqual(s.state,'opening')
     self.assertEqual(len(captures),0 if when=='before' else 1)

 def test_native_not_ready_or_operation_cancelled_never_advertises_input(self):
  s=m.Server(test_control.Fake);s.backend=test_control.Fake();s.backend.start();self.addCleanup(s.close_backend);s.state='active';s.physical_takeover=True
  s.native_activity=types.SimpleNamespace(status=lambda:{'active':False},close=lambda:None)
  status=s.status();self.assertFalse(status['active']);self.assertFalse(status['capture_allowed']);self.assertFalse(status['input_allowed']);self.assertTrue(status['sharing_active'])
  s.physical_takeover=False;s.backend.operation_cancelled=m.threading.Event();s.backend.operation_cancelled.set()
  self.assertFalse(s.status()['input_allowed']);self.assertEqual(s.state,'active')

 def test_settling_is_distinct_and_never_authorizes_challenge_or_control(self):
  s=self.server(calibration_state='settling',calibration_verified=False,post_arm_state='not-started',notice_phase='calibration',notice_requested=False,notice_acknowledged=False,notice_active=False)
  snapshot=s.startup_status_snapshot();native=snapshot['native_activity']
  self.assertEqual(native['calibration_state'],'settling');self.assertFalse(native['calibration_verified']);self.assertFalse(native['post_arm_verified'])
  self.assertFalse(native['calibration_notice']['requested']);self.assertFalse(native['calibration_notice']['request_acknowledged'])
  self.assertFalse(snapshot['active']);self.assertFalse(snapshot['capture_allowed']);self.assertFalse(snapshot['input_allowed']);self.assertEqual(s.state,'opening')

if __name__=='__main__':unittest.main()
