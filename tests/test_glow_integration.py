import unittest
from test_control import m,Fake
class GlowIntegrationTests(unittest.TestCase):
 def test_opt_in_is_explicit_and_only_after_active_consented_capture(self):
  for enabled in (False,True):
   s=m.Server(Fake);calls=[];s.show_cursor_glow=lambda:calls.append(s.status()['active'])
   s.call('desktop_start',{'cursor_glow':enabled})
   self.assertEqual(calls,[True] if enabled else []);s.call('desktop_close',{})
 def test_invalid_opt_in_never_starts_backend(self):
  s=m.Server(Fake)
  with self.assertRaises(ValueError):s.call('desktop_start',{'cursor_glow':'yes'})
  self.assertIsNone(s.backend)
 def test_failed_restoration_keeps_live_status_and_refuses_new_glow(self):
  s=m.Server(Fake);s.call('desktop_start',{})
  class Glow:
   running=True
   def close(self):raise RuntimeError('restoration pending')
   def status(self):return {'active':self.running,'restored':None,'restoration_pending':True}
  glow=Glow();s.cursor_glow=glow;s.close_backend()
  self.assertTrue(s.status()['cursor_glow']['active']);glow.running=False
  self.assertFalse(s.status()['cursor_glow']['active']);self.assertIn('pending',s.status()['cursor_glow_warning'])
  with self.assertRaises(RuntimeError):s.show_cursor_glow()
