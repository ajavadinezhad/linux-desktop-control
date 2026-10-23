"""Coalesced MCP resource updates. No frames, input, network, or model access."""
import threading
import time

URI = 'desktop://observation/changes'


class ChangeNotifier:
    """One writer, no pending event queue; slow clients get the newest hint."""
    def __init__(self, snapshot, send, interval=1.0):
        self.snapshot=snapshot;self.send=send;self.interval=interval
        self.stop_event=threading.Event();self.thread=None
        self.last_key=None;self.last_sent=0

    def poll(self, now=None):
        now=time.monotonic() if now is None else now
        value=self.snapshot()
        if value is None:
            self.last_key=None
            return False
        # Identity is internal; only the fixed resource URI goes on the wire.
        owner, state, stream, revision=value
        key=(owner,state,stream,revision)
        if key==self.last_key or now-self.last_sent<self.interval:return False
        if self.stop_event.is_set():return False
        if self.send(owner):
            self.last_key=key;self.last_sent=now
            return True
        return False

    def start(self):
        if self.thread is not None:raise RuntimeError('Notifier already started')
        def run():
            while not self.stop_event.wait(.1):
                try:self.poll()
                except Exception:
                    # Never serialize adapter exceptions or private event data.
                    self.stop_event.set()
        self.thread=threading.Thread(target=run,daemon=True,name='desktop-change-notifier')
        self.thread.start();return self

    def close(self):
        self.stop_event.set()
        if self.thread is not None and self.thread is not threading.current_thread():self.thread.join(.2)
