import unittest
import test_control
m=test_control.m

class Pipeline:
 def __init__(self):self.states=[]
 def set_state(self,state):self.states.append(state)

class CaptureRecoveryTests(unittest.TestCase):
 backend=test_control.Tests.backend
 def setup_backend(self):
  d=self.backend();d.pipeline=Pipeline();d.capture_info={};d.restarts=0;d.waits=[]
  d.wait_interruptibly=lambda seconds:d.waits.append(seconds)
  def start():d.check();d.restarts+=1;d.pipeline=Pipeline()
  d._start_capture_pipeline=start
  return d
 def test_timeout_reconnects_capture_once_without_new_consent_or_input(self):
  d=self.setup_backend();old=d.pipeline;calls=[]
  def capture(new_stream=False):
   calls.append(new_stream)
   if not new_stream:raise m.CaptureTimeout('stalled')
   d.capture_info={'freshness':'new_stream'};return b'new PNG'
  d._capture_once=capture
  self.assertEqual(d.capture(),b'new PNG')
  self.assertEqual(calls,[False,True]);self.assertEqual(d.restarts,1)
  self.assertEqual(d.waits,[.35]);self.assertEqual(old.states,[m.Gst.State.NULL])
  self.assertEqual(d.session,'/test');self.assertEqual(d.events,[])
  self.assertTrue(d.capture_info['pipeline_reconnected'])
 def test_second_timeout_is_not_retried(self):
  d=self.setup_backend();calls=[]
  def capture(new_stream=False):calls.append(new_stream);raise m.CaptureTimeout('still stalled')
  d._capture_once=capture
  with self.assertRaises(m.CaptureTimeout):d.capture()
  self.assertEqual(calls,[False,True]);self.assertEqual(d.restarts,1)
 def test_revoked_session_never_reconnects(self):
  d=self.setup_backend()
  def capture(new_stream=False):d.cancelled.set();raise m.CaptureTimeout('stalled')
  d._capture_once=capture
  with self.assertRaisesRegex(RuntimeError,'closed'):d.capture()
  self.assertEqual(d.restarts,0)
 def test_cancel_during_settling_never_reconnects(self):
  d=self.setup_backend()
  def capture(new_stream=False):raise m.CaptureTimeout('stalled')
  d._capture_once=capture
  def interrupted_wait(seconds):d.cancelled.set();d.check()
  d.wait_interruptibly=interrupted_wait
  with self.assertRaisesRegex(RuntimeError,'closed'):d.capture()
  self.assertEqual(d.restarts,0)
 def test_other_capture_errors_are_not_retried(self):
  d=self.setup_backend()
  def capture(new_stream=False):raise RuntimeError('pipeline permission denied')
  d._capture_once=capture
  with self.assertRaisesRegex(RuntimeError,'permission denied'):d.capture()
  self.assertEqual(d.restarts,0)

 def test_new_connection_frame_must_still_be_recent(self):
  d=self.setup_backend();d.frames=0
  class Buffer:
   def __init__(self,pts):self.pts=pts
   def get_size(self):return 3
   def extract_dup(self,*args):return b'PNG'
  class Sample:
   def __init__(self,pts):self.buf=Buffer(pts)
   def get_buffer(self):return self.buf
  samples=[Sample(0),Sample(800*m.Gst.MSECOND)]
  class Clock:
   def get_time(self):return 1000*m.Gst.MSECOND
  class LivePipeline:
   def get_clock(self):return Clock()
   def get_base_time(self):return 0
  class Sink:
   def emit(self,*args):return samples.pop(0)
  d.pipeline=LivePipeline();d.sink=Sink()
  self.assertEqual(d._capture_once(new_stream=True),b'PNG')
  self.assertEqual(samples,[]);self.assertEqual(d.capture_info['frame_age_ms'],200)
  self.assertEqual(d.capture_info['freshness'],'new_stream')

if __name__=='__main__':unittest.main()

class CaptureRevocationTests(unittest.TestCase):
 setup_backend=CaptureRecoveryTests.setup_backend
 backend=test_control.Tests.backend
 def test_revocation_during_pipeline_reconnect_never_publishes_a_frame(self):
  d=self.setup_backend();original=d._capture_once;calls=[]
  def capture(new_stream=False):
   calls.append(new_stream)
   if not new_stream:raise m.CaptureTimeout('stalled')
   return original(new_stream=True)
  d._capture_once=capture
  def restart():d.restarts+=1;d.cancelled.set();d.session=None
  d._start_capture_pipeline=restart
  with self.assertRaises(RuntimeError):d.capture()
  self.assertEqual(calls,[False,True]);self.assertEqual(d.restarts,1)
