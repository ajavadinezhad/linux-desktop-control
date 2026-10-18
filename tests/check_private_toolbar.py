#!/usr/bin/python3
"""Fallback isolated Shell test with a private broker; never uses the host bus."""
import os,pathlib,signal,socket,subprocess,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='codex-private-bus-') as folder:
 base=pathlib.Path(folder);config=base/'bus.conf'
 config.write_text('<busconfig><type>session</type><auth>EXTERNAL</auth><policy context="default"><allow user="*"/><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>')
 sock=socket.socket(socket.AF_UNIX);sock.bind(str(base/'bus'));sock.listen(128)
 broker=os.fork()
 if broker==0:
  os.dup2(sock.fileno(),3);os.set_inheritable(3,True)
  os.environ.update(LISTEN_FDS='1',LISTEN_PID=str(os.getpid()))
  os.execv('/usr/bin/dbus-broker-launch',['dbus-broker-launch','--scope','user','--config-file',str(config)])
 sock.close();service=None;test=None
 try:
  env=dict(os.environ,DBUS_SESSION_BUS_ADDRESS='unix:path='+str(base/'bus'),NO_AT_BRIDGE='1')
  service=subprocess.Popen(['/usr/bin/gjs','-m','/usr/share/gnome-shell/org.gnome.Shell.Extensions'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  test=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/check_toolbar_shell.py')],cwd=ROOT,env=env,start_new_session=True)
  code=test.wait(timeout=60)
 finally:
  if test:
   try:os.killpg(test.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:test.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(test.pid,signal.SIGKILL);test.wait()
  if service:
   service.terminate()
   try:service.wait(timeout=5)
   except subprocess.TimeoutExpired:service.kill();service.wait()
  try:os.kill(broker,signal.SIGTERM)
  except ProcessLookupError:pass
  os.waitpid(broker,0)
 raise SystemExit(code)
