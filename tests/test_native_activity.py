"""Fake socket peers only: never runs pkexec or opens input devices."""
import importlib.util
import contextlib
import io
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_activity_test',ROOT/'plugins/linux-desktop-control/native_activity.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class FakeBroker:
 def __init__(self,args,mode='normal',**kwargs):
  self.args=args;self.mode=mode;self.done=threading.Event();self.connection=None;self.returncode=None;self.commands=[];self.error=None
  assert args[:3]==[m.PKEXEC,m.HELPER,'--socket']
  assert stat.S_IMODE(Path(args[3]).parent.stat().st_mode)==0o700
  assert stat.S_IMODE(Path(args[3]).stat().st_mode)==0o600
  assert kwargs['close_fds'] is True
  self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def run(self):
  try:
   s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.connection=s;s.settimeout(3);s.connect(self.args[3])
   if self.mode=='fragmented':
    s.sendall(b'RE');time.sleep(.01);s.sendall(b'ADY\n')
   else:s.sendall(b'READY\n')
   stream=s.makefile('rb');line=stream.readline().decode().strip();self.commands.append(line)
   if line!='CALIBRATE':return
   s.sendall(b'CALIBRATING\n')
   if self.mode=='calibrationfault':s.sendall(b'FAULT\n');stream.close();return
   if self.mode=='calibrationactivity':s.sendall(b'ACTIVITY\n');stream.close();return
   if self.mode=='calibrationeof':stream.close();return
   if self.mode=='calibrationdelay':
    for _ in range(2):
     heartbeat=stream.readline().decode().strip();self.commands.append(heartbeat)
     if heartbeat!='HB':return
     s.sendall(b'ALIVE\n')
   s.sendall(b'CALIBRATED\n')
   if self.mode=='calibrationdelay':s.sendall(b'ALIVE\n')
   line=stream.readline().decode().strip();self.commands.append(line)
   if line!='ARM':return
   s.sendall(b'ARMED\n')
   if self.mode=='finalactivity':
    s.sendall(b'ACTIVITY\n');stream.close();return
   if self.mode=='activity':s.sendall(b'ACTIVITY\n')
   elif self.mode=='fragmented':s.sendall(b'ALIVE\nACTIVITY\n')
   elif self.mode=='wrongnonce':s.sendall(b'ACTIVITY wrong\n')
   elif self.mode=='fault':s.sendall(b'FAULT\n')
   elif self.mode=='eof':return
   elif self.mode=='oversized':s.sendall(b'X'*257)
   while not self.done.is_set():
    line=stream.readline()
    if not line:break
    text=line.decode().strip();self.commands.append(text)
    if text=='CLOSE':break
    if self.mode=='normal' and text=='HB':s.sendall(b'ALIVE\n')
   stream.close()
  except (OSError,IndexError) as error:self.error=type(error).__name__
  finally:
   if self.connection:self.connection.close()
   self.returncode=0;self.done.set()
 def poll(self):return None if self.mode=='eof' else self.returncode
 def wait(self,timeout=None):
  if not self.done.wait(timeout):raise subprocess.TimeoutExpired(self.args,timeout)
  return self.returncode
 def terminate(self):
  self.done.set()
  if self.connection:
   try:self.connection.shutdown(socket.SHUT_RDWR)
   except OSError:pass
 def kill(self):self.terminate()

class NativeActivityTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);os.chmod(self.temp.name,0o700);self.activity=threading.Event();self.fault=threading.Event();self.errors=[];self.brokers=[]
 def controller(self,mode='normal',uid=0,validator=lambda:None,notice=None):
  def launch(args,**kwargs):
   b=FakeBroker(args,mode,**kwargs);self.brokers.append(b);return b
  def fail(error):self.errors.append(error);self.fault.set()
  c=m.Controller(lambda:True,self.activity.set,fail,runtime_dir=self.temp.name,launcher=launch,validator=validator,credentials=lambda s:(123,uid,0),startup_timeout=1,notice=notice)
  self.addCleanup(c.close);return c
 def test_authenticated_handshake_heartbeat_and_private_cleanup(self):
  c=self.controller().start();path=c.directory;time.sleep(.45);self.assertTrue(c.status()['active']);self.assertFalse(self.fault.is_set());c.close();c.close();self.assertFalse(path.exists());self.assertFalse(c.status()['raw_device_fds']);self.assertTrue('HB' in self.brokers[0].commands);self.assertIn('CLOSE',self.brokers[0].commands);self.assertEqual(c.status()['terminal_reason'],'closed');self.assertEqual(c.status()['helper_exit_code'],0)
 def test_activity_cancels_independently_and_closes(self):
  c=self.controller('activity').start();self.assertTrue(self.activity.wait(2));c.close();self.assertFalse(c.status()['active']);self.assertFalse(self.fault.is_set());self.assertEqual(c.status()['terminal_reason'],'activity');self.assertEqual(c.status()['helper_exit_code'],0)
 def test_fault_eof_invalid_token_and_oversize_fail_closed(self):
  for mode in ('fault','eof','wrongnonce','oversized'):
   with self.subTest(mode=mode):
    self.fault.clear();c=self.controller(mode).start();self.assertTrue(self.fault.wait(2));c.close();self.assertFalse(c.status()['active']);self.assertFalse(self.activity.is_set());self.assertEqual(c.status()['terminal_reason'],{'fault':'helper-fault','eof':'transport-closed','wrongnonce':'protocol-invalid','oversized':'protocol-invalid'}[mode]);self.assertEqual(c.status()['helper_exit_code'],0)
 def test_fragmented_ready_and_coalesced_activity_are_parsed(self):
  c=self.controller('fragmented').start();self.assertTrue(self.activity.wait(2));c.close();self.assertFalse(self.fault.is_set())
 def test_silent_peer_expires_heartbeat(self):
  c=self.controller('silent').start();self.assertTrue(self.fault.wait(2));c.close();self.assertIn('failed',c.status()['error']);self.assertEqual(c.status()['terminal_reason'],'heartbeat-timeout')
 def test_nonroot_peer_never_arms(self):
  c=self.controller(uid=1000)
  with self.assertRaisesRegex(RuntimeError,'not root authenticated'):c.start()
  self.assertFalse(c.status()['active']);self.assertFalse('ARM' in self.brokers[0].commands);self.assertEqual(c.status()['terminal_reason'],'protocol-invalid');self.assertEqual(c.status()['helper_exit_code'],0)
 def test_untrusted_or_missing_installation_never_launches(self):
  def reject():raise RuntimeError('untrusted installation')
  c=self.controller(validator=reject)
  with self.assertRaisesRegex(RuntimeError,'untrusted'):c.start()
  self.assertEqual(self.brokers,[]);self.assertIsNone(c.directory)
 def test_real_validator_rejects_symlink_and_writable_executable(self):
  file=Path(self.temp.name)/'helper';file.write_text('x');link=Path(self.temp.name)/'link';link.symlink_to(file)
  with patch.object(m,'HELPER',str(link)):
   with self.assertRaisesRegex(RuntimeError,'not trusted'):m.validate_helper()
  class FakePath:
   parents=()
   def lstat(self):return SimpleNamespace(st_mode=stat.S_IFREG|0o777,st_uid=0)
  with patch.object(m,'Path',return_value=FakePath()):
   with self.assertRaisesRegex(RuntimeError,'not trusted'):m.validate_helper()
 def test_unsafe_runtime_directory_never_launches(self):
  os.chmod(self.temp.name,0o755);c=self.controller()
  with self.assertRaisesRegex(RuntimeError,'not private'):c.start()
  self.assertEqual(self.brokers,[])

 def test_terminal_reason_visible_before_callback_and_close_preserves_it(self):
  c=self.controller();seen=[];c.on_activity=lambda:seen.append(c.status()['terminal_reason']);c.armed_at_monotonic=time.monotonic();c._notify(activity=True);self.assertEqual(seen,['activity']);self.assertEqual(c.status()['terminal_reason'],'activity')
 def test_session_ended_has_fixed_reason_and_elapsed_freezes(self):
  c=self.controller().start();c.active=lambda:False
  deadline=time.monotonic()+2
  while c.status()['helper_exit_code'] is None and time.monotonic()<deadline:time.sleep(.01)
  self.assertTrue(c.closed);self.assertEqual(c.status()['terminal_reason'],'session-ended');self.assertEqual(c.status()['helper_exit_code'],0);elapsed=c.status()['elapsed_seconds'];time.sleep(.01);self.assertEqual(c.status()['elapsed_seconds'],elapsed);self.assertLessEqual(c.status()['lease_remaining_seconds'],120-elapsed)
 def test_approximate_lease_metadata_is_local_and_clamped(self):
  c=self.controller();self.assertIsNone(c.status()['armed_at_monotonic']);self.assertIsNone(c.status()['lease_remaining_seconds']);c.armed_at_monotonic=time.monotonic()-121;self.assertEqual(c.status()['lease_remaining_seconds'],0);self.assertTrue(c.status()['lease_remaining_is_estimate'])
 def test_start_failure_retains_helper_exit_code_without_helper_text(self):
  c=self.controller()
  class Failed:
   def wait(self,timeout):return 47
  def fail_start():c.process=Failed();raise RuntimeError('untrusted diagnostic contents')
  c._start=fail_start
  with self.assertRaises(RuntimeError):c.start()
  self.assertEqual(c.status()['terminal_reason'],'helper-fault');self.assertEqual(c.status()['helper_exit_code'],47);self.assertNotIn('untrusted diagnostic',str(c.status()))

 def test_final_activity_then_helper_exit_is_not_lost(self):
  c=self.controller('finalactivity').start();self.assertTrue(self.activity.wait(2));c.close();self.assertFalse(self.fault.is_set());self.assertEqual(c.status()['terminal_reason'],'activity');self.assertEqual(c.status()['helper_exit_code'],0)
 def test_buffered_activity_wins_over_already_exited_process(self):
  c=self.controller();c.ready=True;c.last_peer=time.monotonic();c.buffer.extend(b'ACTIVITY\n');sent=[];c._send=sent.append;c.process=SimpleNamespace(poll=lambda:0,wait=lambda timeout:0);c._monitor();self.assertTrue(self.activity.is_set());self.assertFalse(self.fault.is_set());self.assertEqual(c.status()['terminal_reason'],'activity');self.assertNotIn('HB',sent)
 def test_broken_heartbeat_still_drains_final_terminal_token(self):
  for token,reason in ((b'ACTIVITY\n','activity'),(b'FAULT\n','helper-fault')):
   with self.subTest(token=token):
    self.activity.clear();self.fault.clear();c=self.controller();c.ready=True;c.last_peer=time.monotonic();c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0);read=c._read;reads=[]
    def first_empty(timeout):
     if not reads:reads.append(1);return None
     return read(timeout)
    def broken_send(message):
     if message=='HB':c.buffer.extend(token);raise BrokenPipeError('fixed test fixture')
    c._read=first_empty;c._send=broken_send;c._monitor();self.assertEqual(c.status()['terminal_reason'],reason);self.assertEqual(self.activity.is_set(),reason=='activity');self.assertEqual(self.fault.is_set(),reason!='activity')
 def test_eof_without_final_token_remains_fault(self):
  c=self.controller();c.ready=True;c.last_peer=time.monotonic();c.process=SimpleNamespace(poll=lambda:0,wait=lambda timeout:0);c._monitor();self.assertTrue(self.fault.is_set());self.assertFalse(self.activity.is_set());self.assertEqual(c.status()['terminal_reason'],'transport-closed')

 def test_calibration_verified_only_after_human_challenge_result_and_arm(self):
  c=self.controller('calibrationdelay');self.assertFalse(c.status()['calibration_verified']);c.start();self.assertTrue(c.status()['calibration_verified']);self.assertEqual(c.status()['calibration_state'],'verified');commands=self.brokers[-1].commands;self.assertEqual(commands[:2],['CALIBRATE','HB']);self.assertLess(commands.index('CALIBRATE'),commands.index('ARM'));self.assertEqual(commands[:commands.index('ARM')].count('HB'),2);c.close()
 def test_calibration_fault_or_unexpected_activity_never_arms(self):
  for mode in ('calibrationfault','calibrationactivity','calibrationeof'):
   with self.subTest(mode=mode):
    c=self.controller(mode)
    with self.assertRaises(m.NativeFailure):c.start()
    self.assertNotIn('ARM',self.brokers[-1].commands);self.assertFalse(c.status()['calibration_verified']);self.assertEqual(c.status()['calibration_state'],'failed');self.assertFalse(self.activity.is_set())
 def test_missing_challenge_times_out_with_heartbeat_but_without_arm(self):
  c=self.controller();clock=[0.0];sent=[];c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0)
  def read(timeout):clock[0]+=.25;return 'ALIVE'
  c._read=read;c._send=sent.append
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
   with self.assertRaisesRegex(m.NativeFailure,'challenge timed out'):c._wait_calibrated()
  self.assertGreaterEqual(clock[0],30);self.assertIn('HB',sent);self.assertNotIn('ARM',sent);self.assertFalse(c.status()['calibration_verified'])
 def test_calibration_time_is_subtracted_from_absolute_lease_estimate(self):
  c=self.controller();now=time.monotonic();c.helper_ready_at_monotonic=now-25;c.armed_at_monotonic=now-5;c.ended_at_monotonic=now;self.assertEqual(c.status()['elapsed_seconds'],5);self.assertEqual(c.status()['lease_remaining_seconds'],95)

 def test_terminal_report_accepts_only_exact_fixed_evidence_bits(self):
  for token,accepted in (('CAL_DIAG_10101010',True),('CAL_DIAG_00000000',True),('FAULT',False),('CAL_DIAG_1010101',False),('CAL_DIAG_1010101x',False),('CAL_DIAG_101010100',False)):
   with self.subTest(token=token):
    c=self.controller();c.calibration_state='waiting';sent=[];messages=iter(('ALIVE',token));c._send=sent.append;c._read=lambda timeout:next(messages);c._request_calibration_report();self.assertEqual(sent,['REPORT']);evidence=c.status()['calibration_evidence'];self.assertEqual(evidence is not None,accepted);self.assertEqual(c.status()['calibration_report_kind'],'received' if accepted else ('fault' if token=='FAULT' else 'malformed'));self.assertFalse(c.calibration_verified);self.assertNotIn('ARM',sent)
    if accepted:self.assertTrue(all(type(v) is bool for v in evidence.values()));self.assertEqual(len(evidence),8)
 def test_timeout_reports_coarse_evidence_but_never_authorizes(self):
  c=self.controller();c.calibration_state='waiting';clock=[0.0];sent=[];c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0)
  def read(timeout):
   if 'REPORT' in sent:return 'CAL_DIAG_11011000'
   clock[0]+=.25;return 'ALIVE'
  c._read=read;c._send=sent.append
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
   with self.assertRaisesRegex(m.NativeFailure,'challenge timed out'):c._wait_calibrated()
  self.assertIn('REPORT',sent);self.assertNotIn('ARM',sent);self.assertTrue(c.calibration_evidence['keyboard_seen']);self.assertTrue(c.calibration_evidence['pointer_seen']);self.assertFalse(c.calibration_verified)
 def test_report_forbidden_after_calibration_or_arm_and_broken_report_is_safe(self):
  c=self.controller();sent=[];c._send=sent.append
  for state in ('not-started','challenge-seen','verified','failed'):
   c.calibration_state=state;c._request_calibration_report()
  self.assertEqual(sent,[]);self.assertEqual(c.status()['calibration_report_kind'],'request-skipped')
  c.calibration_state='waiting'
  def broken(token):raise BrokenPipeError('fixture')
  c._send=broken;c._request_calibration_report();self.assertIsNone(c.calibration_evidence);self.assertEqual(c.status()['calibration_report_kind'],'send-failed')
 def test_calibrating_marker_is_fixed_and_emitted_before_arm(self):
  c=self.controller();output=io.StringIO()
  with contextlib.redirect_stderr(output):c.start()
  self.assertEqual(output.getvalue(),'DESKTOP_CALIBRATION_READY\n');self.assertTrue(c.calibration_verified);c.close()

 def test_close_waits_briefly_for_close_ack_before_socket_shutdown(self):
  c=self.controller();events=[];c._send=lambda token:events.append(token)
  c.connection=SimpleNamespace(shutdown=lambda how:events.append('shutdown'),close=lambda:events.append('socket-close'))
  def wait(timeout):events.append(('wait',timeout));return 0
  c.process=SimpleNamespace(wait=wait);c.close();self.assertEqual(events[:3],['CLOSE',('wait',.1),'shutdown']);self.assertEqual(c.helper_exit_code,0)

 def test_report_failure_kinds_are_local_fixed_enums(self):
  for error,kind in ((m.NativeFailure('transport-closed','untrusted contents'),'transport-closed'),(m.NativeFailure('protocol-invalid','untrusted contents'),'malformed'),(OSError('untrusted contents'),'transport-closed'),(RuntimeError('untrusted contents'),'read-failed')):
   with self.subTest(kind=kind):
    c=self.controller();c.calibration_state='waiting';c._send=lambda token:None
    def read(timeout):raise error
    c._read=read;c._request_calibration_report();self.assertEqual(c.status()['calibration_report_kind'],kind);self.assertIsNone(c.calibration_evidence);self.assertNotIn('untrusted contents',str(c.status()))
  c=self.controller();c.calibration_state='waiting';c._send=lambda token:None;c._read=lambda timeout:None;c._request_calibration_report();self.assertEqual(c.status()['calibration_report_kind'],'missing')
 def test_report_alive_without_result_has_bounded_timeout_kind(self):
  c=self.controller();c.calibration_state='waiting';c._send=lambda token:None;clock=[0.0]
  def read(timeout):clock[0]+=.1;return 'ALIVE'
  c._read=read
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):c._request_calibration_report()
  self.assertEqual(c.status()['calibration_report_kind'],'timeout');self.assertIsNone(c.calibration_evidence);self.assertFalse(c.calibration_verified)

 def test_late_calibrated_before_report_diagnostics_never_authorizes(self):
  c=self.controller();c.calibration_state='waiting';messages=iter(('ALIVE','CALIBRATED','CAL_DIAG_11011000'));sent=[];c._send=sent.append;c._read=lambda timeout:next(messages);c._request_calibration_report();self.assertTrue(c.status()['calibration_late_result']);self.assertEqual(c.status()['calibration_report_kind'],'received');self.assertTrue(c.calibration_evidence['keyboard_seen']);self.assertTrue(c.calibration_evidence['pointer_seen']);self.assertFalse(c.calibration_verified);self.assertEqual(c.calibration_state,'waiting');self.assertEqual(sent,['REPORT'])

 def test_terminal_diagnostics_can_follow_delayed_fd_cleanup_and_clean_exit(self):
  c=self.controller();c.calibration_state='waiting';left,right=socket.socketpair();left.setblocking(False);c.connection=left;done=threading.Event();commands=[]
  class Process:
   def poll(self):return 0 if done.is_set() else None
   def wait(self,timeout):
    if not done.wait(timeout):raise subprocess.TimeoutExpired('fake-cleanup',timeout)
    return 0
  c.process=Process()
  def helper():
   try:
    stream=right.makefile('rb');commands.append(stream.readline().decode().strip());right.sendall(b'ALIVE\nCALIBRATED\n');time.sleep(.5);right.sendall(b'CAL_DIAG_11011000\n');stream.close()
   finally:right.close();done.set()
  worker=threading.Thread(target=helper,daemon=True);worker.start();started=time.monotonic();c._request_calibration_report();elapsed=time.monotonic()-started;self.assertGreaterEqual(elapsed,.45);self.assertLess(elapsed,2);self.assertEqual(c.status()['calibration_report_kind'],'received');self.assertTrue(c.calibration_evidence['keyboard_seen']);self.assertTrue(c.calibration_late_result);self.assertFalse(c.calibration_verified);self.assertEqual(commands,['REPORT']);c.close();worker.join(timeout=1);self.assertEqual(c.status()['helper_exit_code'],0)

 def test_one_or_two_calibration_resets_require_fresh_result(self):
  for resets in (1,2):
   with self.subTest(resets=resets):
    c=self.controller();c.calibration_state='waiting';c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0);messages=iter(['CALIBRATION_RESET']*resets+['CALIBRATED']);c._read=lambda timeout:next(messages);sent=[];c._send=sent.append;output=io.StringIO()
    with contextlib.redirect_stderr(output):c._wait_calibrated()
    self.assertEqual(c.calibration_resets,resets);self.assertEqual(output.getvalue(),'DESKTOP_CALIBRATION_READY_AGAIN\n'*resets);self.assertFalse(c.calibration_verified);self.assertNotIn('ARM',sent)
 def test_excess_calibration_reset_faults_without_arm(self):
  c=self.controller();c.calibration_state='waiting';c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0);c._read=lambda timeout:'CALIBRATION_RESET';c._send=lambda token:None
  with contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaisesRegex(m.NativeFailure,'reset invalid'):c._wait_calibrated()
  self.assertEqual(c.calibration_resets,2);self.assertFalse(c.calibration_verified)
 def test_resets_do_not_extend_original_challenge_deadline(self):
  c=self.controller();c.calibration_state='waiting';clock=[0.0];sent=[];c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0);reads=[0];c._send=sent.append
  def read(timeout):
   if 'REPORT' in sent:return 'CAL_DIAG_00000000'
   clock[0]+=.25;reads[0]+=1
   if reads[0] in (40,80):return 'CALIBRATION_RESET'
   return 'ALIVE'
  c._read=read
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaisesRegex(m.NativeFailure,'challenge timed out'):c._wait_calibrated()
  self.assertEqual(clock[0],30);self.assertEqual(c.calibration_resets,2);self.assertEqual(c.calibration_report_kind,'received');self.assertNotIn('ARM',sent);self.assertFalse(c.calibration_verified)
 def test_reset_token_invalid_outside_waiting_and_after_arm(self):
  c=self.controller();c.calibration_state='challenge-seen';c._read=lambda timeout:'CALIBRATION_RESET';c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0)
  with self.assertRaisesRegex(m.NativeFailure,'reset invalid'):c._wait_calibrated()
  with self.assertRaisesRegex(m.NativeFailure,'invalid response'):c._consume('CALIBRATION_RESET')

 def test_queued_reset_during_report_never_cues_or_authorizes(self):
  c=self.controller();c.calibration_state='waiting';messages=iter(('CALIBRATION_RESET','CAL_DIAG_11011000'));sent=[];c._send=sent.append;c._read=lambda timeout:next(messages);output=io.StringIO()
  with contextlib.redirect_stderr(output):c._request_calibration_report()
  self.assertEqual(output.getvalue(),'');self.assertEqual(c.calibration_resets,1);self.assertEqual(c.calibration_report_kind,'received');self.assertFalse(c.calibration_verified);self.assertTrue(c.calibration_evidence['keyboard_seen']);self.assertEqual(sent,['REPORT'])
  c=self.controller();c.calibration_state='waiting';c.calibration_resets=2;c._send=lambda token:None;c._read=lambda timeout:'CALIBRATION_RESET';c._request_calibration_report();self.assertEqual(c.calibration_resets,2);self.assertEqual(c.calibration_report_kind,'malformed');self.assertIsNone(c.calibration_evidence)

 def test_fixed_activity_category_tokens_cancel_before_callback(self):
  kinds={'ACTIVITY':'unspecified','ACTIVITY_KEY':'key','ACTIVITY_POINTER':'pointer','ACTIVITY_SWITCH':'switch','ACTIVITY_METADATA':'metadata','ACTIVITY_HELD':'held'}
  for token,kind in kinds.items():
   with self.subTest(token=token):
    c=self.controller();seen=[];c.on_activity=lambda:seen.append(c.status()['activity_kind']);self.assertTrue(c._consume(token));self.assertEqual(seen,[kind]);self.assertEqual(c.terminal_reason,'activity');self.assertTrue(c.closed);self.assertEqual(c.status()['activity_kind'],kind)
 def test_unknown_activity_suffix_faults_without_exporting_suffix(self):
  c=self.controller()
  for token in ('ACTIVITY_RAW_KEYCODE','ACTIVITY_KEY 30','ACTIVITY_POINTER_12','ACTIVITY_key'):
   with self.subTest(token=token):
    with self.assertRaises(m.NativeFailure):c._consume(token)
    self.assertIsNone(c.status()['activity_kind']);self.assertNotIn(token,str(c.status()))
 def test_categorized_final_activity_wins_over_helper_exit(self):
  c=self.controller();c.ready=True;c.last_peer=time.monotonic();c.buffer.extend(b'ACTIVITY_HELD\n');c.process=SimpleNamespace(poll=lambda:0,wait=lambda timeout:0);c._monitor();self.assertTrue(self.activity.is_set());self.assertFalse(self.fault.is_set());self.assertEqual(c.status()['activity_kind'],'held');self.assertEqual(c.status()['terminal_reason'],'activity');self.assertEqual(c.status()['helper_exit_code'],0)

 def test_notice_is_shown_only_after_calibrating_and_closed_before_arm(self):
  events=[]
  class Notice:
   def __init__(self):self.shown=False
   def show(self,reset=False):self.shown=True;events.append(('show',reset))
   def close(self):self.shown=False;events.append(('notice-close',))
   def status(self):return {'request_acknowledged':True,'request_active':self.shown,'visible_verified':False,'warning':None}
  c=self.controller(notice=Notice());send=c._send
  def traced(token):events.append((token,));send(token)
  c._send=traced;c.start();self.assertLess(events.index(('CALIBRATE',)),events.index(('show',False)));self.assertLess(events.index(('notice-close',)),events.index(('ARM',)));status=c.status()['calibration_notice'];self.assertTrue(status['requested']);self.assertTrue(status['request_acknowledged']);self.assertFalse(status['request_active']);self.assertFalse(status['visibility_verified']);c.close()
 def test_notice_reset_updates_and_failure_cleanup_are_bounded_by_lifecycle(self):
  events=[]
  class Notice:
   def show(self,reset=False):events.append(('show',reset))
   def close(self):events.append(('close',))
   def status(self):return {'warning':None}
  c=self.controller(notice=Notice());c.calibration_state='waiting';c.process=SimpleNamespace(poll=lambda:None,wait=lambda timeout:0);messages=iter(('CALIBRATION_RESET','FAULT'));c._read=lambda timeout:next(messages);c._send=lambda token:None
  with contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaises(m.NativeFailure):c._wait_calibrated()
  c.close();self.assertEqual(events,[('show',True),('close',)])
 def test_notification_failure_exports_only_fixed_warning_and_no_visibility_claim(self):
  class Notice:
   def show(self,reset=False):raise RuntimeError('private diagnostic text')
   def close(self):raise RuntimeError('private diagnostic text')
  c=self.controller(notice=Notice());c._show_notice();c.close();status=c.status()['calibration_notice'];self.assertTrue(status['requested']);self.assertFalse(status['visibility_verified']);self.assertIn('unconfirmed',status['warning']);self.assertNotIn('private diagnostic text',str(status))
 def test_default_fake_controller_has_no_notice_or_ui(self):
  c=self.controller();self.assertIsNone(c.notice);self.assertEqual(c.status()['calibration_notice'],{'requested':False,'request_acknowledged':False,'request_active':False,'delivery_unknown':False,'visibility_verified':False,'warning':None})

 def test_failed_notice_close_with_active_request_refuses_arm(self):
  class Notice:
   def __init__(self):self.calls=0
   def show(self,reset=False):return True
   def close(self):self.calls+=1;return False
   def status(self):return {'request_acknowledged':True,'request_active':True,'warning':'fixed test warning'}
  notice=Notice();c=self.controller(notice=notice)
  with self.assertRaisesRegex(m.NativeFailure,'notification closure unconfirmed'):c.start()
  self.assertNotIn('ARM',self.brokers[-1].commands);self.assertFalse(c.calibration_verified);self.assertFalse(c.ready);self.assertTrue(c.status()['calibration_notice']['request_active']);self.assertLessEqual(notice.calls,2);self.assertGreaterEqual(notice.calls,1)
 def test_unavailable_notice_without_active_id_does_not_bypass_challenge(self):
  class Notice:
   def show(self,reset=False):return False
   def close(self):return True
   def status(self):return {'request_acknowledged':False,'request_active':False,'warning':'unavailable'}
  c=self.controller(notice=Notice()).start();self.assertTrue(c.calibration_verified);self.assertIn('CALIBRATE',self.brokers[-1].commands);self.assertIn('ARM',self.brokers[-1].commands);self.assertFalse(c.status()['calibration_notice']['visibility_verified']);self.assertIsNotNone(c.status()['calibration_notice']['warning']);c.close()

 def test_notice_not_shown_after_revocation_or_stop_and_revocation_during_show_closes(self):
  calls=[];authorized=[True]
  class Notice:
   def show(self,reset=False):calls.append('show');authorized[0]=False
   def close(self):calls.append('close');return True
   def status(self):return {'request_active':False,'warning':None}
  c=self.controller(notice=Notice());c.active=lambda:False
  with self.assertRaisesRegex(m.NativeFailure,'authorization ended'):c._show_notice()
  self.assertEqual(calls,[])
  c=self.controller(notice=Notice());c.stop.set()
  with self.assertRaisesRegex(m.NativeFailure,'authorization ended'):c._show_notice()
  self.assertEqual(calls,[])
  c=self.controller(notice=Notice());c.active=lambda:authorized[0]
  with self.assertRaisesRegex(m.NativeFailure,'authorization ended'):c._show_notice()
  self.assertEqual(calls,['show','close']);self.assertFalse(c.notice_open)
 def test_failed_notice_close_retains_cleanup_ownership_until_confirmed(self):
  class Notice:
   def __init__(self):self.calls=0
   def close(self):self.calls+=1;return self.calls>1
   def status(self):return {'request_active':self.calls<2,'request_acknowledged':True,'warning':None}
  notice=Notice();c=self.controller(notice=notice);c.notice_open=True;c.notice_active=True;c._close_notice();self.assertTrue(c.notice_open);self.assertTrue(c.notice_active);c._close_notice();self.assertFalse(c.notice_open);self.assertFalse(c.notice_active);self.assertEqual(notice.calls,2)

 def test_unknown_notice_delivery_without_id_refuses_arm(self):
  class Notice:
   def __init__(self):self.calls=0
   def show(self,reset=False):return False
   def close(self):self.calls+=1;return False
   def status(self):return {'request_acknowledged':False,'request_active':False,'delivery_unknown':True,'warning':'fixed unknown delivery warning'}
  notice=Notice();c=self.controller(notice=notice)
  with self.assertRaisesRegex(m.NativeFailure,'notification closure unconfirmed'):c.start()
  self.assertNotIn('ARM',self.brokers[-1].commands);self.assertFalse(c.calibration_verified);self.assertFalse(c.ready);status=c.status()['calibration_notice'];self.assertTrue(status['delivery_unknown']);self.assertFalse(status['request_active']);self.assertFalse(status['visibility_verified']);self.assertIsNotNone(status['warning']);self.assertTrue(c.notice_open);self.assertLessEqual(notice.calls,2)

 def test_late_calibrated_after_original_deadline_refused_without_arm(self):
  c=self.controller();c.calibration_state='waiting';clock=[0.0];sent=[];reads=[0];c._send=sent.append
  def read(timeout):
   reads[0]+=1
   if reads[0]==1:clock[0]=30.01;return 'CALIBRATED'
   return 'CAL_DIAG_11011000'
  c._read=read
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
   with self.assertRaisesRegex(m.NativeFailure,'challenge timed out'):c._wait_calibrated()
  self.assertEqual(sent,['REPORT']);self.assertTrue(c.calibration_late_result);self.assertFalse(c.calibration_verified)
 def test_revocation_or_stop_during_calibrated_read_refuses_success(self):
  for stop in (False,True):
   c=self.controller();c.calibration_state='waiting';authorized=[True];c.active=lambda:authorized[0];sent=[];c._send=sent.append
   def read(timeout):
    if stop:c.stop.set()
    else:authorized[0]=False
    return 'CALIBRATED'
   c._read=read
   with self.assertRaisesRegex(m.NativeFailure,'authorization ended'):c._wait_calibrated()
   self.assertEqual(sent,[]);self.assertFalse(c.calibration_verified)
 def test_revocation_during_notice_closure_refuses_arm(self):
  authorized=[True]
  class Notice:
   def show(self,reset=False):return True
   def close(self):authorized[0]=False;return True
   def status(self):return {'request_active':False,'delivery_unknown':False,'warning':None}
  c=self.controller(notice=Notice());c.active=lambda:authorized[0]
  with self.assertRaisesRegex(m.NativeFailure,'authorization ended'):c.start()
  self.assertNotIn('ARM',self.brokers[-1].commands);self.assertFalse(c.calibration_verified)

if __name__=='__main__':unittest.main()
