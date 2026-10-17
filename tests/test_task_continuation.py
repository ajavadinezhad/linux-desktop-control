import importlib.util,pathlib,sys,unittest
from test_control import m
p=pathlib.Path(m.__file__).with_name('task_continuation.py');spec=importlib.util.spec_from_file_location('task_continuation_test',p)
helper=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
class ContinuationTests(unittest.TestCase):
    def make(self):
        c=helper.TaskContinuation();c.save('Finish disposable note','First paragraph saved','Check final paragraph then save','result1',1);return c
    def state(self,state='active',epoch=1,**extra):return dict(control_state=state,control_epoch=epoch,**extra)
    def test_pause_keeps_remaining_work_pending_without_capture_or_input(self):
        c=self.make();c.record_observation(1)
        for state in ('paused','pausing','resuming'):
            d=c.classify(self.state(state));self.assertEqual(d['decision'],'wait');self.assertTrue(d['pending'])
            self.assertFalse(d['capture']);self.assertFalse(d['input']);self.assertIsNotNone(c.checkpoint)
    def test_toolbar_continue_requires_assistant_image_and_ack_before_plan(self):
        c=self.make();c.classify(self.state('paused',2))
        status=self.state(epoch=2,ready_to_observe=True,recovery={'inspection_required':True,'observation_id':None})
        self.assertEqual(c.classify(status)['decision'],'observe')
        status['ready_to_observe']=False;status['recovery']['observation_id']='new-frame'
        self.assertEqual(c.classify(status)['decision'],'observe')
        c.record_observation(2,'new-frame');d=c.classify(status)
        self.assertEqual(d['decision'],'plan_from_current_state');self.assertEqual(d['recovery_observation_id'],'new-frame')
        self.assertFalse(d['input']);self.assertFalse(d['automatic_retry']);self.assertNotIn('action',d)
    def test_epoch_change_invalidates_cached_view(self):
        c=self.make();c.record_observation(1)
        self.assertEqual(c.classify(self.state())['decision'],'plan_from_current_state')
        self.assertEqual(c.classify(self.state(epoch=2))['decision'],'observe')
    def test_partial_effects_require_reconcile_after_observation(self):
        c=self.make();status=self.state(recovery={'inspection_required':True,'observation_id':'frame','last_result':{'outcome':'effects_uncertain','result_id':'partial2'}})
        self.assertEqual(c.classify(status)['decision'],'observe');c.record_observation(1,'frame')
        self.assertEqual(c.classify(status)['decision'],'reconcile');c.mark_reconciled('wrong')
        self.assertEqual(c.classify(status)['decision'],'reconcile');c.mark_reconciled('partial2')
        self.assertEqual(c.classify(status)['decision'],'plan_from_current_state')
    def test_stop_is_terminal_and_never_automatic_restart(self):
        c=self.make();self.assertEqual(c.classify(self.state('stopped'))['decision'],'end')
        self.assertEqual(c.classify(self.state())['decision'],'end')
    def test_wait_does_not_mark_work_completed_or_replace_intent(self):
        c=self.make();before=c.checkpoint
        for _ in range(20):c.classify(self.state('paused'))
        self.assertEqual(c.checkpoint,before);self.assertEqual(c.checkpoint.next_step,'Check final paragraph then save')
    def test_bounded_checkpoint_rejects_payload_size_and_missing_intent(self):
        c=helper.TaskContinuation()
        with self.assertRaises(ValueError):c.save('x'*1001,'','','id',1)
        with self.assertRaises(ValueError):c.save('','done','next','id',1)
        self.assertEqual(c.classify(self.state())['decision'],'observe')
        c.record_observation(1);self.assertEqual(c.classify(self.state())['decision'],'wait')

if __name__=='__main__':unittest.main()
