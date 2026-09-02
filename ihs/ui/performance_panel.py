"""Timelapse RAM controls and performance diagnostics UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .appearance import _make_vertical_scroll_area
from ..performance import (
    _GIB, _auto_ram_limit_bytes, _fmt_bytes, _format_performance_snapshot,
    _format_seconds_short, _manual_ram_bounds_gb, _process_memory_rss,
    _system_memory_status, _timelapse_memory_policy_snapshot,
)


def _init_timelapse_memory_vars(owner):
    total, _ = _system_memory_status(); suggested = _auto_ram_limit_bytes()/_GIB
    lo,hi=_manual_ram_bounds_gb();suggested=max(lo,min(hi,suggested))
    owner.memory_limit_mode = tk.StringVar(value='Auto')
    owner.memory_limit_gb = tk.DoubleVar(value=max(lo, round(suggested, 1)))
    owner.memory_limit_value_text = tk.StringVar(value=f'{owner.memory_limit_gb.get():.1f} GB')
    owner.memory_limit_range_text = tk.StringVar(value=f'Manual 可调范围：{lo:.1f}–{hi:.1f} GB')
    owner.memory_strategy = tk.StringVar(value='Balanced')
    owner.memory_system_pct = tk.DoubleVar(value=0.0)
    owner.memory_app_pct = tk.DoubleVar(value=0.0)
    owner.memory_system_text = tk.StringVar(value='System RAM：读取中…')
    owner.memory_app_text = tk.StringVar(value='IceHaloStack RAM：读取中…')
    owner.memory_cache_text = tk.StringVar(value='Frame Cache：空闲')
    owner.memory_dag_text = tk.StringVar(value='Shared Node DAG：空闲')
    owner.memory_output_text = tk.StringVar(value='Async Output：空闲')
    owner.memory_budget_text = tk.StringVar(value='RAM Budget：Auto')
    owner.memory_pressure_text = tk.StringVar(value='Memory Pressure：Normal · Disk Cache OFF')
    owner.performance_monitor_text = tk.StringVar(value='Performance：空闲 · 开始批量任务后记录 Stack / Node / Output / FFmpeg / RAM')
    owner.stability_text = tk.StringVar(value='Stability：Idle')
    owner.performance_save_report = tk.BooleanVar(value=False)
    owner._memory_manual_entry = None
    owner._memory_manual_scale = None
    owner._memory_manual_min_gb = lo
    owner._memory_manual_max_gb = hi
    owner._memory_monitor_after = None
    owner._active_memory_policy = None
    owner._active_frame_cache = None
    owner._active_output_pipeline = None
    owner._active_performance_monitor = None
    owner._last_performance_snapshot = None
    owner._timelapse_details_window = None


def _manual_ram_value_changed(owner, value=None):
    try:
        v=float(value if value is not None else owner.memory_limit_gb.get())
        owner.memory_limit_value_text.set(f'{v:.1f} GB')
    except Exception:
        owner.memory_limit_value_text.set('— GB')


def _commit_manual_ram_value(owner, event=None):
    try:v=float(owner.memory_limit_gb.get())
    except Exception:v=float(getattr(owner,'_memory_manual_min_gb',1.0))
    lo=float(getattr(owner,'_memory_manual_min_gb',1.0));hi=float(getattr(owner,'_memory_manual_max_gb',64.0))
    v=round(max(lo,min(hi,v))*10.0)/10.0
    try:owner.memory_limit_gb.set(v)
    except Exception:pass
    _manual_ram_value_changed(owner,v)
    _update_memory_monitor(owner)
    return None


def _memory_limit_mode_changed(owner):
    manual=(owner.memory_limit_mode.get() == 'Manual')
    try:
        if owner._memory_manual_entry is not None: owner._memory_manual_entry.configure(state='normal' if manual else 'disabled')
        if owner._memory_manual_scale is not None: owner._memory_manual_scale.configure(state='normal' if manual else 'disabled')
    except Exception:
        pass
    if manual:_commit_manual_ram_value(owner)
    else:_update_memory_monitor(owner)


def _build_timelapse_memory_panel(owner, parent, wraplength=430, show_dag=False):
    """Compact memory controls for the main timelapse UI.

    v0.9.4.18f intentionally keeps verbose cache/DAG/performance diagnostics out
    of the main workflow.  Those values remain live and are available from the
    separate Details window.
    """
    box=ttk.LabelFrame(parent,text='性能与内存 / Performance & Memory',padding=7);box.pack(fill='x',pady=(8,0))
    ttk.Label(box,textvariable=owner.memory_system_text,wraplength=wraplength).pack(anchor='w')
    ttk.Progressbar(box,variable=owner.memory_system_pct,maximum=100).pack(fill='x',pady=(2,5))
    ttk.Label(box,textvariable=owner.memory_app_text,wraplength=wraplength).pack(anchor='w')
    ttk.Progressbar(box,variable=owner.memory_app_pct,maximum=100).pack(fill='x',pady=(2,5))

    ttl=ttk.Frame(box);ttl.pack(fill='x',pady=(2,0))
    ttk.Label(ttl,text='RAM 上限').pack(side='left')
    ttk.Label(ttl,textvariable=owner.memory_limit_value_text).pack(side='right')
    modes=ttk.Frame(box);modes.pack(fill='x',pady=(1,2))
    ttk.Radiobutton(modes,text='Auto',variable=owner.memory_limit_mode,value='Auto',command=lambda:_memory_limit_mode_changed(owner)).pack(side='left')
    ttk.Radiobutton(modes,text='Manual',variable=owner.memory_limit_mode,value='Manual',command=lambda:_memory_limit_mode_changed(owner)).pack(side='left',padx=(8,0))

    lo=float(getattr(owner,'_memory_manual_min_gb',1.0));hi=float(getattr(owner,'_memory_manual_max_gb',64.0))
    slider_row=ttk.Frame(box);slider_row.pack(fill='x',pady=(0,1))
    scale=ttk.Scale(slider_row,from_=lo,to=hi,orient='horizontal',variable=owner.memory_limit_gb,command=lambda v:_manual_ram_value_changed(owner,v),state='disabled')
    scale.pack(side='left',fill='x',expand=True,padx=(0,6))
    ent=ttk.Entry(slider_row,textvariable=owner.memory_limit_gb,width=7,justify='right',state='disabled');ent.pack(side='left');ttk.Label(slider_row,text='GB').pack(side='left',padx=(3,0))
    owner._memory_manual_entry=ent;owner._memory_manual_scale=scale
    bounds=ttk.Frame(box);bounds.pack(fill='x',pady=(0,3))
    ttk.Label(bounds,text=f'{lo:.1f} GB',foreground='#777').pack(side='left')
    ttk.Label(bounds,text=f'{hi:.1f} GB',foreground='#777').pack(side='right')
    scale.bind('<ButtonRelease-1>',lambda e:_commit_manual_ram_value(owner),add='+')
    scale.bind('<KeyRelease>',lambda e:_commit_manual_ram_value(owner),add='+')
    ent.bind('<Return>',lambda e:_commit_manual_ram_value(owner),add='+')
    ent.bind('<FocusOut>',lambda e:_commit_manual_ram_value(owner),add='+')

    st=ttk.Frame(box);st.pack(fill='x',pady=(2,0));ttk.Label(st,text='策略').pack(side='left')
    ttk.Combobox(st,textvariable=owner.memory_strategy,state='readonly',width=22,values=['Memory Saver','Balanced','Maximum Performance']).pack(side='right')

    actions=ttk.Frame(box);actions.pack(fill='x',pady=(6,0))
    ttk.Button(actions,text='详情…',command=lambda:_show_timelapse_details(owner,show_dag=show_dag)).pack(side='right')
    owner.memory_strategy.trace_add('write',lambda *a:_update_memory_monitor(owner))
    owner.memory_limit_gb.trace_add('write',lambda *a:_manual_ram_value_changed(owner))
    _manual_ram_value_changed(owner)
    _update_memory_monitor(owner)
    return box


def _show_timelapse_details(owner, show_dag=False):
    """Open verbose diagnostics in a separate live window instead of the main UI."""
    old=getattr(owner,'_timelapse_details_window',None)
    try:
        if old is not None and old.winfo_exists():
            old.deiconify();old.lift();old.focus_force();return
    except Exception:
        pass
    win=tk.Toplevel(owner);owner._timelapse_details_window=win
    win.title('IceHaloStack · 性能与内存详情')
    win.geometry('620x650');win.minsize(500,460)
    outer=ttk.Frame(win,padding=12);outer.pack(fill='both',expand=True)
    body,canvas,_shell=_make_vertical_scroll_area(outer,padding=0)

    mem=ttk.LabelFrame(body,text='内存 / Memory',padding=8);mem.pack(fill='x')
    for var in (owner.memory_system_text,owner.memory_app_text,owner.memory_budget_text,owner.memory_cache_text):
        ttk.Label(mem,textvariable=var,wraplength=560).pack(anchor='w',pady=2)
    ttk.Label(mem,textvariable=owner.memory_pressure_text,wraplength=560).pack(anchor='w',pady=2)
    ttk.Label(mem,textvariable=owner.memory_limit_range_text,wraplength=560).pack(anchor='w',pady=2)

    if show_dag:
        dag=ttk.LabelFrame(body,text='共享节点 / Shared Node DAG',padding=8);dag.pack(fill='x',pady=(8,0))
        ttk.Label(dag,textvariable=owner.memory_dag_text,wraplength=560).pack(anchor='w')

    out=ttk.LabelFrame(body,text='异步输出 / Async Output',padding=8);out.pack(fill='x',pady=(8,0))
    ttk.Label(out,textvariable=owner.memory_output_text,wraplength=560).pack(anchor='w')

    perf=ttk.LabelFrame(body,text='性能与稳定性 / Performance & Stability',padding=8);perf.pack(fill='x',pady=(8,0))
    ttk.Label(perf,textvariable=owner.performance_monitor_text,wraplength=560).pack(anchor='w',pady=2)
    ttk.Label(perf,textvariable=owner.stability_text,wraplength=560).pack(anchor='w',pady=2)
    ttk.Checkbutton(perf,text='保存性能报告 JSON/TXT',variable=owner.performance_save_report).pack(anchor='w',pady=(6,0))
    row=ttk.Frame(perf);row.pack(fill='x',pady=(7,0))
    ttk.Button(row,text='完整性能报告…',command=lambda:_show_performance_details(owner)).pack(side='right')

    storage=ttk.LabelFrame(body,text='缓存策略 / Cache Policy',padding=8);storage.pack(fill='x',pady=(8,0))
    ttk.Label(storage,text='中间 Master、RAW Decode Cache 与 Node Cache 仅驻留 RAM；Disk Cache = OFF。RAM 紧张时自动减少缓存或重新解码源文件。',wraplength=560).pack(anchor='w')
    ttk.Button(outer,text='关闭',command=win.destroy).pack(anchor='e',pady=(8,0))
    def closed():
        try:owner._timelapse_details_window=None
        except Exception:pass
        win.destroy()
    win.protocol('WM_DELETE_WINDOW',closed)

def _update_memory_monitor(owner):
    try:
        total, avail = _system_memory_status(); rss = _process_memory_rss(); used=max(0,total-avail)
        # Do not read Tk variables from the worker. This function only runs on UI thread.
        policy = getattr(owner,'_active_memory_policy',None) or _timelapse_memory_policy_snapshot(owner)
        limit = max(1, int(policy['limit_bytes']))
        owner.memory_system_pct.set((used/total*100.0) if total else 0.0)
        owner.memory_app_pct.set(min(100.0, rss/limit*100.0))
        owner.memory_system_text.set(f'System RAM：已用 {_fmt_bytes(used)} / {_fmt_bytes(total)} · 可用 {_fmt_bytes(avail)}')
        owner.memory_app_text.set(f'IceHaloStack：{_fmt_bytes(rss)} / {_fmt_bytes(limit)}')
        if owner.memory_limit_mode.get() == 'Auto':
            owner.memory_limit_value_text.set(f'Auto · {limit/_GIB:.1f} GB')
        else:
            try: owner.memory_limit_value_text.set(f'{float(owner.memory_limit_gb.get()):.1f} GB')
            except Exception: owner.memory_limit_value_text.set('— GB')
        owner.memory_budget_text.set(f'RAM Budget：{owner.memory_limit_mode.get()} · 有效上限 {_fmt_bytes(limit)} · 策略 {owner.memory_strategy.get()}')
        cache=getattr(owner,'_active_frame_cache',None)
        if cache is not None:
            st=cache.stats()
            owner.memory_cache_text.set(f'Frame Cache：{_fmt_bytes(st["bytes"])} · {st["frames"]} 帧 · Hit {st["hits"]} / Miss {st["misses"]} / Evict {st["evictions"]} · Prefetch {st["prefetch_pending"]}')
            owner.memory_pressure_text.set(f'Memory Pressure：{st["pressure"]} · Disk Cache OFF')
        else:
            owner.memory_cache_text.set('Frame Cache：空闲 · 批量任务开始后按 RAM Budget 动态启用')
            reserve=policy['system_reserve_bytes']; pressure='High' if avail and avail<reserve else 'Normal'
            owner.memory_pressure_text.set(f'Memory Pressure：{pressure} · Disk Cache OFF')
        outpipe=getattr(owner,'_active_output_pipeline',None)
        if outpipe is not None:
            ost=outpipe.stats()
            wf=float(ost.get('recent_writer_fps') or ost.get('writer_fps') or 0.0)
            state='空闲/等待处理' if ost.get('writer_idle') else '写入中'
            owner.memory_output_text.set(f'Async Output：{state} · Queue {ost["queued"]}/{ost["capacity"]} · Written {ost["completed"]}/{ost["total"]} · Writer {wf:.2f} fps')
        else:
            owner.memory_output_text.set('Async Output：空闲 · 批量任务时启用 RAM-aware bounded queue')
        perf=getattr(owner,'_active_performance_monitor',None)
        snap=None
        if perf is not None:
            perf.sample_resources();snap=perf.snapshot()
        elif getattr(owner,'_last_performance_snapshot',None):
            snap=dict(owner._last_performance_snapshot)
        if snap:
            hit=float(snap.get('frame_cache_hit_rate',0.0))*100.0
            owner.performance_monitor_text.set(f'Performance：{snap.get("status","Running")} · Elapsed {_format_seconds_short(snap.get("elapsed_seconds",0))} · Master {snap.get("masters",0)} · RAW Decode {snap.get("raw_decodes",0)} · Cache Hit {hit:.1f}% · Stack {snap.get("stack_seconds",0.0):.1f}s · Node {snap.get("node_seconds",0.0):.1f}s · Write {snap.get("output_write_seconds",0.0):.1f}s · Peak RAM {_fmt_bytes(snap.get("peak_rss_bytes",0))}')
            owner.stability_text.set(str(snap.get('stability_text','Stability：Running')))
        else:
            owner.performance_monitor_text.set('Performance：空闲 · 开始批量任务后记录 Stack / Node / Output / FFmpeg / RAM')
            owner.stability_text.set('Stability：Idle')
    except Exception:
        pass
    try:
        if owner.winfo_exists():
            if getattr(owner,'_memory_monitor_after',None) is not None:
                try: owner.after_cancel(owner._memory_monitor_after)
                except Exception: pass
            owner._memory_monitor_after=owner.after(750,lambda:_update_memory_monitor(owner))
    except Exception:
        pass


def _show_performance_details(owner):
    perf=getattr(owner,'_active_performance_monitor',None);snap=perf.snapshot() if perf is not None else getattr(owner,'_last_performance_snapshot',None);messagebox.showinfo('Performance Monitor',_format_performance_snapshot(snap),parent=owner)


# -----------------------------------------------------------------------------
# v0.9.5.2 — Keyframe-guided Exposure / White Balance Smoothing Workspace
# Global pre-stack correction. Source files are read-only. Analysis metrics,
# anchor points, correction tables, thumbnails and preview proxies stay in RAM.
# Every frame that enters the Stack Engine is corrected in linear RGB first.
# -----------------------------------------------------------------------------
