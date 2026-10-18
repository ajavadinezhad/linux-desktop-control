"""Independent opt-in cursor lease worker. No desktop-control operations.
Controller requires an installed theme, private state directory and active callback.
"""
import argparse,json,os,select,subprocess,sys,threading,time
from pathlib import Path
from cursor_theme import CursorThemeLease

class GioSettings:
    def __init__(self):
        import gi
        gi.require_version('Gio','2.0')
        from gi.repository import Gio
        self.settings=Gio.Settings.new('org.gnome.desktop.interface')
    def user_value(self):
        value=self.settings.get_user_value('cursor-theme')
        return None if value is None else value.unpack()
    def effective_value(self):return self.settings.get_string('cursor-theme')
    def set(self,value):
        if not self.settings.set_string('cursor-theme',value):raise RuntimeError('cursor preference write refused')
        from gi.repository import Gio
        Gio.Settings.sync()
        if self.effective_value()!=value:raise RuntimeError('cursor preference verification failed')
    def reset(self):
        self.settings.reset('cursor-theme')
        from gi.repository import Gio
        Gio.Settings.sync()
        if self.user_value() is not None:raise RuntimeError('cursor reset verification failed')

def owner_alive(pid):
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

def serve(lease,theme,owner,input_fd=0,output=None,alive=owner_alive):
    output=output or sys.stdout
    lease.enable(theme,explicit=True)
    try:
        output.write(json.dumps({'ready':True})+'\n');output.flush();pending=b''
        while True:
            if not lease.poll(owner_alive=alive(owner)):break
            readable,_,_=select.select([input_fd],[],[],.2)
            if not readable:continue
            chunk=os.read(input_fd,4096)
            if not chunk:break
            pending+=chunk
            if len(pending)>8192:raise RuntimeError('watchdog command limit')
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1);message=json.loads(line)
                if message=={'command':'close'}:return
                if message!={'command':'heartbeat'}:raise RuntimeError('unknown watchdog command')
                if not lease.heartbeat():return
    finally:
        lease.close()
        output.write(json.dumps({'closed':True})+'\n');output.flush()

class Controller:
    def __init__(self,theme,state_dir,theme_root,active,on_failure=None,launcher=subprocess.Popen,python='/usr/bin/python3'):
        self.args=[python,str(Path(__file__).resolve()),'--theme',theme,'--state',str(state_dir),'--root',str(theme_root),'--owner',str(os.getpid())]
        self.active=active;self.failure=on_failure or (lambda error:None);self.launcher=launcher;self.process=None;self.thread=None;self.stop=threading.Event();self.error=None;self.lock=threading.Lock();self.restored=None;self.closed=False;self.recovery_attempted=False;self.recovery_lock=threading.Lock()
    def _readline(self,process,timeout):
        # Worker emits bounded single writes. Read raw bytes to avoid buffered read-ahead.
        result=b'';deadline=time.monotonic()+timeout
        while len(result)<4096:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([process.stdout],[],[],remaining)[0]:raise RuntimeError('cursor watchdog response timed out')
            byte=os.read(process.stdout.fileno(),1)
            if byte==b'\n':return json.loads(result)
            if not byte:raise RuntimeError('cursor watchdog exited without response')
            result+=byte
        raise RuntimeError('cursor watchdog response oversized')
    def _send(self,message):
        with self.lock:
            payload=(json.dumps(message)+'\n').encode()
            if not select.select([],[self.process.stdin],[],.5)[1]:raise RuntimeError('cursor watchdog command timed out')
            if os.write(self.process.stdin.fileno(),payload)!=len(payload):raise RuntimeError('cursor watchdog command incomplete')
    def start(self):
        if self.process is not None:raise RuntimeError('cursor controller already started')
        if not self.active():raise RuntimeError('cursor activation requires active authorization')
        self.process=self.launcher(self.args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        try:
            os.set_blocking(self.process.stdin.fileno(),False)
            if self._readline(self.process,4)!={'ready':True}:raise RuntimeError('cursor watchdog not ready')
            self.thread=threading.Thread(target=self._heartbeat,daemon=True,name='cursor-glow-heartbeat');self.thread.start();return self
        except BaseException:
            self.close();raise
    def _heartbeat(self):
        try:
            while not self.stop.wait(.2):
                if self.process.poll() is not None:raise RuntimeError('cursor watchdog died')
                if not self.active():
                    self._send({'command':'close'});return
                self._send({'command':'heartbeat'})
        except Exception as error:
            self.error=str(error)
            try:self._recover()
            except Exception as recovery:self.error+='; recovery: '+str(recovery)
            self.failure(self.error)
    def _recover(self):
        # Only recover after the old worker is dead; never fight its exclusive lock.
        if self.process is not None and self.process.poll() is None:raise RuntimeError('watchdog still running')
        with self.recovery_lock:
            if self.recovery_attempted:
                if self.restored:return
                raise RuntimeError('cursor recovery already failed')
            self.recovery_attempted=True
            result=subprocess.run(self.args+['--recover'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=4)
            if result.returncode:raise RuntimeError('cursor startup recovery failed')
            self.restored=True
    def status(self):
        running=self.process is not None and self.process.poll() is None
        return {'active':running and self.restored is not True,'worker_running':running,'restoration_pending':self.stop.is_set() and self.restored is not True,'error':self.error,'restored':self.restored}
    def close(self):
        if self.closed:return
        self.stop.set()
        if self.thread is not None and self.thread is not threading.current_thread():self.thread.join(timeout=5)
        if self.process is None:return
        try:
            if self.process.poll() is None:
                try:self._send({'command':'close'})
                except (OSError,RuntimeError):pass
                self.process.stdin.close()
                self.process.wait(timeout=4)
            if self.process.returncode!=0:self._recover()
            else:
                if self._readline(self.process,1)!={'closed':True}:raise RuntimeError('cursor restoration acknowledgement missing')
                self.restored=True
            self.closed=True
        except Exception as error:
            self.error=str(error)
            # No forced kill: permit the independent lease deadline to restore.
            self.failure(self.error)
            raise RuntimeError('cursor restoration not confirmed: '+self.error) from error
        finally:
            if self.process.poll() is not None:
                self.process.stdin.close()
                self.process.stdout.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--theme',required=True);p.add_argument('--state',required=True);p.add_argument('--root',required=True);p.add_argument('--owner',type=int,required=True);p.add_argument('--recover',action='store_true');a=p.parse_args()
    lease=CursorThemeLease(GioSettings(),a.state,a.root)
    if a.recover:lease.recover()
    else:serve(lease,a.theme,a.owner)
if __name__=='__main__':main()
