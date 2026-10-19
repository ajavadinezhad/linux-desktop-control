"""ARM boundary regression: fake transport only, no socket bind/helper/device access.
Run directly with /usr/bin/python3 tests/test_native_arm_boundary.py.
Post-read deadline and stop fences must prevent readiness publication.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit_native',ROOT/'plugins/linux-desktop-control/native_activity.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def reproduce(mode):
    clock=[100.0];authorized=[True]
    peer=Mock();listener=Mock();listener.accept.return_value=(peer,None)
    process=Mock();process.poll.return_value=None;process.wait.return_value=0
    with tempfile.TemporaryDirectory() as directory:
        controller=m.Controller(lambda:authorized[0],lambda:None,lambda error:None,runtime_dir=directory,validator=lambda:None,launcher=lambda *a,**k:process,credentials=lambda c:(123,0,0))
        controller._send=lambda token:None
        controller._wait_calibrated=lambda:None
        replies=iter(('READY','CALIBRATING','ARMED'))
        def read(timeout):
            token=next(replies)
            if token=='ARMED':
                if mode=='late':clock[0]+=1.01
                elif mode=='revoked':authorized[0]=False
                elif mode=='closed':controller.close()
                elif mode=='reentrant':
                    calls=[0]
                    def authorization():
                        calls[0]+=1
                        if calls[0]==2:controller.close()
                        return True
                    controller.active=authorization
                else:controller.stop.set()
            return token
        controller._read=read
        with patch.object(m.os,'chmod'),patch.object(m.socket,'socket',return_value=listener),patch.object(m.select,'select',return_value=([listener],[],[])),patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),patch.object(m.threading,'Thread'):
            with unittest.TestCase().assertRaises(m.NativeFailure):
                controller.start()
            assert controller.calibration_verified is False
            assert controller.ready is False
            assert controller.thread is None
        controller.close()

class ArmBoundaryTests(unittest.TestCase):
    def test_late_arm_acknowledgement_refused(self):reproduce('late')
    def test_stop_during_arm_read_refused(self):reproduce('stopped')
    def test_authorization_revoked_during_arm_read_refused(self):reproduce('revoked')
    def test_close_during_arm_read_cannot_publish_readiness(self):reproduce('closed')
    def test_authorization_callback_closes_reentrantly_before_publication(self):reproduce('reentrant')

if __name__=='__main__':unittest.main()
