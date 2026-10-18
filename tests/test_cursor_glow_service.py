import importlib.util,io,json,os,signal,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PLUGIN=ROOT/'plugins/linux-desktop-control';sys.path.insert(0,str(PLUGIN))
import cursor_glow_service as service
class ServiceTests(unittest.TestCase):
 def test_fake_lease_owner_loss_and_eof(self):
  class Lease:
   def __init__(self):self.closed=False;self.enabled=False
   def enable(self,*a,**k):self.enabled=True
   def close(self):self.closed=True
   def poll(self,owner_alive=True):return owner_alive
  for alive in (True,False):
   r,w=os.pipe();os.close(w);lease=Lease();out=io.StringIO()
   try:service.serve(lease,'CodexGlow-test',123,input_fd=r,output=out,alive=lambda p:alive)
   finally:os.close(r)
   self.assertTrue(lease.enabled);self.assertTrue(lease.closed);self.assertEqual(out.getvalue().splitlines(),['{"ready": true}','{"closed": true}'])
 def spawn(self,mode):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);theme=root/'CodexGlow-test';(theme/'cursors').mkdir(parents=True);(theme/'index.theme').write_text('x');(theme/'manifest.json').write_text('{"x":1}');(theme/'cursors/left_ptr').write_text('x');state=root/'state';value=root/'value';value.write_text('Original')
  code='''import sys,json,os\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom cursor_theme import CursorThemeLease\nfrom cursor_glow_service import serve\nroot=Path(sys.argv[2]);value=root/'value'\nclass S:\n def user_value(self):return value.read_text()\n def effective_value(self):return value.read_text()\n def set(self,v):value.write_text(v)\n def reset(self):value.write_text('Default')\nlease=CursorThemeLease(S(),root/'state',root)\nserve(lease,'CodexGlow-test',os.getppid(),alive=(lambda p:False) if sys.argv[3]=='dead' else (lambda p:True))\n'''
  p=subprocess.Popen([sys.executable,'-u','-c',code,str(PLUGIN),str(root),mode],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.addCleanup(lambda:p.poll() is None and p.kill());self.assertEqual(json.loads(p.stdout.readline()),{'ready':True});return p,value
 def finish(self,p,value,expected='Original'):
  self.assertEqual(p.wait(timeout=5),0,p.stderr.read());self.assertEqual(value.read_text(),expected);self.assertEqual(json.loads(p.stdout.readline()),{'closed':True});p.stdout.close();p.stderr.close()
 def test_subprocess_eof_restores(self):
  p,value=self.spawn('eof');p.stdin.close();self.finish(p,value)
 def test_subprocess_dead_owner_restores(self):
  p,value=self.spawn('dead');p.stdin.close();self.finish(p,value)
 def test_subprocess_deadline_restores_without_parent_heartbeat(self):
  p,value=self.spawn('timeout');self.finish(p,value);p.stdin.close()
 def test_subprocess_preserves_user_change_on_close(self):
  p,value=self.spawn('user');value.write_text('UserChoice');p.stdin.write(b'{"command":"close"}\n');p.stdin.flush();self.finish(p,value,'UserChoice');p.stdin.close()
 def test_controller_fake_worker_heartbeat_and_close(self):
  code="import sys,json;print(json.dumps({'ready':True}),flush=True)\nfor line in sys.stdin:\n if json.loads(line)=={'command':'close'}:break\nprint(json.dumps({'closed':True}),flush=True)"
  def launcher(args,**kwargs):return subprocess.Popen([sys.executable,'-u','-c',code],**kwargs)
  failures=[];c=service.Controller('CodexGlow-x','/tmp/unused','/tmp',lambda:True,on_failure=failures.append,launcher=launcher)
  c.start();self.assertTrue(c.status()['active']);time.sleep(.25);c.close();c.close();self.assertTrue(c.status()['restored']);self.assertFalse(c.status()['active']);self.assertEqual(failures,[])
 def test_full_command_pipe_is_bounded(self):
  from types import SimpleNamespace
  r,w=os.pipe();os.set_blocking(w,False);stream=os.fdopen(w,'wb',buffering=0)
  try:
   while True:
    try:os.write(w,b'x'*4096)
    except BlockingIOError:break
   c=service.Controller('CodexGlow-x','/tmp/unused','/tmp',lambda:True);c.process=SimpleNamespace(stdin=stream);start=time.monotonic()
   with self.assertRaisesRegex(RuntimeError,'command timed out'):c._send({'command':'heartbeat'})
   self.assertLess(time.monotonic()-start,2)
  finally:stream.close();os.close(r)
 def test_controller_requires_active(self):
  c=service.Controller('CodexGlow-x','/tmp/unused','/tmp',lambda:False)
  with self.assertRaises(RuntimeError):c.start()
  self.assertFalse(c.status()['active'])
class CrashRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.value=self.root/'value';self.value.write_text('Original')
  theme=self.root/'CodexGlow-test';(theme/'cursors').mkdir(parents=True);(theme/'index.theme').write_text('x');(theme/'manifest.json').write_text('{"x":1}');(theme/'cursors/left_ptr').write_text('x')
  self.worker=self.root/'fake_worker.py'
  self.worker.write_text("""import argparse,os,sys
from pathlib import Path
sys.path.insert(0,"""+repr(str(PLUGIN))+""")
from cursor_theme import CursorThemeLease
from cursor_glow_service import serve
p=argparse.ArgumentParser();p.add_argument('--theme');p.add_argument('--state');p.add_argument('--root');p.add_argument('--owner',type=int);p.add_argument('--recover',action='store_true');a=p.parse_args();value=Path(a.root)/'value'
class Settings:
 def user_value(self):return value.read_text()
 def effective_value(self):return value.read_text()
 def set(self,v):
  tmp=value.with_suffix('.tmp');tmp.write_text(v);os.replace(tmp,value)
 def reset(self):self.set('Default')
lease=CursorThemeLease(Settings(),a.state,a.root)
if a.recover:lease.recover()
else:serve(lease,a.theme,a.owner)
""")
 def controller(self,failures):
  c=service.Controller('CodexGlow-test',self.root/'state',self.root,lambda:True,on_failure=failures.append,python=sys.executable);c.args[1]=str(self.worker);return c
 def wait_value(self,value,timeout=5):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   if self.value.read_text()==value:return
   time.sleep(.02)
  self.fail('fake preference did not become '+value)
 def test_actual_owner_sigkill_independent_worker_restores(self):
  code="""import sys,time
sys.path.insert(0,sys.argv[1])
from cursor_glow_service import Controller
c=Controller('CodexGlow-test',sys.argv[2]+'/state',sys.argv[2],lambda:True,python=sys.executable);c.args[1]=sys.argv[3];c.start();print(c.process.pid,flush=True)
while True:time.sleep(1)
"""
  owner=subprocess.Popen([sys.executable,'-u','-c',code,str(PLUGIN),str(self.root),str(self.worker)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.addCleanup(lambda:owner.poll() is None and owner.kill())
  worker_pid=int(owner.stdout.readline());self.assertEqual(self.value.read_text(),'CodexGlow-test')
  owner.kill();self.assertEqual(owner.wait(timeout=3),-signal.SIGKILL)
  self.wait_value('Original');self.assertFalse((self.root/'state/journal.json').exists());owner.stdout.close();owner.stderr.close()
 def test_actual_worker_sigkill_controller_recovers_once(self):
  failures=[];c=self.controller(failures).start();self.assertEqual(self.value.read_text(),'CodexGlow-test');c.process.kill()
  deadline=time.monotonic()+6
  while not failures and time.monotonic()<deadline:time.sleep(.02)
  self.assertTrue(failures);self.assertTrue(c.status()['restored']);self.assertFalse(c.status()['active']);self.wait_value('Original');self.assertFalse((self.root/'state/journal.json').exists());c.close()
 def test_actual_worker_sigkill_preserves_user_change(self):
  failures=[];c=self.controller(failures).start();entered=threading.Event();proceed=threading.Event();recover=c._recover
  def gated_recover():
   entered.set()
   if not proceed.wait(3):raise RuntimeError('test recovery gate timed out')
   recover()
  c._recover=gated_recover;c.process.kill();self.assertTrue(entered.wait(3));self.value.write_text('UserChoice');proceed.set()
  deadline=time.monotonic()+6
  while not failures and time.monotonic()<deadline:time.sleep(.02)
  self.assertTrue(failures);self.assertTrue(c.status()['restored']);self.assertEqual(self.value.read_text(),'UserChoice');c.close()

if __name__=='__main__':unittest.main()
