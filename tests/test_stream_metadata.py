"""Diagnostic-only stream geometry; no display, capture or input device access."""
import importlib.util
import math
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1]/'plugins/linux-desktop-control/stream_metadata.py'
spec = importlib.util.spec_from_file_location('stream_metadata_diagnostic', source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class StreamMetadataTests(unittest.TestCase):
    def test_exact_geometry_provenance_stays_separate_and_detached(self):
        props = {'position': (-1920, 0), 'size': [3840, 2400],
                 'logical_size': [1920, 1200], 'source_type': 1,
                 'mapping_id': 'private-identifier', 'title': 'private-title',
                 'other': {'secret': 'private-data'}}
        result = m.diagnostic_stream_metadata(props)
        self.assertEqual(result, {'position': [-1920, 0], 'size': [3840, 2400],
                                 'logical_size': [1920, 1200], 'source_type': 1,
                                 'mapping_id_present': True})
        result['size'][0] = 1
        self.assertEqual(props['size'], [3840, 2400])
        self.assertNotIn('private', str(result))

    def test_missing_size_is_not_filled_from_other_geometry(self):
        self.assertEqual(m.diagnostic_stream_metadata({'logical_size': [1920, 1200]}),
                         {'logical_size': [1920, 1200], 'mapping_id_present': False})

    def test_malformed_pairs_are_omitted_without_exposing_values(self):
        for value in (None, 'secret', [1], [1, 2, 3], [True, 2], [math.nan, 2],
                      [math.inf, 2], [1_000_001, 2], [10**1000, 2], {'x': 1, 'y': 2}):
            with self.subTest(value=value):
                result = m.diagnostic_stream_metadata(
                    {'position': value, 'size': value, 'logical_size': value})
                self.assertEqual(result, {'mapping_id_present': False})

    def test_dimension_and_enum_bounds(self):
        for value in ([0, 1], [-1, 1], [1, -1_000_001]):
            self.assertNotIn('size', m.diagnostic_stream_metadata({'size': value}))
        for value in (True, '1', 0, -1, 3, 2**32):
            self.assertNotIn('source_type', m.diagnostic_stream_metadata({'source_type': value}))
        for value in (1, 2, 4):
            self.assertEqual(m.diagnostic_stream_metadata({'source_type': value})['source_type'], value)
        self.assertEqual(m.diagnostic_stream_metadata({'position': [-1_000_000, 1_000_000]})['position'],
                         [-1_000_000, 1_000_000])

    def test_non_mapping_and_mapping_id_values_never_escape(self):
        for value in (None, [], 'secret', 1):
            self.assertEqual(m.diagnostic_stream_metadata(value), {})
        for value in (None, 'secret', object(), {'nested': 'secret'}):
            self.assertEqual(m.diagnostic_stream_metadata({'mapping_id': value}),
                             {'mapping_id_present': True})


if __name__ == '__main__':
    unittest.main()
