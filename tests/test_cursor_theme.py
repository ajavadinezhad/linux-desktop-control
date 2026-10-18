import importlib.util,json,struct,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
lease=load('cursor_theme',ROOT/'plugins/linux-desktop-control/cursor_theme.py')
build=load('cursor_build',ROOT/'cursor-theme/build.py')
class Settings:
 def __init__(self,value=None):self.value=value;self.calls=[]
 def user_value(self):return self.value
 def effective_value(self):return self.value or 'Yaru'
 def set(self,v):self.calls.append(v);self.value=v
 def reset(self):self.calls.append(None);self.value=None
class CursorThemeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name);self.name='CodexGlow-test';p=self.path/self.name;(p/'cursors').mkdir(parents=True);(p/'cursors/left_ptr').write_bytes(b'test');(p/'index.theme').write_text('x');(p/'manifest.json').write_text('{"x":1}');self.settings=Settings();self.now=0
 def new(self):return lease.CursorThemeLease(self.settings,self.path/'state',self.path,lambda:self.now)
 def test_explicit_and_restore_unset(self):
  a=self.new()
  with self.assertRaises(ValueError):a.enable(self.name)
  a.enable(self.name,explicit=True);self.assertEqual(self.settings.value,self.name);a.close();self.assertIsNone(self.settings.value)
 def test_exclusive_and_preserve_user_change(self):
  a=self.new();a.enable(self.name,explicit=True)
  with self.assertRaises(RuntimeError):self.new().enable(self.name,explicit=True)
  self.settings.value='UserTheme';self.assertFalse(a.heartbeat());self.assertEqual(self.settings.value,'UserTheme')
 def test_lease_expiry_owner_loss_and_recovery(self):
  a=self.new();self.settings.value='Original';a.enable(self.name,explicit=True);self.now=4;self.assertFalse(a.poll());self.assertEqual(self.settings.value,'Original')
  a.enable(self.name,explicit=True);a._unlock() # Simulated process death releases kernel lock, leaves journal.
  self.new().recover();self.assertEqual(self.settings.value,'Original')
  a.record=None
  a.enable(self.name,explicit=True);self.assertFalse(a.poll(owner_alive=False));self.assertEqual(self.settings.value,'Original')
 def test_journal_failure_never_sets_theme_and_unlocks(self):
  a=self.new()
  def fail(record):raise OSError('journal disk failure')
  a._write=fail
  with self.assertRaisesRegex(OSError,'journal disk failure'):a.enable(self.name,explicit=True)
  self.assertEqual(self.settings.calls,[]);self.assertIsNone(a.fd)
  b=self.new();b.enable(self.name,explicit=True);b.close()
 def test_mutating_write_and_restore_failure_retains_recoverable_journal(self):
  self.settings.value='Original';a=self.new();original_set=self.settings.set
  def fail(value):
   self.settings.value=value
   raise OSError('settings temporarily unavailable')
  self.settings.set=fail
  with self.assertRaises(OSError):a.enable(self.name,explicit=True)
  self.assertIsNone(a.fd);self.assertTrue((self.path/'state/journal.json').exists())
  # Simulate theme still ours when the settings daemon becomes available.
  self.settings.value=self.name;self.settings.set=original_set
  b=self.new();b.recover();self.assertEqual(self.settings.value,'Original');self.assertFalse((self.path/'state/journal.json').exists())
  a.record=None
 def test_recovery_refuses_live_owner_and_corrupt_journal(self):
  a=self.new();a.enable(self.name,explicit=True)
  with self.assertRaises(RuntimeError):self.new().recover()
  self.assertEqual(self.settings.value,self.name);a.close()
  journal=self.path/'state/journal.json';journal.write_text('[]')
  with self.assertRaises(ValueError):self.new().recover()
  self.assertEqual(self.settings.calls,[self.name,None]);journal.unlink()
 def test_enable_recovers_and_snapshots_under_one_lock(self):
  a=self.new();a._lock();a._write({'theme':self.name,'original':'Original'});a._unlock();self.settings.value=self.name
  b=self.new();b.enable(self.name,explicit=True)
  self.assertEqual(b.record['original'],'Original');b.close();self.assertEqual(self.settings.value,'Original')
 def test_geometry_hotspot_animation_and_nonblank(self):
  w=h=8;pixels=bytearray(w*h*4);pixels[4*(3*w+3):4*(3*w+3)+4]=bytes((255,255,255,255))
  data=struct.pack('<7I',build.MAGIC,16,0x10000,1,build.IMAGE,24,28)+struct.pack('<9I',36,build.IMAGE,24,1,w,h,3,3,40)+pixels
  result,frames=build.transform(data);self.assertEqual(result[:64],data[:64]);self.assertEqual(frames,[dict(size=24,width=8,height=8,hotspot=[3,3],delay=40)]);self.assertNotEqual(result[64:],data[64:]);self.assertEqual(result[64+4*(3*w+3):64+4*(3*w+3)+4],bytes((255,255,255,255)))
  with self.assertRaises(ValueError):build.transform(data[:64]+bytes(w*h*4))
  with self.assertRaises(ValueError):build.transform(data[:-1])
if __name__=='__main__':unittest.main()
