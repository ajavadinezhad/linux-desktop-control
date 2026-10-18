"""Concurrent startup status uses no GUI, portal, or native helper."""
import json
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest import mock
from test_control import m

class Input:
    def __init__(self):self.lines=queue.Queue()
    def __iter__(self):return self
    def __next__(self):
        value=self.lines.get(timeout=3)
        if value is None:raise StopIteration
        return value
    def send(self,rid,name,args=None):
        self.lines.put(json.dumps({'jsonrpc':'2.0','id':rid,'method':'tools/call','params':{'name':name,'arguments':args or {}}})+'\n')
class Output:
    def __init__(self):self.lines=queue.Queue()
    def write(self,line):self.lines.put(json.loads(line))
    def flush(self):pass

class StartupStatusTests(unittest.TestCase):
    def test_snapshot_has_no_backend_calls_or_authority_effects(self):
        server=m.Server();server.state='opening';server.backend=mock.Mock()
        server.native_activity=SimpleNamespace(calibration_state='waiting',calibration_resets=1,notice_requested=True,notice_acknowledged=True,notice_active=True)
        token=threading.Event();server.cancel_token=token;server.request_epoch=7
        generation=server.generation
        snapshot=server.startup_status_snapshot()
        self.assertEqual(snapshot['native_activity']['calibration_state'],'waiting')
        self.assertFalse(snapshot['active']);self.assertFalse(snapshot['capture_allowed']);self.assertFalse(snapshot['input_allowed'])
        self.assertFalse(snapshot['portal_closed_confirmed']);self.assertIsNone(snapshot['held_input_count']);self.assertNotIn('input_release',snapshot)
        self.assertEqual(snapshot['snapshot_kind'],'startup-read-only')
        server.backend.assert_not_called();self.assertEqual(server.backend.mock_calls,[])
        self.assertIs(server.cancel_token,token);self.assertEqual(server.request_epoch,7);self.assertEqual(server.generation,generation)

    def test_blocked_start_status_then_close_cancels_original_token(self):
        entered=threading.Event();finished=threading.Event();server=m.Server()
        def call(name,args):
            if name=='desktop_start':
                server.state='opening';server.native_activity=SimpleNamespace(calibration_state='waiting',calibration_resets=0)
                token=server.cancel_token;entered.set()
                self.assertTrue(token.wait(2));self.assertIs(server.cancel_token,token)
                server.state='closed';finished.set()
                return [m.text({'cancelled':True})]
            return [m.text({'closed':True})]
        server.call=call;server.shutdown=lambda:None
        source=Input();output=Output();transport=m.StdioTransport(server)
        worker=threading.Thread(target=transport.run,args=(source,output),daemon=True);worker.start()
        try:
            source.send(1,'desktop_start');self.assertTrue(entered.wait(1))
            original=server.cancel_token;epoch=server.request_epoch
            source.send(2,'desktop_status')
            response=output.lines.get(timeout=1)
            self.assertEqual(response['id'],2)
            snapshot=json.loads(response['result']['content'][0]['text'])
            self.assertEqual(snapshot['native_activity']['calibration_state'],'waiting')
            self.assertFalse(finished.is_set());self.assertIs(server.cancel_token,original);self.assertEqual(server.request_epoch,epoch)
            source.send(3,'desktop_close')
            self.assertTrue(finished.wait(1));self.assertTrue(original.is_set())
            replies=[output.lines.get(timeout=1),output.lines.get(timeout=1)]
            self.assertEqual({r['id'] for r in replies},{1,3})
        finally:
            source.lines.put(None);worker.join(2)
        self.assertFalse(worker.is_alive())

    def test_normal_status_remains_worker_owned(self):
        server=m.Server()
        self.assertIsNone(server.startup_status_snapshot())

    def test_blocked_status_output_does_not_block_close_cancellation(self):
        entered=threading.Event();output_blocked=threading.Event();release=threading.Event();cancelled=threading.Event()
        server=m.Server()
        def call(name,args):
            if name=='desktop_start':
                server.state='opening';server.native_activity=SimpleNamespace(calibration_state='waiting',calibration_resets=0)
                token=server.cancel_token;entered.set()
                if token.wait(1):cancelled.set()
                server.state='closed'
            return [m.text({'closed':True})]
        server.call=call;server.shutdown=lambda:None
        class BlockedOutput(Output):
            def write(self,line):
                output_blocked.set();release.wait(2);super().write(line)
        source=Input();output=BlockedOutput();transport=m.StdioTransport(server)
        worker=threading.Thread(target=transport.run,args=(source,output),daemon=True);worker.start()
        try:
            source.send(1,'desktop_start');self.assertTrue(entered.wait(1))
            source.send(2,'desktop_status');self.assertTrue(output_blocked.wait(1))
            # Fill the single queued reply, then force fallback to normal work.
            source.send(3,'desktop_status');source.send(4,'desktop_status')
            source.send(5,'desktop_close')
            self.assertTrue(cancelled.wait(.5),'Output backpressure delayed cancellation')
            self.assertLessEqual(transport.startup_responses.qsize(),1)
        finally:
            release.set();source.lines.put(None);worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertFalse(transport.startup_writer.is_alive())

    def test_output_backpressure_does_not_block_eof_cancellation(self):
        entered=threading.Event();blocked=threading.Event();release=threading.Event();cancelled=threading.Event()
        server=m.Server()
        def call(name,args):
            server.state='opening';entered.set()
            if server.cancel_token.wait(1):cancelled.set()
            return [m.text({'cancelled':True})]
        server.call=call;server.shutdown=lambda:None
        class BlockedOutput(Output):
            def write(self,line):blocked.set();release.wait(2);super().write(line)
        source=Input();transport=m.StdioTransport(server)
        worker=threading.Thread(target=transport.run,args=(source,BlockedOutput()),daemon=True);worker.start()
        try:
            source.send(1,'desktop_start');self.assertTrue(entered.wait(1))
            source.send(2,'desktop_status');self.assertTrue(blocked.wait(1))
            source.lines.put(None)
            self.assertTrue(cancelled.wait(.5))
        finally:release.set();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertFalse(transport.startup_writer.is_alive())

    def test_main_writer_state_lock_does_not_block_status_then_cancel(self):
        output_blocked=threading.Event();release=threading.Event()
        server=m.Server();server.state='opening'
        backend=SimpleNamespace(cancelled=threading.Event())
        server.backend=backend;server.shutdown=lambda:None
        # Returning from a fake start leaves the main worker in its response
        # publication section, holding state_lock while stdout is blocked.
        server.handle=lambda request:{'jsonrpc':'2.0','id':request['id'],'result':{'content':[]}}
        server.fence_response=lambda request,response:response
        class BlockedOutput(Output):
            def write(self,line):output_blocked.set();release.wait(2);super().write(line)
        source=Input();transport=m.StdioTransport(server)
        worker=threading.Thread(target=transport.run,args=(source,BlockedOutput()),daemon=True);worker.start()
        try:
            source.send(1,'desktop_start');self.assertTrue(output_blocked.wait(1))
            token=server.cancel_token
            source.send(2,'desktop_status')
            source.lines.put(json.dumps({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':1}})+'\n')
            self.assertTrue(token.wait(.5),'Snapshot lock blocked cancellation reader')
            self.assertTrue(backend.cancelled.wait(.5))
        finally:
            release.set();source.lines.put(None);worker.join(2)
        self.assertFalse(worker.is_alive());self.assertFalse(transport.startup_writer.is_alive())
