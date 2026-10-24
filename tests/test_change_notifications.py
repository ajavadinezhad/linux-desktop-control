"""Bounded, metadata-only subscriptions; no desktop or model calls."""
import io
import json
import threading
import time
import unittest
from types import SimpleNamespace
import test_control
import test_context_recovery

m=test_control.m
n=m._change_notifications

class ChangeNotificationTests(unittest.TestCase):
    def make(self):
        fixture=test_context_recovery.ContextRecoveryTests();self.addCleanup(fixture.doCleanups)
        s,b,d=fixture.make();d.continuous_observer=True
        info={'stream_id':'a'*32,'revision':1,'frame_age_ms':4,'running':True,'failed':False,'buffered_frames':1}
        d.frame_observer=SimpleNamespace(snapshot=lambda:dict(info),close=lambda:True)
        return s,b,d,info

    def request(self,s,method,params=None):
        return s.handle({'jsonrpc':'2.0','id':1,'method':method,'params':params or {}})

    def subscribe(self,s):return self.request(s,'resources/subscribe',{'uri':n.URI})

    def test_capabilities_and_resource_discovery_keep_seven_tools(self):
        s=m.Server(test_control.Fake);self.addCleanup(s.close_backend)
        self.assertTrue(self.request(s,'initialize')['result']['capabilities']['resources']['subscribe'])
        self.assertEqual(len(m.tools()),7)
        self.assertEqual(self.request(s,'resources/list')['result']['resources'][0]['uri'],n.URI)
        self.assertIn('error',self.subscribe(s));self.assertIsNone(s.backend)

    def test_explicit_subscription_is_idempotent_and_expires_with_consent(self):
        s,b,d,info=self.make();self.assertIsNone(s.change_notification_snapshot())
        self.assertIn('result',self.subscribe(s));owner=s.change_subscription
        self.assertIn('result',self.subscribe(s));self.assertIs(s.change_subscription,owner)
        self.assertIsNotNone(s.change_notification_snapshot())
        s.consent_id='replacement'
        self.assertIsNone(s.change_notification_snapshot());self.assertIsNone(s.change_subscription)

    def test_unsubscribe_and_closed_lease_clear_pending_hints(self):
        for fault in ('unsubscribe','cancelled','lease'):
            s,b,d,info=self.make();self.subscribe(s)
            if fault=='unsubscribe':self.request(s,'resources/unsubscribe',{'uri':n.URI})
            elif fault=='cancelled':d.cancelled.set()
            else:s.native_activity.healthy=False
            self.assertIsNone(s.change_notification_snapshot(),fault)

    def test_storm_is_coalesced_to_latest_and_does_not_queue(self):
        state=[('owner','active','stream',1)];sent=[]
        notifier=n.ChangeNotifier(lambda:state[0],lambda owner:sent.append(owner) or True)
        self.assertTrue(notifier.poll(1))
        for revision in range(2,1002):state[0]=('owner','active','stream',revision);self.assertFalse(notifier.poll(1.1))
        self.assertEqual(sent,['owner']);self.assertTrue(notifier.poll(2))
        self.assertEqual(notifier.last_key,('owner','active','stream',1001))
        self.assertFalse(notifier.poll(3));notifier.close();self.assertFalse(notifier.poll(4))

    def test_no_raw_frame_text_titles_coordinates_or_tokens_on_wire(self):
        s,b,d,info=self.make();self.subscribe(s)
        t=m.StdioTransport(s);t.output_stream=io.StringIO()
        self.assertTrue(t.send_change_notification(s.change_subscription))
        self.assertEqual(json.loads(t.output_stream.getvalue()),{'jsonrpc':'2.0','method':'notifications/resources/updated','params':{'uri':n.URI}})
        resource=self.request(s,'resources/read',{'uri':n.URI})['result']['contents'][0]
        payload=json.loads(resource['text']);self.assertFalse(payload['input_authority']);self.assertFalse(payload['contains_pixels'])
        self.assertFalse(payload['model_wake_supported'])
        for bad in ('window_id','observation_id','data','title','rect','pixels'):
            self.assertNotIn('"'+bad+'"',resource['text'])
        self.assertEqual(d.events,[])

    def test_publication_age_and_revision_are_hints_not_model_seen_claims(self):
        s,b,d,info=self.make();d.capture_info={'observer_stream_id':'a'*32,'content_revision':1}
        s.note_observation_publication();value=s.change_resource()
        self.assertFalse(value['changed_since_last_publication'])
        info['revision']=2;self.assertTrue(s.change_resource()['changed_since_last_publication'])
        self.assertIn('age_ms',value['last_published_observation'])
        s.consent_id='new';self.assertIsNone(s.change_resource()['last_published_observation'])

    def test_manual_pause_and_auth_wait_return_no_stream_metadata(self):
        s,b,d,info=self.make();self.subscribe(s)
        s.manual_pause_requested=True;s.state='paused'
        self.assertIsNone(s.change_resource()['stream'])
        s.manual_pause_requested=False;s.state='auth-waiting'
        self.assertIsNone(s.change_resource()['stream'])

    def test_pending_notice_rechecks_unsubscribe_at_output_lock(self):
        s,b,d,info=self.make();self.subscribe(s);owner=s.change_subscription
        t=m.StdioTransport(s);t.output_stream=io.StringIO();done=threading.Event();results=[]
        with t.output_lock:
            worker=threading.Thread(target=lambda:(results.append(t.send_change_notification(owner)),done.set()))
            worker.start();self.assertFalse(done.wait(.02));s.change_subscription=None
        worker.join(1);self.assertEqual(results,[False]);self.assertEqual(t.output_stream.getvalue(),'')

    def test_bad_resources_do_not_close_or_act(self):
        s,b,d,info=self.make()
        for method,params in [('resources/read',{'uri':'file:///private'}),('resources/subscribe',{'uri':n.URI,'extra':True})]:
            self.assertIn('error',self.request(s,method,params));self.assertFalse(d.cancelled.is_set());self.assertEqual(d.events,[])

    def test_transport_pushes_changes_without_an_observe_request(self):
        import test_startup_status
        s,b,d,info=self.make()
        source=test_startup_status.Input();output=test_startup_status.Output()
        d.loop=SimpleNamespace(quit=lambda:None)
        transport=m.StdioTransport(s);transport.change_notifier.interval=.01
        worker=threading.Thread(target=transport.run,args=(source,output),daemon=True);worker.start()
        try:
            source.lines.put(json.dumps({'jsonrpc':'2.0','id':50,'method':'resources/subscribe','params':{'uri':n.URI}}))
            messages=[output.lines.get(timeout=1),output.lines.get(timeout=1)]
            self.assertTrue(any(x.get('id')==50 for x in messages))
            self.assertTrue(any(x.get('method')=='notifications/resources/updated' for x in messages))
            info['revision']=99
            update=output.lines.get(timeout=1)
            self.assertEqual(update['method'],'notifications/resources/updated')
            self.assertEqual(d.events,[])
            source.lines.put(json.dumps({'jsonrpc':'2.0','id':51,'method':'resources/unsubscribe','params':{'uri':n.URI}}))
            self.assertEqual(output.lines.get(timeout=1)['id'],51)
            info['revision']=100;self.assertFalse(transport.change_notifier.poll(time.monotonic()+2))
        finally:
            source.lines.put(None);worker.join(2)
        self.assertFalse(worker.is_alive())

if __name__=='__main__':unittest.main()
