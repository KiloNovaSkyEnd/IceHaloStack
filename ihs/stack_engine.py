"""RAM-only frame caching and optimized timelapse stack engines."""

from __future__ import annotations

import gc
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from .dependencies import _deps
from .performance import (
    _GIB, _MIB, _system_memory_status, _process_memory_rss,
    _auto_ram_limit_bytes,
)

class RAMFrameCache:
    """Bounded RAM-only decoded-frame cache introduced in v0.9.4.18b and retained in v0.9.4.18g.

    It never serializes frames or masters. Under pressure it evicts LRU frames,
    disables prefetch, and falls back to re-decoding source files when needed.
    """
    def __init__(self, owner, ref_lum, policy):
        self.owner=owner; self.ref_lum=ref_lum; self.policy=dict(policy or {})
        self.limit_bytes=max(int(1*_GIB),int(self.policy.get('limit_bytes',4*_GIB)))
        self.cache_ceiling=max(0,int(self.limit_bytes*float(self.policy.get('frame_cache_share',0.45))))
        self.prefetch_count=max(0,int(self.policy.get('prefetch_count',2)))
        self.cache=OrderedDict();self.bytes_used=0;self.hits=0;self.misses=0;self.evictions=0
        self.lock=threading.RLock();self.futures={};self.executor=None;self.closed=False;self.pressure='Normal';self.estimated_frame_bytes=0
        if self.prefetch_count>0:
            self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='IHS-RAM-Prefetch')

    def _decode_direct(self,idx):
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:perf.touch('raw_decode')
        t=time.monotonic();img=self.owner._decode(idx,self.ref_lum).astype(_deps()[0].float32,copy=False)
        if perf is not None:perf.add_stage('raw_decode',time.monotonic()-t);perf.inc('raw_decodes',1)
        return img

    def _touch_pressure(self):
        total,avail=_system_memory_status();rss=_process_memory_rss();reserve=int(self.policy.get('system_reserve_bytes',4*_GIB))
        critical=(avail>0 and avail<max(512*_MIB,reserve//2)) or rss>self.limit_bytes*0.97
        high=(avail>0 and avail<reserve) or rss>self.limit_bytes*0.90
        elevated=rss>self.limit_bytes*0.80
        new='Critical' if critical else ('High' if high else ('Elevated' if elevated else 'Normal'))
        self.pressure=new
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:perf.record_pressure(new)
        if critical:self.trim_to(int(self.cache_ceiling*0.10))
        elif high:self.trim_to(int(self.cache_ceiling*0.40))
        if critical or high:
            # Native NumPy/rawpy buffers are normally released promptly; GC helps
            # Python containers relinquish references before the next decode.
            gc.collect()
        return new

    def trim_to(self,target):
        target=max(0,int(target))
        with self.lock:
            while self.cache and self.bytes_used>target:
                _,img=self.cache.popitem(last=False);self.bytes_used=max(0,self.bytes_used-int(getattr(img,'nbytes',0)));self.evictions+=1

    def discard(self,idx):
        """Release a frame known to be outside the future rolling window."""
        with self.lock:
            img=self.cache.pop(idx,None)
            if img is not None:self.bytes_used=max(0,self.bytes_used-int(getattr(img,'nbytes',0)))
            fut=self.futures.pop(idx,None)
        if fut is not None:
            try:fut.cancel()
            except Exception:pass

    def _store(self,idx,img):
        nb=int(getattr(img,'nbytes',0));self.estimated_frame_bytes=max(self.estimated_frame_bytes,nb)
        if nb<=0 or nb>self.cache_ceiling:return img
        self._touch_pressure()
        # Leave process headroom for rolling sum, node scratch and output buffers.
        rss=_process_memory_rss()
        if rss>self.limit_bytes*0.90 or self.pressure in ('High','Critical'):
            return img
        with self.lock:
            old=self.cache.pop(idx,None)
            if old is not None:self.bytes_used=max(0,self.bytes_used-int(getattr(old,'nbytes',0)))
            while self.cache and self.bytes_used+nb>self.cache_ceiling:
                _,victim=self.cache.popitem(last=False);self.bytes_used=max(0,self.bytes_used-int(getattr(victim,'nbytes',0)));self.evictions+=1
            if self.bytes_used+nb<=self.cache_ceiling:
                self.cache[idx]=img;self.bytes_used+=nb
        return img

    def get(self,idx):
        with self.lock:
            img=self.cache.pop(idx,None)
            if img is not None:
                self.cache[idx]=img;self.hits+=1;return img
            fut=self.futures.pop(idx,None)
        if fut is not None:
            try:
                img=fut.result();self.hits+=1;return self._store(idx,img)
            except Exception:
                pass
        self.misses+=1;img=self._decode_direct(idx);return self._store(idx,img)

    def _prefetch_decode(self,idx):
        if self.closed:return None
        return self._decode_direct(idx)

    def prefetch(self,indices):
        if self.closed or self.executor is None or self.prefetch_count<=0:return
        pressure=self._touch_pressure()
        if pressure in ('High','Critical'):return
        todo=[]
        with self.lock:
            for idx in indices:
                if idx in self.cache or idx in self.futures:continue
                todo.append(idx)
                if len(todo)>=self.prefetch_count:break
            # Bound outstanding decoded results as well as active work.
            room=max(0,self.prefetch_count-len(self.futures));todo=todo[:room]
            for idx in todo:self.futures[idx]=self.executor.submit(self._prefetch_decode,idx)

    def stats(self):
        with self.lock:
            return {'bytes':int(self.bytes_used),'frames':len(self.cache),'hits':int(self.hits),'misses':int(self.misses),'evictions':int(self.evictions),'prefetch_pending':len(self.futures),'pressure':self.pressure}

    def close(self):
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:
            try:perf.record_cache_stats(self.stats())
            except Exception:pass
        self.closed=True
        with self.lock:
            fs=list(self.futures.values());self.futures.clear();self.cache.clear();self.bytes_used=0
        for f in fs:
            try:f.cancel()
            except Exception:pass
        if self.executor is not None:
            try:self.executor.shutdown(wait=False,cancel_futures=True)
            except TypeError:self.executor.shutdown(wait=False)
            except Exception:pass
        self.executor=None;gc.collect()


def _next_window_incoming(groups, pos):
    if pos+1>=len(groups):return []
    cur=list(groups[pos]);nxt=list(groups[pos+1]);curset=set(cur)
    return [i for i in nxt if i not in curset]


def _iter_optimized_timelapse_masters(owner, groups, method, ref_lum=None, compatibility=False):
    """Yield timelapse masters using the v0.9.4.18g RAM-only performance core.

    The Stack Engine from 0.9.4.18a remains mathematically unchanged, while
    decoded source frames can now be reused by a bounded LRU ring/cache and a
    one-worker prefetch queue. The cache obeys the user's RAM Budget and never
    spills to disk. If RAM is tight, frames are simply re-decoded.
    """
    np, *_ = _deps()
    if not groups:
        return

    if compatibility:
        for g in groups:
            if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
            yield owner._stack_group(g, method, ref_lum)
        return

    policy=getattr(owner,'_active_memory_policy',None) or {
        'limit_bytes':_auto_ram_limit_bytes(),'system_reserve_bytes':max(int(4*_GIB),int((_system_memory_status()[0] or 0)*0.15)),
        'frame_cache_share':0.45,'prefetch_count':2,'strategy':'Balanced','disk_cache':False,
    }
    cache=RAMFrameCache(owner,ref_lum,policy)
    owner._active_frame_cache=cache
    mode=owner.mode.get()

    try:
        # Sliding / centered Mean: first sum once, then subtract outgoing and add
        # incoming frames. With enough RAM, outgoing frames are cache hits.
        if method == 'mean' and (mode.startswith('滑动') or mode.startswith('中心')):
            first=list(groups[0]);total=None
            for idx in first:
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                img=cache.get(idx)
                if total is None: total=img.copy()
                else: total+=img
            if total is None:return
            prev=first
            cache.prefetch(_next_window_incoming(groups,0))
            yield (total/float(len(first))).astype(np.float32,copy=False)
            for pos,g0 in enumerate(groups[1:],1):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                g=list(g0);prev_set=set(prev);curr_set=set(g)
                outgoing=[idx for idx in prev if idx not in curr_set]
                incoming=[idx for idx in g if idx not in prev_set]
                for idx in outgoing:
                    total-=cache.get(idx);cache.discard(idx)
                for idx in incoming: total+=cache.get(idx)
                cache.prefetch(_next_window_incoming(groups,pos))
                yield (total/float(len(g))).astype(np.float32,copy=False)
                prev=g
            return

        # Cumulative Mean / Maximum: one forward pass. Prefetch the next source
        # frames while the caller processes the current output master.
        if mode.startswith('累计'):
            target_ends=[len(g) for g in groups];target_pos=0;processed=0;master=None
            nfiles=len(owner.app.files)
            for idx in range(nfiles):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                img=cache.get(idx);processed+=1
                if master is None: master=img.copy()
                elif method=='maximum': np.maximum(master,img,out=master)
                else: master+=(img-master)/float(processed)
                cache.discard(idx)
                if target_pos<len(target_ends) and processed==target_ends[target_pos]:
                    cache.prefetch(range(idx+1,min(nfiles,idx+1+max(1,cache.prefetch_count))))
                    yield master.copy();target_pos+=1
                    if target_pos>=len(target_ends):break
            return

        # Leave-one-out Mean: build total once; excluded frames are cache hits
        # when budget permits and otherwise are safely re-decoded.
        if method=='mean' and mode.startswith('逐帧剔除'):
            n=len(owner.app.files)
            if n<2:return
            total=None
            for idx in range(n):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                img=cache.get(idx)
                if total is None:total=img.copy()
                else:total+=img
            all_indices=set(range(n))
            for pos,g in enumerate(groups):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                excluded=list(all_indices.difference(g))
                if len(excluded)!=1:
                    yield owner._stack_group(g,method,ref_lum);continue
                if pos+1<len(groups):
                    nex=list(all_indices.difference(groups[pos+1]));cache.prefetch(nex[:1])
                img=cache.get(excluded[0])
                yield ((total-img)/float(n-1)).astype(np.float32,copy=False)
            return

        # Maximum sliding/centered/LOO remains exact compatibility path in b.
        for g in groups:
            if owner.cancel_event.is_set():raise InterruptedError('cancelled')
            yield owner._stack_group(g,method,ref_lum)
    finally:
        try:cache.close()
        finally:
            owner._active_frame_cache=None


def _timelapse_stack_engine_name(owner, method):
    """Human-readable engine name for status/diagnostics."""
    mode = owner.mode.get()
    if method == 'mean' and (mode.startswith('滑动') or mode.startswith('中心')):
        return 'Rolling Mean'
    if mode.startswith('累计'):
        return 'Incremental Maximum' if method == 'maximum' else 'Incremental Mean'
    if method == 'mean' and mode.startswith('逐帧剔除'):
        return 'Total-Sum Leave-One-Out Mean'
    if method == 'maximum' and (mode.startswith('滑动') or mode.startswith('中心') or mode.startswith('逐帧剔除')):
        return 'Compatibility Maximum'
    return 'Compatibility'


def robust_luminance(img):
    np, *_ = _deps()
    lum = 0.2126*img[...,0] + 0.7152*img[...,1] + 0.0722*img[...,2]
    sample = lum[::8, ::8]
    q20, q80 = np.quantile(sample, [0.20, 0.80])
    core = sample[(sample >= q20) & (sample <= q80)]
    return float(np.median(core if core.size else sample))




