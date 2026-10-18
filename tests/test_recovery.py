import json,unittest
from test_control import m,Fake

class Partial(Fake):
    def __init__(self):
        super().__init__();self.actions=0;self.fail_input=False;self.fail_capture=False
    def action(self,a):
        self.actions+=1
        self.transaction_info={'completed_steps':1,'failed_step':2,'input_events_attempted':4}
        if self.fail_input:raise RuntimeError('interrupted')
        self.transaction_info['failed_step']=None
    def capture(self):
        if self.fail_capture:raise RuntimeError('fresh frame unavailable')
        return super().capture()

class RecoveryTests(unittest.TestCase):
    def make(self):
        s=m.Server(Partial);s.call('desktop_start',{});return s,s.backend
    def act(self,s,**extra):return s.call('desktop_action',dict(action={'type':'click','x':1,'y':1},**extra))
    def test_partial_action_requires_inspection_and_explicit_fresh_token(self):
        s,b=self.make();b.fail_input=True
        with self.assertRaises(RuntimeError):self.act(s)
        result=s.recovery.snapshot()['last_result']
        self.assertEqual(result['outcome'],'effects_uncertain');self.assertEqual(result['completed_steps'],1)
        self.assertEqual(result['input_events_attempted'],4);self.assertTrue(s.status()['fresh_observation_required'])
        with self.assertRaises(RuntimeError):self.act(s)
        self.assertEqual(b.actions,1)
        s.call('desktop_status',{})
        with self.assertRaises(RuntimeError):self.act(s)
        observation=json.loads(s.call('desktop_observe',{})[0]['text'])['recovery']['observation_id']
        with self.assertRaises(RuntimeError):self.act(s,recovery_observation_id='stale')
        b.fail_input=False
        self.act(s,recovery_observation_id=observation)
        self.assertEqual(b.actions,2);self.assertFalse(s.recovery.inspection_required)
        self.assertEqual(s.recovery.last['outcome'],'dispatched_and_observed')
    def test_capture_failure_after_input_preserves_partial_result_and_never_replays(self):
        s,b=self.make();b.fail_capture=True
        with self.assertRaises(RuntimeError):self.act(s)
        self.assertTrue(s.recovery.inspection_required)
        with self.assertRaises(RuntimeError):s.call('desktop_observe',{})
        self.assertIsNone(s.recovery.observation_id);self.assertEqual(b.actions,1)
        b.fail_capture=False;s.call('desktop_observe',{})
        self.assertIsNotNone(s.recovery.observation_id)
    def test_validation_failure_does_not_reuse_previous_progress(self):
        s,b=self.make();self.act(s)
        def reject(a):raise ValueError('invalid action')
        b.action=reject
        with self.assertRaises(ValueError):self.act(s)
        self.assertFalse(s.recovery.inspection_required)
        self.assertEqual(s.recovery.last['input_events_attempted'],0)
        self.assertEqual(s.recovery.last['outcome'],'failed_before_input')
    def test_metadata_is_bounded_and_contains_no_action_payload(self):
        ledger=m.RecoveryLedger()
        for _ in range(100):
            ledger.begin();ledger.finish({'input_events_attempted':0})
        self.assertLess(len(json.dumps(ledger.snapshot())),1000)
        self.assertNotIn('text',ledger.last);self.assertEqual(len(ledger.last['result_id']),32)
    def test_new_observation_invalidates_old_acknowledgment(self):
        s,b=self.make();b.fail_input=True
        with self.assertRaises(RuntimeError):self.act(s)
        s.call('desktop_observe',{});old=s.recovery.observation_id
        s.call('desktop_observe',{})
        with self.assertRaises(RuntimeError):self.act(s,recovery_observation_id=old)
        self.assertEqual(b.actions,1)

if __name__=='__main__':unittest.main()

class PublicationRecoveryTests(unittest.TestCase):
    def test_cancel_after_capture_requires_inspection_before_more_input(self):
        import threading
        s=m.Server(Partial)
        s.call('desktop_start',{})
        content=s.call('desktop_action',{'action':{'type':'click','x':1,'y':1}})
        s.cancel_token=threading.Event();s.cancel_token.set()
        request={'id':7,'params':{'name':'desktop_action'},'_generation':s.generation}
        response=s.fence_response(request,{'id':7,'result':{'content':content}})
        self.assertTrue(response['result']['isError'])
        self.assertTrue(s.recovery.inspection_required)
        self.assertEqual(s.recovery.last['outcome'],'effects_uncertain')
        self.assertFalse(any(c['type']=='image' for c in response['result']['content']))

class SuppressedObservationTests(unittest.TestCase):
    def test_unpublished_observation_cannot_acknowledge_recovery(self):
        import threading
        s=m.Server(Partial);s.call('desktop_start',{});s.backend.fail_input=True
        with self.assertRaises(RuntimeError):s.call('desktop_action',{'action':{'type':'click','x':1,'y':1}})
        content=s.call('desktop_observe',{});self.assertIsNotNone(s.recovery.observation_id)
        s.cancel_token=threading.Event();s.cancel_token.set()
        result=s.fence_response({'id':9,'params':{'name':'desktop_observe'}},{'id':9,'result':{'content':content}})
        self.assertTrue(result['result']['isError']);self.assertIsNone(s.recovery.observation_id)
        self.assertTrue(s.recovery.inspection_required)
