"""Cleanup evidence from production raw-UP dispatch; no live desktop input."""
import unittest
import test_control as fixtures

m = fixtures.m


class ReleaseEvidenceTests(unittest.TestCase):
    def backend(self):
        return fixtures.Tests.backend(self)

    def test_cancel_mid_typing_and_drag_records_raw_release_after_cutoff(self):
        for kind, action in (
            ('NotifyKeyboardKeysym', {'type': 'text', 'focus': {'x': 10, 'y': 10}, 'text': 'abc'}),
            ('NotifyPointerButton', {'type': 'drag', 'path': [[10, 10], [20, 20], [30, 30]]}),
        ):
            with self.subTest(kind=kind):
                d = self.backend(); original = d.call; cutoff = []
                def call(iface, method, signature, args, **kwargs):
                    original(iface, method, signature, args, **kwargs)
                    if method == kind and args[-1] == 1 and not cutoff:
                        cutoff.append(len(d.events)); d.cancelled.set()
                d.call = call
                with self.assertRaises(RuntimeError): d.action(action)
                after = d.events[cutoff[0]:]
                self.assertEqual(len(after), 1)
                self.assertEqual(after[0][1], kind)
                self.assertEqual(after[0][-1][-1], 0)
                status = d.status()
                self.assertEqual(status['held_input_count'], 0)
                self.assertEqual(status['input_release'], {'attempted': 1, 'confirmed': 1, 'failed': 0})
                d.release()
                self.assertEqual(d.status()['input_release'], status['input_release'])

    def test_failed_raw_release_keeps_failure_evidence_and_cleanup_warning(self):
        d = self.backend(); d.held = [('key', 123)]
        def failed(*args, **kwargs): raise RuntimeError('simulated transport loss')
        d.call = failed
        self.assertTrue(d.release())
        status = d.status()
        self.assertEqual(status['held_input_count'], 0)
        self.assertEqual(status['input_release'], {'attempted': 1, 'confirmed': 0, 'failed': 1})
        self.assertIn('release and portal close failed', status['cleanup_warning'])
        self.assertFalse(status['portal_closed_confirmed'])

    def test_portal_already_closed_does_not_invent_a_release_acknowledgement(self):
        d = self.backend(); d.held = [('button', 272)]; d.portal_closed = True
        d.release()
        self.assertEqual(d.status()['held_input_count'], 0)
        self.assertEqual(d.status()['input_release'], {'attempted': 0, 'confirmed': 0, 'failed': 0})
        self.assertEqual(d.events, [])

    def test_no_backend_status_has_zero_aggregate_evidence(self):
        status = m.Server(fixtures.Fake).status()
        self.assertEqual(status['held_input_count'], 0)
        self.assertEqual(status['input_release'], {'attempted': 0, 'confirmed': 0, 'failed': 0})
