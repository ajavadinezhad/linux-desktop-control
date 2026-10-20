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

class PointerYielded(RuntimeError):
    """A newer physical pointer epoch superseded this bounded resume."""


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
                 credentials=peer_credentials, startup_timeout=60, notice=None,
                 retain_sharing=False, on_yield=None, on_quiet=None, session_seconds=120, pointer_source="mouse"):
        # Dependency injections are for isolated tests, never model tool arguments.
        if type(session_seconds) is not int or not 120<=session_seconds<=600:
            raise ValueError("session_seconds must be an integer from 120 to 600")
        self.requested_session_seconds=session_seconds
        self.session_seconds=120
        self.lease_negotiation_started=False
        self.active = active
        self.on_activity = on_activity
        self.on_fault = on_fault
        self.runtime_dir = runtime_dir
        self.launcher = launcher
        self.validator = validator
        self.credentials = credentials
        self.startup_timeout = startup_timeout
        self.notice = notice
        self.notice_open = False
        self.notice_requested = False
        self.notice_warning = None
        self.notice_acknowledged = False
        self.notice_active = False
        self.notice_close_attempts = 0
        self.notice_delivery_unknown = False
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
        self.calibration_idle_evidence = None
        self.calibration_idle_report_kind = 'not-requested'
        self.calibration_evidence = None
        self.calibration_report_kind = 'not-requested'
        self.calibration_late_result = False
        self.calibration_resets = 0
        self.activity_kind = None
        self.observation_evidence = None
        self.observation_report_kind = 'not-requested'
        if type(retain_sharing) is not bool:raise ValueError('retain_sharing must be boolean')
        if pointer_source not in ("mouse","touchpad") or not isinstance(pointer_source,str):
            raise ValueError("Invalid pointer_source")
        if pointer_source=="touchpad" and not retain_sharing:
            raise ValueError("Touchpad observation requires retained sharing")
        self.pointer_source=pointer_source
        self.retain_sharing=retain_sharing
        self.on_yield=on_yield
        self.on_quiet=on_quiet
        self.yield_condition=threading.Condition(threading.RLock())
        self.yield_epoch=0;self.quiet_epoch=None;self.yielded=False
        self.resume_pending=None;self.resume_ack=None
        self.post_arm_verified=False;self.post_arm_state='not-started';self.post_arm_deadline_monotonic=None
        self.post_arm_gate=False
        self.notice_phase='calibration'

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
            if self.post_arm_gate:self.post_arm_state='failed'
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
            if self.requested_session_seconds!=120:self._negotiate_lease()
            if self.retain_sharing:
                self._negotiate_yield()
            self._send('CALIBRATE')
            self._wait_calibration_start()
            self.calibration_state='waiting'
            self._show_notice()
            print('DESKTOP_CALIBRATION_READY',file=sys.stderr,flush=True)
            self._wait_calibrated()
            self.calibration_state='challenge-seen'
            self._close_notice()
            if self.notice_active or self.notice_delivery_unknown:raise NativeFailure('helper-fault','Calibration notification closure unconfirmed')
            if self.stop.is_set() or not self.active():raise NativeFailure('session-ended','Native observer authorization ended')
            self._send('ARM')
            arm_deadline=time.monotonic()+1
            while True:
                remaining=arm_deadline-time.monotonic()
                if remaining<=0:raise NativeFailure('helper-fault','Native observer did not acknowledge arm')
                armed=self._read(remaining)
                if self.stop.is_set() or not self.active():
                    raise NativeFailure('session-ended','Native observer authorization ended')
                if time.monotonic()>=arm_deadline:
                    raise NativeFailure('helper-fault','Native observer arm acknowledgement expired')
                # A heartbeat reply already in flight from calibration may
                # precede ARMED; it does not establish calibration or authority.
                if armed=='ALIVE':continue
                if armed!='ARMED':
                    raise NativeFailure('helper-fault' if armed in (None,'FAULT') else 'protocol-invalid','Native observer did not acknowledge arm')
                break
            with self.close_lock:
                # Serialize readiness publication against close's stop fence.
                authorized=self.active()
                # An injected authorization callback may close reentrantly.
                if self.closed or self.stop.is_set() or not authorized:
                    raise NativeFailure('session-ended','Native observer authorization ended')
                if time.monotonic()>=arm_deadline:
                    raise NativeFailure('helper-fault','Native observer arm acknowledgement expired')
                self.last_peer = time.monotonic()
                self.armed_at_monotonic = self.last_peer
                self.calibration_verified=True
                self.calibration_state='verified'
                self.post_arm_gate=self.retain_sharing
                self.post_arm_state='waiting-motion' if self.retain_sharing else 'not-started'
                self.post_arm_deadline_monotonic=time.monotonic()+30 if self.retain_sharing else None
                self.ready = not self.retain_sharing
                self.thread = threading.Thread(target=self._monitor, daemon=True, name='native-activity-observer')
                self.thread.start()
            if self.retain_sharing:self._wait_post_arm()
            return self
        except BaseException:
            self.close()
            raise

    def _wait_post_arm(self):
        # The monitor is the sole reader after ARM. This gate never authorizes
        # capture/input from initial calibration or an old quiet token.
        self._show_notice(phase='post-arm-pointer')
        with self.yield_condition:
            while True:
                now=time.monotonic()
                if (not self._yield_authorized() or self.notified or
                        now>=self.post_arm_deadline_monotonic):
                    self.post_arm_state='failed'
                    raise NativeFailure('helper-fault','Post-arm mouse readiness was not verified')
                if self.yielded and self.quiet_epoch==self.yield_epoch:
                    epoch=self.yield_epoch
                    self.post_arm_state='resuming'
                    break
                self.yield_condition.wait(min(.02,self.post_arm_deadline_monotonic-now))
        self._close_notice()
        if self.notice_active or self.notice_delivery_unknown:
            raise NativeFailure('helper-fault','Post-arm notification closure unconfirmed')
        remaining=self.post_arm_deadline_monotonic-time.monotonic()
        if remaining<=0 or not self._yield_authorized() or self.notified:
            raise NativeFailure('helper-fault','Post-arm mouse readiness expired')
        self.resume_from_pause(epoch,timeout=min(1,remaining))
        with self.close_lock:
            with self.yield_condition:
                if (not self._yield_authorized() or self.notified or
                        time.monotonic()>=self.post_arm_deadline_monotonic or self.yielded or
                        self.resume_ack!=epoch or self.yield_epoch!=epoch):
                    self.post_arm_state='failed'
                    raise NativeFailure('helper-fault','Post-arm mouse readiness expired')
                self.post_arm_verified=True;self.post_arm_state='verified'
                self.post_arm_gate=False;self.ready=True

    def _show_notice(self,reset=False,phase=None):
        if self.notice is None:return
        if self.stop.is_set() or not self.active():raise NativeFailure('session-ended','Calibration notification authorization ended')
        new_phase=phase or 'calibration'
        if new_phase!=self.notice_phase and (self.notice_open or self.notice_active or self.notice_delivery_unknown):
            raise NativeFailure('helper-fault','Previous notification closure unconfirmed')
        new_notice=not self.notice_open and not self.notice_active and not self.notice_delivery_unknown
        self.notice_phase=new_phase
        self.notice_requested=True;self.notice_open=True;self.notice_delivery_unknown=True
        try:
            if new_notice:self.notice_close_attempts=0
            if phase is None:self.notice.show(reset=reset)
            else:self.notice.show(reset=reset,phase=phase)
            status=self.notice.status()
            self.notice_acknowledged=status.get('request_acknowledged') is True
            self.notice_active=status.get('request_active') is True
            self.notice_delivery_unknown=status.get('delivery_unknown') is True
            if status.get('warning'):
                self.notice_warning='Calibration notification unavailable; visibility is unverified.'
        except Exception:
            self.notice_warning='Calibration notification unavailable; visibility is unverified.'
        if self.stop.is_set() or not self.active():
            self._close_notice()
            raise NativeFailure('session-ended','Calibration notification authorization ended')

    def _close_notice(self):
        if self.notice is None or not self.notice_open or self.notice_close_attempts>=2:return
        self.notice_close_attempts+=1
        try:
            closed=self.notice.close()
            status=self.notice.status()
            self.notice_acknowledged=status.get('request_acknowledged') is True
            self.notice_active=status.get('request_active') is True
            self.notice_delivery_unknown=status.get('delivery_unknown') is True
            if not self.notice_active and not self.notice_delivery_unknown and closed is not False:self.notice_open=False
            if status.get('warning'):
                self.notice_warning='Calibration notification unavailable or closure unconfirmed; visibility is unverified.'
        except Exception:
            self.notice_warning='Calibration notification closure unconfirmed; visibility is unverified.'

    def _wait_calibration_start(self):
        # The helper may wait briefly for authorization-dialog input to be
        # released. This phase grants no challenge credit or notice authority.
        self.calibration_state='settling'
        now=time.monotonic();deadline=now+6;peer_seen=now;next_heartbeat=now
        while True:
            if not self._yield_authorized():
                raise NativeFailure('session-ended','Native calibration authorization ended')
            now=time.monotonic()
            if now>=deadline:raise NativeFailure('helper-fault','Native observer did not begin calibration')
            message=self._read(min(.02,max(0,deadline-time.monotonic())))
            if not self._yield_authorized():
                raise NativeFailure('session-ended','Native calibration authorization ended')
            now=time.monotonic()
            if now>=deadline:raise NativeFailure('helper-fault','Native observer calibration acknowledgement expired')
            if message=='CALIBRATING':return
            if message=='ALIVE':peer_seen=now
            elif message=='FAULT':raise NativeFailure('helper-fault','Native observer did not begin calibration')
            elif message is not None:raise NativeFailure('protocol-invalid','Native observer calibration response invalid')
            if self.process.poll() is not None:raise NativeFailure('helper-fault','Native calibration helper exited')
            if now-peer_seen>=1:raise NativeFailure('heartbeat-timeout','Native calibration heartbeat expired')
            if now>=next_heartbeat:
                self._send('HB');next_heartbeat=now+.2

    def _wait_calibrated(self):
        # No synthetic challenge: only the authenticated broker can attest that
        # its current calibration phase observed the human's physical challenge.
        deadline=time.monotonic()+30
        peer_seen=time.monotonic();next_heartbeat=peer_seen
        while True:
            if not self.active() or self.stop.is_set():
                raise NativeFailure('session-ended','Native calibration authorization ended')
            message=self._read(.02)
            # The read can complete after revocation or the original deadline.
            # A terminal success token must not jump over either fence.
            if self.stop.is_set() or not self.active():
                raise NativeFailure('session-ended','Native calibration authorization ended')
            if time.monotonic()>=deadline:
                if message=='CALIBRATED':self.calibration_late_result=True
                self._request_calibration_report()
                raise NativeFailure('helper-fault','Native calibration challenge timed out')
            if message=='CALIBRATED':return
            if message=='CALIBRATION_RESET':
                if self.calibration_state!='waiting' or self.calibration_resets>=2:
                    raise NativeFailure('protocol-invalid','Native calibration reset invalid')
                self.calibration_resets+=1
                self._show_notice(reset=True)
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
        # helper-controlled text. Optional idle detail uses fixed local enums.
        self.calibration_idle_evidence=None
        self.calibration_idle_report_kind='not-requested'
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
                    self._read_calibration_idle_report(deadline)
                    if self.calibration_idle_report_kind=='received':
                        self._read_observation_report(deadline)
                else:self.calibration_report_kind='malformed'
                return
        except NativeFailure as error:
            self.calibration_report_kind='transport-closed' if error.reason=='transport-closed' else 'malformed'
        except OSError:self.calibration_report_kind='transport-closed'
        except (RuntimeError,ValueError):self.calibration_report_kind='read-failed'

    def _read_calibration_idle_report(self,deadline):
        # The helper appends this optional line in the same terminal write as
        # CAL_DIAG. A legacy helper need not provide it. Never change base-report
        # success, extend its deadline, or treat diagnostic detail as authority.
        remaining=deadline-time.monotonic()
        if remaining<=0:
            self.calibration_idle_report_kind='timeout';return
        try:message=self._read(min(.05,remaining))
        except (NativeFailure,OSError,RuntimeError,ValueError,StopIteration):
            self.calibration_idle_report_kind='unavailable';return
        if time.monotonic()>deadline:
            self.calibration_idle_report_kind='timeout';return
        if message is None:
            self.calibration_idle_report_kind='missing';return
        kinds={'N':'none','H':'held','K':'key-button','R':'relative-motion','Z':'zero-relative',
               'A':'absolute','S':'switch','C':'clock-metadata','M':'other-metadata'}
        ages={'N':'none','R':'recent','S':'settled'}
        reasons={'M':'missing-category','H':'held','R':'recent-activity','Q':'queue-pending','Y':'ready'}
        if (not isinstance(message,str) or len(message)!=15 or not message.startswith('CAL_IDLE_') or
                message[9] not in kinds or message[10] not in ages or message[11] not in reasons or
                any(bit not in '01' for bit in message[12:])):
            self.calibration_idle_report_kind='malformed';return
        self.calibration_idle_evidence={'last_activity_kind':kinds[message[9]],
            'last_activity_age':ages[message[10]],'quiet_reason':reasons[message[11]],
            'input_queue_pending':message[12]=='1','topology_pending':message[13]=='1',
            'owner_pending':message[14]=='1'}
        self.calibration_idle_report_kind='received'

    def _read_observation_report(self,deadline=None):
        # Optional postmortem only. The collector emits this after closing raw
        # descriptors. Cancellation callbacks run first; concurrent teardown
        # may therefore make detail unavailable without changing the outcome.
        if self.ready or not (self.notified or self.calibration_report_kind=='received'):
            self.observation_report_kind='request-skipped';return
        limit=time.monotonic()+.05
        if deadline is not None:limit=min(limit,deadline)
        remaining=limit-time.monotonic()
        if remaining<=0:
            self.observation_report_kind='timeout';return
        try:message=self._read(remaining)
        except (NativeFailure,OSError,RuntimeError,ValueError,StopIteration):
            self.observation_report_kind='unavailable';return
        if time.monotonic()>limit:
            self.observation_report_kind='timeout';return
        if message is None:
            self.observation_report_kind='missing';return
        if (not isinstance(message,str) or len(message)!=13 or
                not message.startswith('OBS_TPAD_' if self.pointer_source=='touchpad' else 'OBS_DIAG_') or any(bit not in '01' for bit in message[9:])):
            self.observation_report_kind='malformed';return
        names=(('touchpad_calibration_seen','primary_record_after_arm',
                'eligible_touchpad_after_arm','yielded_token_sent') if self.pointer_source=='touchpad' else
               ('relative_calibration_seen','primary_record_after_arm',
                'eligible_relative_after_arm','yielded_token_sent'))
        self.observation_evidence={name:bit=='1' for name,bit in zip(names,message[9:])}
        self.observation_report_kind='received'

    def _notify(self, activity=False, error=None, reason='helper-fault'):
        if self.notified or self.stop.is_set():
            return
        self.notified = True
        if self.post_arm_gate:self.post_arm_state='failed'
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
            try:self._read_observation_report()
            finally:self.close()

    def _consume(self,message):
        if isinstance(message,str) and message.startswith(('YIELDED_','QUIET_','ARMED_')):
            self._consume_yield(message)
            return False
        kinds={'ACTIVITY':'unspecified','ACTIVITY_KEY':'key','ACTIVITY_POINTER':'pointer',
               'ACTIVITY_SWITCH':'switch','ACTIVITY_METADATA':'metadata','ACTIVITY_HELD':'held'}
        if message in kinds:
            self.activity_kind=kinds[message]
            self._notify(activity=True)
            return True
        if message == 'ALIVE':
            self.last_peer=time.monotonic()
        elif message == 'FAULT':
            raise NativeFailure('helper-fault','Native observer fault')
        elif message is not None:
            raise NativeFailure('protocol-invalid','Native observer invalid response')
        return False

    def _negotiate_lease(self):
        # One initial negotiation, before mode/calibration; no active renewal.
        if self.lease_negotiation_started or self.calibration_state!='not-started' or self.ready or self.armed_at_monotonic is not None:
            raise NativeFailure('protocol-invalid','Native lease can only be selected once before calibration')
        self.lease_negotiation_started=True
        seconds=self.requested_session_seconds
        deadline=time.monotonic()+1
        if not self._yield_authorized():raise NativeFailure('session-ended','Native observer authorization ended')
        self._send('LEASE_'+str(seconds))
        reply=self._read(max(0,deadline-time.monotonic()))
        if not self._yield_authorized() or time.monotonic()>=deadline:
            raise NativeFailure('session-ended','Native observer lease acknowledgement expired')
        if reply!='LEASE_'+str(seconds)+'_OK':
            raise NativeFailure('protocol-invalid','Native helper did not acknowledge requested initial lease')
        self.session_seconds=seconds

    def _negotiate_yield(self):
        deadline=time.monotonic()+1
        # Negotiate the selected source explicitly. Neither legacy category
        # evidence nor an acknowledgement for another source grants coverage.
        mode='MODEYIELD3' if self.pointer_source=='touchpad' else 'MODEYIELD2'
        self._send(mode)
        if self._read(max(0,deadline-time.monotonic()))!=mode+'_OK':
            raise NativeFailure('protocol-invalid','Native helper lacks strict retained pointer coverage')
        if time.monotonic()>=deadline or not self._yield_authorized():
            raise NativeFailure('session-ended','Native observer authorization ended')

    def _yield_authorized(self):
        # Authorization callbacks may revoke/close reentrantly; their returned
        # value cannot resurrect a stopped owner or renew the original lease.
        if self.stop.is_set() or self.closed:return False
        authorized=self.active()
        lease=self.helper_ready_at_monotonic
        return (authorized and not self.stop.is_set() and not self.closed and
                lease is not None and time.monotonic()-lease<self.session_seconds)

    def is_current_yield(self,epoch,quiet=False):
        with self.yield_condition:
            return (type(epoch) is int and self.retain_sharing and self.yielded and
                    self.yield_epoch==epoch and (not quiet or self.quiet_epoch==epoch) and
                    self._yield_authorized())

    def _consume_yield(self,message):
        kind,number=message.split('_',1)
        if (not self.retain_sharing or not number.isascii() or not number.isdigit() or
                number.startswith('0') or not 1<=int(number)<=64):
            raise NativeFailure('protocol-invalid','Native pointer epoch invalid')
        epoch=int(number);callback=None
        with self.yield_condition:
            if not self._yield_authorized():
                raise NativeFailure('session-ended','Native pointer authorization ended')
            if self.post_arm_gate and time.monotonic()>=self.post_arm_deadline_monotonic:
                raise NativeFailure('helper-fault','Post-arm mouse readiness expired')
            if kind=='YIELDED':
                if epoch!=self.yield_epoch+1:raise NativeFailure('protocol-invalid','Native pointer epoch out of order')
                self.yield_epoch=epoch;self.yielded=True;self.quiet_epoch=None
                self.ready=False;self.resume_ack=None
                if self.post_arm_gate:self.post_arm_state='waiting-quiet'
                else:callback=self.on_yield
            elif kind=='QUIET':
                if not self.yielded or epoch!=self.yield_epoch or self.quiet_epoch is not None:
                    raise NativeFailure('protocol-invalid','Native quiet epoch invalid')
                self.quiet_epoch=epoch
                if not self.post_arm_gate:callback=self.on_quiet
            elif kind=='ARMED':
                pending=self.resume_pending
                if (pending is None or pending[0]!=epoch or epoch!=self.yield_epoch or
                        not self.yielded or self.quiet_epoch!=epoch or time.monotonic()>=pending[1]):
                    raise NativeFailure('protocol-invalid','Native resume acknowledgement invalid')
                self.resume_ack=epoch;self.yielded=False;self.quiet_epoch=None;self.ready=not self.post_arm_gate
            self.last_peer=time.monotonic()
            self.yield_condition.notify_all()
        if callback is not None:callback(self,epoch)

    def resume_from_pause(self,expected_epoch,timeout=1):
        if threading.current_thread() is self.thread:
            raise NativeFailure('protocol-invalid','Native monitor cannot wait for its own acknowledgement')
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0<timeout<=1:
            raise ValueError('Native resume timeout must be bounded')
        deadline=time.monotonic()+timeout
        try:
            with self.yield_condition:
                if not self.is_current_yield(expected_epoch,quiet=True) or self.resume_pending is not None:
                    raise NativeFailure('protocol-invalid','Native pointer resume is stale or busy')
                self.resume_pending=(expected_epoch,deadline);self.resume_ack=None
                self._send('RESUME_'+str(expected_epoch))
                while True:
                    if not self._yield_authorized():raise NativeFailure('session-ended','Native pointer authorization ended')
                    if time.monotonic()>=deadline:raise NativeFailure('helper-fault','Native pointer resume acknowledgement expired')
                    if self.yield_epoch!=expected_epoch:raise PointerYielded('Native pointer moved during resume')
                    if self.resume_ack==expected_epoch and (self.ready or self.post_arm_gate) and not self.yielded:return expected_epoch
                    self.yield_condition.wait(min(.02,max(0,deadline-time.monotonic())))
        except PointerYielded:
            raise
        except Exception:
            self._notify(error='Native pointer resume failed; desktop must close',reason='protocol-invalid')
            raise
        finally:
            with self.yield_condition:self.resume_pending=None;self.yield_condition.notify_all()

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
                'observer_alive':self.calibration_verified and not self.stop.is_set() and not self.closed,
                'yielded':self.yielded,'yield_epoch':self.yield_epoch,'quiet_epoch':self.quiet_epoch,
                'retain_sharing':self.retain_sharing,'pointer_source':self.pointer_source,
                'post_arm_verified':self.post_arm_verified,'post_arm_state':self.post_arm_state,
                'post_arm_remaining_seconds':None if self.post_arm_deadline_monotonic is None else max(0,int(self.post_arm_deadline_monotonic-time.monotonic())),
                'human_provenance': False, 'raw_device_fds': False,
                'error': self.error, 'cleanup_warning': self.cleanup_warning,
                'terminal_reason':self.terminal_reason,'helper_exit_code':self.helper_exit_code,
                'armed_at_monotonic':self.armed_at_monotonic,'elapsed_seconds':elapsed,
                'session_seconds':self.session_seconds,'requested_session_seconds':self.requested_session_seconds,
                'lease_remaining_seconds':None if lease_elapsed is None else max(0,self.session_seconds-lease_elapsed),
                'helper_ready_at_monotonic':self.helper_ready_at_monotonic,
                'calibration_verified':self.calibration_verified,'calibration_state':self.calibration_state,
                'calibration_evidence':self.calibration_evidence,
                'calibration_report_kind':self.calibration_report_kind,
                'calibration_idle_evidence':self.calibration_idle_evidence,
                'calibration_idle_report_kind':self.calibration_idle_report_kind,
                'calibration_late_result':self.calibration_late_result,
                'calibration_resets':self.calibration_resets,'activity_kind':self.activity_kind,
                'observation_evidence':self.observation_evidence,
                'observation_report_kind':self.observation_report_kind,
                'calibration_notice':{'requested':self.notice_requested,'request_acknowledged':self.notice_acknowledged,'request_active':self.notice_active,'delivery_unknown':self.notice_delivery_unknown,'visibility_verified':False,'warning':self.notice_warning},
                'lease_remaining_is_estimate':True}

    def close(self):
        if self.terminal_reason is None:self.terminal_reason='closed'
        if (self.armed_at_monotonic is not None or self.helper_ready_at_monotonic is not None) and self.ended_at_monotonic is None:self.ended_at_monotonic=time.monotonic()
        with self.close_lock:
            self.stop.set()
            self.ready = False
        with self.yield_condition:self.yield_condition.notify_all()
        self._close_notice()
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
