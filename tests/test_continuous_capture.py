"""Capture adapter and MCP waits with synthetic frames and fake GUI guards."""
import json
import queue
import threading
import time
import unittest
from types import SimpleNamespace
import test_control
import test_context_recovery as context_fixture

m=test_control.m


class ContinuousCaptureTests(unittest.TestCase):
    def observer(self,backend):
        q=queue.Queue()
        def read(timeout):
            try:return q.get(timeout=timeout)
            except queue.Empty:return None
        observer=m._frame_observer.LatestFrameObserver(read,lambda:not backend.cancelled.is_set()).start()
        self.addCleanup(observer.close);backend.frame_observer=observer
        return observer,q

    def wait_frame(self,observer):
        until=time.monotonic()+1
        while observer.snapshot()['frame_id']==0:
            if time.monotonic()>until:self.fail('No synthetic frame')
            time.sleep(.002)

    def test_capture_uses_observer_as_only_sample_consumer_and_keeps_fence(self):
        d=test_control.Tests.backend(self);d.frames=0
        class Clock:
            def get_time(self):return 0
        d.pipeline=SimpleNamespace(get_clock=lambda:Clock(),get_base_time=lambda:0)
        d.sink=SimpleNamespace(emit=lambda *args:(_ for _ in ()).throw(AssertionError('Second sample consumer')))
        observer,q=self.observer(d)
        q.put((b'old'*10,100*m.Gst.MSECOND))
        timer=threading.Timer(.02,lambda:q.put((b'new'*10,250*m.Gst.MSECOND)));timer.start()
        self.assertEqual(d._capture_once(),b'new'*10);timer.join()
        self.assertEqual(d.capture_info['settling_ms'],200)
        self.assertTrue(d.capture_info['continuous_observer'])
        self.assertEqual(d.capture_info['observer_stream_id'],observer.stream_id)

    def test_pause_clears_observer_before_pipeline_teardown(self):
        d=test_control.Tests.backend(self);d.operation_cancelled=threading.Event()
        observer,q=self.observer(d);q.put((b'a'*32,1));self.wait_frame(observer)
        def stop(state):self.assertIsNone(d.frame_observer);self.assertIsNone(observer.latest)
        d.pipeline=SimpleNamespace(set_state=stop)
        d.pause_input()
        self.assertIsNone(d.pipeline);self.assertIsNone(observer.latest)

    def test_close_releases_portal_then_observer_and_discards_late_pixels(self):
        d=test_control.Tests.backend(self);d.fd=None;d.closed_sub=None
        observer,q=self.observer(d);q.put((b'a'*32,1));self.wait_frame(observer)
        original=observer.close
        def stop():
            self.assertTrue(d.portal_closed)
            return original()
        observer.close=stop
        d.pipeline=SimpleNamespace(set_state=lambda state:None)
        d.close()
        self.assertIsNone(observer.latest);self.assertIsNone(d.frame_observer)

    def test_context_recovery_change_wait_returns_guarded_image_and_no_input(self):
        fixture=context_fixture.ContextRecoveryTests();self.addCleanup(fixture.doCleanups)
        s,b,d=fixture.make();observer,q=self.observer(d)
        q.put((b'a'*32,1));self.wait_frame(observer)
        timer=threading.Timer(.02,lambda:q.put((b'b'*32,2)));timer.start()
        result=fixture.request(s,'desktop_observe',{'after_stream_id':observer.stream_id,
            'after_revision':1,'wait_for_change_seconds':1})
        timer.join();self.assertFalse(result.get('isError',False),result)
        metadata=json.loads(result['content'][0]['text'])
        self.assertTrue(metadata['change_wait']['changed_before_capture'])
        self.assertTrue(any(c['type']=='image' for c in result['content']))
        self.assertEqual(d.events,[])

    def test_stale_stream_cannot_publish_image(self):
        fixture=context_fixture.ContextRecoveryTests();self.addCleanup(fixture.doCleanups)
        s,b,d=fixture.make();observer,q=self.observer(d)
        q.put((b'a'*32,1));self.wait_frame(observer)
        result=fixture.request(s,'desktop_observe',{'after_stream_id':'0'*32,
            'after_revision':0,'wait_for_change_seconds':0})
        self.assertTrue(result.get('isError',False))
        self.assertFalse(any(c['type']=='image' for c in result['content']))
        self.assertFalse(any(e[1].startswith('Notify') for e in d.events))

    def test_wait_interrupted_by_stop_never_publishes(self):
        fixture=context_fixture.ContextRecoveryTests();self.addCleanup(fixture.doCleanups)
        s,b,d=fixture.make();observer,q=self.observer(d)
        q.put((b'a'*32,1));self.wait_frame(observer)
        timer=threading.Timer(.02,d.cancelled.set);timer.start();started=time.monotonic()
        result=fixture.request(s,'desktop_observe',{'after_stream_id':observer.stream_id,
            'after_revision':1,'wait_for_change_seconds':30})
        timer.join();self.assertLess(time.monotonic()-started,.5)
        self.assertTrue(result.get('isError',False))
        self.assertFalse(any(c['type']=='image' for c in result['content']))


if __name__=='__main__':unittest.main()
