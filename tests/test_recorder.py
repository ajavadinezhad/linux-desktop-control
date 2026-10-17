import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
p=pathlib.Path(__file__).resolve().parents[1]/'demo/record.py';spec=importlib.util.spec_from_file_location('recorder_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RecorderTests(unittest.TestCase):
 def args(self,root,*extra):return m.parse_args(['--output',str(root/'demo.webm'),'--stop-file',str(root/'stop'),*extra])
 def test_defaults_preserve_monitor_panel_and_native_width(self):
  with tempfile.TemporaryDirectory() as root:
   a=self.args(pathlib.Path(root));self.assertEqual(a.crop_top,0);self.assertEqual(a.max_width,3440)
 def test_constructor_failure_leaves_no_empty_video_and_reports_failure(self):
  with tempfile.TemporaryDirectory() as root:
   a=self.args(pathlib.Path(root))
   def fail(args):raise RuntimeError('no display bus')
   with self.assertRaisesRegex(RuntimeError,'no display'):m.record(a,factory=fail)
   self.assertFalse(a.output.exists());self.assertEqual(json.loads(a.status_file.read_text())['state'],'failed')
 def test_failed_recording_closes_session_and_keeps_nonempty_evidence(self):
  with tempfile.TemporaryDirectory() as root:
   a=self.args(pathlib.Path(root));closed=[]
   class Fake:
    def __init__(self,args):self.done=None
    def run(self):a.output.write_bytes(b'partial');raise RuntimeError('capture failed')
    def close(self):closed.append(True)
   with patch.object(m.signal,'signal'):
    with self.assertRaises(RuntimeError):m.record(a,factory=Fake)
   self.assertEqual(closed,[True]);self.assertEqual(a.output.read_bytes(),b'partial');self.assertFalse(json.loads(a.status_file.read_text())['recording'])
 def test_status_is_atomic_private_and_reports_remaining_time(self):
  with tempfile.TemporaryDirectory() as root:
   a=self.args(pathlib.Path(root));m.write_status(a,recording=True,remaining_seconds=3);m.write_status(a,recording=False,stop_reason='time_limit')
   self.assertEqual(json.loads(a.status_file.read_text())['stop_reason'],'time_limit');self.assertEqual(a.status_file.stat().st_mode&0o777,0o600)
   self.assertEqual(list(pathlib.Path(root).glob('.*')),[])
 def test_colliding_existing_and_invalid_paths_are_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   root=pathlib.Path(root)
   for extra in (['--status-file',str(root/'stop')],['--seconds','181'],['--region','0','0','1','2']):
    with patch('sys.stderr'):
     with self.assertRaises(SystemExit):self.args(root,*extra)
   (root/'demo.webm').write_bytes(b'keep')
   with patch('sys.stderr'):
    with self.assertRaises(SystemExit):self.args(root)
   self.assertEqual((root/'demo.webm').read_bytes(),b'keep')
if __name__=='__main__':unittest.main()
