"""Isolated coordinate/foreground contracts; no live display compatibility claim."""
import copy
import unittest
import test_window_guard as fixtures

g = fixtures.g


class DisplayCompatibilityTests(unittest.TestCase):
    def context(self, pointer, rect):
        result = fixtures.context()
        result.update(pointer=pointer, rect=rect)
        return result

    def test_negative_left_and_above_monitor_origins_map_to_local_logical_units(self):
        cases = [
            ({'x': -1920, 'y': 0, 'width': 1920, 'height': 1080}, [-1800, 70], (120, 70)),
            ({'x': 0, 'y': -900, 'width': 1440, 'height': 900}, [300, -700], (300, 200)),
            ({'x': -1600, 'y': -900, 'width': 1600, 'height': 900}, [-1599.5, -899.5], (.5, .5)),
            ({'x': 1920, 'y': 120, 'width': 1280, 'height': 720}, [2100, 200], (180, 80)),
        ]
        for monitor, pointer, expected in cases:
            with self.subTest(monitor=monitor):
                c = self.context(pointer, [monitor['x'], monitor['y'], monitor['width'], monitor['height']])
                self.assertEqual(g.pointer_local(c, monitor), expected)
                guard = g.WindowGuard(fixtures.Bridge(), c, lambda: None)
                guard.validate_points({'type': 'click', 'x': expected[0], 'y': expected[1]},
                                      (monitor['x'], monitor['y']))

    def test_logical_mapping_does_not_double_apply_capture_scale(self):
        # The same logical scene can have different raster sizes. Mapping must
        # use logical monitor geometry, never multiply by capture pixel density.
        monitor = {'x': -1280, 'y': 0, 'width': 1280, 'height': 720}
        c = self.context([-640, 360], [-1280, 0, 1280, 720])
        for pixels in ([1280, 720], [1600, 900], [1920, 1080], [2560, 1440]):
            with self.subTest(pixel_size=pixels):
                c['pixel_size'] = pixels
                self.assertEqual(g.pointer_local(c, monitor), (640, 360))

    def test_monitor_edges_are_half_open_and_outside_pointer_is_refused(self):
        monitor = {'x': -100, 'y': -50, 'width': 100, 'height': 50}
        for pointer in ([-100, -50], [-.01, -.01]):
            self.assertIsInstance(g.pointer_local(self.context(pointer, [-100, -50, 100, 50]), monitor), tuple)
        for pointer in ([0, -1], [-1, 0], [-100.01, -1], [-1, -50.01], [1, 1]):
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                g.pointer_local(self.context(pointer, [-100, -50, 100, 50]), monitor)

    def test_protected_or_invalid_context_cannot_supply_a_pointer(self):
        monitor = {'x': 0, 'y': 0, 'width': 100, 'height': 100}
        for change in ({'available': False, 'reason': 'system-ui'},
                       {'available': False, 'reason': 'no-foreground-window'},
                       {'kind': 'lock-screen'}, {'epoch': True}, {'rect': [0, 0, 0, 10]}):
            c = self.context([10, 10], [0, 0, 100, 100]); c.update(change)
            with self.assertRaisesRegex(RuntimeError, 'context unavailable'):
                g.pointer_local(c, monitor)

    def test_geometry_or_scale_epoch_change_invalidates_even_when_pointer_unchanged(self):
        for change in ({'rect': [-1, 0, 1000, 800]}, {'rect': [0, 0, 999, 800]}, {'epoch': 11}):
            bridge = fixtures.Bridge(); cancelled = []
            guard = g.WindowGuard(bridge, bridge.context(), lambda: cancelled.append(True))
            bridge.value.update(copy.deepcopy(change))
            with self.assertRaises(RuntimeError): guard.check()
            self.assertTrue(cancelled)

    def test_invalid_offsets_and_point_types_fail_closed(self):
        bridge = fixtures.Bridge(); guard = g.WindowGuard(bridge, bridge.context(), lambda: None)
        for offset in (None, [0], [False, 0], [float('inf'), 0]):
            with self.assertRaises(ValueError): guard.validate_points({'x': 1, 'y': 1}, offset)
        for point in ([True, 1], [None, 1], [float('nan'), 1], ['1', 1]):
            with self.assertRaises(ValueError): guard.validate_points({'x': point[0], 'y': point[1]})

    def test_missing_nonfinite_or_zero_monitor_mapping_is_refused(self):
        c = self.context([10, 10], [0, 0, 100, 100])
        for monitor in (None, {}, {'x': 0, 'y': 0, 'width': 0, 'height': 100},
                        {'x': False, 'y': 0, 'width': 100, 'height': 100},
                        {'x': 0, 'y': float('nan'), 'width': 100, 'height': 100}):
            with self.assertRaises(RuntimeError): g.pointer_local(c, monitor)
