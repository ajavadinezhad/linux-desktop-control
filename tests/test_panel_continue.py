import json,unittest
from test_control import m
from test_recovery import Partial

CONTEXT={'reason':'Human takeover','task_summary':'Review disposable note'}
class ContinueTests(unittest.TestCase):
    def make(self):
        s=m.Server(Partial);s.call('desktop_start',{});s.call('desktop_pause',CONTEXT)
        t=m.StdioTransport(s);return s,t
    def execute(self,s,t):
        request,token=t.pending.get_nowait()
        s.cancel_token=token;s.request_epoch=request['_control_epoch'];s.panel_resume=request.get('_panel_resume',False)
        try:return request,s.handle(request)
        finally:
            s.cancel_token=None;s.request_epoch=None;s.panel_resume=False
            if request.get('_resume_reserved'):t.resume_pending=False
    def test_explicit_continue_reopens_consent_but_cannot_enable_unobserved_input(self):
        s,t=self.make();t.panel_control('continue')
        request,response=self.execute(s,t)
        self.assertTrue(request['_panel_resume']);self.assertNotIn('id',request)
        self.assertFalse(response['result'].get('isError',False))
        self.assertFalse(any(c['type']=='image' for c in response['result']['content']))
        self.assertTrue(s.status()['ready_to_observe']);self.assertFalse(s.status()['input_allowed'])
        self.assertIsNone(s.recovery.observation_id)
        with self.assertRaises(RuntimeError):s.call('desktop_action',{'action':{'type':'click','x':1,'y':1}})
        content=s.call('desktop_observe',{})
        self.assertTrue(any(c['type']=='image' for c in content))
        token=json.loads(content[0]['text'])['recovery']['observation_id']
        self.assertFalse(s.status()['ready_to_observe'])
        s.call('desktop_action',{'action':{'type':'click','x':1,'y':1},'recovery_observation_id':token})
        self.assertFalse(s.recovery.inspection_required)
    def test_duplicate_or_disconnected_click_cannot_queue_resume(self):
        s,t=self.make();t.panel_control('continue');t.panel_control('continue')
        self.assertEqual(t.pending.qsize(),1)
        self.execute(s,t);t.panel_control('continue');self.assertTrue(t.pending.empty())
        s.call('desktop_pause',CONTEXT);t.disconnected.set();t.panel_control('continue')
        self.assertTrue(t.pending.empty())
    def test_continue_invalidated_by_new_pause_or_stop(self):
        for boundary in ('desktop_pause','desktop_stop'):
            s,t=self.make();t.panel_control('continue')
            s.begin_boundary(boundary,CONTEXT if boundary=='desktop_pause' else {})
            _,response=self.execute(s,t)
            self.assertTrue(response['result']['isError']);self.assertFalse(s.backend.active)
    def test_denied_continue_stays_paused_without_observation_gate_token(self):
        s,t=self.make()
        def deny():raise RuntimeError('Permission denied')
        s.backend.start=deny;t.panel_control('continue');_,response=self.execute(s,t)
        self.assertTrue(response['result']['isError']);self.assertEqual(s.state,'paused')
        self.assertFalse(s.status()['ready_to_observe']);self.assertFalse(s.backend.active)
    def test_unknown_event_cannot_stop_or_start(self):
        s,t=self.make();epoch=s.control_epoch;t.panel_control('unrecognized')
        self.assertTrue(t.pending.empty());self.assertEqual(s.control_epoch,epoch)

if __name__=='__main__':unittest.main()
