import json,time,unittest
from test_transport import Harness

class StatusWaitTests(unittest.TestCase):
    def wait_reply(self,h,ident):
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            for line in h.output.getvalue().splitlines():
                reply=json.loads(line)
                if reply.get('id')==ident:return reply
            time.sleep(.005)
        self.fail('bounded waiter did not return')
    def send_wait(self,h,ident=80,**extra):
        args=dict(wait_after=h.server.status()['status_revision'],timeout_seconds=5,**extra)
        h.send({'id':ident,'method':'tools/call','params':{'name':'desktop_status','arguments':args}})
        deadline=time.monotonic()+1
        while not h.transport.wait_lock.locked() and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue(h.transport.wait_lock.locked())
    def test_wait_does_not_block_physical_continue_worker_and_never_captures(self):
        h=Harness()
        try:
            h.server.call('desktop_pause',{'reason':'human review','task_summary':'Append only unfinished scratch segment'})
            captures=[]
            original_capture=h.server.backend.capture
            def capture():
                self.assertEqual(h.server.state,'resuming')
                captures.append(True);return original_capture()
            h.server.backend.capture=capture
            self.send_wait(h)
            self.assertEqual(h.output.getvalue(),'')
            self.assertEqual(captures,[])
            h.transport.panel_control('continue')
            reply=self.wait_reply(h,80)
            status=json.loads(reply['result']['content'][0]['text'])
            self.assertEqual(status['wait_outcome'],'changed')
            self.assertTrue(all(c['type']=='text' for c in reply['result']['content']))
            deadline=time.monotonic()+1
            while h.server.state!='active' and time.monotonic()<deadline:time.sleep(.005)
            self.assertEqual(h.server.state,'active')
            self.assertTrue(h.server.status()['ready_to_observe'])
            self.assertFalse(h.server.status()['input_allowed'])
            self.assertEqual(captures,[True])
            # The serial worker remains responsive.
            h.send({'id':81,'method':'ping'})
            self.wait_reply(h,81)
        finally:h.finish()
    def test_stop_wakes_wait_and_remains_terminal(self):
        h=Harness()
        try:
            self.send_wait(h)
            h.send({'id':81,'method':'tools/call','params':{'name':'desktop_stop'}})
            self.wait_reply(h,80);self.wait_reply(h,81)
            self.assertEqual(h.server.status()['control_state'],'stopped')
            self.assertFalse(h.server.status()['capture_allowed'])
        finally:h.finish()
    def test_cancel_wait_does_not_interrupt_desktop(self):
        h=Harness()
        try:
            self.send_wait(h)
            h.send({'method':'notifications/cancelled','params':{'requestId':80}})
            status=json.loads(self.wait_reply(h,80)['result']['content'][0]['text'])
            self.assertEqual(status['wait_outcome'],'cancelled')
            self.assertFalse(h.backend.stopped.is_set())
        finally:h.finish()
    def test_invalid_timeout_returns_error_and_no_input(self):
        h=Harness()
        try:
            h.send({'id':80,'method':'tools/call','params':{'name':'desktop_status','arguments':{'wait_after':'x','timeout_seconds':51}}})
            self.assertTrue(self.wait_reply(h,80)['result']['isError'])
            self.assertFalse(h.backend.entered.is_set())
        finally:h.finish()

if __name__=='__main__':unittest.main()
