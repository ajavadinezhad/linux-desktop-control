import json,unittest
from test_control import m,Fake
class Bridge:
 def __init__(self,events,capable=True,reject=False):self.events=events;self.capable=capable;self.reject=reject;self.bound=True;self.nonce='authenticated-nonce';self.closed=False
 def call(self,method,sig,args):
  self.events.append((method,sig,args))
  if method=='GetDiagnostics':return (json.dumps({'physical_activity_candidate':self.capable}),)
  if method=='SetPhysicalGuard' and args[-1] and self.reject:raise RuntimeError('enable reply lost')
  return (True,)
 def set_physical_guard(self,enabled,on_activity=None):self.events.append(('local-guard',enabled));self.on_activity=on_activity
 def update(self):self.events.append('active-update')
 def close(self):self.events.append('unbind-close');self.closed=True
class PhysicalGuardTests(unittest.TestCase):
 def make(self,capable=True,reject=False):
  events=[]
  class Backend(Fake):
   def start(self):events.append('portal-start');super().start()
   def close(self):events.append('portal-close');super().close()
  s=m.Server(Backend);b=Bridge(events,capable,reject)
  def preflight():events.append('preflight');return b
  s.preflight_context=preflight
  def show():events.append('bind');s.indicator=b
  s.show_indicator=show
  return s,b,events
 def test_default_never_requests_metadata_monitoring(self):
  s,b,e=self.make();s.call('desktop_start',{});self.assertNotIn('preflight',e);self.assertFalse(any(isinstance(v,tuple) and v[0]=='SetPhysicalGuard' for v in e));self.assertFalse(s.physical_takeover);s.close_backend()
 def test_unsupported_explicit_request_refused_before_portal(self):
  s,b,e=self.make(capable=False)
  with self.assertRaisesRegex(RuntimeError,'no sharing requested'):s.call('desktop_start',{'physical_takeover':True})
  self.assertNotIn('portal-start',e);self.assertFalse(s.status()['active'])
 def test_opt_in_follows_preflight_portal_bind_and_active_update_authenticated(self):
  s,b,e=self.make();s.call('desktop_start',{'physical_takeover':True})
  enable=('SetPhysicalGuard','(sb)',(b.nonce,True));self.assertLess(e.index('preflight'),e.index('portal-start'));self.assertLess(e.index('portal-start'),e.index('bind'));self.assertLess(e.index('bind'),e.index('active-update'));self.assertLess(e.index('active-update'),e.index(('local-guard',True)));self.assertLess(e.index(('local-guard',True)),e.index(enable));self.assertTrue(s.status()['physical_takeover']['enabled'])
  s.close_backend();disable=('SetPhysicalGuard','(sb)',(b.nonce,False));self.assertLess(e.index(('local-guard',False)),e.index(disable));self.assertLess(e.index(disable),e.index('unbind-close'));self.assertLess(e.index('unbind-close'),e.index('portal-close'));self.assertFalse(s.physical_takeover)
 def test_lost_enable_reply_disarms_unbinds_and_closes(self):
  s,b,e=self.make(reject=True)
  with self.assertRaisesRegex(RuntimeError,'reply lost'):s.call('desktop_start',{'physical_takeover':True})
  self.assertIn(('SetPhysicalGuard','(sb)',(b.nonce,False)),e);self.assertTrue(b.closed);self.assertFalse(s.backend.active);self.assertFalse(s.physical_takeover)
 def test_schema_is_explicit_opt_in_and_rejects_non_boolean(self):
  schema=next(t for t in m.tools() if t['name']=='desktop_start')['inputSchema']['properties']['physical_takeover'];self.assertEqual(schema['default'],False);self.assertIn('metadata',schema['description'])
  s,b,e=self.make()
  with self.assertRaisesRegex(ValueError,'boolean'):s.call('desktop_start',{'physical_takeover':1})
  self.assertNotIn('portal-start',e)
 def test_explicit_disarm_failure_still_unbinds_and_closes(self):
  s,b,e=self.make();s.call('desktop_start',{'physical_takeover':True});original=b.call
  def fail_disarm(method,sig,args):
   if method=='SetPhysicalGuard' and args[-1] is False:raise RuntimeError('disconnected')
   return original(method,sig,args)
  b.call=fail_disarm;s.close_backend();self.assertTrue(b.closed);self.assertFalse(s.backend.active);self.assertFalse(s.physical_takeover);self.assertIn('unconfirmed',s.status()['physical_takeover_warning']);self.assertIn(('local-guard',False),e);self.assertIsNone(b.on_activity)
 def test_unbound_indicator_never_sends_enable(self):
  s,b,e=self.make();s.indicator=b;b.bound=False
  with self.assertRaisesRegex(RuntimeError,'not bound'):s.enable_physical_guard()
  self.assertFalse(any(isinstance(v,tuple) and v[0]=='SetPhysicalGuard' for v in e))

 def test_local_activity_callback_is_bound_to_that_bridge_before_enable(self):
  s,b,e=self.make();lost=[];s.foreground_lost=lambda expected:lost.append(expected);s.call('desktop_start',{'physical_takeover':True});b.on_activity();self.assertEqual(lost,[b]);s.close_backend();self.assertIsNone(b.on_activity)
