import importlib.util,json,pathlib,unittest
from unittest.mock import patch
from test_control import m
p=pathlib.Path(m.__file__).with_name('toolbar_bridge.py')
spec=importlib.util.spec_from_file_location('toolbar_bridge_test',p);bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
class Reply:
    def __init__(self,*values):self.values=values
    def unpack(self):return self.values
class Bus:
    def __init__(self):self.calls=[];self.subs=[];self.unsub=[];self.reject=None
    def call_sync(self,dest,path,interface,method,args,*rest):
        self.calls.append((dest,path,interface,method,args.unpack()))
        if method==self.reject:raise RuntimeError('missing service')
        if method=='GetNameOwner':return Reply(':1.25')
        if method=='GetDiagnostics':return Reply('{"visible":true,"protocol_version":2}')
        return Reply(True)
    def signal_subscribe(self,*args):self.subs.append(args);return len(self.subs)
    def signal_unsubscribe(self,subscription):self.unsub.append(subscription)
class ToolbarTests(unittest.TestCase):
    def make(self):
        bus=Bus();events=[];state={'control_state':'active','control_epoch':3,'portal_closed_confirmed':False}
        b=bridge.ToolbarBridge(lambda:state,lambda event,expected_epoch=None:events.append(event),bus)
        with patch.object(bridge.threading,'Thread'):b.start()
        return b,bus,events,state
    def signal(self,b,nonce=None,event='pause',epoch=3,sequence=1,sender=':1.25'):
        b._signal(None,sender,bridge.PATH,bridge.INTERFACE,'Control',Reply(nonce or b.nonce,event,epoch,sequence))
    def test_pins_unique_owner_and_only_fixed_public_metadata(self):
        b,bus,events,state=self.make();state['secret']='private';b._update()
        self.assertEqual(bus.subs[0][0],':1.25');self.assertEqual(bus.calls[1][0],':1.25')
        self.assertNotIn('private',str(bus.calls[-1]));self.assertEqual(b.diagnostics(),{'visible':True,'protocol_version':2})
        b.close();self.assertEqual(bus.unsub,[1,2]);self.assertEqual(bus.calls[-1][3],'Unbind')
    def test_nonce_sender_epoch_sequence_and_event_validation(self):
        b,bus,events,state=self.make()
        self.signal(b,nonce='wrong');self.signal(b,sender=':1.99');self.signal(b,event='unknown')
        self.signal(b,epoch=2,sequence=1);self.signal(b,sequence=1)
        self.assertEqual(events,[])
        self.signal(b,sequence=2);self.signal(b,sequence=2);self.assertEqual(events,['pause'])
        state['control_epoch']=4;self.signal(b,event='continue',epoch=4,sequence=3)
        self.assertEqual(events,['pause','continue'])
    def test_owner_loss_or_update_failure_stops_once(self):
        for mode in ('owner','update'):
            b,bus,events,state=self.make()
            if mode=='owner':b._owner_changed(None,None,None,None,None,Reply(bridge.NAME,':1.25',''))
            else:
                bus.reject='Update'
                with self.assertRaises(RuntimeError):b._update()
                b.fail()
            b.fail();self.assertTrue(b.failed);self.assertEqual(events,['stop'])
    def test_missing_extension_refuses_control_with_explicit_instruction(self):
        bus=Bus();bus.reject='Bind';events=[];b=bridge.ToolbarBridge(lambda:{},lambda event,expected_epoch=None:events.append(event),bus)
        with self.assertRaisesRegex(RuntimeError,'logout/login'):b.start()
        self.assertFalse(b.bound);self.assertTrue(b.failed);self.assertEqual(events,['stop']);self.assertEqual(bus.unsub,[1,2])
    def test_closed_bridge_ignores_controls_and_does_not_spuriously_stop(self):
        b,bus,events,state=self.make();b.close();self.signal(b);b.fail();self.assertEqual(events,[])
    def test_activity_is_fixed_enum_and_does_not_leak_task_text(self):
        for activity in ('working','observe','plan_ack','waiting_executor','consent','wait','end'):
            view=bridge.toolbar_view({'control_state':'active','next_required_action':activity,'task':{'intent':'private'}})
            self.assertEqual(view['activity'],activity);self.assertNotIn('private',str(view))
        self.assertEqual(bridge.toolbar_view({'next_required_action':'private'})['activity'],'waiting_executor')
    def test_preflight_ownership_conflict_does_not_request_logout(self):
        bus=Bus();original=bus.call_sync
        def call(*args):
            if args[3]=='GetDiagnostics':return Reply('{"owner":":1.77"}')
            return original(*args)
        bus.call_sync=call;bus.get_unique_name=lambda:':1.88'
        b=bridge.ToolbarBridge(lambda:{},lambda *args:None,bus)
        with self.assertRaisesRegex(RuntimeError,'Another desktop session owns') as error:b.preflight()
        self.assertIn('extension is loaded',str(error.exception))
        self.assertEqual(bus.calls,[])
    def test_sanitizes_monitor_and_unknown_state(self):
        v=bridge.toolbar_view({'control_state':'private','control_epoch':True,'monitor':{'x':0,'y':0,'width':float('nan'),'height':2}})
        self.assertEqual(v['state'],'stopped');self.assertFalse(v['visible']);self.assertEqual(v['epoch'],0);self.assertNotIn('monitor',v)
        v=bridge.toolbar_view({'control_state':'paused','portal_closed_confirmed':True,'monitor':{'x':-1920,'y':0,'width':1920,'height':1080}})
        self.assertTrue(v['can_continue']);self.assertEqual(v['monitor']['x'],-1920)
    def test_publisher_failure_dispatches_stop(self):
        b,bus,events,state=self.make();bus.reject='Update'
        with patch.object(b.closed,'wait',return_value=False):b.publish()
        self.assertEqual(events,['stop'])

if __name__=='__main__':unittest.main()

class ToolbarMappingTests(unittest.TestCase):
    def test_starting_visibility_requires_completed_consent(self):
        for ready in (False,True):
            view=bridge.toolbar_view({'control_state':'starting','toolbar_session_ready':ready})
            self.assertEqual(view['visible'],ready)
    def test_closure_warning_is_boolean_and_never_raw_error(self):
        for status in ({'control_state':'active','cleanup_warning':'private failure'},
                       {'control_state':'paused','portal_closed_confirmed':False}):
            view=bridge.toolbar_view(status)
            self.assertIs(view['closure_warning'],True);self.assertNotIn('private',json.dumps(view))
        self.assertFalse(bridge.toolbar_view({'control_state':'paused','portal_closed_confirmed':True})['closure_warning'])
    def test_wait_accepts_one_mapped_allocated_actor(self):
        b=bridge.ToolbarBridge(lambda:{},lambda e:None)
        b.diagnostics=lambda:{'visible':True,'actors':1,'rect':[0,0,400,60]}
        self.assertEqual(b.wait_visible()['actors'],1)
    def test_wait_rejects_missing_duplicate_or_unallocated_actor(self):
        for data in ({'visible':False,'actors':1,'rect':[0,0,400,60]},
                     {'visible':True,'actors':2,'rect':[0,0,400,60]},
                     {'visible':True,'actors':1,'rect':[0,0,0,60]},
                     {'visible':True,'actors':1,'rect':[0,0,float('nan'),60]}):
            events=[];b=bridge.ToolbarBridge(lambda:{},events.append);b.diagnostics=lambda:data
            with self.assertRaisesRegex(RuntimeError,'input refused'):b.wait_visible(timeout=0)
            self.assertTrue(b.failed);self.assertEqual(events,['stop'])
    def test_wait_checks_cancellation_before_diagnostics(self):
        b=bridge.ToolbarBridge(lambda:{},lambda e:None)
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):b.wait_visible(cancel)

class EmergencyEpochTests(unittest.TestCase):
    make=ToolbarTests.make
    signal=ToolbarTests.signal
    def test_authentic_stop_is_honored_despite_stale_display_epoch(self):
        b,bus,events,state=self.make()
        self.signal(b,event='stop',epoch=1,sequence=2)
        self.assertEqual(events,['stop'])

class StopWithoutStatusTests(unittest.TestCase):
    make=ToolbarTests.make
    signal=ToolbarTests.signal
    def test_stop_does_not_wait_for_status_lookup(self):
        b,bus,events,state=self.make()
        def unavailable():raise RuntimeError('status unavailable')
        b.status=unavailable
        self.signal(b,event='stop',epoch=0,sequence=1)
        self.assertEqual(events,['stop']);self.assertFalse(b.failed)

class ToolbarProtocolTests(unittest.TestCase):
 def test_old_loaded_toolbar_refuses_before_consent_or_binding(self):
  bus=Bus();original=bus.call_sync
  def call(*args):
   if args[3]=='GetDiagnostics':return Reply('{"visible":false,"owner":null}')
   return original(*args)
  bus.call_sync=call
  b=bridge.ToolbarBridge(lambda:{},lambda *args:None,bus)
  with self.assertRaisesRegex(RuntimeError,'not loaded'):b.preflight()
  self.assertFalse(b.bound);self.assertFalse(bus.calls)
