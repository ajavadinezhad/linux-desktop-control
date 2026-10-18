import importlib.util,pathlib,json,unittest
p=pathlib.Path(__file__).resolve().parents[1]/'examples/consent_first.py';spec=importlib.util.spec_from_file_location('consent_example',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Client:
 def __init__(self,result):self.result=result;self.calls=[]
 def call(self,name,args):self.calls.append((name,args));return self.result
class ConsentFirstTests(unittest.TestCase):
 def result(self,active=True,image=True):return {'content':[{'type':'text','text':json.dumps({'active':active,'window_observation':{'available':True,'observation_id':'x'*32}})}]+([{'type':'image','data':'fixture'}] if image else [])}
 def test_denied_cancelled_or_missing_pixels_never_launch_application(self):
  for result in [self.result(False),self.result(image=False),{'isError':True,'content':[]}]:
   c=Client(result)
   with self.assertRaises(Exception):m.begin(c,lambda _:True)
   self.assertEqual([name for name,_ in c.calls],['desktop_start','desktop_close'])
 def test_uninspected_consent_screen_cannot_authorize_launch(self):
  c=Client(self.result())
  with self.assertRaises(RuntimeError):m.begin(c,lambda _:False)
  self.assertFalse(any(name=='desktop_action' for name,_ in c.calls))
 def test_only_after_consent_and_inspection_can_observed_gui_launch_once(self):
  c=Client(self.result());inspected=[];desktop=m.begin(c,lambda r:inspected.append(True) or True)
  self.assertEqual([name for name,_ in c.calls],['desktop_start']);desktop.open_launcher()
  self.assertTrue(inspected);self.assertEqual(c.calls[-1],('desktop_action',{'window_observation_id':'x'*32,'focus_transition':True,'action':{'type':'keys','keys':['Super']}}))
  with self.assertRaises(RuntimeError):desktop.open_launcher()
  self.assertEqual(len(c.calls),2)
