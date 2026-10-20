import json,threading,unittest
import test_control as fixtures

class PauseReaderProgressTests(unittest.TestCase):
 def test_pause_followed_by_close_cancel_or_eof_never_waits_for_publication_lock(self):
  for tail in ('close','cancel','eof'):
   with self.subTest(tail=tail):
    s=fixtures.m.Server(fixtures.Fake);s.call('desktop_start',{'interruption_policy':'retain-sharing'})
    t=fixtures.m.StdioTransport(s);active=threading.Event();t.tokens[99]=active;s.cancel_token=active
    seen=[]
    def stream():
     seen.append('pause');yield json.dumps({'id':1,'method':'tools/call','params':{'name':'desktop_pause'}})+'\n'
     if tail=='close':
      seen.append('close');yield json.dumps({'id':2,'method':'tools/call','params':{'name':'desktop_close'}})+'\n'
     elif tail=='cancel':
      seen.append('cancel');yield json.dumps({'method':'notifications/cancelled','params':{'requestId':99}})+'\n'
     seen.append('eof')
    s.state_lock.acquire()
    reader=threading.Thread(target=t.read,args=(stream(),),daemon=True)
    try:
     reader.start();reader.join(.3)
     self.assertFalse(reader.is_alive(),'reader waited behind blocked publication')
     self.assertEqual(seen[-1],'eof');self.assertTrue(s.backend.operation_cancelled.is_set());self.assertTrue(s.backend.cancelled.is_set());self.assertTrue(active.is_set())
    finally:s.state_lock.release();reader.join(1);s.shutdown()
 def test_stale_manual_latch_cannot_pause_replacement_consent(self):
  s=fixtures.m.Server(fixtures.Fake);s.call('desktop_start',{'interruption_policy':'retain-sharing'})
  try:
   old=(s.backend,s.consent_id);s.call('desktop_close',{});s.call('desktop_start',{'interruption_policy':'retain-sharing'})
   s.manual_pause_latch=old
   self.assertFalse(s.manual_pause_pending());self.assertFalse(s.backend.operation_cancelled.is_set())
  finally:s.shutdown()
 def test_actual_blocked_stdout_pause_then_terminal_reader_progress(self):
  import io,os
  for tail in ('close','cancel','eof'):
   with self.subTest(tail=tail):
    s=fixtures.m.Server(fixtures.Fake);s.call('desktop_start',{'interruption_policy':'retain-sharing'});t=fixtures.m.StdioTransport(s)
    entered,release=threading.Event(),threading.Event()
    class Output(io.StringIO):
     def write(self,value):entered.set();release.wait(2);return super().write(value)
    r,w=os.pipe();reader,writer=os.fdopen(r,'r'),os.fdopen(w,'w');worker=threading.Thread(target=t.run,args=(reader,Output()),daemon=True);worker.start()
    def send(value):writer.write(json.dumps(value)+'\n');writer.flush()
    try:
     send({'id':1,'method':'tools/call','params':{'name':'desktop_status'}});self.assertTrue(entered.wait(1))
     send({'id':2,'method':'tools/call','params':{'name':'desktop_pause'}})
     if tail=='close':send({'id':3,'method':'tools/call','params':{'name':'desktop_close'}})
     elif tail=='cancel':send({'method':'notifications/cancelled','params':{'requestId':1}})
     writer.close()
     self.assertTrue(t.disconnected.wait(.3),'EOF stalled behind blocked stdout')
     self.assertTrue(s.backend.operation_cancelled.is_set());self.assertTrue(s.backend.cancelled.is_set())
    finally:
     if not writer.closed:writer.close()
     release.set();worker.join(2);reader.close()
    self.assertFalse(worker.is_alive())
 def test_owner_changed_while_capturing_operation_does_not_cancel_replacement(self):
  class ReplacingBackend(fixtures.Fake):
   hook=None
   def __getattribute__(self,name):
    if name=='operation_cancelled':
     hook=object.__getattribute__(self,'hook')
     if hook is not None:
      object.__setattr__(self,'hook',None);hook()
    return super().__getattribute__(name)
  s=fixtures.m.Server(ReplacingBackend);s.call('desktop_start',{'interruption_policy':'retain-sharing'});t=fixtures.m.StdioTransport(s)
  try:
   old=s.consent_id;replacement=threading.Event()
   def replace():s.consent_id='replacement-consent';s.backend.operation_cancelled=replacement
   s.backend.hook=replace
   t.read([json.dumps({'id':1,'method':'tools/call','params':{'name':'desktop_pause'}})+'\n'])
   request,_=t.pending.get_nowait()
   self.assertEqual(request['_pause_owner'][1],old);self.assertEqual(s.consent_id,'replacement-consent')
   self.assertFalse(replacement.is_set());self.assertFalse(s.manual_pause_pending());self.assertIn('_admission_error',request)
  finally:s.shutdown()
