"""Exact multi-contact opt-in admission and shared private-context recovery."""
import time,unittest
from unittest.mock import patch
import test_keyboard_recovery as keyboard
import test_click_controller as adapter

class MultiContactAdapterTests(unittest.TestCase):
 def make(self,**extra):
  return adapter.m.Controller(lambda:True,lambda:None,lambda _:None,retain_sharing=True,
      pointer_source='touchpad',click_policy='pause-return',multi_contact_policy='pause-recover',**extra)
 def test_exact_ack_refuses_old_helper_and_malformed_reply(self):
  for reply,accepted in [('MULTICONTACT1_OK',True),('KEYPAUSE1_OK',False),('MULTICONTACT1_OK extra',False),(None,False)]:
   c=self.make();c.click_mode_acknowledged=True;c.helper_ready_at_monotonic=time.monotonic();sent=[];c._send=sent.append;c._read=lambda _,reply=reply:reply
   if accepted:c._negotiate_multi_contact();self.assertTrue(c.multi_contact_mode_acknowledged)
   else:
    with self.assertRaises(adapter.m.NativeFailure):c._negotiate_multi_contact()
    self.assertFalse(c.multi_contact_mode_acknowledged)
   self.assertEqual(sent,['MULTICONTACT1'])
 def test_constructor_never_silently_widens_mouse_or_close_policy(self):
  for args in ({'retain_sharing':True,'click_policy':'pause-return'}, {'retain_sharing':True,'pointer_source':'touchpad'}, {'pointer_source':'touchpad','click_policy':'pause-return'}):
   with self.assertRaises(ValueError):adapter.m.Controller(lambda:True,lambda:None,lambda _:None,multi_contact_policy='pause-recover',**args)
 def test_no_click_ack_or_expired_lease_refuses_before_sending(self):
  for fault in ('click','lease'):
   c=self.make();c.click_mode_acknowledged=fault!='click';c.helper_ready_at_monotonic=time.monotonic()-(601 if fault=='lease' else 0);sent=[];c._send=sent.append
   with self.assertRaises(adapter.m.NativeFailure):c._negotiate_multi_contact()
   self.assertEqual(sent,[])

class MultiContactRecoveryTests(unittest.TestCase):
 def make(self):
  fixture=keyboard.KeyboardRecoveryTests();s,b,d,n=fixture.make(True);self.addCleanup(fixture.doCleanups)
  s.native_keyboard_policy='close';s.native_multi_contact_policy='pause-recover';fixture.paused(s,n)
  return s,b,d,n
 def test_multicontact_only_refreshes_and_never_reclaims_pointer(self):
  s,b,d,n=self.make();self.assertTrue(s.return_after_quiet(n,1));self.assertEqual(d.events,[]);self.assertEqual(n.resumed,[1]);self.assertEqual(s.return_state,'context-refreshed')
 def test_workspace_overview_waits_inert_until_ordinary_and_quiet(self):
  s,b,d,n=self.make();ordinary=dict(b.value);b.value.update(kind='overview',window_id='shell-overview')
  self.assertFalse(s.return_after_quiet(n,1));self.assertEqual(d.captures,0);self.assertEqual(d.events,[])
  b.value=ordinary;b.value.update(window_id='new-workspace',epoch=13)
  with patch.object(keyboard.recovery.retained.m,'CONTEXT_RECOVERY_QUIET',.02):
   deadline=time.monotonic()+1.2
   while s.state!='active' and time.monotonic()<deadline:time.sleep(.01)
  self.assertEqual(s.state,'active');self.assertEqual(n.resumed,[1]);self.assertEqual(d.events,[]);self.assertEqual(d.captures,1)
 def test_old_adapter_cannot_claim_multicontact_ready(self):
  s,b,d,n=self.make();n.yielded=False
  with self.assertRaises(RuntimeError):s.require_native_ready()
 def test_option_is_explicit_and_default_closed(self):
  start=next(t for t in keyboard.recovery.retained.m.tools() if t['name']=='desktop_start')
  option=start['inputSchema']['properties']['multi_contact_policy'];self.assertEqual(option['default'],'close');self.assertEqual(option['enum'],['close','pause-recover'])
