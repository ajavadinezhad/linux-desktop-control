"""Observed pointer endpoints, independent from dispatched coordinate intent."""
import unittest
from unittest import mock
import test_control
m=test_control.m


class PointerEndpointTests(unittest.TestCase):
    def make(self,mapping=lambda x,y:(x,y)):
        backend=test_control.Tests().backend();backend.pointer_position=None
        state={'position':(10,10),'reads':0,'clock':100.0}
        def call(*args,**kwargs):
            backend.events.append(args)
            if args[1]=='NotifyPointerMotion':
                dx,dy=args[3][-2:]
                state['position']=mapping(state['position'][0]+dx,state['position'][1]+dy)
        def reader():
            state['reads']+=1
            return state['position']
        def wait(seconds):
            backend.check();state['clock']+=max(.001,seconds);backend.check()
        backend.call=call;backend.pointer_reader=reader;backend.wait_interruptibly=wait
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(m.time,'monotonic',side_effect=lambda:state['clock']).start()
        return backend,state

    def buttons(self,backend):
        return [event for event in backend.events if event[1]=='NotifyPointerButton']

    def test_half_scale_endpoint_refuses_click_without_down_or_retry(self):
        backend,state=self.make(lambda x,y:(x/2,y/2))
        with self.assertRaisesRegex(RuntimeError,'endpoint'):
            backend.action({'type':'click','x':960,'y':580})
        self.assertEqual(self.buttons(backend),[])
        self.assertTrue(backend.cancelled.is_set())
        motions=[event for event in backend.events if event[1]=='NotifyPointerMotion']
        self.assertTrue(motions)
        # The first mismatching displacement is terminal; no correction follows.
        self.assertLessEqual(len(motions),2)

    def test_delayed_endpoint_requires_two_fresh_matching_reads_before_down(self):
        backend,state=self.make();base=backend.pointer_reader
        def delayed():
            value=base()
            return (10,10) if state['reads']<=3 else value
        backend.pointer_reader=delayed
        backend.action({'type':'click','x':100,'y':100})
        self.assertGreaterEqual(state['reads'],6)
        self.assertEqual([event[3][-1] for event in self.buttons(backend)],[1,0])

    def test_missing_or_invalid_observer_never_sends_button(self):
        for observed in (None,(float('nan'),0),(True,2),(-1,2),(99999,2)):
            with self.subTest(observed=observed):
                backend,state=self.make()
                backend.pointer_reader=lambda:observed
                with self.assertRaises((RuntimeError,TypeError,ValueError)):
                    backend._primitive({'type':'click','x':100,'y':100})
                self.assertEqual(self.buttons(backend),[])
        backend,state=self.make();backend.pointer_reader=None
        with self.assertRaisesRegex(RuntimeError,'unavailable'):
            backend._primitive({'type':'click','x':100,'y':100})
        self.assertEqual(self.buttons(backend),[])

    def test_endpoint_failure_during_drag_releases_held_button(self):
        def mapping(x,y):return (x,y) if x<200 else (x/2,y/2)
        backend,state=self.make(mapping)
        with self.assertRaisesRegex(RuntimeError,'endpoint'):
            backend.action({'type':'drag','path':[[100,100],[300,300]]})
        self.assertEqual([event[3][-1] for event in self.buttons(backend)],[1,0])
        self.assertEqual(backend.held,[])

    def test_scroll_mismatch_sends_no_axis_event(self):
        backend,state=self.make(lambda x,y:(x/2,y/2))
        with self.assertRaisesRegex(RuntimeError,'endpoint'):
            backend.action({'type':'scroll','x':300,'y':300,'dy':1})
        self.assertFalse(any(event[1]=='NotifyPointerAxisDiscrete' for event in backend.events))

    def test_cancellation_during_endpoint_wait_stops_without_button(self):
        backend,state=self.make()
        def cancelled():backend.cancelled.set();return (100,100)
        backend.pointer_reader=cancelled
        with self.assertRaises(RuntimeError):backend._primitive({'type':'click','x':100,'y':100})
        self.assertEqual(self.buttons(backend),[])

    def test_mapping_guard_missing_or_changed_emits_no_motion(self):
        for guard in (None,lambda:(_ for _ in ()).throw(RuntimeError('layout changed'))):
            backend,state=self.make();backend.mapping_guard=guard
            with self.assertRaises(RuntimeError):backend.position(100,100)
            self.assertEqual(backend.events,[])
            self.assertTrue(backend.cancelled.is_set())

    def test_nonzero_monitor_origin_uses_local_delta_not_global_origin(self):
        from test_window_guard import g as window_guard
        backend,state=self.make()
        context={'available':True,'epoch':1,'window_id':'window','kind':'window',
                 'rect':[0,240,1920,1200],'pointer':[10,250]}
        geometry={'x':0,'y':240,'width':1920,'height':1200}
        original=backend.pointer_reader
        def reader():
            local=original();context['pointer']=[local[0],local[1]+240]
            return window_guard.pointer_local(context,geometry)
        backend.pointer_reader=reader
        backend.position(960,580)
        self.assertEqual(backend.events[0][3][-2:],(950.,570.))
        self.assertEqual(state['position'],(960.,580.))
        self.assertEqual(len(backend.events),1)

    def test_pointer_outside_selected_monitor_emits_no_motion(self):
        backend,state=self.make();backend.pointer_reader=lambda:(-5,10)
        with self.assertRaises(RuntimeError):backend.position(100,100)
        self.assertEqual(backend.events,[])


if __name__=='__main__':unittest.main()
