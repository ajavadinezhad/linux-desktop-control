"""Cursor startup cancellation using isolated protocol workers, never settings."""
import pathlib
import subprocess
import sys
import threading
import unittest

PLUGIN = pathlib.Path(__file__).resolve().parents[1] / 'plugins/linux-desktop-control'
sys.path.insert(0, str(PLUGIN))
import cursor_glow_service as service

WORKER = """import json,sys
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
    if json.loads(line)=={'command':'close'}:break
print(json.dumps({'closed':True}),flush=True)
"""


class ActivationBoundaryTests(unittest.TestCase):
    def controller(self, active):
        children = []
        def launch(args, **kwargs):
            child = subprocess.Popen([sys.executable, '-u', '-c', WORKER], **kwargs)
            children.append(child)
            return child
        controller = service.Controller('CodexGlow-test', '/tmp/unused', '/tmp', active, launcher=launch)
        def cleanup():
            for child in children:
                if child.poll() is None:
                    child.kill(); child.wait(timeout=3)
                for stream in (child.stdin, child.stdout):
                    if stream is not None: stream.close()
        self.addCleanup(cleanup)
        return controller, children

    def test_close_before_start_never_launches(self):
        controller, children = self.controller(lambda: True)
        controller.close()
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            controller.start()
        self.assertEqual(children, [])
        self.assertTrue(controller.closed)
        self.assertTrue(controller.status()['restored'])
        self.assertFalse(controller.status()['active'])

    def test_authorization_revoked_during_ready_closes_child(self):
        authorized = [True]
        controller, children = self.controller(lambda: authorized[0])
        read = controller._readline
        def revoke(*args):
            reply = read(*args)
            if reply == {'ready': True}: authorized[0] = False
            return reply
        controller._readline = revoke
        with self.assertRaisesRegex(RuntimeError, 'active authorization'):
            controller.start()
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].poll(), 0)
        self.assertTrue(controller.closed)
        self.assertTrue(controller.status()['restored'])
        self.assertIsNone(controller.thread)

    def test_close_while_ready_pending_is_serialized_and_never_activates(self):
        controller, children = self.controller(lambda: True)
        ready = threading.Event(); proceed = threading.Event()
        read = controller._readline
        def hold(*args):
            reply = read(*args)
            if reply == {'ready': True}:
                ready.set()
                if not proceed.wait(3): raise RuntimeError('test gate timed out')
            return reply
        controller._readline = hold
        errors = []
        def start():
            try: controller.start()
            except Exception as error: errors.append(error)
        starter = threading.Thread(target=start)
        starter.start(); self.assertTrue(ready.wait(3))
        closer = threading.Thread(target=controller.close)
        closer.start(); self.assertTrue(controller.stop.wait(1))
        proceed.set(); starter.join(3); closer.join(3)
        self.assertFalse(starter.is_alive()); self.assertFalse(closer.is_alive())
        self.assertEqual(len(errors), 1); self.assertIn('cancelled', str(errors[0]))
        self.assertEqual(children[0].poll(), 0)
        self.assertTrue(controller.status()['restored'])
        self.assertIsNone(controller.thread)

    def test_authorization_callback_cancellation_never_launches(self):
        controller, children = self.controller(lambda: True)
        controller.active = lambda: (controller.close(), True)[1]
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            controller.start()
        self.assertEqual(children, [])


if __name__ == '__main__': unittest.main()
