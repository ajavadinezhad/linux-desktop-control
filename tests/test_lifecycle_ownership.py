"""Session resource ownership under overlapping cleanup; no desktop/portal."""
import threading
import unittest
from types import SimpleNamespace
from test_control import Fake, m


class Backend(Fake):
    def __init__(self):
        super().__init__()
        self.held = []
    def start(self):
        self.cancelled.clear()
        super().start()
    def close(self):
        self.held.clear()
        super().close()


class LifecycleOwnershipTests(unittest.TestCase):
    def test_old_observer_cleanup_finishes_before_close_and_reopen(self):
        entered = threading.Event();release = threading.Event();reopened = threading.Event()
        native_closed = threading.Event()
        indicator_closed = threading.Event();provider_closed = threading.Event()
        class Native:
            def close(self):
                entered.set()
                if not release.wait(2):raise RuntimeError('fixture wait expired')
                native_closed.set()
            def status(self):return {'active': False}
        server = m.Server(Backend);server.call('desktop_start', {})
        server.backend.held = ['held']
        server.native_activity = Native()
        server.indicator = SimpleNamespace(close=indicator_closed.set)
        server.target_provider = SimpleNamespace(close=provider_closed.set)
        old = threading.Thread(target=server.close_backend)
        new_indicator_closed = threading.Event()
        new_indicator = SimpleNamespace(close=new_indicator_closed.set)
        errors = []
        def serialized_worker():
            try:
                server.call('desktop_close', {})
                server.call('desktop_start', {})
                server.indicator = new_indicator
                reopened.set()
            except BaseException as error:errors.append(error)
        worker = threading.Thread(target=serialized_worker)
        try:
            old.start();self.assertTrue(entered.wait(1))
            self.assertEqual(server.backend.held, [])
            self.assertFalse(server.backend.active)
            worker.start()
            self.assertFalse(reopened.wait(.05),'Replacement opened before old observer cleanup')
            release.set();old.join(1);worker.join(1)
            self.assertFalse(old.is_alive());self.assertFalse(worker.is_alive())
            self.assertEqual(errors, []);self.assertTrue(reopened.is_set())
            for closed in (native_closed,indicator_closed,provider_closed):self.assertTrue(closed.is_set())
            self.assertIs(server.indicator,new_indicator)
            self.assertFalse(new_indicator_closed.is_set())
            self.assertEqual(server.state,'active');self.assertTrue(server.backend.active)
        finally:
            release.set();old.join(2)
            if worker.ident is not None:worker.join(2)
            server.close_backend()

    def test_stale_callback_owner_is_checked_inside_lifecycle_lock(self):
        for kind in ('native','indicator'):
            with self.subTest(kind=kind):
                server = m.Server(Backend);server.call('desktop_start', {})
                old_owner = object();new_owner = object()
                attribute = 'native_activity' if kind=='native' else 'indicator'
                setattr(server,attribute,old_owner)
                entered = threading.Event();finished = threading.Event()
                def delayed_cleanup():
                    entered.set()
                    server.close_backend(**{'expected_'+kind:old_owner})
                    finished.set()
                with server.lifecycle_lock:
                    cleanup = threading.Thread(target=delayed_cleanup);cleanup.start()
                    self.assertTrue(entered.wait(1))
                    self.assertFalse(finished.wait(.05))
                    with server.state_lock:setattr(server,attribute,new_owner)
                    self.assertFalse(server.backend.cancelled.is_set())
                cleanup.join(1)
                self.assertFalse(cleanup.is_alive());self.assertTrue(finished.is_set())
                self.assertIs(getattr(server,attribute),new_owner)
                self.assertFalse(server.backend.cancelled.is_set());self.assertTrue(server.backend.active)
                setattr(server,attribute,None);server.close_backend()

    def test_callback_owner_check_and_invalidation_are_atomic_with_replacement(self):
        for method,attribute in (('native_activity_lost','native_activity'),
                                 ('foreground_lost','indicator'),
                                 ('indicator_failed','indicator')):
            with self.subTest(method=method):
                server=m.Server(Backend);server.call('desktop_start',{})
                old=object();new=object();server.own_observer(attribute,old)
                entered=threading.Event();finished=threading.Event()
                def callback():
                    entered.set();getattr(server,method)(old);finished.set()
                with server.state_lock:
                    pending=threading.Thread(target=callback);pending.start()
                    self.assertTrue(entered.wait(1));self.assertFalse(finished.wait(.05))
                    # Replacement ownership changes use the same lock as the
                    # callback's conditional invalidation in production.
                    server.backend.cancelled=threading.Event()
                    server.own_observer(attribute,new)
                    generation=server.generation
                pending.join(1)
                self.assertFalse(pending.is_alive());self.assertTrue(finished.is_set())
                self.assertEqual(server.generation,generation)
                self.assertIs(getattr(server,attribute),new)
                self.assertFalse(server.backend.cancelled.is_set())
                self.assertTrue(server.backend.active);self.assertEqual(server.state,'active')
                setattr(server,attribute,None);server.close_backend()

    def test_paused_callback_invalidation_cannot_cancel_replacement(self):
        for method,attribute in (('native_activity_lost','native_activity'),
                                 ('foreground_lost','indicator'),
                                 ('indicator_failed','indicator')):
            with self.subTest(method=method):
                server=m.Server(Backend);server.call('desktop_start',{})
                old=SimpleNamespace(close=lambda:None,status=lambda:{'active':False})
                new=SimpleNamespace(close=lambda:None,status=lambda:{'active':True})
                server.own_observer(attribute,old)
                entered=threading.Event();release=threading.Event();replaced=threading.Event()
                original=server.invalidate;errors=[]
                def delayed(*args,**kwargs):
                    if threading.current_thread().name=='audit-callback':
                        entered.set()
                        if not release.wait(2):raise RuntimeError('fixture wait expired')
                    return original(*args,**kwargs)
                server.invalidate=delayed
                callback=threading.Thread(target=lambda:getattr(server,method)(old),name='audit-callback')
                def replace():
                    try:
                        server.call('desktop_close',{})
                        server.call('desktop_start',{})
                        server.own_observer(attribute,new)
                        replaced.set()
                    except BaseException as error:errors.append(error)
                replacement=threading.Thread(target=replace)
                try:
                    callback.start();self.assertTrue(entered.wait(1))
                    replacement.start()
                    self.assertTrue(replaced.wait(.5),'Callback paused before atomic check must not block replacement')
                    release.set();callback.join(1);replacement.join(1)
                    self.assertFalse(callback.is_alive());self.assertFalse(replacement.is_alive())
                    self.assertEqual(errors,[]);self.assertTrue(replaced.is_set())
                    self.assertIs(getattr(server,attribute),new)
                    self.assertFalse(server.backend.cancelled.is_set())
                    self.assertTrue(server.backend.active);self.assertEqual(server.state,'active')
                finally:
                    release.set();callback.join(2)
                    if replacement.ident is not None:replacement.join(2)
                    server.close_backend()

    def test_callbacks_cancel_owned_input_even_while_publication_lock_is_held(self):
        for method,attribute in (('native_activity_lost','native_activity'),
                                 ('foreground_lost','indicator'),
                                 ('indicator_failed','indicator')):
            with self.subTest(method=method):
                server=m.Server(Backend);server.call('desktop_start',{})
                owner=SimpleNamespace(close=lambda:None,status=lambda:{'active':False})
                server.own_observer(attribute,owner)
                finished=threading.Event()
                def invoke():getattr(server,method)(owner);finished.set()
                with server.state_lock:
                    callback=threading.Thread(target=invoke);callback.start()
                    self.assertTrue(server.backend.cancelled.wait(.5),'Owned cancellation waited on output/state lock')
                    self.assertFalse(finished.is_set())
                callback.join(1)
                self.assertFalse(callback.is_alive());self.assertTrue(finished.is_set())
                server.close_backend()

    def test_delayed_captured_event_can_only_cancel_its_original_session(self):
        server=m.Server(Backend);server.call('desktop_start',{})
        entered=threading.Event();release=threading.Event()
        class DelayedEvent(threading.Event):
            def set(self):
                if threading.current_thread().name=='captured-owner-callback':
                    entered.set()
                    if not release.wait(2):raise RuntimeError('fixture wait expired')
                return super().set()
        old_event=DelayedEvent();server.backend.cancelled=old_event
        old=SimpleNamespace(close=lambda:None,status=lambda:{'active':False})
        server.own_observer('native_activity',old)
        callback=threading.Thread(target=lambda:server.native_activity_lost(old),name='captured-owner-callback')
        try:
            callback.start();self.assertTrue(entered.wait(1))
            server.call('desktop_close',{});server.call('desktop_start',{})
            new=SimpleNamespace(close=lambda:None,status=lambda:{'active':True})
            server.own_observer('native_activity',new)
            new_event=server.backend.cancelled;generation=server.generation
            self.assertIsNot(new_event,old_event)
            release.set();callback.join(1)
            self.assertFalse(callback.is_alive());self.assertTrue(old_event.is_set())
            self.assertFalse(new_event.is_set());self.assertTrue(server.backend.active)
            self.assertEqual(server.generation,generation);self.assertIs(server.native_activity,new)
        finally:release.set();callback.join(2);server.close_backend()

    def test_inactive_backend_with_attached_old_owner_refuses_replacement(self):
        server=m.Server(Backend);server.call('desktop_start',{})
        old_closed=threading.Event()
        old=SimpleNamespace(close=old_closed.set,status=lambda:{'active':False})
        server.own_observer('native_activity',old)
        callback=threading.Thread(target=lambda:server.native_activity_lost(old))
        with server.state_lock:
            callback.start()
            self.assertTrue(server.backend.cancelled.wait(.5))
            # Model the watchdog closing virtual input before the callback can
            # acquire the response-publication lock and detach its owner.
            server.backend.active=False
            old_event=server.backend.cancelled
            with self.assertRaisesRegex(RuntimeError,'Previous session resources'):
                server.call('desktop_start',{})
            self.assertTrue(old_closed.is_set());self.assertIsNone(server.native_activity)
            self.assertIs(server.backend.cancelled,old_event)
            server.call('desktop_start',{})
            new_event=server.backend.cancelled
            self.assertIsNot(new_event,old_event)
        callback.join(1)
        self.assertFalse(callback.is_alive());self.assertFalse(new_event.is_set())
        self.assertTrue(server.backend.active);self.assertEqual(server.state,'active')
        server.close_backend()

    def test_start_retires_each_attached_resource_before_refusing(self):
        for attribute in ('native_activity','indicator','target_provider'):
            with self.subTest(attribute=attribute):
                server=m.Server(Backend);closed=threading.Event()
                resource=SimpleNamespace(close=closed.set,status=lambda:{'active':False})
                setattr(server,attribute,resource)
                with self.assertRaisesRegex(RuntimeError,'Previous session resources'):
                    server.call('desktop_start',{})
                self.assertTrue(closed.is_set());self.assertIsNone(getattr(server,attribute))
                self.assertFalse(server.backend.active);self.assertEqual(server.state,'closed')
                server.call('desktop_start',{})
                self.assertTrue(server.backend.active);server.close_backend()

    def test_explicit_close_cancels_before_waiting_for_lifecycle_lock(self):
        server = m.Server(Backend);server.call('desktop_start', {})
        finished = threading.Event()
        with server.lifecycle_lock:
            closer = threading.Thread(target=lambda:(server.close_backend(),finished.set()))
            closer.start()
            self.assertTrue(server.backend.cancelled.wait(.5))
            self.assertFalse(finished.is_set())
        closer.join(1)
        self.assertFalse(closer.is_alive());self.assertTrue(finished.is_set())


if __name__=='__main__':unittest.main()
