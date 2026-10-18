#!/usr/bin/python3
"""GNOME Wayland desktop backend. No root privileges or private compositor APIs."""
import base64
import hashlib
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

def load_toolbar_bridge():
    path=os.path.join(os.path.dirname(__file__),"toolbar_bridge.py")
    spec=importlib.util.spec_from_file_location("desktop_panel_bridge",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.ToolbarBridge

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gio, GLib, Gst

VERSION = '0.6.5'
DEST = 'org.freedesktop.portal.Desktop'
PATH = '/org/freedesktop/portal/desktop'
RD = 'org.freedesktop.portal.RemoteDesktop'
SC = 'org.freedesktop.portal.ScreenCast'

class CaptureTimeout(RuntimeError):pass

class Desktop:
    def __init__(self):
        Gst.init(None)
        self.loop = GLib.MainLoop()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()
        self.session = None
        self.pipeline = None
        self.fd = None
        self.closed_sub = None
        self.portal_closed = False
        self.stopped = threading.Event()
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
            if self.stopped.wait(.05) or (self.session and time.monotonic()-self.last_used > 300):
                with self.lock:
                    if self.stopped.is_set() or (self.session and time.monotonic()-self.last_used > 300):
                        self.stopped.set()
                        self.close()
                time.sleep(.05)

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
                if self.stopped.is_set() or (getattr(self,'request_cancel',None) and self.request_cancel.is_set()) or time.monotonic() > deadline:
                    self.call('org.freedesktop.portal.Request', 'Close', '()', (), path=actual)
                    raise RuntimeError('Portal request stopped or timed out')
            code, data = result
            if code:
                raise RuntimeError(f'Portal permission cancelled or denied (response {code})')
            return data
        finally:
            self.bus.signal_unsubscribe(sub)

    def start(self):
        with self.lock:
            if self.session and not self.stopped.is_set():
                return self.status()
            self.close()
            self.portal_closed = False
            self.stopped.clear()
            if getattr(self,'request_cancel',None) and self.request_cancel.is_set():
                self.stopped.set()
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
                reply, fds = self.bus.call_with_unix_fd_list_sync(DEST, PATH, SC,
                    'OpenPipeWireRemote', GLib.Variant('(oa{sv})', (self.session, {})),
                    GLib.VariantType('(h)'), Gio.DBusCallFlags.NONE, 5000, None, None)
                self.fd = fds.get(reply.unpack()[0])
                self._start_capture_pipeline()
                self.capture()
                return self.status()
            except BaseException:
                self.close()
                raise

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
            self.stopped.set()

    def status(self):
        return {'active': bool(self.session) and not self.stopped.is_set(),
                'monitor': self.monitor_geometry(),
                'pid': os.getpid(), 'idle_timeout_seconds': 300,
                'logical_size': [getattr(self,'width',0), getattr(self,'height',0)],
                'stop': f'kill -USR1 {os.getpid()}',
                'cleanup_warning':getattr(self,'cleanup_warning',None),
                'portal_closed_confirmed':getattr(self,'portal_closed',False) or (self.session is None and not getattr(self,'cleanup_warning',None))}

    def monitor_geometry(self):
        position=getattr(self,'props',{}).get('position')
        if isinstance(position,(list,tuple)) and len(position)==2:
            return {'x':position[0],'y':position[1],'width':getattr(self,'width',0),'height':getattr(self,'height',0)}
        return None

    def check(self):
        if getattr(self,'request_cancel',None) and self.request_cancel.is_set():self.stopped.set()
        if self.stopped.is_set() or not self.session:
            raise RuntimeError('Desktop session is stopped; call desktop_start for new consent')
        if getattr(self,'action_deadline',None) and time.monotonic()>self.action_deadline:
            raise RuntimeError('Input sequence exceeded 15 seconds; stopped before next event')
        self.last_used = time.monotonic()

    def pause(self, seconds):
        if self.stopped.wait(seconds):
            raise RuntimeError('Desktop control stopped')
        self.check()

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
                self.pause(.35)
                self._start_capture_pipeline()
                png=self._capture_once(new_stream=True)
                self.capture_info['pipeline_reconnected']=True
                return png

    def _capture_once(self,new_stream=False):
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
                    'frame_age_ms':age_ms,'freshness':'new_stream' if new_stream else 'post_settle_frame'}
                png = buf.extract_dup(0, buf.get_size())
                self.frames += 1
                return png
            error = self.pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
            if error:
                raise RuntimeError(str(error.parse_error()[0]))
        raise CaptureTimeout('No fresh screen frame received within 5 seconds')

    def notify(self, method, sig, *args):
        self.check()
        target=getattr(self,'target_guard',None)
        if target is not None:
            if method=='NotifyKeyboardKeysym' and args[-1]:target.check()
            elif method not in ('NotifyKeyboardKeysym','NotifyPointerButton') or (method=='NotifyPointerButton' and args[-1]):target.live()
            self.check()
        if getattr(self,'action_deadline',None):
            self.transaction_info['input_events_attempted'] += 1
        self.call(RD, method, '(oa{sv}'+sig+')', (self.session, {}, *args))

    def position(self, x, y):
        x, y = float(x), float(y)
        if not all(map(math.isfinite, (x,y))) or not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError('Position outside logical_size of selected monitor')
        self.notify('NotifyPointerMotionAbsolute', 'udd', self.node, x, y)
        self.pointer_position=(x,y)

    def move_to(self,x,y,seconds=.25):
        start=getattr(self,'pointer_position',None)
        if start is None or seconds==0:
            self.position(x,y)
            return
        count=max(1,int(seconds/.016))
        for i in range(1,count+1):
            t=i/count
            blend=t*t*(3-2*t)
            self.position(start[0]+(x-start[0])*blend,start[1]+(y-start[1])*blend)
            self.pause(seconds/count)

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
        for kind, code in reversed(self.held[:]):
            try:
                method = 'NotifyKeyboardKeysym' if kind == 'key' else 'NotifyPointerButton'
                self.call(RD, method, '(oa{sv}iu)', (self.session, {}, code, 0))
            except Exception:
                failed=True
                self.stopped.set()
                # Fail closed: remove the portal's virtual input devices instead
                # of silently continuing with a potentially held button/key.
                try:
                    self.call('org.freedesktop.portal.Session','Close','()',(),path=self.session)
                    self.portal_closed=True
                    self.session=None
                except Exception:
                    self.cleanup_warning='Input release and portal close failed. Stop sharing using the GNOME indicator.'
                break
        self.held.clear()
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
            self.pause(.02)
            for sym in reversed(chord):self.state('key',sym,False)
            self.pause(.1)
            for digit in format(code,'x'):
                self.state('key',ord(digit),True);self.state('key',ord(digit),False)
                self.pause(.015)
            self.state('key',0xff0d,True);self.state('key',0xff0d,False)
            self.pause(.1)
        else:
            sym={'\n':0xff0d,'\t':0xff09}.get(char,code if 0x20<=code<=0xff else 0x01000000|code)
            self.state('key',sym,True);self.state('key',sym,False)
            self.pause(.005)

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
            if kind not in ('keys','text') or not isinstance(f,dict):
                raise ValueError('focus is supported only for keys/text')
            self.validate_point(f.get('x'),f.get('y'))
        if kind in ('text','keys') and not in_sequence and 'focus' not in a and not self.activates_focus(a) and not getattr(self,'target_guard',None):
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
            self.action_deadline=time.monotonic()+15
            try:
                for index,step in enumerate(steps):
                    self.transaction_info['failed_step']=index+1
                    self.check()
                    if 'focus' in step:
                        self._primitive({'type':'click',**step['focus']})
                        self.pause(.15)
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
            finally:
                self.action_deadline=None
                self.release()

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
                        self.state('button',button,True)
                        self.pause(.04)
                        self.state('button',button,False)
                        self.pause(.07)
                elif kind == 'scroll':
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
                    self.pause(.04)
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
                    self.state('button',272,True)
                    for point in path[1:]:
                        self.position(*point)
                        self.pause(.02)
                    self.state('button',272,False)
                elif kind == 'wait':
                    seconds = float(a.get('seconds',.2))
                    if not math.isfinite(seconds) or not 0<=seconds<=5:
                        raise ValueError('Wait must be 0..5 seconds')
                    self.pause(seconds)
                elif kind != 'move' and kind not in ('click','scroll'):
                    raise ValueError('Unknown action type')
                self.pause(.1)
            finally:
                if self.release():
                    raise RuntimeError('Input release failed; control stopped and portal closure attempted. Check desktop_status and GNOME sharing indicator.')

    def close(self):
        with self.lock:
            self.stopped.set()
            try:self.release()
            except Exception:self.cleanup_warning='Input release failed; portal closure attempted. Check sharing.'
            # Always attempt portal closure even when capture/fd cleanup fails.
            if self.pipeline:
                try:self.pipeline.set_state(Gst.State.NULL)
                except Exception:self.cleanup_warning='Capture shutdown failed; portal closure attempted. Check sharing.'
                finally:self.pipeline=None
            if self.fd is not None:
                try:os.close(self.fd)
                except OSError:self.cleanup_warning='Capture descriptor cleanup failed; portal closure attempted. Check sharing.'
                finally:self.fd=None
            if self.session:
                if not getattr(self,'portal_closed',False):
                    try:
                        self.call('org.freedesktop.portal.Session','Close','()',(),path=self.session)
                        self.portal_closed=True
                    except Exception:
                        if not getattr(self,'portal_closed',False):
                            self.cleanup_warning='Portal closure could not be confirmed. Use the GNOME sharing indicator to stop sharing.'
                self.session=None
            if self.closed_sub:
                try:self.bus.signal_unsubscribe(self.closed_sub)
                except Exception:self.cleanup_warning='Portal signal cleanup failed. Check sharing.'
                finally:self.closed_sub=None
            self.pointer_position=None

    def shutdown(self):
        self.shutdown_requested = True
        self.stopped.set()
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
    specs = [
      ('desktop_start','Request GNOME permission for one monitor, keyboard and mouse; return screenshot. Optional nonsecret task_summary preserves intent if the human presses Pause.',{'task_summary':{'type':'string','minLength':1,'maxLength':1000}}),
      ('desktop_observe','Return fresh PNG and dimensions. Optional inspect_target=true binds an opaque single-use identity to the currently focused editable accessibility control, without reading names/text/values. Inspect image before using target_id; unavailable accessibility is explicit.',{'inspect_target':{'type':'boolean'}}),
      ('desktop_action','Perform one approved desktop transaction and return a fresh screenshot. Approval may focus ChatGPT: text/keys require focus:{x,y} to click the target in THIS call. Alternatively type=sequence with 1..8 steps, starting with a target click or keys:[Alt,F2]/[Super], then text/keys without another approval. Never split focus acquisition and typing across calls. Sequences are bounded, interruptible, not rollback-atomic. Coordinates use logical_size, relative to selected monitor. Scrolling uses discrete wheel steps: integer dx/dy in -50..50, positive dy down. Smooth pixels are unsupported. Text defaults to GNOME Unicode composition for non-ASCII; text_mode=keysyms is optional but may drop unsupported characters. Verify the exact rendered text. Within one sequence, later pointer moves/clicks interpolate from the known current point; the first movement may jump after approval. Drag uses path of [x,y]. Keys is a simultaneous chord, e.g. [Ctrl,a]. Text entry does not change the clipboard.',{'action':ACTION_SCHEMA,'target_id':{'type':'string','minLength':32,'maxLength':32,'description':'Optional single-use identity from desktop_observe(inspect_target=true). Reject vanished, hidden, changed or wrongly focused controls; no coordinate fallback. Use focus or initial click to reacquire the observed window after approval, then exact control focus is checked before keys. Expires after60seconds and any input/observe/Pause/Stop. Guarded text is limited to32characters across the action; accessibility latency is extra and may cause an honest partial result at the15second dispatch deadline.'},'recovery_observation_id':{'type':'string','description':'After uncertain input, inspect desktop_observe image and pass the returned recovery.observation_id before deciding another action.'},'task_checkpoint':{'type':'object','description':'Nonsecret confirmed progress before this action and remaining intent; never action payloads or credentials.','properties':{'completed_summary':{'type':'string','maxLength':1000},'next_step':{'type':'string','minLength':1,'maxLength':1000}},'required':['completed_summary','next_step'],'additionalProperties':False}}),
      ('desktop_pause','Hand the desktop back to the human for any needed input, judgment, information or human-only action. Interrupt current work, invalidate queued input/capture, release input and close the portal. No screenshots while paused. Explain the reason to the user; never include credentials in context.',{'reason':{'type':'string','minLength':1,'maxLength':500},'task_summary':{'type':'string','minLength':1,'maxLength':1000},'handoff_kind':{'type':'string','enum':['human_action','background_wait','manual_takeover']},'job_reference':{'type':'string','maxLength':500}}),
      ('desktop_resume','Only after the human explicitly says ready/continue: resume this handoff, request fresh GNOME consent and return a fresh screenshot before any input. Never resume on elapsed time or guess that the human finished. No cached pointer/window assumptions.',{'handoff_id':{'type':'string'},'human_ready':{'type':'boolean','const':True}}),
      ('desktop_stop','Release input, close capture/control, and clear in-memory handoff context. Full status includes cleanup warnings.',{}),
      ('desktop_status','Get state without capturing. For an unfinished foreground task, pass the last status_revision as wait_after and timeout_seconds (1–50) to wait for a control/task state change. This never resumes or captures; Continue and consent are still human actions. Reissue after timeout while the task remains pending.',{'wait_after':{'type':'string','maxLength':64},'timeout_seconds':{'type':'number','minimum':1,'maximum':50}})]
    return [{'name':n,'description':d,'inputSchema':{'type':'object','properties':p,
             'required':[k for k in p if k not in ('recovery_observation_id','task_checkpoint','target_id') and n not in ('desktop_start','desktop_status','desktop_observe') and (n!='desktop_pause' or k in ('reason','task_summary'))],'additionalProperties':False},
             'annotations':{'readOnlyHint':n in ('desktop_status','desktop_observe'),
                            'destructiveHint':n=='desktop_action','openWorldHint':True}}
            for n,d,p in specs]

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
    def __init__(self, factory=Desktop):
        self.factory=factory
        self.backend=None
        self.cancel_token=None
        self.request_epoch=None
        self.boundary_prepared=False
        self.state_lock=threading.RLock()
        self.control_epoch=0
        self.state='stopped'
        self.handoff=None
        self.recovery=RecoveryLedger()
        self.panel=None
        self.task_summary="Desktop task; consult the conversation before continuing"
        self.panel_control=None
        self.panel_resume=False
        self.toolbar_session_ready=False
        self.toolbar_geometry=None
        self.awaiting_assistant_observation=False
        self.task_checkpoint=None
        self.resume_event=None
        self.operation_active=False
        self.target_provider=None
        self.target_record=None
        self.target_cleanup_warning=None

    def close_target_provider(self):
        provider=self.target_provider;self.target_provider=None
        if provider is not None and callable(getattr(provider,'close',None)):
            try:confirmed=provider.close() is not False
            except Exception:confirmed=False
            self.target_cleanup_warning=None if confirmed else 'Accessibility connection closure unconfirmed; target access is disabled.'

    def inspect_keyboard_target(self):
        self.target_gate()
        if self.target_provider is None:
            path=os.path.join(os.path.dirname(__file__),'target_guard.py')
            spec=importlib.util.spec_from_file_location('desktop_target_guard',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.target_provider=module.AtspiProvider()
        self.target_gate()
        return self.target_provider.snapshot(self.target_gate)

    def target_gate(self):
        self.guard(('active',))
        if callable(getattr(self.backend,'check',None)):self.backend.check()

    def prepare_toolbar(self):
        if self.panel_control and self.factory is Desktop:
            if self.panel is None:self.panel=load_toolbar_bridge()(self.status,self.panel_control)
            self.panel.preflight(self.guard)

    def ensure_panel(self):
        if self.panel_control and self.factory is Desktop:
            if self.panel is None:self.panel=load_toolbar_bridge()(self.status,self.panel_control)
            if not self.panel.bound:self.panel.start(self.guard)
        if self.panel and (self.panel.failed or not self.panel.bound):
            raise RuntimeError('Desktop toolbar unavailable; enable its GNOME extension and reconnect the MCP server')
        if self.panel:self.panel.wait_visible(self.guard)

    def protect_toolbar(self,action):
        if not self.panel:return
        try:diagnostics=self.panel.diagnostics()
        except Exception:
            self.panel.fail()
            raise RuntimeError('Toolbar connection lost; desktop input refused')
        if diagnostics.get('visible') is not True:
            raise RuntimeError('Toolbar is hidden by system UI; observe and reassess before input')
        rect=diagnostics.get('rect');monitor=diagnostics.get('monitor_bounds')
        if not isinstance(rect,list) or len(rect)!=4 or not isinstance(monitor,dict):
            raise RuntimeError('Toolbar geometry unavailable; desktop input refused')
        position=getattr(self.backend,'props',{}).get('position')
        ox,oy=position if isinstance(position,(tuple,list)) and len(position)==2 else (monitor['x'],monitor['y'])
        left,top,width,height=rect
        self.toolbar_geometry={'excluded_rect':[left-ox,top-oy,width,height]}
        def check(a):
            points=[]
            if 'x' in a and 'y' in a:points.append((a['x'],a['y']))
            if isinstance(a.get('focus'),dict):points.append((a['focus'].get('x'),a['focus'].get('y')))
            points.extend(a.get('path',[]))
            for point in points:
                if len(point)!=2:continue
                x,y=point
                if isinstance(x,(int,float)) and isinstance(y,(int,float)) and left<=x+ox<left+width and top<=y+oy<top+height:
                    raise ValueError('Synthetic input cannot target the human toolbar; choose an app target outside its excluded rectangle')
            for step in a.get('steps',[]):check(step)
        check(action)

    @staticmethod
    def validate_handoff(args):
        for key,limit in (('reason',500),('task_summary',1000)):
            value=args.get(key)
            if not isinstance(value,str) or not value.strip() or len(value)>limit:
                raise ValueError(f'{key} must be nonempty text of at most {limit} characters; do not include credentials')

        if args.get('handoff_kind','human_action') not in ('human_action','background_wait','manual_takeover'):
            raise ValueError('Unknown handoff kind')
        if not isinstance(args.get('job_reference',''),str) or len(args.get('job_reference',''))>500:
            raise ValueError('job_reference must be at most 500 characters; no secrets')

    def begin_boundary(self,name,args):
        if name=='desktop_pause':self.validate_handoff(args)
        # Cooperative interruption does not wait for resource cleanup/state writes.
        if self.backend:self.backend.stopped.set()
        with self.state_lock:
            self.control_epoch+=1
            self.target_record=None
            self.state='pausing' if name=='desktop_pause' else 'stopping'
            if name=='desktop_pause':
                self.handoff={'id':uuid.uuid4().hex,'reason':args['reason'].strip(),
                    'task_summary':args['task_summary'].strip(),
                    'kind':args.get('handoff_kind','human_action'),
                    'job_reference':args.get('job_reference','').strip(),
                    'task_checkpoint':dict(self.task_checkpoint) if self.task_checkpoint else None}
            else:self.handoff=None
            return self.control_epoch

    def admission_error(self,name):
        with self.state_lock:
            if name in ('desktop_action','desktop_observe') and self.state!='active':
                return 'Desktop input/capture is not active; paused work requires explicit desktop_resume and a fresh observation'
            if name=='desktop_resume' and self.state!='paused':
                return 'Resume is accepted only after pause completed and the human explicitly said ready/continue'
            if name=='desktop_start' and self.state not in ('stopped','active'):
                return 'desktop_start cannot bypass a handoff; use desktop_resume after explicit human readiness'
        return None

    def guard(self,allowed=None,ignore_cancel=False):
        with self.state_lock:
            if self.request_epoch is not None and self.request_epoch!=self.control_epoch:
                raise RuntimeError('Request invalidated by a later pause/stop; obtain a fresh observation after explicit resume')
            if not ignore_cancel and self.cancel_token is not None and self.cancel_token.is_set():
                if self.backend:self.backend.stopped.set()
                raise RuntimeError('Request cancelled before further desktop input/capture')
            if allowed is not None and self.state not in allowed:
                raise RuntimeError('Desktop is '+self.state+'; input and capture require an active session')

    @staticmethod
    def validate_task_checkpoint(value):
        if not isinstance(value,dict) or set(value)!={'completed_summary','next_step'}:
            raise ValueError('task_checkpoint requires only completed_summary and next_step; no action payloads or credentials')
        for key in ('completed_summary','next_step'):
            if not isinstance(value[key],str) or len(value[key])>1000:
                raise ValueError('Use nonsecret checkpoint summaries of at most 1000 characters')
        if not value['next_step'].strip():raise ValueError('Checkpoint next_step must name remaining work')
        return {key:value[key].strip() for key in ('completed_summary','next_step')}

    def task_status(self,active):
        if self.state in ('paused','pausing'):phase='wait'
        elif self.state in ('starting','resuming'):phase='consent'
        elif self.state in ('stopped','stopping'):phase='end'
        elif self.operation_active:phase='working'
        elif active and (self.awaiting_assistant_observation or (self.recovery.inspection_required and not self.recovery.observation_id)):phase='observe'
        elif active and self.recovery.inspection_required:phase='plan_ack'
        else:phase='waiting_executor'
        task=dict(self.task_checkpoint) if self.task_checkpoint else None
        if task:
            task['last_result_id']=(self.recovery.last or {}).get('result_id')
            task['epoch']=self.control_epoch
        return {'task':task,'resume_event':dict(self.resume_event) if self.resume_event else None,
                'operation_active':self.operation_active,'next_required_action':phase,
                'executor_note':'Toolbar Continue restores consented sharing only. An active foreground assistant must observe and continue the remaining intent; an idle assistant needs a new chat message.'}

    def status(self):
        with self.state_lock:
            raw=self.backend.status() if self.backend else {'active':False,'portal_closed_confirmed':True}
            if self.state=='active' and not raw.get('active'):
                self.state='stopped'
            active=self.state=='active' and raw.get('active',False)
            result=dict(raw,server_version=VERSION,active=active,control_state=self.state,control_epoch=self.control_epoch,
                toolbar=self.toolbar_geometry,toolbar_session_ready=self.toolbar_session_ready,capture_allowed=active,input_allowed=active and not self.recovery.inspection_required,
                recovery=self.recovery.snapshot(),
                ready_to_observe=active and self.awaiting_assistant_observation,
                handoff=dict(self.handoff) if self.handoff else None,
                fresh_observation_required=not active or self.recovery.inspection_required)
            if self.target_cleanup_warning:result['accessibility_cleanup_warning']=self.target_cleanup_warning
            result.update(self.task_status(active))
            if not active:result['logical_size']=[0,0]
            if self.handoff:
                result['human_instructions']='Control and capture are suspended only when state is paused and portal closure is confirmed. Complete the human step, then explicitly tell the assistant ready/continue. Resume requests fresh GNOME consent. Do not share passwords or credentials.'
            revision={k:result.get(k) for k in ('control_state','control_epoch','resume_event','next_required_action','portal_closed_confirmed','cleanup_warning')}
            result['status_revision']=hashlib.sha256(json.dumps(revision,sort_keys=True).encode()).hexdigest()
            return result

    def clear_observation(self):
        self.target_record=None
        self.awaiting_assistant_observation=False
        if self.backend:
            self.backend.pointer_position=None
            self.backend.capture_info={}

    def close_backend(self):
        if self.backend:
            self.backend.stopped.set()
            self.backend.close()
        self.clear_observation()
        self.close_target_provider()

    def closure_confirmed(self):
        if self.backend is None:return True
        raw=self.backend.status()
        return not raw.get('active') and not raw.get('cleanup_warning') and (
            raw.get('portal_closed_confirmed') is True or getattr(self.backend,'session',None) is None)

    def ensure_backend(self):
        self.guard()
        if self.backend is None:self.backend=self.factory()
        self.backend.request_cancel=self.cancel_token
        self.guard()

    def capture_result(self,allowed):
        self.guard(allowed)
        png=self.backend.capture()
        self.guard(allowed)
        with self.state_lock:
            self.guard(allowed)
            self.state='active'
            self.recovery.observed()
        import struct
        w,h=struct.unpack('>II',png[16:24])
        return [text(dict(self.status(),pixel_size=[w,h],
                    capture=getattr(self.backend,'capture_info',{}),
                    transaction=getattr(self.backend,'transaction_info',{}),
                    coordinate_rule='x_logical=x_pixel*logical_width/pixel_width; likewise y')),image(png)]

    def call(self,name,args):
        if name not in {x['name'] for x in tools()}:raise ValueError('Unknown tool')
        if name=='desktop_status':return [text(self.status())]
        if name in ('desktop_pause','desktop_stop'):
            if name=='desktop_pause':self.validate_handoff(args)
            if not self.boundary_prepared:self.begin_boundary(name,args)
            self.guard(ignore_cancel=name=='desktop_stop')
            self.close_backend()
            self.guard(ignore_cancel=name=='desktop_stop')
            with self.state_lock:
                if name=='desktop_pause':
                    if not self.closure_confirmed():
                        raise RuntimeError('Input is gated, but portal closure is unconfirmed. Stop sharing in GNOME before sensitive human work; resume is blocked.')
                    self.state='paused'
                else:
                    self.state='stopped';self.handoff=None
                    self.task_checkpoint=None;self.resume_event=None
            if name=='desktop_stop' and self.closure_confirmed() and self.panel:
                self.panel.close();self.panel=None
                self.toolbar_session_ready=False;self.toolbar_geometry=None
            return [text(self.status())]
        self.guard()
        problem=self.admission_error(name)
        if problem:raise RuntimeError(problem)
        if name=='desktop_resume':
            if not self.closure_confirmed():raise RuntimeError('Previous portal closure is unconfirmed; stop sharing in GNOME before resuming')
            if args.get('human_ready') is not True:raise ValueError('Explicit human readiness is required; never resume on a timer')
            with self.state_lock:
                if not self.handoff or args.get('handoff_id')!=self.handoff['id']:
                    raise ValueError('Handoff ID does not match the current paused task')
                self.state='resuming'
            try:
                self.clear_observation()
                self.ensure_backend()
                self.prepare_toolbar()
                self.backend.start()
                self.toolbar_session_ready=True
                self.ensure_panel()
                content=self.capture_result(('resuming',))
                if self.panel_resume:
                    # This response has no assistant recipient. Never count the
                    # discarded image as an assistant observation.
                    with self.state_lock:
                        self.awaiting_assistant_observation=True
                        self.recovery.inspection_required=True
                        self.recovery.observation_id=None
                    return [text(self.status())]
                return content
            except BaseException:
                self.close_backend()
                with self.state_lock:
                    if self.state=='resuming':self.state='paused'
                raise
        if name=='desktop_start':
            summary=args.get('task_summary',self.task_summary)
            if not isinstance(summary,str) or not summary.strip() or len(summary)>1000:raise ValueError('task_summary must be nonsecret text of at most 1000 characters')
            if self.task_checkpoint is None:
                self.task_checkpoint={'intent':summary,'completed_summary':'','next_step':'Inspect current state and plan remaining work'}
            self.task_summary=summary
            if not self.closure_confirmed() and self.state!='active':raise RuntimeError('Previous portal closure is unconfirmed; stop sharing in GNOME before starting')
            with self.state_lock:
                self.state='starting';self.toolbar_session_ready=False
            try:
                self.ensure_backend()
                self.prepare_toolbar()
                self.backend.start()
                self.toolbar_session_ready=True
                self.ensure_panel()
                return self.capture_result(('starting',))
            except BaseException:
                self.close_backend()
                with self.state_lock:
                    if self.state=='starting':self.state='stopped'
                raise
        self.guard(('active',))
        self.ensure_backend()
        if name=='desktop_action':
            record=self.target_record;self.target_record=None
            checkpoint=self.validate_task_checkpoint(args['task_checkpoint']) if 'task_checkpoint' in args else None
            self.protect_toolbar(args['action'])
            self.recovery.begin(args.get('recovery_observation_id'))
            target=None
            # Reset before backend validation, so an old call cannot contaminate
            # the current partial-result report.
            self.backend.transaction_info={'completed_steps':0,'failed_step':None,'input_events_attempted':0,'input_characters_completed':0}
            try:
                if 'target_id' in args:
                    if not record or args['target_id']!=record['id'] or record['epoch']!=self.control_epoch or time.monotonic()-record['issued']>60:
                        raise RuntimeError('Target identity expired or invalid; inspect a fresh desktop_observe(inspect_target=true) result before input')
                    target=record['target'];target.live();self.guard(('active',))
                if checkpoint is not None:self.task_checkpoint={'intent':self.task_summary,**checkpoint}
                self.operation_active=True
                self.backend.target_guard=target
                try:self.backend.action(args['action'])
                finally:
                    self.operation_active=False
                    self.backend.target_guard=None
                content=self.capture_result(('active',))
            except BaseException:
                self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
                raise
            self.recovery.finish(getattr(self.backend,'transaction_info',{}))
            # Capture assembled status before finish; refresh only metadata.
            metadata=json.loads(content[0]['text'])
            metadata['recovery']=self.recovery.snapshot()
            metadata.update(self.task_status(True))
            content[0]=text(metadata)
            return content
        self.target_record=None
        target=None;target_error=None
        if name=='desktop_observe' and args.get('inspect_target') is True:
            try:target=self.inspect_keyboard_target()
            except Exception as error:
                self.guard(('active',))
                target_error=str(error)[:300]
        content=self.capture_result(('active',))
        if name=='desktop_observe':
            with self.state_lock:self.awaiting_assistant_observation=False
            metadata=json.loads(content[0]['text'])
            metadata['ready_to_observe']=False
            if args.get('inspect_target') is True:
                if target is not None:
                    try:
                        target.live(active=True,focused=True)
                        self.guard(('active',))
                        with self.state_lock:
                            self.guard(('active',))
                            record={'id':uuid.uuid4().hex,'epoch':self.control_epoch,'issued':time.monotonic(),'target':target}
                            self.target_record=record
                            metadata['target']={'available':True,'target_id':record['id'],'epoch':record['epoch'],'expires_seconds':60,**target.describe()}
                    except Exception as error:
                        self.guard(('active',));target_error=str(error)[:300]
                if target_error is not None:metadata['target']={'available':False,'reason':target_error,'no_fallback':True}
            metadata.update(self.task_status(True))
            content[0]=text(metadata)
        return content

    def error_result(self,error,name=None):
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
            except Exception as e:result=self.error_result(e,params.get('name'))
        elif method and method.startswith('notifications/'):return None
        else:return {'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':request.get('id'),'result':result}

    def fence_response(self,request,response):
        # Caller holds state_lock through write/flush. Already-published frames
        # cannot be retracted, but no later stale frame may cross this fence.
        content=(response or {}).get('result',{}).get('content',[])
        if any(c.get('type')=='image' for c in content):
            if request.get('_control_epoch',self.control_epoch)!=self.control_epoch or self.state!='active' or (self.cancel_token is not None and self.cancel_token.is_set()) or (self.backend is not None and self.backend.stopped.is_set()):
                name=request.get('params',{}).get('name')
                self.recovery.observation_id=None
                self.target_record=None
                if name=='desktop_action':
                    self.recovery.finish(getattr(self.backend,'transaction_info',{}),failed=True)
                return {'jsonrpc':'2.0','id':request.get('id'),'result':self.error_result('Screenshot invalidated by pause/stop; no image published',name)}
        return response

    def shutdown(self):
        self.close_target_provider()
        if self.panel:self.panel.close()
        if self.backend:self.backend.shutdown()
        with self.state_lock:
            self.state='stopped';self.handoff=None;self.control_epoch+=1
            self.task_checkpoint=None;self.resume_event=None;self.operation_active=False;self.target_record=None

class StdioTransport:
    """Read interruption signals independently; serialize all desktop operations."""
    def __init__(self,server):
        self.server=server
        self.pending=queue.Queue()
        self.tokens={}
        self.token_lock=threading.Lock()
        self.disconnected=threading.Event()
        self.resume_pending=False
        self.state_changed=threading.Condition()
        self.output_lock=threading.Lock()
        self.wait_lock=threading.Lock()
        self.wait_threads=[]
        self.emergency_requested=threading.Event()
        self.server.panel_control=self.panel_control

    def request_emergency_stop(self):
        # Signal handlers only set cancellation flags; cleanup runs off-handler.
        if self.server.backend:self.server.backend.stopped.set()
        self.emergency_requested.set()

    def watch_emergency(self):
        while not self.disconnected.is_set():
            if self.emergency_requested.wait(.05):
                self.emergency_requested.clear()
                self.panel_control('stop')

    def notify_state(self):
        with self.state_changed:self.state_changed.notify_all()

    def wait_status(self,request,token,output_stream):
        # Separate read-only waiter: never occupies the serial desktop worker,
        # which must remain able to process physical Continue and consent.
        try:
            args=request['params'].get('arguments',{})
            after=args.get('wait_after');timeout=args.get('timeout_seconds',30)
            if not isinstance(after,str) or len(after)>64:raise ValueError('wait_after must be a status_revision string')
            if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 1<=timeout<=50:raise ValueError('timeout_seconds must be between 1 and 50')
            deadline=time.monotonic()+timeout
            with self.state_changed:
                while True:
                    status=self.server.status()
                    changed=status['status_revision']!=after
                    cancelled=token.is_set() or self.disconnected.is_set()
                    remaining=deadline-time.monotonic()
                    if changed or cancelled or remaining<=0:break
                    self.state_changed.wait(min(remaining,.25))
            status['wait_outcome']='cancelled' if cancelled else ('changed' if changed else 'timeout')
            result={'content':[text(status)]}
        except Exception as e:result=self.server.error_result(e,'desktop_status')
        try:
            if not self.disconnected.is_set():
                with self.output_lock:
                    output_stream.write(json.dumps({'jsonrpc':'2.0','id':request.get('id'),'result':result})+'\n');output_stream.flush()
        except (BrokenPipeError,OSError):self.disconnected.set()
        finally:
            with self.token_lock:self.tokens.pop(request.get('id'),None)
            self.wait_lock.release()

    def panel_control(self,event,expected_epoch=None):
        if self.disconnected.is_set():return
        if event=='continue':
            with self.server.state_lock:
                if expected_epoch is not None and expected_epoch!=self.server.control_epoch:return
                if self.server.state!='paused' or not self.server.handoff:return
                with self.token_lock:
                    if self.resume_pending:return
                    self.resume_pending=True
                args={'handoff_id':self.server.handoff['id'],'human_ready':True}
                epoch=self.server.control_epoch
                self.server.resume_event={'id':uuid.uuid4().hex,'epoch':epoch,'source':'toolbar_continue'}
            request={'jsonrpc':'2.0','method':'tools/call',
                     'params':{'name':'desktop_resume','arguments':args},
                     '_control_epoch':epoch,'_panel_event':True,
                     '_panel_resume':True,'_resume_reserved':True}
            self.pending.put((request,threading.Event()))
            self.notify_state()
            return
        if event not in ('pause','stop'):return
        name="desktop_pause" if event=="pause" else "desktop_stop"
        args={"reason":"You pressed Pause in the desktop toolbar", "task_summary":self.server.task_summary, "handoff_kind":"manual_takeover"} if event=="pause" else {}
        with self.server.state_lock:
            # Ignore stale Pause before touching the current backend. Emergency
            # Stop remains effective even when its toolbar epoch is outdated.
            if event=='pause':
                if expected_epoch is not None and expected_epoch!=self.server.control_epoch:return
                if self.server.state!='active':return
            if self.server.backend:self.server.backend.stopped.set()
            epoch=self.server.begin_boundary(name,args)
        self.interrupt(all_requests=True)
        request={"jsonrpc":"2.0","method":"tools/call","params":{"name":name,"arguments":args},"_control_epoch":epoch,"_boundary_prepared":True,"_panel_event":True}
        self.pending.put((request,threading.Event()))
        self.notify_state()

    def interrupt(self,request_id=None,all_requests=False):
        with self.token_lock:
            if all_requests:
                for token in self.tokens.values():token.set()
            elif request_id in self.tokens:
                self.tokens[request_id].set()
        # Do not interrupt an unrelated active request when one queued ID is cancelled.
        self.notify_state()
        active=self.server.cancel_token
        if self.server.backend and (all_requests or (active is not None and active.is_set())):
            self.server.backend.stopped.set()

    def read(self,stream):
        try:
            for line in stream:
                try:
                    request=json.loads(line)
                    if not isinstance(request,dict):raise ValueError('Request must be an object')
                    if not isinstance(request.get('method'),str):raise ValueError('Method must be a string')
                    request_id=request.get('id')
                    if request_id is not None and (not isinstance(request_id,(str,int)) or isinstance(request_id,bool)):
                        raise ValueError('Request ID must be a string or integer')
                    params=request.get('params',{})
                    if not isinstance(params,dict):raise ValueError('Params must be an object')
                    if request.get('method')=='tools/call':
                        if not isinstance(params.get('name'),str):raise ValueError('Tool name must be a string')
                        if not isinstance(params.get('arguments',{}),dict):raise ValueError('Tool arguments must be an object')
                    if request.get('method')=='notifications/cancelled':
                        self.interrupt(params.get('requestId'))
                        continue
                    if request.get('method')=='tools/call':
                        name=params.get('name')
                        if name in ('desktop_pause','desktop_stop'):
                            try:
                                self.server.begin_boundary(name,params.get('arguments',{}))
                            except Exception as e:request['_admission_error']=str(e)
                            else:
                                self.interrupt(all_requests=True)
                                request['_boundary_prepared']=True
                        else:
                            request['_admission_error']=self.server.admission_error(name)
                            if name=='desktop_resume' and not request['_admission_error']:
                                with self.token_lock:
                                    if self.resume_pending:request['_admission_error']='A resume is already pending; wait for its result and a new human instruction before retrying'
                                    else:self.resume_pending=True;request['_resume_reserved']=True
                    with self.server.state_lock:request['_control_epoch']=self.server.control_epoch
                    token=threading.Event()
                    request_id=request.get('id')
                    if request_id is not None:
                        with self.token_lock:self.tokens[request_id]=token
                    self.pending.put((request,token))
                except Exception as e:
                    self.pending.put(({'_parse_error':str(e)},threading.Event()))
        finally:
            self.disconnected.set()
            self.interrupt(all_requests=True)
            self.pending.put(None)

    def run(self,input_stream,output_stream):
        reader=threading.Thread(target=self.read,args=(input_stream,),daemon=True)
        reader.start()
        emergency=threading.Thread(target=self.watch_emergency,daemon=True)
        emergency.start()
        try:
            while True:
                item=self.pending.get()
                if item is None:break
                request,token=item
                params=request.get('params') or {}
                if params.get('name')=='desktop_status' and 'wait_after' in params.get('arguments',{}):
                    if self.wait_lock.acquire(blocking=False):
                        waiter=threading.Thread(target=self.wait_status,args=(request,token,output_stream),daemon=True)
                        self.wait_threads=[t for t in self.wait_threads if t.is_alive()]
                        self.wait_threads.append(waiter);waiter.start()
                        continue
                    request['_admission_error']='Only one bounded status wait may be pending'
                try:
                    if '_parse_error' in request:
                        response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':request['_parse_error']}}
                    else:
                        self.server.cancel_token=token
                        self.server.request_epoch=request.get('_control_epoch')
                        self.server.boundary_prepared=request.get('_boundary_prepared',False)
                        self.server.panel_resume=request.get('_panel_resume',False)
                        # Discovery/status may complete after stdin EOF; new desktop
                        # access must never start after the client has disconnected.
                        name=(request.get('params') or {}).get('name')
                        if self.disconnected.is_set() and request.get('method')=='tools/call' and name not in ('desktop_stop','desktop_status'):
                            token.set()
                        response=self.server.handle(request)
                    if response is not None and not request.get("_panel_event"):
                        with self.server.state_lock:
                            response=self.server.fence_response(request,response)
                            with self.output_lock:
                                output_stream.write(json.dumps(response)+'\n');output_stream.flush()
                except (BrokenPipeError,OSError):
                    self.disconnected.set();self.interrupt(all_requests=True);break
                finally:
                    self.server.cancel_token=None
                    self.server.request_epoch=None
                    self.server.boundary_prepared=False
                    self.server.panel_resume=False
                    self.notify_state()
                    with self.token_lock:
                        self.tokens.pop(request.get('id'),None)
                        if request.get('_resume_reserved'):self.resume_pending=False
        finally:
            self.disconnected.set()
            self.interrupt(all_requests=True)
            self.server.shutdown()
            self.notify_state()
            for waiter in self.wait_threads:waiter.join(1)
            emergency.join(1)


def main():
    server=Server()
    transport=StdioTransport(server)
    def stop(signum,frame):
        transport.request_emergency_stop()
        if signum!=signal.SIGUSR1:raise SystemExit(0)
    for s in (signal.SIGINT,signal.SIGTERM,signal.SIGUSR1):signal.signal(s,stop)
    transport.run(sys.stdin,sys.stdout)

if __name__ == '__main__':main()
