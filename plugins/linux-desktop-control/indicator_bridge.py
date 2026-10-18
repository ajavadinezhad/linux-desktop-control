"""Read-only foreground observer and passive label. No input or human-control signals."""
import json,threading,uuid
from gi.repository import Gio,GLib
NAME='org.gnome.Shell';PATH='/org/codex/DesktopIndicator';IFACE='org.codex.DesktopIndicator'
class IndicatorBridge:
 def __init__(self,status,bus=None,on_failure=None):
  self.on_failure=on_failure;self.status=status;self.bus=bus;self.nonce=uuid.uuid4().hex;self.owner=None;self.bound=False;self.closed=threading.Event();self.subscription=None;self.armed=None
  self._physical_lock=threading.Lock();self._physical_enabled=False;self._physical_callback=None;self._physical_generation=0;self._physical_pending=False;self._physical_worker=False
 def call(self,method,signature,args):return self.bus.call_sync(self.owner,PATH,IFACE,method,GLib.Variant(signature,args),None,Gio.DBusCallFlags.NONE,1000,None).unpack()
 def preflight(self):
  if self.bus is None:self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
  self.owner=self.bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner',GLib.Variant('(s)',(NAME,)),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
  diagnostics=json.loads(self.call('GetDiagnostics','()',())[0])
  if diagnostics.get('protocol_version')!=2 or diagnostics.get('pointer_snapshot') is not True:raise RuntimeError('Foreground observer protocol 2 with fresh pointer snapshots is not loaded. Save work and log out/in manually before a new session. No sharing requested.')
 def start(self):
  self.preflight()
  if self.call('Bind','(s)',(self.nonce,))!=(True,):raise RuntimeError('Indicator already owned')
  self.bound=True;self.subscription=self.bus.signal_subscribe(self.owner,IFACE,'ContextChanged',PATH,None,Gio.DBusSignalFlags.NONE,self.context_changed,None);self.update();threading.Thread(target=self.publish,daemon=True).start()
 def context(self):
  if self.closed.is_set() or not self.bound:raise RuntimeError('Foreground context unavailable')
  return json.loads(self.call('GetContext','(s)',(self.nonce,))[0])
 def context_changed(self,connection,sender,path,iface,signal,parameters,user=None):
  if self.closed.is_set() or sender!=self.owner or path!=PATH or iface!=IFACE or signal!='ContextChanged':return
  try:nonce,epoch=parameters.unpack()
  except Exception:return
  if nonce!=self.nonce or not isinstance(epoch,int) or isinstance(epoch,bool):return
  armed=self.armed
  if armed is not None:armed.changed(epoch)
  self._queue_physical_context()
 def set_physical_guard(self,enabled,on_activity=None):
  """Local routing only; caller separately authenticates remote opt-in."""
  if type(enabled) is not bool:raise ValueError('Physical routing must be boolean')
  with self._physical_lock:
   self._physical_generation+=1;self._physical_enabled=enabled and not self.closed.is_set()
   self._physical_callback=on_activity if self._physical_enabled else None
   self._physical_pending=False
 def _queue_physical_context(self):
  with self._physical_lock:
   if self.closed.is_set() or not self._physical_enabled:return
   self._physical_pending=True
   if self._physical_worker:return
   self._physical_worker=True
  # Never perform synchronous D-Bus GetContext in its signal dispatch callback.
  try:threading.Thread(target=self._check_physical_context,daemon=True,name='desktop-device-source-check').start()
  except Exception:
   with self._physical_lock:self._physical_worker=False
   self._physical_check_failed()
 def _physical_check_failed(self):
  if self.closed.is_set():return
  self.close()
  if self.on_failure is not None:self.on_failure()
 def _check_physical_context(self):
  while True:
   with self._physical_lock:
    if self.closed.is_set() or not self._physical_enabled or not self._physical_pending:
     self._physical_worker=False;return
    self._physical_pending=False;generation=self._physical_generation
   try:
    context=self.context()
    if not isinstance(context,dict):raise RuntimeError('Invalid device-source context')
   except Exception:
    with self._physical_lock:
     current=generation==self._physical_generation and self._physical_enabled
     if current:self._physical_worker=False
    if current:
     self._physical_check_failed();return
    continue
   callback=None
   with self._physical_lock:
    if generation==self._physical_generation and self._physical_enabled and not self.closed.is_set() and context.get('reason')=='device-source-activity':
     self._physical_enabled=False;self._physical_pending=False;callback=self._physical_callback
   if callback is not None:
    try:callback()
    except Exception:self._physical_check_failed()
 def update(self):
  if self.closed.is_set():return
  if self.call('Update','(sb)',(self.nonce,self.status().get('active') is True))!=(True,):raise RuntimeError('Indicator update refused')
 def publish(self):
  while not self.closed.wait(.2):
   try:self.update()
   except Exception:
    if self.closed.is_set():return
    self.close()
    if self.on_failure is not None:self.on_failure()
    return
 def close(self):
  if self.closed.is_set():return
  self.closed.set();self.armed=None;self.set_physical_guard(False)
  if self.subscription is not None:
   try:self.bus.signal_unsubscribe(self.subscription)
   except Exception:pass
   self.subscription=None
  if self.bound:
   try:self.call('Update','(sb)',(self.nonce,False))
   except Exception:pass
   try:self.call('Unbind','(s)',(self.nonce,))
   except Exception:pass
   self.bound=False
