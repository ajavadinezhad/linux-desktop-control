#!/usr/bin/env python3
"""EXPERIMENT: coarse activity from an explicitly preopened fd. No device opens.
This is not a privileged broker, physical provenance verifier or installed plugin.
"""
import argparse
import fcntl
import os
import select
import stat
import struct
import sys
import time

# Linux input_event on the supported 64-bit native ABI: timeval + type/code/value.
RECORD_SIZE = struct.calcsize('@llHHi')
TYPE_OFFSET = struct.calcsize('@ll')
ACTIVITY_TYPES = frozenset((1, 2, 3))  # EV_KEY, EV_REL, EV_ABS.
SYN_DROPPED = 3  # EV_SYN code signaling kernel event-queue overflow.

class Framer:
    def __init__(self, max_records=4096):
        if sys.platform != 'linux' or struct.calcsize('@l') != 8 or RECORD_SIZE != 24:
            raise RuntimeError('Unsupported Linux input_event ABI')
        if type(max_records) is not int or not 1 <= max_records <= 65536:
            raise ValueError('Invalid input record limit')
        self._pending = bytearray()
        self._remaining = max_records
        self._terminal = False

    def feed(self, chunk):
        if self._terminal:
            raise RuntimeError('Input stream unavailable')
        if not isinstance(chunk, bytes) or len(chunk) > 4096:
            self._terminal = True
            self._pending.clear()
            raise ValueError('Invalid input chunk')
        self._pending.extend(chunk)
        while len(self._pending) >= RECORD_SIZE:
            if self._remaining <= 0:
                self._terminal = True
                self._pending.clear()
                raise RuntimeError('Input record limit exceeded')
            self._remaining -= 1
            event_type = struct.unpack_from('@H', self._pending, TYPE_OFFSET)[0]
            # Only synchronization codes are examined for stream-loss detection.
            # Key/button codes, all values and timestamps are never decoded.
            dropped = event_type == 0 and struct.unpack_from('@H', self._pending, TYPE_OFFSET + 2)[0] == SYN_DROPPED
            del self._pending[:RECORD_SIZE]
            if dropped:
                self._terminal = True
                self._pending.clear()
                raise RuntimeError('Input synchronization lost')
            if event_type in ACTIVITY_TYPES:
                self._terminal = True
                self._pending.clear()
                return True
        return False

    def finish(self):
        self._terminal = True
        partial = bool(self._pending)
        self._pending.clear()
        if partial:
            raise RuntimeError('Incomplete input record')
        raise RuntimeError('Input stream unavailable')


def validate_fd(fd):
    """Validate inherited transport metadata without reading any device."""
    if type(fd) is not int or fd < 3:
        raise ValueError('An explicit preopened fd >= 3 is required')
    info = os.fstat(fd)
    if not (stat.S_ISCHR(info.st_mode) or stat.S_ISFIFO(info.st_mode) or stat.S_ISSOCK(info.st_mode)):
        raise ValueError('A stream or character-device fd is required')
    if not fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_NONBLOCK:
        raise ValueError('Caller must supply a nonblocking fd')

def observe(fd, timeout=3, max_records=4096):
    """Return True on activity; all unavailable/quiet outcomes raise a fault.
    Never closes the caller fd. Pipe fixtures do not establish evdev access.
    """
    validate_fd(fd)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 30:
        raise ValueError('Timeout must be in (0, 30] seconds')
    framer = Framer(max_records)
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                framer.finish()
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                framer.finish()
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if not chunk:
                framer.finish()
            if framer.feed(chunk):
                return True
    finally:
        framer._pending.clear()


class ProtocolParser(argparse.ArgumentParser):
    def error(self, message):
        print('FAULT', flush=True)
        raise SystemExit(2)


def main():
    parser = ProtocolParser(description=__doc__, add_help=False)
    parser.add_argument('--input-fd', required=True, type=int)
    parser.add_argument('--timeout', type=float, default=3)
    args = parser.parse_args()
    try:
        if os.geteuid() == 0:
            raise RuntimeError('Unprivileged reader required')
        validate_fd(args.input_fd)
        if not 0 < args.timeout <= 30:
            raise ValueError('Invalid timeout')
        Framer()  # Validate the native ABI before reporting readiness.
        print('READY', flush=True)
        observe(args.input_fd, args.timeout)
    except (OSError, ValueError, RuntimeError):
        # Fixed tokens only: errors must never look like absence of activity.
        print('FAULT', flush=True)
        return 2
    print('ACTIVITY', flush=True)
    return 0

if __name__ == '__main__':
    sys.exit(main())
