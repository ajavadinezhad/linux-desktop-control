"""Larger stable-canvas batches preserve transactional admission and cancellation."""
import unittest
import test_control as legacy

class StrokeBatchTests(unittest.TestCase):
    backend=legacy.Tests.backend
    def batch(self,n=24):
        return {'type':'sequence','stroke_batch':True,'steps':[{'type':'click','x':5,'y':5}]+[{'type':'drag','path':[[10,10],[12,12]]} for _ in range(n-1)]}
    def test_twenty_four_stable_steps_admitted_but_default_remains_eight(self):
        d=self.backend();a=self.batch();d.validate_action(a)
        a.pop('stroke_batch')
        with self.assertRaises(ValueError):d.validate_action(a)
        with self.assertRaises(ValueError):d.validate_action(self.batch(25))
    def test_no_text_keys_scroll_or_tool_selection_inside_extended_batch(self):
        for step in ({'type':'text','text':'x'},{'type':'keys','keys':['Return']},{'type':'click','x':3,'y':4},{'type':'scroll','x':3,'y':4,'dy':1},{'type':'wait','seconds':0},{'type':'drag','path':[[1,1],[2,2]],'button':'right'}):
            d=self.backend();a=self.batch();a['steps'][-1]=step
            with self.subTest(step=step),self.assertRaises(ValueError):d.action(a)
            self.assertFalse(d.events)
    def test_budget_and_all_points_validated_before_any_input(self):
        for invalid in ('budget','point'):
            d=self.backend();a=self.batch()
            if invalid=='budget':
                for step in a['steps'][1:]:step['path']=[[10,10]]*20
            else:a['steps'][-1]['path'][-1]=[99999,10]
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):d.action(a)
            self.assertFalse(d.events)
    def test_cancellation_prevents_later_strokes_and_releases_input(self):
        d=self.backend();seen=[]
        def primitive(step):
            seen.append(step)
            if len(seen)==3:d.cancelled.set()
        d._primitive=primitive
        with self.assertRaises(RuntimeError):d.action(self.batch())
        self.assertEqual(len(seen),3)
        self.assertEqual(d.transaction_info['completed_steps'],3)
        self.assertFalse(d.held)
    def test_flag_is_boolean_outer_sequence_only(self):
        for a in ({'type':'move','x':1,'y':1,'stroke_batch':True},dict(self.batch(),stroke_batch=1)):
            with self.assertRaises(ValueError):self.backend().validate_action(a)
        a=self.batch();a['steps'][1]['stroke_batch']=False
        with self.assertRaises(ValueError):self.backend().validate_action(a)
    def test_single_focus_click_required(self):
        for update in ({'count':2},{'button':'right'},{'type':'move'}):
            a=self.batch();a['steps'][0].update(update)
            with self.assertRaises(ValueError):self.backend().validate_action(a)
