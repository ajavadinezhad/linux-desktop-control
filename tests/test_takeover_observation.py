"""Read-only observation during takeover cannot become input authority."""
import json
import threading
import time
from types import SimpleNamespace
import unittest
import test_control
import test_context_recovery
import test_continuous_capture

m=test_control.m

class TakeoverObservationTests(unittest.TestCase):
    observer=test_continuous_capture.ContinuousCaptureTests.observer
    wait_frame=test_continuous_capture.ContinuousCaptureTests.wait_frame
    def make_watch(self):
        fixture=test_context_recovery.ContextRecoveryTests();self.addCleanup(fixture.doCleanups)
        s,b,d=fixture.make();s.native_activity.yielded=True
        d.observe_during_takeover=True;d.continuous_observer=True
        consent=s.consent_id
        d.takeover_capture_gate=lambda:s.takeover_capture_allowed(d,consent)
        d.takeover_capture_permitted=lambda:m.Desktop.takeover_capture_permitted(d)
        d._capture_once=lambda observation_check=None:m.Desktop._capture_once(d,observation_check=observation_check)
        d.frames=0
        d.pipeline=SimpleNamespace(get_clock=lambda:SimpleNamespace(get_time=lambda:0),get_base_time=lambda:0,
                                   set_state=lambda state:None)
        observer,q=self.observer(d)
        observer.permitted=d.takeover_capture_permitted
        s.begin_pause('pointer-motion');s.finish_pause()
        png=test_control.Fake.capture(d);q.put((png,250*m.Gst.MSECOND));self.wait_frame(observer)
        return fixture,s,b,d,observer,q,png

    def test_takeover_observe_is_read_only_and_does_not_resume_or_mint_tokens(self):
        f,s,b,d,o,q,png=self.make_watch()
        result=f.request(s,'desktop_observe')
        self.assertFalse(result.get('isError',False),result)
        meta=json.loads(result['content'][0]['text'])
        self.assertTrue(meta['observation_only']);self.assertFalse(meta['input_allowed'])
        self.assertFalse(meta['window_observation']['available']);self.assertIsNone(s.window_record)
        self.assertEqual(s.state,'paused');self.assertTrue(d.operation_cancelled.is_set())
        self.assertEqual(d.events,[]);self.assertEqual(d.resumes,0)
        refused=f.request(s,'desktop_action',{'action':{'type':'click','x':1,'y':1}})
        self.assertTrue(refused['isError']);self.assertEqual(d.events,[])

    def test_manual_pause_clears_live_observer_even_when_watch_enabled(self):
        f,s,b,d,o,q,png=self.make_watch()
        result=f.request(s,'desktop_pause')
        self.assertFalse(result.get('isError',False),result)
        self.assertIsNone(d.pipeline);self.assertIsNone(d.frame_observer);self.assertIsNone(o.latest)
        self.assertTrue(f.request(s,'desktop_observe')['isError'])

    def test_protected_context_blocks_frame_retention_and_publication(self):
        f,s,b,d,o,q,png=self.make_watch()
        b.value={'available':False,'reason':'locked'}
        self.assertFalse(d.takeover_capture_permitted())
        q.put((png,300*m.Gst.MSECOND))
        until=time.monotonic()+.5
        while o.latest is not None and time.monotonic()<until:time.sleep(.002)
        self.assertIsNone(o.latest)
        result=f.request(s,'desktop_observe')
        self.assertFalse(any(c['type']=='image' for c in result['content']))

    def test_manual_pause_or_new_context_after_capture_discards_pending_image(self):
        for change in ('manual','context','lease','replacement','stop'):
            f,s,b,d,o,q,png=self.make_watch()
            request={'id':1,'method':'tools/call','params':{'name':'desktop_observe','arguments':{}}}
            response=s.handle(request)
            self.assertTrue(any(c['type']=='image' for c in response['result']['content']))
            if change=='manual':s.manual_pause_requested=True
            elif change=='context':b.value=dict(b.value,epoch=900)
            elif change=='lease':s.native_activity.healthy=False
            elif change=='replacement':s.consent_id='replacement'
            else:d.cancelled.set()
            response=s.fence_response(request,response)
            self.assertFalse(any(c['type']=='image' for c in response['result']['content']),change)

    def test_change_wait_during_takeover_and_stale_stream_refusal(self):
        f,s,b,d,o,q,png=self.make_watch()
        revision=o.revision
        timer=threading.Timer(.02,lambda:q.put((png+b'new',300*m.Gst.MSECOND)));timer.start()
        r=f.request(s,'desktop_observe',{'after_stream_id':o.stream_id,'after_revision':revision,'wait_for_change_seconds':1})
        timer.join();self.assertFalse(r.get('isError',False),r)
        self.assertTrue(json.loads(r['content'][0]['text'])['change_wait']['changed_before_capture'])
        r=f.request(s,'desktop_observe',{'after_stream_id':'0'*32,'after_revision':0})
        self.assertTrue(r['isError']);self.assertFalse(any(c['type']=='image' for c in r['content']))

    def test_mapping_fault_and_auth_wait_suspend_watch_gate(self):
        f,s,b,d,o,q,png=self.make_watch()
        s.permission_wait_stage='preparing';self.assertFalse(d.takeover_capture_permitted())
        s.permission_wait_stage=None
        d.mapping_guard=lambda:(_ for _ in ()).throw(RuntimeError('mapping fault'))
        self.assertFalse(d.takeover_capture_permitted())

    def test_stop_during_takeover_change_wait_discards_image_promptly(self):
        f,s,b,d,o,q,png=self.make_watch()
        timer=threading.Timer(.02,d.cancelled.set);timer.start();started=time.monotonic()
        r=f.request(s,'desktop_observe',{'after_stream_id':o.stream_id,'after_revision':o.revision,'wait_for_change_seconds':30})
        timer.join();self.assertLess(time.monotonic()-started,.5)
        self.assertFalse(any(c['type']=='image' for c in r['content']))

    def test_opt_in_validation_happens_before_portal_start(self):
        for args in ({'observe_during_takeover':True},{'observe_during_takeover':'yes'}):
            s=m.Server(test_control.Fake);self.addCleanup(s.close_backend)
            with self.assertRaises(ValueError):s.call('desktop_start',args)
            self.assertIsNone(s.backend)

if __name__=='__main__':unittest.main()
