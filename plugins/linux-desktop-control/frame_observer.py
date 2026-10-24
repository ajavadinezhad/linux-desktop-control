"""Portable, ephemeral latest-frame observer. No GUI, model or file I/O.

The adapter owns capture permission and supplies bounded, interruptible reads.
Frame revisions describe byte changes, not semantic understanding or input
authority. A slow reader never accumulates a queue of outdated frames.
"""
import hashlib
import threading
import time
import uuid


class ObserverStopped(RuntimeError): pass
class ObserverFailed(RuntimeError): pass
class ObserverTimeout(RuntimeError): pass


class LatestFrameObserver:
    MAX_FRAME_BYTES = 32 * 1024 * 1024

    def __init__(self, read_frame, permitted, clock=time.monotonic, on_fault=None):
        self.read_frame = read_frame
        self.permitted = permitted
        self.clock = clock
        self.on_fault = on_fault
        self.stream_id = uuid.uuid4().hex
        self.condition = threading.Condition()
        self.stop_event = threading.Event()
        self.thread = None
        self.latest = None
        self.digest = None
        self.frame_id = 0
        self.revision = 0
        self.overwritten_frames = 0
        self.failed = False

    def start(self):
        with self.condition:
            if self.thread is not None or self.stop_event.is_set():
                raise ObserverStopped('Observer cannot restart')
            self.thread = threading.Thread(target=self._run, daemon=True, name='desktop-frame-observer')
            self.thread.start()
        return self

    def _clear(self):
        self.latest = None
        self.digest = None
        self.condition.notify_all()

    def _run(self):
        try:
            while not self.stop_event.is_set():
                if not self.permitted():
                    with self.condition: self._clear()
                    self.stop_event.wait(.02)
                    continue
                frame = self.read_frame(.1)
                if frame is None: continue
                data, pts = frame
                if (type(data) is not bytes or not 24 <= len(data) <= self.MAX_FRAME_BYTES or
                    type(pts) is not int or pts < 0):
                    raise ObserverFailed('Invalid stream frame')
                digest = hashlib.blake2b(data, digest_size=16).digest()
                # Adapter permission checks may query a compositor. Never hold
                # the buffer lock across them: Stop must clear pixels promptly.
                permitted = self.permitted()
                with self.condition:
                    if self.stop_event.is_set(): break
                    if not permitted:
                        self._clear()
                        continue
                    if self.latest is not None and pts < self.latest['pts']:
                        raise ObserverFailed('Stream timestamp moved backwards')
                    if self.latest is not None: self.overwritten_frames += 1
                    self.frame_id += 1
                    if digest != self.digest: self.revision += 1
                    self.digest = digest
                    self.latest = {'data':data, 'pts':pts, 'received':self.clock(),
                                   'frame_id':self.frame_id, 'revision':self.revision}
                    self.condition.notify_all()
        except Exception:
            # Adapter errors can contain private desktop data. Publish no text.
            with self.condition:
                self.failed = True
                self._clear()
            if not self.stop_event.is_set() and self.on_fault is not None:
                self.on_fault()
        finally:
            with self.condition:
                self._clear()

    def snapshot(self):
        with self.condition:
            return {'stream_id':self.stream_id, 'running':bool(self.thread and self.thread.is_alive()) and not self.stop_event.is_set(),
                    'failed':self.failed, 'frame_id':self.frame_id, 'revision':self.revision,
                    'buffered_frames':int(self.latest is not None), 'overwritten_frames':self.overwritten_frames,
                    'frame_age_ms':None if self.latest is None else max(0,round((self.clock()-self.latest['received'])*1000)),
                    'change_detection':'encoded-frame-bytes', 'persistent_recording':False}

    def wait_frame(self, minimum_pts, timeout, check, max_age=.75):
        deadline = self.clock() + timeout
        while True:
            check()
            if not self.permitted():
                with self.condition: self._clear()
                raise ObserverStopped('Continuous observation is suspended')
            with self.condition:
                if self.failed: raise ObserverFailed('Continuous observer failed')
                if self.stop_event.is_set(): raise ObserverStopped('Continuous observer stopped')
                frame = self.latest
                if frame is not None and frame['pts'] >= minimum_pts and self.clock()-frame['received'] <= max_age:
                    result = dict(frame)
                else: result = None
                remaining = deadline-self.clock()
                if result is None:
                    if remaining <= 0: raise ObserverTimeout('No eligible stream frame')
                    self.condition.wait(min(.05,remaining))
                    continue
            check()
            if not self.permitted():
                with self.condition: self._clear()
                raise ObserverStopped('Continuous observation is suspended')
            return result

    def wait_change(self, stream_id, revision, timeout, check):
        if type(stream_id) is not str or stream_id != self.stream_id:
            raise ValueError('Stream changed; inspect a new observation')
        if type(revision) is not int or revision < 0:
            raise ValueError('Revision must be a nonnegative integer')
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0 <= timeout <= 30:
            raise ValueError('Change wait must be from 0 to 30 seconds')
        deadline = self.clock() + timeout
        while True:
            check()
            if not self.permitted():
                with self.condition: self._clear()
                raise ObserverStopped('Continuous observation is suspended')
            with self.condition:
                if self.failed: raise ObserverFailed('Continuous observer failed')
                if self.stop_event.is_set(): raise ObserverStopped('Continuous observer stopped')
                if revision > self.revision: raise ValueError('Revision is ahead of this stream')
                if self.latest is not None and self.revision > revision:
                    changed = True
                elif self.clock() >= deadline:
                    changed = False
                else:
                    self.condition.wait(min(.05,max(0,deadline-self.clock())))
                    continue
            check()
            if not self.permitted():
                with self.condition: self._clear()
                raise ObserverStopped('Continuous observation is suspended')
            return changed

    def close(self):
        self.stop_event.set()
        with self.condition: self._clear()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=.3)
        return self.thread is None or not self.thread.is_alive()
