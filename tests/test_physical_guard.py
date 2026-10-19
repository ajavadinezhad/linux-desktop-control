"""Native guard integration with fake portal/helper; never launches pkexec."""
import json,threading,unittest
from types import SimpleNamespace
from test_control import m,Fake

class Bridge:
 def __init__(self,events):self.events=events;self.closed=False
 def call(self,*args):raise AssertionError('Legacy Clutter SetPhysicalGuard must never be called')
 def close(self):self.events.append('indicator-close');self.closed=True

class PhysicalGuardTests(unittest.TestCase):
 def make(self,reject=False,installed=True):
  events=[];closed=threading.Event()
  class Backend(Fake):
   def __init__(self):super().__init__();self.held=[]
   def start(self,defer_capture=False):events.append(('portal-start',defer_capture));super().start()
   def finish_start(self):events.append('capture-start')
   def capture(self):events.append('capture');return super().capture()
   def close(self):events.append('portal-close');self.held=[];super().close()
  s=m.Server(Backend);bridge=Bridge(events)
  class Native:
   def __init__(self,active,on_activity,on_fault,notice=None):self.notice=notice;self.active=active;self.on_activity=on_activity;self.on_fault=on_fault;self.ready=False;self.closed=False
   def start(self):
    self.assert_owned=s.native_activity is self;events.append('native-arm');assert self.active() and self.assert_owned
    if reject:raise RuntimeError('administrator authorization denied')
    self.ready=True;return self
   def status(self):return {'active':self.ready and not self.closed,'supported':self.ready,'raw_device_fds':False}
   def close(self):
    self.closed=True;self.ready=False;events.append('native-close');assert not s.backend.held;closed.set()
  def validate():
   events.append('validate-helper')
   if not installed:raise RuntimeError('trusted native helper missing')
  s.native_activity_module=lambda:SimpleNamespace(validate_helper=validate,Controller=Native)
  class Notice:
   def __init__(self):events.append('notice-created')
   def show(self,reset=False):events.append(('notice-show',reset))
   def close(self):events.append('notice-close')
   def status(self):return {'warning':None}
  s.calibration_notice_module=lambda:SimpleNamespace(CalibrationNotice=Notice)
  def show():events.append('indicator-bind');s.indicator=bridge
  s.show_indicator=show
  self.addCleanup(s.close_backend)
  return s,bridge,events,closed

 def test_default_never_validates_or_launches_native_observer(self):
  s,b,e,_=self.make();s.call('desktop_start',{});self.assertNotIn('validate-helper',e);self.assertNotIn('native-arm',e);self.assertIn(('portal-start',False),e);self.assertFalse(s.status()['physical_takeover']['enabled'])

 def test_missing_trusted_helper_refused_before_backend_or_portal(self):
  s,b,e,_=self.make(installed=False)
  with self.assertRaisesRegex(RuntimeError,'helper missing'):s.call('desktop_start',{'physical_takeover':True})
  self.assertEqual(e,['validate-helper']);self.assertIsNone(s.backend)

 def test_consent_then_arm_then_capture_no_legacy_filter_call(self):
  s,b,e,_=self.make();content=s.call('desktop_start',{'physical_takeover':True});meta=json.loads(content[0]['text']);self.assertTrue(meta['physical_takeover']['enabled']);self.assertFalse(meta['native_activity']['raw_device_fds'])
  self.assertLess(e.index('validate-helper'),e.index(('portal-start',True)));self.assertLess(e.index(('portal-start',True)),e.index('native-arm'));self.assertLess(e.index(('portal-start',True)),e.index('notice-created'));self.assertLess(e.index('notice-created'),e.index('native-arm'));self.assertIsNotNone(s.native_activity.notice);self.assertLess(e.index('native-arm'),e.index('indicator-bind'));self.assertLess(e.index('native-arm'),e.index('capture-start'));self.assertLess(e.index('capture-start'),e.index('capture'))

 def test_denied_or_lost_arm_closes_portal_before_observer_wait_no_capture(self):
  s,b,e,_=self.make(reject=True)
  with self.assertRaisesRegex(RuntimeError,'authorization denied'):s.call('desktop_start',{'physical_takeover':True})
  self.assertNotIn('capture-start',e);self.assertNotIn('capture',e);self.assertLess(e.index('portal-close'),e.index('native-close'));self.assertFalse(s.backend.active);self.assertIsNone(s.native_activity)

 def test_activity_and_fault_cancel_without_indicator_bound(self):
  for fault in (False,True):
   with self.subTest(fault=fault):
    s,b,e,closed=self.make();s.state='opening';s.ensure_backend();s.backend.start(defer_capture=True);s.enable_physical_guard();native=s.native_activity;self.assertIsNone(s.indicator);before=s.generation;s.backend.held=['pressed']
    if fault:native.on_fault('peer gone')
    else:native.on_activity()
    self.assertTrue(closed.wait(2));self.assertTrue(s.backend.cancelled.is_set());self.assertGreater(s.generation,before);self.assertFalse(s.backend.active);self.assertLess(e.index('portal-close'),e.index('native-close'));self.assertFalse(s.status()['physical_takeover']['enabled'])
    if fault:self.assertIn('fault',s.physical_takeover_warning)

 def test_stale_native_callback_cannot_close_new_session(self):
  s,b,e,_=self.make();s.call('desktop_start',{'physical_takeover':True});old=s.native_activity;s.close_backend();s.call('desktop_start',{});before=s.generation;old.on_activity();self.assertEqual(s.generation,before);self.assertTrue(s.backend.active)

 def test_active_default_session_cannot_silently_opt_in(self):
  s,b,e,_=self.make();s.call('desktop_start',{})
  with self.assertRaisesRegex(RuntimeError,'before a new consent'):s.call('desktop_start',{'physical_takeover':True})
  self.assertNotIn('native-arm',e);self.assertFalse(s.physical_takeover)

 def test_schema_default_off_describes_admin_and_raw_fd_boundary(self):
  schema=next(t for t in m.tools() if t['name']=='desktop_start')['inputSchema']['properties']['physical_takeover'];self.assertIs(schema['default'],False);self.assertIn('administrator',schema['description']);self.assertIn('never raw input',schema['description'])
  s,b,e,_=self.make()
  with self.assertRaisesRegex(ValueError,'boolean'):s.call('desktop_start',{'physical_takeover':1})
  self.assertEqual(e,[])

 def test_desktop_deferred_start_never_opens_pipewire_or_captures(self):
  from test_monitor_mapping import Bus,state
  d=object.__new__(m.Desktop);d.lock=threading.RLock();d.session=None;d.cancelled=threading.Event();events=[]
  d.close=lambda:setattr(d,'session',None)
  mapping_bus=Bus(state(scale=1.,origin=(0,0),size=(1920,1080)))
  def mapping_call(*args):
   events.append('mapping-read');return mapping_bus.mapping_call(*args)
  d.bus=SimpleNamespace(signal_subscribe=lambda *a:1,call_with_unix_fd_list_sync=lambda *a:events.append('pipewire'),mapping_call=mapping_call)
  def request(interface,method,*args):
   events.append(method)
   if method=='CreateSession':return {'session_handle':'/fake'}
   if method=='Start':return {'devices':3,'streams':[(1,{'position':(0,0),'logical_size':(1920,1080)})]}
   return {}
  d.request=request;d.finish_start=lambda:events.append('capture-start')
  d.start(defer_capture=True);self.assertNotIn('pipewire',events);self.assertNotIn('capture-start',events);self.assertIn('Start',events)
  self.assertLess(events.index('Start'),events.index('mapping-read'));self.assertTrue(callable(d.mapping_guard))

 def test_notice_never_constructed_before_personal_portal_consent(self):
  s,b,e,_=self.make();s.state='opening';s.ensure_backend()
  with self.assertRaisesRegex(RuntimeError,'Personal portal consent'):s.enable_physical_guard()
  self.assertNotIn('notice-created',e)

if __name__=='__main__':unittest.main()
