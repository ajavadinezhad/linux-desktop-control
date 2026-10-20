#!/usr/bin/python3
"""Explicitly consented, silent demo recording. Separate from desktop control.

Only run with the clean scratch scene visible. Stop before switching apps.
The recorder is independent of the desktop input session.
"""
import argparse,json,os,signal,threading,time,uuid,tempfile
from pathlib import Path
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gio,GLib,Gst
DEST='org.freedesktop.portal.Desktop';PATH='/org/freedesktop/portal/desktop'
SC='org.freedesktop.portal.ScreenCast'
class Recorder:
 def __init__(self,args):
  self.args=args;self.session=None;self.pipe=None;self.fd=None;self.sub=None
  self.done=threading.Event();self.loop=GLib.MainLoop();self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
  threading.Thread(target=self.loop.run,daemon=True).start();Gst.init(None)
 def call(self,interface,method,signature,args,path=PATH):
  return self.bus.call_sync(DEST,path,interface,method,GLib.Variant(signature,args),None,Gio.DBusCallFlags.NONE,3000,None).unpack()
 def request(self,method,signature,args,options):
  token='r'+uuid.uuid4().hex;sender=self.bus.get_unique_name()[1:].replace('.','_')
  path=f'{PATH}/request/{sender}/{token}';event=threading.Event();result=[]
  def response(*cb):result.extend(cb[-2].unpack());event.set()
  sub=self.bus.signal_subscribe(DEST,'org.freedesktop.portal.Request','Response',path,None,Gio.DBusSignalFlags.NONE,response,None)
  actual=None
  try:
   actual=self.call(SC,method,signature,(*args,dict(options,handle_token=GLib.Variant('s',token))))[0]
   if actual!=path:raise RuntimeError('Unexpected portal request handle')
   end=time.monotonic()+120
   while not event.wait(.1):
    if self.done.is_set() or time.monotonic()>end:raise RuntimeError('Recording consent cancelled or timed out')
   code,data=result
   if code:raise RuntimeError(f'GNOME recording permission denied/cancelled ({code})')
   return data
  finally:
   self.bus.signal_unsubscribe(sub)
   if actual and not event.is_set():
    try:self.call('org.freedesktop.portal.Request','Close','()',(),actual)
    except GLib.Error:pass
 def run(self):
  self.session=self.request('CreateSession','(a{sv})',(),{'session_handle_token':GLib.Variant('s','s'+uuid.uuid4().hex)})['session_handle']
  self.sub=self.bus.signal_subscribe(DEST,'org.freedesktop.portal.Session','Closed',self.session,None,Gio.DBusSignalFlags.NONE,lambda *_:self.done.set(),None)
  self.request('SelectSources','(oa{sv})',(self.session,),{'types':GLib.Variant('u',1),'multiple':GLib.Variant('b',False),'cursor_mode':GLib.Variant('u',2)})
  print('GNOME consent: choose the primary monitor with ONLY the clean scratch demo visible.',flush=True)
  data=self.request('Start','(osa{sv})',(self.session,''),{})
  if len(data.get('streams',[]))!=1:raise RuntimeError('Exactly one recording source required')
  node,props=data['streams'][0];w,h=props.get('size',(0,0));crop=self.args.crop_top
  if w<2 or h<=crop+2:raise RuntimeError('Invalid recording dimensions')
  reply,fds=self.bus.call_with_unix_fd_list_sync(DEST,PATH,SC,'OpenPipeWireRemote',GLib.Variant('(oa{sv})',(self.session,{})),GLib.VariantType('(h)'),Gio.DBusCallFlags.NONE,3000,None,None)
  self.fd=fds.get(reply.unpack()[0]);region=self.args.region
  if region:
   x,y,rw,rh=region
   if x<0 or y<0 or rw<2 or rh<2 or x+rw>w or y+rh>h:raise RuntimeError('Recording region outside selected source')
   filters=f'videocrop left={x} top={y} right={w-x-rw} bottom={h-y-rh}'
   cw,ch=rw,rh
  else:filters=f'videocrop top={crop}';cw,ch=w,h-crop
  scale=min(1,self.args.max_width/cw);ow=max(2,int(cw*scale)//2*2);oh=max(2,int(ch*scale)//2*2)
  self.pipe=Gst.parse_launch(f'pipewiresrc name=source do-timestamp=true ! queue max-size-buffers=3 max-size-bytes=0 max-size-time=0 leaky=downstream ! videorate ! video/x-raw,framerate=15/1 ! {filters} ! videoconvert ! videoscale ! video/x-raw,width={ow},height={oh},pixel-aspect-ratio=1/1 ! vp8enc deadline=1 cpu-used=4 target-bitrate=2500000 ! webmmux ! filesink name=output')
  source=self.pipe.get_by_name('source');source.set_property('fd',self.fd);source.set_property('path',str(node))
  if props.get('pipewire-serial'):source.set_property('target-object',str(props['pipewire-serial']))
  self.pipe.get_by_name('output').set_property('location',str(self.args.output))
  self.pipe.set_state(Gst.State.PLAYING);self.pipe.get_state(3*Gst.SECOND)
  print(json.dumps({'recording':True,'silent':True,'width':ow,'height':oh,'stop_file':str(self.args.stop_file),'maximum_seconds':self.args.seconds}),flush=True)
  started=time.monotonic();bus=self.pipe.get_bus();self.stop_reason=None;last_status=0
  def progress():
   elapsed=time.monotonic()-started
   write_status(self.args,recording=True,state='recording',elapsed_seconds=round(elapsed,2),remaining_seconds=max(0,round(self.args.seconds-elapsed,2)),width=ow,height=oh)
  progress()
  while not self.done.wait(.1):
   elapsed=time.monotonic()-started
   if elapsed-last_status>=.5:progress();last_status=elapsed
   if self.args.stop_file.exists():self.stop_reason='stop_file';break
   if elapsed>=self.args.seconds:self.stop_reason='time_limit';break
   message=bus.pop_filtered(Gst.MessageType.ERROR)
   if message:raise RuntimeError(message.parse_error()[0].message)
  self.pipe.send_event(Gst.Event.new_eos());message=bus.timed_pop_filtered(5*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR)
  if message is None or message.type!=Gst.MessageType.EOS:raise RuntimeError('Recording finalization was not confirmed')
  result={'recording':False,'state':'finished','stop_reason':self.stop_reason or 'session_closed_or_signal','duration_seconds':round(time.monotonic()-started,2),'bytes':self.args.output.stat().st_size}
  write_status(self.args,**result);print(json.dumps(result),flush=True)
 def close(self):
  self.done.set()
  if self.pipe:self.pipe.set_state(Gst.State.NULL)
  if self.session:
   try:self.call('org.freedesktop.portal.Session','Close','()',(),self.session)
   except GLib.Error:pass
  if self.sub:self.bus.signal_unsubscribe(self.sub)
  if self.fd is not None:os.close(self.fd)
  self.loop.quit()
def write_status(args,**state):
 # Atomic, private sidecar lets a coordinator detect the safety time limit
 # before performing work it mistakenly believes is still being recorded.
 path=args.status_file
 fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
 try:
  with os.fdopen(fd,'w') as stream:json.dump(state,stream);stream.write('\n')
  os.replace(name,path)
 finally:
  try:os.unlink(name)
  except FileNotFoundError:pass

def parse_args(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--stop-file',type=Path,required=True)
 p.add_argument('--status-file',type=Path);p.add_argument('--seconds',type=int,default=120)
 p.add_argument('--crop-top',type=int,default=0);p.add_argument('--region',type=int,nargs=4,metavar=('X','Y','WIDTH','HEIGHT'))
 p.add_argument('--max-width',type=int,default=3440);a=p.parse_args(argv)
 a.output=a.output.resolve();a.stop_file=a.stop_file.resolve()
 a.status_file=(a.status_file or Path(str(a.output)+'.status.json')).resolve()
 paths=(a.output,a.stop_file,a.status_file)
 if len(set(paths))!=3 or any(path.exists() for path in paths):p.error('Output, stop and status paths must be distinct and must not already exist')
 if not 1<=a.seconds<=900 or not 0<=a.crop_top<=200 or not 320<=a.max_width<=3840:p.error('Duration must be 1–900 seconds; crop 0–200 pixels; maximum width 320–3840 pixels')
 if a.region and (min(a.region[:2])<0 or min(a.region[2:])<2):p.error('Region needs nonnegative origin and dimensions of at least 2 pixels')
 return a

def record(args,factory=Recorder):
 args.output.parent.mkdir(parents=True,exist_ok=True);args.status_file.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
 recorder=None
 try:
  write_status(args,recording=False,state='awaiting_consent')
  recorder=factory(args)
  signal.signal(signal.SIGINT,lambda *_:recorder.done.set());signal.signal(signal.SIGTERM,lambda *_:recorder.done.set())
  recorder.run()
 except BaseException:
  write_status(args,recording=False,state='failed')
  if args.output.exists() and args.output.stat().st_size==0:args.output.unlink()
  raise
 finally:
  if recorder is not None:recorder.close()
if __name__=='__main__':record(parse_args())
