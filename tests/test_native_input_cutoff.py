"""Socket monitor -> real Server cancellation -> real Desktop raw-UP cleanup.

Only helper protocol and portal RPC are faked. No helper, device, GI desktop,
notification, admin prompt or sharing session is used. This is not physical
takeover acceptance.
"""
import json
import tempfile
import unittest

import test_native_activity as native_fixtures
import test_window_guard as desktop_fixtures


class NativeInputCutoffTests(unittest.TestCase):
    def run_cutoff(self, action, trigger_method, token, expected_kind=None):
        server, bridge, desktop = desktop_fixtures.FullTransitionTests().make()
        # Restore the production status method, including raw release evidence.
        desktop.status = lambda: desktop_fixtures.m.Desktop.status(desktop)
        brokers = []
        with tempfile.TemporaryDirectory(prefix='native-cutoff-') as runtime:
            def launch(args, **kwargs):
                broker = native_fixtures.FakeBroker(args, mode='normal', **kwargs)
                brokers.append(broker)
                return broker
            controller = native_fixtures.m.Controller(
                active=lambda: server.state in ('opening', 'active'),
                on_activity=lambda: server.native_activity_lost(controller),
                on_fault=lambda error: server.native_activity_lost(controller, error),
                runtime_dir=runtime, launcher=launch, validator=lambda: None,
                credentials=lambda connection: (123, 0, 0), startup_timeout=1)
            server.native_activity = controller
            server.physical_takeover = True
            original_call, original_action = desktop.call, desktop.action
            cutoff, cancellation_observed, action_calls = [], [], []

            def call(interface, method, signature, arguments, **kwargs):
                original_call(interface, method, signature, arguments, **kwargs)
                if method == trigger_method and arguments[-1] == 1 and not cutoff:
                    # The down RPC has really reached the fixture portal. Hold
                    # this production action until the controller's socket
                    # reader invokes the production cancellation callback.
                    cutoff.append(len(desktop.events))
                    brokers[0].connection.sendall((token + '\n').encode('ascii'))
                    if not desktop.cancelled.wait(2):
                        raise AssertionError('Socket monitor failed to cancel active input')
                    cancellation_observed.append(True)

            def counted_action(value):
                action_calls.append(value)
                return original_action(value)

            desktop.call, desktop.action = call, counted_action
            try:
                controller.start()
                self.assertTrue(controller.status()['active'])
                request = {'id': 1, 'method': 'tools/call', 'params': {
                    'name': 'desktop_action', 'arguments': {
                        'window_observation_id': server.window_record['id'],
                        'action': action}}}
                result = server.fence_response(request, server.handle(request))['result']
                self.assertEqual(cancellation_observed, [True])
                self.assertTrue(result['isError'])
                self.assertFalse(any(item['type'] == 'image' for item in result['content']))
                receipt = json.loads(result['content'][0]['text'])
                self.assertEqual(receipt['transaction']['completed_steps'], 0)
                self.assertEqual(receipt['transaction']['input_characters_completed'], 0)
                self.assertGreater(receipt['transaction']['input_events_attempted'], 0)
                self.assertEqual(receipt['recovery']['last_result']['outcome'], 'effects_uncertain')

                after = desktop.events[cutoff[0]:]
                inputs = [event for event in after if event[1].startswith('Notify')]
                self.assertEqual(len(inputs), 1, inputs)
                self.assertEqual(inputs[0][1], trigger_method)
                self.assertEqual(inputs[0][-1][-1], 0)  # raw UP after cancellation
                self.assertFalse(any(event[1] == 'NotifyPointerMotionAbsolute' for event in after))
                self.assertTrue(desktop.portal_closed)
                self.assertEqual(desktop.status()['held_input_count'], 0)
                self.assertEqual(desktop.status()['input_release'], {
                    'attempted': 1, 'confirmed': 1, 'failed': 0})
                self.assertFalse(server.status()['active'])
                self.assertTrue(server.status()['portal_closed_confirmed'])
                self.assertFalse(server.status()['input_allowed'])
                self.assertIsNone(server.status().get('cleanup_warning'))
                self.assertTrue(bridge.closed)
                self.assertEqual(len(action_calls), 1)
                self.assertEqual(len(brokers), 1)
                self.assertEqual(brokers[0].commands.count('ARM'), 1)
                if expected_kind is not None:
                    self.assertEqual(controller.status()['terminal_reason'], 'activity')
                    self.assertEqual(controller.status()['activity_kind'], expected_kind)
                else:
                    self.assertEqual(controller.status()['terminal_reason'], 'helper-fault')
                    self.assertIn('observer fault', server.status()['physical_takeover_warning'])
            finally:
                server.close_backend()
                controller.close()
                if controller.thread is not None:
                    controller.thread.join(2)
                    self.assertFalse(controller.thread.is_alive())
                if brokers:
                    self.assertTrue(brokers[0].done.wait(2))

    def test_socket_key_activity_cuts_off_actual_typing_and_releases_key(self):
        self.run_cutoff({'type': 'text', 'focus': {'x': 40, 'y': 40},
                         'text': 'should stop before completing this text', 'text_mode': 'keysyms'},
                        'NotifyKeyboardKeysym', 'ACTIVITY_KEY', 'key')

    def test_socket_pointer_activity_cuts_off_actual_drag_and_releases_button(self):
        self.run_cutoff({'type': 'drag', 'path': [[40, 40], [60, 60], [80, 80]]},
                        'NotifyPointerButton', 'ACTIVITY_POINTER', 'pointer')

    def test_socket_helper_fault_cuts_off_actual_drag_and_releases_button(self):
        self.run_cutoff({'type': 'drag', 'path': [[40, 40], [60, 60], [80, 80]]},
                        'NotifyPointerButton', 'FAULT')
