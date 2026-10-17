import io,json,threading,time,unittest
from test_control import m,Fake
from test_transport import Harness

CONTEXT={'reason':'Human review is needed','task_summary':'Finish the scratch note'}
class Counting(Fake):
    def __init__(self):
        super().__init__();self.starts=0;self.captures=0;self.inputs=0;self.closes=0
        self.pointer_position=(900,900);self.capture_info={'old':True}
        self.deny=False;self.capture_fail=False;self.warning=None
    def start(self):
        self.starts+=1
        if self.deny:raise RuntimeError('GNOME consent denied')
        self.stopped.clear();super().start()
    def capture(self):
        self.captures+=1
        if self.capture_fail:raise RuntimeError('capture failed')
        return super().capture()
    def action(self,a):self.inputs+=1
    def close(self):self.closes+=1;super().close()
    def status(self):return dict(super().status(),portal_closed_confirmed=not self.active,cleanup_warning=self.warning)

class HandoffTests(unittest.TestCase):
    def make(self):
        s=m.Server(Counting);s.call('desktop_start',{});return s,s.backend
    def pause(self,s):
        result=s.call('desktop_pause',dict(CONTEXT))
        self.assertTrue(all(c['type']=='text' for c in result))
        return json.loads(result[0]['text'])
    def test_pause_closes_and_blocks_all_input_capture_and_start(self):
        s,b=self.make();status=self.pause(s)
        self.assertEqual(status['control_state'],'paused');self.assertFalse(status['active'])
        self.assertFalse(status['capture_allowed']);self.assertFalse(status['input_allowed'])
        self.assertIsNone(b.pointer_position);self.assertEqual(b.capture_info,{})
        before=(b.starts,b.captures,b.inputs)
        for name,args in [('desktop_action',{'action':{'type':'move','x':1,'y':1}}),('desktop_observe',{}),('desktop_start',{})]:
            with self.assertRaises(RuntimeError):s.call(name,args)
        self.assertEqual((b.starts,b.captures,b.inputs),before)
    def test_resume_is_explicit_and_fresh(self):
        s,b=self.make();h=self.pause(s)['handoff'];count=b.captures
        for args in ({'handoff_id':h['id'],'human_ready':False},{'handoff_id':'stale','human_ready':True}):
            with self.assertRaises(ValueError):s.call('desktop_resume',args)
        self.assertEqual(s.state,'paused');self.assertEqual(b.captures,count)
        result=s.call('desktop_resume',{'handoff_id':h['id'],'human_ready':True})
        self.assertEqual(b.starts,2);self.assertEqual(b.captures,count+1)
        self.assertTrue(any(c['type']=='image' for c in result));self.assertEqual(s.state,'active')
        self.assertEqual(s.handoff['task_summary'],CONTEXT['task_summary'])
    def test_denied_consent_preserves_paused_context(self):
        s,b=self.make();h=self.pause(s)['handoff'];b.deny=True
        with self.assertRaises(RuntimeError):s.call('desktop_resume',{'handoff_id':h['id'],'human_ready':True})
        self.assertEqual(s.state,'paused');self.assertEqual(s.handoff,h);self.assertFalse(b.active)
    def test_resume_capture_failure_does_not_allow_input(self):
        s,b=self.make();h=self.pause(s)['handoff'];b.capture_fail=True
        with self.assertRaises(RuntimeError):s.call('desktop_resume',{'handoff_id':h['id'],'human_ready':True})
        self.assertEqual(s.state,'paused');self.assertFalse(b.active)
        with self.assertRaises(RuntimeError):s.call('desktop_action',{'action':{}})
        self.assertEqual(b.inputs,0)
    def test_stop_while_paused_clears_context_and_old_resume(self):
        s,b=self.make();h=self.pause(s)['handoff'];s.call('desktop_stop',{})
        self.assertEqual(s.state,'stopped');self.assertIsNone(s.handoff)
        with self.assertRaises(RuntimeError):s.call('desktop_resume',{'handoff_id':h['id'],'human_ready':True})
    def test_background_wait_reference_retained_without_job_management(self):
        s,b=self.make()
        s.call('desktop_pause',dict(CONTEXT,handoff_kind='background_wait',job_reference='scratch-archive.zip'))
        self.assertEqual(s.handoff['kind'],'background_wait');self.assertEqual(s.handoff['job_reference'],'scratch-archive.zip')
        self.assertEqual(s.state,'paused')
    def test_unconfirmed_close_is_not_a_safe_pause(self):
        s,b=self.make();b.warning='portal close failed'
        with self.assertRaises(RuntimeError):s.call('desktop_pause',CONTEXT)
        self.assertEqual(s.state,'pausing')
        with self.assertRaises(RuntimeError):s.call('desktop_resume',{'handoff_id':s.handoff['id'],'human_ready':True})
    def test_completed_old_capture_cannot_cross_output_fence(self):
        s,b=self.make();epoch=s.control_epoch
        content=s.call('desktop_observe',{})
        s.begin_boundary('desktop_pause',CONTEXT)
        response={'id':1,'result':{'content':content}}
        with s.state_lock:response=s.fence_response({'id':1,'_control_epoch':epoch},response)
        self.assertTrue(response['result']['isError'])
        self.assertFalse(any(c['type']=='image' for c in response['result']['content']))
    def test_status_during_pause_does_not_capture(self):
        s,b=self.make();self.pause(s);count=b.captures
        for _ in range(3):s.call('desktop_status',{})
        self.assertEqual(b.captures,count);self.assertEqual(s.state,'paused')

class HandoffTransportTests(unittest.TestCase):
    def test_pause_interrupts_active_typing_and_rejects_queued_work(self):
        h=Harness()
        try:
            h.begin('text')
            h.send({'id':44,'method':'tools/call','params':{'name':'desktop_observe'}})
            h.send({'id':45,'method':'tools/call','params':{'name':'desktop_pause','arguments':CONTEXT}})
            h.send({'id':46,'method':'tools/call','params':{'name':'desktop_start'}})
            self.assertTrue(h.backend.finished.wait(1))
            end=time.monotonic()+1
            while h.server.state!='paused' and time.monotonic()<end:time.sleep(.005)
            self.assertEqual(h.server.state,'paused');self.assertTrue(h.backend.was_released)
        finally:h.finish()
        replies={r['id']:r for r in map(json.loads,h.output.getvalue().splitlines())}
        for i in (42,44,46):self.assertTrue(replies[i]['result']['isError'])
        self.assertFalse(replies[45]['result'].get('isError',False))
        self.assertFalse(any(c['type']=='image' for r in replies.values() for c in r.get('result',{}).get('content',[])))
    def test_pause_interrupts_drag_and_disconnect_clears_context(self):
        h=Harness()
        h.begin('drag');h.send({'id':45,'method':'tools/call','params':{'name':'desktop_pause','arguments':CONTEXT}})
        self.assertTrue(h.backend.finished.wait(1))
        end=time.monotonic()+1
        while h.server.state!='paused' and time.monotonic()<end:time.sleep(.005)
        self.assertIsNotNone(h.server.handoff)
        h.finish();self.assertEqual(h.server.state,'stopped');self.assertIsNone(h.server.handoff)
        self.assertTrue(h.backend.was_shutdown)
    def test_admission_rejects_resume_before_pause_ack(self):
        s=m.Server(Counting);s.begin_boundary('desktop_pause',CONTEXT)
        self.assertIsNotNone(s.admission_error('desktop_resume'))
        self.assertIsNotNone(s.admission_error('desktop_action'))
    def test_stop_invalidates_an_earlier_pause_generation(self):
        s=m.Server(Counting);old=s.begin_boundary('desktop_pause',CONTEXT)
        s.begin_boundary('desktop_stop',{})
        s.request_epoch=old;s.boundary_prepared=True
        with self.assertRaises(RuntimeError):s.call('desktop_pause',CONTEXT)
        self.assertIsNone(s.handoff);self.assertEqual(s.state,'stopping')

if __name__=='__main__':unittest.main()

class CaptureRaceTests(unittest.TestCase):
    def test_pause_during_capture_suppresses_image_and_queued_input(self):
        h=Harness();entered=threading.Event();release=threading.Event()
        def capture():
            entered.set();release.wait(2);return Fake().capture()
        h.backend.capture=capture
        try:
            h.send({'id':1,'method':'tools/call','params':{'name':'desktop_observe'}})
            self.assertTrue(entered.wait(1))
            h.send({'id':2,'method':'tools/call','params':{'name':'desktop_pause','arguments':CONTEXT}})
            end=time.monotonic()+1
            while h.server.state!='pausing' and time.monotonic()<end:time.sleep(.005)
            self.assertEqual(h.server.state,'pausing')
            h.send({'id':3,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{}}}})
            release.set()
            end=time.monotonic()+1
            while h.server.state!='paused' and time.monotonic()<end:time.sleep(.005)
            self.assertEqual(h.server.state,'paused')
        finally:release.set();h.finish()
        replies={r['id']:r for r in map(json.loads,h.output.getvalue().splitlines())}
        self.assertTrue(replies[1]['result']['isError']);self.assertTrue(replies[3]['result']['isError'])
        self.assertFalse(any(c['type']=='image' for r in replies.values() for c in r.get('result',{}).get('content',[])))
    def test_invalid_pause_reports_original_request_id_without_interrupt(self):
        h=Harness()
        try:
            h.send({'id':123,'method':'tools/call','params':{'name':'desktop_pause','arguments':{'reason':''}}})
            end=time.monotonic()+1
            while '"id": 123' not in h.output.getvalue() and time.monotonic()<end:time.sleep(.005)
            self.assertFalse(h.backend.stopped.is_set());self.assertEqual(h.server.state,'active')
        finally:h.finish()
        response=json.loads(h.output.getvalue().splitlines()[0])
        self.assertEqual(response['id'],123);self.assertTrue(response['result']['isError'])

class PublicationAndClosureTests(unittest.TestCase):
    make=HandoffTests.make
    def test_cancel_after_capture_blocks_publication(self):
        s,b=self.make();content=s.call('desktop_observe',{})
        s.cancel_token=threading.Event();s.cancel_token.set()
        result=s.fence_response({'id':9},{'id':9,'result':{'content':content}})
        self.assertTrue(result['result']['isError'])
    def test_backend_stop_after_capture_blocks_publication(self):
        s,b=self.make();content=s.call('desktop_observe',{});b.stopped.set()
        result=s.fence_response({'id':9},{'id':9,'result':{'content':content}})
        self.assertTrue(result['result']['isError'])
    def test_failed_close_stop_start_cannot_reopen(self):
        s,b=self.make();b.warning='closure unknown'
        with self.assertRaises(RuntimeError):s.call('desktop_pause',CONTEXT)
        s.call('desktop_stop',{});before=b.starts
        with self.assertRaises(RuntimeError):s.call('desktop_start',{})
        self.assertEqual(b.starts,before)

class DuplicateResumeTests(unittest.TestCase):
    def test_queued_duplicate_resume_cannot_reprompt_after_denial(self):
        h=Harness();h.server.state='paused';h.backend.active=False
        h.server.handoff={'id':'handoff','reason':'Review','task_summary':'Scratch','kind':'human_action','job_reference':''}
        entered=threading.Event();release=threading.Event();starts=[]
        def denied():
            starts.append(True);entered.set();release.wait(1);raise RuntimeError('consent denied')
        h.backend.start=denied
        try:
            for i in (1,2):h.send({'id':i,'method':'tools/call','params':{'name':'desktop_resume','arguments':{'handoff_id':'handoff','human_ready':True}}})
            self.assertTrue(entered.wait(1))
            end=time.monotonic()+1
            while 2 not in h.transport.tokens and time.monotonic()<end:time.sleep(.005)
            self.assertIn(2,h.transport.tokens)
            release.set()
            end=time.monotonic()+1
            while len(h.output.getvalue().splitlines())<2 and time.monotonic()<end:time.sleep(.005)
            self.assertEqual(len(starts),1)
        finally:release.set();h.finish()
        replies={r['id']:r for r in map(json.loads,h.output.getvalue().splitlines())}
        self.assertTrue(replies[1]['result']['isError']);self.assertTrue(replies[2]['result']['isError'])
