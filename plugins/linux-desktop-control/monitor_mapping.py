"""Read-only GNOME logical-monitor binding; no connection or query on import.

DisplayConfig monitor identifiers remain private. Geometry diagnostics do not
provide input authority; callers must check this guard before input dispatch.
"""
import math

NAME='org.gnome.Mutter.DisplayConfig'
PATH='/org/gnome/Mutter/DisplayConfig'
TIMEOUT_MS=3000

class MappingError(RuntimeError):
    pass


def _fail():
    raise MappingError('Selected monitor mapping is unavailable, changed, or unsupported; input refused')


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def _normalize(value, depth=0, budget=None):
    if budget is None:budget=[20000]
    budget[0]-=1
    if depth>12 or budget[0]<0:_fail()
    if hasattr(value,'unpack'):value=value.unpack()
    if value is None:return ('none',)
    if type(value) is bool:return ('bool',value)
    if type(value) is int:
        if not -(1<<64)<=value<(1<<64):_fail()
        return ('int',value)
    if type(value) is float:
        if not math.isfinite(value):_fail()
        return ('float',value)
    if type(value) is str:
        if len(value)>4096:_fail()
        return ('str',value)
    if type(value) in (tuple,list):
        return ('array',tuple(_normalize(item,depth+1,budget) for item in value))
    if type(value) is dict:
        if not all(type(key) is str and len(key)<=4096 for key in value):_fail()
        return ('dict',tuple((key,_normalize(value[key],depth+1,budget)) for key in sorted(value)))
    _fail()


def _unpack(value):
    if hasattr(value,'unpack'):return _unpack(value.unpack())
    if type(value) in (tuple,list):return tuple(_unpack(item) for item in value)
    if type(value) is dict:return {key:_unpack(item) for key,item in value.items()}
    return value


def _pair(value, positive=False):
    if type(value) not in (tuple,list) or len(value)!=2:_fail()
    if not all(type(item) is int and -100000<=item<=100000 for item in value):_fail()
    if positive and min(value)<=0:_fail()
    return tuple(value)


def _spec(value):
    if type(value) not in (tuple,list) or len(value)!=4:_fail()
    if not all(type(item) is str and len(item)<=4096 for item in value) or not value[0]:_fail()
    return tuple(value)


def validate_state(state, props):
    """Pure schema/geometry validation; returns private normalized binding + rect/scale."""
    normalized=_normalize(state)
    _normalize(props)
    state=_unpack(state);props=_unpack(props)
    if type(state) not in (tuple,list) or len(state)!=4 or type(props) is not dict:_fail()
    serial,monitors,logical,properties=state
    if type(serial) is not int or not 0<=serial<(1<<32):_fail()
    if type(monitors) not in (tuple,list) or not monitors or type(logical) not in (tuple,list) or not logical:_fail()
    # Mutter's documented absence default is logical layout mode 1.
    if type(properties) is not dict or type(properties.get('layout-mode',1)) is not int or properties.get('layout-mode',1)!=1:_fail()
    origin=_pair(props.get('position'))
    size=_pair(props.get('logical_size',props.get('size')),True)
    # If both exist, size can be buffer pixels rather than logical dimensions;
    # logical_size is the sole selected geometry authority in that case.
    selected=origin+size
    physical={}
    for monitor in monitors:
        if type(monitor) not in (tuple,list) or len(monitor)!=3:_fail()
        identity,modes,metadata=monitor;identity=_spec(identity)
        if identity in physical or type(modes) not in (tuple,list) or type(metadata) is not dict:_fail()
        active=[]
        for mode in modes:
            if type(mode) not in (tuple,list) or len(mode)!=7:_fail()
            mode_id,width,height,refresh,preferred,scales,flags=mode
            if type(mode_id) is not str or not mode_id or type(width) is not int or type(height) is not int or not 0<width<=100000 or not 0<height<=100000:_fail()
            if not _number(refresh) or refresh<=0 or not _number(preferred) or preferred<=0 or type(scales) not in (tuple,list) or not scales or not all(_number(v) and .25<=v<=8 for v in scales) or type(flags) is not dict:_fail()
            if 'is-current' in flags and type(flags['is-current']) is not bool:_fail()
            if flags.get('is-current') is True:active.append((width,height,tuple(scales)))
        physical[identity]=active
    candidates=[];used=set();rectangles=[]
    for monitor in logical:
        if type(monitor) not in (tuple,list) or len(monitor)!=7:_fail()
        x,y,scale,transform,primary,identities,metadata=monitor
        _pair((x,y))
        if not _number(scale) or not .25<=scale<=8 or type(transform) is not int or transform!=0 or type(primary) is not bool or type(metadata) is not dict:_fail()
        # Mirroring is deliberately unsupported: one physical source per logical monitor.
        if type(identities) not in (tuple,list) or len(identities)!=1:_fail()
        identity=_spec(identities[0])
        if identity in used or identity not in physical or len(physical[identity])!=1:_fail()
        used.add(identity)
        width,height,scales=physical[identity][0]
        if not any(abs(scale-supported)<1e-6 for supported in scales):_fail()
        rect=(x,y,math.floor(width/scale+.5),math.floor(height/scale+.5))
        for prior in rectangles:
            if max(rect[0],prior[0])<min(rect[0]+rect[2],prior[0]+prior[2]) and max(rect[1],prior[1])<min(rect[1]+rect[3],prior[1]+prior[3]):_fail()
        rectangles.append(rect)
        if rect==selected:candidates.append((rect,float(scale)))
    if len(candidates)!=1:_fail()
    rect,scale=candidates[0]
    return (serial,normalized,selected),rect,scale


class MonitorMapping:
    def __init__(self,bus,props):
        self.bus=bus
        self.failed=False
        try:
            _normalize(props)
            props=_unpack(props)
            if type(props) is not dict:_fail()
            self.props={'position':_pair(props.get('position')),
                        'logical_size':_pair(props.get('logical_size',props.get('size')),True)}
            owner,state=self._read()
            binding,self.rect,self.scale=validate_state(state,self.props)
            self.owner=owner;self.binding=binding
            self.props_binding=_normalize(self.props)
            self.geometry_binding=_normalize((self.rect,self.scale))
        except Exception:
            self.failed=True;_fail()

    def _call(self,destination,path,interface,method,parameters=None):
        # Injection is a read-only fixture adapter, never a model argument.
        adapter=getattr(self.bus,'mapping_call',None)
        if adapter is not None:return _unpack(adapter(destination,path,interface,method,parameters,TIMEOUT_MS))
        from gi.repository import Gio,GLib
        arguments=GLib.Variant('(s)',(NAME,)) if method=='GetNameOwner' else None
        result=self.bus.call_sync(destination,path,interface,method,arguments,None,
                                  Gio.DBusCallFlags.NO_AUTO_START,TIMEOUT_MS,None)
        return _unpack(result)

    def _owner(self):
        result=self._call('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner',NAME)
        if type(result) not in (list,tuple) or len(result)!=1 or type(result[0]) is not str or not result[0].startswith(':') or len(result[0])>255:_fail()
        return result[0]

    def _read(self):
        owner=self._owner()
        state=self._call(owner,PATH,NAME,'GetCurrentState')
        if self._owner()!=owner:_fail()
        return owner,state

    def check(self):
        if self.failed:_fail()
        try:
            owner,state=self._read()
            # Still query the owner/state/owner on every check. Exact typed
            # equality with the fully validated initial state proves unchanged
            # geometry without re-deriving every inactive display mode. Never
            # use Python's untyped equality (True == 1), a serial-only cache, or
            # a time-based cache as authority.
            if (owner!=self.owner or _normalize(state)!=self.binding[1] or
                    _normalize(self.props)!=self.props_binding or
                    _normalize((self.rect,self.scale))!=self.geometry_binding):_fail()
        except Exception:
            self.failed=True;_fail()
        return True

    assert_current=check

    def status(self):
        return {'supported':not self.failed,'diagnostic':'logical-monitor-bound' if not self.failed else 'monitor-mapping-refused',
                'logical_rect':list(self.rect) if hasattr(self,'rect') else None,
                'scale':self.scale if hasattr(self,'scale') else None}

    def _other_window_monitor(self, context):
        """Read-only two-monitor geometry shared by distinct GUI gestures."""
        self.check()
        owner,state=self._read()
        binding,rect,scale=validate_state(state,self.props)
        if owner!=self.owner or binding!=self.binding:_fail()
        state=_unpack(state)
        if len(state[2])!=2:raise MappingError('Window move requires exactly two unambiguous monitors')
        dimensions={}
        for identity,modes,_ in state[1]:
            active=[mode for mode in modes if mode[6].get('is-current') is True]
            if len(active)!=1:_fail()
            dimensions[tuple(identity)]=active[0][1:3]
        rectangles=[]
        for x,y,factor,transform,primary,identities,properties in state[2]:
            w,h=dimensions[tuple(identities[0])]
            candidate=(x,y,math.floor(w/factor+.5),math.floor(h/factor+.5))
            validate_state(state,{'position':candidate[:2],'logical_size':candidate[2:]})
            rectangles.append(candidate)
        source=next(item for item in rectangles if item!=self.rect)
        frame=context.get('rect')
        if context.get('available') is not True or context.get('kind')!='window' or not isinstance(frame,(tuple,list)) or len(frame)!=4 or not all(_number(v) for v in frame):
            raise MappingError('Current focused window unavailable')
        if frame[2]<=0 or frame[3]<=0:raise MappingError('Invalid focused window frame')
        return tuple(source),tuple(frame)

    def window_normalize_source(self, context):
        source,frame=self._other_window_monitor(context)
        x,y,w,h=frame;a,b,c,d=source
        def inside(px,py):return a<=px<a+c and b<=py<b+d
        # Both the frame origin/titlebar and center must belong to the other
        # monitor. A straddling/oversized frame is never assigned by guesswork.
        if a<=x and b<=y and x+w<=a+c and y+h<=b+d:
            raise MappingError('Focused window already wholly on source; use the separate monitor move')
        sx,sy,sw,sh=self.rect
        if max(x,sx)<min(x+w,sx+sw) and max(y,sy)<min(y+h,sy+sh):
            raise MappingError('Focused window intersects the shared monitor; normalization refused')
        if not inside(x,y) or not inside(x+w/2,y+h/2):
            raise MappingError('Focused window origin and center must belong to the other monitor')
        return source

    def window_fit_shared(self, context):
        source,frame=self._other_window_monitor(context)
        x,y,w,h=frame;a,b,c,d=self.rect
        def inside(px,py):return a<=px<a+c and b<=py<b+d
        def intersection(rect):
            rx,ry,rw,rh=rect
            return max(0,min(x+w,rx+rw)-max(x,rx))*max(0,min(y+h,ry+rh)-max(y,ry))
        if a<=x and b<=y and x+w<=a+c and y+h<=b+d:
            raise MappingError('Focused window already fits the shared monitor')
        if not inside(x+w/2,y+h/2) or not inside(x+w/2,y):
            raise MappingError('Focused window center and titlebar midpoint must identify the shared monitor')
        if intersection(self.rect)<=0 or intersection(self.rect)<=intersection(source):
            raise MappingError('Shared monitor must contain the unique largest window intersection')
        return tuple(self.rect)

    def window_move_direction(self, context, direction):
        source,frame=self._other_window_monitor(context)
        x,y,w,h=frame;a,b,c,d=source
        if not (a<=x and b<=y and x+w<=a+c and y+h<=b+d):
            raise MappingError('Focused window must be wholly on the other monitor')
        x,y,w,h=source;a,b,c,d=self.rect
        permitted={'Left':a+c<=x and max(y,b)<min(y+h,b+d),
                   'Right':x+w<=a and max(y,b)<min(y+h,b+d),
                   'Up':b+d<=y and max(x,a)<min(x+w,a+c),
                   'Down':y+h<=b and max(x,a)<min(x+w,a+c)}
        if permitted.get(direction) is not True:raise MappingError('Requested shortcut does not lead to the shared monitor')
        return tuple(self.rect)
