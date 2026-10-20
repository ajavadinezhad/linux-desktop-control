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

VERSION = '0.8.17'
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
        if kind == 'sequence':
            steps = a.get('steps')
            if in_sequence or not isinstance(steps,list) or not 1 <= len(steps) <= 8:
                raise ValueError('Provide 1..8 non-nested steps')
            if any(not isinstance(step,dict) for step in steps):raise ValueError('Each step must be an object')
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
ACTION_SCHEMA['properties']['steps']={'type':'array','items':STEP_SCHEMA,'minItems':1,'maxItems':8}

def tools():
    specs=[
      ('desktop_start','Request personal GNOME consent for one monitor, keyboard and pointer; return a fresh screenshot. Optional cursor_glow temporarily changes the desktop-wide cursor theme and restores it on close.',{'session_seconds':{'type':'integer','minimum':120,'maximum':600,'default':120,'description':'Optional initial native-helper lease in seconds, physical_takeover required. Negotiated once before calibration; default120, hard maximum600. No active renewal; Stop and faults remain terminal.'},'physical_takeover':{'type':'boolean','default':False,'description':'Explicit opt-in to a separately installed native activity helper; administrator authorization follows personal GNOME sharing approval. Backend receives only coarse activity/fault notices, never raw input descriptors. Not human-provenance attestation.'},'cursor_glow':{'type':'boolean','description':'Explicit opt-in after explaining desktop-wide theme scope. Applies real themed cursor glow while active; custom app cursors may ignore it.'},'pointer_motion_return':{'type':'boolean','default':False,'description':'With retained sharing and native observation, yield on mouse movement and return once to the last confirmed point after physical quiet in the same app. No action replay.'},'interruption_policy':{'type':'string','enum':['close','retain-sharing'],'default':'close','description':'Opt-in retained consent for explicit pause/resume; physical observer faults remain terminal. No automatic cursor return or replay.'}}),
      ('desktop_observe','Return a fresh screenshot and dimensions. Optional inspect_target binds a single-use editable accessibility identity; inspect before input.',{'inspect_target':{'type':'boolean'}}),
      ('desktop_action','Perform bounded input and return a fresh screenshot. Text/keys need same-call focus or a sequence beginning with a target click/focus shortcut. Coordinates use logical_size. Discrete wheel steps only. Text uses GNOME Unicode composition by default; verify actual results. Never replay uncertain input.',{'action':ACTION_SCHEMA,'target_id':{'type':'string','minLength':32,'maxLength':32},'recovery_observation_id':{'type':'string'},'window_observation_id':{'type':'string','minLength':32,'maxLength':32},'window_fit_shared':{'type':'boolean','description':'Separate opt-in Alt+F10 resize toggle fitting the current oversized focused window to the shared monitor. Exactly two verified monitors; center/titlebar midpoint and strictly largest intersection must identify the shared monitor. Same-window full containment required after; no focus activation or retry.'},'window_normalize_for_move':{'type':'boolean','description':'Separate opt-in Alt+F10 resize toggle of the currently focused window on the other of two verified monitors before a later monitor move. Only a frame not wholly source-contained is admitted; origin and center must identify that source; same-window full source containment required after. No focus activation or content observation.'},'window_move_to_shared':{'type':'boolean','description':'Opt-in single Super+Shift+Arrow move of the currently focused window from the other monitor to the shared monitor; exactly two unambiguous monitors and unchanged configured shortcut required. No focus activation or unseen-content claim.'},'focus_transition':{'type':'boolean','description':'Only one explicit left click, launcher/Return or Ctrl+s/Ctrl+Shift+s/Ctrl+o gesture may change foreground; no remaining batch. Inspect its returned image before further input.'}}),
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

class Server:
    def __init__(self,factory=Desktop):
        self.factory=factory;self.backend=None;self.cancel_token=None;self.request_epoch=None
        self.state_lock=threading.RLock();self.generation=0;self.state='closed'
        # Opening a replacement session must wait until every owned resource
        # from the previous session has finished cleanup. Cancellation itself
        # never waits for this lock.
        self.lifecycle_lock=threading.RLock()
        self.execution_lock=threading.RLock()
        self.owner_cancel_events={}
        self.interruption_policy='close';self.pause_id=None;self.pause_reason=None;self.pause_fence_generation=-1;self.pause_watch_stop=None
        self.pointer_motion_return=False;self.consent_id=None;self.native_pause_epoch=None;self.manual_pause_requested=False
        self.return_state='disabled';self.return_attempted=set();self.return_record=None
        self.recovery=RecoveryLedger();self.target_provider=None;self.target_record=None
        self.cursor_glow=None;self.cursor_glow_pending=None;self.cursor_glow_warning=None;self.cursor_glow_last=None
        self.physical_takeover=False;self.physical_takeover_warning=None;self.native_activity=None;self.native_activity_last=None;self.native_session_seconds=120
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

    def invalidate(self,expected_native=None,expected_indicator=None,warning=None):
        conditional=expected_native is not None or expected_indicator is not None
        if expected_native is not None:self.cancel_observer('native_activity',expected_native)
        if expected_indicator is not None:self.cancel_observer('indicator',expected_indicator)
        if not conditional and self.backend:self.backend.cancelled.set()
        with self.state_lock:
            if expected_native is not None and self.native_activity is not expected_native:return False
            if expected_indicator is not None and self.indicator is not expected_indicator:return False
            if conditional and self.state not in ('opening','active','pausing','paused','resuming'):return False
            if conditional and self.backend:self.backend.cancelled.set()
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
            capture_allowed=active,input_allowed=active and not self.recovery.inspection_required,
            sharing_active=bool(raw.get('active')),interruption_policy=self.interruption_policy,
            pause={'pause_id':self.pause_id,'reason':self.pause_reason,'automatic_return':self.pointer_motion_return,'automatic_resume':self.pointer_motion_return,
                'return_state':self.return_state},
            recovery=self.recovery.snapshot(),fresh_observation_required=not active or self.recovery.inspection_required)
        if not active:result['logical_size']=[0,0]
        if self.target_cleanup_warning:result['accessibility_cleanup_warning']=self.target_cleanup_warning
        result['native_activity']=native
        result['physical_takeover']={'enabled':self.physical_takeover and native.get('active') is True,'classification':'native-device-source-activity','human_provenance':False}
        if self.physical_takeover_warning:result['physical_takeover_warning']=self.physical_takeover_warning
        if self.indicator_warning:result['indicator_warning']=self.indicator_warning
        result['cursor_glow']=self.cursor_glow.status() if self.cursor_glow else (self.cursor_glow_pending.status() if self.cursor_glow_pending else (self.cursor_glow_last or {'active':False}))
        if self.cursor_glow_warning:result['cursor_glow_warning']=self.cursor_glow_warning
        return result

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
        if event is not None:event.set()
        with self.state_lock:
            if backend is not self.backend:return False
            if expected_native is not None and self.native_activity is not expected_native:return False
            if expected_epoch is not None and not expected_native.is_current_yield(expected_epoch):return False
            effective_reason='manual' if self.manual_pause_requested else reason
            if self.state in ('pausing','paused') and self.pause_reason==effective_reason and (expected_epoch is None or self.native_pause_epoch==expected_epoch):return True
            if self.state not in ('active','resuming','pausing','paused'):raise RuntimeError('Only active sharing can pause')
            current=getattr(self.backend,'operation_cancelled',None)
            if current is not None:current.set()
            self.generation+=1;self.pause_fence_generation=self.generation
            self.state='pausing';self.pause_id=uuid.uuid4().hex
            self.pause_reason=effective_reason if effective_reason in ('manual','pointer-motion') else 'manual'
            self.native_pause_epoch=expected_epoch
            self.return_record=getattr(backend,'confirmed_pointer_record',None)
            self.return_state='waiting-quiet' if self.pause_reason=='pointer-motion' and self.pointer_motion_return else 'manual'
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

    def pointer_quiet(self,controller,epoch):
        if not self.pointer_motion_return:return
        threading.Thread(target=self.return_after_quiet,args=(controller,epoch),daemon=True,name='pointer-quiet-return').start()

    def return_after_quiet(self,controller,epoch):
        # Serialize with transport request context and response publication. A
        # source callback can still cancel the captured operation immediately.
        with self.execution_lock,self.lifecycle_lock:
            if not self.pointer_motion_return or self.interruption_policy!='retain-sharing' or self.manual_pause_requested:return False
            if self.state not in ('active','pausing','paused','resuming'):return False
            if self.native_activity is not controller or not controller.is_current_yield(epoch,quiet=True):return False
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

    def check_pause_health(self,pause_id,backend,indicator):
        # Pausing capture/input must not suspend lock, observer or layout checks.
        # A retired watch cannot close a resumed or replacement consent session.
        if self.state!='paused' or self.pause_id!=pause_id:return False
        try:
            if backend.cancelled.is_set() or not backend.status().get('active'):raise RuntimeError('Sharing ended')
            if getattr(backend,'requires_window_guard',False):
                backend.mapping_guard()
                self.pause_context_signature(indicator.context())
            return True
        except Exception:
            with self.lifecycle_lock:
                with self.state_lock:
                    if self.backend is not backend or self.indicator is not indicator or self.state!='paused' or self.pause_id!=pause_id:return False
                    self.invalidate()
                self.close_backend()
            return False

    def resume_sharing(self,args,return_record=None,expected_native=None,expected_epoch=None):
        with self.lifecycle_lock:
            self.guard(('paused',))
            if not self.pause_id or args.get('pause_id')!=self.pause_id:
                raise RetainedPause('Stale or missing pause_id; sharing remains paused')
            pause_id=self.pause_id
            if return_record is not None and self.manual_pause_requested:raise RetainedPause('Manual pause superseded automatic return')
            self.require_runtime()
            if self.backend.cancelled.is_set() or not self.backend.status().get('active'):
                raise RuntimeError('Sharing consent ended while paused')
            mapping=getattr(self.backend,'mapping_guard',None)
            if getattr(self.backend,'requires_window_guard',False):
                if not callable(mapping):raise RuntimeError('Verified monitor mapping unavailable')
                mapping()
            if self.physical_takeover:
                native=self.native_activity
                if native is None or (expected_native is not None and native is not expected_native):
                    raise RuntimeError('Native observer is unavailable; a new consent session is required')
                if self.pause_reason=='pointer-motion' or native.status().get('yielded') is True:
                    epoch=(self.native_pause_epoch if self.native_pause_epoch is not None else native.status().get('yield_epoch')) if expected_epoch is None else expected_epoch
                    if not native.is_current_yield(epoch,quiet=True):raise RetainedPause('Physical pointer is not quiet; sharing remains paused')
                    try:native.resume_from_pause(epoch)
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
                if return_record is not None and self.manual_pause_requested:raise RetainedPause('Manual pause superseded automatic return')
                if return_record is None:self.manual_pause_requested=False
                if self.pause_watch_stop:self.pause_watch_stop.set()
                self.pause_watch_stop=None
                self.state='resuming';self.generation+=1;self.pause_fence_generation=self.generation
                if self.request_epoch is not None:self.request_epoch=self.generation
                self.backend.operation_cancelled=threading.Event()
                self.backend.request_cancel=self.cancel_token
                self.backend.pointer_position=None
                self.pause_id=None
            if return_record is not None:
                if self.manual_pause_requested:
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
            if return_record is not None and self.manual_pause_requested:
                self.begin_pause('manual');self.finish_pause()
                raise RetainedPause('Manual pause superseded automatic capture')
            self.backend.resume_capture()
            content=self.capture_result(('resuming',),return_record['context'] if return_record is not None else None)
            self.pause_reason=None
            return content

    def require_runtime(self):
        try:require_current_runtime()
        except RuntimeError:
            self.invalidate();self.close_backend()
            raise

    def startup_status_snapshot(self):
        # Only coarse Python-owned fields: no backend/GUI calls or authority writes.
        if not self.state_lock.acquire(blocking=False):return None
        try:
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
        if self.interruption_policy=='retain-sharing' and (status.get('post_arm_verified') is not True or status.get('post_arm_state')!='verified'):
            raise RuntimeError('Post-ARM mouse readiness is unverified; capture and input refused')

    def enable_physical_guard(self):
        if self.native_activity is not None:raise RuntimeError('Native activity observer already owned')
        self.guard(('opening','active'))
        if self.backend is None or self.backend.status().get('active') is not True:raise RuntimeError('Personal portal consent is required before calibration notification')
        module=self.native_activity_module()
        notice=self.calibration_notice_module().CalibrationNotice()
        controller=module.Controller(
            active=lambda:self.state in ('opening','active','pausing','paused','resuming') and self.backend is not None and self.backend.status().get('active') is True,
            on_activity=lambda:self.native_activity_lost(controller),
            on_fault=lambda error:self.native_activity_lost(controller,error),notice=notice,
            retain_sharing=self.interruption_policy=='retain-sharing',
            on_yield=self.pointer_yielded,on_quiet=self.pointer_quiet,
            **({'session_seconds':self.native_session_seconds} if self.native_session_seconds!=120 else {}))
        # Publish ownership atomically with callback invalidation checks.
        self.own_observer('native_activity',controller)
        controller.start()
        self.require_native_ready()
        self.guard(('opening','active'))
        self.require_runtime()
        self.physical_takeover=True;self.physical_takeover_warning=None

    def native_activity_lost(self,expected,error=None):
        if not self.invalidate(expected_native=expected,warning='native' if error else None):return
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

    def foreground_lost(self,expected):
        if not self.invalidate(expected_indicator=expected):return
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
            self.return_state='closed'
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
            if context.get('available') is True:return context
            if context.get('reason')!='no-foreground-window' or settle_seconds<=0 or time.monotonic()>=deadline:raise RuntimeError('Foreground context unavailable or system UI active; session must close')
            # This is read-only app-launch settling, never readiness or a retry.
            if callable(getattr(self.backend,'wait_interruptibly',None)):self.backend.wait_interruptibly(.05)
            else:time.sleep(.05)

    def window_guard_module(self):
        self.require_runtime()
        path=os.path.join(os.path.dirname(__file__),'window_guard.py')
        spec=importlib.util.spec_from_file_location('desktop_window_guard',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def stable_transition_context(self,deadline):
        stable=None;since=None
        while True:
            context=self.read_window_context(max(0,deadline-time.monotonic()))
            signature=self.window_guard_module().WindowGuard.signature(context)
            now=time.monotonic()
            if signature!=stable:stable=signature;since=now
            if now-since>=.15:return context
            if now>=deadline:raise RuntimeError('Intentional transition did not settle; session must close')
            wait=min(.05,deadline-now)
            if callable(getattr(self.backend,'wait_interruptibly',None)):self.backend.wait_interruptibly(wait)
            else:time.sleep(wait)

    def capture_result(self,allowed,expected_window=None,transition_settle=False,moved_window=None):
        required=getattr(self.backend,'requires_window_guard',False)
        deadline=time.monotonic()+2
        attempts=0
        while True:
            before=(self.stable_transition_context(deadline) if transition_settle else self.read_window_context()) if required else None
            if moved_window is not None:
                self.backend.mapping_guard()
                self.window_guard_module().validate_monitor_arrival(before,*moved_window)
            if expected_window is not None and self.window_guard_module().WindowGuard.signature(before)!=expected_window:raise RuntimeError('Foreground changed after input; session must close')
            self.require_runtime()
            self.guard(allowed)
            if self.state=='opening' and self.physical_takeover:self.require_native_ready()
            png=self.backend.capture();self.guard(allowed)
            if self.state=='opening' and self.physical_takeover:self.require_native_ready()
            after=self.read_window_context(max(0,deadline-time.monotonic()) if transition_settle else 0) if required else None
            if moved_window is not None:
                self.backend.mapping_guard()
                self.window_guard_module().validate_monitor_arrival(after,*moved_window)
            if not required or self.window_guard_module().WindowGuard.signature(before)==self.window_guard_module().WindowGuard.signature(after):break
            # Only the already-authorized single transition may settle across a
            # capture race. Discard pixels and observe again; never repeat input.
            attempts+=1
            if not transition_settle or attempts>=2 or time.monotonic()>=deadline:raise RuntimeError('Foreground changed while capturing; no image is published')
        with self.state_lock:
            self.guard(allowed)
            if self.state=='opening' and self.physical_takeover:self.require_native_ready()
            operation=getattr(self.backend,'operation_cancelled',None)
            if operation is not None and operation.is_set():raise RetainedPause('Capture discarded by pause')
            self.state='active'
        self.recovery.observed();self.window_record=None
        observation={'available':False}
        if after:
            self.window_record={'id':uuid.uuid4().hex,'generation':self.generation,'issued':time.monotonic(),'context':after}
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
            self.invalidate();self.close_backend();return [text(self.status())]
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
                        self.interruption_policy=policy;self.pause_id=None;self.pause_reason=None
                        self.pointer_motion_return=auto_return;self.consent_id=uuid.uuid4().hex;self.backend.consent_id=self.consent_id
                        self.backend.confirmed_pointer_record=None;self.return_record=None;self.return_attempted=set();self.native_pause_epoch=None;self.manual_pause_requested=False
                        self.return_state='ready' if auto_return else 'disabled'
                        self.state='opening';self.target_record=None
                if previous_owned:
                    self.invalidate();self.close_backend()
                    raise RuntimeError('Previous session resources required cleanup; call desktop_start again for a new consent session')
                try:
                    if getattr(self.backend,'requires_window_guard',False) and self.indicator is None:self.preflight_context()
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
            if 'session_seconds' in args and session_seconds!=self.native_session_seconds:raise ValueError('An active native lease cannot be changed; close before selecting a new initial limit')
            if physical and not self.physical_takeover:raise RuntimeError('Device-source observation must be selected before a new consent session')
            expected=self.window_guard_module().WindowGuard.signature(self.window_record['context']) if self.window_record else None
            return self.capture_result(('active',),expected)
        self.guard(('active',));self.ensure_backend()
        if name=='desktop_action':
            record=self.target_record;self.target_record=None
            window_record=self.window_record;self.window_record=None
            self.recovery.begin(args.get('recovery_observation_id'))
            target=None;window=None
            # Reset before backend validation, so an old call cannot contaminate
            # the current partial-result report.
            self.backend.transaction_info={'completed_steps':0,'failed_step':None,'input_events_attempted':0,'input_characters_completed':0}
            try:
                monitor_move=args.get('window_move_to_shared',False);moved_window=None
                normalize_window=args.get('window_normalize_for_move',False)
                if type(normalize_window) is not bool:raise ValueError('window_normalize_for_move must be boolean')
                fit_window=args.get('window_fit_shared',False)
                if type(fit_window) is not bool:raise ValueError('window_fit_shared must be boolean')
                if type(monitor_move) is not bool:raise ValueError('window_move_to_shared must be boolean')
                if sum((normalize_window,fit_window,monitor_move))>1:raise ValueError('Window setup gestures require separate observed actions')
                transition=args.get('focus_transition',False)
                if (monitor_move or normalize_window or fit_window) and (transition is not True or not getattr(self.backend,'requires_window_guard',False)):raise ValueError('Monitor move requires a guarded explicit focus transition')
                if type(transition) is not bool:raise ValueError('focus_transition must be boolean')
                if transition and 'target_id' in args:raise ValueError('A focus transition cannot reuse an editable-control identity')
                if getattr(self.backend,'requires_window_guard',False):
                    if not window_record or args.get('window_observation_id')!=window_record['id'] or window_record['generation']!=self.generation:raise RuntimeError('Foreground observation expired or invalid; inspect a fresh screenshot before input')
                    def cancel_window():
                        self.backend.cancelled.set()
                        if self.cancel_token:self.cancel_token.set()
                    module=self.window_guard_module();window=module.WindowGuard(self.indicator,window_record['context'],cancel_window);window.check()
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
                        self.indicator.armed=None
                    self.backend.begin_transition=begin_transition if transition else None
                if 'target_id' in args:
                    if not record or args['target_id']!=record['id'] or record['epoch']!=self.generation or time.monotonic()-record['issued']>60:
                        raise RuntimeError('Target identity expired or invalid; inspect a fresh desktop_observe(inspect_target=true) result before input')
                    target=record['target'];target.live(active=True,focused=True);self.guard(('active',))
                self.backend.target_guard=target
                try:
                    self.backend.action(args['action'])
                    if window is not None and not transition:window.check()
                finally:
                    self.backend.target_guard=None;self.backend.pointer_reader=None;self.backend.begin_transition=None;self.backend.endpoint_context=None
                    self.backend.window_guard=None;self.backend.window_transition=False;self.backend.transition_activation_key=None
                    if self.indicator:self.indicator.armed=None
                content=self.capture_result(('active',),window.baseline if window is not None and not transition else None,transition_settle=transition,moved_window=moved_window)
            except BaseException:
                self.backend.pointer_reader=None;self.backend.begin_transition=None;self.backend.endpoint_context=None
                self.backend.window_guard=None;self.backend.window_transition=False;self.backend.transition_activation_key=None
                if self.indicator:self.indicator.armed=None
                self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
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


    def error_result(self,error,name=None):
        retained=isinstance(error,RetainedPause) and self.interruption_policy=='retain-sharing'
        if name in ('desktop_start','desktop_observe','desktop_action','desktop_resume','desktop_pause') and not retained:
            try:self.invalidate();self.close_backend()
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
            if request.get('params',{}).get('name')=='desktop_start' and self.physical_takeover:
                try:self.require_native_ready()
                except Exception:
                    return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result('Native readiness changed before startup image publication','desktop_start')}
            if self.interruption_policy=='retain-sharing' and self.state in ('pausing','paused'):
                return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result(RetainedPause('Screenshot discarded by pause; no image published'),request.get('params',{}).get('name'))}
            if getattr(self.backend,'requires_window_guard',False):
                try:
                    if not self.window_record or self.window_guard_module().WindowGuard.signature(self.read_window_context())!=self.window_guard_module().WindowGuard.signature(self.window_record['context']):raise RuntimeError('Foreground changed')
                except Exception:
                    name=request.get('params',{}).get('name');self.recovery.observation_id=None
                    if name=='desktop_action':self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
                    return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result('Screenshot invalidated by foreground change; no image published',name)}
            if request.get('_generation',self.generation)!=self.generation or self.state!='active' or (self.cancel_token and self.cancel_token.is_set()) or (self.backend and self.backend.cancelled.is_set()) or (getattr(self.backend,'operation_cancelled',None) is not None and self.backend.operation_cancelled.is_set()):
                name=request.get('params',{}).get('name');self.recovery.observation_id=None;self.target_record=None;self.window_record=None
                if name=='desktop_action':self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
                return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result(RetainedPause('Screenshot invalidated by pause; no image published') if self.interruption_policy=='retain-sharing' and (self.state in ('pausing','paused') or (getattr(self.backend,'operation_cancelled',None) is not None and self.backend.operation_cancelled.is_set())) else 'Screenshot invalidated by session closure; no image published',name)}
            if getattr(self.backend,'requires_window_guard',False):
                bridge=self.indicator
                guard=self.window_guard_module().WindowGuard(bridge,self.window_record['context'],lambda:self.foreground_lost(bridge))
                bridge.armed=guard
                try:guard.check()
                except Exception:return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result('Foreground changed before publication; session closed',request.get('params',{}).get('name'))}
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
                            if not self.server.begin_pause():self.interrupt(all_requests=True)
                        if params['name']=='desktop_close':self.interrupt(all_requests=True);self.server.invalidate()
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
                    if '_protocol_error' in request:response={'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32600,'message':request['_protocol_error']}}
                    elif '_parse_error' in request:response={'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32700,'message':request['_parse_error']}}
                    else:
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
