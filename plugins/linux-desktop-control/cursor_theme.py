"""Opt-in cursor-theme lease. Importing this module never changes settings.
Adapter methods: user_value() -> str|None; effective_value() -> str;
set(value: str); reset(). Caller must disclose desktop-wide scope before enable.
"""
import fcntl, json, os, stat, tempfile, time, uuid
from pathlib import Path

class CursorThemeLease:
    def __init__(self,settings,state_dir,theme_root,clock=time.monotonic):
        self.settings=settings; self.directory=Path(state_dir);self.root=Path(theme_root).resolve();self.clock=clock;self.fd=None;self.record=None
    def _lock(self):
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        info=self.directory.stat()
        if self.directory.is_symlink() or info.st_uid!=os.getuid() or info.st_mode & 0o022:raise ValueError('unsafe state directory')
        fd=os.open(self.directory/'lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o022:raise ValueError('unsafe lock file')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:os.close(fd);raise RuntimeError('cursor theme already leased')
        self.fd=fd
    def _write(self,record):
        fd,path=tempfile.mkstemp(prefix='.journal-',dir=self.directory)
        try:
            with os.fdopen(fd,'w') as f:json.dump(record,f);f.flush();os.fsync(f.fileno())
            os.replace(path,self.directory/'journal.json')
            directory=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            if os.path.exists(path):os.unlink(path)
    def _restore(self,record):
        # Never overwrite a preference changed by the user during our lease.
        if self.settings.effective_value()==record['theme']:
            if record['original'] is None:self.settings.reset()
            else:self.settings.set(record['original'])
        (self.directory/'journal.json').unlink(missing_ok=True)
    def _recover_locked(self):
        path=self.directory/'journal.json'
        if path.exists():
            if path.is_symlink() or path.stat().st_size>4096:raise ValueError('unsafe journal')
            record=json.loads(path.read_text())
            if not isinstance(record,dict):raise ValueError('invalid journal')
            theme=record.get('theme');original=record.get('original')
            if not isinstance(theme,str) or len(theme)>512 or not theme.startswith('CodexGlow-') or '/' in theme or '\\' in theme or not (original is None or isinstance(original,str) and len(original)<=512):raise ValueError('invalid journal')
            self._restore(record)
    def recover(self):
        if self.fd is not None:raise RuntimeError('already owned')
        self._lock()
        try:self._recover_locked()
        finally:self._unlock()
    def enable(self,theme,explicit=False):
        if not explicit:raise ValueError('explicit activation required')
        if self.fd is not None or self.record is not None:raise RuntimeError('already owned or restoration pending')
        if not theme.startswith('CodexGlow-') or '/' in theme or '\\' in theme:raise ValueError('invalid unique theme')
        path=(self.root/theme).resolve()
        if path.parent!=self.root or not (path/'index.theme').is_file() or not (path/'manifest.json').is_file() or not (path/'cursors').is_dir():raise ValueError('theme not installed')
        if (path/'manifest.json').stat().st_size>4*1024*1024:raise ValueError('manifest too large')
        manifest=json.loads((path/'manifest.json').read_text())
        if not manifest or not (path/'cursors'/'left_ptr').is_file():raise ValueError('incomplete theme')
        self._lock()
        try:
            self._recover_locked()
            self.record={'theme':theme,'original':self.settings.user_value(),'owner':os.getpid(),'nonce':uuid.uuid4().hex}
            self._write(self.record) # Durable original BEFORE changing desktop preference.
            self.settings.set(theme);self.deadline=self.clock()+3
        except BaseException:
            try:
                if self.record is not None:self._restore(self.record)
                self.record=None
            finally:self._unlock()
            raise
    def heartbeat(self):
        if self.record is None:raise RuntimeError('not active')
        if self.settings.effective_value()!=self.record['theme']:
            self.close();return False
        self.deadline=self.clock()+3;return True
    def poll(self,owner_alive=True):
        if self.record is not None and (not owner_alive or self.clock()>=self.deadline):self.close();return False
        return self.record is not None
    def _unlock(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
    def close(self):
        if self.record is not None and self.fd is None:self._lock()
        try:
            if self.record is not None:self._restore(self.record);self.record=None
        finally:self._unlock()
