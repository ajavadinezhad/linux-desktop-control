"""Independent failure boundaries for retained consent; no devices or GUI."""
import unittest
from types import SimpleNamespace
import test_retained_pause as retained


class RetainedPauseBoundaryTests(unittest.TestCase):
    def make(self):
        fixture = retained.RetainedPauseTests()
        server, bus, backend = fixture.make()
        self.addCleanup(fixture.doCleanups)
        return fixture, server, backend

    def test_mapping_change_during_pause_cannot_resume_capture(self):
        fixture, server, backend = self.make()
        fixture.request(server, 'desktop_pause')
        pause_id = server.pause_id
        backend.mapping_guard = lambda: (_ for _ in ()).throw(RuntimeError('layout changed'))
        result = fixture.request(server, 'desktop_resume', {'pause_id': pause_id})
        self.assertTrue(result['isError'])
        self.assertEqual(backend.resumes, 0)
        self.assertEqual(backend.captures, 0)
        self.assertFalse(any(event[1].startswith('Notify') for event in backend.events))
        self.assertEqual(server.state, 'closed')

    def test_missing_native_owner_cannot_resume_protected_session(self):
        fixture, server, backend = self.make()
        fixture.request(server, 'desktop_pause')
        pause_id = server.pause_id
        server.physical_takeover = True
        server.native_activity = None
        result = fixture.request(server, 'desktop_resume', {'pause_id': pause_id})
        self.assertTrue(result['isError'])
        self.assertEqual((backend.resumes, backend.captures), (0, 0))
        self.assertEqual(server.state, 'closed')

    def test_old_pause_id_cannot_resume_a_later_pause(self):
        fixture, server, backend = self.make()
        fixture.request(server, 'desktop_pause')
        first = server.pause_id
        fixture.request(server, 'desktop_resume', {'pause_id': first})
        fixture.request(server, 'desktop_pause')
        second = server.pause_id
        self.assertNotEqual(first, second)
        result = fixture.request(server, 'desktop_resume', {'pause_id': first})
        self.assertTrue(result['isError'])
        self.assertEqual(server.state, 'paused')
        self.assertEqual(server.pause_id, second)
        self.assertEqual((backend.resumes, backend.captures), (1, 1))
        self.assertEqual(backend.events, [])

    def test_stale_native_owner_cannot_pause_replacement_operation(self):
        fixture, server, backend = self.make()
        stale = SimpleNamespace()
        current = SimpleNamespace()
        server.native_activity = current
        generation = server.generation
        self.assertFalse(server.begin_pause('pointer-motion', expected_native=stale))
        self.assertEqual(server.state, 'active')
        self.assertEqual(server.generation, generation)
        self.assertFalse(backend.operation_cancelled.is_set())
        # Avoid fabricating ownership cleanup methods: this is a stale-owner test.
        server.native_activity = None


if __name__ == '__main__':
    unittest.main()
