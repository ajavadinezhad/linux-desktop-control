import json,unittest
from test_control import m
from test_recovery import Partial
class TaskBridgeTests(unittest.TestCase):
    def make(self):
        s=m.Server(Partial);s.call('desktop_start',{'task_summary':'Finish disposable note'});t=m.StdioTransport(s);return s,t
    def act(self,s,**extra):return s.call('desktop_action',dict(action={'type':'click','x':1,'y':1},**extra))
    def test_checkpoint_survives_pause_continue_observe_and_next_unique_result(self):
        s,t=self.make();self.act(s,task_checkpoint={'completed_summary':'First paragraph confirmed','next_step':'Inspect final paragraph then save'})
        first=s.status()['task']['last_result_id'];s.call('desktop_pause',{'reason':'Review','task_summary':s.task_summary})
        self.assertEqual(s.status()['next_required_action'],'wait');self.assertIn('task_checkpoint',s.handoff)
        t.panel_control('continue');event=s.status()['resume_event'];self.assertEqual(event['epoch'],s.control_epoch)
        t.panel_control('continue');self.assertEqual(s.status()['resume_event'],event)
        request,token=t.pending.get_nowait();s.panel_resume=True
        result=s.handle(request);s.panel_resume=False
        self.assertFalse(result['result'].get('isError',False));self.assertEqual(s.status()['next_required_action'],'observe')
        content=s.call('desktop_observe',{});metadata=json.loads(content[0]['text'])
        self.assertEqual(metadata['next_required_action'],'plan_ack')
        self.assertEqual(metadata['task']['completed_summary'],'First paragraph confirmed')
        self.assertEqual(s.backend.actions,1)
        self.act(s,recovery_observation_id=s.recovery.observation_id,task_checkpoint={'completed_summary':'Final paragraph inspected','next_step':'Save and verify'})
        self.assertEqual(s.backend.actions,2);self.assertNotEqual(s.status()['task']['last_result_id'],first)
        self.assertEqual(s.status()['next_required_action'],'waiting_executor');self.assertFalse(s.status()['operation_active'])
    def test_operation_active_only_during_input_and_clears_on_failure(self):
        s,t=self.make();original=s.backend.action
        def action(a):
            self.assertTrue(s.status()['operation_active']);self.assertEqual(s.status()['next_required_action'],'working')
            original(a);raise RuntimeError('injected partial effect')
        s.backend.action=action
        with self.assertRaises(RuntimeError):self.act(s)
        self.assertFalse(s.status()['operation_active']);self.assertEqual(s.status()['next_required_action'],'observe')
    def test_checkpoint_validation_happens_before_input_and_rejects_payload(self):
        s,t=self.make()
        for checkpoint in ({'completed_summary':'x'*1001,'next_step':'next'}, {'completed_summary':'done','next_step':' '}, {'completed_summary':'done','next_step':'next','action':{'text':'payload'}}):
            with self.assertRaises(ValueError):self.act(s,task_checkpoint=checkpoint)
        self.assertEqual(s.backend.actions,0)
        self.assertNotIn('action',s.status()['task'])
    def test_stop_clears_task_and_resume_event(self):
        s,t=self.make();s.call('desktop_pause',{'reason':'Review','task_summary':s.task_summary});t.panel_control('continue')
        self.assertIsNotNone(s.status()['resume_event']);s.call('desktop_stop',{})
        self.assertIsNone(s.status()['task']);self.assertIsNone(s.status()['resume_event']);self.assertEqual(s.status()['next_required_action'],'end')
    def test_confirmed_stop_releases_toolbar_for_a_new_session(self):
        s,t=self.make()
        class Panel:
            closed=False
            def close(self):self.closed=True
        panel=Panel();s.panel=panel;s.toolbar_session_ready=True
        s.call('desktop_stop',{})
        self.assertTrue(panel.closed);self.assertIsNone(s.panel)
        self.assertFalse(s.toolbar_session_ready)
    def test_schema_retains_seven_tools_optional_checkpoint(self):
        tools=m.tools();self.assertEqual(len(tools),7)
        action=next(t for t in tools if t['name']=='desktop_action')['inputSchema']
        self.assertIn('task_checkpoint',action['properties']);self.assertEqual(action['required'],['action'])

if __name__=='__main__':unittest.main()
