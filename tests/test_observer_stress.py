"""Bounded offline concurrency stress; synthetic bytes, no desktop or model."""
import importlib.util
from pathlib import Path
import queue
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location('stress_' + name, ROOT / 'plugins/linux-desktop-control' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

frames = load('frame_observer')
notices = load('change_notifications')


class ObserverStressTests(unittest.TestCase):
    def observer(self):
        source = queue.Queue()
        def read(timeout):
            try:
                return source.get(timeout=min(timeout, .002))
            except queue.Empty:
                return None
        observer = frames.LatestFrameObserver(read, lambda: True).start()
        self.addCleanup(observer.close)
        return observer, source

    def until(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail('Synthetic producer did not settle within four seconds')
            time.sleep(.001)

    def test_twenty_thousand_changes_leave_only_final_frame(self):
        observer, source = self.observer()
        for number in range(20000):
            source.put((number.to_bytes(8, 'big') * 4, number))
        self.until(lambda: observer.snapshot()['frame_id'] == 20000)
        result = observer.wait_frame(19999, .1, lambda: None)
        self.assertEqual(result['data'], (19999).to_bytes(8, 'big') * 4)
        snapshot = observer.snapshot()
        self.assertEqual(snapshot['buffered_frames'], 1)
        self.assertEqual(snapshot['revision'], 20000)
        self.assertEqual(snapshot['overwritten_frames'], 19999)
        observer.close()
        self.assertIsNone(observer.latest)

    def test_fifty_replacements_never_accept_old_stream_or_pixels(self):
        previous = None
        identities = set()
        for generation in range(50):
            observer, source = self.observer()
            self.assertNotIn(observer.stream_id, identities)
            identities.add(observer.stream_id)
            self.assertIsNone(observer.latest)
            if previous is not None:
                with self.assertRaises(ValueError):
                    observer.wait_change(previous.stream_id, previous.revision, 0, lambda: None)
                self.assertIsNone(previous.latest)
                self.assertFalse(previous.thread.is_alive())
            payload = generation.to_bytes(8, 'big') * 4
            source.put((payload, generation))
            self.until(lambda: observer.snapshot()['frame_id'] == 1)
            self.assertEqual(observer.wait_frame(generation, .1, lambda: None)['data'], payload)
            self.assertTrue(observer.close())
            previous = observer

    def test_twenty_close_races_wake_waiters_during_updates(self):
        for repetition in range(20):
            observer, source = self.observer()
            entered = threading.Event()
            result = []
            def check():
                entered.set()
            def wait():
                try:
                    observer.wait_frame(1000000, 10, check)
                except frames.ObserverStopped:
                    result.append('stopped')
                except Exception as error:
                    result.append(type(error).__name__)
            waiter = threading.Thread(target=wait)
            waiter.start()
            try:
                self.assertTrue(entered.wait(1))
                for number in range(200):
                    source.put((b'x' * 32, number))
                self.assertTrue(observer.close())
                waiter.join(1)
                self.assertFalse(waiter.is_alive())
                self.assertEqual(result, ['stopped'])
                self.assertIsNone(observer.latest)
            finally:
                observer.close()
                waiter.join(1)

    def test_thousand_ownership_changes_reject_inflight_old_owner(self):
        state = [('owner-0', 'active', 'stream', 0)]
        sent = []
        replace_during_send = [False]
        def send(owner):
            if replace_during_send[0]:
                # Models the transport's final ownership check after waiting
                # for its output lock, without granting the notifier authority.
                state[0] = (owner + '-replacement', 'active', 'stream', 1)
                return False
            if owner != state[0][0]:
                return False
            sent.append((owner, state[0][3]))
            return True
        notifier = notices.ChangeNotifier(lambda: state[0], send, interval=1)
        self.addCleanup(notifier.close)
        for generation in range(1000):
            state[0] = ('owner-' + str(generation), 'active', 'stream', generation)
            replace_during_send[0] = True
            before = len(sent)
            self.assertFalse(notifier.poll(generation * 3 + 1))
            self.assertEqual(len(sent), before)
            replace_during_send[0] = False
            self.assertTrue(notifier.poll(generation * 3 + 1))
            for revision in range(2, 22):
                state[0] = (state[0][0], 'active', 'stream', revision)
                self.assertFalse(notifier.poll(generation * 3 + 1.1))
            self.assertTrue(notifier.poll(generation * 3 + 2))
            self.assertEqual(notifier.last_key, state[0])
            state[0] = None
            self.assertFalse(notifier.poll(generation * 3 + 2.1))
            self.assertIsNone(notifier.last_key)
        self.assertEqual(len(sent), 2000)
        notifier.close()
        state[0] = ('post-close', 'active', 'stream', 999)
        self.assertFalse(notifier.poll(99999))


if __name__ == '__main__':
    unittest.main()
