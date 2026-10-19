"""Full Python socket handshake with an injected peer, never pkexec/devices/UI."""
import os
import socket
import tempfile
import threading
import time
import unittest
import test_native_activity as legacy
m=legacy.m

class Notice:
    def __init__(self):self.phase=None;self.active=False;self.post_arm=threading.Event();self.events=[];self.owner=None;self.fail_close=False
    def show(self,reset=False,phase='calibration'):
        self.phase=phase;self.active=True;self.events.append(('show',phase))
        if phase=='post-arm-pointer':self.post_arm.set()
    def close(self):
        self.events.append(('close',self.phase))
        if self.fail_close and self.phase=='post-arm-pointer':return False
        self.active=False;return True
    def status(self):return {'request_acknowledged':True,'request_active':self.active,'delivery_unknown':False}

class GatePeer(legacy.FakeBroker):
    def __init__(self,args,**kwargs):
        self.motion=threading.Event();self.allow_ack=threading.Event();self.resume_seen=threading.Event();self.initial_arm=threading.Event();self.terminal_key=False;self.supersede_resume=False
        super().__init__(args,**kwargs)
    def run(self):
        try:
            peer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.connection=peer;peer.settimeout(3);peer.connect(self.args[3]);stream=peer.makefile('rb')
            peer.sendall(b'READY\n')
            for expected,response in (('MODEYIELD2',b'MODEYIELD2_OK\n'),('CALIBRATE',b'CALIBRATING\nCALIBRATED\n'),('ARM',b'ARMED\n')):
                while True:
                    command=stream.readline().decode().strip();self.commands.append(command)
                    if command=='HB':peer.sendall(b'ALIVE\n');continue
                    if command!=expected:return
                    peer.sendall(response);break
            self.initial_arm.set();sent=False;ack=False
            while not self.done.is_set():
                command=stream.readline().decode().strip();self.commands.append(command)
                if not command or command=='CLOSE':break
                if command=='HB':
                    peer.sendall(b'ALIVE\n')
                    if self.motion.is_set() and not sent:
                        if self.terminal_key:
                            peer.sendall(b'ACTIVITY_KEY\nOBS_DIAG_1100\n');break
                        peer.sendall(b'YIELDED_1\nQUIET_1\n');sent=True
                elif command=='RESUME_1':
                    self.resume_seen.set()
                    if self.supersede_resume:peer.sendall(b'YIELDED_2\nQUIET_2\n')
                else:return
                if self.resume_seen.is_set() and self.allow_ack.is_set() and not ack:
                    peer.sendall(b'ARMED_1\n');ack=True
            stream.close()
        except OSError as error:self.error=type(error).__name__
        finally:
            if self.connection:self.connection.close()
            self.returncode=0;self.done.set()

class PostArmIntegrationTests(unittest.TestCase):
    def make(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);os.chmod(temporary.name,0o700)
        peers=[];callbacks=[];notice=Notice();authorized=[True]
        def launch(args,**kwargs):peer=GatePeer(args,**kwargs);peers.append(peer);return peer
        controller=m.Controller(lambda:authorized[0],lambda:callbacks.append('terminal'),lambda error:callbacks.append('fault'),retain_sharing=True,
            on_yield=lambda *args:callbacks.append('server-yield'),on_quiet=lambda *args:callbacks.append('server-quiet'),
            notice=notice,runtime_dir=temporary.name,launcher=launch,validator=lambda:None,credentials=lambda peer:(123,0,0),startup_timeout=1)
        self.addCleanup(controller.close);notice.owner=controller;errors=[]
        controller.gate_reader_ids=set();read=controller._read
        def traced_read(timeout):
            if controller.post_arm_gate and not controller.stop.is_set():controller.gate_reader_ids.add(threading.get_ident())
            return read(timeout)
        controller._read=traced_read
        def start():
            try:controller.start()
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=start,daemon=True);worker.start();self.addCleanup(lambda:worker.join(2))
        self.assertTrue(notice.post_arm.wait(1));self.assertTrue(peers[0].initial_arm.is_set())
        return controller,peers[0],notice,callbacks,worker,errors,authorized

    def test_initial_arm_not_ready_until_fresh_yield_quiet_resume_ack(self):
        c,peer,notice,callbacks,worker,errors,_=self.make()
        self.assertFalse(c.ready);self.assertFalse(c.status()['active']);self.assertFalse(c.post_arm_verified)
        self.assertTrue(worker.is_alive());self.assertEqual(c.post_arm_state,'waiting-motion')
        peer.motion.set();self.assertTrue(peer.resume_seen.wait(1))
        self.assertFalse(c.ready);self.assertFalse(c.status()['active']);self.assertFalse(notice.active)
        self.assertEqual(callbacks,[])
        peer.allow_ack.set();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertEqual(errors,[]);self.assertTrue(c.ready);self.assertTrue(c.post_arm_verified)
        self.assertEqual(c.post_arm_state,'verified');self.assertEqual(callbacks,[])
        self.assertEqual(c.gate_reader_ids,{c.thread.ident})
        self.assertEqual(peer.commands.count('ARM'),1);self.assertEqual(peer.commands.count('RESUME_1'),1)
        self.assertEqual(notice.events,[('show','calibration'),('close','calibration'),('show','post-arm-pointer'),('close','post-arm-pointer')])

    def test_missing_post_arm_motion_times_out_without_resume_or_callbacks(self):
        c,peer,notice,callbacks,worker,errors,_=self.make()
        c.post_arm_deadline_monotonic=time.monotonic()+.05;worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertFalse(c.ready);self.assertFalse(c.post_arm_verified)
        self.assertNotIn('RESUME_1',peer.commands);self.assertNotIn('server-yield',callbacks);self.assertNotIn('server-quiet',callbacks)
        self.assertTrue(c.stop.is_set());self.assertFalse(notice.active)

    def test_terminal_key_during_gate_stops_before_any_resume(self):
        c,peer,notice,callbacks,worker,errors,_=self.make();peer.terminal_key=True;peer.motion.set();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertFalse(c.post_arm_verified);self.assertFalse(c.ready)
        self.assertIn('terminal',callbacks);self.assertNotIn('RESUME_1',peer.commands);self.assertFalse(notice.active)

    def test_revoked_authorization_while_waiting_for_ack_never_ready(self):
        c,peer,notice,callbacks,worker,errors,authorized=self.make();peer.motion.set();self.assertTrue(peer.resume_seen.wait(1))
        authorized[0]=False;peer.allow_ack.set();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertFalse(c.ready);self.assertFalse(c.post_arm_verified)

    def test_unknown_notification_closure_refuses_resume(self):
        c,peer,notice,callbacks,worker,errors,_=self.make();notice.fail_close=True;peer.motion.set();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertFalse(c.ready);self.assertNotIn('RESUME_1',peer.commands)

    def test_new_motion_epoch_during_gate_resume_refuses_readiness(self):
        c,peer,notice,callbacks,worker,errors,_=self.make();peer.supersede_resume=True;peer.motion.set();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertFalse(c.ready);self.assertFalse(c.post_arm_verified)
        self.assertNotIn('server-yield',callbacks);self.assertNotIn('server-quiet',callbacks)
        self.assertNotIn('RESUME_2',peer.commands)

    def test_explicit_stop_wakes_gate_wait_without_resume(self):
        c,peer,notice,callbacks,worker,errors,_=self.make();c.close();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertFalse(c.ready);self.assertFalse(c.post_arm_verified)
        self.assertNotIn('RESUME_1',peer.commands);self.assertFalse(notice.active)

if __name__=='__main__':unittest.main()
