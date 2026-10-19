"""Failed release and failed portal close must retain retryable input state."""
import unittest
import test_control


class ReleaseUncertaintyTests(unittest.TestCase):
    def backend(self):
        backend=test_control.Tests().backend()
        backend.portal_closed=False
        backend.held=[('key',65),('button',272)]
        return backend

    def test_failed_release_and_close_retain_unresolved_input_for_retry(self):
        backend=self.backend()
        def fail(*args,**kwargs):raise RuntimeError('unavailable')
        backend.call=fail
        self.assertTrue(backend.release())
        self.assertEqual(backend.status()['held_input_count'],2)
        self.assertFalse(backend.status()['portal_closed_confirmed'])
        self.assertIsNotNone(backend.session)
        retried=[]
        backend.call=lambda *args,**kwargs:retried.append(args)
        self.assertFalse(backend.release())
        self.assertEqual(len(retried),2)
        self.assertEqual(backend.held,[])
        self.assertEqual(backend.release_counts,{'attempted':3,'confirmed':2,'failed':1})

    def test_confirmed_releases_are_removed_before_later_failure(self):
        backend=self.backend()
        def call(*args,**kwargs):
            if args[1]=='NotifyPointerButton':return
            raise RuntimeError('unavailable')
        backend.call=call
        self.assertTrue(backend.release())
        self.assertEqual(backend.held,[('key',65)])
        self.assertEqual(backend.release_counts,{'attempted':2,'confirmed':1,'failed':1})

    def test_confirmed_portal_close_discards_all_virtual_held_state(self):
        backend=self.backend()
        def call(*args,**kwargs):
            if args[1]=='Close':return
            raise RuntimeError('release unavailable')
        backend.call=call
        self.assertTrue(backend.release())
        self.assertTrue(backend.status()['portal_closed_confirmed'])
        self.assertIsNone(backend.session)
        self.assertEqual(backend.held,[])


if __name__=='__main__':unittest.main()
