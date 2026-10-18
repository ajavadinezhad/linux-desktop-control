import io,json,os,pathlib,threading,time,unittest
from test_control import m,Fake

class Blocking(Fake):
    def __init__(self):
        super().__init__();self.active=True
        self.entered=threading.Event();self.finished=threading.Event()
        self.held=False;self.was_released=False;self.was_shutdown=False
    def action(self,a):
        self.held=True;self.entered.set()
        try:
            if not self.cancelled.wait(3):raise RuntimeError('test timeout waiting for cancellation')
            raise RuntimeError('cancelled in '+a['type'])
        finally:
            self.held=False;self.was_released=True;self.finished.set()
    def close(self):
        self.active=False
    def shutdown(self):
        self.was_shutdown=True;self.close()

class Harness:
    def __init__(self):
        self.backend=Blocking();self.server=m.Server(lambda:self.backend)
        self.server.backend=self.backend;self.server.state='active'
        self.transport=m.StdioTransport(self.server)
        r,w=os.pipe();self.reader=os.fdopen(r,'r');self.writer=os.fdopen(w,'w')
        self.output=io.StringIO()
        self.thread=threading.Thread(target=self.transport.run,args=(self.reader,self.output),daemon=True)
        self.thread.start()
    def send(self,request):
        self.writer.write(json.dumps(request)+'\n');self.writer.flush()
    def begin(self,kind):
        self.send({'jsonrpc':'2.0','id':42,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{'type':kind}}}})
        assert self.backend.entered.wait(1),'action not started'
    def finish(self):
        if not self.writer.closed:self.writer.close()
        self.thread.join(1)
        self.reader.close()

class TransportTests(unittest.TestCase):
    def test_stop_interrupts_drag_while_reader_keeps_running(self):
        h=Harness()
        try:
            h.begin('drag')
            started=time.monotonic()
            h.send({'jsonrpc':'2.0','id':43,'method':'tools/call','params':{'name':'desktop_close'}})
            self.assertTrue(h.backend.finished.wait(1))
            self.assertLess(time.monotonic()-started,1)
            self.assertTrue(h.backend.was_released)
        finally:h.finish()
        self.assertFalse(h.thread.is_alive())
        replies={r['id']:r for r in map(json.loads,h.output.getvalue().splitlines())}
        self.assertTrue(replies[42]['result']['isError'])
        self.assertFalse(json.loads(replies[43]['result']['content'][0]['text'])['active'])
    def test_cancel_notification_interrupts_typing(self):
        h=Harness()
        try:
            h.begin('text')
            h.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':42,'reason':'user cancelled'}})
            self.assertTrue(h.backend.finished.wait(1))
            self.assertTrue(h.backend.was_released)
        finally:h.finish()
    def test_unrelated_cancel_does_not_stop_active_action(self):
        h=Harness()
        try:
            h.begin('drag')
            h.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':999}})
            h.send({'jsonrpc':'2.0','id':99,'method':'ping'})
            self.assertFalse(h.backend.finished.wait(.05))
            self.assertFalse(h.backend.cancelled.is_set())
        finally:h.finish()
        self.assertTrue(h.backend.was_released)
    def test_eof_interrupts_typing_and_runs_shutdown(self):
        h=Harness();h.begin('text')
        h.writer.close()
        self.assertTrue(h.backend.finished.wait(1))
        h.finish()
        self.assertFalse(h.thread.is_alive())
        self.assertTrue(h.backend.was_shutdown)
        self.assertTrue(h.backend.was_released)
    def test_cancelled_queued_request_never_reaches_action(self):
        h=Harness()
        try:
            h.begin('drag')
            h.send({'id':44,'method':'tools/call','params':{'name':'desktop_action','arguments':{'action':{'type':'text'}}}})
            h.send({'method':'notifications/cancelled','params':{'requestId':44}})
            # Complete the current action; queued cancellation must survive dispatch.
            h.send({'method':'notifications/cancelled','params':{'requestId':42}})
            self.assertTrue(h.backend.finished.wait(1))
        finally:h.finish()
        replies={r['id']:r for r in map(json.loads,h.output.getvalue().splitlines())}
        self.assertTrue(replies[44]['result']['isError'])
        self.assertRegex(json.loads(replies[44]['result']['content'][0]['text'])['error'],'cancelled|invalidated')
    def test_malformed_calls_do_not_disconnect_backend(self):
        h=Harness()
        try:
            for index,arguments in enumerate((None,False,0,[],"invalid")):
                h.send({'id':100+index,'method':'tools/call','params':{'name':'desktop_status','arguments':arguments}})
            for params in (None,False,0,[]):
                h.send({'id':200,'method':'tools/call','params':params})
            h.send({'id':300,'method':'ping'})
            deadline=time.monotonic()+1
            while '"id": 300' not in h.output.getvalue() and time.monotonic()<deadline:
                time.sleep(.005)
            self.assertTrue(h.thread.is_alive())
            self.assertIn('"id": 300',h.output.getvalue())
            self.assertFalse(h.backend.was_shutdown)
            self.assertFalse(h.backend.cancelled.is_set())
        finally:h.finish()
        replies=list(map(json.loads,h.output.getvalue().splitlines()))
        self.assertEqual(sum('error' in r for r in replies),9)
    def test_stop_surfaces_cleanup_warning_at_tool_boundary(self):
        server=m.Server(Blocking);server.backend=Blocking()
        server.backend.status=lambda:{'active':False,'cleanup_warning':'portal close unconfirmed'}
        result=server.handle({'id':1,'method':'tools/call','params':{'name':'desktop_close'}})
        payload=json.loads(result['result']['content'][0]['text'])
        self.assertEqual(payload['cleanup_warning'],'portal close unconfirmed')

if __name__=='__main__':unittest.main()
