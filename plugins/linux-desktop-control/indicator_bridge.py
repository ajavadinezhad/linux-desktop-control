"""Read-only foreground observer and passive label. No input or human-control signals."""
import json,threading,uuid
from gi.repository import Gio,GLib
NAME='org.gnome.Shell';PATH='/org/codex/DesktopIndicator';IFACE='org.codex.DesktopIndicator'
class IndicatorBridge:
 def __init__(self,status,bus=None,on_failure=None):
  self.on_failure=on_failure;self.status=status;self.bus=bus;self.nonce=uuid.uuid4().hex;self.owner=None;self.bound=False;self.closed=threading.Event();self.subscription=None;self.armed=None
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
  self.closed.set();self.armed=None
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
