"""RAM policy, resource measurement, and performance monitoring."""

import json
import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path

from .constants import VERSION


_GIB = 1024 ** 3
_MIB = 1024 ** 2


def _fmt_bytes(n):
    try:
        n = max(0.0, float(n))
    except Exception:
        return '—'
    if n >= _GIB:
        return f'{n/_GIB:.2f} GB'
    if n >= _MIB:
        return f'{n/_MIB:.0f} MB'
    if n >= 1024:
        return f'{n/1024:.0f} KB'
    return f'{n:.0f} B'



def _format_seconds_short(seconds):
    try:
        sec=max(0,int(round(float(seconds))))
    except Exception:
        return '—'
    h,rem=divmod(sec,3600);m,ss=divmod(rem,60)
    return f'{h:02d}:{m:02d}:{ss:02d}' if h else f'{m:02d}:{ss:02d}'


def _system_memory_status():
    """Return (total_bytes, available_bytes) without an extra dependency."""
    # Windows target: GlobalMemoryStatusEx reports ullAvailPhys directly.
    if os.name == 'nt':
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]
            st = MEMORYSTATUSEX(); st.dwLength = ctypes.sizeof(st)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullTotalPhys), int(st.ullAvailPhys)
        except Exception:
            pass
    # Linux / WSL fallback, useful for development/testing.
    try:
        vals = {}
        with open('/proc/meminfo', 'r', encoding='utf-8') as f:
            for line in f:
                if ':' not in line: continue
                k, v = line.split(':', 1)
                vals[k] = int(v.strip().split()[0]) * 1024
        total = int(vals.get('MemTotal', 0)); avail = int(vals.get('MemAvailable', vals.get('MemFree', 0)))
        if total > 0: return total, max(0, avail)
    except Exception:
        pass
    # Generic POSIX fallback.
    try:
        page = int(os.sysconf('SC_PAGE_SIZE')); total = int(os.sysconf('SC_PHYS_PAGES')) * page
        avail = int(os.sysconf('SC_AVPHYS_PAGES')) * page
        return total, max(0, avail)
    except Exception:
        return 0, 0


def _process_memory_rss():
    """Best-effort current process resident memory, bytes.

    On Windows use K32GetProcessMemoryInfo with explicit 64-bit-safe ctypes
    signatures.  Older builds relied on ctypes defaults, which can return 0 on
    some 64-bit Windows/Python combinations even while large RAM caches exist.
    """
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes
            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t),
                    ('PrivateUsage', ctypes.c_size_t),
                ]
            counters=PROCESS_MEMORY_COUNTERS_EX(); counters.cb=ctypes.sizeof(counters)
            kernel32=ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.GetCurrentProcess.argtypes=[]; kernel32.GetCurrentProcess.restype=wintypes.HANDLE
            handle=kernel32.GetCurrentProcess()
            fn=getattr(kernel32,'K32GetProcessMemoryInfo',None)
            if fn is not None:
                fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),wintypes.DWORD]
                fn.restype=wintypes.BOOL
                if fn(handle,ctypes.byref(counters),ctypes.sizeof(counters)):
                    return int(counters.WorkingSetSize)
            psapi=ctypes.WinDLL('psapi', use_last_error=True)
            fn=psapi.GetProcessMemoryInfo
            fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),wintypes.DWORD]
            fn.restype=wintypes.BOOL
            if fn(handle,ctypes.byref(counters),ctypes.sizeof(counters)):
                return int(counters.WorkingSetSize)
        except Exception:
            pass
    try:
        with open('/proc/self/statm', 'r', encoding='utf-8') as f:
            parts=f.read().split()
        if len(parts) >= 2:
            return int(parts[1]) * int(os.sysconf('SC_PAGE_SIZE'))
    except Exception:
        pass
    try:
        import resource
        val=float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return int(val if sys.platform == 'darwin' else val*1024)
    except Exception:
        return 0

def _auto_ram_limit_bytes():
    total, avail = _system_memory_status(); rss = _process_memory_rss()
    if total <= 0:
        return max(int(4*_GIB), int(rss + 2*_GIB))
    reserve = max(int(4*_GIB), int(total * 0.15))
    free_for_app = max(512*_MIB, avail - reserve)
    # Keep Auto conservative: use at most ~55% of physical RAM while allowing
    # current process RSS plus 70% of safely available headroom.
    target = int(rss + free_for_app * 0.70)
    target = min(target, int(total * 0.55), max(int(1*_GIB), total - reserve))
    return max(int(1*_GIB), target)


def _timelapse_memory_policy_snapshot(owner):
    total, avail = _system_memory_status(); rss = _process_memory_rss()
    reserve = max(int(4*_GIB), int(total * 0.15)) if total else int(4*_GIB)
    mode = str(owner.memory_limit_mode.get()) if hasattr(owner,'memory_limit_mode') else 'Auto'
    strategy = str(owner.memory_strategy.get()) if hasattr(owner,'memory_strategy') else 'Balanced'
    if mode == 'Manual':
        try: requested = float(owner.memory_limit_gb.get())
        except Exception: requested = 4.0
        requested = max(1.0, requested)
        limit = int(requested * _GIB)
        if total > 0: limit = min(limit, max(int(1*_GIB), total - reserve))
    else:
        limit = _auto_ram_limit_bytes()
    # Frame-cache share of the software budget. Scratch buffers, rolling sum,
    # node processing and output remain outside this cache allowance.
    shares = {'Memory Saver':0.22, 'Balanced':0.45, 'Maximum Performance':0.65}
    prefetch = {'Memory Saver':0, 'Balanced':2, 'Maximum Performance':4}
    return {
        'limit_bytes': max(int(1*_GIB), int(limit)),
        'system_total_bytes': int(total), 'system_available_bytes': int(avail),
        'system_reserve_bytes': int(reserve), 'rss_at_start_bytes': int(rss),
        'strategy': strategy, 'frame_cache_share': shares.get(strategy,0.45),
        'prefetch_count': prefetch.get(strategy,2), 'disk_cache': False,
    }


def _manual_ram_bounds_gb():
    total, _ = _system_memory_status()
    if total <= 0:
        return 1.0, 64.0
    reserve=max(int(4*_GIB),int(total*0.15))
    hi=max(1.0,(max(int(1*_GIB),total-reserve))/_GIB)
    return 1.0, max(1.0, round(hi,1))


class PerformanceMonitor:
    """Low-overhead in-memory profiler and non-destructive watchdog for timelapse jobs."""
    def __init__(self, owner, engine, policy, kind='Timelapse', save_report=False):
        self.owner=owner;self.engine=str(engine);self.kind=str(kind);self.policy=dict(policy or {});self.save_report=bool(save_report)
        self.lock=threading.RLock();self.started=time.monotonic();self.ended=None;self.status='Running';self.last_activity=self.started;self.last_activity_label='start';self.error=''
        self.counters=Counter();self.stage_seconds=Counter();self.node_seconds=Counter();self.node_counts=Counter();self.pressure_events=Counter()
        self.peak_rss_bytes=_process_memory_rss();_total,avail=_system_memory_status();self.min_system_available_bytes=int(avail or 0)
        self.peak_frame_cache_bytes=0;self.peak_dag_bytes=0;self.peak_output_queue_bytes=0;self.final_frame_cache_stats={};self.final_output_stats={};self.final_dag_stats={}
        owner._active_performance_monitor=self

    def touch(self,label='activity'):
        with self.lock:self.last_activity=time.monotonic();self.last_activity_label=str(label)

    def add_stage(self,name,seconds,count=0):
        sec=max(0.0,float(seconds or 0.0))
        with self.lock:
            self.stage_seconds[str(name)]+=sec
            if count:self.counters[str(name)+'_count']+=int(count)
            self.last_activity=time.monotonic();self.last_activity_label=str(name)

    def inc(self,name,n=1):
        with self.lock:self.counters[str(name)]+=int(n);self.last_activity=time.monotonic();self.last_activity_label=str(name)

    def record_node(self,node,seconds):
        sec=max(0.0,float(seconds or 0.0))
        with self.lock:
            self.node_seconds[str(node)]+=sec;self.node_counts[str(node)]+=1;self.stage_seconds['node_processing']+=sec;self.counters['node_computes']+=1;self.last_activity=time.monotonic();self.last_activity_label='node:'+str(node)

    def record_pressure(self,pressure):
        with self.lock:self.pressure_events[str(pressure)]+=1

    def record_cache_stats(self,st):
        if not st:return
        with self.lock:self.final_frame_cache_stats=dict(st);self.peak_frame_cache_bytes=max(self.peak_frame_cache_bytes,int(st.get('bytes',0)))

    def record_output_stats(self,st):
        if not st:return
        with self.lock:self.final_output_stats=dict(st);self.peak_output_queue_bytes=max(self.peak_output_queue_bytes,int(st.get('peak_bytes',st.get('queued_bytes',0))))

    def record_dag_stats(self,st):
        if not st:return
        with self.lock:self.final_dag_stats=dict(st);self.peak_dag_bytes=max(self.peak_dag_bytes,int(st.get('peak_bytes',0)))

    def sample_resources(self):
        rss=_process_memory_rss();_total,avail=_system_memory_status();cache=getattr(self.owner,'_active_frame_cache',None);out=getattr(self.owner,'_active_output_pipeline',None)
        with self.lock:
            self.peak_rss_bytes=max(self.peak_rss_bytes,int(rss or 0))
            if avail>0:self.min_system_available_bytes=int(avail) if self.min_system_available_bytes<=0 else min(self.min_system_available_bytes,int(avail))
        try:
            if cache is not None:self.record_cache_stats(cache.stats())
        except Exception:pass
        try:
            if out is not None:self.record_output_stats(out.stats())
        except Exception:pass

    def wrap_masters(self,iterable):
        it=iter(iterable)
        while True:
            self.touch('stack_wait');t=time.monotonic()
            try:master=next(it)
            except StopIteration:return
            self.add_stage('stack',time.monotonic()-t);self.inc('masters',1);yield master

    def _stability(self,now=None):
        now=time.monotonic() if now is None else now;age=max(0.0,now-self.last_activity)
        if self.status!='Running':return f'Stability：{self.status}'
        if age>=120:return f'Stability：Possible stall / 长操作超过 {int(age)}s · 当前阶段 {self.last_activity_label} · 仅提示，不会强制终止'
        if age>=30:return f'Stability：Long operation · {int(age)}s · 当前阶段 {self.last_activity_label}'
        return f'Stability：Running · 最近活动 {age:.1f}s 前 · {self.last_activity_label}'

    def snapshot(self):
        self.sample_resources();now=self.ended or time.monotonic()
        with self.lock:
            c=dict(self.counters);st=dict(self.stage_seconds);nodes=dict(self.node_seconds);node_counts=dict(self.node_counts);fc=dict(self.final_frame_cache_stats);out=dict(self.final_output_stats);dag=dict(self.final_dag_stats);hits=int(fc.get('hits',0));misses=int(fc.get('misses',0));den=hits+misses
            return {'version':VERSION,'kind':self.kind,'engine':self.engine,'status':self.status,'elapsed_seconds':max(0.0,now-self.started),'masters':int(c.get('masters',0)),'processed_tasks':int(c.get('processed_tasks',0)),'raw_decodes':int(c.get('raw_decodes',0)),'frames_written':int(out.get('completed',c.get('frames_written',0))),'raw_decode_seconds':float(st.get('raw_decode',0.0)),'stack_seconds':float(st.get('stack',0.0)),'node_seconds':float(st.get('node_processing',0.0)),'output_prepare_seconds':float(st.get('output_prepare',0.0)),'output_backpressure_seconds':float(st.get('output_backpressure',0.0)),'output_write_seconds':float(st.get('output_write',0.0)),'ffmpeg_seconds':float(st.get('ffmpeg',0.0)),'peak_rss_bytes':int(self.peak_rss_bytes),'min_system_available_bytes':int(self.min_system_available_bytes),'peak_frame_cache_bytes':int(self.peak_frame_cache_bytes),'peak_dag_bytes':int(self.peak_dag_bytes),'peak_output_queue_bytes':int(self.peak_output_queue_bytes),'frame_cache_hits':hits,'frame_cache_misses':misses,'frame_cache_evictions':int(fc.get('evictions',0)),'frame_cache_hit_rate':(hits/den if den else 0.0),'dag_hits':int(dag.get('hits',0)),'dag_computes':int(dag.get('computes',0)),'dag_budget_skips':int(dag.get('budget_skips',0)),'dag_hits_by_node':dict(dag.get('hits_by_node',{})),'dag_computes_by_node':dict(dag.get('computes_by_node',{})),'dag_reusable_by_node':dict(dag.get('reusable_by_node',{})),'node_seconds_by_type':nodes,'node_compute_count_by_type':node_counts,'pressure_events':dict(self.pressure_events),'last_activity':self.last_activity_label,'stability_text':self._stability(now),'ram_budget_bytes':int(self.policy.get('limit_bytes',0)),'memory_strategy':self.policy.get('strategy',''),'disk_cache':False,'error':self.error}

    def finalize(self,status,run_dir=None,error='',extra=None):
        self.sample_resources()
        with self.lock:self.status=str(status);self.error=str(error or '');self.ended=time.monotonic();self.last_activity=self.ended;self.last_activity_label='finalize'
        snap=self.snapshot()
        if extra:snap['extra']=dict(extra)
        self.owner._last_performance_snapshot=snap
        if self.save_report and run_dir:
            try:self._write_report(Path(run_dir),snap)
            except Exception:pass
        if getattr(self.owner,'_active_performance_monitor',None) is self:self.owner._active_performance_monitor=None
        self.owner._active_memory_policy=None
        return snap

    @staticmethod
    def _write_report(run_dir,snap):
        run_dir.mkdir(parents=True,exist_ok=True);jp=run_dir/f'performance_report_v{VERSION}.json';tp=run_dir/f'performance_report_v{VERSION}.txt';jp.write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding='utf-8');tp.write_text(_format_performance_snapshot(snap),encoding='utf-8')


def _format_performance_snapshot(s):
    if not s:return '尚无性能数据。'
    lines=[f'IceHaloStack {s.get("version",VERSION)} Performance Monitor',f'Status: {s.get("status","—")}',f'Engine: {s.get("engine","—")}',f'Elapsed: {_format_seconds_short(s.get("elapsed_seconds",0))}','',f'Masters: {s.get("masters",0)}',f'Processed tasks: {s.get("processed_tasks",0)}',f'RAW decodes: {s.get("raw_decodes",0)} · {s.get("raw_decode_seconds",0.0):.3f}s',f'Stack: {s.get("stack_seconds",0.0):.3f}s',f'Node processing: {s.get("node_seconds",0.0):.3f}s',f'Output preparation: {s.get("output_prepare_seconds",0.0):.3f}s',f'Output queue wait / backpressure: {s.get("output_backpressure_seconds",0.0):.3f}s',f'Output encode/write: {s.get("output_write_seconds",0.0):.3f}s',f'FFmpeg: {s.get("ffmpeg_seconds",0.0):.3f}s',f'Frames written: {s.get("frames_written",0)}','',f'Peak IceHaloStack RAM: {_fmt_bytes(s.get("peak_rss_bytes",0))}',f'RAM Budget: {_fmt_bytes(s.get("ram_budget_bytes",0))}',f'Min system available RAM: {_fmt_bytes(s.get("min_system_available_bytes",0))}',f'Peak Frame Cache: {_fmt_bytes(s.get("peak_frame_cache_bytes",0))}',f'Frame Cache: Hit {s.get("frame_cache_hits",0)} / Miss {s.get("frame_cache_misses",0)} / Evict {s.get("frame_cache_evictions",0)} · Hit rate {float(s.get("frame_cache_hit_rate",0))*100:.1f}%',f'Shared DAG: Hit {s.get("dag_hits",0)} / Compute {s.get("dag_computes",0)} / Budget Skip {s.get("dag_budget_skips",0)} · Peak {_fmt_bytes(s.get("peak_dag_bytes",0))}',f'Output Queue Peak: {_fmt_bytes(s.get("peak_output_queue_bytes",0))}','',str(s.get('stability_text','')),'Disk Cache: OFF']
    nodes=s.get('node_seconds_by_type') or {}
    if nodes:
        counts=s.get('node_compute_count_by_type') or {};dh=s.get('dag_hits_by_node') or {};dc=s.get('dag_computes_by_node') or {}
        lines+=['','Node timing / DAG audit:']
        for k,v in sorted(nodes.items(),key=lambda kv:-float(kv[1])):
            n=int(counts.get(k,0));avg=(float(v)/n if n else 0.0)
            lines.append(f'  {k}: {float(v):.3f}s · Compute {n} · Avg {avg:.3f}s · DAG Hit {int(dh.get(k,0))} / Compute {int(dc.get(k,0))}')
    reusable=s.get('dag_reusable_by_node') or {}
    if reusable:lines+=['','DAG reusable uses by node:']+[f'  {k}: {int(v)}' for k,v in sorted(reusable.items())]
    if s.get('error'):lines+=['','Error:',str(s.get('error'))]
    return '\n'.join(lines)

