"""Path-independent identity of the reviewed runtime source; no desktop side effects."""
import hashlib
import pathlib
import stat

RUNTIME_FILES = (
    'calibration_notice.py',
    'desktop.py', 'indicator_bridge.py', 'native_activity.py',
    'runtime_build.py', 'target_guard.py', 'window_guard.py',
    'monitor_mapping.py', 'stream_metadata.py', 'frame_observer.py', 'change_notifications.py',
)
MAX_SOURCE_BYTES = 2 * 1024 * 1024


def fingerprint(directory=None):
    root = pathlib.Path(directory) if directory is not None else pathlib.Path(__file__).parent
    digest = hashlib.sha256()
    for name in RUNTIME_FILES:
        path = root / name
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SOURCE_BYTES:
            raise RuntimeError('Invalid desktop runtime source')
        with path.open('rb') as source:
            content = source.read(MAX_SOURCE_BYTES + 1)
        if len(content) > MAX_SOURCE_BYTES:
            raise RuntimeError('Invalid desktop runtime source')
        digest.update(name.encode('ascii') + b'\0')
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    return digest.hexdigest()
