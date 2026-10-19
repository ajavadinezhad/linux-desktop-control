"""Real local sockets, fake privileged peer and GUI: no input devices opened."""
import os
import socket
import tempfile
import threading
import time
import unittest
import test_native_activity as native
import test_retained_pause as fixtures


class YieldBroker(native.FakeBroker):
    def __init__(self,args,mode_ack=b'MODEYIELD2_OK\n',coverage=True,**kwargs):
        self.trigger=threading.Event()
        self.mode_ack=mode_ack;self.coverage=coverage
        super().__init__(args,**kwargs)

    def run(self):
        try:
            peer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.connection=peer;peer.settimeout(3);peer.connect(self.args[3])
            stream=peer.makefile('rb');peer.sendall(b'READY\n')
            for expected,response in [('MODEYIELD2',self.mode_ack),('CALIBRATE',b'CALIBRATING\n'+(b'CALIBRATED\n' if self.coverage else b'')),('ARM',b'ARMED\nYIELDED_1\nQUIET_1\n')]:
                while True:
                    command=stream.readline().decode().strip();self.commands.append(command)
                    if command=='HB':peer.sendall(b'ALIVE\n');continue
                    if command=='REPORT':peer.sendall(b'CAL_DIAG_11011000\n');continue
                    if command!=expected:return
                    peer.sendall(response);break
            sent=False
            while not self.done.is_set():
                command=stream.readline().decode().strip();self.commands.append(command)
                if not command or command=='CLOSE':break
                if command=='HB':
                    peer.sendall(b'ALIVE\n')
                    if self.trigger.is_set() and not sent:
                        peer.sendall(b'YIELDED_2\nQUIET_2\n');sent=True
                elif command in ('RESUME_1','RESUME_2'):peer.sendall(('ARMED_'+command.split('_')[1]+'\n').encode())
                else:return
            stream.close()
        except OSError as error:self.error=type(error).__name__
        finally:
            if self.connection:self.connection.close()
            self.returncode=0;self.done.set()


class RetainedSocketIntegrationTests(unittest.TestCase):
    def test_legacy_missing_and_malformed_mode_ack_never_reach_calibration_or_arm(self):
        for ack in (b'MODEYIELD_OK\n',b'',b'MODEYIELD2_OK extra\n'):
            with self.subTest(ack=ack),tempfile.TemporaryDirectory() as directory:
                os.chmod(directory,0o700);brokers=[]
                def launch(args,**kwargs):
                    broker=YieldBroker(args,mode_ack=ack,**kwargs);brokers.append(broker);return broker
                controller=native.m.Controller(lambda:True,lambda:None,lambda error:None,
                    retain_sharing=True,runtime_dir=directory,launcher=launch,validator=lambda:None,
                    credentials=lambda peer:(123,0,0),startup_timeout=1)
                self.addCleanup(controller.close)
                with self.assertRaises(native.m.NativeFailure):controller.start()
                self.assertEqual(brokers[0].commands[0],'MODEYIELD2')
                self.assertNotIn('CALIBRATE',brokers[0].commands)
                self.assertNotIn('ARM',brokers[0].commands)
                self.assertFalse(controller.status()['active'])
                self.assertFalse(controller.status()['calibration_verified'])

    def test_real_controller_quiet_handshake_returns_once_without_replaying_input(self):
        fixture=fixtures.RetainedPauseTests();server,bridge,backend=fixture.make()
        self.addCleanup(fixture.doCleanups)
        server.pointer_motion_return=True;server.consent_id='consent';backend.consent_id='consent'
        backend.endpoint_context=server.window_guard_module().WindowGuard.signature(bridge.value)
        backend.pointer_reader=lambda:tuple(bridge.value['pointer'])
        backend.position(100,100);backend.pointer_reader=None;backend.endpoint_context=None
        backend.events.clear();bridge.value['pointer']=[140,130]
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory,0o700);brokers=[]
            def launch(args,**kwargs):
                broker=YieldBroker(args,**kwargs);brokers.append(broker);return broker
            controller=native.m.Controller(
                active=lambda:server.state in ('active','pausing','paused','resuming') and backend.session is not None,
                on_activity=lambda:server.native_activity_lost(controller),
                on_fault=lambda error:server.native_activity_lost(controller,error),
                retain_sharing=True,on_yield=server.pointer_yielded,on_quiet=server.pointer_quiet,
                runtime_dir=directory,launcher=launch,validator=lambda:None,
                credentials=lambda peer:(123,0,0),startup_timeout=1)
            server.own_observer('native_activity',controller);server.physical_takeover=True
            try:
                controller.start();brokers[0].trigger.set()
                self.assertEqual(brokers[0].commands[0],'MODEYIELD2')
                deadline=time.monotonic()+3
                while server.return_state!='returned' and time.monotonic()<deadline:time.sleep(.005)
                self.assertEqual(server.return_state,'returned')
                self.assertEqual(server.state,'active');self.assertFalse(backend.cancelled.is_set())
                motions=[event for event in backend.events if event[1]=='NotifyPointerMotion']
                self.assertEqual(len(motions),1);self.assertEqual(motions[0][-1][-2:],(-40.,-30.))
                self.assertFalse(any(event[1] in ('NotifyPointerButton','NotifyKeyboardKeysym','NotifyPointerAxisDiscrete') for event in backend.events))
                self.assertEqual(backend.captures,1);self.assertEqual(brokers[0].commands.count('RESUME_1'),1);self.assertEqual(brokers[0].commands.count('RESUME_2'),1)
                self.assertTrue(controller.status()['active']);self.assertTrue(controller.status()['observer_alive'])
                self.assertFalse(server.return_after_quiet(controller,1));self.assertEqual(len(motions),1)
            finally:server.close_backend()


if __name__=='__main__':unittest.main()
