import contextlib
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_activity_reader', ROOT / 'reader.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)

def record(kind, code=0, value=0):
    return struct.pack('@llHHi', 123456, 987654, kind, code, value)

@contextlib.contextmanager
def pipe(payload=b''):
    r, w = os.pipe2(os.O_NONBLOCK)
    try:
        if payload:
            os.write(w, payload)
        os.close(w)
        w = None
        yield r
    finally:
        os.close(r)
        if w is not None:
            os.close(w)

class ReaderTests(unittest.TestCase):
    def test_split_record_ignores_code_value_and_timestamp(self):
        # Every code/value pair has identical exported meaning; no contents retained.
        for code, value in ((30, 1), (65535, -2147483648), (1, 0)):
            framer = reader.Framer()
            payload = record(1, code, value)
            self.assertFalse(framer.feed(payload[:17]))
            self.assertTrue(framer.feed(payload[17:]))
            self.assertEqual(framer._pending, bytearray())

    def test_keyboard_motion_and_absolute_only_return_coarse_bool(self):
        for kind in (1, 2, 3):
            with pipe(record(0) + record(4, 4, 999) + record(kind, 70, -500)) as fd:
                self.assertIs(reader.observe(fd), True)
        with pipe(record(0) + record(4, 4, 999)) as fd:
            with self.assertRaisesRegex(RuntimeError, 'Input stream unavailable'):
                reader.observe(fd)

    def test_partial_eof_and_record_budget_fail_without_payload(self):
        with pipe(record(1)[:-1]) as fd:
            with self.assertRaisesRegex(RuntimeError, '^Incomplete input record$'):
                reader.observe(fd)
        with pipe(record(0) * 3) as fd:
            with self.assertRaisesRegex(RuntimeError, '^Input record limit exceeded$'):
                reader.observe(fd, max_records=2)

    def test_timeout_and_passed_fd_ownership(self):
        r, w = os.pipe2(os.O_NONBLOCK)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Input stream unavailable'):
                reader.observe(r, timeout=.01)
            os.fstat(r)  # Reader must not revoke/close the broker's passed fd.
        finally:
            os.close(r)
            os.close(w)

    def test_regular_files_and_blocking_fds_refused(self):
        with tempfile.TemporaryFile() as file:
            with self.assertRaisesRegex(ValueError, 'stream or character'):
                reader.observe(file.fileno())
        r, w = os.pipe()
        try:
            with self.assertRaisesRegex(ValueError, 'nonblocking'):
                reader.observe(r)
        finally:
            os.close(r)
            os.close(w)

    @unittest.skipIf(os.geteuid() == 0, 'CLI intentionally refuses root')
    def test_subprocess_pipe_export_contains_no_event_fields(self):
        with pipe(record(1, 54321, -123456789)) as fd:
            process = subprocess.run([sys.executable, str(ROOT/'reader.py'), '--input-fd', str(fd)], pass_fds=(fd,), capture_output=True, text=True, timeout=3)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout, 'READY\nACTIVITY\n')
        self.assertEqual(process.stderr, '')
        self.assertNotIn('54321', process.stdout)
        self.assertNotIn('-123456789', process.stdout)

    def test_syn_dropped_faults_before_any_following_activity(self):
        framer = reader.Framer()
        with self.assertRaisesRegex(RuntimeError, '^Input synchronization lost$'):
            framer.feed(record(0, 3) + record(1, 30, 1))
        self.assertEqual(framer._pending, bytearray())
        with self.assertRaisesRegex(RuntimeError, 'Input stream unavailable'):
            framer.feed(record(1, 30, 1))

    @unittest.skipIf(os.geteuid() == 0, 'CLI intentionally refuses root')
    def test_subprocess_eof_partial_and_syn_dropped_are_fault(self):
        for payload in (b'', record(1)[:-1], record(0, 3) + record(1)):
            with pipe(payload) as fd:
                result = subprocess.run([sys.executable, str(ROOT/'reader.py'), '--input-fd', str(fd)], pass_fds=(fd,), capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, 'READY\nFAULT\n')
            self.assertEqual(result.stderr, '')

    @unittest.skipIf(os.geteuid() == 0, 'CLI intentionally refuses root')
    def test_subprocess_timeout_is_fault_not_quiet(self):
        r, w = os.pipe2(os.O_NONBLOCK)
        try:
            result = subprocess.run([sys.executable, str(ROOT/'reader.py'), '--input-fd', str(r), '--timeout', '.01'], pass_fds=(r,), capture_output=True, text=True, timeout=3)
        finally:
            os.close(r)
            os.close(w)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, 'READY\nFAULT\n')

    def test_cli_bad_configuration_is_fixed_fault_without_readiness(self):
        result = subprocess.run([sys.executable, str(ROOT/'reader.py'), '--input-fd', '999999'], capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, 'FAULT\n')
        self.assertEqual(result.stderr, '')

if __name__ == '__main__':
    unittest.main()
