"""Focus metadata cannot change the primitive or evade batch prevalidation."""
import unittest
import test_control


class FocusBoundaryTests(unittest.TestCase):
    def test_extra_focus_fields_are_rejected_before_any_primitive(self):
        for extra in ({'type':'text','text':'unexpected'}, {'button':'right'},
                      {'count':3}, {'steps':[]}, {'x_extra':1}):
            with self.subTest(extra=extra):
                backend=test_control.Tests().backend()
                backend.wait_interruptibly=lambda _:None
                primitives=[]
                backend._primitive=primitives.append
                with self.assertRaises(ValueError):
                    backend.action({'type':'text','text':'intended',
                                    'focus':{'x':40,'y':50,**extra}})
                self.assertEqual(primitives,[])
                self.assertEqual(backend.events,[])

    def test_invalid_later_focus_rejects_entire_sequence_before_first_click(self):
        backend=test_control.Tests().backend()
        primitives=[]
        backend._primitive=primitives.append
        with self.assertRaises(ValueError):
            backend.action({'type':'sequence','steps':[
                {'type':'click','x':40,'y':50},
                {'type':'text','text':'intended',
                 'focus':{'x':40,'y':50,'type':'text','text':'unexpected'}}]})
        self.assertEqual(primitives,[])
        self.assertEqual(backend.events,[])


if __name__=='__main__':unittest.main()
