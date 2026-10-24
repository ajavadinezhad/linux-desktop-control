"""Supervised action authority; never launches apps or a real model."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'examples'))
import qwen_desktop_agent as m

class Tests(unittest.TestCase):
    def setUp(self):
        self.meta={'active':True,'logical_size':[1920,1200],'window_observation':{'observation_id':'a'*32}}
        self.path=Path('/tmp/new-qwen-test.mmp')
    def check(self,action,**fields):
        return m.checked_action(dict(intent='Test visible LMMS control',action=action,**fields),self.meta,(1280,800),self.path)
    def test_maps_model_pixels_to_logical_coordinates(self):
        result=self.check({'type':'click','x':640,'y':400})
        self.assertEqual(result['action']['x'],960);self.assertEqual(result['action']['y'],600)
        self.assertEqual(result['window_observation_id'],'a'*32)
    def test_model_cannot_supply_authority_tokens_or_unknown_fields(self):
        with self.assertRaises(ValueError):self.check({'type':'click','x':1,'y':1},window_observation_id='forged')
    def test_nonfinite_and_out_of_bounds_coordinates_refuse(self):
        for x in (-1,1280,float('nan'),float('inf'),True):
            with self.subTest(x=x),self.assertRaises(ValueError):self.check({'type':'click','x':x,'y':1})
    def test_system_shortcuts_refused(self):
        for keys in (['Super','l'],['Alt','F4'],['Ctrl','l'],['Ctrl','o'],['Ctrl','Alt','Delete']):
            with self.subTest(keys=keys),self.assertRaises(ValueError):self.check({'type':'keys','keys':keys})
    def test_transition_separated_from_batches(self):
        with self.assertRaises(ValueError):self.check({'type':'sequence','steps':[{'type':'click','x':1,'y':1}]},focus_transition=True)
        self.check({'type':'keys','keys':['Super']},focus_transition=True)
    def test_only_assigned_save_path_allowed(self):
        self.check({'type':'text','text':str(self.path)})
        for text in ('/tmp/existing.mmp','hello\nworld','echo hi; reboot','$(bad)'):
            with self.subTest(text=text),self.assertRaises(ValueError):self.check({'type':'text','text':text})
    def test_no_nested_or_oversized_sequence(self):
        for steps in ([{'type':'click','x':1,'y':1}]*9,[{'type':'sequence','steps':[]}]):
            with self.assertRaises(ValueError):self.check({'type':'sequence','steps':steps})
    def test_dispatch_requires_fresh_supervisor_approval(self):
        calls=[];client=SimpleNamespace(tool=lambda *args:calls.append(args) or 'ok')
        for approve,now in ((False,1),(True,51),(True,-1)):
            with self.assertRaises(RuntimeError):m.dispatch(client,{},approve,0,now)
        self.assertEqual(calls,[])
        self.assertEqual(m.dispatch(client,{},True,0,1),'ok')
        self.assertEqual(calls,[('desktop_action',{})])
    def test_action_client_is_separate_from_read_only_client(self):
        self.assertNotIn('desktop_action',m.DesktopClient.allowed_tools)
        self.assertIn('desktop_action',m.ActionClient.allowed_tools)
        client=object.__new__(m.DesktopClient)
        with self.assertRaises(ValueError):client.tool('desktop_action',{})
    def test_observation_only_cannot_grant_actions(self):
        import json
        value={'content':[{'type':'text','text':json.dumps(dict(self.meta,observation_only=True))}]}
        with self.assertRaises(RuntimeError):m.frame(value)
    def test_done_cannot_include_action(self):
        with self.assertRaises(ValueError):self.check({'type':'click','x':1,'y':1},done=True)

class PlannerProtocolTests(unittest.TestCase):
    def test_schema_constrained_plan_uses_local_completion_endpoint(self):
        import io,json
        model=m.Planner('http://127.0.0.1:1234','local');requests=[]
        plan={'intent':'Open launcher','done':False,'action':{'type':'keys','keys':['Super']},'focus_transition':True,'await_context_change':False}
        def send(request,timeout):
            requests.append(request)
            return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(plan)}}]}).encode())
        model.opener=SimpleNamespace(open=send)
        self.assertEqual(model.plan(b'x'*32,(1280,800),'LMMS',[],''),plan)
        body=json.loads(requests[0].data)
        self.assertEqual(body['response_format']['type'],'json_schema')
        self.assertEqual(requests[0].full_url,'http://127.0.0.1:1234/v1/chat/completions')
        self.assertFalse(body['store']);self.assertNotIn('tools',body)
    def test_incomplete_plan_never_becomes_an_action(self):
        import io,json
        model=m.Planner('http://127.0.0.1:1234','local')
        response={'choices':[{'finish_reason':'length','message':{'content':'{"action":'}}]}
        model.opener=SimpleNamespace(open=lambda request,timeout:io.BytesIO(json.dumps(response).encode()))
        with self.assertRaises(RuntimeError):model.plan(b'x'*32,(1280,800),'LMMS',[], '')

class HandoffTests(unittest.TestCase):
    def client(self):
        import json
        calls=[]
        def tool(name,args=None):
            calls.append((name,args))
            if name=='desktop_status':return {'content':[{'type':'text','text':json.dumps({'session_state':'paused','pause':{'pause_id':'a'*32,'reason':'pointer-motion'}})}]}
            return 'fresh-frame'
        return SimpleNamespace(tool=tool),calls
    def test_pause_never_resumes_without_explicit_current_handback(self):
        for decision in ({},{'resume':False},{'resume':True,'pause_id':'old'},{'stop':True}):
            client,calls=self.client()
            with self.assertRaises(m.SupervisorStopped):m.acquire(client,decide=lambda:decision)
            self.assertEqual([x[0] for x in calls],['desktop_status'])
    def test_explicit_handback_returns_resume_frame_without_replay(self):
        client,calls=self.client()
        self.assertEqual(m.acquire(client,decide=lambda:{'resume':True,'pause_id':'a'*32}),'fresh-frame')
        self.assertEqual(calls[-1],('desktop_resume',{'pause_id':'a'*32}))
        self.assertNotIn('desktop_action',[x[0] for x in calls])

if __name__=='__main__':unittest.main()
