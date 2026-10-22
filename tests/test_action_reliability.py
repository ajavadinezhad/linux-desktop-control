"""Validation failures must be informative, private and free of input effects."""
import json
import unittest
import test_control
import test_context_recovery as context_fixture

m = test_control.m


class ActionReliabilityTests(unittest.TestCase):
    make = context_fixture.ContextRecoveryTests.make
    request = context_fixture.ContextRecoveryTests.request

    def test_bad_shapes_keep_sharing_and_return_a_new_observation(self):
        for action in ({'type':'move','dx':20,'dy':10},
                       {'type':'click','x':20},
                       {'type':'sequence','steps':[{'type':'keys','keys':['Ctrl','l']}]}):
            with self.subTest(action=action):
                s,b,d = self.make()
                old = s.window_record['id']
                result = self.request(s,'desktop_action',{'window_observation_id':old,'action':action})
                self.assertFalse(result.get('isError',False),result)
                status = json.loads(result['content'][0]['text'])
                self.assertIn('action_argument_error',status)
                self.assertTrue(s.status()['active'])
                self.assertNotEqual(s.window_record['id'],old)
                self.assertEqual(d.events,[])
                self.assertEqual(status['recovery']['last_result']['input_events_attempted'],0)
                corrected = {'window_observation_id':s.window_record['id'],
                    'action':{'type':'move','x':50,'y':50,'seconds':0}}
                if status['recovery']['observation_id']:
                    corrected['recovery_observation_id'] = status['recovery']['observation_id']
                followup = self.request(s,'desktop_action',corrected)
                self.assertFalse(followup.get('isError',False),followup)
                self.assertTrue(d.events)
                self.assertTrue(s.status()['active'])

    def test_oversized_ascii_refused_before_any_key_or_click(self):
        s,b,d = self.make()
        result = self.request(s,'desktop_action',{'window_observation_id':s.window_record['id'],
            'action':{'type':'sequence','steps':[{'type':'click','x':50,'y':50},
                {'type':'text','text':'a'*900,'text_mode':'keysyms'}]}})
        self.assertFalse(result.get('isError',False),result)
        status = json.loads(result['content'][0]['text'])
        self.assertEqual(status['action_argument_error']['code'],'input-budget-exceeded')
        self.assertEqual(d.events,[])
        self.assertTrue(s.status()['active'])

    def test_invalid_top_level_flag_needs_same_fresh_context_to_retain(self):
        for changed,unknown in ((False,False),(True,False),(False,True)):
            with self.subTest(changed=changed,unknown=unknown):
                s,b,d = self.make()
                token = s.window_record['id']
                if changed:b.value.update(window_id='another-app',epoch=11)
                result = self.request(s,'desktop_action',{'window_observation_id':'0'*32 if unknown else token,
                    'focus_transition':'yes','action':{'type':'click','x':50,'y':50}})
                self.assertFalse(any(e[1].startswith('Notify') for e in d.events))
                if not changed and not unknown:
                    self.assertFalse(result.get('isError',False),result)
                    self.assertTrue(s.status()['active'])
                    self.assertIn('action_argument_error',json.loads(result['content'][0]['text']))
                else:
                    self.assertTrue(result.get('isError',False),result)
                    self.assertFalse(any(c['type']=='image' for c in result['content']))

    def test_unknown_key_and_generic_errors_never_echo_private_values(self):
        for message in ('Unknown key: secret-password', 'secret-password'):
            diagnostic = m.action_argument_diagnostic(ValueError(message))
            self.assertNotIn('secret-password',json.dumps(diagnostic))

    def test_short_text_remains_admitted_and_schema_explains_pointer_move(self):
        d = test_control.Tests.backend(self)
        d.validate_action({'type':'sequence','steps':[{'type':'click','x':50,'y':50},
            {'type':'text','text':'a'*400,'text_mode':'keysyms'}]})
        self.assertIn('logical',m.ACTION_SCHEMA['properties']['x']['description'])
        self.assertIn('pointer',m.ACTION_SCHEMA['properties']['type']['description'])


if __name__ == '__main__': unittest.main()
