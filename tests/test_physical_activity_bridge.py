"""Authenticated device-source cancellation independent of a window guard."""
import importlib.util,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('physical_activity_bridge',ROOT/'plugins/linux-desktop-control/indicator_bridge.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Parameters:
 def __init__(self,nonce,epoch=4):self.values=(nonce,epoch)
 def unpack(self):return self.values
class PhysicalActivityBridgeTests(unittest.TestCase):
 def make(self):
  bridge=m.IndicatorBridge(lambda:{'active':True});bridge.owner=':1.44';bridge.bound=True
  bridge.call=lambda *args:(True,)
  self.addCleanup(bridge.close);return bridge
 def signal(self,b,sender=None,nonce=None):
  b.context_changed(None,sender or b.owner,m.PATH,m.IFACE,'ContextChanged',Parameters(nonce or b.nonce))
 def wait_idle(self,b):
  deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   with b._physical_lock:
    if not b._physical_worker:return
   time.sleep(.005)
  self.fail('physical context worker did not finish')
 def test_default_and_spoofed_signals_never_query_context(self):
  b=self.make();reads=[];b.context=lambda:reads.append(1)
  self.signal(b);self.assertEqual(reads,[])
  b.set_physical_guard(True,lambda:self.fail('spoofed activity accepted'))
  self.signal(b,sender=':1.evil');self.signal(b,nonce='wrong');self.wait_idle(b);self.assertEqual(reads,[])
 def test_capture_without_window_guard_still_cancels_off_signal_thread(self):
  b=self.make();cancelled=threading.Event();threads=[];signal_thread=threading.get_ident();b.armed=None
  def context():threads.append(threading.get_ident());return {'available':False,'reason':'device-source-activity'}
  b.context=context;b.set_physical_guard(True,cancelled.set)
  # Represents the capture/intentional-transition interval, where armed is None.
  self.signal(b);self.assertTrue(cancelled.wait(2));self.wait_idle(b);self.assertNotEqual(threads,[signal_thread])
  self.signal(b);self.assertEqual(len(threads),1)
 def test_allowed_focus_and_protected_context_never_masquerade_as_activity(self):
  b=self.make();calls=[];b.set_physical_guard(True,lambda:calls.append('activity'))
  for context in ({'available':True,'kind':'window'},{'available':False,'reason':'no-foreground-window'},{'available':False,'reason':'system-ui'}):
   b.context=lambda context=context:context;self.signal(b);self.wait_idle(b)
  self.assertEqual(calls,[])
 def test_coalesced_signal_during_query_is_not_lost(self):
  b=self.make();entered=threading.Event();resume=threading.Event();cancelled=threading.Event();reads=[]
  def context():
   reads.append(1)
   if len(reads)==1:
    entered.set();resume.wait(2);return {'available':True}
   return {'available':False,'reason':'device-source-activity'}
  b.context=context;b.set_physical_guard(True,cancelled.set);self.signal(b);self.assertTrue(entered.wait(2));self.signal(b);resume.set();self.assertTrue(cancelled.wait(2));self.wait_idle(b);self.assertEqual(len(reads),2)
 def test_close_or_opt_out_suppresses_inflight_activity_reply(self):
  for close in (False,True):
   b=self.make();entered=threading.Event();resume=threading.Event();calls=[]
   def context():entered.set();resume.wait(2);return {'reason':'device-source-activity'}
   b.context=context;b.set_physical_guard(True,lambda:calls.append(1));self.signal(b);self.assertTrue(entered.wait(2))
   if close:b.close()
   else:b.set_physical_guard(False)
   resume.set();self.wait_idle(b);self.assertEqual(calls,[])
 def test_context_transport_failure_closes_observer_and_notifies(self):
  b=self.make();failed=threading.Event();b.on_failure=failed.set
  def context():raise RuntimeError('disconnected')
  b.context=context;b.set_physical_guard(True,lambda:self.fail('transport error is not activity'));self.signal(b);self.assertTrue(failed.wait(2));self.assertTrue(b.closed.is_set());self.wait_idle(b)
