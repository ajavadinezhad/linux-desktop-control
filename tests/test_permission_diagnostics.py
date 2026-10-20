import json,time,unittest
import test_permission_wait as fixture
import test_control as control

class PermissionDiagnosticsTests(unittest.TestCase):
 def test_blocked_fixed_categories_persist_after_cleanup_and_do_not_export_other_data(self):
  none={'auth_state':'none','origin_window_id':'window-1','attempt_id':None,'action_category':'none'}
  for reason in ('unknown-system-ui','locked','greeter','auth-observer-unsupported','observer-unavailable','polkit-dialog-unavailable','origin-unavailable','origin-changed','modal-mismatch'):
   s,b,d,events,auth=fixture.PermissionWaitTests().make([none,dict(none,auth_state='blocked',reason=reason,private='SECRET-PASSWORD-AND-TITLE')])
   try:
    result=fixture.PermissionWaitTests().action(s);self.assertTrue(result['result']['isError'])
    self.assertEqual(s.status()['permission_wait_reason'],'blocked-'+reason)
    self.assertEqual(s.status()['permission_wait_failure_stage'],'waiting-for-prompt')
    s.close_backend();self.assertEqual(s.status()['permission_wait_reason'],'blocked-'+reason)
    self.assertNotIn('SECRET-PASSWORD-AND-TITLE',json.dumps(result));self.assertNotIn('capture',events)
   finally:s.shutdown()
 def test_unknown_observer_reason_and_exception_are_reduced_to_fixed_categories(self):
  none={'auth_state':'none','origin_window_id':'window-1','attempt_id':None,'action_category':'none'}
  s,b,d,events,auth=fixture.PermissionWaitTests().make([none,dict(none,auth_state='blocked',reason='SECRET')])
  try:
   result=fixture.PermissionWaitTests().action(s);self.assertEqual(s.permission_wait_reason,'observer-invalid-state');self.assertNotIn('SECRET',json.dumps(result))
  finally:s.shutdown()
  s,b,d,events,auth=fixture.PermissionWaitTests().make()
  try:
   record=s.prepare_permission_wait(b.context());b.auth_state=lambda:(_ for _ in ()).throw(RuntimeError('SECRET'))
   with self.assertRaises(RuntimeError):s.permission_state(record)
   self.assertEqual(s.permission_wait_reason,'observer-unavailable');self.assertNotIn('SECRET',json.dumps(s.status()))
  finally:s.shutdown()
 def test_first_diagnostic_wins_and_new_consent_resets_it(self):
  s=control.m.Server(control.Fake);s.call('desktop_start',{})
  try:
   s.permission_wait_stage='waiting-for-human'
   with self.assertRaises(RuntimeError):s.permission_fail('attempt-changed')
   with self.assertRaises(RuntimeError):s.permission_fail('cancelled')
   s.call('desktop_close',{});self.assertEqual(s.status()['permission_wait_reason'],'attempt-changed')
   self.assertEqual(s.status()['permission_wait_failure_stage'],'waiting-for-human')
   s.call('desktop_start',{});self.assertIsNone(s.status()['permission_wait_reason']);self.assertIsNone(s.status()['permission_wait_failure_stage'])
  finally:s.shutdown()
 def test_cancel_deadline_native_lease_and_origin_have_distinct_fixed_reasons(self):
  for cause,reason in [('cancel','cancelled'),('deadline','deadline-expired'),('native','native-observer-ended'),('lease','lease-ended'),('origin','origin-changed')]:
   s,b,d,events,auth=fixture.PermissionWaitTests().make()
   try:
    record=s.prepare_permission_wait(b.context())
    if cause=='cancel':d.cancelled.set()
    elif cause=='deadline':record['deadline']=time.monotonic()-1
    elif cause=='native':s.native_activity.status=lambda:{'active':False}
    elif cause=='lease':s.native_activity._yield_authorized=lambda:False
    else:b.auth_state=lambda:{'auth_state':'none','origin_window_id':'SECRET-OTHER-ORIGIN'}
    with self.assertRaises(RuntimeError):s.permission_state(record)
    self.assertEqual(s.permission_wait_reason,reason);self.assertNotIn('SECRET',json.dumps(s.status()))
   finally:s.shutdown()
 def test_generic_authentication_waits_only_and_unknown_category_refuses(self):
  none={'auth_state':'none','origin_window_id':'window-1','attempt_id':None,'action_category':'none'}
  visible=dict(none,auth_state='visible',attempt_id='a'*32,action_category='system-authentication')
  s,b,d,events,auth=fixture.PermissionWaitTests().make([none,visible,dict(none,attempt_id='a'*32)])
  try:
   result=fixture.PermissionWaitTests().action(s);self.assertFalse(result['result'].get('isError',False),result)
   self.assertEqual(events.count('click'),1);self.assertEqual(events.count('capture'),1);self.assertIsNone(s.permission_wait_reason)
  finally:s.shutdown()
  s,b,d,events,auth=fixture.PermissionWaitTests().make([none,visible,dict(visible,action_category='unexpected-category')])
  try:
   result=fixture.PermissionWaitTests().action(s);self.assertTrue(result['result']['isError']);self.assertEqual(s.permission_wait_reason,'attempt-unsupported')
   self.assertEqual(s.permission_wait_failure_stage,'waiting-for-human');self.assertNotIn('capture',events)
  finally:s.shutdown()

 def test_owned_terminal_cause_survives_observer_detachment(self):
  s,b,d,events,auth=fixture.PermissionWaitTests().make()
  try:
   record=s.prepare_permission_wait(b.context())
   s.invalidate(expected_native=s.native_activity,warning='native');s.close_backend()
   with self.assertRaises(RuntimeError):s.permission_state(record)
   self.assertEqual(s.permission_wait_reason,'native-observer-ended')
  finally:s.shutdown()

 def test_old_loaded_observer_revisions_refuse_before_activation(self):
  for revision in (0,1,2):
   s,b,d,events,auth=fixture.PermissionWaitTests().make();b.auth_wait_protocol=revision
   try:
    result=fixture.PermissionWaitTests().action(s);self.assertTrue(result['result']['isError'])
    self.assertNotIn('click',events);self.assertNotIn('auth-begin',events);self.assertNotIn('capture',events)
   finally:s.shutdown()
