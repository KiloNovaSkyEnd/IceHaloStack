"""Bounded asynchronous final-frame output pipeline."""

from __future__ import annotations

import gc
import threading
import time
from collections import deque
from pathlib import Path
from queue import Queue, Empty, Full

from .image_io import save_pil_png_atomic, save_timelapse_sequence_frame_atomic
from .performance import _GIB, _MIB

class AsyncOutputPipeline:
    """RAM-aware bounded final-frame writer for v0.9.4.18l.

    Processing and image encoding/disk writing overlap. Queue capacity is small
    and controlled by the RAM strategy; no stack master, decoded RAW, or node
    intermediate is serialized to disk. Backpressure blocks the producer when
    the writer or disk cannot keep up.
    """
    def __init__(self, owner, policy, ui_queue, event_kind, total_tasks):
        self.owner=owner;self.policy=dict(policy or {});self.ui_queue=ui_queue;self.event_kind=str(event_kind)
        self.total_tasks=max(0,int(total_tasks));self.cancel_event=owner.cancel_event
        strategy=str(self.policy.get('strategy','Balanced'))
        self.capacity={'Memory Saver':1,'Balanced':2,'Maximum Performance':3}.get(strategy,2)
        self.limit_bytes=max(int(1*_GIB),int(self.policy.get('limit_bytes',4*_GIB)))
        share={'Memory Saver':0.05,'Balanced':0.10,'Maximum Performance':0.16}.get(strategy,0.10)
        self.byte_budget=max(96*_MIB,int(self.limit_bytes*share))
        self.q=Queue(maxsize=self.capacity);self.lock=threading.RLock();self.cond=threading.Condition(self.lock)
        self.queued_bytes=0;self.peak_bytes=0;self.submitted=0;self.completed=0;self.error=None;self.closed=False
        self.write_seconds=0.0;self.write_samples=deque(maxlen=12);self.writer_active=False;self.last_write_seconds=0.0
        self.started=time.monotonic();self.first_submit=None;self.last_path='';self._sentinel=object()
        self.thread=threading.Thread(target=self._worker,name='IHS-Async-Output',daemon=True);self.thread.start()
        owner._active_output_pipeline=self

    def _raise_if_failed(self):
        if self.error is not None:
            raise RuntimeError('异步输出失败 / Async output failed:\n'+str(self.error))

    def _estimate_bytes(self,obj):
        n=getattr(obj,'nbytes',None)
        if n is not None:
            try:return max(1,int(n))
            except Exception:pass
        try:
            w,h=obj.size;return max(1,int(w)*int(h)*3)
        except Exception:return 32*_MIB

    def _wait_memory_slot(self,nb):
        # A single large frame is always allowed; otherwise obey the queue byte budget.
        with self.cond:
            while not self.closed and self.error is None and not self.cancel_event.is_set():
                if self.queued_bytes==0 or self.queued_bytes+nb<=self.byte_budget:return
                self.cond.wait(timeout=0.08)
        if self.cancel_event.is_set():raise InterruptedError('cancelled')
        self._raise_if_failed()

    def submit_array(self,path,img,fmt='PNG 8-bit',png_compression='Balanced'):
        if self.closed:raise RuntimeError('AsyncOutputPipeline already closed')
        self._raise_if_failed();nb=self._estimate_bytes(img);perf=getattr(self.owner,'_active_performance_monitor',None);tw=time.monotonic();self._wait_memory_slot(nb)
        if perf is not None:perf.add_stage('output_backpressure',time.monotonic()-tw)
        task=('array',Path(path),img,str(fmt),str(png_compression),nb)
        while True:
            if self.cancel_event.is_set():raise InterruptedError('cancelled')
            self._raise_if_failed()
            try:self.q.put(task,timeout=0.08);break
            except Full:continue
        with self.cond:
            self.queued_bytes+=nb;self.peak_bytes=max(self.peak_bytes,self.queued_bytes);self.submitted+=1
            if self.first_submit is None:self.first_submit=time.monotonic()
        self._emit()

    def submit_pil_png(self,path,pil,compress_level=3):
        if self.closed:raise RuntimeError('AsyncOutputPipeline already closed')
        self._raise_if_failed();nb=self._estimate_bytes(pil);perf=getattr(self.owner,'_active_performance_monitor',None);tw=time.monotonic();self._wait_memory_slot(nb)
        if perf is not None:perf.add_stage('output_backpressure',time.monotonic()-tw)
        task=('pil_png',Path(path),pil,int(compress_level),'',nb)
        while True:
            if self.cancel_event.is_set():raise InterruptedError('cancelled')
            self._raise_if_failed()
            try:self.q.put(task,timeout=0.08);break
            except Full:continue
        with self.cond:
            self.queued_bytes+=nb;self.peak_bytes=max(self.peak_bytes,self.queued_bytes);self.submitted+=1
            if self.first_submit is None:self.first_submit=time.monotonic()
        self._emit()

    def _worker(self):
        try:
            while True:
                task=self.q.get()
                if task is self._sentinel:
                    self.q.task_done();break
                kind,path,obj,opt1,opt2,nb=task
                try:
                    if not self.cancel_event.is_set():
                        perf=getattr(self.owner,'_active_performance_monitor',None)
                        if perf is not None:perf.touch('output_write')
                        tw=time.monotonic()
                        with self.lock:self.writer_active=True
                        if kind=='array':save_timelapse_sequence_frame_atomic(path,obj,opt1,opt2)
                        else:save_pil_png_atomic(path,obj,opt1)
                        wdt=max(0.0,time.monotonic()-tw)
                        if perf is not None:perf.add_stage('output_write',wdt);perf.inc('frames_written',1)
                        with self.lock:
                            self.completed+=1;self.last_path=str(path);self.write_seconds+=wdt;self.last_write_seconds=wdt;self.write_samples.append(wdt);self.writer_active=False
                except Exception as e:
                    self.error=e
                finally:
                    with self.lock:self.writer_active=False
                    # Release queued image reference as soon as this file is done.
                    obj=None
                    with self.cond:
                        self.queued_bytes=max(0,self.queued_bytes-int(nb));self.cond.notify_all()
                    self.q.task_done();self._emit()
                if self.error is not None:break
        finally:
            # Drain unprocessed tasks after cancellation/error so join cannot deadlock.
            while True:
                try:t=self.q.get_nowait()
                except Empty:break
                try:
                    if t is not self._sentinel:
                        nb=t[-1]
                        with self.cond:self.queued_bytes=max(0,self.queued_bytes-int(nb));self.cond.notify_all()
                finally:self.q.task_done()
            self._emit()

    def _emit(self):
        try:self.ui_queue.put((self.event_kind,self.stats()))
        except Exception:pass

    def stats(self):
        with self.lock:
            elapsed=max(1e-6,time.monotonic()-(self.first_submit or self.started))
            # pipeline_fps is end-to-end completion throughput and includes time
            # when the writer is idle waiting for node processing. It must not be
            # presented as disk/write speed. writer_fps measures only active file
            # encoding+write time; recent_writer_fps uses the last 12 files.
            pipeline_fps=float(self.completed)/elapsed if self.completed else 0.0
            writer_fps=(float(self.completed)/self.write_seconds) if self.completed and self.write_seconds>1e-9 else 0.0
            recent_sum=sum(self.write_samples);recent_writer_fps=(len(self.write_samples)/recent_sum) if recent_sum>1e-9 else 0.0
            remain=max(0,self.total_tasks-self.completed);eta=(remain/pipeline_fps) if pipeline_fps>1e-9 else None
            idle=(not self.writer_active and self.q.qsize()==0)
            return {'queued':self.q.qsize(),'capacity':self.capacity,'queued_bytes':int(self.queued_bytes),'peak_bytes':int(self.peak_bytes),
                    'submitted':int(self.submitted),'completed':int(self.completed),'total':int(self.total_tasks),
                    'fps':pipeline_fps,'pipeline_fps':pipeline_fps,'writer_fps':writer_fps,'recent_writer_fps':recent_writer_fps,
                    'writer_active':bool(self.writer_active),'writer_idle':bool(idle),'write_seconds':float(self.write_seconds),
                    'last_write_seconds':float(self.last_write_seconds),'eta':eta,'byte_budget':int(self.byte_budget),
                    'last_path':self.last_path,'error':str(self.error) if self.error else ''}

    def finish(self):
        if self.closed:
            self._raise_if_failed();return
        self.closed=True
        # Enqueue sentinel only after all producer tasks. If writer failed, it has already drained.
        if self.error is None:
            while self.thread.is_alive():
                try:self.q.put(self._sentinel,timeout=0.08);break
                except Full:
                    if self.error is not None:break
        self.thread.join()
        self._raise_if_failed();self._detach()

    def cancel(self):
        self.closed=True
        # Worker finishes the currently encoded final file; queued future files are discarded.
        try:
            while True:
                t=self.q.get_nowait()
                try:
                    if t is not self._sentinel:
                        nb=t[-1]
                        with self.cond:self.queued_bytes=max(0,self.queued_bytes-int(nb));self.cond.notify_all()
                finally:self.q.task_done()
        except Empty:pass
        if self.thread.is_alive():
            try:self.q.put_nowait(self._sentinel)
            except Full:pass
            self.thread.join(timeout=30)
        self._detach()

    def _detach(self):
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:
            try:perf.record_output_stats(self.stats())
            except Exception:pass
        if getattr(self.owner,'_active_output_pipeline',None) is self:self.owner._active_output_pipeline=None
        gc.collect()


