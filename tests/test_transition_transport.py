"""Actual reader/worker queue coverage with production action dispatch."""
import io
import json
import os
import threading
import time
import unittest
import types
import test_window_guard as fixtures


class Output(io.StringIO):
    def __init__(self):
        super().__init__()
        self.changed = threading.Condition()

    def write(self, value):
        with self.changed:
            result = super().write(value)
            self.changed.notify_all()
            return result

    def reply(self, request_id):
        deadline = time.monotonic() + 4
        with self.changed:
            while True:
                for line in self.getvalue().splitlines():
                    value = json.loads(line)
                    if value.get('id') == request_id:
                        return value
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError('No transport response for ' + str(request_id))
                self.changed.wait(remaining)


class Harness:
    def __init__(self):
        self.server, self.bridge, self.backend = fixtures.FullTransitionTests().make()
        self.observation_id = self.server.window_record['id']
        self.backend.loop = types.SimpleNamespace(quit=lambda: None)
        self.transport = fixtures.m.StdioTransport(self.server)
        r, w = os.pipe()
        self.reader, self.writer = os.fdopen(r, 'r'), os.fdopen(w, 'w')
        self.output = Output()
        self.thread = threading.Thread(target=self.transport.run,
                                       args=(self.reader, self.output), daemon=True)
        self.thread.start()

    def send(self, request_id, name, arguments=None):
        self.writer.write(json.dumps({'id': request_id, 'method': 'tools/call',
                                     'params': {'name': name, 'arguments': arguments or {}}}) + '\n')
        self.writer.flush()

    def action(self, request_id, action):
        self.send(request_id, 'desktop_action', {
            'window_observation_id': self.observation_id,
            'focus_transition': True, 'action': action})

    def close(self):
        self.writer.close()
        self.thread.join(2)
        self.reader.close()
        if self.thread.is_alive():
            raise AssertionError('Transport failed to shut down')


class TransitionTransportTests(unittest.TestCase):
    def test_approach_takeover_invalidates_already_queued_action_and_start(self):
        h = Harness()
        entered, release = threading.Event(), threading.Event()
        queued_action, queued_start = threading.Event(), threading.Event()
        original_call, original_action = h.backend.call, h.backend.action
        calls, starts = [], []
        original_put = h.transport.pending.put

        def put(item, *args, **kwargs):
            original_put(item, *args, **kwargs)
            if item is not None:
                request = item[0]
                if request.get('id') == 2:
                    queued_action.set()
                if request.get('id') == 3:
                    queued_start.set()

        def call(iface, method, signature, args, **kwargs):
            original_call(iface, method, signature, args, **kwargs)
            if method == 'NotifyPointerMotion' and not entered.is_set():
                entered.set()
                if not release.wait(2):
                    raise RuntimeError('Test queue did not become ready')
                h.bridge.value.update(epoch=11, window_id='human-app')

        def action(value):
            calls.append(value)
            return original_action(value)

        def start():
            starts.append(True)
            raise AssertionError('Stale queued start reached backend')

        h.transport.pending.put = put
        h.backend.call, h.backend.action, h.backend.start = call, action, start
        try:
            h.action(1, {'type': 'click', 'x': 100, 'y': 100})
            self.assertTrue(entered.wait(1))
            h.action(2, {'type': 'click', 'x': 120, 'y': 120})
            h.send(3, 'desktop_start')
            self.assertTrue(queued_action.wait(1))
            self.assertTrue(queued_start.wait(1))
            release.set()
            for request_id in (1, 2, 3):
                reply = h.output.reply(request_id)['result']
                self.assertTrue(reply['isError'])
                self.assertFalse(any(c['type'] == 'image' for c in reply['content']))
            self.assertEqual(len(calls), 1)
            self.assertEqual(starts, [])
            self.assertEqual(h.backend.held, [])
            self.assertTrue(h.backend.portal_closed)
            self.assertFalse(h.server.status()['active'])
            self.assertTrue(h.bridge.closed)
            self.assertFalse(any(e[1] == 'NotifyPointerButton' and e[-1][-1] == 1
                                 for e in h.backend.events))
        finally:
            release.set()
            h.close()

    def test_save_chord_returns_native_dialog_without_replaying_input(self):
        h = Harness()
        original = h.backend.call

        def call(iface, method, signature, args, **kwargs):
            original(iface, method, signature, args, **kwargs)
            if method == 'NotifyKeyboardKeysym' and args[-2:] == (ord('s'), 1):
                h.bridge.value.update(epoch=11, window_id='native-save-dialog')

        h.backend.call = call
        try:
            h.action(1, {'type': 'keys', 'keys': ['Ctrl', 's']})
            reply = h.output.reply(1)['result']
            self.assertFalse(reply.get('isError', False))
            self.assertTrue(any(c['type'] == 'image' for c in reply['content']))
            self.assertEqual(h.server.window_record['context']['window_id'], 'native-save-dialog')
            events = [(e[-1][-2], e[-1][-1]) for e in h.backend.events
                      if e[1] == 'NotifyKeyboardKeysym']
            self.assertEqual(events, [(0xffe3, 1), (ord('s'), 1), (ord('s'), 0), (0xffe3, 0)])
            self.assertEqual(h.backend.held, [])
            h.send(2, 'desktop_close')
            closed = json.loads(h.output.reply(2)['result']['content'][0]['text'])
            self.assertFalse(closed['active'])
            self.assertTrue(closed['portal_closed_confirmed'])
        finally:
            h.close()
