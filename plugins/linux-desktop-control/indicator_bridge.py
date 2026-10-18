"""Optional passive pointer label. No input, shortcuts or human-control signals."""
import json,threading,uuid
from gi.repository import Gio,GLib
NAME='org.gnome.Shell';PATH='/org/codex/DesktopIndicator';IFACE='org.codex.DesktopIndicator'
class IndicatorBridge:
 def __init__(self,status,bus=None):
  self.status=status;self.bus=bus;self.nonce=uuid.uuid4().hex;self.owner=None;self.bound=False;self.closed=threading.Event()
 def call(self,method,signature,args):return self.bus.call_sync(self.owner,PATH,IFACE,method,GLib.Variant(signature,args),None,Gio.DBusCallFlags.NONE,1000,None).unpack()
 def start(self):
  if self.bus is None:self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
  self.owner=self.bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner',GLib.Variant('(s)',(NAME,)),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
  diagnostics=json.loads(self.call('GetDiagnostics','()',())[0])
  if diagnostics.get('protocol_version')!=1:raise RuntimeError('Passive indicator is unavailable')
  if self.call('Bind','(s)',(self.nonce,))!=(True,):raise RuntimeError('Indicator already owned')
  self.bound=True;self.update();threading.Thread(target=self.publish,daemon=True).start()
 def update(self):
  if self.closed.is_set():return
  if self.call('Update','(sb)',(self.nonce,self.status().get('active') is True))!=(True,):raise RuntimeError('Indicator update refused')
 def publish(self):
  while not self.closed.wait(.2):
   try:self.update()
   except Exception:self.close();return
 def close(self):
  if self.closed.is_set():return
  self.closed.set()
  if self.bound:
   try:self.call('Update','(sb)',(self.nonce,False))
   except Exception:pass
   try:self.call('Unbind','(s)',(self.nonce,))
   except Exception:pass
   self.bound=False
