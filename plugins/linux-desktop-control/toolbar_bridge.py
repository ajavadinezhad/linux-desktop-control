"""Authenticated same-user GNOME Shell toolbar transport; no capture or input."""
import json,math,threading,time,uuid
from gi.repository import Gio,GLib

NAME='org.gnome.Shell'
PATH='/org/codex/DesktopToolbar'
INTERFACE='org.codex.DesktopToolbar'
ENABLE_MESSAGE='Enable the installed desktop toolbar extension after logout/login; desktop control cannot proceed without the toolbar.'
STATES=frozenset(('active','paused','pausing','resuming','stopping','starting','stopped'))


def toolbar_view(status):
    state=status.get('control_state','stopped')
    if state not in STATES:state='stopped'
    epoch=status.get('control_epoch',0)
    if not isinstance(epoch,int) or isinstance(epoch,bool) or not 0<=epoch<=0xffffffff:epoch=0
    view={'state':state,'epoch':epoch,
          'visible':state in ('active','paused','pausing','resuming','stopping') or (state=='starting' and status.get('toolbar_session_ready') is True),
          'closure_warning':bool(status.get('cleanup_warning')) or (state=='paused' and status.get('portal_closed_confirmed') is not True),
          'can_continue':state=='paused' and status.get('portal_closed_confirmed') is True,
          'ready_to_observe':status.get('ready_to_observe') is True}
    activity=status.get('next_required_action','waiting_executor')
    view['activity']=activity if activity in ('working','observe','plan_ack','waiting_executor','consent','wait','end') else 'waiting_executor'
    monitor=status.get('monitor')
    if isinstance(monitor,dict):
        values=[monitor.get(k) for k in ('x','y','width','height')]
        if all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and abs(v)<=100000 for v in values) and values[2]>0 and values[3]>0:
            view['monitor']=dict(zip(('x','y','width','height'),values))
    if status.get('cleanup_warning') or (state=='stopped' and status.get('toolbar_session_ready') and status.get('portal_closed_confirmed') is not True):
        view['visible']=True;view['closure_warning']=True;view['can_continue']=False
    return view


class ToolbarBridge:
    def __init__(self,status,control,bus=None):
        self.status=status;self.control=control;self.bus=bus
        self.nonce=uuid.uuid4().hex;self.owner=None;self.sequence=0
        self.closed=threading.Event();self.failed=False;self.bound=False
        self.subscriptions=[];self.failure_lock=threading.Lock()

    def _call(self,method,signature,args,timeout=1000):
        return self.bus.call_sync(self.owner,PATH,INTERFACE,method,
                GLib.Variant(signature,args),None,Gio.DBusCallFlags.NONE,timeout,None)

    def preflight(self,guard=lambda:None):
        """Read-only availability check before asking for desktop consent."""
        guard()
        try:
            if self.bus is None:self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            reply=self.bus.call_sync(NAME,PATH,INTERFACE,'GetDiagnostics',GLib.Variant('()',()),None,Gio.DBusCallFlags.NONE,1000,None)
            diagnostics=json.loads(reply.unpack()[0])
        except Exception as error:
            raise RuntimeError('Desktop toolbar diagnostics unavailable: '+str(error)+'. '+ENABLE_MESSAGE) from error
        owner=diagnostics.get('owner')
        if owner and owner!=self.bus.get_unique_name():
            raise RuntimeError('Another desktop session owns the toolbar ('+str(owner)+'). Stop that session before starting this one; the extension is loaded and no logout is needed for this ownership conflict.')
        if diagnostics.get('protocol_version')!=2:
            raise RuntimeError('Updated desktop toolbar is not loaded. Save your work and log out/in manually; GNOME cannot hot-reload this extension. No sharing was requested.')
        guard()

    def start(self,guard=lambda:None):
        if self.bound:return
        guard()
        try:
            if self.bus is None:self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            reply=self.bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus',
                'org.freedesktop.DBus','GetNameOwner',GLib.Variant('(s)',(NAME,)),
                None,Gio.DBusCallFlags.NONE,1000,None)
            self.owner=reply.unpack()[0]
            if not isinstance(self.owner,str) or not self.owner.startswith(':'):raise RuntimeError('Invalid Shell owner')
            self.subscriptions.append(self.bus.signal_subscribe(self.owner,INTERFACE,'Control',PATH,None,Gio.DBusSignalFlags.NONE,self._signal))
            self.subscriptions.append(self.bus.signal_subscribe('org.freedesktop.DBus','org.freedesktop.DBus','NameOwnerChanged','/org/freedesktop/DBus',NAME,Gio.DBusSignalFlags.NONE,self._owner_changed))
            guard()
            if self._call('Bind','(s)',(self.nonce,)).unpack()!=(True,):
                raise RuntimeError('Toolbar is already bound to another desktop session')
            self.bound=True
            guard()
            self._update()
            guard()
        except BaseException as error:
            self.fail()
            self._cleanup()
            if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
            raise RuntimeError(ENABLE_MESSAGE) from error
        threading.Thread(target=self.publish,daemon=True).start()

    def _signal(self,connection,sender,path,interface,signal,parameters):
        if self.closed.is_set() or self.failed or not self.bound:return
        if sender!=self.owner or path!=PATH or interface!=INTERFACE or signal!='Control':return
        try:nonce,event,epoch,sequence=parameters.unpack()
        except (TypeError,ValueError):return
        if nonce!=self.nonce or event not in ('pause','continue','stop'):return
        if not isinstance(sequence,int) or isinstance(sequence,bool) or sequence<=self.sequence:return
        # Consume authentic sequence even if its epoch is stale; reject replay.
        self.sequence=sequence
        if event=='stop':
            try:self.control('stop',expected_epoch=None)
            except Exception:self.fail()
            return
        try:current=self.status().get('control_epoch')
        except Exception:self.fail();return
        if epoch!=current and event!='stop':return
        try:self.control(event,expected_epoch=None if event=='stop' else epoch)
        except Exception:self.fail()

    def _owner_changed(self,connection,sender,path,interface,signal,parameters):
        try:name,old,new=parameters.unpack()
        except (TypeError,ValueError):return
        if name==NAME and old==self.owner and new!=self.owner:self.fail()

    def _update(self):
        view=toolbar_view(self.status())
        if self._call('Update','(ss)',(self.nonce,json.dumps(view,separators=(',',':')))).unpack()!=(True,):
            raise RuntimeError('Shell toolbar rejected state update')

    def publish(self):
        while not self.closed.wait(.2):
            try:self._update()
            except Exception:self.fail();return

    def fail(self):
        with self.failure_lock:
            if self.closed.is_set() or self.failed:return
            self.failed=True
        self.control('stop')

    def diagnostics(self):
        if self.closed.is_set() or not self.bound:raise RuntimeError('Toolbar is not connected')
        return json.loads(self._call('GetDiagnostics','()',()).unpack()[0])

    def wait_visible(self,guard=lambda:None,timeout=3):
        """Refuse input until Shell confirms one mapped, allocated toolbar."""
        deadline=time.monotonic()+timeout
        while True:
            guard()
            if self.closed.is_set() or self.failed:
                raise RuntimeError('Desktop toolbar disconnected before it became visible')
            try:
                diagnostics=self.diagnostics()
                rect=diagnostics.get('rect')
                allocated=(isinstance(rect,(list,tuple)) and len(rect)==4 and
                    all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in rect) and
                    rect[2]>0 and rect[3]>0)
                if diagnostics.get('visible') is True and diagnostics.get('actors')==1 and allocated:
                    guard()
                    return diagnostics
            except Exception:
                self.fail()
                raise RuntimeError('Desktop toolbar visibility could not be confirmed; input refused')
            if time.monotonic()>=deadline:
                self.fail()
                raise RuntimeError('Desktop toolbar did not become visible; input refused')
            self.closed.wait(min(.05,max(0,deadline-time.monotonic())))

    def _cleanup(self):
        if self.bus:
            for subscription in self.subscriptions:
                self.bus.signal_unsubscribe(subscription)
            self.subscriptions=[]
            if self.bound:
                try:self._call('Unbind','(s)',(self.nonce,),timeout=500)
                except Exception:pass
        self.bound=False

    def close(self):
        self.closed.set()
        self._cleanup()
