"""Recorder readiness and pipeline admission with files/fakes, never devices."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('guard_recorder_test',ROOT/'demo/record.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
g=r.guard

class RecordingGuardTests(unittest.TestCase):
 def fixture(self,root):
  args=r.parse_args(['--output',str(root/'video.webm'),'--stop-file',str(root/'stop'),
                     '--system-audio-device','example_sink.monitor'])
  args.output.write_bytes(b'encoded video and audio');args.output.chmod(0o600)
  value=dict(g.status_metadata(args,now=100),state='recording',recording=True,remaining_seconds=60)
  self.write(args,value)
  return args,value
 def write(self,args,value):
  args.status_file.write_text(json.dumps(value));args.status_file.chmod(0o600)
 def test_fresh_live_bound_recording_with_audio_passes(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root));result=g.check_ready(a.status_file,a.output,recording_id=v['recording_id'],require_audio=True,now=101)
   self.assertTrue(result['ready']);self.assertEqual(result['audio_mode'],'system-playback-monitor')
 def test_every_inactive_state_refuses(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root))
   for state in ('awaiting_consent','starting','failed','finished','other'):
    self.write(a,dict(v,state=state,recording=False))
    self.assertFalse(g.check_ready(a.status_file,a.output,now=101)['ready'])
 def test_stale_heartbeat_stalled_output_and_expiring_budget_refuse(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root))
   for changes,reason in (({'heartbeat_monotonic':90},'stale-status'),({'output_progress_monotonic':90},'output-stalled'),({'remaining_seconds':1},'insufficient-time'),({'heartbeat_monotonic':102},'stale-status')):
    self.write(a,dict(v,**changes));self.assertEqual(g.check_ready(a.status_file,a.output,now=101)['reason'],reason)
 def test_reused_process_or_prior_boot_refuses(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root))
   for changes in ({'process_start':'old'},{'boot_id':'old'}):
    self.write(a,dict(v,**changes));self.assertEqual(g.check_ready(a.status_file,a.output,now=101)['reason'],'recorder-not-live')
 def test_recording_and_output_identity_are_required(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root))
   self.assertEqual(g.check_ready(a.status_file,a.output,recording_id='b'*32,now=101)['reason'],'different-recording')
   other=Path(root)/'other';other.write_bytes(b'encoded');other.chmod(0o600)
   self.assertEqual(g.check_ready(a.status_file,other,now=101)['reason'],'different-output')
   self.write(a,dict(v,output_bytes=0));self.assertEqual(g.check_ready(a.status_file,a.output,now=101)['reason'],'output-not-started')
 def test_silent_mode_never_substitutes_for_requested_audio(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root));self.write(a,dict(v,audio_mode='silent'))
   self.assertFalse(g.check_ready(a.status_file,a.output,require_audio=True,now=101)['ready'])
   self.assertTrue(g.check_ready(a.status_file,a.output,require_audio=False,now=101)['ready'])
 def test_malformed_and_unsafe_files_never_report_ready(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root))
   for changes in ({'pid':True},{'guard_protocol':True},{'heartbeat_monotonic':float('nan')},{'remaining_seconds':'60'},{'output_inode':True},{'recording_id':'invalid'}):
    self.write(a,dict(v,**changes));self.assertFalse(g.check_ready(a.status_file,a.output,now=101)['ready'])
   a.status_file.write_text('{bad');self.assertFalse(g.check_ready(a.status_file,a.output,now=101)['ready'])
   self.write(a,v);a.status_file.chmod(0o644);self.assertEqual(g.check_ready(a.status_file,a.output,now=101)['reason'],'untrusted-file')
   self.write(a,v);link=Path(root)/'link';link.symlink_to(a.output)
   self.assertFalse(g.check_ready(a.status_file,link,now=101)['ready'])
   a.output.chmod(0o644);self.assertFalse(g.check_ready(a.status_file,a.output,now=101)['ready'])
 def test_heartbeat_does_not_fake_output_progress(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root));first=g.status_metadata(a,now=101)
   self.assertEqual(first['output_progress_monotonic'],100)
   with a.output.open('ab') as stream:stream.write(b'more')
   second=g.status_metadata(a,now=102)
   self.assertEqual(second['output_progress_monotonic'],102)
 def test_audio_device_is_explicit_monitor_and_silent_default_remains(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);base=['--output',str(root/'out'),'--stop-file',str(root/'stop')]
   self.assertIsNone(r.parse_args(base).system_audio_device)
   for source in ('default','alsa_input.microphone','monitor;bad',''):
    with patch('sys.stderr'):
     with self.assertRaises(SystemExit):r.parse_args(base+['--system-audio-device',source])
 def test_pipeline_requires_playing_error_free_and_output_before_ready(self):
  with tempfile.TemporaryDirectory() as root:
   a,v=self.fixture(Path(root));done=threading.Event()
   class Bus:
    error=False
    def pop_filtered(self,_):return object() if self.error else None
   class Pipeline:
    bus=Bus();result=r.Gst.StateChangeReturn.SUCCESS;state=r.Gst.State.PLAYING
    def set_state(self,_):return self.result
    def get_state(self,_):return self.result,self.state,None
    def get_bus(self):return self.bus
   p=Pipeline();r.confirm_pipeline_started(p,a,done)
   p.result=r.Gst.StateChangeReturn.FAILURE
   with self.assertRaises(RuntimeError):r.confirm_pipeline_started(p,a,done)
   p.result=r.Gst.StateChangeReturn.SUCCESS;p.state=r.Gst.State.PAUSED
   with self.assertRaises(RuntimeError):r.confirm_pipeline_started(p,a,done)
   p.state=r.Gst.State.PLAYING;p.bus.error=True
   with self.assertRaises(RuntimeError):r.confirm_pipeline_started(p,a,done)
   p.bus.error=False;a.output.write_bytes(b'')
   with self.assertRaises(RuntimeError):r.confirm_pipeline_started(p,a,done,timeout=0)
   a.output.write_bytes(b'data');done.set()
   with self.assertRaises(RuntimeError):r.confirm_pipeline_started(p,a,done)

if __name__=='__main__':unittest.main()
