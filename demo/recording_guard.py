"""Read-only, local recorder readiness checks; never grants desktop authority."""
import argparse
import json
import math
import os
from pathlib import Path
import stat
import time
import uuid

PROTOCOL = 1
MAX_AGE = 3.0
MAX_PROGRESS_AGE = 5.0


def process_identity(pid):
    """Linux start ticks distinguish a recorder from a reused process number."""
    value = Path(f'/proc/{pid}/stat').read_text()
    return value[value.rfind(')') + 2:].split()[19]


def boot_identity():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def status_metadata(args, *, now=None):
    now = time.monotonic() if now is None else now
    if not hasattr(args, '_recording_identity'):
        args._recording_identity = {
            'guard_protocol': PROTOCOL, 'recording_id': uuid.uuid4().hex,
            'pid': os.getpid(), 'process_start': process_identity(os.getpid()),
            'boot_id': boot_identity(),
            'audio_mode': 'system-playback-monitor' if getattr(args, 'system_audio_device', None) else 'silent',
        }
        args._last_output_bytes = 0
        args._last_output_progress = now
    try:
        info = args.output.stat()
    except FileNotFoundError:
        return dict(args._recording_identity, heartbeat_monotonic=now,
                    output_device=None, output_inode=None, output_bytes=0,
                    output_progress_monotonic=args._last_output_progress)
    if info.st_size > args._last_output_bytes:
        args._last_output_progress = now
    args._last_output_bytes = info.st_size
    return dict(args._recording_identity, heartbeat_monotonic=now,
                output_device=info.st_dev, output_inode=info.st_ino,
                output_bytes=info.st_size, output_progress_monotonic=args._last_output_progress)


def _private_file(path, *, limit=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError('untrusted-file')
        if limit is None:
            return info, None
        if info.st_size > limit:
            raise ValueError('malformed-status')
        with os.fdopen(fd, 'r') as stream:
            fd = None
            value = json.load(stream)
        return info, value
    finally:
        if fd is not None:
            os.close(fd)


def check_ready(status_file, output_file, *, recording_id=None, require_audio=False,
                minimum_remaining=5.0, now=None):
    """A momentary check, not an input fence or proof of audible music/privacy."""
    now = time.monotonic() if now is None else now
    reason = 'unavailable'
    try:
        _, value = _private_file(status_file, limit=16384)
        if not isinstance(value, dict):
            raise ValueError('malformed-status')
        if value.get('guard_protocol') != PROTOCOL or type(value.get('guard_protocol')) is not int:
            raise ValueError('unsupported-status')
        identity = value.get('recording_id')
        if not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('malformed-status')
        if recording_id is not None and identity != recording_id:
            raise ValueError('different-recording')
        state = value.get('state')
        if state != 'recording' or value.get('recording') is not True:
            raise ValueError(state if state in ('awaiting_consent', 'starting', 'failed', 'finished') else 'not-recording')
        for key in ('heartbeat_monotonic', 'output_progress_monotonic', 'remaining_seconds'):
            number = value.get(key)
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ValueError('malformed-status')
        age = now - value['heartbeat_monotonic']
        if not 0 <= age <= MAX_AGE:
            raise ValueError('stale-status')
        if not 0 <= now - value['output_progress_monotonic'] <= MAX_PROGRESS_AGE:
            raise ValueError('output-stalled')
        if value['remaining_seconds'] < minimum_remaining:
            raise ValueError('insufficient-time')
        pid = value.get('pid')
        if type(pid) is not int or pid <= 0:
            raise ValueError('malformed-status')
        if value.get('boot_id') != boot_identity() or value.get('process_start') != process_identity(pid):
            raise ValueError('recorder-not-live')
        if value.get('audio_mode') not in ('silent', 'system-playback-monitor'):
            raise ValueError('malformed-status')
        if require_audio and value['audio_mode'] != 'system-playback-monitor':
            raise ValueError('audio-not-enabled')
        info, _ = _private_file(output_file)
        if any(type(value.get(key)) is not int for key in ('output_device', 'output_inode', 'output_bytes')):
            raise ValueError('malformed-status')
        if (info.st_dev, info.st_ino) != (value['output_device'], value['output_inode']):
            raise ValueError('different-output')
        if not 0 < value['output_bytes'] <= info.st_size:
            raise ValueError('output-not-started')
        return {'ready': True, 'recording_id': identity, 'audio_mode': value['audio_mode'],
                'remaining_seconds': value['remaining_seconds']}
    except ValueError as error:
        allowed = {'untrusted-file', 'malformed-status', 'unsupported-status', 'different-recording',
                   'awaiting_consent', 'starting', 'failed', 'finished', 'not-recording', 'stale-status',
                   'output-stalled', 'insufficient-time', 'recorder-not-live', 'audio-not-enabled',
                   'different-output', 'output-not-started'}
        reason = str(error) if str(error) in allowed else 'malformed-status'
    except (OSError, IndexError, TypeError):
        pass
    return {'ready': False, 'reason': reason}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status-file', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--recording-id')
    parser.add_argument('--require-audio', action='store_true')
    args = parser.parse_args()
    result = check_ready(args.status_file, args.output, recording_id=args.recording_id,
                         require_audio=args.require_audio)
    print(json.dumps(result))
    return 0 if result['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
