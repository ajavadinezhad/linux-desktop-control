#!/usr/bin/python3
"""GNOME Wayland desktop backend. No root privileges or private compositor APIs."""
import base64
import ctypes
import json
import math
import queue
import os
import signal
import sys
import threading
import time
import uuid
import importlib.util

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gio, GLib, Gst

VERSION = '0.8.33'
# Freeze identity at module load: old providers must never report a new disk build.
_build_spec = importlib.util.spec_from_file_location('_desktop_runtime_build', os.path.join(os.path.dirname(__file__), 'runtime_build.py'))
_runtime_build = importlib.util.module_from_spec(_build_spec)
_build_spec.loader.exec_module(_runtime_build)
SERVER_BUILD = _runtime_build.fingerprint(os.path.dirname(__file__))
_stream_spec = importlib.util.spec_from_file_location('_desktop_stream_metadata', os.path.join(os.path.dirname(__file__), 'stream_metadata.py'))
_stream_metadata = importlib.util.module_from_spec(_stream_spec)
_stream_spec.loader.exec_module(_stream_metadata)

def require_current_runtime():
    try:
        current = _runtime_build.fingerprint(os.path.dirname(__file__))
    except Exception:
        raise RuntimeError('Desktop runtime source unavailable; restart the provider before sharing') from None
    if current != SERVER_BUILD:
        raise RuntimeError('Desktop runtime source changed; restart the provider before sharing')

DEST = 'org.freedesktop.portal.Desktop'
PATH = '/org/freedesktop/portal/desktop'
RD = 'org.freedesktop.portal.RemoteDesktop'
SC = 'org.freedesktop.portal.ScreenCast'

class CaptureTimeout(RuntimeError):pass

class RetainedPause(RuntimeError):
    """An invalidated operation may not turn a retained pause into closure."""
    pass

class ClickContextPending(RuntimeError):
    """Only a foreground guard may request bounded physical-click correlation."""
    pass

class Desktop:
    requires_window_guard=True
    def __init__(self):
        Gst.init(None)
        self.loop = GLib.MainLoop()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()
        self.session = None
        self.monitor_mapping = None
        self.mapping_guard = None
        self.pipeline = None
        self.fd = None
        self.closed_sub = None
        self.portal_closed = False
        self.cancelled = threading.Event()
        self.operation_cancelled = threading.Event()
        self.confirmed_pointer_record = None
        self.lock = threading.RLock()
        self.held = []
        self.last_used = time.monotonic()
        self.frames = 0
        self.shutdown_requested = False
        self.xkb = ctypes.CDLL('libxkbcommon.so.0')
        self.xkb.xkb_keysym_from_name.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self.xkb.xkb_keysym_from_name.restype = ctypes.c_uint
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _watchdog(self):
        while not self.shutdown_requested:
            if self.cancelled.wait(.05) or (self.session and time.monotonic()-self.last_used > 300):
                with self.lock:
                    if self.cancelled.is_set() or (self.session and time.monotonic()-self.last_used > 300):
                        self.cancelled.set()
                        self.close()
                time.sleep(.05)
            elif getattr(self,'operation_cancelled',None) is not None and self.operation_cancelled.is_set():
                try:self.pause_input()
                except Exception:self.cancelled.set()

    def call(self, interface, method, signature, args, path=PATH):
        return self.bus.call_sync(DEST, path, interface, method,
            GLib.Variant(signature, args), None, Gio.DBusCallFlags.NONE, 5000, None)

    def request(self, interface, method, signature, args, options):
        token = 'r' + uuid.uuid4().hex
        sender = self.bus.get_unique_name()[1:].replace('.', '_')
        request_path = f'{PATH}/request/{sender}/{token}'
        options = dict(options, handle_token=GLib.Variant('s', token))
        done = threading.Event()
        result = []
        def response(*cb):
            result.extend(cb[-2].unpack())
            done.set()
        sub = self.bus.signal_subscribe(DEST, 'org.freedesktop.portal.Request',
            'Response', request_path, None, Gio.DBusSignalFlags.NONE, response, None)
        try:
            actual = self.call(interface, method, signature, (*args, options)).unpack()[0]
            if actual != request_path:
                raise RuntimeError('Portal did not honor request handle token')
            deadline = time.monotonic() + 120
            while not done.wait(.05):
                if self.cancelled.is_set() or (getattr(self,'request_cancel',None) and self.request_cancel.is_set()) or time.monotonic() > deadline:
                    self.call('org.freedesktop.portal.Request', 'Close', '()', (), path=actual)
                    raise RuntimeError('Portal request stopped or timed out')
            code, data = result
            if code:
                raise RuntimeError(f'Portal permission cancelled or denied (response {code})')
            return data
        finally:
            self.bus.signal_unsubscribe(sub)

    def start(self,defer_capture=False):
        with self.lock:
            if self.session and not self.cancelled.is_set():
                return self.status()
            self.close()
            if self.session is not None:raise RuntimeError('Previous portal closure is unconfirmed; end sharing in GNOME before a new session')
            self.cleanup_warning=None
            self.portal_closed = False
            self.cancelled.clear()
            if getattr(self,'request_cancel',None) and self.request_cancel.is_set():
                self.cancelled.set()
                raise RuntimeError('Desktop start cancelled before permission request')
            self.last_used = time.monotonic()
            try:
                self.session = self.request(RD, 'CreateSession', '(a{sv})', (),
                    {'session_handle_token': GLib.Variant('s', 's'+uuid.uuid4().hex)})['session_handle']
                self.closed_sub = self.bus.signal_subscribe(DEST, 'org.freedesktop.portal.Session',
                    'Closed', self.session, None, Gio.DBusSignalFlags.NONE,
                    self.on_session_closed, None)
                self.request(RD, 'SelectDevices', '(oa{sv})', (self.session,),
                    {'types': GLib.Variant('u', 3)})
                self.request(SC, 'SelectSources', '(oa{sv})', (self.session,),
                    {'types': GLib.Variant('u', 1), 'multiple': GLib.Variant('b', False),
                     'cursor_mode': GLib.Variant('u', 2)})
                data = self.request(RD, 'Start', '(osa{sv})', (self.session, ''), {})
                if data.get('devices', 0) & 3 != 3 or len(data.get('streams', [])) != 1:
                    raise RuntimeError('Grant keyboard, pointer and exactly one monitor')
                self.node, self.props = data['streams'][0]
                size = self.props.get('logical_size', self.props.get('size'))
                if not size or min(size) <= 0:
                    raise RuntimeError('Portal omitted valid stream dimensions')
                self.width, self.height = size
                self.check()
                require_current_runtime()
                spec = importlib.util.spec_from_file_location('_desktop_monitor_mapping', os.path.join(os.path.dirname(__file__), 'monitor_mapping.py'))
                mapping_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mapping_module)
                mapping = mapping_module.MonitorMapping(self.bus,self.props)
                require_current_runtime()
                self.check()
                self.monitor_mapping = mapping
                self.mapping_guard = mapping.check
                if not defer_capture:self.finish_start()
                return self.status()
            except BaseException:
                self.close()
                raise

    def finish_start(self):
        """Start capture only after any explicitly requested native guard is armed."""
        with self.lock:
            self.check()
            if self.pipeline is not None:return self.status()
            try:
                require_current_runtime()
                reply,fds=self.bus.call_with_unix_fd_list_sync(DEST,PATH,SC,
                    'OpenPipeWireRemote',GLib.Variant('(oa{sv})',(self.session,{})),
                    GLib.VariantType('(h)'),Gio.DBusCallFlags.NONE,5000,None,None)
                self.fd=fds.get(reply.unpack()[0])
                require_current_runtime()
                self._start_capture_pipeline();self.capture()
                return self.status()
            except BaseException:
                self.close();raise

    def _start_capture_pipeline(self):
        self.check()
        self.pipeline = Gst.parse_launch('pipewiresrc name=source do-timestamp=true ! '
            'queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream ! '
            'videorate drop-only=true max-rate=5 ! video/x-raw,framerate=5/1 ! '
            'videoconvert ! video/x-raw,format=RGB ! pngenc compression-level=1 ! '
            'appsink name=sink max-buffers=1 drop=true sync=false')
        source = self.pipeline.get_by_name('source')
        source.set_property('fd', self.fd)
        source.set_property('path', str(self.node))
        if self.props.get('pipewire-serial'):
            source.set_property('target-object', str(self.props['pipewire-serial']))
        self.sink = self.pipeline.get_by_name('sink')
        self.pipeline.set_state(Gst.State.PLAYING)
        self.pipeline.get_state(3 * Gst.SECOND)
        self.check()

    def on_session_closed(self,connection,sender,path,interface,name,parameters,user):
        if path==self.session:
            self.portal_closed=True
            self.cleanup_warning=None
            self.cancelled.set()

    def status(self):
        return {'active': bool(self.session) and not self.cancelled.is_set(),
                'monitor': self.monitor_geometry(),
                'pid': os.getpid(), 'idle_timeout_seconds': 300,
                'logical_size': [getattr(self,'width',0), getattr(self,'height',0)],
                'stream_geometry': _stream_metadata.diagnostic_stream_metadata(getattr(self,'props',{})),
                'pointer_transport': 'observed-relative',
                'monitor_mapping': self.monitor_mapping.status() if getattr(self,'monitor_mapping',None) is not None else None,
                'held_input_count':len(getattr(self,'held',[])),
                'input_release':dict(getattr(self,'release_counts',{'attempted':0,'confirmed':0,'failed':0})),

                'cleanup_warning':getattr(self,'cleanup_warning',None),
                'portal_closed_confirmed':getattr(self,'portal_closed',False) or (self.session is None and not getattr(self,'cleanup_warning',None))}

    def monitor_geometry(self):
        position=getattr(self,'props',{}).get('position')
        if isinstance(position,(list,tuple)) and len(position)==2:
            return {'x':position[0],'y':position[1],'width':getattr(self,'width',0),'height':getattr(self,'height',0)}
        return None

    def check(self):
        if getattr(self,'request_cancel',None) and self.request_cancel.is_set():self.cancelled.set()
        if self.cancelled.is_set() or not self.session:
            raise RuntimeError('Desktop session is closed; call desktop_start for new consent')
        if getattr(self,'operation_cancelled',None) is not None and self.operation_cancelled.is_set():
            raise RetainedPause('Desktop input is paused; use desktop_resume with the current pause_id')
        if getattr(self,'action_deadline',None) and time.monotonic()>self.action_deadline:
            raise RuntimeError('Input sequence exceeded 15 seconds; stopped before next event')
        window=getattr(self,'window_guard',None)
        if window is not None and not (getattr(self,'window_transition',False) and getattr(self,'transition_activated',False)):window.check()
        self.last_used = time.monotonic()

    def wait_interruptibly(self,seconds):
        deadline=time.monotonic()+seconds
        while True:
            self.check();remaining=deadline-time.monotonic()
            if remaining<=0:return
            if self.cancelled.wait(min(remaining,.05)):raise RuntimeError('Desktop session closed')

    def capture(self):
        with self.lock:
            self.check()
            try:return self._capture_once()
            except CaptureTimeout:
                # Reconnect only capture, once, under the existing consent. No
                # input, portal restart, or cached-frame timestamp substitution.
                self.check()
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline=None
                self.wait_interruptibly(.35)
                self._start_capture_pipeline()
                png=self._capture_once(new_stream=True)
                self.capture_info['pipeline_reconnected']=True
                return png

    def _capture_once(self,new_stream=False):
        capture_started=time.monotonic()
        self.check()
        # Require a frame captured after a settling fence, not merely the next
        # PNG emitted by an encoder that may still be processing older input.
        clock=self.pipeline.get_clock()
        if clock is None: raise RuntimeError('Screen pipeline has no clock')
        fence=0 if new_stream else clock.get_time()-self.pipeline.get_base_time()+350*Gst.MSECOND
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            self.check()
            sample = self.sink.emit('try-pull-sample', 100 * Gst.MSECOND)
            if sample:
                buf = sample.get_buffer()
                if buf.pts == Gst.CLOCK_TIME_NONE or buf.pts < fence:
                    continue
                age_ms=max(0,(clock.get_time()-self.pipeline.get_base_time()-buf.pts)/Gst.MSECOND)
                if age_ms>750:continue
                self.capture_info={'frame_id':self.frames+1,'settling_ms':350,
                    'frame_age_ms':age_ms,'freshness':'new_stream' if new_stream else 'post_settle_frame',
                    'capture_duration_ms':max(0,round((time.monotonic()-capture_started)*1000))}
                png = buf.extract_dup(0, buf.get_size())
                self.frames += 1
                return png
            error = self.pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
            if error:
                raise RuntimeError(str(error.parse_error()[0]))
        raise CaptureTimeout('No fresh screen frame received within 5 seconds')

    def notify(self, method, sig, *args):
        self.check()
        mapping_guard=getattr(self,'mapping_guard',None)
        if not callable(mapping_guard):
            self.cancelled.set()
            raise RuntimeError('Verified monitor mapping unavailable; input refused')
        try:mapping_guard()
        except BaseException:
            self.cancelled.set()
            raise
        self.check()
        # Keep the approach and modifiers fenced. The one authorized gesture
        # begins only at its activating press, never at motion or key release.
        activating=(method=='NotifyPointerButton' and args[-1]==1) or (method=='NotifyKeyboardKeysym' and args[-1]==1 and args[0] not in (0xffe1,0xffe2,0xffe3,0xffe4,0xffe9,0xffea))
        transition_key=getattr(self,'transition_activation_key',None)
        if transition_key is not None:activating=method=='NotifyKeyboardKeysym' and args[-1]==1 and args[0]==transition_key
        if getattr(self,'window_transition',False) and not getattr(self,'transition_activated',False) and activating:
            callback=getattr(self,'begin_transition',None)
            if callback is not None:callback()
            self.transition_activated=True
        target=getattr(self,'target_guard',None)
        if target is not None:
            if method=='NotifyKeyboardKeysym' and args[-1]:target.check()
            elif method not in ('NotifyKeyboardKeysym','NotifyPointerButton') or (method=='NotifyPointerButton' and args[-1]):target.live(active=True,focused=True)
            self.check()
        if getattr(self,'action_deadline',None):
            self.transaction_info['input_events_attempted'] += 1
        self.call(RD, method, '(oa{sv}'+sig+')', (self.session, {}, *args))

    def observe_pointer(self):
        # Both displacement and endpoint evidence need a current, bound display
        # layout. A missing guard is a refusal, never an unguarded test mode.
        guard=getattr(self,'mapping_guard',None)
        reader=getattr(self,'pointer_reader',None)
        try:
            if not callable(guard):raise RuntimeError('Display mapping guard unavailable; pointer effect refused')
            if not callable(reader):raise RuntimeError('Fresh compositor pointer observation unavailable; pointer effect refused')
            self.check();guard()
            observed=reader()
            self.check();guard()
            if (not isinstance(observed,(tuple,list)) or len(observed)!=2 or
                    not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in observed) or
                    not (0<=observed[0]<self.width and 0<=observed[1]<self.height)):
                raise RuntimeError('Invalid compositor pointer observation; pointer effect refused')
            return tuple(observed)
        except RetainedPause:
            raise
        except BaseException:
            self.cancelled.set()
            raise

    def position(self, x, y):
        x, y = float(x), float(y)
        if not all(map(math.isfinite, (x,y))) or not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError('Position outside logical_size of selected monitor')
        observed=self.observe_pointer()
        # Relative motion avoids this GNOME stack's incompatible absolute
        # stream units. Dispatch once; a mismatch stops without correction.
        self.notify('NotifyPointerMotion', 'dd', x-observed[0], y-observed[1])
        self.confirm_pointer_endpoint(x,y)

    def confirm_pointer_endpoint(self,x,y):
        # Dispatch success is not endpoint evidence. Require two independent
        # compositor snapshots; never infer position from emitted motion events.
        deadline=time.monotonic()+.35
        matched=0
        while True:
            observed=self.observe_pointer()
            if time.monotonic()>deadline:
                self.cancelled.set()
                raise RuntimeError('Pointer endpoint did not match the requested logical point; no retry')
            matched=matched+1 if abs(observed[0]-x)<=1 and abs(observed[1]-y)<=1 else 0
            if matched>=2:
                self.pointer_position=tuple(observed)
                context=getattr(self,'endpoint_context',None)
                if context is not None:
                    self.confirmed_pointer_record={'point':tuple(observed),'context':context,
                        'consent_id':getattr(self,'consent_id',None),'session':self.session,
                        'mapping':getattr(self,'monitor_mapping',None) or getattr(self,'mapping_guard',None)}
                return
            self.wait_interruptibly(.016)

    def move_to(self,x,y,seconds=.25):
        start=getattr(self,'pointer_position',None)
        if start is None or seconds==0:
            self.position(x,y)
            return
        deadline=time.monotonic()+seconds
        while True:
            remaining=deadline-time.monotonic()
            t=max(0,min(1,1-remaining/seconds))
            blend=t*t*(3-2*t)
            self.position(start[0]+(x-start[0])*blend,start[1]+(y-start[1])*blend)
            if t>=1:break
            self.wait_interruptibly(min(.016,max(0,deadline-time.monotonic())))
        # position() already confirms every interpolated point, including the
        # final one. Effects still take their own fresh pre-press observation.

    def state(self, kind, code, down):
        method = 'NotifyKeyboardKeysym' if kind == 'key' else 'NotifyPointerButton'
        if down:
            self.held.append((kind, code))
        self.notify(method, 'iu', code, int(down))
        if not down and (kind,code) in self.held:
            self.held.remove((kind,code))

    def release(self):
        if getattr(self,'portal_closed',False):
            self.held.clear()
            return False
        failed=False
        if not hasattr(self,'release_counts'):self.release_counts={'attempted':0,'confirmed':0,'failed':0}
        for kind, code in reversed(self.held[:]):
            confirmed=False
            self.release_counts['attempted']+=1
            try:
                method = 'NotifyKeyboardKeysym' if kind == 'key' else 'NotifyPointerButton'
                self.call(RD, method, '(oa{sv}iu)', (self.session, {}, code, 0))
                confirmed=True
                self.held.remove((kind,code))
            except Exception:
                failed=True
                self.cancelled.set()
                # Fail closed: remove the portal's virtual input devices instead
                # of silently continuing with a potentially held button/key.
                try:
                    self.call('org.freedesktop.portal.Session','Close','()',(),path=self.session)
                    self.portal_closed=True
                    self.session=None
                    self.held.clear()
                except Exception:
                    self.cleanup_warning='Input release and portal close failed. Stop sharing using the GNOME indicator.'
                break
            finally:
                # Aggregate portal-call outcomes only; no input codes/content.
                # A confirmed call is not proof of physical-device state.
                self.release_counts['confirmed' if confirmed else 'failed']+=1
        return failed

    def keysym(self, name):
        aliases = {'Ctrl':'Control_L','Control':'Control_L','Alt':'Alt_L','Shift':'Shift_L',
                   'Super':'Super_L','Enter':'Return','Esc':'Escape','Space':'space'}
        name = aliases.get(name, name)
        sym = self.xkb.xkb_keysym_from_name(name.encode(), 0)
        if not sym:
            raise ValueError('Unknown key: '+name)
        return sym

    @staticmethod
    def text_cost(value,mode='gnome_unicode'):
        return sum(.28+.015*len(format(ord(c),'x')) if ord(c)>127 and mode=='gnome_unicode' else .005 for c in value)

    def type_character(self,char,mode):
        code=ord(char)
        if code>127 and mode=='gnome_unicode':
            chord=[self.keysym(k) for k in ('Ctrl','Shift','u')]
            for sym in chord:self.state('key',sym,True)
            self.wait_interruptibly(.02)
            for sym in reversed(chord):self.state('key',sym,False)
            self.wait_interruptibly(.1)
            for digit in format(code,'x'):
                self.state('key',ord(digit),True);self.state('key',ord(digit),False)
                self.wait_interruptibly(.015)
            self.state('key',0xff0d,True);self.state('key',0xff0d,False)
            self.wait_interruptibly(.1)
        else:
            sym={'\n':0xff0d,'\t':0xff09}.get(char,code if 0x20<=code<=0xff else 0x01000000|code)
            self.state('key',sym,True);self.state('key',sym,False)
            self.wait_interruptibly(.005)

    def validate_action(self, a, in_sequence=False):
        if not isinstance(a, dict): raise ValueError('Action must be an object')
        kind = a.get('type')
        stroke_batch=a.get('stroke_batch',False)
        if type(stroke_batch) is not bool:raise ValueError('stroke_batch must be boolean')
        if 'stroke_batch' in a and (kind!='sequence' or in_sequence):raise ValueError('stroke_batch requires an outer sequence')
        if kind == 'sequence':
            steps = a.get('steps')
            limit=24 if stroke_batch else 8
            if in_sequence or not isinstance(steps,list) or not 1 <= len(steps) <= limit:
                raise ValueError('Provide 1..'+str(limit)+' non-nested steps')
            if any(not isinstance(step,dict) for step in steps):raise ValueError('Each step must be an object')
            if stroke_batch:
                first=steps[0]
                if len(steps)<2 or first.get('type')!='click' or first.get('button','left')!='left' or first.get('count',1)!=1 or set(first)-{'type','x','y','button','count'}:
                    raise ValueError('Stroke batch requires one observed single left focus click')
                if any(step.get('type')!='drag' or step.get('button','left')!='left' or set(step)-{'type','path','button'} for step in steps[1:]):
                    raise ValueError('Stroke batch permits only left-button drag strokes after focus')
            if not getattr(self,'target_guard',None) and steps[0].get('type') != 'click' and not self.activates_focus(steps[0]):
                raise ValueError('Sequence must begin with a target click or focus-acquiring shortcut')
            for step in steps: self.validate_action(step, True)
            estimated = sum(self.text_cost(x.get('text',''),x.get('text_mode','gnome_unicode')) + float(x.get('seconds',0)) + .3 + .02*len(x.get('path',[])) for x in steps)
            if estimated > 10: raise ValueError('Sequence exceeds 10-second estimated input budget')
            return
        if kind not in ('move','click','scroll','keys','text','drag','wait'):
            raise ValueError('Unknown action type')
        if 'focus' in a:
            f=a['focus']
            if kind not in ('keys','text') or not isinstance(f,dict) or set(f)!={'x','y'}:
                raise ValueError('focus is supported only for keys/text')
            self.validate_point(f.get('x'),f.get('y'))
        if kind in ('text','keys') and not in_sequence and 'focus' not in a and not self.activates_focus(a) and not getattr(self,'target_guard',None) and not (kind=='keys' and getattr(self,'window_transition',False)):
            raise ValueError('Input focus may have changed during approval. Supply focus:{x,y}, or use a sequence starting with a click/focus-acquiring shortcut.')
        if kind in ('move','click','scroll'):
            self.validate_point(a.get('x'),a.get('y'))
        if kind == 'click':
            if a.get('button','left') not in ('left','right','middle') or type(a.get('count',1)) is not int or a.get('count',1) not in (1,2,3):
                raise ValueError('Invalid button/count')
        if kind == 'scroll':
            if a.get('unit','steps')!='steps':raise ValueError('Smooth pixel scrolling is unreliable on this GNOME backend; use unit=steps')
            if any(type(a.get(k,0)) is not int or abs(a.get(k,0))>50 for k in ('dx','dy')):
                raise ValueError('Wheel steps must be integers in -50..50')
            for v in (a.get('dx',0),a.get('dy',0)):
                if not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>2000:
                    raise ValueError('Invalid scroll delta')
        if kind == 'text' and (not isinstance(a.get('text'),str) or len(a['text'])>4000):
            raise ValueError('Text must be <=4000 characters')
        if kind == 'text' and not in_sequence and self.text_cost(a['text'],a.get('text_mode','gnome_unicode'))+.6>10:
            raise ValueError('Text exceeds the 10-second input budget; split it into targeted calls')
        if kind=='text' and a.get('text_mode','gnome_unicode') not in ('gnome_unicode','keysyms'):
            raise ValueError('Unknown text_mode')
        if kind=='text' and any(0xd800<=ord(c)<=0xdfff for c in a['text']):raise ValueError('Invalid Unicode surrogate')
        if kind == 'text' and any((ord(c)<32 or 127<=ord(c)<=159) and c not in ('\n','\t') for c in a['text']):
            raise ValueError('Text contains unsupported control characters')
        if kind == 'keys':
            keys=a.get('keys')
            if not isinstance(keys,list) or not 1<=len(keys)<=8: raise ValueError('Provide 1..8 key names')
            if any(not isinstance(key,str) for key in keys):raise ValueError('Key names must be strings')
            for key in keys:self.keysym(key)
        if kind == 'drag':
            path=a.get('path')
            if not isinstance(path,list) or not 2<=len(path)<=200:raise ValueError('Invalid drag path')
            for point in path:
                if not isinstance(point,list) or len(point)!=2:raise ValueError('Invalid drag point')
                self.validate_point(*point)
        if kind in ('wait','move'):
            v=a.get('seconds',.25 if kind=='move' else .2)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=5:raise ValueError('Wait must be 0..5 seconds')

    def validate_point(self,x,y):
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (x,y)) or not (0<=x<self.width and 0<=y<self.height):
            raise ValueError('Position outside selected monitor')

    @staticmethod
    def activates_focus(a):
        keys=a.get('keys',[])
        return a.get('type')=='keys' and (keys in (['Super'],['Super_L']) or keys in (['Alt','F2'],['Alt_L','F2']))

    def action(self,a):
        with self.lock:
            self.transaction_info={'completed_steps':0,'failed_step':None,'input_events_attempted':0,'input_characters_completed':0}
            self.check()
            self.validate_action(a)
            target=getattr(self,'target_guard',None)
            steps=a['steps'] if a['type']=='sequence' else [a]
            if target is not None:
                if sum(len(step.get('text','')) for step in steps)>32:
                    raise ValueError('Identity-guarded text is limited to32characters per action; inspect and use short batches. Accessibility latency is additional to the input estimate.')
                if any(step['type'] not in ('keys','text','wait') and not (i==0 and step['type']=='click') for i,step in enumerate(steps)):
                    raise ValueError('Identity-guarded input supports keyboard/wait plus one initial focus click; use separate visual actions for pointer workflows')
                if any('focus' in step for step in steps[1:]):raise ValueError('Guarded focus acquisition belongs only in the first step')
                target.live()
            acquired=False
            # Approval/user activity may have moved the physical pointer. Never
            # interpolate from a cached position belonging to a previous call.
            self.pointer_position=None
            self.transition_activated=False
            reader=getattr(self,'pointer_reader',None)
            if reader is not None and any(step['type'] in ('move','click','drag','scroll') or 'focus' in step for step in steps):self.pointer_position=reader()
            self.action_deadline=time.monotonic()+15
            input_started=time.monotonic()
            try:
                for index,step in enumerate(steps):
                    self.transaction_info['failed_step']=index+1
                    self.check()
                    if 'focus' in step:
                        self._primitive({'type':'click','x':step['focus']['x'],'y':step['focus']['y']})
                        self.wait_interruptibly(.15)
                    if target is not None:
                        if index==0 and step['type']=='click':
                            self._primitive(step);target.acquire();acquired=True
                            self.transaction_info['completed_steps']+=1;self.transaction_info['failed_step']=None
                            continue
                        if not acquired:target.acquire();acquired=True
                        target.check()
                    self._primitive(step)
                    self.transaction_info['completed_steps']+=1
                    self.transaction_info['failed_step']=None
                self.check()
            finally:
                self.action_deadline=None
                self.release()
                self.transaction_info['input_duration_ms']=max(0,round((time.monotonic()-input_started)*1000))

    def _primitive(self, a):
        with self.lock:
            self.check()
            try:
                kind = a['type']
                if kind in ('move','click') and not all(k in a for k in ('x','y')):
                    raise ValueError('move/click requires x and y')
                if ('x' in a) != ('y' in a):
                    raise ValueError('Provide both x and y')
                if kind in ('click','scroll') and 'x' in a:
                    self.move_to(a['x'], a['y'],.2)
                if kind == 'move':
                    self.move_to(a['x'],a['y'],float(a.get('seconds',.25)))
                if kind == 'click':
                    button = {'left':272,'right':273,'middle':274}[a.get('button','left')]
                    count = int(a.get('count',1))
                    if count not in (1,2,3): raise ValueError('count must be 1..3')
                    for _ in range(count):
                        self.confirm_pointer_endpoint(a['x'],a['y'])
                        self.state('button',button,True)
                        self.wait_interruptibly(.04)
                        self.state('button',button,False)
                        self.wait_interruptibly(.07)
                elif kind == 'scroll':
                    endpoint=(a['x'],a['y']) if 'x' in a else getattr(self,'pointer_position',None)
                    if endpoint is None:
                        self.cancelled.set()
                        raise RuntimeError('Scroll endpoint unavailable; pointer effect refused')
                    self.confirm_pointer_endpoint(*endpoint)
                    dx, dy = float(a.get('dx',0)), float(a.get('dy',0))
                    if not all(map(math.isfinite,(dx,dy))) or max(abs(dx),abs(dy)) > 2000:
                        raise ValueError('Scroll deltas must be finite and <=2000')
                    for axis,delta in ((0,dy),(1,dx)):
                        if delta:self.notify('NotifyPointerAxisDiscrete','ui',axis,int(delta))
                elif kind == 'keys':
                    keys = a['keys']
                    if not isinstance(keys,list) or not 1 <= len(keys) <= 8:
                        raise ValueError('Provide 1..8 key names')
                    syms = [self.keysym(k) for k in keys]
                    for sym in syms: self.state('key',sym,True)
                    self.wait_interruptibly(.04)
                    for sym in reversed(syms): self.state('key',sym,False)
                elif kind == 'text':
                    value = a['text']
                    if not isinstance(value,str) or len(value)>4000:
                        raise ValueError('Text must be <=4000 characters')
                    for char in value:
                        self.type_character(char,a.get('text_mode','gnome_unicode'))
                        self.transaction_info['input_characters_completed']+=1
                elif kind == 'drag':
                    path = a['path']
                    if not isinstance(path,list) or not 2<=len(path)<=200:
                        raise ValueError('Drag path must contain 2..200 positions')
                    # Validate every point before pressing a button.
                    for x,y in path:
                        if not all(isinstance(v,(float,int)) and math.isfinite(v) for v in (x,y)) or not (0<=x<self.width and 0<=y<self.height):
                            raise ValueError('Invalid drag point')
                    self.position(*path[0])
                    self.confirm_pointer_endpoint(*path[0])
                    self.state('button',272,True)
                    for point in path[1:]:
                        self.position(*point)
                        self.wait_interruptibly(.02)
                    self.state('button',272,False)
                elif kind == 'wait':
                    seconds = float(a.get('seconds',.2))
                    if not math.isfinite(seconds) or not 0<=seconds<=5:
                        raise ValueError('Wait must be 0..5 seconds')
                    self.wait_interruptibly(seconds)
                elif kind != 'move' and kind not in ('click','scroll'):
                    raise ValueError('Unknown action type')
                # Pointer arrival is already observed. Capture applies its own
                # settling fence; do not add a blanket wait after every stroke,
                # move, wheel operation or an explicitly requested wait.
                if kind in ('click','keys','text'):
                    self.wait_interruptibly(.1)
            finally:
                if self.release():
                    raise RuntimeError('Input release failed; session closed and portal closure attempted. Check desktop_status and GNOME sharing indicator.')

    def pause_input(self):
        with self.lock:
            if self.cancelled.is_set() or not self.session:
                raise RuntimeError('Sharing closed while pausing')
            if self.release():raise RuntimeError('Virtual input release failed while pausing')
            self.pointer_position=None
            pipeline=self.pipeline
            if pipeline is not None:
                done=threading.Event();failure=[]
                def teardown():
                    try:pipeline.set_state(Gst.State.NULL)
                    except Exception:failure.append(True)
                    finally:done.set()
                threading.Thread(target=teardown,daemon=True).start()
                if not done.wait(2) or failure:raise RuntimeError('Capture suspension failed; sharing must close')
                self.pipeline=None
            self.action_deadline=None

    def resume_capture(self):
        # A fresh pipeline rejects buffered pre-pause frames. The PipeWire
        # remote and portal session remain the original consented resources.
        with self.lock:
            self.check()
            self._start_capture_pipeline()

    def close(self):
        with self.lock:
            self.cancelled.set()
            self.mapping_guard=None
            self.monitor_mapping=None
            # Close virtual devices before capture teardown, which can stall in Gst.
            if self.session:
                if not getattr(self,'portal_closed',False):
                    try:self.call('org.freedesktop.portal.Session','Close','()',(),path=self.session);self.portal_closed=True
                    except Exception:self.cleanup_warning='Portal closure could not be confirmed. End sharing in GNOME.'
                if getattr(self,'portal_closed',False):self.session=None
            try:self.release()
            except Exception:self.cleanup_warning='Input release failed; portal closure attempted. Check GNOME sharing.'
            if self.fd is not None:
                try:os.close(self.fd)
                except OSError:self.cleanup_warning='Capture descriptor cleanup failed; portal closure attempted.'
                finally:self.fd=None
            pipeline=self.pipeline;self.pipeline=None
            if pipeline:
                done=threading.Event();failure=[]
                def teardown():
                    try:pipeline.set_state(Gst.State.NULL)
                    except Exception:failure.append(True)
                    finally:done.set()
                threading.Thread(target=teardown,daemon=True).start()
                if not done.wait(2) or failure:self.cleanup_warning='Capture teardown incomplete; check GNOME sharing. Virtual session closure was attempted first.'
            if self.closed_sub:
                try:self.bus.signal_unsubscribe(self.closed_sub)
                except Exception:self.cleanup_warning='Portal signal cleanup failed; check GNOME sharing.'
                finally:self.closed_sub=None
            self.pointer_position=None
            self.confirmed_pointer_record=None

    def shutdown(self):
        self.shutdown_requested = True
        self.cancelled.set()
        self.close()
        self.loop.quit()


def text(value):
    return {'type':'text','text':json.dumps(value)}

def image(png):
    return {'type':'image','mimeType':'image/png','data':base64.b64encode(png).decode()}

ACTION_SCHEMA = {'type':'object','required':['type'],'properties':{
    'type':{'type':'string','enum':['move','click','scroll','keys','text','drag','wait']},
    'unit':{'type':'string','enum':['steps']},
    'text_mode':{'type':'string','enum':['gnome_unicode','keysyms']},
    'x':{'type':'number'},'y':{'type':'number'},'dx':{'type':'number'},'dy':{'type':'number'},
    'button':{'type':'string','enum':['left','right','middle']},'count':{'type':'integer','minimum':1,'maximum':3},
    'keys':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':8},
    'text':{'type':'string','maxLength':4000},
    'path':{'type':'array','minItems':2,'maxItems':200,'items':{'type':'array','items':{'type':'number'},'minItems':2,'maxItems':2}},
    'seconds':{'type':'number','minimum':0,'maximum':5},
    'focus':{'type':'object','properties':{'x':{'type':'number'},'y':{'type':'number'}},'required':['x','y'],'additionalProperties':False}},'additionalProperties':False}

import copy
STEP_SCHEMA=copy.deepcopy(ACTION_SCHEMA)
ACTION_SCHEMA['properties']['type']['enum'].append('sequence')
ACTION_SCHEMA['properties']['steps']={'type':'array','items':STEP_SCHEMA,'minItems':1,'maxItems':24}
ACTION_SCHEMA['properties']['stroke_batch']={'type':'boolean','default':False,'description':'Explicit stable-canvas drawing batch: one harmless observed single left focus click followed by up to23 left drag strokes. Same canvas, brush, colour and layout only; no UI transitions. Existing10-second estimated/15-second actual input budgets and interruption guards remain. Default sequences still max8.'}

def tools():
    specs=[
      ('desktop_start','Request personal GNOME consent for one monitor, keyboard and pointer; return a fresh screenshot. Optional cursor_glow temporarily changes the desktop-wide cursor theme and restores it on close.',{'context_change_policy':{'type':'string','enum':['close','pause-recover'],'default':'close','description':'Explicit native retained-sharing opt-in: ordinary foreground changes cancel pending work and recover a stable fresh context without replay or focus reclaim. A fresh observation is required before more input; protected UI and faults remain terminal.'},'multi_contact_policy':{'type':'string','enum':['close','pause-recover'],'default':'close','description':'Explicit retained native touchpad multi-contact intervention support through four fingers. Requires touchpad source and click_policy pause-return with exact MULTICONTACT1 acknowledgement. Waits through contact and private workspace UI until released quiet and stable ordinary context. No gesture emulation, pointer reclaim or motion credit; unsupported devices and faults remain terminal.'},'keyboard_policy':{'type':'string','enum':['close','pause-recover'],'default':'close','description':'Explicit physical keyboard intervention recovery after released quiet. Requires native retained sharing and click_policy pause-return with exact helper KEYPAUSE1 acknowledgement. Fresh ordinary context and no replay. All click/key interventions refresh context without pointer reclaim while enabled; Stop, locks and faults remain terminal.'},'click_policy':{'type':'string','enum':['close','pause-return'],'default':'close','description':'Explicit native retained-sharing opt-in: ordinary left/right/middle clicks pause, then after released quiet recover from a fresh context; no action replay or forced focus. Keys remain terminal unless keyboard_policy is selected; scrolling, protected UI and faults remain terminal.'},'allow_permission_wait':{'type':'boolean','default':False,'description':'Explicit native retained-sharing opt-in for trusted GNOME Polkit permission waiting for an already authorized task; human approval only. Requires helper AUTHMODE1 and observer protocol3.'},'startup_verification':{'type':'string','enum':['challenge','passive'],'default':'challenge','description':'Explicit passive supervised mode skips manual calibration and starts monitoring with coverage unverified. Requires native retained sharing and exact helper acknowledgement; automatic return additionally requires real selected-source motion in the current pause. Challenge retains diagnostic keyboard/pointer tests.'},'pointer_source':{'type':'string','enum':['mouse','touchpad'],'default':'mouse','description':'Retained native observation source. Touchpad requires physical_takeover and retain-sharing; verified single-finger indirect devices only.'},'session_seconds':{'type':'integer','minimum':120,'maximum':600,'default':120,'description':'Optional initial native-helper lease in seconds, physical_takeover required. Negotiated once before calibration; default120, hard maximum600. No active renewal; Stop and faults remain terminal.'},'physical_takeover':{'type':'boolean','default':False,'description':'Explicit opt-in to a separately installed native activity helper; administrator authorization follows personal GNOME sharing approval. Backend receives only coarse activity/fault notices, never raw input descriptors. Not human-provenance attestation.'},'cursor_glow':{'type':'boolean','description':'Explicit opt-in after explaining desktop-wide theme scope. Applies real themed cursor glow while active; custom app cursors may ignore it.'},'pointer_motion_return':{'type':'boolean','default':False,'description':'With retained sharing and native observation, yield on mouse movement and return once to the last confirmed point after physical quiet in the same app. No action replay.'},'interruption_policy':{'type':'string','enum':['close','retain-sharing'],'default':'close','description':'Opt-in retained consent for explicit pause/resume; physical observer faults remain terminal. No automatic cursor return or replay.'}}),
      ('desktop_observe','Return a fresh screenshot and dimensions. Optional inspect_target binds a single-use editable accessibility identity; inspect before input.',{'inspect_target':{'type':'boolean'}}),
      ('desktop_action','Perform bounded input and return a fresh screenshot. Text/keys need same-call focus or a sequence beginning with a target click/focus shortcut. Coordinates use logical_size. Discrete wheel steps only. Text uses GNOME Unicode composition by default; verify actual results. Never replay uncertain input.',{'action':ACTION_SCHEMA,'target_id':{'type':'string','minLength':32,'maxLength':32},'recovery_observation_id':{'type':'string'},'window_observation_id':{'type':'string','minLength':32,'maxLength':32},'window_fit_shared':{'type':'boolean','description':'Separate opt-in Alt+F10 resize toggle fitting the current oversized focused window to the shared monitor. Exactly two verified monitors; center/titlebar midpoint and strictly largest intersection must identify the shared monitor. Same-window full containment required after; no focus activation or retry.'},'window_normalize_for_move':{'type':'boolean','description':'Separate opt-in Alt+F10 resize toggle of the currently focused window on the other of two verified monitors before a later monitor move. Only a frame not wholly source-contained is admitted; origin and center must identify that source; same-window full source containment required after. No focus activation or content observation.'},'window_move_to_shared':{'type':'boolean','description':'Opt-in single Super+Shift+Arrow move of the currently focused window from the other monitor to the shared monitor; exactly two unambiguous monitors and unchanged configured shortcut required. No focus activation or unseen-content claim.'},'wait_for_permission':{'type':'boolean','description':'One observed package Install left click then capture/input-free trusted GNOME authentication waiting; requires startup allow_permission_wait, native retained sharing and recording_stopped=true. No approval automation or action replay.'},'recording_stopped':{'type':'boolean','description':'Explicit operator attestation all owned recorders are stopped and finalized before a permission-wait gesture; not proof about external recorders.'},'await_context_change':{'type':'boolean','description':'Explicit launch-only opt-in with focus_transition: one left click or Return, then require an actual foreground context change within a hard five-second budget before publishing an image. No replay or app-identity guarantee.'},'focus_transition':{'type':'boolean','description':'Only one explicit left click, launcher/Return or Ctrl+s/Ctrl+Shift+s/Ctrl+o gesture may change foreground; no remaining batch. Inspect its returned image before further input.'}}),
      ('desktop_pause','Cancel current work, release virtual input and stop capture. Retaining sharing requires interruption_policy=retain-sharing at startup.',{}),
      ('desktop_resume','Explicitly resume retained sharing with a fresh screenshot and new observation tokens. Never replays input.',{'pause_id':{'type':'string','minLength':32,'maxLength':32}}),
      ('desktop_status','Read session and cleanup state without capturing or sending input.',{}),
      ('desktop_close','Close this session and release virtual input, capture and the portal. This is resource cleanup; a later session requires fresh GNOME consent.',{})]
    return [{'name':n,'description':d,'inputSchema':{'type':'object','properties':props,'required':['action','window_observation_id'] if n=='desktop_action' else (['pause_id'] if n=='desktop_resume' else []),'additionalProperties':False},'annotations':{'readOnlyHint':n in ('desktop_status','desktop_observe'),'destructiveHint':n=='desktop_action','openWorldHint':True}} for n,d,props in specs]

class RecoveryLedger:
    """Bounded, nonsecret action outcome metadata; never replay desktop input."""
    def __init__(self):
        self.last=None
        self.inspection_required=False
        self.observation_id=None

    def snapshot(self):
        return {'inspection_required':self.inspection_required,
                'observation_id':self.observation_id,
                'last_result':dict(self.last) if self.last else None,
                'instruction':'Inspect the fresh image and current app state before deciding the next action. Never automatically repeat uncertain input.'}

    def begin(self,observation_id=None):
        if self.inspection_required:
            if not self.observation_id or observation_id!=self.observation_id:
                raise RuntimeError('Previous input may have taken effect. Call desktop_observe, inspect the image, then supply its recovery observation_id as recovery_observation_id. Do not blindly retry.')
        self.inspection_required=False
        self.observation_id=None
        self.last={'result_id':uuid.uuid4().hex,'outcome':'in_progress',
                   'completed_steps':0,'failed_step':None,'input_events_attempted':0,'input_characters_completed':0}

    def finish(self,progress,failed=False):
        if self.last is None:return
        for key in ('completed_steps','failed_step','input_events_attempted','input_characters_completed'):
            value=progress.get(key)
            if isinstance(value,int) and not isinstance(value,bool):self.last[key]=max(0,value)
            elif key=='failed_step':self.last[key]=None
        effects=self.last['input_events_attempted']>0
        self.last['outcome']='effects_uncertain' if failed and effects else ('failed_before_input' if failed else 'dispatched_and_observed')
        self.inspection_required=failed and effects
        self.observation_id=None

    def observed(self):
        if self.inspection_required:self.observation_id=uuid.uuid4().hex

PERMISSION_NO_PROMPT_GRACE=3

class ContextManualPause(RuntimeError):pass

class InterventionWaitExpired(RuntimeError):
    pass

class ContextRecoveryPending(RetainedPause):
    pass

CONTEXT_RECOVERY_SECONDS=15
CONTEXT_RECOVERY_QUIET=1.5

class PermissionWaitFailure(RuntimeError):
    pass

PERMISSION_FAILURE_REASONS=frozenset((
    'owner-changed','cancelled','deadline-expired','native-observer-ended','lease-ended',
    'observer-unavailable','observer-invalid-state','origin-changed','attempt-changed','attempt-unsupported',
    'prompt-disappeared','prompt-still-active','mapping-unavailable','mapping-changed',
    'native-begin-failed','native-end-failed','capture-suspension-failed','capture-resume-failed',
    'foreground-unavailable','publication-changed','action-failed','unexpected-failure',
    'blocked-unknown-system-ui','blocked-locked','blocked-greeter','blocked-observer-unavailable',
    'blocked-auth-observer-unsupported','blocked-auth-observer-unavailable','blocked-unavailable',
    'blocked-polkit-dialog-unavailable','blocked-origin-unavailable','blocked-origin-changed','blocked-modal-mismatch'))
PERMISSION_FAILURE_STAGES=frozenset(('preparing','waiting-for-prompt','waiting-for-human',
    'waiting-for-released-input','prompt-observed','prompt-not-observed'))

class PermissionSignal:
    # Signal receipt grants no authority and performs no blocking D-Bus work.
    # The waiting worker validates the trusted auth state before any resume.
    def changed(self,epoch):pass

class Server:
    def __init__(self,factory=Desktop):
        self.factory=factory;self.backend=None;self.cancel_token=None;self.request_epoch=None
        self.state_lock=threading.RLock();self.generation=0;self.state='closed';self.closure_reason=None
        # Opening a replacement session must wait until every owned resource
        # from the previous session has finished cleanup. Cancellation itself
        # never waits for this lock.
        self.lifecycle_lock=threading.RLock()
        self.execution_lock=threading.RLock()
        self.owner_cancel_events={}
        self.interruption_policy='close';self.pause_id=None;self.pause_reason=None;self.pause_fence_generation=-1;self.pause_watch_stop=None
        self.pointer_motion_return=False;self.consent_id=None;self.native_pause_epoch=None;self.keyboard_wait_deadline=None;self.keyboard_context_wait=None;self.manual_pause_requested=False;self.manual_pause_latch=None;self.intervention_latch=None;self.click_context_pending=None
        self.return_state='disabled';self.return_attempted=set();self.return_record=None
        self.recovery=RecoveryLedger();self.target_provider=None;self.target_record=None
        self.cursor_glow=None;self.cursor_glow_pending=None;self.cursor_glow_warning=None;self.cursor_glow_last=None
        self.physical_takeover=False;self.physical_takeover_warning=None;self.native_activity=None;self.native_activity_last=None;self.native_session_seconds=120;self.native_pointer_source="mouse";self.native_click_policy="close";self.native_keyboard_policy="close";self.native_multi_contact_policy="close";self.context_change_policy='close';self.context_recovery=None;self.context_observation_required=False;self.native_startup_verification='challenge';self.native_allow_permission_wait=False;self.permission_wait_stage=None;self.permission_wait_reason=None;self.permission_wait_failure_stage=None
        self.target_cleanup_warning=None;self.indicator=None;self.indicator_warning=None;self.window_record=None

    def own_observer(self,attribute,owner):
        with self.state_lock:
            self.owner_cancel_events[attribute]=(owner,self.backend.cancelled)
            setattr(self,attribute,owner)

    def cancel_observer(self,attribute,owner):
        # A tuple may be replaced after this read. Its event belongs only to
        # that consent session, so even a delayed callback cannot cancel a new
        # session. Never wait for publication/state locks to stop owned input.
        lease=self.owner_cancel_events.get(attribute)
        if lease is not None and lease[0] is owner:lease[1].set()

    def invalidate(self,expected_native=None,expected_indicator=None,warning=None,reason=None):
        conditional=expected_native is not None or expected_indicator is not None
        if expected_native is not None:self.cancel_observer('native_activity',expected_native)
        if expected_indicator is not None:self.cancel_observer('indicator',expected_indicator)
        if not conditional and self.backend:self.backend.cancelled.set()
        with self.state_lock:
            if expected_native is not None and self.native_activity is not expected_native:return False
            if expected_indicator is not None and self.indicator is not expected_indicator:return False
            if conditional and self.state not in ('opening','active','pausing','paused','resuming','auth-waiting'):return False
            if conditional and self.backend:self.backend.cancelled.set()
            # Fixed categories only: keep the initiating cause through cleanup
            # and downstream observer authorization loss; never export context.
            category=reason if reason in ('foreground-context-changed','requested-close','publication-foreground-fault','physical-activity','intervention-wait-expired') else ('native-observer-fault' if warning=='native' else ('foreground-observer-fault' if warning=='indicator' else 'session-invalidated'))
            if self.closure_reason is None:self.closure_reason=category
            if self.context_recovery is not None and self.context_recovery.get('phase') in ('admitting','settling','capturing'):self.context_recovery['phase']='cancelled'
            if self.state=='auth-waiting':
                cause={'native-observer-fault':'native-observer-ended','foreground-observer-fault':'observer-unavailable',
                    'foreground-context-changed':'origin-changed','requested-close':'cancelled'}.get(category)
                if cause:self.permission_diagnostic(cause)
            if warning=='native':self.physical_takeover_warning='Native activity observer fault; desktop session closed.'
            elif warning=='indicator':self.indicator_warning='Foreground observer heartbeat failed; session closed without retry.'
            self.generation+=1;self.state='closing';self.target_record=None;self.window_record=None
            return True

    def guard(self,allowed=None):
        if self.request_epoch is not None and self.request_epoch!=self.generation:
            if self.interruption_policy=='retain-sharing' and self.request_epoch<self.pause_fence_generation:
                raise RetainedPause('Queued work was discarded by pause; submit a new request after observing resume')
            raise RuntimeError('Request invalidated by session closure')
        if self.cancel_token is not None and self.cancel_token.is_set():
            if self.backend:self.backend.cancelled.set()
            raise RuntimeError('Request cancelled before further input/capture')
        if allowed is not None and self.state not in allowed:
            if self.state in ('pausing','paused') and self.interruption_policy=='retain-sharing':raise RetainedPause('Desktop input is paused; resume explicitly with the current pause_id')
            raise RuntimeError('Desktop session is not active')

    def status(self):
        raw=self.backend.status() if self.backend else {'active':False,'portal_closed_confirmed':True}
        raw.setdefault('held_input_count',0)
        raw.setdefault('input_release',{'attempted':0,'confirmed':0,'failed':0})
        native=self.native_activity.status() if self.native_activity is not None else (self.native_activity_last or {'active':False,'supported':False,'raw_device_fds':False})
        operation=getattr(self.backend,'operation_cancelled',None)
        active=bool(raw.get('active')) and self.state=='active' and not (operation is not None and operation.is_set())
        if self.physical_takeover and native.get('active') is not True:active=False
        if not raw.get('active') and self.state=='active':self.state='closed'
        try:disk_match=_runtime_build.fingerprint(os.path.dirname(__file__))==SERVER_BUILD
        except Exception:disk_match=False
        result=dict(raw,server_version=VERSION,server_build=SERVER_BUILD,server_disk_match=disk_match,active=active,session_state=self.state,
            capture_allowed=active,input_allowed=active and not self.recovery.inspection_required and not self.context_observation_required,context_change_policy=self.context_change_policy,context_observation_required=self.context_observation_required,closure_reason=self.closure_reason,
            sharing_active=bool(raw.get('active')),permission_wait_stage=self.permission_wait_stage,permission_wait_reason=self.permission_wait_reason,permission_wait_failure_stage=self.permission_wait_failure_stage,interruption_policy=self.interruption_policy,
            pause={'pause_id':self.pause_id,'reason':self.pause_reason,'automatic_return':self.pointer_motion_return,'automatic_resume':self.pointer_motion_return,
                'return_state':self.return_state},
            recovery=self.recovery.snapshot(),fresh_observation_required=not active or self.recovery.inspection_required or self.context_observation_required)
        if not active:result['logical_size']=[0,0]
        if self.target_cleanup_warning:result['accessibility_cleanup_warning']=self.target_cleanup_warning
        result['native_activity']=native
        result['physical_takeover']={'enabled':self.physical_takeover and native.get('active') is True,'classification':'native-device-source-activity','human_provenance':False}
        if self.physical_takeover_warning:result['physical_takeover_warning']=self.physical_takeover_warning
        if self.indicator_warning:result['indicator_warning']=self.indicator_warning
        result['cursor_glow']=self.cursor_glow.status() if self.cursor_glow else (self.cursor_glow_pending.status() if self.cursor_glow_pending else (self.cursor_glow_last or {'active':False}))
        if self.cursor_glow_warning:result['cursor_glow_warning']=self.cursor_glow_warning
        return result

    def intervention_context_wait_enabled(self):
        return self.native_keyboard_policy=='pause-recover' or self.native_multi_contact_policy=='pause-recover'

    def manual_pause_pending(self):
        latch=self.manual_pause_latch
        return self.manual_pause_requested or (latch is not None and latch[0] is self.backend and latch[1]==self.consent_id)

    def begin_pause(self,reason='manual',expected_native=None,expected_epoch=None):
        # Set the captured operation event before waiting for publication locks.
        # Never clear it: delayed work must retain its cancelled event forever.
        if self.interruption_policy!='retain-sharing':
            self.invalidate(expected_native=expected_native)
            return False
        if reason=='manual' and expected_native is None:self.manual_pause_requested=True
        backend=self.backend
        event=getattr(backend,'operation_cancelled',None)
        if expected_native is not None and self.native_activity is not expected_native:return False
        if expected_epoch is not None and not expected_native.is_current_yield(expected_epoch):return False
        if reason=='physical-click' and not expected_native.is_current_intervention(expected_epoch):return False
        if event is not None:event.set()
        with self.state_lock:
            if backend is not self.backend:return False
            if expected_native is not None and self.native_activity is not expected_native:return False
            if expected_epoch is not None and not expected_native.is_current_yield(expected_epoch):return False
            if reason=='physical-click' and not expected_native.is_current_intervention(expected_epoch):return False
            effective_reason='manual' if self.manual_pause_pending() else reason
            if self.state in ('pausing','paused') and self.pause_reason==effective_reason and (expected_epoch is None or self.native_pause_epoch==expected_epoch):return True
            if self.state not in ('active','resuming','pausing','paused'):raise RuntimeError('Only active sharing can pause')
            current=getattr(self.backend,'operation_cancelled',None)
            if current is not None:current.set()
            self.generation+=1;self.pause_fence_generation=self.generation
            self.state='pausing';self.pause_id=uuid.uuid4().hex
            self.pause_reason=effective_reason if effective_reason in ('manual','pointer-motion','physical-click','context-change') else 'manual'
            self.native_pause_epoch=expected_epoch
            if reason=='physical-click' and self.intervention_context_wait_enabled() and self.keyboard_wait_deadline is None:self.keyboard_wait_deadline=time.monotonic()+CONTEXT_RECOVERY_SECONDS
            self.return_record=getattr(backend,'confirmed_pointer_record',None)
            self.return_state='waiting-quiet' if self.pause_reason in ('pointer-motion','physical-click') and (self.pointer_motion_return or self.native_click_policy=='pause-return') else 'manual'
            self.target_record=None;self.window_record=None
            if self.indicator:self.indicator.armed=None
        return True

    def finish_pause(self,expected_pause_id=None):
        with self.lifecycle_lock:
            if expected_pause_id is not None and self.pause_id!=expected_pause_id:return False
            if self.state=='paused':return True
            if self.state!='pausing':raise RuntimeError('Pause was superseded by sharing closure')
            self.backend.pause_input()
            self.close_target_provider()
            self.pause_context_signature=self.window_guard_module().WindowGuard.signature if getattr(self.backend,'requires_window_guard',False) else None
            with self.state_lock:
                if self.state!='pausing' or self.backend.cancelled.is_set():raise RuntimeError('Sharing ended while pausing')
                self.state='paused'
                stop=threading.Event();self.pause_watch_stop=stop
                pause_id=self.pause_id;backend=self.backend;indicator=self.indicator
            def watch():
                while not stop.wait(.2):
                    if not self.check_pause_health(pause_id,backend,indicator):return
            threading.Thread(target=watch,daemon=True,name='retained-sharing-health').start()

    def pointer_yielded(self,controller,epoch):
        # This runs on the helper's sole reader: never wait for publication or
        # backend cleanup here. Keep heartbeat/fault/quiet consumption alive.
        event=getattr(self.backend,'operation_cancelled',None)
        if self.native_activity is not controller or not controller.is_current_yield(epoch):return
        if event is not None:event.set()
        context_record=self.context_recovery
        if context_record is not None and context_record.get('phase') in ('admitting','settling','capturing') and context_record['native'] is controller:
            context_record['native_yield']=epoch;return
        def suspend():
            pause_id=None
            try:
                if not self.begin_pause('pointer-motion',controller,epoch):return
                pause_id=self.pause_id
                self.finish_pause(pause_id)
            except Exception:
                with self.lifecycle_lock:
                    if self.native_activity is controller and self.pause_id==pause_id:self.native_activity_lost(controller,'Pause suspension failed')
        threading.Thread(target=suspend,daemon=True,name='pointer-motion-yield').start()

    def physical_intervention(self,controller,epoch):
        # Sole native reader callback: cancel the captured operation before any
        # publication lock. Consent/event ownership prevents stale cancellation.
        backend=self.backend;consent=self.consent_id
        event=getattr(backend,'operation_cancelled',None)
        if (self.native_click_policy!='pause-return' or self.native_activity is not controller or
            backend is not self.backend or consent!=self.consent_id or not controller.is_current_intervention(epoch)):return
        self.intervention_latch=(controller,backend,consent,epoch)
        if event is not None:event.set()
        context_record=self.context_recovery
        if context_record is not None and context_record.get('phase') in ('admitting','settling','capturing') and context_record['native'] is controller:
            context_record['native_yield']=epoch;return
        def suspend():
            pause_id=None
            try:
                if not self.begin_pause('physical-click',controller,epoch):return
                pause_id=self.pause_id
                self.finish_pause(pause_id)
            except Exception:
                with self.lifecycle_lock:
                    if self.native_activity is controller and self.pause_id==pause_id:self.native_activity_lost(controller,'Click pause suspension failed')
        threading.Thread(target=suspend,daemon=True,name='physical-click-pause').start()

    def pointer_quiet(self,controller,epoch):
        if not self.pointer_motion_return and self.native_click_policy!='pause-return':return
        threading.Thread(target=self.return_after_quiet,args=(controller,epoch),daemon=True,name='pointer-quiet-return').start()

    def return_after_quiet(self,controller,epoch):
        # Serialize with transport request context and response publication. A
        # source callback can still cancel the captured operation immediately.
        with self.execution_lock,self.lifecycle_lock:
            click_return=self.native_click_policy=='pause-return' and controller.is_current_intervention(epoch,quiet=True)
            if (not self.pointer_motion_return and not click_return) or self.interruption_policy!='retain-sharing' or self.manual_pause_pending():return False
            if self.state not in ('active','pausing','paused','resuming'):return False
            if self.native_activity is not controller or not controller.is_current_yield(epoch,quiet=True):return False
            if self.native_startup_verification=='passive' and not click_return:
                proof=getattr(controller,'motion_epoch',None)
                if type(proof) is not int or proof!=epoch:
                    self.return_state='waiting-motion-evidence';return False
            if click_return:
                try:return self.return_after_click(controller,epoch)
                except RetainedPause:return False
                except InterventionWaitExpired:
                    if self.native_activity is controller:self.invalidate(reason='intervention-wait-expired');self.close_backend()
                    return False
                except Exception:
                    if self.native_activity is controller:self.native_activity_lost(controller,'Click recovery context failed')
                    return False
            if getattr(controller,'intervention_epoch',None) is not None:return False
            if self.native_pause_epoch!=epoch:
                if not self.begin_pause('pointer-motion',controller,epoch):return False
            if self.pause_reason!='pointer-motion':return False
            self.finish_pause(self.pause_id)
            if self.state!='paused' or epoch in self.return_attempted:return False
            record=self.return_record
            if not record or record.get('consent_id')!=self.consent_id or record.get('session')!=self.backend.session:
                self.return_state='no-confirmed-point';return False
            mapping=getattr(self.backend,'monitor_mapping',None) or getattr(self.backend,'mapping_guard',None)
            if record.get('mapping') is not mapping:
                self.return_state='mapping-changed';self.invalidate();self.close_backend();return False
            try:
                self.backend.mapping_guard()
                module=self.window_guard_module()
                current=self.indicator.context()
                if module.WindowGuard.signature(current)!=record['context']:
                    self.return_state='foreground-changed';return False
                # A human moving onto another monitor never authorizes crossing
                # monitors to reclaim the old point.
                try:module.pointer_local(current,self.backend.monitor_geometry())
                except RuntimeError:self.return_state='pointer-outside-monitor';return False
                if not controller.is_current_yield(epoch,quiet=True):return False
                self.return_attempted.add(epoch);self.return_state='returning'
                self.resume_sharing({'pause_id':self.pause_id},return_record=record,expected_native=controller,expected_epoch=epoch)
                with self.state_lock:
                    if self.state!='active' or self.native_pause_epoch!=epoch:return False
                    self.return_state='returned'
                return True
            except RetainedPause:
                # A new motion epoch already cancelled this one. No correction,
                # no retry, and no old request's image may survive this yield.
                return False
            except Exception:
                if self.native_activity is controller:self.native_activity_lost(controller,'Pointer return failed')
                return False

    def return_after_click(self,controller,epoch):
        # Called under execution+lifecycle ownership. A click may select a new
        # ordinary window; never reclaim focus or replay the interrupted action.
        if self.manual_pause_pending() or not controller.is_current_intervention(epoch,quiet=True):return False
        if self.native_pause_epoch!=epoch or self.pause_reason!='physical-click':
            if not self.begin_pause('physical-click',controller,epoch):return False
        self.finish_pause(self.pause_id)
        if self.state!='paused' or epoch in self.return_attempted:return False
        self.backend.mapping_guard()
        module=self.window_guard_module();context=self.indicator.context()
        if self.keyboard_private_wait(context):
            self.keyboard_context_wait={'pause_id':self.pause_id,'epoch':epoch,'signature':None,'since':None}
            self.return_state='waiting-context';return False
        pending=self.keyboard_context_wait
        if pending is not None and pending['pause_id']==self.pause_id:
            if pending['epoch']!=epoch:raise RetainedPause('Private context epoch changed')
            if pending['signature']!=module.WindowGuard.signature(context):
                pending['signature']=None;pending['since']=None;self.return_state='waiting-context';return False
            if time.monotonic()>=self.keyboard_wait_deadline:raise InterventionWaitExpired('Physical intervention context wait expired')
            if pending['since'] is None or time.monotonic()-pending['since']<CONTEXT_RECOVERY_QUIET:return False
        signature=module.WindowGuard.signature(context)
        if context.get('kind')!='window':raise RuntimeError('Click recovery requires an ordinary foreground window')
        record=self.return_record
        mapping=getattr(self.backend,'monitor_mapping',None) or getattr(self.backend,'mapping_guard',None)
        # The coarse intervention token deliberately carries no key identity.
        # Keyboard opt-in therefore suppresses pointer reclaim for every such token.
        eligible=(not self.intervention_context_wait_enabled() and record is not None and record.get('consent_id')==self.consent_id and
                  record.get('session')==self.backend.session and record.get('mapping') is mapping and record.get('context')==signature)
        if eligible:
            try:module.pointer_local(context,self.backend.monitor_geometry())
            except RuntimeError:eligible=False
        if not controller.is_current_intervention(epoch,quiet=True) or self.manual_pause_pending():return False
        self.return_attempted.add(epoch);self.return_state='returning' if eligible else 'refreshing-context'
        self.resume_sharing({'pause_id':self.pause_id},return_record=record if eligible else None,
                            expected_native=controller,expected_epoch=epoch,click_return=True,click_context=signature)
        if self.state=='active':self.return_state='returned' if eligible else 'context-refreshed'
        return self.state=='active'

    def keyboard_inert_context(self,context):
        if context.get('available') is True and context.get('kind')=='overview':
            self.window_guard_module().WindowGuard.signature(context);return True
        epoch=context.get('epoch')
        return (set(context)=={'available','epoch','reason'} and context.get('available') is False and
                type(epoch) is int and epoch>=0 and context.get('reason') in ('no-foreground-window','system-ui'))

    def keyboard_private_wait(self,context):
        # Metadata-only waiting is never authority to capture or control shell UI.
        if not self.keyboard_inert_context(context):return False
        native=self.native_activity
        if (not self.intervention_context_wait_enabled() or self.pause_reason not in ('physical-click','manual') or
            self.state!='paused' or native is None or not native.is_current_intervention(self.native_pause_epoch)):return False
        if self.keyboard_wait_deadline is None or time.monotonic()>=self.keyboard_wait_deadline:raise InterventionWaitExpired('Physical intervention context wait expired')
        return True

    def check_pause_health(self,pause_id,backend,indicator):
        # Pausing capture/input must not suspend lock, observer or layout checks.
        # A retired watch cannot close a resumed or replacement consent session.
        if self.state!='paused' or self.pause_id!=pause_id:return False
        try:
            if backend.cancelled.is_set() or not backend.status().get('active'):raise RuntimeError('Sharing ended')
            if getattr(backend,'requires_window_guard',False):
                backend.mapping_guard()
                context=indicator.context()
                if self.backend is not backend or self.indicator is not indicator or self.state!='paused' or self.pause_id!=pause_id:return False
                if self.keyboard_private_wait(context):
                    self.keyboard_context_wait={'pause_id':pause_id,'epoch':self.native_pause_epoch,'signature':None,'since':None}
                    self.return_state='waiting-context'
                else:
                    signature=self.pause_context_signature(context)
                    pending=self.keyboard_context_wait;native=self.native_activity
                    if pending is not None and pending['pause_id']==pause_id:
                        if time.monotonic()>=self.keyboard_wait_deadline:raise InterventionWaitExpired('Physical intervention context wait expired')
                        if context.get('kind')!='window':raise RuntimeError('Intervention recovery requires an ordinary window')
                        now=time.monotonic()
                        if pending['signature']!=signature:pending['signature']=signature;pending['since']=now
                        if (not self.manual_pause_pending() and now-pending['since']>=CONTEXT_RECOVERY_QUIET and
                            native is not None and native.is_current_intervention(pending['epoch'],quiet=True) and self.return_state=='waiting-context'):
                            self.return_state='context-ready'
                            self.pointer_quiet(native,pending['epoch'])
            return True
        except Exception as error:
            with self.lifecycle_lock:
                with self.state_lock:
                    if self.backend is not backend or self.indicator is not indicator or self.state!='paused' or self.pause_id!=pause_id:return False
                    self.invalidate(reason='intervention-wait-expired' if isinstance(error,InterventionWaitExpired) else None)
                self.close_backend()
            return False

    def resume_sharing(self,args,return_record=None,expected_native=None,expected_epoch=None,click_return=False,click_context=None):
        with self.lifecycle_lock:
            self.guard(('paused',))
            if not self.pause_id or args.get('pause_id')!=self.pause_id:
                raise RetainedPause('Stale or missing pause_id; sharing remains paused')
            pause_id=self.pause_id
            if (return_record is not None or click_return) and self.manual_pause_pending():raise RetainedPause('Manual pause superseded automatic return')
            self.require_runtime()
            if self.backend.cancelled.is_set() or not self.backend.status().get('active'):
                raise RuntimeError('Sharing consent ended while paused')
            mapping=getattr(self.backend,'mapping_guard',None)
            if getattr(self.backend,'requires_window_guard',False):
                if not callable(mapping):raise RuntimeError('Verified monitor mapping unavailable')
                mapping()
            if self.intervention_context_wait_enabled() and self.keyboard_wait_deadline is not None:
                context=self.indicator.context()
                if self.keyboard_private_wait(context):
                    if self.keyboard_context_wait is None:self.keyboard_context_wait={'pause_id':pause_id,'epoch':self.native_pause_epoch,'signature':None,'since':None}
                    self.return_state='waiting-context'
                    raise RetainedPause('Private context remains suspended')
                signature=self.window_guard_module().WindowGuard.signature(context)
                if context.get('kind')!='window':raise RetainedPause('Ordinary context is required before resuming')
                pending=self.keyboard_context_wait
                if pending is not None:
                    if time.monotonic()>=self.keyboard_wait_deadline:raise InterventionWaitExpired('Physical intervention context wait expired')
                    if (pending['pause_id']!=pause_id or pending['epoch']!=self.native_pause_epoch or pending['signature']!=signature or
                        pending['since'] is None or time.monotonic()-pending['since']<CONTEXT_RECOVERY_QUIET):raise RetainedPause('Private context is not yet stable')
            if self.physical_takeover:
                native=self.native_activity
                if native is None or (expected_native is not None and native is not expected_native):
                    raise RuntimeError('Native observer is unavailable; a new consent session is required')
                if self.pause_reason=='pointer-motion' or native.status().get('yielded') is True:
                    epoch=(self.native_pause_epoch if self.native_pause_epoch is not None else native.status().get('yield_epoch')) if expected_epoch is None else expected_epoch
                    if not native.is_current_yield(epoch,quiet=True):raise RetainedPause('Physical pointer is not quiet; sharing remains paused')
                    try:
                        clicked=self.native_click_policy=='pause-return' and native.is_current_intervention(epoch,quiet=True)
                        if click_return and not clicked:raise RetainedPause('Click recovery epoch changed')
                        if clicked:native.resume_from_pause(epoch,click_return=True)
                        else:native.resume_from_pause(epoch)
                    except Exception:
                        current=native.status()
                        if self.native_activity is native and self.state in ('pausing','paused') and current.get('yielded') is True and current.get('yield_epoch')!=epoch:
                            raise RetainedPause('New pointer motion interrupted native resume') from None
                        raise
                    if self.pause_id!=pause_id or self.state!='paused':raise RetainedPause('A new motion replaced this resume')
                if native.status().get('active') is not True:raise RuntimeError('Native observer did not resume')
            with self.state_lock:
                self.guard(('paused',))
                if self.pause_id!=pause_id:raise RetainedPause('A new motion replaced this resume')
                if (return_record is not None or click_return) and self.manual_pause_pending():raise RetainedPause('Manual pause superseded automatic return')
                if return_record is None and not click_return:self.manual_pause_requested=False;self.manual_pause_latch=None;self.intervention_latch=None;self.click_context_pending=None
                if self.pause_watch_stop:self.pause_watch_stop.set()
                self.pause_watch_stop=None
                self.state='resuming';self.generation+=1;self.pause_fence_generation=self.generation
                if self.request_epoch is not None:self.request_epoch=self.generation
                self.click_context_pending=None
                self.backend.operation_cancelled=threading.Event()
                self.backend.request_cancel=self.cancel_token
                self.backend.pointer_position=None
                self.pause_id=None
            if click_return:
                if self.manual_pause_pending():raise RetainedPause('Manual pause superseded click recovery')
                module=self.window_guard_module()
                if module.WindowGuard.signature(self.indicator.context())!=click_context:raise RuntimeError('Foreground changed during click recovery')
            if return_record is not None:
                if self.manual_pause_pending():
                    self.begin_pause('manual');self.finish_pause()
                    raise RetainedPause('Manual pause superseded automatic return')
                module=self.window_guard_module()
                baseline=return_record['context']
                guard=module.WindowGuard(self.indicator,self.indicator.context(),lambda:self.foreground_lost(self.indicator))
                if guard.baseline!=baseline:raise RuntimeError('Foreground changed before pointer return')
                geometry=self.backend.monitor_geometry()
                self.backend.pointer_reader=lambda:module.pointer_local(self.read_window_context(),geometry)
                self.backend.window_guard=guard;self.backend.endpoint_context=baseline
                self.indicator.armed=guard
                try:self.backend.position(*return_record['point'])
                finally:self.backend.pointer_reader=None;self.backend.window_guard=None;self.backend.endpoint_context=None
            if (return_record is not None or click_return) and self.manual_pause_pending():
                self.begin_pause('manual');self.finish_pause()
                raise RetainedPause('Manual pause superseded automatic capture')
            self.backend.resume_capture()
            content=self.capture_result(('resuming',),return_record['context'] if return_record is not None else click_context)
            if click_return:self.backend.mapping_guard()
            self.pause_reason=None;self.keyboard_wait_deadline=None;self.keyboard_context_wait=None
            return content

    def require_runtime(self):
        try:require_current_runtime()
        except RuntimeError:
            self.invalidate();self.close_backend()
            raise

    def permission_diagnostic(self,reason):
        category=reason if type(reason) is str and reason in PERMISSION_FAILURE_REASONS else 'unexpected-failure'
        if self.permission_wait_reason is None:
            self.permission_wait_reason=category
            stage=self.permission_wait_stage
            self.permission_wait_failure_stage=stage if stage in PERMISSION_FAILURE_STAGES else 'not-started'

    def permission_fail(self,reason,record=None):
        # Fixed categories only. Never stringify exception details, application
        # text, authentication fields, identifiers, input or dialog contents.
        category=reason if type(reason) is str and reason in PERMISSION_FAILURE_REASONS else 'unexpected-failure'
        owned=record is None or (self.backend is record['backend'] and self.consent_id==record['consent'])
        if owned:self.permission_diagnostic(category)
        raise PermissionWaitFailure(category)

    def permission_auth_state(self,record=None,publishing=False):
        try:value=self.indicator.auth_state()
        except Exception:
            if record is not None:self.permission_check(record,publishing=publishing)
            self.permission_fail('observer-unavailable',record)
        if record is not None:self.permission_check(record,publishing=publishing)
        if type(value) is not dict or value.get('auth_state') not in ('none','pending','visible','blocked'):
            self.permission_fail('observer-invalid-state',record)
        if value['auth_state']=='blocked':
            reason=value.get('reason')
            category='blocked-'+reason if type(reason) is str and 'blocked-'+reason in PERMISSION_FAILURE_REASONS else 'observer-invalid-state'
            self.permission_fail(category,record)
        return value

    def permission_context(self,record=None):
        try:return self.read_window_context()
        except Exception:
            if record is not None:self.permission_check(record)
            self.permission_fail('foreground-unavailable',record)

    def permission_check(self,record,publishing=False):
        if (self.backend is not record['backend'] or self.native_activity is not record['controller'] or
            self.consent_id!=record['consent'] or self.generation!=record['generation'] or self.state!=('active' if publishing else 'auth-waiting')):
            if self.backend is record['backend'] and self.consent_id==record['consent']:
                cause={'native-observer-fault':'native-observer-ended','foreground-observer-fault':'observer-unavailable',
                    'foreground-context-changed':'origin-changed','requested-close':'cancelled'}.get(self.closure_reason)
                if cause:self.permission_fail(cause,record)
            self.permission_fail('owner-changed',record)
        try:self.guard()
        except Exception:self.permission_fail('cancelled',record)
        if time.monotonic()>=record['deadline']:self.permission_fail('deadline-expired',record)
        if self.backend.cancelled.is_set() or self.manual_pause_pending() or (getattr(self.backend,'operation_cancelled',None) is not None and self.backend.operation_cancelled.is_set()):
            self.permission_fail('cancelled',record)
        try:native_active=record['controller'].status().get('active') is True
        except Exception:self.permission_fail('native-observer-ended',record)
        if not native_active:self.permission_fail('native-observer-ended',record)
        authorized=getattr(record['controller'],'_yield_authorized',None)
        if callable(authorized) and not authorized():self.permission_fail('lease-ended',record)
        if time.monotonic()>=record['deadline']:self.permission_fail('deadline-expired',record)

    def permission_state(self,record):
        self.permission_check(record)
        value=self.permission_auth_state(record)
        self.permission_check(record)
        if value.get('auth_state') not in ('none','pending','visible'):self.permission_fail('observer-invalid-state',record)
        if value.get('origin_window_id')!=record['origin']:self.permission_fail('origin-changed',record)
        return value

    def prepare_permission_wait(self,context):
        self.permission_wait_reason=None;self.permission_wait_failure_stage=None;self.permission_wait_stage='preparing'
        controller=self.native_activity;backend=self.backend
        origin=context['window_id']
        initial=self.permission_auth_state()
        self.guard(('active',))
        if initial.get('auth_state')!='none' or initial.get('origin_window_id')!=origin:self.permission_fail('origin-changed')
        current=self.permission_context()
        if self.window_guard_module().WindowGuard.signature(current)!=self.window_guard_module().WindowGuard.signature(context):self.permission_fail('origin-changed')
        record={'backend':backend,'controller':controller,'consent':self.consent_id,'generation':self.generation,
            'origin':origin,'previous_attempt':initial.get('attempt_id'),'deadline':time.monotonic()+120,'epoch':None,'action_category':None}
        self.permission_signal=PermissionSignal()
        self.state='auth-waiting';self.permission_wait_stage='preparing'
        # The separate recorder must have been finalized by the operator. This
        # suspends only this backend capture; it cannot stop external recorders.
        try:backend.pause_input()
        except Exception:self.permission_fail('capture-suspension-failed',record)
        self.permission_check(record)
        try:record['epoch']=controller.begin_auth_wait()
        except Exception:self.permission_fail('native-begin-failed',record)
        self.permission_check(record)
        self.permission_wait_stage='waiting-for-prompt'
        return record

    def finish_permission_wait(self,record):
        # The single reserved activation click is already complete. No further
        # task input or screenshots occur until the trusted attempt has ended.
        self.backend.action_deadline=None
        self.indicator.armed=self.permission_signal
        attempt=None;seen_visible=False;grace_deadline=min(record['deadline'],time.monotonic()+PERMISSION_NO_PROMPT_GRACE)
        while True:
            value=self.permission_state(record);state=value['auth_state']
            if state in ('pending','visible'):
                token=value.get('attempt_id')
                category=value.get('action_category')
                if category!='system-authentication':self.permission_fail('attempt-unsupported',record)
                if record['action_category'] is not None and category!=record['action_category']:self.permission_fail('attempt-changed',record)
                record['action_category']=category
                if not isinstance(token,str) or len(token)!=32:self.permission_fail('observer-invalid-state',record)
                if token==record['previous_attempt'] or (attempt is not None and token!=attempt):self.permission_fail('attempt-changed',record)
                attempt=token;seen_visible|=state=='visible'
                self.permission_wait_stage='waiting-for-human'
            elif seen_visible:
                if value.get('attempt_id')!=attempt:self.permission_fail('attempt-changed',record)
                break
            elif attempt is not None:self.permission_fail('prompt-disappeared',record)
            else:
                if value.get('attempt_id')!=record['previous_attempt']:self.permission_fail('attempt-changed',record)
                current=self.permission_context(record);self.permission_check(record)
                if current.get('kind')!='window' or current.get('window_id')!=record['origin']:self.permission_fail('origin-changed',record)
                self.permission_mapping_check()
                self.permission_check(record)
                if time.monotonic()>=grace_deadline:
                    attempt=record['previous_attempt'];break
            self.permission_check(record)
            if self.backend.cancelled.wait(.05):self.permission_fail('cancelled',record)
        self.permission_wait_stage='waiting-for-released-input'
        try:record['controller'].end_auth_wait(record['epoch'])
        except Exception:self.permission_fail('native-end-failed',record)
        value=self.permission_state(record)
        if value.get('auth_state')!='none':self.permission_fail('prompt-still-active',record)
        if value.get('attempt_id')!=attempt:self.permission_fail('attempt-changed',record)
        current=self.permission_context(record)
        self.permission_check(record)
        if current.get('kind')!='window' or current.get('window_id')!=record['origin']:self.permission_fail('origin-changed',record)
        self.permission_mapping_check()
        self.permission_check(record)
        try:self.backend.resume_capture()
        except Exception:self.permission_fail('capture-resume-failed',record)
        self.permission_check(record)
        result=self.capture_result(('auth-waiting',),self.window_guard_module().WindowGuard.signature(current))
        record['attempt']=attempt
        self.permission_publish_check(record)
        self.window_record['permission_binding']=record
        self.permission_wait_stage='prompt-observed' if seen_visible else 'prompt-not-observed'
        if self.indicator:self.indicator.armed=None
        return result

    def permission_publish_check(self,record):
        self.permission_check(record,publishing=True)
        self.permission_mapping_check()
        self.permission_check(record,publishing=True)
        value=self.permission_auth_state(record,publishing=True)
        self.permission_check(record,publishing=True)
        if value.get('auth_state')!='none' or value.get('origin_window_id')!=record['origin'] or value.get('attempt_id')!=record['attempt']:
            self.permission_fail('publication-changed',record)

    def permission_mapping_check(self):
        mapping=getattr(self.backend,'mapping_guard',None)
        if not callable(mapping):self.permission_fail('mapping-unavailable')
        try:mapping()
        except Exception:self.permission_fail('mapping-changed')

    def startup_status_snapshot(self):
        # Only coarse Python-owned fields: no backend/GUI calls or authority writes.
        if not self.state_lock.acquire(blocking=False):return None
        try:
            if self.state in ('active','pausing','paused','resuming') and self.context_recovery_owned() and self.context_recovery.get('phase') in ('admitting','settling'):
                return {'server_version':VERSION,'server_build':SERVER_BUILD,'session_state':'context-settling','active':False,
                    'capture_allowed':False,'input_allowed':False,'snapshot_kind':'context-recovery-read-only',
                    'fresh_observation_required':True,'portal_closed_confirmed':False,'held_input_count':None}
            if self.state=='auth-waiting':
                return {'server_version':VERSION,'server_build':SERVER_BUILD,'session_state':'auth-waiting',
                    'active':False,'capture_allowed':False,'input_allowed':False,'snapshot_kind':'permission-wait-read-only',
                    'permission_wait_stage':self.permission_wait_stage,'permission_wait_reason':self.permission_wait_reason,'permission_wait_failure_stage':self.permission_wait_failure_stage,'portal_closed_confirmed':False,'held_input_count':None}
            if self.state!='opening':return None
            controller=self.native_activity
            native={'active':False,'calibration_state':'not-started','calibration_verified':False,
                'post_arm_required':False,'post_arm_state':'not-started','post_arm_verified':False,
                'post_arm_remaining_seconds':None,'readiness_stage':'calibration'}
            if controller is not None:
                state=getattr(controller,'calibration_state','not-started')
                native['calibration_state']=state if state in ('not-started','settling','waiting','challenge-seen','verified','failed') else 'not-started'
                native['calibration_verified']=state=='verified' and getattr(controller,'calibration_verified',False) is True
                native['calibration_resets']=min(2,max(0,getattr(controller,'calibration_resets',0)))
                required=getattr(controller,'retain_sharing',False) is True
                phase=getattr(controller,'post_arm_state','not-started')
                phases=('not-started','waiting-motion','waiting-quiet','resuming','verified','failed')
                phase=phase if isinstance(phase,str) and phase in phases else 'not-started'
                native['post_arm_required']=required
                native['post_arm_state']=phase
                native['post_arm_verified']=required and phase=='verified' and getattr(controller,'post_arm_verified',False) is True
                native['readiness_stage']='ready' if native['post_arm_verified'] else ('post-arm-pointer' if required and phase!='not-started' else 'calibration')
                deadline=getattr(controller,'post_arm_deadline_monotonic',None)
                if required and phase in ('waiting-motion','waiting-quiet','resuming') and type(deadline) in (int,float) and math.isfinite(deadline):
                    native['post_arm_remaining_seconds']=min(30,max(0,math.ceil(deadline-time.monotonic())))
                notice_phase=getattr(controller,'notice_phase','calibration')
                if notice_phase not in ('calibration','post-arm-pointer'):notice_phase=None
                native['calibration_notice']={'requested':getattr(controller,'notice_requested',False) is True,
                    'phase':notice_phase,
                    'request_acknowledged':getattr(controller,'notice_acknowledged',False) is True,
                    'request_active':getattr(controller,'notice_active',False) is True,
                    'delivery_unknown':getattr(controller,'notice_delivery_unknown',False) is True,
                    'visibility_verified':False}
                if getattr(controller,'startup_verification','challenge')=='passive':
                    native.update(startup_verification='passive',calibration_state='not-requested',
                        calibration_verified=False,post_arm_required=False,post_arm_state='not-required-passive',
                        post_arm_verified=False,post_arm_remaining_seconds=None,coverage_verified=False,
                        readiness_stage='passive-startup')
                    native['calibration_notice'].update(requested=False,phase=None,request_acknowledged=False,request_active=False)
            return {'server_version':VERSION,'server_build':SERVER_BUILD,
                'session_state':'opening','active':False,'capture_allowed':False,'input_allowed':False,
                'startup_snapshot':True,'snapshot_kind':'startup-read-only',
                'portal_closed_confirmed':False,'held_input_count':None,'native_activity':native}
        finally:self.state_lock.release()

    def preflight_context(self):
        self.require_runtime()
        path=os.path.join(os.path.dirname(__file__),'indicator_bridge.py')
        spec=importlib.util.spec_from_file_location('desktop_indicator_preflight',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        bridge=module.IndicatorBridge(self.status);bridge.preflight();return bridge

    def native_activity_module(self):
        self.require_runtime()
        path=os.path.join(os.path.dirname(__file__),'native_activity.py')
        spec=importlib.util.spec_from_file_location('desktop_native_activity',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def preflight_physical_guard(self):
        # No portal, backend construction or administrator prompt before validation.
        self.native_activity_module().validate_helper()

    def calibration_notice_module(self):
        self.require_runtime()
        path=os.path.join(os.path.dirname(__file__),'calibration_notice.py')
        spec=importlib.util.spec_from_file_location('desktop_calibration_notice',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def require_native_ready(self):
        status=self.native_activity.status() if self.native_activity is not None else {}
        if status.get('active') is not True:raise RuntimeError('Native activity observer did not arm')
        if self.native_multi_contact_policy=='pause-recover' and (status.get('multi_contact_policy')!='pause-recover' or status.get('multi_contact_wait_supported') is not True):raise RuntimeError('Multi-contact recovery acknowledgement is unavailable')
        if self.native_keyboard_policy=='pause-recover' and (status.get('keyboard_policy')!='pause-recover' or status.get('keyboard_wait_supported') is not True):raise RuntimeError('Keyboard recovery acknowledgement is unavailable')
        if self.native_startup_verification=='passive':
            if (status.get('startup_verification')!='passive' or status.get('readiness_kind')!='passive-unverified' or
                status.get('passive_acknowledged') is not True or status.get('monitor_armed') is not True or
                status.get('calibration_verified') is not False or status.get('post_arm_verified') is not False):
                raise RuntimeError('Passive observer acknowledgement is unverified; capture and input refused')
            return
        if self.interruption_policy=='retain-sharing' and (status.get('post_arm_verified') is not True or status.get('post_arm_state')!='verified'):
            raise RuntimeError('Post-ARM mouse readiness is unverified; capture and input refused')

    def enable_physical_guard(self):
        if self.native_activity is not None:raise RuntimeError('Native activity observer already owned')
        self.guard(('opening','active'))
        if self.backend is None or self.backend.status().get('active') is not True:raise RuntimeError('Personal portal consent is required before calibration notification')
        module=self.native_activity_module()
        notice=self.calibration_notice_module().CalibrationNotice()
        if self.native_pointer_source=='touchpad':
            notice.BODY='Press and release Shift, move one finger on the touchpad, then lift it and keep your hands still.'
            notice.RESET_BODY='Again: press and release Shift, move one finger on the touchpad, then lift it and keep your hands still.'
            notice.POST_ARM_SUMMARY='Desktop control touchpad readiness'
            notice.POST_ARM_BODY='Move one finger on the touchpad briefly, then lift it. Do not click or press keys.'
        controller=module.Controller(
            active=lambda:self.state in ('opening','active','pausing','paused','resuming','auth-waiting') and self.backend is not None and self.backend.status().get('active') is True,
            on_activity=lambda:self.native_activity_lost(controller),
            on_fault=lambda error:self.native_activity_lost(controller,error),notice=notice,
            retain_sharing=self.interruption_policy=='retain-sharing',
            on_yield=self.pointer_yielded,on_quiet=self.pointer_quiet,
            **({'session_seconds':self.native_session_seconds} if self.native_session_seconds!=120 else {}),
            **({'pointer_source':self.native_pointer_source} if self.native_pointer_source!='mouse' else {}),
            **({'click_policy':self.native_click_policy,'on_intervention':self.physical_intervention} if self.native_click_policy!='close' else {}),
            **({'multi_contact_policy':self.native_multi_contact_policy} if self.native_multi_contact_policy!='close' else {}),
            **({'keyboard_policy':self.native_keyboard_policy} if self.native_keyboard_policy!='close' else {}),
            **({'startup_verification':self.native_startup_verification} if self.native_startup_verification!='challenge' else {}),
            **({'allow_permission_wait':True} if self.native_allow_permission_wait else {}))
        # Publish ownership atomically with callback invalidation checks.
        self.own_observer('native_activity',controller)
        controller.start()
        self.require_native_ready()
        self.guard(('opening','active'))
        self.require_runtime()
        self.physical_takeover=True
        self.physical_takeover_warning=('Supervised passive observation: fresh keyboard/pointer coverage has not been calibrated.'
            if self.native_startup_verification=='passive' else None)

    def native_activity_lost(self,expected,error=None):
        if not self.invalidate(expected_native=expected,warning='native' if error else None,reason='physical-activity' if error is None else None):return
        def cleanup():
            self.close_backend(expected_native=expected)
        threading.Thread(target=cleanup,daemon=True).start()

    def show_indicator(self):
        self.require_runtime()
        if self.factory is not Desktop:return
        try:
            path=os.path.join(os.path.dirname(__file__),'indicator_bridge.py')
            spec=importlib.util.spec_from_file_location('desktop_indicator',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            bridge=module.IndicatorBridge(self.status)
            self.own_observer('indicator',bridge)
            bridge.on_failure=lambda:self.indicator_failed(bridge)
            self.indicator.start();self.indicator_warning=None
        except Exception:
            if self.indicator:self.indicator.close()
            with self.state_lock:
                self.owner_cancel_events.pop('indicator',None)
                self.indicator=None;self.indicator_warning='Foreground observer or pointer label unavailable; guarded desktop control is refused.'

    def indicator_failed(self,expected=None):
        if not self.invalidate(expected_indicator=expected,warning='indicator'):return
        self.close_backend(expected_indicator=expected)

    def cursor_glow_config(self):
        path=os.path.join(os.path.dirname(__file__),'cursor_theme_config.json')
        if os.path.getsize(path)>4096:raise RuntimeError('Invalid cursor theme configuration')
        with open(path) as f:config=json.load(f)
        if not isinstance(config,dict) or not all(isinstance(config.get(key),str) for key in ('theme','theme_root','state_dir')):raise RuntimeError('Cursor theme is not installed')
        return config

    def recover_cursor_glow(self):
        if self.factory is not Desktop:return
        try:
            config=self.cursor_glow_config()
            service=os.path.join(os.path.dirname(__file__),'cursor_glow_service.py')
            import subprocess
            result=subprocess.run(['/usr/bin/python3',service,'--theme',config['theme'],'--state',config['state_dir'],'--root',config['theme_root'],'--owner',str(os.getpid()),'--recover'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=4)
            if result.returncode:raise RuntimeError('Cursor theme recovery could not be confirmed')
        except FileNotFoundError:pass
        except Exception as error:self.cursor_glow_warning=str(error)

    def show_cursor_glow(self):
        if self.cursor_glow is not None:return
        if self.cursor_glow_pending is not None:raise RuntimeError('Previous cursor restoration is unconfirmed; no new glow lease is allowed')
        config=self.cursor_glow_config()
        self.require_runtime()
        path=os.path.join(os.path.dirname(__file__),'cursor_glow_service.py')
        spec=importlib.util.spec_from_file_location('desktop_cursor_glow',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        controller=module.Controller(config['theme'],config['state_dir'],config['theme_root'],active=lambda:self.state in ('active','pausing','paused','resuming') and self.backend is not None and self.backend.status().get('active') is True,on_failure=lambda error:self.cursor_glow_failed(controller,error))
        self.own_observer('cursor_glow',controller)
        self.cursor_glow_warning=None
        try:controller.start()
        except Exception:
            with self.state_lock:
                self.owner_cancel_events.pop('cursor_glow',None)
                self.cursor_glow=None
            raise

    def cursor_glow_failed(self,expected,error):
        self.cancel_observer('cursor_glow',expected)
        with self.state_lock:
            if self.cursor_glow is not expected:return
            self.cursor_glow_warning=str(error)
            indicator=self.indicator
        if indicator is not None:self.foreground_lost(indicator)

    def defer_click_context_loss(self,expected):
        # Only the explicit click policy may briefly correlate a foreground
        # signal with native click evidence. No input/capture while correlating.
        backend=self.backend;native=self.native_activity;consent=self.consent_id
        event=getattr(backend,'operation_cancelled',None)
        if (self.native_click_policy!='pause-return' or self.interruption_policy!='retain-sharing' or
            expected is not self.indicator or native is None or backend is not self.backend or
            consent!=self.consent_id or self.state not in ('active','resuming','pausing','paused') or backend.cancelled.is_set()):return False
        pending=self.click_context_pending
        if pending is not None and pending['backend'] is backend and pending['event'] is event and pending['native'] is native and pending['consent']==consent:return True
        record={'backend':backend,'native':native,'indicator':expected,'consent':consent,'event':event,
                'deadline':time.monotonic()+.25,'done':threading.Event(),'epoch':None}
        self.click_context_pending=record
        if event is not None:event.set()
        def correlate():
            matched=False
            try:
                with self.lifecycle_lock:
                    if (self.backend is not backend or self.native_activity is not native or self.indicator is not expected or
                        self.consent_id!=consent or backend.operation_cancelled is not event or backend.cancelled.is_set()):return
                    backend.pause_input()
                while time.monotonic()<record['deadline']:
                    if (self.backend is not backend or self.native_activity is not native or self.indicator is not expected or
                        self.consent_id!=consent or backend.operation_cancelled is not event or backend.cancelled.is_set()):return
                    context=expected.context()
                    if time.monotonic()>=record['deadline']:break
                    inert=self.intervention_context_wait_enabled() and self.keyboard_inert_context(context)
                    if context.get('available') is True and not inert:
                        self.window_guard_module().WindowGuard.signature(context)
                        if context.get('kind')!='window':break
                    elif not inert and context.get('reason')!='no-foreground-window':break
                    epoch=native.status().get('intervention_epoch')
                    if (context.get('available') is True or inert) and type(epoch) is int and native.is_current_intervention(epoch):
                        record['epoch']=epoch;matched=True;self.physical_intervention(native,epoch);return
                    backend.cancelled.wait(min(.01,max(0,record['deadline']-time.monotonic())))
            except Exception:pass
            finally:
                record['done'].set()
                if not matched and self.click_context_pending is record and self.backend is backend and self.native_activity is native and self.indicator is expected and self.consent_id==consent and backend.operation_cancelled is event:
                    if self.invalidate(expected_indicator=expected,reason='foreground-context-changed'):
                        self.close_backend(expected_indicator=expected)
        threading.Thread(target=correlate,daemon=True,name='click-context-correlation').start()
        return True

    def matched_click_context_loss(self):
        record=self.click_context_pending
        if record is None:return False
        record['done'].wait(max(0,record['deadline']-time.monotonic())+.02)
        epoch=record['epoch']
        return (type(epoch) is int and self.backend is record['backend'] and self.native_activity is record['native'] and
                self.consent_id==record['consent'] and self.backend.operation_cancelled is record['event'] and
                not self.backend.cancelled.is_set() and record['native'].is_current_intervention(epoch))

    def make_window_guard(self,bridge,context,cancel):
        cls=self.window_guard_module().WindowGuard
        if self.context_change_policy=='pause-recover':return cls(bridge,context,cancel,failure=ContextRecoveryPending)
        return cls(bridge,context,cancel)

    def context_recovery_owned(self,record=None):
        record=self.context_recovery if record is None else record
        return bool(record is not None and self.context_recovery is record and
            self.backend is record['backend'] and self.native_activity is record['native'] and
            self.indicator is record['indicator'] and self.consent_id==record['consent'] and
            self.backend.operation_cancelled is record['event'] and not self.backend.cancelled.is_set())

    def context_changed(self):
        if self.defer_context_loss(self.indicator):raise ContextRecoveryPending('Ordinary foreground change is awaiting a fresh observation')
        raise RuntimeError('Foreground changed; session must close')

    def defer_context_loss(self,expected):
        if self.context_change_policy!='pause-recover' or self.interruption_policy!='retain-sharing':return False
        backend=self.backend;native=self.native_activity;consent=self.consent_id
        event=getattr(backend,'operation_cancelled',None)
        if (native is None or expected is not self.indicator or backend is not self.backend or
            consent!=self.consent_id or event is None or backend.cancelled.is_set() or
            self.state not in ('active','resuming','pausing','paused')):return False
        existing=self.context_recovery
        if self.context_recovery_owned(existing) and existing['phase'] in ('admitting','settling'):return True
        event.set()
        record={'backend':backend,'native':native,'indicator':expected,'consent':consent,'event':event,
            'deadline':time.monotonic()+CONTEXT_RECOVERY_SECONDS,'phase':'admitting','native_yield':None}
        self.context_recovery=record;self.context_observation_required=True
        threading.Thread(target=self.recover_context,args=(record,),daemon=True,name='ordinary-context-recovery').start()
        return True

    def recover_context(self,record):
        backend=record['backend'];native=record['native'];bridge=record['indicator']
        try:
            with self.execution_lock,self.lifecycle_lock:
                if not self.context_recovery_owned(record):return
                if not self.begin_pause('context-change'):return
                backend.pause_input();self.close_target_provider()
                self.state='paused';record['phase']='settling'
                stable=None;since=None
                while self.context_recovery_owned(record):
                    if self.manual_pause_pending():
                        self.pause_reason='manual';self.state='pausing';self.finish_pause(self.pause_id);record['phase']='manual';return
                    if time.monotonic()>=record['deadline']:raise RuntimeError('Ordinary foreground recovery timed out')
                    status=native.status()
                    if not native._yield_authorized() or status.get('observer_alive') is not True or status.get('auth_waiting'):
                        raise RuntimeError('Native observer unavailable during foreground recovery')
                    epoch=record['native_yield'] or (status.get('yield_epoch') if status.get('yielded') else None)
                    if epoch is not None:
                        record['phase']='handed-off'
                        if native.is_current_intervention(epoch):self.physical_intervention(native,epoch)
                        else:self.pointer_yielded(native,epoch)
                        return
                    if status.get('active') is not True:raise RuntimeError('Native observer unavailable during foreground recovery')
                    backend.mapping_guard()
                    context=bridge.context()
                    if not self.context_recovery_owned(record):return
                    if time.monotonic()>=record['deadline']:raise RuntimeError('Ordinary foreground recovery timed out')
                    status=native.status()
                    if not native._yield_authorized() or status.get('observer_alive') is not True:raise RuntimeError('Native observer unavailable during foreground recovery')
                    if status.get('yielded'):continue
                    if status.get('active') is not True:raise RuntimeError('Native observer unavailable during foreground recovery')
                    backend.mapping_guard()
                    if context.get('available') is not True:
                        if context.get('reason')!='no-foreground-window':raise RuntimeError('Protected foreground cannot recover')
                        stable=None;since=None
                    else:
                        signature=self.window_guard_module().WindowGuard.signature(context)
                        if context.get('kind')!='window':raise RuntimeError('Only ordinary application windows can recover')
                        now=time.monotonic()
                        if signature!=stable:stable=signature;since=now
                        if now-since>=CONTEXT_RECOVERY_QUIET:
                            with self.state_lock:
                                if not self.context_recovery_owned(record) or self.manual_pause_pending():continue
                                if time.monotonic()>=record['deadline']:raise RuntimeError('Ordinary foreground recovery timed out')
                                # Old work retains its cancelled event. Only a new
                                # observe can produce authority for further input.
                                backend.operation_cancelled=threading.Event();record['event']=backend.operation_cancelled
                                self.state='resuming'
                            try:backend.resume_capture()
                            except RetainedPause:
                                if self.manual_pause_pending():
                                    self.state='pausing';self.pause_reason='manual';self.finish_pause(self.pause_id);record['phase']='manual';return
                                epoch=native.status().get('yield_epoch')
                                if native.is_current_yield(epoch):
                                    record['phase']='handed-off'
                                    if native.is_current_intervention(epoch):self.physical_intervention(native,epoch)
                                    else:self.pointer_yielded(native,epoch)
                                    return
                                raise
                            backend.mapping_guard()
                            current=bridge.context()
                            if not self.context_recovery_owned(record):return
                            if time.monotonic()>=record['deadline']:raise RuntimeError('Ordinary foreground recovery timed out')
                            if self.manual_pause_pending():
                                self.state='pausing';self.pause_reason='manual';self.finish_pause(self.pause_id);record['phase']='manual';return
                            if self.window_guard_module().WindowGuard.signature(current)!=stable:
                                record['event'].set();backend.pause_input();self.state='paused';stable=None;since=None;continue
                            status=native.status()
                            if not native._yield_authorized() or status.get('observer_alive') is not True:raise RuntimeError('Native observer unavailable during foreground recovery')
                            if status.get('yielded'):
                                record['event'].set();backend.pause_input();record['phase']='handed-off'
                                epoch=status.get('yield_epoch')
                                if native.is_current_intervention(epoch):self.physical_intervention(native,epoch)
                                else:self.pointer_yielded(native,epoch)
                                return
                            with self.state_lock:
                                if not self.context_recovery_owned(record):return
                                if self.manual_pause_pending():raise ContextManualPause()
                                backend.mapping_guard()
                                status=native.status()
                                if time.monotonic()>=record['deadline'] or not native._yield_authorized() or status.get('observer_alive') is not True:raise RuntimeError('Foreground recovery admission changed')
                                if status.get('yielded'):
                                    record['event'].set();record['phase']='handed-off';epoch=status.get('yield_epoch')
                                    if native.is_current_intervention(epoch):self.physical_intervention(native,epoch)
                                    else:self.pointer_yielded(native,epoch)
                                    return
                                if self.manual_pause_pending():raise ContextManualPause()
                                if status.get('active') is not True or record['event'].is_set():raise RuntimeError('Foreground recovery admission changed')
                                self.state='active';self.pause_id=None;self.pause_reason=None
                                self.window_record=None;self.target_record=None;self.return_record=None
                                backend.confirmed_pointer_record=None
                                self.return_state='context-awaiting-observation';record['phase']='complete'
                                bridge.armed=self.make_window_guard(bridge,context,lambda:self.foreground_lost(bridge))
                                return
                    backend.cancelled.wait(.05)
        except ContextManualPause:
            if self.context_recovery_owned(record):
                try:
                    self.begin_pause('manual');self.finish_pause(self.pause_id);record['phase']='manual'
                except Exception:
                    if self.invalidate(expected_indicator=bridge,reason='foreground-context-changed'):self.close_backend(expected_indicator=bridge)
        except Exception:
            if self.context_recovery_owned(record):
                record['phase']='failed'
                if self.invalidate(expected_indicator=bridge,reason='foreground-context-changed'):self.close_backend(expected_indicator=bridge)

    def foreground_lost(self,expected):
        if self.defer_context_loss(expected):return
        if self.defer_click_context_loss(expected):return
        if not self.invalidate(expected_indicator=expected,reason='foreground-context-changed'):return
        # Do not do synchronous D-Bus cleanup in the context-signal callback.
        def cleanup():
            self.close_backend(expected_indicator=expected)
        threading.Thread(target=cleanup,daemon=True).start()

    def close_backend(self,expected_native=None,expected_indicator=None):
        # Callback-owned closures were cancelled by invalidate() already. Do not
        # touch a potentially newer backend before validating their owner under
        # the same lock used by desktop_start.
        if expected_native is None and expected_indicator is None and self.backend:
            self.backend.cancelled.set()
        with self.lifecycle_lock:
            with self.state_lock:
                if expected_native is not None and self.native_activity is not expected_native:return
                if expected_indicator is not None and self.indicator is not expected_indicator:return
            self._close_backend_owned()

    def _close_backend_owned(self):
        with self.state_lock:
            if self.pause_watch_stop:self.pause_watch_stop.set()
            self.pause_watch_stop=None
            self.owner_cancel_events.clear()
            self.return_record=None;self.consent_id=None;self.native_pause_epoch=None
            self.return_state='closed';self.click_context_pending=None
            glow=self.cursor_glow;self.cursor_glow=None
            native=self.native_activity;self.native_activity=None
            indicator=self.indicator;self.indicator=None
            self.physical_takeover=False
        # Cancel immediately and destroy/release virtual input before waiting for
        # observer process cleanup. Never leave held input behind an admin worker.
        if self.backend:self.backend.cancelled.set();self.backend.close();self.backend.pointer_position=None
        if native is not None:
            try:native.close()
            except Exception:self.physical_takeover_warning='Native observer closure unconfirmed; portal closure attempted.'
            self.native_activity_last=native.status()
        if indicator:indicator.close()
        if glow is not None:
            try:glow.close()
            except Exception as error:
                self.cursor_glow_warning=str(error);self.cursor_glow_pending=glow
            self.cursor_glow_last=glow.status()
        self.target_record=None;self.window_record=None;self.close_target_provider()
        with self.state_lock:self.state='closed';self.pause_id=None;self.pause_reason=None

    def ensure_backend(self):
        self.guard()
        if self.backend is None:self.backend=self.factory()
        self.backend.request_cancel=self.cancel_token
        self.guard()

    def close_target_provider(self):
        provider=self.target_provider;self.target_provider=None
        if provider is not None and callable(getattr(provider,'close',None)):
            try:confirmed=provider.close() is not False
            except Exception:confirmed=False
            self.target_cleanup_warning=None if confirmed else 'Accessibility connection closure unconfirmed; target access is disabled.'


    def inspect_keyboard_target(self):
        self.target_gate()
        if self.target_provider is None:
            self.require_runtime()
            path=os.path.join(os.path.dirname(__file__),'target_guard.py')
            spec=importlib.util.spec_from_file_location('desktop_target_guard',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.target_provider=module.AtspiProvider()
        self.target_gate()
        return self.target_provider.snapshot(self.target_gate)


    def target_gate(self):
        self.guard(('active',))
        if callable(getattr(self.backend,'check',None)):self.backend.check()


    def read_window_context(self,settle_seconds=0):
        if self.indicator is None:raise RuntimeError('Updated foreground observer unavailable; input is refused. Reload the indicator extension before a new session.')
        deadline=time.monotonic()+settle_seconds
        while True:
            self.guard()
            if callable(getattr(self.backend,'check',None)):self.backend.check()
            context=self.indicator.context()
            self.guard()
            if callable(getattr(self.backend,'check',None)):self.backend.check()
            if settle_seconds>0 and time.monotonic()>=deadline:raise RuntimeError('Foreground observation exceeded transition deadline')
            if context.get('available') is True:return context
            if context.get('reason')=='no-foreground-window' and settle_seconds<=0:self.context_changed()
            if context.get('reason')!='no-foreground-window' or time.monotonic()>=deadline:raise RuntimeError('Foreground context unavailable or system UI active; session must close')
            # This is read-only app-launch settling, never readiness or a retry.
            if callable(getattr(self.backend,'wait_interruptibly',None)):self.backend.wait_interruptibly(.05)
            else:time.sleep(.05)

    def window_guard_module(self):
        self.require_runtime()
        path=os.path.join(os.path.dirname(__file__),'window_guard.py')
        spec=importlib.util.spec_from_file_location('desktop_window_guard',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def stable_transition_context(self,deadline,origin=None):
        stable=None;since=None
        while True:
            context=self.read_window_context(max(0,deadline-time.monotonic()))
            signature=self.window_guard_module().WindowGuard.signature(context)
            now=time.monotonic()
            if signature!=stable:stable=signature;since=now
            if now>=deadline:raise RuntimeError('Intentional transition did not settle; session must close')
            if signature!=origin and now-since>=.15:return context
            wait=min(.05,deadline-now)
            if callable(getattr(self.backend,'wait_interruptibly',None)):self.backend.wait_interruptibly(wait)
            else:time.sleep(wait)

    def capture_result(self,allowed,expected_window=None,transition_settle=False,moved_window=None,transition_origin=None,transition_deadline=None):
        required=getattr(self.backend,'requires_window_guard',False)
        deadline=transition_deadline if transition_deadline is not None else time.monotonic()+2
        attempts=0
        while True:
            before=(self.stable_transition_context(deadline,transition_origin) if transition_settle else self.read_window_context()) if required else None
            if moved_window is not None:
                self.backend.mapping_guard()
                self.window_guard_module().validate_monitor_arrival(before,*moved_window)
            if expected_window is not None and self.window_guard_module().WindowGuard.signature(before)!=expected_window:self.context_changed()
            self.require_runtime()
            self.guard(allowed)
            if self.state=='opening' and self.physical_takeover:self.require_native_ready()
            png=self.backend.capture();self.guard(allowed)
            if transition_settle and time.monotonic()>=deadline:raise RuntimeError('Transition capture exceeded deadline; no image published')
            if self.state=='opening' and self.physical_takeover:self.require_native_ready()
            after=self.read_window_context(max(0,deadline-time.monotonic()) if transition_settle else 0) if required else None
            if transition_settle and time.monotonic()>=deadline:raise RuntimeError('Transition observation exceeded deadline; no image published')
            if moved_window is not None:
                self.backend.mapping_guard()
                self.window_guard_module().validate_monitor_arrival(after,*moved_window)
            if not required or self.window_guard_module().WindowGuard.signature(before)==self.window_guard_module().WindowGuard.signature(after):break
            # Only the already-authorized single transition may settle across a
            # capture race. Discard pixels and observe again; never repeat input.
            attempts+=1
            if not transition_settle or attempts>=2 or time.monotonic()>=deadline:self.context_changed()
        with self.state_lock:
            self.guard(allowed)
            if self.state=='opening' and self.physical_takeover:self.require_native_ready()
            operation=getattr(self.backend,'operation_cancelled',None)
            if operation is not None and operation.is_set():raise RetainedPause('Capture discarded by pause')
            if transition_settle and time.monotonic()>=deadline:raise RuntimeError('Transition publication exceeded deadline; no image published')
            self.state='active'
        self.recovery.observed();self.window_record=None
        observation={'available':False}
        if after:
            self.window_record={'id':uuid.uuid4().hex,'generation':self.generation,'issued':time.monotonic(),'context':after}
            if transition_settle:self.window_record['publication_deadline']=deadline
            observation={'available':True,'observation_id':self.window_record['id'],'epoch':after['epoch'],'kind':after['kind'],'frame_rect':after['rect'],'expires_seconds':60}
        import struct
        w,h=struct.unpack('>II',png[16:24])
        return [text(dict(self.status(),window_observation=observation,pixel_size=[w,h],capture=getattr(self.backend,'capture_info',{}),transaction=getattr(self.backend,'transaction_info',{}),coordinate_rule='x_logical=x_pixel*logical_width/pixel_width; likewise y')),image(png)]

    def call(self,name,args):
        with self.execution_lock:
            if name in ('desktop_start','desktop_resume'):
                with self.lifecycle_lock:return self._call_owned(name,args)
            return self._call_owned(name,args)

    def _call_owned(self,name,args):
        if name not in {t['name'] for t in tools()}:raise ValueError('Unknown tool')
        if not isinstance(args,dict):raise ValueError('Arguments must be an object')
        if name=='desktop_status':return [text(self.status())]
        if name=='desktop_close':
            self.invalidate(reason='requested-close');self.close_backend();return [text(self.status())]
        if name=='desktop_pause':
            if self.begin_pause():self.finish_pause()
            else:self.close_backend()
            return [text(self.status())]
        if name=='desktop_resume':return self.resume_sharing(args)
        if name in ('desktop_start','desktop_action','desktop_observe'):
            self.require_runtime()
        self.guard()
        if name=='desktop_start':
            policy=args.get('interruption_policy','close')
            if policy not in ('close','retain-sharing'):raise ValueError('Invalid interruption_policy')
            if self.state in ('pausing','paused','resuming'):raise RetainedPause('Sharing is paused; use desktop_resume rather than desktop_start')
            physical=args.get('physical_takeover',False)
            if type(physical) is not bool:raise ValueError('physical_takeover must be boolean')
            context_policy=args.get('context_change_policy','close')
            if context_policy not in ('close','pause-recover') or not isinstance(context_policy,str):raise ValueError('Invalid context_change_policy')
            if context_policy=='pause-recover' and (not physical or policy!='retain-sharing'):raise ValueError('Context recovery requires retained native sharing')
            click_policy=args.get('click_policy','close')
            if type(click_policy) is not str or click_policy not in ('close','pause-return'):raise ValueError('Invalid click_policy')
            if click_policy=='pause-return' and (not physical or policy!='retain-sharing'):raise ValueError('Click pause requires physical_takeover and retained sharing')
            keyboard_policy=args.get('keyboard_policy','close')
            if type(keyboard_policy) is not str or keyboard_policy not in ('close','pause-recover'):raise ValueError('Invalid keyboard_policy')
            if keyboard_policy=='pause-recover' and (not physical or policy!='retain-sharing' or click_policy!='pause-return'):raise ValueError('Keyboard recovery requires retained physical click recovery')
            pointer_source=args.get('pointer_source','mouse')
            if not isinstance(pointer_source,str) or pointer_source not in ('mouse','touchpad'):raise ValueError('Invalid pointer_source')
            if pointer_source=='touchpad' and (not physical or policy!='retain-sharing'):raise ValueError('Touchpad observation requires physical_takeover and retained sharing')
            multi_contact_policy=args.get('multi_contact_policy','close')
            if type(multi_contact_policy) is not str or multi_contact_policy not in ('close','pause-recover'):raise ValueError('Invalid multi_contact_policy')
            if multi_contact_policy=='pause-recover' and (not physical or policy!='retain-sharing' or click_policy!='pause-return' or pointer_source!='touchpad'):raise ValueError('Multi-contact recovery requires retained physical touchpad click recovery')
            allow_permission_wait=args.get('allow_permission_wait',False)
            if type(allow_permission_wait) is not bool or (allow_permission_wait and (not physical or policy!='retain-sharing')):raise ValueError('Permission waiting requires retained native sharing')
            startup_verification=args.get('startup_verification','challenge')
            if not isinstance(startup_verification,str) or startup_verification not in ('challenge','passive'):raise ValueError('Invalid startup_verification')
            if startup_verification=='passive' and (not physical or policy!='retain-sharing'):raise ValueError('Passive supervision requires physical_takeover and retained sharing')
            session_seconds=args.get('session_seconds',120)
            if type(session_seconds) is not int or not 120<=session_seconds<=600:raise ValueError('session_seconds must be an integer from 120 to 600')
            if 'session_seconds' in args and not physical:raise ValueError('session_seconds requires physical_takeover')
            auto_return=args.get('pointer_motion_return',False)
            if type(auto_return) is not bool:raise ValueError('pointer_motion_return must be boolean')
            if auto_return and (policy!='retain-sharing' or not physical):raise ValueError('Automatic pointer return requires retained sharing and native activity observation')
            if physical:self.preflight_physical_guard()
            glow=args.get('cursor_glow',False)
            if type(glow) is not bool:raise ValueError('cursor_glow must be boolean')
            self.ensure_backend()
            if not self.backend.status().get('active'):
                with self.state_lock:
                    previous_owned=(self.native_activity is not None or self.indicator is not None or
                        self.cursor_glow is not None or self.target_provider is not None or
                        self.state in ('active','closing'))
                    if not previous_owned:
                        # Never clear an event captured by an old observer. Its
                        # late callback cannot cancel this replacement session.
                        self.backend.cancelled=threading.Event()
                        self.backend.operation_cancelled=threading.Event()
                        self.native_session_seconds=session_seconds
                        self.native_pointer_source=pointer_source;self.native_click_policy=click_policy;self.native_keyboard_policy=keyboard_policy;self.native_multi_contact_policy=multi_contact_policy;self.context_change_policy=context_policy;self.context_recovery=None;self.context_observation_required=False
                        self.native_startup_verification=startup_verification;self.native_allow_permission_wait=allow_permission_wait;self.permission_wait_stage=None;self.permission_wait_reason=None;self.permission_wait_failure_stage=None
                        self.interruption_policy=policy;self.pause_id=None;self.pause_reason=None
                        self.pointer_motion_return=auto_return;self.consent_id=uuid.uuid4().hex;self.backend.consent_id=self.consent_id
                        self.backend.confirmed_pointer_record=None;self.return_record=None;self.return_attempted=set();self.native_pause_epoch=None;self.manual_pause_requested=False;self.manual_pause_latch=None;self.intervention_latch=None;self.click_context_pending=None
                        self.return_state='ready' if auto_return else 'disabled'
                        self.state='opening';self.target_record=None;self.closure_reason=None
                if previous_owned:
                    self.invalidate();self.close_backend()
                    raise RuntimeError('Previous session resources required cleanup; call desktop_start again for a new consent session')
                try:
                    if getattr(self.backend,'requires_window_guard',False) and self.indicator is None:
                        preflight=self.preflight_context()
                        if self.native_allow_permission_wait and getattr(preflight,'auth_wait_protocol',0)!=3:raise RuntimeError('Permission-wait observer protocol unavailable')
                    if physical:
                        self.backend.start(defer_capture=True)
                        self.enable_physical_guard()
                        self.show_indicator()
                        if getattr(self.backend,'requires_window_guard',False):
                            self.backend.wait_interruptibly(.2)
                            self.read_window_context(2)
                        self.require_runtime()
                        self.require_native_ready()
                        self.backend.finish_start()
                    else:
                        self.backend.start();self.show_indicator()
                    content=self.capture_result(('opening',))
                    if glow:
                        self.show_cursor_glow()
                        metadata=json.loads(content[0]['text']);metadata.update(self.status());content[0]=text(metadata)
                    return content
                except BaseException:self.close_backend();raise
            if 'allow_permission_wait' in args and allow_permission_wait!=self.native_allow_permission_wait:raise ValueError('An active permission-wait mode cannot change')
            if 'startup_verification' in args and startup_verification!=self.native_startup_verification:raise ValueError('An active startup verification mode cannot be changed')
            if 'pointer_source' in args and pointer_source!=self.native_pointer_source:raise ValueError('An active input source cannot be changed')
            if 'context_change_policy' in args and context_policy!=self.context_change_policy:raise ValueError('An active context recovery policy cannot change')
            if 'multi_contact_policy' in args and multi_contact_policy!=self.native_multi_contact_policy:raise ValueError('An active multi-contact policy cannot be changed')
            if 'keyboard_policy' in args and keyboard_policy!=self.native_keyboard_policy:raise ValueError('An active keyboard policy cannot be changed')
            if 'click_policy' in args and click_policy!=self.native_click_policy:raise ValueError('An active click policy cannot be changed')
            if 'session_seconds' in args and session_seconds!=self.native_session_seconds:raise ValueError('An active native lease cannot be changed; close before selecting a new initial limit')
            if physical and not self.physical_takeover:raise RuntimeError('Device-source observation must be selected before a new consent session')
            expected=self.window_guard_module().WindowGuard.signature(self.window_record['context']) if self.window_record else None
            return self.capture_result(('active',),expected)
        self.guard(('active',));self.ensure_backend()
        if name=='desktop_action':
            if self.context_observation_required:raise RetainedPause('Ordinary context recovered; inspect desktop_observe before further input')
            record=self.target_record;self.target_record=None
            window_record=self.window_record;self.window_record=None
            self.recovery.begin(args.get('recovery_observation_id'))
            target=None;window=None
            # Reset before backend validation, so an old call cannot contaminate
            # the current partial-result report.
            self.backend.transaction_info={'completed_steps':0,'failed_step':None,'input_events_attempted':0,'input_characters_completed':0}
            try:
                permission=args.get('wait_for_permission',False)
                if type(permission) is not bool:raise ValueError('wait_for_permission must be boolean')
                if 'recording_stopped' in args and type(args['recording_stopped']) is not bool:raise ValueError('recording_stopped must be boolean')
                if permission:
                    action=args.get('action',{})
                    if (args.get('focus_transition') is not True or args.get('recording_stopped') is not True or
                        any(args.get(k,False) for k in ('await_context_change','window_move_to_shared','window_fit_shared','window_normalize_for_move')) or
                        'target_id' in args or action.get('type')!='click' or action.get('button','left')!='left' or action.get('count',1)!=1 or
                        not set(action)<={'type','button','count','x','y'}):raise ValueError('Permission waiting requires one separate observed Install click and stopped owned recorders')
                    if not self.native_allow_permission_wait or self.interruption_policy!='retain-sharing' or self.native_activity is None or self.native_activity.status().get('auth_wait_supported') is not True or getattr(self.indicator,'auth_wait_protocol',0)!=3:raise RuntimeError('Permission waiting capability unavailable')
                monitor_move=args.get('window_move_to_shared',False);moved_window=None
                normalize_window=args.get('window_normalize_for_move',False)
                if type(normalize_window) is not bool:raise ValueError('window_normalize_for_move must be boolean')
                fit_window=args.get('window_fit_shared',False)
                if type(fit_window) is not bool:raise ValueError('window_fit_shared must be boolean')
                if type(monitor_move) is not bool:raise ValueError('window_move_to_shared must be boolean')
                if sum((normalize_window,fit_window,monitor_move))>1:raise ValueError('Window setup gestures require separate observed actions')
                transition=args.get('focus_transition',False)
                await_change=args.get('await_context_change',False)
                if type(await_change) is not bool:raise ValueError('await_context_change must be boolean')
                if await_change:
                    action=args.get('action',{})
                    launch_click=action.get('type')=='click' and action.get('button','left')=='left' and action.get('count',1)==1 and set(action)<= {'type','button','count','x','y'}
                    launch_return=action=={'type':'keys','keys':['Return']}
                    if transition is not True or monitor_move or normalize_window or fit_window or not getattr(self.backend,'requires_window_guard',False) or not (launch_click or launch_return):raise ValueError('await_context_change requires a separate guarded launch click or Return transition')
                if (monitor_move or normalize_window or fit_window) and (transition is not True or not getattr(self.backend,'requires_window_guard',False)):raise ValueError('Monitor move requires a guarded explicit focus transition')
                if type(transition) is not bool:raise ValueError('focus_transition must be boolean')
                if transition and 'target_id' in args:raise ValueError('A focus transition cannot reuse an editable-control identity')
                if getattr(self.backend,'requires_window_guard',False):
                    if not window_record or args.get('window_observation_id')!=window_record['id'] or window_record['generation']!=self.generation:raise RuntimeError('Foreground observation expired or invalid; inspect a fresh screenshot before input')
                    def cancel_window():
                        if self.context_change_policy=='pause-recover':
                            self.foreground_lost(self.indicator);return
                        if self.defer_click_context_loss(self.indicator):raise ClickContextPending('Foreground change awaiting physical click evidence')
                        self.backend.cancelled.set()
                        if self.cancel_token:self.cancel_token.set()
                    module=self.window_guard_module();window=self.make_window_guard(self.indicator,window_record['context'],cancel_window);window.check()
                    if time.monotonic()-window_record['issued']>60:
                        # A matching old token grants no input. If its foreground
                        # still matches, return a fresh inspected-image opportunity
                        # instead of needlessly reopening the portal. No replay.
                        self.recovery.finish(self.backend.transaction_info,failed=True)
                        content=self.capture_result(('active',),window.baseline)
                        metadata=json.loads(content[0]['text'])
                        metadata['action_refused']='Observation expired; zero input was sent. Inspect this fresh image and use its new token for any next action.'
                        metadata['recovery']=self.recovery.snapshot();content[0]=text(metadata)
                        return content
                    geometry=self.backend.monitor_geometry() if callable(getattr(self.backend,'monitor_geometry',None)) else None
                    def pointer_reader():
                        window.check()
                        return module.pointer_local(self.read_window_context(),geometry)
                    self.backend.pointer_reader=pointer_reader
                    if normalize_window or fit_window:
                        module.validate_normalize_for_move(args['action'])
                        module.normalize_shortcut_configured()
                        mapping=getattr(self.backend,'monitor_mapping',None)
                        if mapping is None:raise RuntimeError('Verified monitor mapping unavailable')
                        mapping_admission=mapping.window_fit_shared if fit_window else mapping.window_normalize_source
                        destination=mapping_admission(window_record['context'])
                        moved_window=(window_record['context']['window_id'],destination)
                        self.backend.transition_activation_key=self.backend.keysym('F10')
                    elif monitor_move:
                        direction=module.validate_monitor_move(args['action'])
                        module.monitor_shortcut_configured(direction)
                        mapping=getattr(self.backend,'monitor_mapping',None)
                        if mapping is None:raise RuntimeError('Verified monitor mapping unavailable')
                        destination=mapping.window_move_direction(window_record['context'],direction)
                        moved_window=(window_record['context']['window_id'],destination)
                        self.backend.transition_activation_key=self.backend.keysym(direction)
                    elif transition:module.validate_transition(args['action'])
                    else:
                        geometry=self.backend.monitor_geometry() if callable(getattr(self.backend,'monitor_geometry',None)) else None
                        window.validate_points(args['action'],(geometry['x'],geometry['y']) if geometry else (0,0))
                    self.backend.endpoint_context=window.baseline
                    self.backend.window_guard=window;self.backend.window_transition=transition
                    self.indicator.armed=window
                    def begin_transition():
                        window.check()
                        if normalize_window or fit_window:
                            module.normalize_shortcut_configured()
                            mapping_admission(self.read_window_context())
                            window.check()
                        elif monitor_move:
                            module.monitor_shortcut_configured(direction)
                            mapping.window_move_direction(self.read_window_context(),direction)
                            window.check()
                        self.indicator.armed=self.permission_signal if permission else None
                    self.backend.begin_transition=begin_transition if transition else None
                if 'target_id' in args:
                    if not record or args['target_id']!=record['id'] or record['epoch']!=self.generation or time.monotonic()-record['issued']>60:
                        raise RuntimeError('Target identity expired or invalid; inspect a fresh desktop_observe(inspect_target=true) result before input')
                    target=record['target'];target.live(active=True,focused=True);self.guard(('active',))
                self.backend.target_guard=target
                auth_record=None
                if permission:
                    window.validate_points(args['action'],(geometry['x'],geometry['y']))
                    auth_record=self.prepare_permission_wait(window_record['context'])
                transition_deadline=time.monotonic()+5 if await_change else None
                try:
                    self.backend.action(args['action'])
                    if window is not None and not transition:window.check()
                finally:
                    self.backend.target_guard=None;self.backend.pointer_reader=None;self.backend.begin_transition=None;self.backend.endpoint_context=None
                    self.backend.window_guard=None;self.backend.window_transition=False;self.backend.transition_activation_key=None
                    if self.indicator:self.indicator.armed=None
                if permission:
                    content=self.finish_permission_wait(auth_record)
                else:content=self.capture_result(('active',),window.baseline if window is not None and not transition else None,transition_settle=transition,moved_window=moved_window,transition_origin=window.baseline if await_change else None,transition_deadline=transition_deadline)
            except BaseException as action_error:
                self.backend.pointer_reader=None;self.backend.begin_transition=None;self.backend.endpoint_context=None
                self.backend.window_guard=None;self.backend.window_transition=False;self.backend.transition_activation_key=None
                if self.indicator:self.indicator.armed=None
                self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
                progress=getattr(self.backend,'transaction_info',{})
                if (isinstance(action_error,ValueError) and not permission and window is not None and
                    self.interruption_policy=='retain-sharing' and self.native_activity is not None and
                    progress.get('input_events_attempted')==0 and progress.get('completed_steps')==0):
                    # Only a successfully bound, fresh window token can reach
                    # this path. Invalid/stale identities and partial input fail.
                    self.backend.check();self.backend.mapping_guard();window.check()
                    native=self.native_activity;status=native.status()
                    if not native._yield_authorized() or status.get('active') is not True or status.get('observer_alive') is not True:raise RuntimeError('Native readiness changed during validation refusal')
                    content=self.capture_result(('active',),window.baseline)
                    self.backend.mapping_guard();window.check();status=native.status()
                    if self.native_activity is not native or not native._yield_authorized() or status.get('active') is not True or status.get('observer_alive') is not True:raise RuntimeError('Native readiness changed before validation image')
                    metadata=json.loads(content[0]['text']);metadata['action_refused']='Invalid action arguments; zero input was sent. Inspect the fresh image before choosing a corrected action.'
                    content[0]=text(metadata);return content
                if permission:
                    if self.permission_wait_reason is None:
                        self.permission_wait_reason='action-failed'
                        stage=self.permission_wait_stage
                        self.permission_wait_failure_stage=stage if stage in PERMISSION_FAILURE_STAGES else 'not-started'
                    raise RuntimeError('Permission wait interrupted or could not be verified') from None
                raise
            self.recovery.finish(getattr(self.backend,'transaction_info',{}))
            # Capture assembled status before finish; refresh only metadata.
            metadata=json.loads(content[0]['text'])
            metadata['recovery']=self.recovery.snapshot()
            content[0]=text(metadata)
            return content
        self.target_record=None
        target=None;target_error=None
        if name=='desktop_observe' and args.get('inspect_target') is True:
            try:target=self.inspect_keyboard_target()
            except Exception as error:
                self.guard(('active',))
                target_error=str(error)[:300]
        expected=self.window_guard_module().WindowGuard.signature(self.window_record['context']) if self.window_record else None
        content=self.capture_result(('active',),expected)
        if name=='desktop_observe':
            self.context_observation_required=False
            metadata=json.loads(content[0]['text'])
            if args.get('inspect_target') is True:
                if target is not None:
                    try:
                        target.live(active=True,focused=True)
                        self.guard(('active',))
                        with self.state_lock:
                            self.guard(('active',))
                            record={'id':uuid.uuid4().hex,'epoch':self.generation,'issued':time.monotonic(),'target':target}
                            self.target_record=record
                            metadata['target']={'available':True,'target_id':record['id'],'epoch':record['epoch'],'expires_seconds':60,**target.describe()}
                    except Exception as error:
                        self.guard(('active',));target_error=str(error)[:300]
                if target_error is not None:metadata['target']={'available':False,'reason':target_error,'no_fallback':True}
            content[0]=text(metadata)
        return content


    def error_result(self,error,name=None,closure_reason=None):
        if isinstance(error,ContextRecoveryPending):
            if self.context_recovery_owned():error=RetainedPause('Foreground changed; pending work was cancelled and a fresh observation is required')
            else:error=RuntimeError('Foreground recovery could not be admitted; session must close')
        if name in ('desktop_action','desktop_observe','desktop_resume') and isinstance(error,ClickContextPending) and self.matched_click_context_loss():
            error=RetainedPause('Foreground change matched a physical click; interrupted work was discarded')
        retained=isinstance(error,RetainedPause) and self.interruption_policy=='retain-sharing'
        if name in ('desktop_start','desktop_observe','desktop_action','desktop_resume','desktop_pause') and not retained:
            try:self.invalidate(reason=closure_reason);self.close_backend()
            except Exception:pass
        progress=getattr(self.backend,'transaction_info',{}) if name=='desktop_action' else {}
        return {'isError':True,'content':[text({'error':str(error),'transaction':progress,
            'observe_before_retry':self.recovery.inspection_required,
            'recovery':self.recovery.snapshot(),
            'session':self.status()})]}


    def handle(self,request):
        method,params=request.get('method'),request.get('params',{})
        if method=='initialize':
            result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},
                    'serverInfo':{'name':'linux-desktop-control','version':VERSION}}
        elif method=='ping':result={}
        elif method=='tools/list':result={'tools':tools()}
        elif method=='tools/call':
            try:
                if request.get('_admission_error'):raise RuntimeError(request['_admission_error'])
                result={'content':self.call(params['name'],params.get('arguments',{}))}
                if params['name']=='desktop_resume':request['_generation']=self.generation
            except Exception as e:result=self.error_result(e,params.get('name'))
        elif method and method.startswith('notifications/'):return None
        else:return {'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':request.get('id'),'result':result}


    def fence_response(self,request,response):
        content=(response or {}).get('result',{}).get('content',[])
        if any(c.get('type')=='image' for c in content):
            permission_binding=(self.window_record or {}).get('permission_binding')
            if permission_binding is not None:
                try:self.permission_publish_check(permission_binding)
                except Exception:return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result('Permission state invalidated image publication',request.get('params',{}).get('name'))}
            if request.get('params',{}).get('name')=='desktop_start' and self.physical_takeover:
                try:self.require_native_ready()
                except Exception:
                    return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result('Native readiness changed before startup image publication','desktop_start')}
            if self.interruption_policy=='retain-sharing' and self.state in ('pausing','paused'):
                return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result(RetainedPause('Screenshot discarded by pause; no image published'),request.get('params',{}).get('name'))}
            if getattr(self.backend,'requires_window_guard',False):
                try:
                    if self.window_record and self.window_record.get('publication_deadline') is not None and time.monotonic()>=self.window_record['publication_deadline']:raise RuntimeError('Transition publication deadline expired')
                    if not self.window_record or self.window_guard_module().WindowGuard.signature(self.read_window_context())!=self.window_guard_module().WindowGuard.signature(self.window_record['context']):self.context_changed()
                except Exception as foreground_error:
                    name=request.get('params',{}).get('name');self.recovery.observation_id=None
                    if name=='desktop_action':self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
                    return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result(foreground_error if isinstance(foreground_error,RetainedPause) else 'Screenshot invalidated by foreground change; no image published',name,closure_reason='publication-foreground-fault')}
            if request.get('_generation',self.generation)!=self.generation or self.state!='active' or (self.cancel_token and self.cancel_token.is_set()) or (self.backend and self.backend.cancelled.is_set()) or (getattr(self.backend,'operation_cancelled',None) is not None and self.backend.operation_cancelled.is_set()):
                name=request.get('params',{}).get('name');self.recovery.observation_id=None;self.target_record=None;self.window_record=None
                if name=='desktop_action':self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
                return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result(RetainedPause('Screenshot invalidated by pause; no image published') if self.interruption_policy=='retain-sharing' and (self.state in ('pausing','paused') or (getattr(self.backend,'operation_cancelled',None) is not None and self.backend.operation_cancelled.is_set())) else 'Screenshot invalidated by session closure; no image published',name)}
            if getattr(self.backend,'requires_window_guard',False):
                bridge=self.indicator
                guard=self.make_window_guard(bridge,self.window_record['context'],lambda:self.foreground_lost(bridge))
                bridge.armed=guard
                try:
                    guard.check()
                    if permission_binding is not None:self.permission_publish_check(permission_binding)
                    if self.window_record and self.window_record.get('publication_deadline') is not None and time.monotonic()>=self.window_record['publication_deadline']:raise RuntimeError('Transition publication deadline expired')
                except Exception as foreground_error:return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result(foreground_error if isinstance(foreground_error,RetainedPause) else 'Foreground changed before publication; session closed',request.get('params',{}).get('name'),closure_reason='publication-foreground-fault')}
        return response

    def shutdown(self):
        self.close_backend()
        if self.backend:self.backend.shutdown()

class StdioTransport:
    """Serialize desktop work; read cancellation and closure independently."""
    def __init__(self,server):
        self.startup_responses=queue.Queue(maxsize=1);self.writer_stop=threading.Event();self.startup_writer=None
        self.server=server;self.output_lock=threading.Lock();self.output_stream=None;self.pending=queue.Queue();self.tokens={};self.token_lock=threading.Lock();self.disconnected=threading.Event()
    def interrupt(self,request_id=None,all_requests=False):
        with self.token_lock:
            for key,token in self.tokens.items():
                if all_requests or key==request_id:token.set()
        active=self.server.cancel_token
        if self.server.backend and (all_requests or (active is not None and active.is_set())):self.server.backend.cancelled.set()
    def write_response(self,response):
        with self.output_lock:
            self.output_stream.write(json.dumps(response)+'\n');self.output_stream.flush()

    def write_startup_responses(self):
        # One bounded daemon writer: output backpressure must never block the
        # stdin reader that consumes cancellation, close, and disconnect.
        while not self.writer_stop.is_set():
            try:response=self.startup_responses.get(timeout=.1)
            except queue.Empty:continue
            if self.writer_stop.is_set():break
            try:self.write_response(response)
            except (BrokenPipeError,OSError):
                self.disconnected.set();self.interrupt(all_requests=True);break

    def read(self,stream):
        try:
            for line in stream:
                try:
                    request=json.loads(line)
                    if not isinstance(request,dict) or not isinstance(request.get('method'),str):raise ValueError('Invalid request')
                    params=request.get('params',{})
                    if not isinstance(params,dict):raise ValueError('Params must be an object')
                    rid=request.get('id')
                    if rid is not None and (not isinstance(rid,(str,int)) or isinstance(rid,bool)):raise ValueError('Invalid request ID')
                    if rid is not None:
                        with self.token_lock:duplicate=rid in self.tokens
                        if duplicate:
                            # No status shortcut, close, input or token mutation
                            # is permitted for a duplicate in-flight request ID.
                            self.pending.put(({'_protocol_error':'Duplicate pending request ID','id':rid},threading.Event()))
                            continue
                    if request['method']=='notifications/cancelled':self.interrupt(params.get('requestId'));continue
                    if request['method']=='tools/call':
                        if not isinstance(params.get('name'),str) or not isinstance(params.get('arguments',{}),dict):raise ValueError('Invalid tool arguments')
                        if params['name']=='desktop_status' and rid is not None:
                            snapshot=self.server.startup_status_snapshot()
                            if snapshot is not None:
                                try:
                                    self.startup_responses.put_nowait({'jsonrpc':'2.0','id':rid,'result':{'content':[text(snapshot)]}})
                                except queue.Full:pass # Busy: retain normal serialized handling below.
                                else:continue
                        if params['name']=='desktop_pause':
                            # Reader must never wait for state/publication locks.
                            # Bind manual intent to this consent owner before
                            # cancelling only its current operation. The worker
                            # performs the fenced state transition later.
                            backend=self.server.backend;consent=self.server.consent_id
                            request['_pause_owner']=(backend,consent)
                            operation=getattr(backend,'operation_cancelled',None)
                            if backend is not self.server.backend or consent!=self.server.consent_id:
                                request['_admission_error']='Pause consent owner changed'
                            elif self.server.interruption_policy=='retain-sharing' and backend is not None:
                                self.server.manual_pause_latch=(backend,consent)
                                if operation is not None:operation.set()
                            else:self.interrupt(all_requests=True)
                        if params['name']=='desktop_close':self.interrupt(all_requests=True)
                    request['_generation']=self.server.generation;token=threading.Event()
                    if rid is not None:
                        with self.token_lock:self.tokens[rid]=token
                    self.pending.put((request,token))
                except (BrokenPipeError,OSError):
                    self.disconnected.set();self.interrupt(all_requests=True);break
                except Exception as error:self.pending.put(({'_parse_error':str(error)},threading.Event()))
        finally:self.disconnected.set();self.interrupt(all_requests=True);self.pending.put(None)
    def run(self,input_stream,output_stream):
        self.output_stream=output_stream
        self.startup_writer=threading.Thread(target=self.write_startup_responses,daemon=True,name='startup-status-writer')
        self.startup_writer.start()
        threading.Thread(target=self.read,args=(input_stream,),daemon=True).start()
        try:
            while True:
                item=self.pending.get()
                if item is None:break
                request,token=item;params=request.get('params') or {}
                self.server.execution_lock.acquire()
                try:
                    latch=self.server.manual_pause_latch
                    if latch is not None and latch[0] is self.server.backend and latch[1]==self.server.consent_id and self.server.state in ('active','resuming'):
                        self.server.begin_pause()
                    if '_protocol_error' in request:response={'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32600,'message':request['_protocol_error']}}
                    elif '_parse_error' in request:response={'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32700,'message':request['_parse_error']}}
                    else:
                        if '_pause_owner' in request:
                            owner,consent=request['_pause_owner']
                            if owner is not self.server.backend or consent!=self.server.consent_id:request['_admission_error']='Pause consent owner changed'
                        self.server.cancel_token=token;self.server.request_epoch=request.get('_generation')
                        if self.disconnected.is_set() and request.get('method')=='tools/call' and params.get('name') not in ('desktop_status','desktop_close'):token.set()
                        response=self.server.handle(request)
                    if response is not None:
                        with self.server.state_lock:
                            response=self.server.fence_response(request,response)
                            self.write_response(response)
                except (BrokenPipeError,OSError):self.disconnected.set();self.interrupt(all_requests=True);break
                finally:
                    self.server.cancel_token=None;self.server.request_epoch=None
                    self.server.execution_lock.release()
                    with self.token_lock:
                        rid=request.get('id')
                        if self.tokens.get(rid) is token:self.tokens.pop(rid,None)
        finally:
            self.writer_stop.set();self.disconnected.set();self.interrupt(all_requests=True);self.server.shutdown()
            self.startup_writer.join(timeout=.2)

def main():
    server=Server();server.recover_cursor_glow();transport=StdioTransport(server)
    def terminate(signum,frame):
        if server.backend:server.backend.cancelled.set()
        raise SystemExit(0)
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,terminate)
    transport.run(sys.stdin,sys.stdout)

if __name__=='__main__':main()
