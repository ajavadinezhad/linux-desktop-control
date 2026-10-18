"""Opt-in native broker controller. Importing never launches or authorizes anything.
No raw input descriptor or event contents enter this process. Installation and
broker privilege review are separate; a successful handshake is required.
"""
import os
from pathlib import Path
import select
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time

HELPER = '/usr/libexec/codex-desktop-activity'
PKEXEC = '/usr/bin/pkexec'


TERMINAL_REASONS = frozenset(('activity','helper-fault','heartbeat-timeout',
    'protocol-invalid','transport-closed','session-ended','closed'))

class NativeFailure(RuntimeError):
    def __init__(self,reason,message):
        super().__init__(message)
        self.reason=reason if reason in TERMINAL_REASONS else 'protocol-invalid'


def validate_helper():
    """Accept only the fixed executable and root-owned nonwritable ancestors."""
    for filename in (HELPER, PKEXEC):
        path = Path(filename)
        for entry in (path, *path.parents):
            info = entry.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise RuntimeError('Native helper installation is not trusted')
            if entry != path and not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('Native helper parent is not a directory')
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & stat.S_IXUSR:
            raise RuntimeError('Native helper is not executable')


def peer_credentials(connection):
    return struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))


class Controller:
    def __init__(self, active, on_activity, on_fault, runtime_dir=None,
                 launcher=subprocess.Popen, validator=validate_helper,
                 credentials=peer_credentials, startup_timeout=60):
        # Dependency injections are for isolated tests, never model tool arguments.
        self.active = active
        self.on_activity = on_activity
        self.on_fault = on_fault
        self.runtime_dir = runtime_dir
        self.launcher = launcher
        self.validator = validator
        self.credentials = credentials
        self.startup_timeout = startup_timeout
        self.listener = None
        self.connection = None
        self.process = None
        self.directory = None
        self.thread = None
        self.stop = threading.Event()
        self.send_lock = threading.Lock()
        self.close_lock = threading.RLock()
        self.buffer = bytearray()
        self.ready = False
        self.error = None
        self.cleanup_warning = None
        self.notified = False
        self.closed = False
        self.last_peer = None
        self.terminal_reason = None
        self.helper_exit_code = None
        self.armed_at_monotonic = None
        self.ended_at_monotonic = None
        self.helper_ready_at_monotonic = None
        self.calibration_verified = False
        self.calibration_state = 'not-started'
        self.calibration_evidence = None
        self.calibration_report_kind = 'not-requested'
        self.calibration_late_result = False
        self.calibration_resets = 0

    def _send(self, token):
        payload = (token + '\n').encode('ascii')
        with self.send_lock:
            connection = self.connection
            if connection is None or not select.select([], [connection], [], .2)[1]:
                raise NativeFailure('transport-closed','Native observer transport unavailable')
            if connection.send(payload) != len(payload):
                raise NativeFailure('transport-closed','Native observer command incomplete')

    def _read(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            if b'\n' in self.buffer:
                line, _, remainder = self.buffer.partition(b'\n')
                self.buffer = bytearray(remainder)
                if len(line) > 128:
                    raise NativeFailure('protocol-invalid','Native observer message oversized')
                try:
                    return line.decode('ascii')
                except UnicodeError:
                    raise NativeFailure('protocol-invalid','Native observer message invalid') from None
            if len(self.buffer) > 128:
                raise NativeFailure('protocol-invalid','Native observer message oversized')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            connection = self.connection
            if connection is None:
                raise NativeFailure('transport-closed','Native observer connection closed')
            if not select.select([connection], [], [], remaining)[0]:
                return None
            chunk = connection.recv(256)
            if not chunk:
                raise NativeFailure('transport-closed','Native observer disconnected')
            self.buffer.extend(chunk)

    def start(self):
        try:return self._start()
        except BaseException as error:
            self.terminal_reason=(error.reason if isinstance(error,NativeFailure) else 'helper-fault')
            self.error='Native activity observer startup failed'
            if not self.calibration_verified:self.calibration_state='failed'
            self.close()
            raise

    def _start(self):
        if self.process is not None or self.closed:
            raise RuntimeError('Native observer cannot restart')
        if not self.active():
            raise NativeFailure('session-ended','Native observer requires active authorization')
        self.validator()
        base = Path(self.runtime_dir or os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
        info = base.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError('Native observer runtime directory is not private')
        try:
            self.directory = Path(tempfile.mkdtemp(prefix='codex-activity-', dir=base))
            os.chmod(self.directory, 0o700)
            path = self.directory / 'observer.sock'
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
            self.listener.bind(str(path))
            os.chmod(path, 0o600)
            self.listener.listen(1)
            self.listener.setblocking(False)
            self.process = self.launcher([PKEXEC, HELPER, '--socket', str(path)], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            deadline = time.monotonic() + self.startup_timeout
            while True:
                if not self.active() or self.stop.is_set():
                    raise NativeFailure('session-ended','Native observer authorization ended')
                if self.process.poll() is not None:
                    raise NativeFailure('helper-fault','Native helper exited before readiness')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise NativeFailure('helper-fault','Native helper authorization timed out')
                if select.select([self.listener], [], [], min(.2, remaining))[0]:
                    self.connection, _ = self.listener.accept()
                    break
            self.connection.setblocking(False)
            _pid, uid, _gid = self.credentials(self.connection)
            if uid != 0:
                raise NativeFailure('protocol-invalid','Native observer peer is not root authenticated')
            self.listener.close()
            self.listener = None
            readiness=self._read(5)
            if readiness != 'READY':
                try:
                    code = self.process.wait(timeout=.5)
                    self.helper_exit_code=code
                except subprocess.TimeoutExpired:
                    code = None
                raise NativeFailure('helper-fault' if readiness in (None,'FAULT') else 'protocol-invalid','Native observer did not become ready')
            self.helper_ready_at_monotonic=time.monotonic()
            self._send('CALIBRATE')
            calibrating=self._read(1)
            if calibrating != 'CALIBRATING':
                raise NativeFailure('helper-fault' if calibrating in (None,'FAULT') else 'protocol-invalid','Native observer did not begin calibration')
            self.calibration_state='waiting'
            print('DESKTOP_CALIBRATION_READY',file=sys.stderr,flush=True)
            self._wait_calibrated()
            self.calibration_state='challenge-seen'
            self._send('ARM')
            arm_deadline=time.monotonic()+1
            while True:
                remaining=arm_deadline-time.monotonic()
                if remaining<=0:raise NativeFailure('helper-fault','Native observer did not acknowledge arm')
                armed=self._read(remaining)
                # A heartbeat reply already in flight from calibration may
                # precede ARMED; it does not establish calibration or authority.
                if armed=='ALIVE':continue
                if armed!='ARMED':
                    raise NativeFailure('helper-fault' if armed in (None,'FAULT') else 'protocol-invalid','Native observer did not acknowledge arm')
                break
            if not self.active():
                raise NativeFailure('session-ended','Native observer authorization ended')
            self.last_peer = time.monotonic()
            self.armed_at_monotonic = self.last_peer
            self.calibration_verified=True
            self.calibration_state='verified'
            self.ready = True
            self.thread = threading.Thread(target=self._monitor, daemon=True, name='native-activity-observer')
            self.thread.start()
            return self
        except BaseException:
            self.close()
            raise

    def _wait_calibrated(self):
        # No synthetic challenge: only the authenticated broker can attest that
        # its current calibration phase observed the human's physical challenge.
        deadline=time.monotonic()+30
        peer_seen=time.monotonic();next_heartbeat=peer_seen
        while True:
            if not self.active() or self.stop.is_set():
                raise NativeFailure('session-ended','Native calibration authorization ended')
            message=self._read(.02)
            if message=='CALIBRATED':return
            if message=='CALIBRATION_RESET':
                if self.calibration_state!='waiting' or self.calibration_resets>=2:
                    raise NativeFailure('protocol-invalid','Native calibration reset invalid')
                self.calibration_resets+=1
                print('DESKTOP_CALIBRATION_READY_AGAIN',file=sys.stderr,flush=True)
            elif message=='ALIVE':peer_seen=time.monotonic()
            elif message=='FAULT':raise NativeFailure('helper-fault','Native calibration failed')
            elif message is not None:raise NativeFailure('protocol-invalid','Native calibration response invalid')
            now=time.monotonic()
            if self.process.poll() is not None:raise NativeFailure('helper-fault','Native calibration helper exited')
            if now>=deadline:
                self._request_calibration_report()
                raise NativeFailure('helper-fault','Native calibration challenge timed out')
            if now-peer_seen>=1:raise NativeFailure('heartbeat-timeout','Native calibration heartbeat expired')
            if now>=next_heartbeat:
                self._send('HB');next_heartbeat=now+.2

    def _request_calibration_report(self):
        # Terminal diagnostics only. Export locally chosen enum labels, never
        # helper-controlled text; eight literal bits are the only accepted data.
        if self.calibration_state!='waiting' or self.calibration_verified or self.ready:
            self.calibration_report_kind='request-skipped'
            return
        names=('keyboard_seen','pointer_seen','any_stream_record','query_success',
               'any_held_seen','held_last_check','quiet_blocked','any_stale_timestamp')
        deadline=time.monotonic()+2
        self.calibration_report_kind='send-pending'
        try:self._send('REPORT')
        except (OSError,RuntimeError,ValueError):
            self.calibration_report_kind='send-failed'
            return
        self.calibration_report_kind='reply-pending'
        try:
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    self.calibration_report_kind='timeout'
                    return
                message=self._read(remaining)
                if message=='ALIVE':continue
                if message=='CALIBRATION_RESET':
                    if self.calibration_resets>=2:
                        self.calibration_report_kind='malformed'
                        return
                    self.calibration_resets+=1
                    continue # Terminal reporting never requests another challenge.
                if message=='CALIBRATED':
                    self.calibration_late_result=True
                    continue # Timeout already won; never ARM on this late result.
                if message is None:
                    self.calibration_report_kind='missing'
                elif message=='FAULT':
                    self.calibration_report_kind='fault'
                elif len(message)==17 and message.startswith('CAL_DIAG_') and all(bit in '01' for bit in message[9:]):
                    self.calibration_evidence={name:bit=='1' for name,bit in zip(names,message[9:])}
                    self.calibration_report_kind='received'
                else:self.calibration_report_kind='malformed'
                return
        except NativeFailure as error:
            self.calibration_report_kind='transport-closed' if error.reason=='transport-closed' else 'malformed'
        except OSError:self.calibration_report_kind='transport-closed'
        except (RuntimeError,ValueError):self.calibration_report_kind='read-failed'

    def _notify(self, activity=False, error=None, reason='helper-fault'):
        if self.notified or self.stop.is_set():
            return
        self.notified = True
        self.ready = False
        self.error = error
        self.terminal_reason='activity' if activity else reason
        self.ended_at_monotonic=time.monotonic()
        try:
            if activity:
                self.on_activity()
            else:
                self.on_fault(error or 'Native observer fault')
        finally:
            self.close()

    def _consume(self,message):
        if message == 'ACTIVITY':
            self._notify(activity=True)
            return True
        if message == 'ALIVE':
            self.last_peer=time.monotonic()
        elif message == 'FAULT':
            raise NativeFailure('helper-fault','Native observer fault')
        elif message is not None:
            raise NativeFailure('protocol-invalid','Native observer invalid response')
        return False

    def _drain_final(self):
        # The authenticated helper may notify then immediately close/exit. Read
        # its last token before interpreting process death or a broken HB write.
        deadline=time.monotonic()+.05
        for _ in range(16):
            message=self._read(max(0,deadline-time.monotonic()))
            if self._consume(message):return True
            if message is None:return False
        raise NativeFailure('protocol-invalid','Native observer final message flood')

    def _monitor(self):
        next_heartbeat=time.monotonic()
        try:
            while not self.stop.is_set():
                if not self.active():
                    self.terminal_reason='session-ended'
                    self.close()
                    return
                # Reads take priority even when process.poll already reports exit.
                if self._consume(self._read(.02)):return
                if self.process.poll() is not None:
                    if self._drain_final():return
                    raise NativeFailure('helper-fault','Native helper exited')
                now=time.monotonic()
                if now>=next_heartbeat:
                    try:self._send('HB')
                    except (OSError,RuntimeError):
                        if self._drain_final():return
                        raise
                    next_heartbeat=now+.2
                if time.monotonic()-self.last_peer>=1:
                    raise NativeFailure('heartbeat-timeout','Native observer heartbeat expired')
        except Exception as error:
            # Taxonomy is local fixed enums, never helper-controlled text.
            reason=error.reason if isinstance(error,NativeFailure) else ('transport-closed' if isinstance(error,OSError) else 'helper-fault')
            self._notify(error='Native activity observation failed; desktop must close',reason=reason)

    def status(self):
        elapsed=None if self.armed_at_monotonic is None else max(0,(self.ended_at_monotonic or time.monotonic())-self.armed_at_monotonic)
        lease_start=self.helper_ready_at_monotonic or self.armed_at_monotonic
        lease_elapsed=None if lease_start is None else max(0,(self.ended_at_monotonic or time.monotonic())-lease_start)
        return {'active': self.ready and not self.stop.is_set(), 'supported': self.ready,
                'human_provenance': False, 'raw_device_fds': False,
                'error': self.error, 'cleanup_warning': self.cleanup_warning,
                'terminal_reason':self.terminal_reason,'helper_exit_code':self.helper_exit_code,
                'armed_at_monotonic':self.armed_at_monotonic,'elapsed_seconds':elapsed,
                'lease_remaining_seconds':None if lease_elapsed is None else max(0,120-lease_elapsed),
                'helper_ready_at_monotonic':self.helper_ready_at_monotonic,
                'calibration_verified':self.calibration_verified,'calibration_state':self.calibration_state,
                'calibration_evidence':self.calibration_evidence,
                'calibration_report_kind':self.calibration_report_kind,
                'calibration_late_result':self.calibration_late_result,
                'calibration_resets':self.calibration_resets,
                'lease_remaining_is_estimate':True}

    def close(self):
        if self.terminal_reason is None:self.terminal_reason='closed'
        if (self.armed_at_monotonic is not None or self.helper_ready_at_monotonic is not None) and self.ended_at_monotonic is None:self.ended_at_monotonic=time.monotonic()
        self.stop.set()
        self.ready = False
        # Socket shutdown wakes an independent reader before any join.
        connection = self.connection
        if connection is not None:
            try:
                self._send('CLOSE')
            except (OSError, RuntimeError, ValueError):
                pass
            if self.process is not None:
                try:self.helper_exit_code=self.process.wait(timeout=.1)
                except (OSError,subprocess.TimeoutExpired):pass
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=.5)
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            if self.listener is not None:
                self.listener.close()
                self.listener = None
            if self.process is not None:
                try:
                    self.helper_exit_code=self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        self.process.terminate()
                        self.helper_exit_code=self.process.wait(timeout=.5)
                    except (OSError, subprocess.TimeoutExpired):
                        try:
                            self.process.kill()
                            self.helper_exit_code=self.process.wait(timeout=.5)
                        except (OSError, subprocess.TimeoutExpired):
                            self.cleanup_warning = 'Native helper exit unconfirmed; socket is closed'
            if self.directory is not None:
                shutil.rmtree(self.directory)
                self.directory = None
            self.buffer.clear()
