"""Read-only adapter boundaries; no GUI, network or real model required."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import unittest
from types import SimpleNamespace

path=Path(__file__).resolve().parents[1]/'examples/notification_observer.py'
spec=importlib.util.spec_from_file_location('notification_observer_client_test',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ClientTests(unittest.TestCase):
    def test_only_explicit_loopback_without_redirects_or_proxy(self):
        for url in ('https://example.com','http://localhost:1234','http://127.0.0.1:1234/private','http://name:secret@127.0.0.1:1234','http://127.0.0.1','http://127.0.0.1:1234?token=x'):
            with self.subTest(url=url),self.assertRaises(ValueError):m.LocalModel(url,'model')
        m.LocalModel('http://127.0.0.1:1234','model')
        with self.assertRaises(RuntimeError):m.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_api_payload_has_no_action_tools_and_disables_chat_storage(self):
        model=m.LocalModel('http://127.0.0.1:1234','model');requests=[]
        def send(request,timeout):
            requests.append(request);return io.BytesIO(json.dumps({'output':[{'type':'message','content':'A cursor.'}]}).encode())
        model.opener=SimpleNamespace(open=send)
        self.assertEqual(model.describe(b'x'*32),'A cursor.')
        body=json.loads(requests[0].data)
        self.assertEqual(body['input'][0]['content'],m.TASK_PROMPT)
        self.assertEqual(body['integrations'],[]);self.assertFalse(body['store']);self.assertFalse(body['stream'])
        self.assertEqual(body['input'][1]['data_url'],'data:image/png;base64,'+base64.b64encode(b'x'*32).decode())

    def test_adapter_refuses_input_before_sending_to_process(self):
        client=object.__new__(m.DesktopClient)
        for name in ('desktop_action','desktop_resume','desktop_pause'):
            with self.assertRaises(ValueError):client.tool(name,{'action':{'type':'click'}})

    def test_newer_revision_is_reported_after_inference(self):
        result={'content':[{'type':'text','text':json.dumps({'observation_only':True,'capture':{'observer_stream_id':'s','content_revision':1}})},
                           {'type':'image','data':base64.b64encode(b'x'*32).decode()}]}
        calls=[]
        client=SimpleNamespace(tool=lambda name:calls.append(name) or result,
                               resource=lambda:{'session_state':'paused','stream':{'stream_id':'s','revision':2}})
        model=SimpleNamespace(describe=lambda frame:'Description of earlier frame')
        r=m.observe_turn(client,model)
        self.assertTrue(r['newer_frame_available']);self.assertTrue(r['observation_only'])
        self.assertFalse(r['input_authority']);self.assertEqual(calls,['desktop_observe'])

    def test_stop_during_model_turn_discards_description(self):
        result={'content':[{'type':'text','text':'{"capture":{"observer_stream_id":"s","content_revision":1}}'}, {'type':'image','data':base64.b64encode(b'x'*32).decode()}]}
        client=SimpleNamespace(tool=lambda name:result,resource=lambda:{'session_state':'closed'})
        r=m.observe_turn(client,SimpleNamespace(describe=lambda frame:'Private description'))
        self.assertEqual(r['kind'],'description-discarded');self.assertNotIn('description',r)

class CompletionTests(unittest.TestCase):
    def test_token_limit_fragment_is_not_a_completed_answer(self):
        model=m.LocalModel('http://127.0.0.1:1234','model')
        response={'output':[{'type':'message','content':'The screenshot shows a terminal with a'}],
                  'stats':{'total_output_tokens':120}}
        model.opener=SimpleNamespace(open=lambda request,timeout:io.BytesIO(json.dumps(response).encode()))
        with self.assertRaises(m.IncompleteModelResponse):model.describe(b'x'*32)

class DelayedResultTests(unittest.TestCase):
    def test_result_suppressed_when_observation_becomes_unavailable(self):
        result={'content':[{'type':'text','text':'{"capture":{"observer_stream_id":"s","content_revision":1}}'},
                           {'type':'image','data':base64.b64encode(b'x'*32).decode()}]}
        for state in ('closed','unavailable','auth-waiting','resuming','session-invalidated',None):
            with self.subTest(state=state):
                client=SimpleNamespace(tool=lambda name:result,resource=lambda:{'session_state':state,'stream':{'stream_id':'s','revision':1}})
                value=m.observe_turn(client,SimpleNamespace(describe=lambda frame:'Earlier private frame'))
                self.assertEqual(value['kind'],'description-discarded');self.assertNotIn('description',value)

    def test_manual_pause_without_stream_suppresses_delayed_result(self):
        result={'content':[{'type':'text','text':'{"capture":{"observer_stream_id":"s","content_revision":1}}'},
                           {'type':'image','data':base64.b64encode(b'x'*32).decode()}]}
        client=SimpleNamespace(tool=lambda name:result,resource=lambda:{'session_state':'paused','stream':None})
        value=m.observe_turn(client,SimpleNamespace(describe=lambda frame:'Earlier private frame'))
        self.assertEqual(value['kind'],'description-discarded');self.assertNotIn('description',value)

class TransitionTests(unittest.TestCase):
    @staticmethod
    def observation(stream='s',revision=1,pixels=b'a'*32):
        return {'content':[{'type':'text','text':json.dumps({'capture':{'observer_stream_id':stream,'content_revision':revision}})},
                           {'type':'image','data':base64.b64encode(pixels).decode()}]}

    def test_unchanged_frame_is_not_marked_newer(self):
        client=SimpleNamespace(tool=lambda name:self.observation(),resource=lambda:{'session_state':'active','stream':{'stream_id':'s','revision':1}})
        value=m.observe_turn(client,SimpleNamespace(describe=lambda frame:'Original screen'))
        self.assertFalse(value['newer_frame_available']);self.assertFalse(value['input_authority'])

    def test_reconnected_stream_discards_previous_consent_description(self):
        client=SimpleNamespace(tool=lambda name:self.observation(),resource=lambda:{'session_state':'active','stream':{'stream_id':'replacement','revision':1}})
        value=m.observe_turn(client,SimpleNamespace(describe=lambda frame:'Previous stream'))
        self.assertEqual(value['kind'],'description-discarded');self.assertNotIn('description',value)

    def test_invalid_capture_identity_never_reaches_model(self):
        for capture in ({},None,{'observer_stream_id':'s','content_revision':True},
                        {'observer_stream_id':'','content_revision':1},
                        {'observer_stream_id':'s','content_revision':-1}):
            with self.subTest(capture=capture):
                result=self.observation();result['content'][0]['text']=json.dumps({'capture':capture})
                client=SimpleNamespace(tool=lambda name:result)
                value=m.observe_turn(client,SimpleNamespace(describe=lambda frame:self.fail('Unbound image sent to model')))
                self.assertEqual(value['kind'],'description-discarded')

    def test_invalid_final_stream_or_revision_regression_discards_description(self):
        for stream in ({},[],{'stream_id':'s','revision':True},
                       {'stream_id':'s','revision':0}):
            with self.subTest(stream=stream):
                client=SimpleNamespace(tool=lambda name:self.observation(),
                    resource=lambda:{'session_state':'active','stream':stream})
                value=m.observe_turn(client,SimpleNamespace(describe=lambda frame:'Earlier screen'))
                self.assertEqual(value['kind'],'description-discarded');self.assertNotIn('description',value)

    def test_next_turn_uses_new_image_instead_of_replaying_previous_frame(self):
        observations=iter([self.observation(pixels=b'a'*32),self.observation(revision=2,pixels=b'b'*32)])
        current={'revision':1};seen=[]
        client=SimpleNamespace(tool=lambda name:next(observations),resource=lambda:{'session_state':'active','stream':{'stream_id':'s','revision':current['revision']}})
        model=SimpleNamespace(describe=lambda frame:seen.append(frame) or 'Captured screen')
        self.assertFalse(m.observe_turn(client,model)['newer_frame_available'])
        current['revision']=2
        self.assertFalse(m.observe_turn(client,model)['newer_frame_available'])
        self.assertEqual(seen,[b'a'*32,b'b'*32])

    def test_model_timeout_is_not_retried_and_does_not_send_input(self):
        calls=[]
        client=SimpleNamespace(tool=lambda name:calls.append(name) or self.observation(),resource=lambda:self.fail('No result should be published'))
        def fail(frame):raise TimeoutError('simulated inference timeout')
        with self.assertRaises(TimeoutError):m.observe_turn(client,SimpleNamespace(describe=fail))
        self.assertEqual(calls,['desktop_observe'])

    def test_notification_burst_coalesces_and_disconnect_wakes_receiver(self):
        import threading
        import queue
        values=[{'method':'notifications/resources/updated','params':{'uri':m.URI}}]*1000
        client=object.__new__(m.DesktopClient)
        client.changed=threading.Event();client.closed=threading.Event();client.responses=queue.Queue(maxsize=4)
        client.process=SimpleNamespace(stdout=io.StringIO(''.join(json.dumps(v)+'\n' for v in values)))
        client._receive()
        self.assertTrue(client.changed.is_set());self.assertTrue(client.closed.is_set())
        self.assertTrue(client.responses.empty())

if __name__=='__main__':unittest.main()
