#!/usr/bin/env python3
"""Synthetic observer overhead only. Never captures a desktop or calls a model."""
import importlib.util
import json
from pathlib import Path
import queue
import statistics
import time

path=Path(__file__).resolve().parents[1]/'plugins/linux-desktop-control/frame_observer.py'
spec=importlib.util.spec_from_file_location('benchmark_frame_observer',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def main():
    frames=queue.Queue()
    def read(timeout):
        try:return frames.get(timeout=timeout)
        except queue.Empty:return None
    observer=module.LatestFrameObserver(read,lambda:True).start()
    latencies=[]
    try:
        for revision in range(200):
            started=time.perf_counter()
            frames.put((revision.to_bytes(4,'big')*256,revision))
            if not observer.wait_change(observer.stream_id,revision,1,lambda:None):
                raise RuntimeError('Synthetic change missed')
            latencies.append((time.perf_counter()-started)*1000)
        snapshot=observer.snapshot()
        print(json.dumps({'measurement':'synthetic frame enqueue to change notification; no capture/model latency',
            'frames':len(latencies),'p50_ms':round(statistics.median(latencies),3),
            'p95_ms':round(sorted(latencies)[189],3),'buffered_frames':snapshot['buffered_frames'],
            'frames_overwritten':snapshot['overwritten_frames'],'live_speedup_established':False},indent=2))
    finally:observer.close()


if __name__=='__main__':main()
