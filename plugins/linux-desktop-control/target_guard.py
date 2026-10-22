"""Optional AT-SPI keyboard identity guards. Never reads text, names or clipboard."""
import time,threading
from types import SimpleNamespace

class TargetUnavailable(RuntimeError):pass

class AtspiTarget:
    def __init__(self,api,window,node,gate,deadline=None):
        self.api=api;self.window=window;self.node=node;self.gate=gate
        self.deadline=deadline if deadline is not None else time.monotonic()+.6
        self.identity=(node.app.bus_name,node.path,window.path,self.call(node.get_process_id))
        self.role=self.call(node.get_role).value_nick
        self.bounds=self.rect(node);self.window_bounds=self.rect(window)
    def call(self,fn,*args):
        self.gate()
        if time.monotonic()>self.deadline:raise TargetUnavailable('Accessibility guard budget exceeded')
        value=fn(*args);self.gate()
        if time.monotonic()>self.deadline:raise TargetUnavailable('Accessibility guard budget exceeded')
        return value
    def rect(self,node):
        component=self.call(node.get_component_iface)
        if component is None:raise TargetUnavailable('Target has no accessibility component')
        rect=self.call(component.get_extents,self.api.CoordType.WINDOW)
        value=[rect.x,rect.y,rect.width,rect.height]
        if rect.width<=0 or rect.height<=0:raise TargetUnavailable('Target geometry is unavailable')
        return value
    def states(self,node):
        self.call(node.clear_cache_single)
        return self.call(node.get_state_set)
    def live(self,active=False,focused=False,deadline=None):
        self.deadline=min(time.monotonic()+.6,deadline) if deadline is not None else time.monotonic()+.6
        A=self.api.StateType
        for node in (self.window,self.node):
            s=self.states(node)
            if s.contains(A.DEFUNCT) or not s.contains(A.VISIBLE) or not s.contains(A.SHOWING):
                raise TargetUnavailable('Observed target vanished or is hidden; inspect a new observation before input')
        role=self.call(self.node.get_role)
        if role==self.api.Role.PASSWORD_TEXT or not self.states(self.node).contains(A.EDITABLE):
            raise TargetUnavailable('Target became protected or noneditable; input refused')
        if role.value_nick!=self.role:raise TargetUnavailable('Target role changed')
        if (self.node.app.bus_name,self.node.path,self.window.path,self.call(self.node.get_process_id))!=self.identity:
            raise TargetUnavailable('Target identity changed; inspect again')
        if self.rect(self.window)!=self.window_bounds or self.rect(self.node)!=self.bounds:
            raise TargetUnavailable('Target geometry changed; inspect and reacquire it')
        if active and not self.states(self.window).contains(A.ACTIVE):
            raise TargetUnavailable('Expected target window is not active; no keyboard input sent')
        if focused and not self.states(self.node).contains(A.FOCUSED):
            raise TargetUnavailable('Expected control lost keyboard focus; no further input sent')
    def acquire(self):
        # Never reclaim a control after the human moved focus elsewhere.
        self.live(active=True,focused=True)
    def check(self):self.live(active=True,focused=True)
    def describe(self):
        return {'role':self.role,'process_id':self.identity[3],
                'control_bounds_in_window':list(self.bounds),
                'window_size':self.window_bounds[2:],
                'coordinate_note':'Accessibility bounds are window-relative; never use them as screen coordinates.',
                'text_values_read':False}

class DirectStates:
    def __init__(self,words):self.words=words
    def contains(self,state):
        bit=int(state);word=bit//32
        return word<len(self.words) and bool(self.words[word] & (1<<(bit%32)))

class DirectNode:
    """No libatspi cache/events: only explicitly requested public D-Bus metadata."""
    ACCESSIBLE='org.a11y.atspi.Accessible'
    COMPONENT='org.a11y.atspi.Component'
    def __init__(self,client,bus_name,path):
        self.client=client;self.app=SimpleNamespace(bus_name=bus_name);self.path=path
    def rpc(self,interface,method,signature='()',args=()):
        return self.client.call(self.app.bus_name,self.path,interface,method,signature,args)
    def get_child_count(self):
        value=self.rpc('org.freedesktop.DBus.Properties','Get','(ss)',(self.ACCESSIBLE,'ChildCount'))[0]
        return int(value.unpack() if hasattr(value,'unpack') else value)
    def get_child_at_index(self,index):
        bus,path=self.rpc(self.ACCESSIBLE,'GetChildAtIndex','(i)',(index,))[0]
        if not bus or path=='/org/a11y/atspi/null':raise TargetUnavailable('Accessible child disappeared')
        return DirectNode(self.client,bus,path)
    def clear_cache_single(self):pass # Every state/role/geometry query is a fresh RPC.
    def get_state_set(self):return DirectStates(self.rpc(self.ACCESSIBLE,'GetState')[0])
    def get_role(self):return self.client.roles(self.rpc(self.ACCESSIBLE,'GetRole')[0])
    def get_process_id(self):
        return self.client.call('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixProcessID','(s)',(self.app.bus_name,))[0]
    def get_component_iface(self):return self
    def get_extents(self,coord):
        values=self.rpc(self.COMPONENT,'GetExtents','(u)',(int(coord),))[0]
        return SimpleNamespace(**dict(zip(('x','y','width','height'),values)))

class DirectClient:
    def __init__(self,roles):
        from gi.repository import Gio,GLib
        self.Gio=Gio;self.GLib=GLib;self.roles=roles;self.bus=None
        session=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        address=session.call_sync('org.a11y.Bus','/org/a11y/bus','org.a11y.Bus','GetAddress',None,None,Gio.DBusCallFlags.NONE,300,None).unpack()[0]
        cancelled=Gio.Cancellable();timer=threading.Timer(.3,cancelled.cancel);timer.daemon=True;timer.start()
        try:self.bus=Gio.DBusConnection.new_for_address_sync(address,Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,None,cancelled)
        finally:timer.cancel()
    def call(self,dest,path,interface,method,signature,args):
        allowed={(DirectNode.ACCESSIBLE,'GetChildAtIndex'),(DirectNode.ACCESSIBLE,'GetState'),(DirectNode.ACCESSIBLE,'GetRole'),(DirectNode.COMPONENT,'GetExtents'),('org.freedesktop.DBus','GetConnectionUnixProcessID')}
        if (interface,method)==('org.freedesktop.DBus.Properties','Get'):
            if args!=(DirectNode.ACCESSIBLE,'ChildCount'):raise TargetUnavailable('Accessibility property is outside identity inspection')
        elif (interface,method) not in allowed:raise TargetUnavailable('Accessibility method is outside identity inspection')
        if self.bus is None or self.bus.is_closed():raise TargetUnavailable('Accessibility connection is closed; inspect a fresh target')
        return self.bus.call_sync(dest,path,interface,method,self.GLib.Variant(signature,args),None,self.Gio.DBusCallFlags.NONE,150,None).unpack()
    def close(self):
        bus=self.bus;self.bus=None
        if bus is None or bus.is_closed():return True
        cancelled=self.Gio.Cancellable();timer=threading.Timer(.3,cancelled.cancel);timer.daemon=True;timer.start()
        try:
            bus.close_sync(cancelled)
        except Exception:pass # No further RPCs admitted; report unconfirmed closure separately.
        finally:timer.cancel()
        return bus.is_closed()

class AtspiProvider:
    def __init__(self):
        import gi
        gi.require_version('Atspi','2.0')
        from gi.repository import Atspi
        # Import enum definitions only. Never initialize libatspi or subscribe to
        # its caches, which may otherwise collect accessible names in background.
        self.client=DirectClient(Atspi.Role)
        self.api=SimpleNamespace(StateType=Atspi.StateType,Role=Atspi.Role,CoordType=Atspi.CoordType,
            get_desktop=lambda index:DirectNode(self.client,'org.a11y.atspi.Registry','/org/a11y/atspi/accessible/root'))
    def close(self):return self.client.close()
    def snapshot(self,gate):
        A=self.api.StateType;deadline=time.monotonic()+1.5
        def call(fn,*args):
            gate()
            if time.monotonic()>deadline:raise TargetUnavailable('Accessibility inspection budget exceeded')
            value=fn(*args);gate()
            if time.monotonic()>deadline:raise TargetUnavailable('Accessibility inspection budget exceeded')
            return value
        def children(node,limit,label):
            count=call(node.get_child_count)
            if not isinstance(count,int) or isinstance(count,bool) or not 0<=count<=limit:
                raise TargetUnavailable(label+' exceeds bounded inspection budget')
            return [call(node.get_child_at_index,k) for k in range(count)]
        root=call(self.api.get_desktop,0);windows=[]
        for app in children(root,64,'Accessibility applications'):
            for win in children(app,16,'Application windows'):
                call(win.clear_cache_single);state=call(win.get_state_set)
                if state.contains(A.ACTIVE) and state.contains(A.SHOWING) and state.contains(A.VISIBLE) and not state.contains(A.DEFUNCT):
                    windows.append(win)
        if not windows:raise TargetUnavailable('No unique active accessible window; reacquire and inspect again')
        # Some applications retain ACTIVE on more than one top-level window.
        # Resolve only a globally unique focused editable control, never the
        # first active window. Preserve ambiguity/password refusal across all
        # candidates and bound the aggregate traversal rather than each window.
        seen=set();focused=[]
        for window in windows:
            queue=[(window,0)]
            while queue:
                node,depth=queue.pop();identity=(node.app.bus_name,node.path)
                if identity in seen:continue
                seen.add(identity)
                if len(seen)>512:raise TargetUnavailable('Accessible windows exceed bounded inspection budget')
                call(node.clear_cache_single);state=call(node.get_state_set)
                if state.contains(A.DEFUNCT) or not state.contains(A.SHOWING) or not state.contains(A.VISIBLE):continue
                if state.contains(A.FOCUSED):
                    if call(node.get_role)==self.api.Role.PASSWORD_TEXT:raise TargetUnavailable('Password controls are excluded')
                    if state.contains(A.EDITABLE):focused.append((window,node))
                if depth<24:
                    queue.extend((child,depth+1) for child in children(node,128,'Accessible container'))
        if len(focused)!=1:raise TargetUnavailable('No unique focused editable control across active windows; focus the intended field and inspect again')
        window,node=focused[0]
        target=AtspiTarget(self.api,window,node,gate,deadline=deadline)
        target.live(active=True,focused=True,deadline=deadline)
        return target
