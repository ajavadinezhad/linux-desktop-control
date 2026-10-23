"""Portable observer tests with synthetic bytes; no desktop or model access."""
import importlib.util
from pathlib import Path
import queue
import threading
import time
import unittest

path=Path(__file__).resolve().parents[1]/'plugins/linux-desktop-control/frame_observer.py'
spec=importlib.util.spec_from_file_location('frame_observer_test',path)
observer_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer_module)


class FrameObserverTests(unittest.TestCase):
    def make(self):
        frames=queue.Queue();allowed=threading.Event();allowed.set();fault=threading.Event()
        def read(timeout):
            try:return frames.get(timeout=timeout)
            except queue.Empty:return None
        observer=observer_module.LatestFrameObserver(read,allowed.is_set,on_fault=fault.set).start()
        self.addCleanup(observer.close)
        return observer,frames,allowed,fault

    def wait(self,predicate):
        deadline=time.monotonic()+1
        while not predicate():
            if time.monotonic()>deadline:self.fail('Synthetic observer did not settle')
            time.sleep(.002)

    def frame(self,value=b'a',pts=1):return value*32,pts

    def test_slow_consumer_gets_latest_without_frame_backlog(self):
        o,q,_,_=self.make()
        for i in range(1000):q.put(self.frame(pts=i))
        self.wait(lambda:o.snapshot()['frame_id']==1000)
        frame=o.wait_frame(999,.1,lambda:None)
        self.assertEqual(frame['pts'],999)
        self.assertEqual(o.snapshot()['buffered_frames'],1)
        self.assertEqual(o.snapshot()['overwritten_frames'],999)

    def test_revisions_change_only_for_different_frame_bytes(self):
        o,q,_,_=self.make()
        for i in range(3):q.put(self.frame(pts=i))
        self.wait(lambda:o.snapshot()['frame_id']==3)
        self.assertEqual(o.snapshot()['revision'],1)
        q.put(self.frame(b'b',4));self.wait(lambda:o.snapshot()['revision']==2)
        self.assertTrue(o.wait_change(o.stream_id,1,.1,lambda:None))

    def test_pause_clears_pixels_and_cannot_publish(self):
        o,q,allowed,_=self.make();q.put(self.frame())
        self.wait(lambda:o.snapshot()['buffered_frames']==1)
        allowed.clear()
        with self.assertRaises(observer_module.ObserverStopped):o.wait_frame(0,.1,lambda:None)
        self.assertIsNone(o.latest)

    def test_stop_discards_late_inflight_frame(self):
        entered=threading.Event();release=threading.Event()
        def read(timeout):entered.set();release.wait(1);return self.frame()
        o=observer_module.LatestFrameObserver(read,lambda:True).start()
        self.assertTrue(entered.wait(.5))
        self.assertFalse(o.close());self.assertIsNone(o.latest)
        release.set();o.thread.join(.5)
        self.assertFalse(o.thread.is_alive());self.assertEqual(o.snapshot()['frame_id'],0)

    def test_new_stream_cannot_reuse_previous_identity(self):
        o,q,_,_=self.make();q.put(self.frame());self.wait(lambda:o.snapshot()['frame_id']==1)
        other,_,_,_=self.make()
        with self.assertRaises(ValueError):other.wait_change(o.stream_id,0,0,lambda:None)

    def test_change_wait_cancellation_is_prompt(self):
        o,q,_,_=self.make();q.put(self.frame());self.wait(lambda:o.snapshot()['frame_id']==1)
        cancelled=threading.Event();timer=threading.Timer(.02,cancelled.set);timer.start()
        def check():
            if cancelled.is_set():raise RuntimeError('cancelled')
        start=time.monotonic()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):o.wait_change(o.stream_id,1,30,check)
        self.assertLess(time.monotonic()-start,.3);timer.join()

    def test_change_timeout_and_future_revision_are_distinct(self):
        o,q,_,_=self.make();q.put(self.frame());self.wait(lambda:o.snapshot()['frame_id']==1)
        self.assertFalse(o.wait_change(o.stream_id,1,.01,lambda:None))
        with self.assertRaises(ValueError):o.wait_change(o.stream_id,2,0,lambda:None)
        for value in (True,-1,float('nan'),31):
            with self.assertRaises(ValueError):o.wait_change(o.stream_id,1,value,lambda:None)

    def test_timestamp_fence_and_age_refuse_old_frames(self):
        o,q,_,_=self.make();q.put(self.frame(pts=10));self.wait(lambda:o.snapshot()['frame_id']==1)
        with self.assertRaises(observer_module.ObserverTimeout):o.wait_frame(11,.01,lambda:None)
        with self.assertRaises(observer_module.ObserverTimeout):o.wait_frame(0,.01,lambda:None,max_age=0)

    def test_bad_frame_fails_without_leaking_adapter_errors(self):
        o,q,_,fault=self.make();q.put((b'x',1))
        self.assertTrue(fault.wait(.5));self.assertTrue(o.snapshot()['failed']);self.assertIsNone(o.latest)
        with self.assertRaises(observer_module.ObserverFailed):o.wait_frame(0,.1,lambda:None)

    def test_backward_timestamp_is_terminal(self):
        o,q,_,fault=self.make();q.put(self.frame(pts=2));q.put(self.frame(pts=1))
        self.assertTrue(fault.wait(.5));self.assertIsNone(o.latest)

    def test_permission_revoked_during_final_check_discards_result(self):
        o,q,allowed,_=self.make();q.put(self.frame());self.wait(lambda:o.snapshot()['frame_id']==1)
        checks=[]
        def check():
            checks.append(True)
            if len(checks)==2:allowed.clear()
        with self.assertRaises(observer_module.ObserverStopped):o.wait_frame(0,.1,check)
        self.assertIsNone(o.latest)

    def test_close_wakes_waiter_and_erases_buffer(self):
        o,q,_,_=self.make();q.put(self.frame());self.wait(lambda:o.snapshot()['frame_id']==1)
        timer=threading.Timer(.02,o.close);timer.start();start=time.monotonic()
        with self.assertRaises(observer_module.ObserverStopped):o.wait_change(o.stream_id,1,30,lambda:None)
        self.assertLess(time.monotonic()-start,.3);timer.join();self.assertIsNone(o.latest)


    def test_stalled_permission_check_cannot_block_close_or_retain_late_pixels(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def permitted():
            calls.append(True)
            if len(calls)==2:entered.set();release.wait(2)
            return True
        observer=observer_module.LatestFrameObserver(lambda timeout:(b'a'*32,1),permitted).start()
        self.addCleanup(release.set);self.addCleanup(observer.close)
        self.assertTrue(entered.wait(1))
        started=time.monotonic();self.assertFalse(observer.close())
        self.assertLess(time.monotonic()-started,.6);self.assertIsNone(observer.latest)
        release.set();observer.thread.join(1)
        self.assertIsNone(observer.latest);self.assertFalse(observer.thread.is_alive())

if __name__=='__main__':unittest.main()
