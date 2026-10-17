import base64
import importlib.util
import json
import pathlib
import struct
import subprocess
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT/'plugins/linux-desktop-control/desktop.py'
spec=importlib.util.spec_from_file_location('desktop',SOURCE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Fake:
    def __init__(self): self.stopped=threading.Event(); self.active=False
    def start(self): self.active=True
    def status(self): return {'active':self.active,'logical_size':[1920,1080]}
    def capture(self): return b'\x89PNG\r\n\x1a\n'+b'\0'*8+struct.pack('>II',3840,2160)
    def action(self,a):
        if a['type']=='fail': raise RuntimeError('injected')
    def close(self): self.active=False
    def shutdown(self): self.close()

class Tests(unittest.TestCase):
    def test_stdio_discovery_no_desktop_consent(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'desktop_status'}}]
        p=subprocess.run(['/usr/bin/python3',str(SOURCE)],input='\n'.join(map(json.dumps,requests))+'\n',text=True,capture_output=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
        replies=list(map(json.loads,p.stdout.splitlines()))
        self.assertEqual(len(replies),3)
        self.assertEqual(len(replies[1]['result']['tools']),7)
        self.assertFalse(json.loads(replies[2]['result']['content'][0]['text'])['active'])
    def test_image_content_and_scaling(self):
        s=m.Server(Fake)
        content=s.call('desktop_start',{})
        self.assertEqual(content[1]['mimeType'],'image/png')
        self.assertTrue(base64.b64decode(content[1]['data']).startswith(b'\x89PNG'))
        self.assertEqual(json.loads(content[0]['text'])['pixel_size'],[3840,2160])
        s.call('desktop_stop',{})
        self.assertFalse(s.backend.active)
    def test_tool_error_is_protocol_result(self):
        s=m.Server(Fake)
        r=s.handle({'id':1,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{'type':'fail'}}}})
        self.assertTrue(r['result']['isError'])
    def backend(self):
        d=object.__new__(m.Desktop)
        d.lock=threading.RLock(); d.stopped=threading.Event(); d.session='/test'
        d.node=1;d.width=1920;d.height=1080;d.held=[];d.events=[]
        d.call=lambda *args,**kw:d.events.append(args)
        return d
    def test_invalid_numeric_and_key_inputs_emit_no_events(self):
        actions=[{'type':'click','x':1,'y':1,'count':True},
                 {'type':'click','x':1,'y':1,'count':1.0},
                 {'type':'scroll','x':1,'y':1,'dy':True},
                 {'type':'wait','seconds':True},
                 {'type':'move','x':1,'y':1,'seconds':False},
                 {'type':'keys','focus':{'x':1,'y':1},'keys':[1]}]
        for action in actions:
            with self.subTest(action=action):
                d=self.backend()
                with self.assertRaises(ValueError):d.action(action)
                self.assertEqual(d.events,[])
    def test_drag_releases_after_interruption(self):
        d=self.backend()
        def pause(t):
            d.stopped.set()
            raise RuntimeError('stopped')
        d.pause=pause
        with self.assertRaises(RuntimeError): d.action({'type':'drag','path':[[1,1],[20,20]]})
        self.assertFalse(d.held)
        self.assertEqual(d.events[-1][1],'NotifyPointerButton')
        self.assertEqual(d.events[-1][3][-1],0)
    def test_invalid_drag_has_no_input(self):
        d=self.backend()
        with self.assertRaises(ValueError):d.action({'type':'drag','path':[[1,1],[5000,20]]})
        self.assertFalse(d.events)
    def test_revocation_blocks_input(self):
        d=self.backend();d.stopped.set()
        with self.assertRaises(RuntimeError):d.action({'type':'click','x':1,'y':1})
        self.assertFalse(d.events)
    def test_nonfinite_coordinate_rejected(self):
        d=self.backend()
        with self.assertRaises(ValueError):d.position(float('nan'),2)
        self.assertFalse(d.events)


class FocusTests(unittest.TestCase):
    backend=Tests.backend
    def test_unfocused_text_is_rejected_without_input(self):
        d=self.backend()
        with self.assertRaisesRegex(ValueError,'focus'):
            d.action({'type':'text','text':'must not reach ChatGPT'})
        self.assertFalse(d.events)
    def test_unfocused_shortcut_is_rejected(self):
        d=self.backend()
        with self.assertRaisesRegex(ValueError,'focus'):
            d.action({'type':'keys','keys':['Ctrl','a']})
        self.assertFalse(d.events)
    def test_target_acquired_in_same_transaction(self):
        d=self.backend();d.pause=lambda seconds:None
        steps=[];d._primitive=lambda a:steps.append(a)
        d.action({'type':'text','text':'test','focus':{'x':40,'y':50}})
        self.assertEqual(steps[0],{'type':'click','x':40,'y':50})
        self.assertEqual(steps[1]['text'],'test')
    def test_launcher_sequence_is_one_transaction(self):
        d=self.backend();d.keysym=lambda k:1
        steps=[];d._primitive=lambda a:steps.append(a)
        seq=[{'type':'keys','keys':['Alt','F2']},{'type':'text','text':'test'}]
        d.action({'type':'sequence','steps':seq})
        self.assertEqual(steps,seq)
    def test_invalid_later_step_prevents_all_input(self):
        d=self.backend()
        with self.assertRaises(ValueError):
            d.action({'type':'sequence','steps':[{'type':'click','x':10,'y':10},{'type':'text','text':42}]})
        self.assertFalse(d.events)
    def test_sequence_stops_before_later_step(self):
        d=self.backend();steps=[]
        def step(a):steps.append(a);d.stopped.set()
        d._primitive=step
        with self.assertRaises(RuntimeError):
            d.action({'type':'sequence','steps':[{'type':'click','x':10,'y':10},{'type':'text','text':'never'}]})
        self.assertEqual(len(steps),1)
    def test_capture_rejects_pre_settle_frames(self):
        d=self.backend();d.frames=0
        class Buffer:
            def __init__(self,pts):self.pts=pts
            def get_size(self):return 3
            def extract_dup(self,a,b):return b'PNG'
        class Sample:
            def __init__(self,pts):self.buffer=Buffer(pts)
            def get_buffer(self):return self.buffer
        samples=[Sample(100*m.Gst.MSECOND),Sample(349*m.Gst.MSECOND),Sample(360*m.Gst.MSECOND)]
        class Clock:
            def get_time(self):return 0
        class Pipeline:
            def get_clock(self):return Clock()
            def get_base_time(self):return 0
        class Sink:
            def emit(self,*args):return samples.pop(0)
        d.pipeline=Pipeline();d.sink=Sink()
        self.assertEqual(d.capture(),b'PNG')
        self.assertFalse(samples)
        self.assertEqual(d.capture_info['settling_ms'],350)



class ReliabilityTests(unittest.TestCase):
    backend=Tests.backend
    def test_oversized_typing_rejected_before_click(self):
        d=self.backend()
        with self.assertRaisesRegex(ValueError,'budget'):
            d.action({'type':'text','text':'x'*2500,'focus':{'x':20,'y':20}})
        self.assertFalse(d.events)
    def test_release_failure_revokes_portal(self):
        d=self.backend();d.held=[('key',123)]
        def call(interface,method,*args,**kw):
            d.events.append(method)
            if method=='NotifyKeyboardKeysym':raise RuntimeError('injected release failure')
        d.call=call
        self.assertTrue(d.release())
        self.assertTrue(d.stopped.is_set())
        self.assertIsNone(d.session)
        self.assertIn('Close',d.events)
        self.assertFalse(d.held)
    def test_sequence_reports_partial_progress(self):
        d=self.backend()
        def primitive(a):
            if a['type']=='text':raise RuntimeError('injected')
        d._primitive=primitive
        with self.assertRaises(RuntimeError):
            d.action({'type':'sequence','steps':[{'type':'click','x':1,'y':1},{'type':'text','text':'test'}]})
        self.assertEqual(d.transaction_info['completed_steps'],1)
        self.assertEqual(d.transaction_info['failed_step'],2)
    def test_smooth_move_has_intermediate_points_and_exact_endpoint(self):
        d=self.backend();d.pointer_position=(10,10);points=[]
        d.position=lambda x,y:points.append((x,y));d.pause=lambda t:None
        d.move_to(100,70,.25)
        self.assertGreater(len(points),5)
        self.assertEqual(points[-1],(100,70))
        self.assertTrue(all(10<x<=100 for x,y in points))
    def test_smooth_move_interrupts(self):
        d=self.backend();d.pointer_position=(0,0);points=[]
        d.position=lambda x,y:points.append((x,y))
        def pause(t):raise RuntimeError('stop')
        d.pause=pause
        with self.assertRaises(RuntimeError):d.move_to(100,100,.25)
        self.assertEqual(len(points),1)
        self.assertNotEqual(points[-1],(100,100))
    def test_previous_transaction_pointer_position_is_not_trusted(self):
        d=self.backend();d.pointer_position=(999,999);seen=[]
        d._primitive=lambda a:seen.append(d.pointer_position)
        d.action({'type':'move','x':10,'y':10})
        self.assertEqual(seen,[None])
    def test_wheel_steps_must_be_integer_and_bounded(self):
        d=self.backend()
        for delta in (1.2,51):
            with self.assertRaises(ValueError):d.action({'type':'scroll','x':10,'y':10,'dy':delta,'unit':'steps'})
        self.assertFalse(d.events)

class UnicodeAndCleanupTests(unittest.TestCase):
    backend=Tests.backend
    def test_unicode_uses_gnome_compose_then_hex_and_commit(self):
        d=self.backend();d.keysym=lambda k:{'Ctrl':1,'Shift':2,'u':3}[k]
        events=[];d.state=lambda kind,code,down:events.append((code,down));d.pause=lambda t:None
        d.type_character('é','gnome_unicode')
        self.assertEqual(events[:6],[(1,True),(2,True),(3,True),(3,False),(2,False),(1,False)])
        self.assertEqual(events[6:],[(ord('e'),True),(ord('e'),False),(ord('9'),True),(ord('9'),False),(0xff0d,True),(0xff0d,False)])
    def test_unicode_budget_is_not_ascii_budget(self):
        self.assertGreater(m.Desktop.text_cost('ف'*100),m.Desktop.text_cost('f'*100))
        d=self.backend()
        with self.assertRaisesRegex(ValueError,'budget'):d.action({'type':'text','text':'ف'*100,'focus':{'x':1,'y':1}})
        self.assertFalse(d.events)
    def test_failed_release_and_close_is_visible(self):
        d=self.backend();d.held=[('button',272)]
        def fail(*args,**kwargs):raise RuntimeError('connection lost')
        d.call=fail
        self.assertTrue(d.release())
        self.assertTrue(d.stopped.is_set())
        self.assertIn('GNOME indicator',d.cleanup_warning)

class RevocationTests(unittest.TestCase):
    backend=Tests.backend
    def test_confirmed_revocation_does_not_close_again_or_warn(self):
        d=self.backend();d.pipeline=None;d.fd=None;d.closed_sub=None
        d.portal_closed=False;d.cleanup_warning='earlier warning'
        d.on_session_closed(None,None,'/test',None,None,None,None)
        d.close()
        self.assertTrue(d.portal_closed)
        self.assertIsNone(d.cleanup_warning)
        self.assertFalse(d.events)
        self.assertFalse(d.status()['active'])
    def test_unrelated_session_signal_is_ignored(self):
        d=self.backend();d.portal_closed=False
        d.on_session_closed(None,None,'/different',None,None,None,None)
        self.assertFalse(d.portal_closed)
        self.assertFalse(d.stopped.is_set())

if __name__=='__main__':unittest.main()
