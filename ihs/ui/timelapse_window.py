"""Stack timelapse window UI.

This module owns the stack-timelapse workspace previously kept in the
compatibility entry point. It intentionally keeps the existing Tk behavior
while allowing the entry point to remain a thin launcher.
"""

from __future__ import annotations

import copy
import gc
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from collections import Counter, OrderedDict, deque

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ihs.constants import ALL_EXTS, APP_NAME, VERSION
from ihs.dependencies import (
    _deps, detect_system_cuda_toolkit, detect_nvidia_driver,
    detect_cuda_backend, choose_stack_backend, get_ffmpeg_executable,
)
from ihs.image_ops import (
    estimate_asinh_params, auto_stretch_for_display, apply_asinh_stretch,
    _blur, apply_usm, overlay_blend, softlight_blend, highpass_filter,
    apply_highpass, _emboss_components, _photoshop_emboss_filter,
    emboss_filter, apply_emboss, _smoothstep, apply_basic, _rgb_to_hsv_np,
    _hsv_to_rgb_np, apply_white_balance_post, apply_presence_advanced,
    apply_global_hsl, _hue_weight, apply_color_mixer_hsl, _grade_tint,
    apply_color_grading, apply_detail_base, apply_optics_base,
    apply_calibration_base, _base_activity, apply_base_editor, build_curve_lut,
    apply_curve_lut, protect_channel_chroma_noise, apply_channel_mixer,
    background_suppression,
)
from ihs.image_io import (
    srgb_to_linear, linear_to_srgb, read_linear_rgb, save_tiff,
    save_timelapse_sequence_frame, resize_pil_percent,
    resize_float_percent_array, save_timelapse_sequence_frame_scaled,
    _atomic_temp_path, _atomic_replace_with_retry,
    save_timelapse_sequence_frame_atomic, save_pil_png_atomic,
    prepare_video_frame, make_float_preview_proxy,
)
from ihs.performance import (
    _GIB, _MIB, _fmt_bytes, _format_seconds_short, _system_memory_status,
    _process_memory_rss, _auto_ram_limit_bytes,
    _timelapse_memory_policy_snapshot, _manual_ram_bounds_gb,
    PerformanceMonitor, _format_performance_snapshot,
)
from ihs.stack_engine import (
    RAMFrameCache, _next_window_incoming, _iter_optimized_timelapse_masters,
    _timelapse_stack_engine_name, robust_luminance,
)
from ihs.output_pipeline import (
    AsyncOutputPipeline, _build_ffmpeg_video_plan, _run_ffmpeg_command,
)
from ihs.node_workflow import (
    NODE_ORDER as _NODE_WORKFLOW_ORDER, default_edges as _node_default_edges,
    normalize_flow as _normalize_node_flow, node_enabled as _node_flow_enabled,
    flow_exec_order as _node_flow_exec_order,
    node_signature as _node_flow_signature,
    prepare_shared_node_dag as _prepare_node_shared_dag,
    shared_dag_cache_cap as _node_shared_dag_cache_cap,
    release_shared_flow_refs as _release_node_shared_flow_refs,
    apply_single_flow_node as _apply_node_flow_node,
    apply_flow_pipeline as _apply_node_flow_pipeline,
    execute_shared_flow as _execute_node_shared_flow,
    preset_payload as _node_preset_payload,
    flow_from_payload as _node_flow_from_payload,
    preview_cache_get as _node_preview_cache_get,
    preview_cache_put as _node_preview_cache_put,
    clear_preview_stage_cache as _clear_node_preview_stage_cache,
    apply_flow_pipeline_preview_cached as _apply_node_flow_pipeline_preview_cached,
    workflow_snapshot as _node_workflow_snapshot,
    workflow_states_equal as _node_workflow_states_equal,
    commit_workflow_history as _commit_node_workflow_history,
    workflow_history_undo as _node_workflow_history_undo,
    workflow_history_redo as _node_workflow_history_redo,
    restore_workflow_snapshot as _restore_node_workflow_snapshot,
    apply_timelapse_pipeline, scale_timelapse_cfg_for_proxy,
)
from ihs.services import ImageProcessingService
from ihs.exposure_wb import (
    _EWB_TONE_KEYS, _ewb_default_config, _ewb_resize_float,
    _ewb_analysis_crop, _ewb_measure_proxy, _ewb_median_filter_1d,
    _ewb_clean_outliers, _ewb_clean_chroma_joint,
    _ewb_smooth_chroma_joint, _ewb_gaussian_smooth_1d,
    _ewb_temp_tint_to_log_delta, _ewb_log_to_temp_tint,
    _ewb_anchor_residual_curve, _ewb_direct_anchor_curve,
    _ewb_smooth_direct_anchor_curve, _ewb_build_correction_table,
    _ewb_apply_additional_smoothing_round, _ewb_build_table_from_snapshot,
    _ewb_apply_to_frame,
)
from ihs.ui import appearance as _appearance
from ihs.ui.appearance import (
    FONT_CHOICES, LANGUAGE_CHOICES, THEME_CHOICES, THEME_PALETTES,
    _apply_ui_font_preference, _apply_ui_language, _apply_ui_theme,
    _configure_tk_high_dpi, _enforce_regular_typography,
    _install_combobox_selection_behavior, _make_vertical_scroll_area,
    _mousewheel_steps, _tr, _translate_flow_list_item, _translate_text,
    _ui_font, AngleDial,
)
from ihs.ui.performance_panel import (
    _build_timelapse_memory_panel, _commit_manual_ram_value,
    _init_timelapse_memory_vars, _manual_ram_value_changed,
    _memory_limit_mode_changed, _show_performance_details,
    _show_timelapse_details, _update_memory_monitor,
)
from ihs.ui.exposure_wb_window import (
    _build_ewb_panel, _ewb_analyze_async, _ewb_analyze_files,
    _ewb_anchor_signature, _ewb_apply_preview_adjustment,
    _ewb_config_snapshot, _ewb_correction_signature_for, _ewb_enabled,
    _ewb_files_signature, _ewb_get_preview_proxy, _ewb_invalidate,
    _ewb_make_thumbnail, _ewb_measurement_signature_for, _ewb_open_workspace,
    _ewb_rebuild_table, _ewb_require_analysis, _ewb_settings_dialog,
    _ewb_show_curves, _ewb_signature, _ewb_table_summary,
    _ewb_workspace_close, _init_ewb_vars, read_analysis_proxy,
)


class TimelapseWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app=app
        self.title(f'{APP_NAME} · 堆栈延时 v{VERSION}')
        self.geometry('1180x820')
        self.minsize(980,700)
        self.queue=Queue(); self.worker=None; self.cancel_event=threading.Event(); self.preview_photo=None
        self.curve_snapshot=copy.deepcopy(getattr(app,'curve_points',{}))
        self._init_vars(); self._build_ui(); _enforce_regular_typography(self); self.after_idle(lambda: _enforce_regular_typography(self)); self._initialize_profile_presets(); self._update_summary(); self.after(80,self._poll)

    def _init_vars(self):
        a=self.app
        self.mode=tk.StringVar(value='滑动窗口（推荐：观察变化）')
        self.stack_method=tk.StringVar(value='平均值 Mean')
        self.stack_range_start=tk.IntVar(value=1)
        self.stack_range_end=tk.IntVar(value=1)
        self.stack_range_info=tk.StringVar(value='当前堆栈区间：1 - 1（0 帧）')
        self.window_size=tk.IntVar(value=min(15,max(2,len(a.files))))
        self.step=tk.IntVar(value=1)
        self.normalize=tk.BooleanVar(value=bool(a.normalize_var.get()))
        self.summary=tk.StringVar(value='')
        self.mode_description=tk.StringVar(value='')
        self.preview_index=tk.IntVar(value=1)
        self.reference_master=None
        self.reference_group=None
        self.reference_index=None
        self.pipeline_locked=False
        self.lock_status=tk.StringVar(value='处理方案尚未锁定')
        _init_timelapse_memory_vars(self)
        _init_ewb_vars(self)
        self.normalize.set(False)  # v0.9.5 timelapse uses Exposure/WB Smoothing instead of legacy one-frame normalization.

        self.p_stretch=tk.BooleanVar(value=True)
        self.p_stretch_strength=tk.DoubleVar(value=float(getattr(a,'stretch_strength',tk.DoubleVar(value=8)).get()))
        self.p_stretch_black=tk.DoubleVar(value=float(getattr(a,'stretch_black',tk.DoubleVar(value=0)).get()))

        self.p_basic=tk.BooleanVar(value=True)
        bv=getattr(a,'basic_vars',{})
        def bget(key,default=0.0):
            try:return float(bv[key].get())
            except Exception:return float(default)
        self.p_exposure=tk.DoubleVar(value=bget('exposure')); self.p_contrast=tk.DoubleVar(value=bget('contrast'))
        self.p_highlights=tk.DoubleVar(value=bget('highlights')); self.p_shadows=tk.DoubleVar(value=bget('shadows'))
        self.p_whites=tk.DoubleVar(value=bget('whites')); self.p_blacks=tk.DoubleVar(value=bget('blacks'))
        self.p_clarity=tk.DoubleVar(value=bget('clarity')); self.p_dehaze=tk.DoubleVar(value=bget('dehaze'))
        self.p_vibrance=tk.DoubleVar(value=bget('vibrance')); self.p_saturation=tk.DoubleVar(value=bget('saturation'))

        self.p_bg=tk.BooleanVar(value=False); self.p_bg_radius=tk.DoubleVar(value=80.0); self.p_bg_strength=tk.DoubleVar(value=100.0)
        self.p_curves=tk.BooleanVar(value=False)
        self.p_usm=tk.BooleanVar(value=False); self.p_usm_amount=tk.DoubleVar(value=float(getattr(a,'usm_amount',tk.DoubleVar(value=100)).get() or 100)); self.p_usm_radius=tk.DoubleVar(value=float(getattr(a,'usm_radius',tk.DoubleVar(value=2)).get())); self.p_usm_threshold=tk.DoubleVar(value=float(getattr(a,'usm_threshold',tk.DoubleVar(value=0)).get())); self.p_usm_passes=tk.IntVar(value=1)
        self.p_hp=tk.BooleanVar(value=False); self.p_hp_radius=tk.DoubleVar(value=float(getattr(a,'hp_radius',tk.DoubleVar(value=10)).get())); self.p_hp_amount=tk.DoubleVar(value=float(getattr(a,'hp_amount',tk.DoubleVar(value=100)).get())); self.p_hp_mode=tk.StringVar(value=str(getattr(a,'hp_mode',tk.StringVar(value='Overlay')).get()))
        self.p_emboss=tk.BooleanVar(value=False); self.p_emboss_angle=tk.DoubleVar(value=float(getattr(a,'emboss_angle',tk.DoubleVar(value=-128)).get())); self.p_emboss_height=tk.DoubleVar(value=float(getattr(a,'emboss_height',tk.DoubleVar(value=1)).get())); self.p_emboss_amount=tk.DoubleVar(value=float(getattr(a,'emboss_strength',tk.DoubleVar(value=100)).get())); self.p_emboss_style=tk.StringVar(value=str(getattr(a,'emboss_style',tk.StringVar(value='Photoshop Emboss')).get())); self.p_emboss_blend=tk.StringVar(value=str(getattr(a,'emboss_blend',tk.StringVar(value='Normal')).get())); self.p_emboss_opacity=tk.DoubleVar(value=float(getattr(a,'emboss_opacity',tk.DoubleVar(value=100)).get()))
        self.p_channel=tk.BooleanVar(value=False); self.p_channel_output=tk.StringVar(value=str(getattr(a,'channel_output',tk.StringVar(value='灰色')).get())); self.p_channel_mono=tk.BooleanVar(value=bool(getattr(a,'channel_mono',tk.BooleanVar(value=True)).get()))
        self.p_channel_red=tk.DoubleVar(value=float(getattr(a,'channel_red',tk.DoubleVar(value=40)).get())); self.p_channel_green=tk.DoubleVar(value=float(getattr(a,'channel_green',tk.DoubleVar(value=40)).get())); self.p_channel_blue=tk.DoubleVar(value=float(getattr(a,'channel_blue',tk.DoubleVar(value=20)).get())); self.p_channel_constant=tk.DoubleVar(value=float(getattr(a,'channel_constant',tk.DoubleVar(value=0)).get()))
        self.p_channel_noise=tk.BooleanVar(value=bool(getattr(a,'channel_noise_protect',tk.BooleanVar(value=True)).get())); self.p_channel_noise_strength=tk.DoubleVar(value=float(getattr(a,'channel_noise_strength',tk.DoubleVar(value=30)).get())); self.p_channel_noise_radius=tk.DoubleVar(value=float(getattr(a,'channel_noise_radius',tk.DoubleVar(value=0.8)).get()))

        self.selected_profile_idx=tk.IntVar(value=0)
        self.export_profiles=[]
        profile_defaults=[
            ('01_平均值堆栈', '仅拉伸+调色', True),
            ('02_BG+Curves', '背景+曲线', True),
            ('03_USM+BG+Curves', 'USM+背景+曲线', True),
            ('04_ChannelMixer', '通道混合器', True),
            ('05_全部开启', '全部开启', True),
        ]
        for name,preset,enabled in profile_defaults:
            self.export_profiles.append({
                'enabled': tk.BooleanVar(value=enabled),
                'name': tk.StringVar(value=name),
                'preset': tk.StringVar(value=preset),
                'name_template': tk.StringVar(value='{index:02d}_{name}'),
                'save_sequence': tk.BooleanVar(value=True),
                'save_video': tk.BooleanVar(value=True),
                'delete_sequence_after_video_only': tk.BooleanVar(value=True),
                'video_format': tk.StringVar(value='MP4 H.264'),
                'scale_percent': tk.DoubleVar(value=100.0),
                'stretch': tk.BooleanVar(value=True),
                'basic': tk.BooleanVar(value=True),
                'background': tk.BooleanVar(value=False),
                'curves': tk.BooleanVar(value=False),
                'usm': tk.BooleanVar(value=False),
                'highpass': tk.BooleanVar(value=False),
                'emboss': tk.BooleanVar(value=False),
                'channel': tk.BooleanVar(value=False),
            })

        self.output_folder=tk.StringVar(value=str(Path.cwd()/'IceHaloStack_Timelapse_Output'))
        self.save_sequence=tk.BooleanVar(value=True)
        self.sequence_format=tk.StringVar(value='PNG 8-bit')
        self.video_format=tk.StringVar(value='MP4 H.264')
        self.fps=tk.DoubleVar(value=24.0)
        self.resolution=tk.StringVar(value='原始分辨率')
        self.custom_w=tk.IntVar(value=1920); self.custom_h=tk.IntVar(value=1080)
        self.fit_mode=tk.StringVar(value='Fill 裁切')
        self.progress=tk.DoubleVar(value=0.0); self.status=tk.StringVar(value='第 1 步：先生成一张参考堆栈')
        self.processing_progress=tk.DoubleVar(value=0.0);self.writing_progress=tk.DoubleVar(value=0.0)
        self.output_pipeline_text=tk.StringVar(value='写入：空闲')
        self.live_preview=tk.BooleanVar(value=True)
        self.live_preview_delay_ms=45
        self._live_preview_after_id=None
        self._live_preview_token=0
        self._live_preview_running=False
        self._live_preview_pending=False
        self._live_preview_requested_quality='fast'
        self.reference_proxy_drag=None
        self.reference_proxy_drag_scale=1.0
        self.reference_proxy_fast=None
        self.reference_proxy_fast_scale=1.0
        self.reference_proxy_hq=None
        self.reference_proxy_hq_scale=1.0
        self.tl_curve_channel=tk.StringVar(value='RGB')
        self.tl_curve_input=tk.DoubleVar(value=0.0)
        self.tl_curve_output=tk.DoubleVar(value=0.0)
        self.tl_curve_selected_idx=None
        self.tl_curve_axis_drag=None
        self._tl_curve_sync=False
        self._tl_curve_hist_source=None
        self._tl_curve_hist_cache={}
        self._tl_curve_hist_dirty=True

    def _entry_row(self,parent,label,var,width=10):
        r=ttk.Frame(parent); r.pack(fill='x',pady=2)
        ttk.Label(r,text=label).pack(side='left')
        e=ttk.Entry(r,textvariable=var,width=width,justify='right'); e.pack(side='right')
        def sel(ev=None): e.selection_range(0,'end'); e.icursor('end'); return 'break'
        e.bind('<Control-a>',sel); e.bind('<Control-A>',sel); e.bind('<Double-Button-1>',sel)
        return e

    def _slider_row(self,parent,label,var,frm,to,res=1.0,reset_value=None):
        """Numeric entry + draggable ttk.Scale for timelapse processing parameters."""
        box=ttk.Frame(parent); box.pack(fill='x',pady=2)
        top=ttk.Frame(box); top.pack(fill='x')
        ttk.Label(top,text=label).pack(side='left')
        e=ttk.Entry(top,width=10,justify='right'); e.pack(side='right')
        initial=float(var.get())
        if reset_value is None:
            reset_value = 0.0 if float(frm) <= 0.0 <= float(to) else initial

        def fmt(v):
            try:
                fv=float(v)
                if float(res) >= 1 and abs(float(res)-round(float(res))) < 1e-9:
                    return str(int(round(fv)))
                digits=4 if abs(float(res)) < 0.01 else (2 if abs(float(res)) < 1 else 1)
                return f'{fv:.{digits}f}'.rstrip('0').rstrip('.')
            except Exception:
                return str(v)

        editing={'active':False}
        def sync(*_):
            if editing['active'] and self.focus_get() == e:
                return
            e.delete(0,'end'); e.insert(0,fmt(var.get()))

        def commit(ev=None):
            try:
                v=float(e.get().strip())
                v=max(float(frm),min(float(to),v))
                var.set(v)
            except Exception:
                sync()
            editing['active']=False
            self._schedule_live_preview(force=True)
            return 'break' if ev is not None and getattr(ev,'keysym','')=='Return' else None

        def select_all(ev=None):
            editing['active']=True
            e.focus_set(); e.selection_range(0,'end'); e.icursor('end'); return 'break'

        def on_scale_move(value=None):
            sync()
            self._schedule_live_preview(dragging=True)

        scale=ttk.Scale(box,from_=frm,to=to,variable=var,command=on_scale_move)
        scale.pack(fill='x',pady=(1,0))

        def slider_press(ev=None):
            # Commit any typed value first, then move focus to Scale so FocusOut cannot
            # restore an old Entry value over the dragged slider position.
            if self.focus_get() == e:
                commit()
            try: scale.focus_set()
            except Exception: pass
            self._schedule_live_preview(dragging=True)

        def slider_release(ev=None):
            self._schedule_live_preview(force=True)

        def slider_reset(ev=None):
            var.set(float(reset_value))
            try: scale.focus_set()
            except Exception: pass
            self._schedule_live_preview(force=True)
            return 'break'

        var.trace_add('write',sync); sync()
        e.bind('<FocusIn>',lambda ev: editing.__setitem__('active',True))
        e.bind('<Return>',commit); e.bind('<FocusOut>',commit)
        e.bind('<Control-a>',select_all); e.bind('<Control-A>',select_all); e.bind('<Double-Button-1>',select_all)
        scale.bind('<ButtonPress-1>',slider_press,add='+')
        scale.bind('<ButtonRelease-1>',slider_release,add='+')
        scale.bind('<Double-Button-1>',slider_reset)
        return scale

    def _initialize_profile_presets(self):
        for i,p in enumerate(self.export_profiles):
            self._apply_profile_preset(i)
        self._rebuild_export_profiles_ui()

    def _new_export_profile(self, name=None, preset='自定义', enabled=True):
        idx=len(self.export_profiles)+1
        return {
            'enabled': tk.BooleanVar(value=enabled),
            'name': tk.StringVar(value=name or f'{idx:02d}_新输出组'),
            'preset': tk.StringVar(value=preset),
            'name_template': tk.StringVar(value='{index:02d}_{name}'),
            'save_sequence': tk.BooleanVar(value=True),
            'save_video': tk.BooleanVar(value=True),
            'video_format': tk.StringVar(value='MP4 H.264'),
            'scale_percent': tk.DoubleVar(value=100.0),
            'stretch': tk.BooleanVar(value=True),
            'basic': tk.BooleanVar(value=True),
            'background': tk.BooleanVar(value=False),
            'curves': tk.BooleanVar(value=False),
            'usm': tk.BooleanVar(value=False),
            'highpass': tk.BooleanVar(value=False),
            'emboss': tk.BooleanVar(value=False),
            'channel': tk.BooleanVar(value=False),
        }

    def _current_profile(self):
        if not self.export_profiles:
            return None
        idx=max(0,min(len(self.export_profiles)-1,int(self.selected_profile_idx.get() or 0)))
        self.selected_profile_idx.set(idx)
        return self.export_profiles[idx]

    def _apply_profile_preset(self, idx):
        p=self.export_profiles[idx]
        preset=p['preset'].get()
        mapping={
            '仅拉伸+调色': dict(stretch=True,basic=True,background=False,curves=False,usm=False,highpass=False,emboss=False,channel=False),
            '背景+曲线': dict(stretch=True,basic=True,background=True,curves=True,usm=False,highpass=False,emboss=False,channel=False),
            'USM+背景+曲线': dict(stretch=True,basic=True,background=True,curves=True,usm=True,highpass=False,emboss=False,channel=False),
            '通道混合器': dict(stretch=True,basic=True,background=False,curves=False,usm=False,highpass=False,emboss=False,channel=True),
            'USM+通道混合器': dict(stretch=True,basic=True,background=False,curves=False,usm=True,highpass=False,emboss=False,channel=True),
            '全部开启': dict(stretch=True,basic=True,background=True,curves=True,usm=True,highpass=True,emboss=True,channel=True),
            '自定义': None,
        }
        m=mapping.get(preset)
        if m:
            for k,v in m.items():
                p[k].set(bool(v))
        self._update_profile_summary(); self._draw_selected_profile_graph(); self._schedule_live_preview(force=True)

    def _build_export_profiles_ui(self, parent):
        self.export_box=ttk.LabelFrame(parent,text='多路序列导出（无限输出组）',padding=6); self.export_box.pack(fill='x',pady=(8,0))
        ttk.Label(self.export_box,text='这一版开始支持无限多个输出组。每个输出组都可以有自己的流程、预览、是否保存序列、是否保存视频、视频格式、命名模板，以及按原始比例缩小输出尺寸。下方节点画布会显示当前选中输出组的工作流。',foreground='#555555',wraplength=430).pack(anchor='w',pady=(0,6))
        tools=ttk.Frame(self.export_box); tools.pack(fill='x',pady=(0,4))
        ttk.Button(tools,text='＋ 新增输出组',command=self._add_export_profile).pack(side='left')
        ttk.Button(tools,text='－ 删除当前输出组',command=self._remove_selected_profile).pack(side='left',padx=(6,0))
        ttk.Button(tools,text='复制当前输出组',command=self._duplicate_selected_profile).pack(side='left',padx=(6,0))
        self.profile_rows=ttk.Frame(self.export_box); self.profile_rows.pack(fill='x')
        self.profile_summary=tk.StringVar(value='')
        ttk.Label(self.export_box,textvariable=self.profile_summary,foreground='#666666',wraplength=430).pack(anchor='w',pady=(6,4))
        self.profile_canvas_title=tk.StringVar(value='节点画布：未选择输出组')
        ttk.Label(self.export_box,textvariable=self.profile_canvas_title,font=_ui_font(9)).pack(anchor='w',pady=(2,2))
        self.profile_node_canvas=tk.Canvas(self.export_box,height=145,bg='#161616',highlightthickness=1,highlightbackground='#3a3a3a')
        self.profile_node_canvas.pack(fill='x',pady=(0,4))
        self.profile_node_canvas.bind('<Button-1>', self._on_profile_canvas_click)
        self._rebuild_export_profiles_ui()

    def _rebuild_export_profiles_ui(self):
        if not hasattr(self,'profile_rows'):
            return
        for w in self.profile_rows.winfo_children():
            w.destroy()
        presets=['仅拉伸+调色','背景+曲线','USM+背景+曲线','通道混合器','USM+通道混合器','全部开启','自定义']
        vfmts=['不生成视频','MP4 H.264','MOV H.264','MOV ProRes','GIF']
        for i,p in enumerate(self.export_profiles,1):
            row=ttk.LabelFrame(self.profile_rows,text=f'输出组 {i}',padding=4); row.pack(fill='x',pady=3)
            top=ttk.Frame(row); top.pack(fill='x')
            ttk.Radiobutton(top,text='预览',variable=self.selected_profile_idx,value=i-1,command=self._on_selected_profile_changed).pack(side='left')
            ttk.Checkbutton(top,text='启用',variable=p['enabled'],command=self._on_profile_option_changed).pack(side='left',padx=(4,0))
            ttk.Entry(top,textvariable=p['name'],width=16).pack(side='left',padx=(6,4))
            ttk.Label(top,text='预设').pack(side='left')
            cb=ttk.Combobox(top,textvariable=p['preset'],state='readonly',width=14,values=presets)
            cb.pack(side='left',padx=(4,8)); cb.bind('<<ComboboxSelected>>',lambda e,idx=i-1:self._apply_profile_preset(idx))
            ttk.Label(top,text='命名模板').pack(side='left')
            ttk.Entry(top,textvariable=p['name_template'],width=16).pack(side='left',padx=(4,0))
            io=ttk.Frame(row); io.pack(fill='x',pady=(4,0))
            ttk.Checkbutton(io,text='保存序列',variable=p['save_sequence'],command=self._on_profile_option_changed).pack(side='left')
            ttk.Checkbutton(io,text='保存视频',variable=p['save_video'],command=self._on_profile_option_changed).pack(side='left',padx=(8,0))
            ttk.Combobox(io,textvariable=p['video_format'],state='readonly',width=12,values=vfmts).pack(side='left',padx=(8,0))
            ttk.Label(io,text='缩放 %').pack(side='left',padx=(8,0))
            ttk.Entry(io,textvariable=p['scale_percent'],width=7,justify='right').pack(side='left',padx=(4,0))
            mods=ttk.Frame(row); mods.pack(fill='x',pady=(4,0))
            for key,label in [('stretch','拉伸'),('basic','调色'),('background','BG'),('curves','Curves'),('usm','USM'),('highpass','HighPass'),('emboss','Emboss'),('channel','ChannelMixer')]:
                ttk.Checkbutton(mods,text=label,variable=p[key],command=self._on_profile_option_changed).pack(side='left')
        self._update_profile_summary(); self._draw_selected_profile_graph()

    def _add_export_profile(self):
        self.export_profiles.append(self._new_export_profile())
        self.selected_profile_idx.set(len(self.export_profiles)-1)
        self._rebuild_export_profiles_ui(); self._schedule_live_preview(force=True)

    def _remove_selected_profile(self):
        if len(self.export_profiles) <= 1:
            messagebox.showinfo(APP_NAME,'至少保留 1 个输出组。',parent=self); return
        idx=max(0,min(len(self.export_profiles)-1,int(self.selected_profile_idx.get() or 0)))
        self.export_profiles.pop(idx)
        self.selected_profile_idx.set(max(0,min(idx,len(self.export_profiles)-1)))
        self._rebuild_export_profiles_ui(); self._schedule_live_preview(force=True)

    def _duplicate_selected_profile(self):
        p=self._current_profile()
        if p is None: return
        new=self._new_export_profile(name=p['name'].get()+'_副本', preset='自定义', enabled=p['enabled'].get())
        for k in ['name_template','save_sequence','save_video','delete_sequence_after_video_only','video_format','scale_percent','stretch','basic','background','curves','usm','highpass','emboss','channel']:
            try: new[k].set(p[k].get())
            except Exception: pass
        self.export_profiles.append(new)
        self.selected_profile_idx.set(len(self.export_profiles)-1)
        self._rebuild_export_profiles_ui(); self._schedule_live_preview(force=True)

    def _sanitize_profile_name(self, name, fallback='output'):
        bad='<>:"/' + '\\' + '|?*'
        txt=''.join(ch if ch not in bad else '_' for ch in str(name).strip())
        txt=' '.join(txt.split())
        return txt or fallback

    def _format_output_name(self, prof, method='mean', mode='timelapse'):
        raw_tpl = prof.get('name_template', '{index:02d}_{name}')
        tpl = str(raw_tpl.get() if hasattr(raw_tpl,'get') else raw_tpl) or '{index:02d}_{name}'
        raw_name = prof.get('name', 'output')
        name = self._sanitize_profile_name(raw_name.get() if hasattr(raw_name,'get') else raw_name, 'output')
        raw_index = prof.get('index', 1)
        index = int(raw_index.get() if hasattr(raw_index,'get') else raw_index)
        data={'index':index, 'name':name, 'method':method, 'mode':mode}
        try:
            out=tpl.format(**data)
        except Exception:
            out=f"{int(data['index']):02d}_{name}"
        return self._sanitize_profile_name(out, f"{int(data['index']):02d}_{name}")

    def _profile_to_cfg(self, base_cfg, p):
        cfg=dict(base_cfg)
        for k in ['stretch','basic','background','curves','usm','highpass','emboss','channel']:
            cfg[k]=bool(p[k].get())
        return cfg

    def _iter_enabled_export_profiles(self, base_cfg):
        out=[]
        for i,p in enumerate(self.export_profiles,1):
            save_seq=bool(p['save_sequence'].get())
            save_video=bool(p['save_video'].get()) and str(p['video_format'].get())!='不生成视频'
            if not bool(p['enabled'].get()):
                continue
            if not save_seq and not save_video:
                continue
            cfg=self._profile_to_cfg(base_cfg,p)
            name=self._sanitize_profile_name(p['name'].get(), f'output_{i:02d}')
            out.append({'index':i,'name':name,'cfg':cfg,'name_template':str(p['name_template'].get()),'save_sequence':save_seq,'save_video':save_video,'delete_sequence_after_video_only':bool(p['delete_sequence_after_video_only'].get()),'video_format':str(p['video_format'].get()),'scale_percent':max(1.0,float(p['scale_percent'].get() or 100.0))})
        return out

    def _update_profile_summary(self):
        lines=[]
        for i,p in enumerate(self.export_profiles,1):
            if not bool(p['enabled'].get()):
                continue
            mods=[]
            for key,label in [('stretch','拉伸'),('basic','调色'),('background','BG'),('curves','Curves'),('usm','USM'),('highpass','HighPass'),('emboss','Emboss'),('channel','ChannelMixer')]:
                if bool(p[key].get()): mods.append(label)
            saves=[]
            if bool(p['save_sequence'].get()): saves.append('序列')
            if bool(p['save_video'].get()) and str(p['video_format'].get())!='不生成视频': saves.append(str(p['video_format'].get()))
            lines.append(f"{i}. {self._sanitize_profile_name(p['name'].get(), f'output_{i:02d}')} → " + (' → '.join(mods) if mods else '仅保存线性结果') + ' ｜ 输出：' + (' + '.join(saves) if saves else '无') + f" ｜ 缩放 {float(p['scale_percent'].get() or 100.0):.0f}%")
        txt='；'.join(lines) if lines else '当前没有有效输出组。请启用输出组，并至少勾选保存序列或保存视频。'
        if hasattr(self,'profile_summary'): self.profile_summary.set(txt)

    def _on_profile_option_changed(self, *args):
        self._update_profile_summary(); self._draw_selected_profile_graph(); self._schedule_live_preview(force=True)

    def _on_selected_profile_changed(self):
        self._draw_selected_profile_graph(); self._schedule_live_preview(force=True)

    def _draw_selected_profile_graph(self):
        if not hasattr(self,'profile_node_canvas'):
            return
        c=self.profile_node_canvas; c.delete('all')
        p=self._current_profile()
        if p is None:
            return
        self.profile_canvas_title.set(f"节点画布：{self._sanitize_profile_name(p['name'].get(),'output')}（点击下方节点可切换启用/禁用）")
        W=max(c.winfo_width(),520); H=max(c.winfo_height(),145)
        y=H//2
        labels=[('stack','Stack',True),('stretch','Stretch',p['stretch'].get()),('basic','Basic',p['basic'].get()),('background','BG',p['background'].get()),('curves','Curves',p['curves'].get()),('usm','USM',p['usm'].get()),('highpass','HP',p['highpass'].get()),('emboss','Emboss',p['emboss'].get()),('channel','Mixer',p['channel'].get()),('output','Output',True)]
        xs=[]; n=len(labels)
        left=35; right=W-35
        step=(right-left)/max(1,n-1)
        self._profile_canvas_hit=[]
        for i,(key,label,enabled) in enumerate(labels):
            x=int(round(left+i*step)); xs.append(x)
        enabled_keys=[k for k,_,e in labels if e]
        # draw connections between enabled pipeline stages
        prev_x=None
        for (key,label,enabled),x in zip(labels,xs):
            if enabled:
                if prev_x is not None:
                    c.create_line(prev_x+36,y,x-36,y,fill='#5fb0ff',width=2,arrow='last')
                prev_x=x
        for (key,label,enabled),x in zip(labels,xs):
            fill='#2e8fff' if enabled else '#3a3a3a'
            outline='#bfe0ff' if enabled else '#777777'
            c.create_rectangle(x-36,y-20,x+36,y+20,fill=fill,outline=outline,width=2)
            c.create_text(x,y-1,text=label,fill='white' if enabled else '#cccccc',font=_ui_font(9))
            if key not in ('stack','output'):
                self._profile_canvas_hit.append((x-36,y-20,x+36,y+20,key))
        c.create_text(8,10,anchor='nw',text='固定顺序：Stack → Stretch → Basic → BG → Curves → USM → HighPass → Emboss → ChannelMixer → Output',fill='#bbbbbb',font=_ui_font(8))

    def _on_profile_canvas_click(self, event):
        p=self._current_profile()
        if p is None: return
        for x1,y1,x2,y2,key in getattr(self,'_profile_canvas_hit',[]):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                p[key].set(not bool(p[key].get()))
                self._on_profile_option_changed()
                return

    def _build_ui(self):
        root=ttk.Frame(self,padding=8); root.pack(fill='both',expand=True)
        top=ttk.Frame(root); top.pack(fill='x')
        ttk.Label(top,text='堆栈延时 / Stack Timelapse',font=_ui_font(15)).pack(side='left')
        ttk.Label(top,text=f'输入 {len(self.app.files)} 帧',foreground='#666666').pack(side='right')
        ttk.Separator(root).pack(fill='x',pady=7)
        pane=ttk.Panedwindow(root,orient='horizontal'); pane.pack(fill='both',expand=True)
        left_outer=ttk.Frame(pane); right=ttk.Frame(pane,padding=(8,0,0,0)); pane.add(left_outer,weight=3); pane.add(right,weight=4)
        canvas=tk.Canvas(left_outer,highlightthickness=0); sb=ttk.Scrollbar(left_outer,orient='vertical',command=canvas.yview,style='IHS.Vertical.TScrollbar'); canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
        left=ttk.Frame(canvas,padding=(2,0,8,0)); wid=canvas.create_window((0,0),window=left,anchor='nw')
        left.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all'))); canvas.bind('<Configure>',lambda e:canvas.itemconfigure(wid,width=e.width))
        canvas.bind('<Enter>',lambda e:canvas.bind_all('<MouseWheel>',lambda ev:canvas.yview_scroll(-1 if ev.delta>0 else 1,'units'))); canvas.bind('<Leave>',lambda e:canvas.unbind_all('<MouseWheel>'))

        gen=ttk.LabelFrame(left,text='第 1 步 · 生成参考堆栈',padding=8); gen.pack(fill='x')
        r=ttk.Frame(gen); r.pack(fill='x',pady=2); ttk.Label(r,text='生成模式').pack(side='left'); modecb=ttk.Combobox(r,textvariable=self.mode,state='readonly',width=28,values=['滑动窗口（推荐：观察变化）','中心窗口（按中央时刻理解）','累计堆栈（观察信号生长）','逐帧剔除（贡献分析）']); modecb.pack(side='right')
        ttk.Label(gen,textvariable=self.mode_description,foreground='#555555',wraplength=430,justify='left').pack(anchor='w',pady=(5,7))
        r=ttk.Frame(gen); r.pack(fill='x',pady=2); ttk.Label(r,text='堆栈方式').pack(side='left'); ttk.Combobox(r,textvariable=self.stack_method,state='readonly',width=24,values=['平均值 Mean','最大值 Maximum']).pack(side='right')
        self._entry_row(gen,'窗口大小（帧）',self.window_size); self._entry_row(gen,'步长（帧）',self.step)
        ttk.Label(gen,textvariable=self.summary,foreground='#555555',wraplength=430).pack(anchor='w',pady=(5,4))
        rr=ttk.Frame(gen); rr.pack(fill='x',pady=(5,0)); ttk.Label(rr,text='参考输出帧').pack(side='left'); self.preview_spin=ttk.Spinbox(rr,textvariable=self.preview_index,from_=1,to=1,width=8); self.preview_spin.pack(side='left',padx=6); ttk.Button(rr,text='生成参考堆栈',style='Primary.TButton',command=self.generate_reference).pack(side='right')
        ttk.Label(gen,text='参考堆栈只生成一次。后面调拉伸、颜色、Background、Curves、USM、浮雕时都直接在这张参考图上预览，不会反复重新堆栈。',foreground='#666666',wraplength=430).pack(anchor='w',pady=(6,0))
        _build_ewb_panel(self,left,wraplength=430)
        _build_timelapse_memory_panel(self,left,wraplength=430)

        proc=ttk.LabelFrame(left,text='第 2 步 · 在参考图上搭建处理链',padding=8); proc.pack(fill='x',pady=(8,0))
        ttk.Label(proc,text='每一段都有蓝色滑块 + 可直接输入的数值框，并可“预览到此步骤”。后面的批量帧会使用完全相同的参数。',foreground='#555555',wraplength=430).pack(anchor='w',pady=(0,6))

        # Stretch
        sec=ttk.LabelFrame(proc,text='A. 拉伸',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用 Asinh 拉伸',variable=self.p_stretch).pack(anchor='w'); self._slider_row(sec,'Strength',self.p_stretch_strength,0.1,500,0.1,reset_value=float(self.p_stretch_strength.get())); self._slider_row(sec,'Black Point',self.p_stretch_black,0.0,0.25,0.0001,reset_value=0.0)
        ttk.Button(sec,text='预览：拉伸后',command=lambda:self.preview_stage('stretch')).pack(fill='x',pady=(4,0))

        # Basic color/tone
        sec=ttk.LabelFrame(proc,text='B. 基础调色',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用基础调色',variable=self.p_basic).pack(anchor='w')
        self._slider_row(sec,'Exposure EV',self.p_exposure,-3,3,0.05,reset_value=0.0)
        for label,var in [('Contrast',self.p_contrast),('Highlights',self.p_highlights),('Shadows',self.p_shadows),('Whites',self.p_whites),('Blacks',self.p_blacks),('Clarity',self.p_clarity),('Dehaze',self.p_dehaze),('Vibrance',self.p_vibrance),('Saturation',self.p_saturation)]:
            self._slider_row(sec,label,var,-100,100,1,reset_value=0.0)
        ttk.Button(sec,text='预览：拉伸 + 调色后',command=lambda:self.preview_stage('basic')).pack(fill='x',pady=(4,0))

        # Background + Curves: curves are edited directly on the timelapse reference frame.
        sec=ttk.LabelFrame(proc,text='C. Background + Curves',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='Background Suppression 背景抑制',variable=self.p_bg).pack(anchor='w'); self._slider_row(sec,'Radius px',self.p_bg_radius,1,500,1,reset_value=80.0); self._slider_row(sec,'Strength %',self.p_bg_strength,0,200,1,reset_value=100.0)
        cr=ttk.Frame(sec); cr.pack(fill='x',pady=(5,3)); ttk.Checkbutton(cr,text='使用 Curves',variable=self.p_curves).pack(side='left'); ttk.Button(cr,text='读取主界面曲线',command=self._capture_curves).pack(side='right')
        crow=ttk.Frame(sec); crow.pack(fill='x',pady=(2,3)); ttk.Label(crow,text='曲线通道').pack(side='left')
        ccb=ttk.Combobox(crow,textvariable=self.tl_curve_channel,state='readonly',width=10,values=['RGB','红色','绿色','蓝色','亮度']); ccb.pack(side='right'); ccb.bind('<<ComboboxSelected>>',lambda e:self._tl_curve_channel_changed())
        self.tl_curve_canvas=tk.Canvas(sec,height=285,bg='#202020',highlightthickness=1,highlightbackground='#404040')
        self.tl_curve_canvas.pack(fill='x',pady=(2,4))
        self.tl_curve_canvas.bind('<Button-1>',self._tl_curve_click); self.tl_curve_canvas.bind('<B1-Motion>',self._tl_curve_drag); self.tl_curve_canvas.bind('<ButtonRelease-1>',self._tl_curve_release); self.tl_curve_canvas.bind('<Button-3>',self._tl_curve_right_click); self.tl_curve_canvas.bind('<Configure>',lambda e:(self.tl_curve_canvas.delete('curve_static'),self._draw_tl_curve_editor()))
        cv=ttk.Frame(sec); cv.pack(fill='x',pady=(0,4))
        ttk.Label(cv,text='输入').grid(row=0,column=0,sticky='w'); ie=ttk.Entry(cv,textvariable=self.tl_curve_input,width=9,justify='right'); ie.grid(row=0,column=1,sticky='ew',padx=(4,10))
        ttk.Label(cv,text='输出').grid(row=0,column=2,sticky='w'); oe=ttk.Entry(cv,textvariable=self.tl_curve_output,width=9,justify='right'); oe.grid(row=0,column=3,sticky='ew',padx=(4,0)); cv.columnconfigure(1,weight=1); cv.columnconfigure(3,weight=1)
        for ee in (ie,oe):
            ee.bind('<Control-a>',lambda ev,e=ee:(e.selection_range(0,'end'),'break')[1]); ee.bind('<Control-A>',lambda ev,e=ee:(e.selection_range(0,'end'),'break')[1]); ee.bind('<Double-Button-1>',lambda ev,e=ee:(e.focus_set(),e.selection_range(0,'end'),'break')[2])
        self.tl_curve_input.trace_add('write',lambda *a:self._tl_curve_numeric_changed()); self.tl_curve_output.trace_add('write',lambda *a:self._tl_curve_numeric_changed())
        cbuttons=ttk.Frame(sec); cbuttons.pack(fill='x',pady=(2,2)); ttk.Button(cbuttons,text='重置当前通道',command=self._reset_tl_curve_current).pack(side='left',fill='x',expand=True,padx=(0,3)); ttk.Button(cbuttons,text='重置全部曲线',command=self._reset_tl_curves).pack(side='left',fill='x',expand=True,padx=(3,0))
        ttk.Label(sec,text='点击添加控制点；左右拖动改变 Input，上下拖动改变 Output；右键删除中间控制点。灰色波峰为参考帧在进入 Curves 前的直方图。',foreground='#666666',wraplength=420).pack(anchor='w',pady=(3,2))
        ttk.Button(sec,text='预览：Background + Curves 后',command=lambda:self.preview_stage('background_curves')).pack(fill='x',pady=(4,0))

        # USM with repeat count.
        sec=ttk.LabelFrame(proc,text='D. USM 锐化（可重复）',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用 USM',variable=self.p_usm).pack(anchor='w'); self._slider_row(sec,'Amount %',self.p_usm_amount,0,500,1,reset_value=0.0); self._slider_row(sec,'Radius px',self.p_usm_radius,0.1,250,0.1,reset_value=2.0); self._slider_row(sec,'Threshold',self.p_usm_threshold,0,255,1,reset_value=0.0); self._slider_row(sec,'重复次数（1–10）',self.p_usm_passes,1,10,1,reset_value=1)
        ttk.Label(sec,text='例如次数=3：同一组 USM 参数连续应用 3 次。',foreground='#666666').pack(anchor='w')
        ttk.Button(sec,text='预览：USM 后',command=lambda:self.preview_stage('usm')).pack(fill='x',pady=(4,0))

        sec=ttk.LabelFrame(proc,text='E. High Pass',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用 High Pass',variable=self.p_hp).pack(anchor='w'); self._slider_row(sec,'Radius px',self.p_hp_radius,0.1,250,0.1,reset_value=10.0); self._slider_row(sec,'Opacity %',self.p_hp_amount,0,100,1,reset_value=100.0)
        r=ttk.Frame(sec); r.pack(fill='x',pady=2); ttk.Label(r,text='Mode').pack(side='left'); ttk.Combobox(r,textvariable=self.p_hp_mode,state='readonly',width=15,values=['Overlay','Soft Light','Linear Light']).pack(side='right')
        ttk.Button(sec,text='预览：High Pass 后',command=lambda:self.preview_stage('highpass')).pack(fill='x',pady=(4,0))

        sec=ttk.LabelFrame(proc,text='F. 浮雕 Emboss',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用浮雕',variable=self.p_emboss).pack(anchor='w')
        r=ttk.Frame(sec);r.pack(fill='x',pady=2);ttk.Label(r,text='Style').pack(side='left');ttk.Combobox(r,textvariable=self.p_emboss_style,state='readonly',width=20,values=['Photoshop Emboss','Color Emboss','Gray Emboss']).pack(side='right')
        self._slider_row(sec,'Angle °',self.p_emboss_angle,-180,180,1,reset_value=-128.0)
        dialrow=ttk.Frame(sec);dialrow.pack(fill='x',pady=(1,3));ttk.Label(dialrow,text='Angle Dial / 方向圆盘',foreground='#666').pack(side='left');AngleDial(dialrow,self.p_emboss_angle,command=lambda v:self._schedule_live_preview(dragging=True),release_command=lambda v:self._schedule_live_preview(force=True),reset_value=-128.0,size=66).pack(side='right')
        self._slider_row(sec,'Height px',self.p_emboss_height,1,200,1,reset_value=1.0); self._slider_row(sec,'Amount %',self.p_emboss_amount,1,500,1,reset_value=100.0)
        r=ttk.Frame(sec);r.pack(fill='x',pady=2);ttk.Label(r,text='Blend Mode').pack(side='left');ttk.Combobox(r,textvariable=self.p_emboss_blend,state='readonly',width=16,values=['Normal','Overlay','Soft Light','Linear Light']).pack(side='right')
        self._slider_row(sec,'Opacity %',self.p_emboss_opacity,0,100,1,reset_value=100.0)
        ttk.Label(sec,text='Photoshop Emboss：PS 风格灰色浮雕基底 + 原色边缘描迹；Color Emboss：完整保留原图色彩；Gray Emboss：旧版中性灰浮雕。',foreground='#666',wraplength=390).pack(anchor='w',pady=(2,0))
        ttk.Button(sec,text='预览：浮雕后',command=lambda:self.preview_stage('emboss')).pack(fill='x',pady=(4,0))

        sec=ttk.LabelFrame(proc,text='G. Channel Mixer',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用通道混合器',variable=self.p_channel).pack(anchor='w')
        r=ttk.Frame(sec); r.pack(fill='x',pady=2); ttk.Label(r,text='输出').pack(side='left'); ttk.Combobox(r,textvariable=self.p_channel_output,state='readonly',width=12,values=['灰色','红色','绿色','蓝色']).pack(side='right')
        ttk.Checkbutton(sec,text='单色',variable=self.p_channel_mono).pack(anchor='w'); self._slider_row(sec,'R %',self.p_channel_red,-200,200,1,reset_value=40.0); self._slider_row(sec,'G %',self.p_channel_green,-200,200,1,reset_value=40.0); self._slider_row(sec,'B %',self.p_channel_blue,-200,200,1,reset_value=20.0); self._slider_row(sec,'常数 %',self.p_channel_constant,-100,100,1,reset_value=0.0)
        ttk.Checkbutton(sec,text='色彩噪声保护',variable=self.p_channel_noise).pack(anchor='w'); self._slider_row(sec,'噪声保护强度 %',self.p_channel_noise_strength,0,100,1,reset_value=30.0); self._slider_row(sec,'噪声保护半径 px',self.p_channel_noise_radius,0.1,10,0.1,reset_value=0.8)
        ttk.Button(sec,text='预览：最终处理效果',command=lambda:self.preview_stage('channel')).pack(fill='x',pady=(4,0))

        lock=ttk.Frame(proc); lock.pack(fill='x',pady=(8,2)); self.lock_btn=ttk.Button(lock,text='锁定当前处理方案',style='Primary.TButton',command=self.lock_pipeline); self.lock_btn.pack(side='left',fill='x',expand=True); ttk.Label(lock,textvariable=self.lock_status,foreground='#666666').pack(side='right',padx=(8,0))

        out=ttk.LabelFrame(left,text='第 3 步 · 批量生成与视频输出',padding=8); out.pack(fill='x',pady=(8,0))
        r=ttk.Frame(out); r.pack(fill='x'); ttk.Entry(r,textvariable=self.output_folder).pack(side='left',fill='x',expand=True); ttk.Button(r,text='选择...',command=self._choose_output).pack(side='right',padx=(5,0))
        r=ttk.Frame(out); r.pack(fill='x',pady=(5,2)); ttk.Checkbutton(r,text='保存图像序列',variable=self.save_sequence).pack(side='left'); ttk.Combobox(r,textvariable=self.sequence_format,state='readonly',width=17,values=['PNG 8-bit','JPEG','TIFF 16-bit','TIFF 32-bit Float']).pack(side='right')
        r=ttk.Frame(out); r.pack(fill='x',pady=2); ttk.Label(r,text='视频格式').pack(side='left'); ttk.Combobox(r,textvariable=self.video_format,state='readonly',width=18,values=['不生成视频','MP4 H.264','MOV H.264','MOV ProRes','GIF']).pack(side='right')
        self._entry_row(out,'FPS',self.fps)
        r=ttk.Frame(out); r.pack(fill='x',pady=2); ttk.Label(r,text='视频分辨率').pack(side='left'); ttk.Combobox(r,textvariable=self.resolution,state='readonly',width=20,values=['原始分辨率','16:9 · 3840×2160','4:3 · 2880×2160','自定义']).pack(side='right')
        self._entry_row(out,'自定义 Width',self.custom_w); self._entry_row(out,'自定义 Height',self.custom_h)
        r=ttk.Frame(out); r.pack(fill='x',pady=2); ttk.Label(r,text='宽高比处理').pack(side='left'); ttk.Combobox(r,textvariable=self.fit_mode,state='readonly',width=16,values=['Fill 裁切','Fit 黑边','Stretch 拉伸']).pack(side='right')
        self._build_export_profiles_ui(out)

        prev=ttk.LabelFrame(right,text='参考图 / 处理效果预览',padding=6); prev.pack(fill='both',expand=True)
        self.preview_title=tk.StringVar(value='尚未生成参考堆栈')
        prev_head=ttk.Frame(prev);prev_head.pack(fill='x')
        ttk.Label(prev_head,textvariable=self.preview_title,font=_ui_font(10)).pack(side='left',anchor='w')
        self.preview_zoom_text=tk.StringVar(value='Fit')
        zoom_bar=ttk.Frame(prev_head);zoom_bar.pack(side='right')
        for label,value in [('25%',0.25),('50%',0.50),('100%',1.0),('200%',2.0)]:
            ttk.Button(zoom_bar,text=label,width=5,command=lambda v=value:self._preview_set_zoom(v)).pack(side='left',padx=1)
        ttk.Button(zoom_bar,text='Fit',width=5,command=self._preview_fit).pack(side='left',padx=(2,0))
        ttk.Label(zoom_bar,textvariable=self.preview_zoom_text,width=10,anchor='e').pack(side='left',padx=(5,0))
        ttk.Checkbutton(prev,text='实时预览参考帧处理效果',variable=self.live_preview,command=lambda:self._schedule_live_preview(force=True)).pack(anchor='w',pady=(2,0))
        self.preview_canvas=tk.Canvas(prev,bg='#151515',highlightthickness=0); self.preview_canvas.pack(fill='both',expand=True,pady=(6,0)); self.preview_canvas.create_text(15,15,anchor='nw',fill='#aaa',text='第 1 步：点击“生成参考堆栈”。')
        self.preview_zoom=1.0; self.preview_fit_mode=True; self.preview_pan=[0.0,0.0]; self.preview_pan_anchor=None; self.last_preview_image=None; self.preview_display_rect=None
        self.preview_canvas.bind('<MouseWheel>',self._preview_wheel)
        self.preview_canvas.bind('<Button-4>',lambda e:self._preview_wheel_linux(e,1))
        self.preview_canvas.bind('<Button-5>',lambda e:self._preview_wheel_linux(e,-1))
        self.preview_canvas.bind('<ButtonPress-1>',self._preview_pan_start)
        self.preview_canvas.bind('<B1-Motion>',self._preview_pan_drag)
        self.preview_canvas.bind('<ButtonRelease-1>',self._preview_pan_end)
        self.preview_canvas.bind('z',lambda e:self._preview_fit())
        self.preview_canvas.bind('Z',lambda e:self._preview_fit())
        self.preview_canvas.bind('<Configure>',lambda e:self._preview_redraw(),add='+')
        ttk.Label(right,text='工作流：先确认参考堆栈 → 在同一张参考图上逐段预览处理 → 锁定参数 → 批量应用到全部时间帧。开启“实时预览”后，拖动滑块或修改数值会自动刷新右侧参考帧画面。',foreground='#555555',wraplength=600).pack(anchor='w',pady=(6,4))
        br=ttk.Frame(right); br.pack(fill='x',pady=(3,0)); self.start_btn=ttk.Button(br,text='开始批量生成',style='Primary.TButton',command=self.start_batch,state='disabled'); self.start_btn.pack(side='left',fill='x',expand=True,padx=(0,4)); self.cancel_btn=ttk.Button(br,text='取消',command=self.cancel,state='disabled'); self.cancel_btn.pack(side='right',padx=(4,0))
        ttk.Label(right,text='Processing / 处理',foreground='#666').pack(anchor='w',pady=(7,0))
        ttk.Progressbar(right,variable=self.processing_progress,maximum=100).pack(fill='x',pady=(2,2))
        ttk.Label(right,text='Writing / 写入',foreground='#666').pack(anchor='w',pady=(2,0))
        ttk.Progressbar(right,variable=self.writing_progress,maximum=100).pack(fill='x',pady=(2,2))
        ttk.Label(right,textvariable=self.output_pipeline_text,foreground='#666',wraplength=600).pack(anchor='w',pady=(1,2))
        ttk.Progressbar(right,variable=self.progress,maximum=100).pack(fill='x',pady=(4,3)); ttk.Label(right,textvariable=self.status).pack(anchor='w')

        for v in (self.mode,self.stack_method,self.window_size,self.step):
            v.trace_add('write',lambda *a:self._update_summary())
        proc_vars=[self.p_stretch,self.p_stretch_strength,self.p_stretch_black,self.p_basic,self.p_exposure,self.p_contrast,self.p_highlights,self.p_shadows,self.p_whites,self.p_blacks,self.p_clarity,self.p_dehaze,self.p_vibrance,self.p_saturation,self.p_bg,self.p_bg_radius,self.p_bg_strength,self.p_curves,self.p_usm,self.p_usm_amount,self.p_usm_radius,self.p_usm_threshold,self.p_usm_passes,self.p_hp,self.p_hp_radius,self.p_hp_amount,self.p_hp_mode,self.p_emboss,self.p_emboss_angle,self.p_emboss_height,self.p_emboss_amount,self.p_emboss_style,self.p_emboss_blend,self.p_emboss_opacity,self.p_channel,self.p_channel_output,self.p_channel_mono,self.p_channel_red,self.p_channel_green,self.p_channel_blue,self.p_channel_constant,self.p_channel_noise,self.p_channel_noise_strength,self.p_channel_noise_radius]
        for v in proc_vars:v.trace_add('write',lambda *a:self._on_processing_param_changed())
        # Only parameters *before* Curves change the histogram entering Curves.
        # Cache that histogram so dragging a curve point never recomputes Background/Basic/Stretch.
        curve_hist_upstream=[self.p_stretch,self.p_stretch_strength,self.p_stretch_black,self.p_basic,self.p_exposure,self.p_contrast,self.p_highlights,self.p_shadows,self.p_whites,self.p_blacks,self.p_clarity,self.p_dehaze,self.p_vibrance,self.p_saturation,self.p_bg,self.p_bg_radius,self.p_bg_strength]
        for v in curve_hist_upstream:v.trace_add('write',lambda *a:self._invalidate_tl_curve_hist())

    def _capture_curves(self):
        self.curve_snapshot=copy.deepcopy(getattr(self.app,'curve_points',{})); self.status.set('已读取主界面当前 Curves 控制点'); self._mark_pipeline_dirty(); self._draw_tl_curve_editor(); self._schedule_live_preview(force=True)

    def _on_processing_param_changed(self):
        self._mark_pipeline_dirty()
        self._schedule_live_preview()

    def _schedule_live_preview(self, force=False, dragging=False):
        if self.reference_master is None or not bool(self.live_preview.get()):
            return
        if self.worker and self.worker.is_alive() and not force:
            return
        self._live_preview_requested_quality = 'drag' if dragging else ('hq' if force else 'fast')
        try:
            if self._live_preview_after_id is not None:
                self.after_cancel(self._live_preview_after_id)
        except Exception:
            pass
        delay = 1 if force else (18 if dragging else int(self.live_preview_delay_ms))
        self._live_preview_after_id = self.after(delay, self._launch_live_preview)

    def _launch_live_preview(self):
        self._live_preview_after_id=None
        if self.reference_master is None or not bool(self.live_preview.get()):
            return
        if self._live_preview_running:
            self._live_preview_pending=True
            return
        quality=self._live_preview_requested_quality
        if quality=='hq' and self.reference_proxy_hq is not None:
            base=self.reference_proxy_hq; scale=self.reference_proxy_hq_scale
        elif quality=='drag' and self.reference_proxy_drag is not None:
            base=self.reference_proxy_drag; scale=self.reference_proxy_drag_scale
        elif self.reference_proxy_fast is not None:
            base=self.reference_proxy_fast; scale=self.reference_proxy_fast_scale
        else:
            base=self.reference_master; scale=1.0
        base_cfg=self._snapshot_cfg();
        current_profile=self._current_profile()
        effective_cfg=self._profile_to_cfg(base_cfg,current_profile) if current_profile is not None else base_cfg
        cfg=scale_timelapse_cfg_for_proxy(effective_cfg,scale); curves=copy.deepcopy(self.curve_snapshot)
        self._live_preview_token += 1
        token=self._live_preview_token
        self._live_preview_running=True
        qname='拖动代理' if quality=='drag' else ('快速代理' if quality=='fast' else '高质量代理')
        self.preview_title.set('实时预览：最终处理效果 · '+qname)
        self.status.set('正在实时刷新参考帧预览…')
        def work():
            try:
                out=apply_timelapse_pipeline(base,cfg,curves,stop_after='channel')
                self.queue.put(('stage_preview_live',(token,out,'实时预览：最终处理效果')))
            except Exception as e:
                self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()

    def _tl_curve_points(self):
        ch=self.tl_curve_channel.get()
        return self.curve_snapshot.setdefault(ch,[(0.0,0.0),(1.0,1.0)])

    def _tl_curve_geom(self):
        c=self.tl_curve_canvas; W=max(c.winfo_width(),120); H=max(c.winfo_height(),160); m=18; strip=20
        return W,H,m,max(20,W-2*m),max(20,H-2*m-strip)

    def _tl_curve_to_canvas(self,x,y):
        W,H,m,w,h=self._tl_curve_geom(); return m+x*w,m+(1-y)*h

    def _tl_canvas_to_curve(self,cx,cy):
        W,H,m,w,h=self._tl_curve_geom(); return max(0,min(1,(cx-m)/w)),max(0,min(1,1-(cy-m)/h))

    def _tl_curve_nearest(self,cx,cy,threshold=10):
        best=None; bd=1e9
        for i,(x,y) in enumerate(self._tl_curve_points()):
            px,py=self._tl_curve_to_canvas(x,y); d=((cx-px)**2+(cy-py)**2)**0.5
            if d<bd: best=i; bd=d
        return best if best is not None and bd<=threshold else None

    def _tl_curve_set_numeric(self):
        if self.tl_curve_selected_idx is None:return
        pts=self._tl_curve_points(); i=self.tl_curve_selected_idx
        if not (0<=i<len(pts)):return
        self._tl_curve_sync=True
        try:
            self.tl_curve_input.set(round(pts[i][0]*255,2)); self.tl_curve_output.set(round(pts[i][1]*255,2))
        finally:self._tl_curve_sync=False

    def _invalidate_tl_curve_hist(self):
        self._tl_curve_hist_dirty=True
        self._tl_curve_hist_source=None
        self._tl_curve_hist_cache.clear()
        # Do not force a redraw for every slider tick. The next curve redraw/channel change
        # will lazily rebuild the histogram once from the newest upstream parameters.

    def _timelapse_curve_hist_image(self):
        if self.reference_master is None:return None
        if not self._tl_curve_hist_dirty and self._tl_curve_hist_source is not None:
            return self._tl_curve_hist_source
        base=self.reference_proxy_drag if self.reference_proxy_drag is not None else (self.reference_proxy_fast if self.reference_proxy_fast is not None else self.reference_master)
        scale=self.reference_proxy_drag_scale if self.reference_proxy_drag is not None else (self.reference_proxy_fast_scale if self.reference_proxy_fast is not None else 1.0)
        base_cfg=self._snapshot_cfg()
        current_profile=self._current_profile()
        effective_cfg=self._profile_to_cfg(base_cfg,current_profile) if current_profile is not None else base_cfg
        cfg=scale_timelapse_cfg_for_proxy(effective_cfg,scale)
        # Curves histogram is the signal entering Curves: stretch/basic/background only.
        cfg['curves']=False
        try:self._tl_curve_hist_source=apply_timelapse_pipeline(base,cfg,{},stop_after='background_curves')
        except Exception:self._tl_curve_hist_source=base
        self._tl_curve_hist_cache.clear();self._tl_curve_hist_dirty=False
        return self._tl_curve_hist_source

    def _tl_curve_hist(self,ch):
        cached=self._tl_curve_hist_cache.get(ch)
        if cached is not None:return cached
        try:
            np,*_=_deps();img=self._timelapse_curve_hist_image()
            if img is None:return None
            smp=np.clip(img[::4,::4],0,1)
            if ch=='红色':vals=smp[...,0].ravel()
            elif ch=='绿色':vals=smp[...,1].ravel()
            elif ch=='蓝色':vals=smp[...,2].ravel()
            else:vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
            hist,_=np.histogram(vals,bins=160,range=(0,1));hist=np.log1p(hist.astype(np.float64));hist/=max(hist.max(),1.0)
            self._tl_curve_hist_cache[ch]=hist
            return hist
        except Exception:return None

    def _draw_tl_curve_editor(self):
        if not hasattr(self,'tl_curve_canvas'):return
        c=self.tl_curve_canvas;c.delete('curve_dynamic');W,H,m,w,h=self._tl_curve_geom()
        # Static background/grid/histogram is rebuilt only when missing or histogram becomes dirty.
        if not c.find_withtag('curve_static') or self._tl_curve_hist_dirty:
            c.delete('curve_static')
            c.create_rectangle(m,m,m+w,m+h,outline='#666666',fill='#222222',tags='curve_static')
            for j in range(1,4):
                gx=m+w*j/4;gy=m+h*j/4;c.create_line(gx,m,gx,m+h,fill='#343434',tags='curve_static');c.create_line(m,gy,m+w,gy,fill='#343434',tags='curve_static')
            c.create_line(m,m+h,m+w,m,fill='#555555',dash=(4,3),tags='curve_static')
            hist=self._tl_curve_hist(self.tl_curve_channel.get())
            if hist is not None:
                poly=[m,m+h];ridge=[]
                for j,v in enumerate(hist):
                    x=m+(j/(len(hist)-1))*w;y=m+h-v*h*0.78;poly.extend([x,y]);ridge.extend([x,y])
                poly.extend([m+w,m+h]);c.create_polygon(*poly,fill='#4a4a4a',outline='',tags='curve_static');c.create_line(*ridge,fill='#777777',width=1,tags='curve_static')
            # Recreate dynamic curve after static background so it remains on top.
        pts=self._tl_curve_points();lut=build_curve_lut(pts,256);line=[]
        for j,v in enumerate(lut):
            x,y=self._tl_curve_to_canvas(j/255,float(v));line.extend([x,y])
        c.create_line(*line,fill='#58a6ff',width=2,smooth=True,tags='curve_dynamic')
        axis_y=m+h+12
        if len(pts)>=2:
            bx,_=self._tl_curve_to_canvas(pts[0][0],pts[0][1]);wx,_=self._tl_curve_to_canvas(pts[-1][0],pts[-1][1])
            c.create_polygon(bx-6,axis_y+6,bx+6,axis_y+6,bx,axis_y-4,fill='#111111',outline='#999999',tags='curve_dynamic')
            c.create_polygon(wx-6,axis_y+6,wx+6,axis_y+6,wx,axis_y-4,fill='#eeeeee',outline='#999999',tags='curve_dynamic')
        for i,(x,y) in enumerate(pts):
            cx,cy=self._tl_curve_to_canvas(x,y);r=6 if i==self.tl_curve_selected_idx else 4;fill='#fff' if i==self.tl_curve_selected_idx else '#b9d6ff';c.create_oval(cx-r,cy-r,cx+r,cy+r,fill=fill,outline='#1f6feb',tags='curve_dynamic')
        try:c.tag_raise('curve_dynamic')
        except Exception:pass

    def _tl_curve_channel_changed(self):
        self.tl_curve_selected_idx=None
        try:self.tl_curve_canvas.delete('curve_static')
        except Exception:pass
        self._draw_tl_curve_editor()

    def _tl_curve_click(self,event):
        pts=self._tl_curve_points(); W,H,m,w,h=self._tl_curve_geom(); axis_y=m+h+12
        if len(pts)>=2:
            bx,_=self._tl_curve_to_canvas(pts[0][0],pts[0][1]); wx,_=self._tl_curve_to_canvas(pts[-1][0],pts[-1][1])
            if abs(event.y-axis_y)<=12 and abs(event.x-bx)<=12:self.tl_curve_axis_drag='black';self.tl_curve_selected_idx=0;self._tl_curve_set_numeric();return
            if abs(event.y-axis_y)<=12 and abs(event.x-wx)<=12:self.tl_curve_axis_drag='white';self.tl_curve_selected_idx=len(pts)-1;self._tl_curve_set_numeric();return
        self.tl_curve_axis_drag=None
        if event.y>m+h:return
        idx=self._tl_curve_nearest(event.x,event.y)
        if idx is None:
            x,y=self._tl_canvas_to_curve(event.x,event.y);pts.append((x,y));pts.sort(key=lambda p:p[0]);idx=min(range(len(pts)),key=lambda i:abs(pts[i][0]-x)+abs(pts[i][1]-y));
            if not self.p_curves.get():self.p_curves.set(True)
        self.tl_curve_selected_idx=idx;self._tl_curve_set_numeric();self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(dragging=True)

    def _tl_curve_drag(self,event):
        if self.tl_curve_selected_idx is None:return
        pts=self._tl_curve_points();i=self.tl_curve_selected_idx;x,y=self._tl_canvas_to_curve(event.x,event.y)
        if self.tl_curve_axis_drag=='black':x=max(0,min(pts[1][0]-0.002,x));pts[0]=(x,pts[0][1]);i=0
        elif self.tl_curve_axis_drag=='white':x=max(pts[-2][0]+0.002,min(1,x));pts[-1]=(x,pts[-1][1]);i=len(pts)-1
        else:
            if i==0:x=max(0,min(pts[1][0]-0.002,x))
            elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
            else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
            pts[i]=(x,y)
        self.tl_curve_selected_idx=i
        if not self.p_curves.get():self.p_curves.set(True)
        self._tl_curve_set_numeric();self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(dragging=True)

    def _tl_curve_release(self,event):
        self.tl_curve_axis_drag=None;self._schedule_live_preview(force=True)

    def _tl_curve_right_click(self,event):
        idx=self._tl_curve_nearest(event.x,event.y);pts=self._tl_curve_points()
        if idx is None or idx in (0,len(pts)-1):return
        pts.pop(idx);self.tl_curve_selected_idx=None;self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(force=True)

    def _tl_curve_numeric_changed(self):
        if self._tl_curve_sync or self.tl_curve_selected_idx is None:return
        pts=self._tl_curve_points();i=self.tl_curve_selected_idx
        try:x=max(0,min(1,float(self.tl_curve_input.get())/255));y=max(0,min(1,float(self.tl_curve_output.get())/255))
        except Exception:return
        if i==0:x=max(0,min(pts[1][0]-0.002,x))
        elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
        else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
        pts[i]=(x,y)
        if not self.p_curves.get():self.p_curves.set(True)
        self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview()

    def _reset_tl_curve_current(self):
        self.curve_snapshot[self.tl_curve_channel.get()]=[(0.0,0.0),(1.0,1.0)];self.tl_curve_selected_idx=None;self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(force=True)

    def _reset_tl_curves(self):
        self.curve_snapshot={k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']};self.tl_curve_selected_idx=None;self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(force=True)

    def _mark_pipeline_dirty(self):
        if getattr(self,'pipeline_locked',False):
            self.pipeline_locked=False
            self.lock_status.set('参数已改变，请重新锁定')
            try:self.start_btn.configure(state='disabled')
            except Exception:pass

    def lock_pipeline(self):
        if self.reference_master is None:
            messagebox.showwarning(APP_NAME,'请先生成参考堆栈并检查处理效果。',parent=self); return
        self.pipeline_locked=True
        self.lock_status.set('已锁定 · 批量帧使用同一参数')
        self.start_btn.configure(state='normal')
        self.status.set('处理方案已锁定，可以开始批量生成')

    def generate_reference(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME,'当前正在批量生成，请先等待或取消。',parent=self); return
        if not _ewb_require_analysis(self):return
        groups=self._groups()
        if not groups:return
        i=max(1,min(len(groups),int(self.preview_index.get())))-1
        method='maximum' if self.stack_method.get().startswith('最大值') else 'mean'
        self.status.set(f'正在生成参考堆栈 {i+1}/{len(groups)}…'); self.preview_title.set('正在生成参考堆栈…')
        self.reference_master=None; self.pipeline_locked=False; self.start_btn.configure(state='disabled'); self.lock_status.set('处理方案尚未锁定')
        def work():
            try:
                ref=self._ref_lum(); master=self._stack_group(groups[i],method,ref); self.queue.put(('reference',(master,i,groups[i])))
            except Exception as e:self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()

    def preview_stage(self,stage):
        if self.reference_master is None:
            messagebox.showwarning(APP_NAME,'请先在第 1 步生成参考堆栈。',parent=self); return
        base=self.reference_proxy_hq if self.reference_proxy_hq is not None else self.reference_master
        scale=self.reference_proxy_hq_scale if self.reference_proxy_hq is not None else 1.0
        base_cfg=self._snapshot_cfg()
        current_profile=self._current_profile()
        effective_cfg=self._profile_to_cfg(base_cfg,current_profile) if current_profile is not None else base_cfg
        cfg=scale_timelapse_cfg_for_proxy(effective_cfg,scale); curves=copy.deepcopy(self.curve_snapshot)
        names={'stretch':'拉伸后','basic':'拉伸 + 调色后','background_curves':'Background + Curves 后','usm':'USM 后','highpass':'High Pass 后','emboss':'浮雕后','channel':'最终处理效果'}
        self.status.set('正在计算参考图预览：'+names.get(stage,stage)+'…')
        def work():
            try:
                out=apply_timelapse_pipeline(base,cfg,curves,stop_after=stage); self.queue.put(('stage_preview',(out,names.get(stage,stage))))
            except Exception as e:self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()

    def _choose_output(self):
        p=filedialog.askdirectory(title='选择延时输出目录',parent=self)
        if p:self.output_folder.set(p)

    def _groups(self):
        n=len(self.app.files); step=max(1,int(self.step.get() or 1)); mode=self.mode.get()
        if n<1:return []
        if mode.startswith('累计'):
            ends=list(range(1,n+1,step))
            if ends[-1]!=n:ends.append(n)
            return [list(range(0,e)) for e in ends]
        if mode.startswith('逐帧剔除'):
            if n<2:return []
            return [[j for j in range(n) if j!=i] for i in range(0,n,step)]
        w=max(1,min(n,int(self.window_size.get() or 1)))
        if mode.startswith('中心'):
            # Valid centered windows only; fixed window size avoids edge frames using fewer samples.
            starts=list(range(0,n-w+1,step))
            return [list(range(s,s+w)) for s in starts]
        starts=list(range(0,n-w+1,step))
        return [list(range(s,s+w)) for s in starts]

    def _update_summary(self):
        try:
            groups=self._groups(); count=len(groups); mode=self.mode.get(); method=self.stack_method.get(); n=len(self.app.files); w=max(1,min(n,int(self.window_size.get() or 1))) if n else 0
            if mode.startswith('滑动'):
                desc=f'推荐用于真正的冰晕变化延时。例如 100 张、窗口 15：第1帧堆 1–15，第2帧堆 2–16，第3帧堆 3–17……每次向前移动“步长”张。'
            elif mode.startswith('中心'):
                desc=f'同样使用连续的固定窗口，但把每个堆栈结果理解为“窗口中央时刻”的状态。例如 1–15 代表约第8张附近的天空状态，适合按时间中心解释。'
            elif mode.startswith('累计'):
                desc='用于展示信号逐渐累积/生长：第1帧=第1张；第2帧=1–2；第3帧=1–3……最后一帧=全部照片。它展示“堆栈越多，冰晕如何逐渐显现”，不是普通时间变化。'
            else:
                desc='贡献分析模式：每个输出都使用几乎全部照片，但依次剔除一张。例如第1帧=除第1张外全部；第2帧=除第2张外全部。适合判断单张照片对总结果的影响，不推荐作为普通变化延时。'
            self.mode_description.set(desc)
            txt=f'预计输出 {count} 帧。'
            if groups:
                g=groups[0]; txt+=f' 当前参考首组会使用 {len(g)} 张输入。'
                if len(g)<=18: txt+=f' 范围示例：{g[0]+1}–{g[-1]+1}。'
            if method.startswith('最大值') and (mode.startswith('滑动') or mode.startswith('中心') or mode.startswith('逐帧剔除')):
                txt+=' Maximum 在此模式需要更多重算，通常慢于 Mean。'
            self.summary.set(txt); self.preview_spin.configure(to=max(1,count)); self.preview_index.set(min(max(1,self.preview_index.get()),max(1,count)))
            # Window/mode changes invalidate the old reference stack.
            if self.reference_master is not None:
                self.reference_master=None; self.pipeline_locked=False; self.lock_status.set('时间窗口已改变，请重新生成参考堆栈'); self.start_btn.configure(state='disabled'); self.preview_title.set('参考堆栈已失效')
        except Exception:
            self.summary.set('请检查窗口大小和步长。')

    def _snapshot_cfg(self):
        return dict(stretch=self.p_stretch.get(),stretch_strength=self.p_stretch_strength.get(),stretch_black=self.p_stretch_black.get(),
                    basic=self.p_basic.get(),exposure=self.p_exposure.get(),contrast=self.p_contrast.get(),highlights=self.p_highlights.get(),shadows=self.p_shadows.get(),whites=self.p_whites.get(),blacks=self.p_blacks.get(),clarity=self.p_clarity.get(),dehaze=self.p_dehaze.get(),vibrance=self.p_vibrance.get(),saturation=self.p_saturation.get(),
                    background=self.p_bg.get(),bg_radius=self.p_bg_radius.get(),bg_strength=self.p_bg_strength.get(),curves=self.p_curves.get(),
                    usm=self.p_usm.get(),usm_amount=self.p_usm_amount.get(),usm_radius=self.p_usm_radius.get(),usm_threshold=self.p_usm_threshold.get(),usm_passes=max(1,min(10,int(self.p_usm_passes.get() or 1))),
                    highpass=self.p_hp.get(),hp_radius=self.p_hp_radius.get(),hp_amount=self.p_hp_amount.get(),hp_mode=self.p_hp_mode.get(),
                    emboss=self.p_emboss.get(),emboss_angle=self.p_emboss_angle.get(),emboss_height=self.p_emboss_height.get(),emboss_amount=self.p_emboss_amount.get(),emboss_style=self.p_emboss_style.get(),emboss_blend=self.p_emboss_blend.get(),emboss_opacity=self.p_emboss_opacity.get(),
                    channel=self.p_channel.get(),channel_output=self.p_channel_output.get(),channel_mono=self.p_channel_mono.get(),channel_red=self.p_channel_red.get(),channel_green=self.p_channel_green.get(),channel_blue=self.p_channel_blue.get(),channel_constant=self.p_channel_constant.get(),
                    channel_noise=self.p_channel_noise.get(),channel_noise_strength=self.p_channel_noise_strength.get(),channel_noise_radius=self.p_channel_noise_radius.get())

    def _ref_lum(self):
        if not self.normalize.get() or not self.app.files:return None
        img=read_linear_rgb(self.app.files[0]); return robust_luminance(img)

    def _decode(self,idx,ref_lum=None):
        img=read_linear_rgb(self.app.files[idx])
        img=_ewb_apply_to_frame(self,img,idx)
        if ref_lum is not None:
            lum=robust_luminance(img)
            if lum>1e-8: img=img*(ref_lum/lum)
        return img

    def _stack_group(self,indices,method,ref_lum=None):
        np,*_= _deps(); master=None
        for k,idx in enumerate(indices,1):
            if self.cancel_event.is_set(): raise InterruptedError('cancelled')
            img=self._decode(idx,ref_lum).astype(np.float32,copy=False)
            if master is None: master=img.copy()
            elif method=='maximum': np.maximum(master,img,out=master)
            else: master += (img-master)/float(k)
        return master

    def preview_selected(self):
        self.generate_reference()

    def _preview_current_scale(self):
        img=getattr(self,'last_preview_image',None)
        if img is None:return max(0.01,float(getattr(self,'preview_zoom',1.0)))
        h,w=img.shape[:2]; c=self.preview_canvas; W=max(c.winfo_width(),1); H=max(c.winfo_height(),1)
        fit=min(W/max(w,1),H/max(h,1))
        return fit if getattr(self,'preview_fit_mode',True) else max(0.01,float(getattr(self,'preview_zoom',1.0)))

    def _preview_update_zoom_text(self,scale=None):
        if not hasattr(self,'preview_zoom_text'):return
        if getattr(self,'preview_fit_mode',True):
            self.preview_zoom_text.set('Fit')
        else:
            sc=self._preview_current_scale() if scale is None else float(scale)
            self.preview_zoom_text.set(f'{sc*100:.0f}%')

    def _preview_wheel(self,e):
        try:
            direction=1 if getattr(e,'delta',0)>0 else -1
            self._preview_zoom_step(direction,getattr(e,'x',None),getattr(e,'y',None))
        except Exception:pass
        return 'break'

    def _preview_wheel_linux(self,e,direction):
        self._preview_zoom_step(direction,getattr(e,'x',None),getattr(e,'y',None));return 'break'

    def _preview_set_zoom(self,scale):
        old=self._preview_current_scale();new=max(0.05,min(20.0,float(scale)))
        self._preview_adjust_pan_for_zoom(old,new,None,None);self.preview_zoom=new;self.preview_fit_mode=False
        self._preview_update_zoom_text(new);self._preview_redraw();self.preview_canvas.focus_set();return 'break'

    def _preview_zoom_step(self,direction,x=None,y=None):
        old=self._preview_current_scale();factor=1.12 if direction>0 else 1/1.12;new=max(0.05,min(20.0,old*factor))
        if abs(new-old)<1e-9:return
        self._preview_adjust_pan_for_zoom(old,new,x,y);self.preview_zoom=new;self.preview_fit_mode=False;self._preview_update_zoom_text(new);self._preview_redraw()
        try:self.status.set(f'预览缩放：{new*100:.0f}% · Z 回到 Fit')
        except Exception:pass

    def _preview_adjust_pan_for_zoom(self,old_scale,new_scale,x=None,y=None):
        try:
            c=self.preview_canvas;cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2]
            mx=cw/2 if x is None else float(x);my=ch/2 if y is None else float(y);rx=mx-(cw/2+px);ry=my-(ch/2+py);ratio=new_scale/max(old_scale,1e-9)
            self.preview_pan=[mx-cw/2-rx*ratio,my-ch/2-ry*ratio]
        except Exception:self.preview_pan=[0.0,0.0]

    def _preview_pan_start(self,e):
        self.preview_canvas.focus_set()
        if getattr(self,'preview_fit_mode',True):self.preview_pan_anchor=None;return 'break'
        self.preview_pan_anchor=(float(e.x),float(e.y),float(self.preview_pan[0]),float(self.preview_pan[1]));return 'break'
    def _preview_pan_drag(self,e):
        if not self.preview_pan_anchor:return 'break'
        x0,y0,px0,py0=self.preview_pan_anchor
        self.preview_pan=[px0+float(e.x)-x0,py0+float(e.y)-y0]
        self._preview_move_canvas_image_fast()
        return 'break'

    def _preview_move_canvas_image_fast(self):
        """Pan fast path: move the existing Tk canvas image only.

        No PIL resize, NumPy conversion, node processing or PhotoImage rebuild is
        performed while the mouse is moving. This makes panning independent of
        source image resolution and keeps preview/output fidelity untouched.
        """
        try:
            c=self.preview_canvas; item=getattr(self,'preview_image_item',None)
            if not item:return
            W=max(c.winfo_width(),1);H=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2]
            cx=W/2+px;cy=H/2+py;c.coords(item,int(cx),int(cy))
            rect=getattr(self,'preview_display_rect',None)
            if rect:
                _,_,nw,nh=rect;self.preview_display_rect=(int(cx-nw/2),int(cy-nh/2),nw,nh)
        except Exception:pass
    def _preview_pan_end(self,e):
        self.preview_pan_anchor=None;return 'break'

    def _preview_fit(self):
        self.preview_fit_mode=True;self.preview_pan=[0.0,0.0];self._preview_update_zoom_text();self._preview_redraw();self.preview_canvas.focus_set()
        try:self.status.set('预览已回到 Fit')
        except Exception:pass
        return 'break'

    def _preview_redraw(self):
        img=getattr(self,'last_preview_image',None)
        if img is not None:self._show_preview(img)

    def _show_preview(self,img):
        try:
            np,_,Image,ImageTk,*_=_deps();c=self.preview_canvas;W=max(c.winfo_width(),200);H=max(c.winfo_height(),200);h,w=img.shape[:2];fit=min(W/max(w,1),H/max(h,1));sc=fit if getattr(self,'preview_fit_mode',True) else max(0.05,float(getattr(self,'preview_zoom',1.0)));nw=max(1,int(w*sc));nh=max(1,int(h*sc))
            src_key=(id(img),h,w)
            if getattr(self,'_preview_pil_source_key',None)!=src_key:
                self._preview_pil_source=Image.fromarray(np.round(np.clip(img,0,1)*255).astype(np.uint8),'RGB');self._preview_pil_source_key=src_key
            src=self._preview_pil_source;pil=src if (nw,nh)==(w,h) else src.resize((nw,nh),Image.Resampling.LANCZOS)
            self.preview_photo=ImageTk.PhotoImage(pil);c.delete('all');px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];cx=W/2+px;cy=H/2+py;self.preview_image_item=c.create_image(int(cx),int(cy),image=self.preview_photo,anchor='center',tags=('preview_image',));self.last_preview_image=img;self.preview_display_rect=(int(cx-nw/2),int(cy-nh/2),nw,nh);self._preview_update_zoom_text(sc);c.create_text(10,10,anchor='nw',fill='#e0e0e0',font=_ui_font(9),text=('Fit' if getattr(self,'preview_fit_mode',True) else f'{sc*100:.0f}%')+' · 滚轮缩放 · 拖拽平移 · Z Fit',tags=('preview_overlay',))
        except Exception as e:self.status.set('预览显示失败：'+str(e))

    def _iter_masters(self,groups,method,ref_lum):
        # v0.9.4.18a: traditional and node timelapse now share one optimized
        # stack engine, preventing future performance/behavior drift.
        yield from _iter_optimized_timelapse_masters(self,groups,method,ref_lum)

    def start_batch(self):
        if self.worker and self.worker.is_alive():return
        if not _ewb_require_analysis(self):return
        if self.reference_master is None:
            messagebox.showwarning(APP_NAME,'请先完成第 1 步：生成参考堆栈。',parent=self); return
        if not self.pipeline_locked:
            messagebox.showwarning(APP_NAME,'请先在参考图上确认处理效果，然后点击“锁定当前处理方案”。',parent=self); return
        groups=self._groups()
        if not groups:messagebox.showwarning(APP_NAME,'当前设置无法产生输出帧。',parent=self);return
        base=Path(self.output_folder.get()).expanduser()
        try:base.mkdir(parents=True,exist_ok=True)
        except Exception as e:messagebox.showerror(APP_NAME,'无法创建输出目录：\n'+str(e),parent=self);return
        self.cancel_event.clear(); self._last_performance_snapshot=None; self.performance_monitor_text.set('Performance：准备启动…'); self.stability_text.set('Stability：Starting'); self.start_btn.configure(state='disabled'); self.cancel_btn.configure(state='normal'); self.progress.set(0); self.processing_progress.set(0); self.writing_progress.set(0); self.output_pipeline_text.set('写入：准备启动…'); self.status.set('准备批量生成…')
        cfg=self._snapshot_cfg(); curves=copy.deepcopy(self.curve_snapshot); method='maximum' if self.stack_method.get().startswith('最大值') else 'mean'
        profiles=self._iter_enabled_export_profiles(cfg)
        if not profiles:
            self.start_btn.configure(state='normal'); self.cancel_btn.configure(state='disabled'); messagebox.showwarning(APP_NAME,'没有有效输出组。请至少启用一个输出组并选择序列或视频。',parent=self); return
        self._active_memory_policy=_timelapse_memory_policy_snapshot(self)
        settings=dict(groups=groups,cfg=cfg,curves=curves,method=method,profiles=profiles,save_seq=self.save_sequence.get(),seqfmt=self.sequence_format.get(),video=self.video_format.get(),fps=max(0.1,float(self.fps.get())),res=self.resolution.get(),cw=max(2,int(self.custom_w.get())),ch=max(2,int(self.custom_h.get())),fit=self.fit_mode.get(),base=base,save_performance_report=bool(self.performance_save_report.get()),exposure_wb_smoothing=_ewb_config_snapshot(self))
        self.worker=threading.Thread(target=self._batch_worker,args=(settings,),daemon=True); self.worker.start()

    def cancel(self):
        self.cancel_event.set(); self.status.set('正在取消…'); self.cancel_btn.configure(state='disabled')

    def _batch_worker(self,s):
        run_dir=None;outpipe=None
        try:
            stamp=time.strftime('%Y%m%d_%H%M%S'); run_dir=s['base']/f'IceHaloStack_Timelapse_{stamp}'; run_dir.mkdir(parents=True,exist_ok=True)
            ref=self._ref_lum(); total=len(s['groups'])
            ext_map={'PNG 8-bit':'.png','JPEG':'.jpg','TIFF 16-bit':'.tif','TIFF 32-bit Float':'.tif'}; seq_ext=ext_map[s['seqfmt']]
            profile_dirs=[]
            for prof in s['profiles']:
                folder_name=self._format_output_name(prof, method=s['method'], mode='timelapse')
                pdir=run_dir/folder_name;pdir.mkdir(parents=True,exist_ok=True);seq_dir=pdir/'sequence'
                if prof['save_sequence'] or prof['save_video']:seq_dir.mkdir(exist_ok=True)
                recipe=[f"名称: {prof['name']}",f"命名模板: {prof['name_template']}",f"保存序列: {prof['save_sequence']}",f"保存视频: {prof['save_video']}",f"视频格式: {prof['video_format']}",f"缩放百分比: {prof['scale_percent']}",f"只保存视频时自动删除 sequence: {prof.get('delete_sequence_after_video_only', True)}",'Async Output: ON (RAM-aware bounded queue)','Disk Cache: OFF']
                ewb=s.get('exposure_wb_smoothing',{});recipe.append('曝光/白平衡平滑: '+('ON' if (ewb.get('exposure_enabled') or ewb.get('wb_enabled')) else 'OFF'));recipe.append('曝光/白平衡平滑设置: '+json.dumps(ewb,ensure_ascii=False))
                mods=[]
                for key,label in [('stretch','拉伸'),('basic','调色'),('usm','USM / 锐化'),('background','Background / 背景'),('curves','Curves / 曲线（BGR）'),('highpass','High Pass / 高反差保留'),('emboss','Emboss / 浮雕'),('channel','Channel Mixer / 通道混合器（BR）')]:
                    if prof['cfg'].get(key):mods.append(label)
                recipe.append('流程: '+(' -> '.join(mods) if mods else '仅保存线性结果'))
                (pdir/'recipe.txt').write_text('\n'.join(recipe),encoding='utf-8')
                profile_dirs.append({'prof':prof,'root':pdir,'seq':seq_dir,'video_path':None,'folder_name':folder_name})
            total_work=max(1,total*max(1,len(profile_dirs)));done_work=0;proc_start=time.monotonic()
            pol=getattr(self,'_active_memory_policy',{}) or {};engine=_timelapse_stack_engine_name(self,s['method'])
            perf=PerformanceMonitor(self,engine,pol,'Traditional Timelapse',s.get('save_performance_report',False))
            outpipe=AsyncOutputPipeline(self,pol,self.queue,'tl_output',total_work)
            # The Tk thread/queue remains the scheduler, while pixel
            # processing crosses the UI-independent service boundary.
            processing_service=ImageProcessingService(cancellation=self.cancel_event)
            self.queue.put(('tl_status',f'堆栈引擎：{engine} · 曝光/WB平滑 {"ON" if _ewb_enabled(self) else "OFF"} · Async Output ON · Queue {outpipe.capacity} · RAM Budget {_fmt_bytes(pol.get("limit_bytes",0))} · Disk Cache OFF'))
            for i,master in enumerate(perf.wrap_masters(self._iter_masters(s['groups'],s['method'],ref)),1):
                if self.cancel_event.is_set():raise InterruptedError('cancelled')
                for bundle in profile_dirs:
                    if self.cancel_event.is_set():raise InterruptedError('cancelled')
                    prof=bundle['prof'];self.queue.put(('tl_status',f"处理输出帧 {i}/{total} · 输出组 {prof['index']} {prof['name']}…"))
                    perf.touch('node_pipeline');tn=time.monotonic();out=processing_service.process_image(master,prof['cfg'],curve_points=s['curves']);perf.add_stage('node_processing',time.monotonic()-tn);perf.inc('processed_tasks',1)
                    tp=time.monotonic()
                    if prof['save_sequence']:
                        scaled=resize_float_percent_array(out,prof['scale_percent']);perf.add_stage('output_prepare',time.monotonic()-tp)
                        outpipe.submit_array(bundle['seq']/f'frame_{i:06d}{seq_ext}',scaled,s['seqfmt'],'Balanced')
                    elif prof['save_video']:
                        pil=prepare_video_frame(out,s['res'],s['cw'],s['ch'],s['fit']);pil=resize_pil_percent(pil,prof['scale_percent']);perf.add_stage('output_prepare',time.monotonic()-tp)
                        outpipe.submit_pil_png(bundle['seq']/f'frame_{i:06d}.png',pil,compress_level=3)
                    done_work+=1;elapsed=max(1e-6,time.monotonic()-proc_start);fps=done_work/elapsed;remain=max(0,total_work-done_work);eta=(remain/fps if fps>1e-9 else None)
                    self.queue.put(('tl_processing',{'done':done_work,'total':total_work,'fps':fps,'eta':eta}))
            self.queue.put(('tl_status','处理完成，等待 Async Output Queue 写入剩余最终帧…'))
            outpipe.finish();outpipe=None
            self.queue.put(('tl_processing',{'done':total_work,'total':total_work,'fps':total_work/max(1e-6,time.monotonic()-proc_start),'eta':0.0}))
            video_paths=[];ff=None;vidflows=[b for b in profile_dirs if b['prof']['save_video']]
            for vidx,bundle in enumerate(vidflows,1):
                prof=bundle['prof']
                if self.cancel_event.is_set():raise InterruptedError('cancelled')
                if ff is None:
                    ff=get_ffmpeg_executable()
                    if not ff:raise RuntimeError('未找到 FFmpeg。请重新运行启动脚本安装 imageio-ffmpeg，或把 ffmpeg.exe 放在程序目录/系统 PATH。图像序列若已启用仍已保存。')
                self.queue.put(('tl_status',f"正在编码视频 {vidx}/{len(vidflows)} · {prof['name']}…"));fps=str(s['fps']);base_name=self._format_output_name(prof,method=s['method'],mode='timelapse');fmt=prof['video_format'];src_ext=seq_ext if prof['save_sequence'] else '.png';pattern=str(bundle['seq']/f'frame_%06d{src_ext}')
                plan=_build_ffmpeg_video_plan(ff,fmt,fps,pattern,bundle['root'],base_name,bundle['seq'])
                if plan is None:continue
                video_path=plan['video_path']
                if plan['palette_command'] is not None:
                    p1=_run_ffmpeg_command(plan['palette_command'],perf)
                    if p1.returncode!=0:raise RuntimeError('GIF palette 生成失败：\n'+(p1.stderr or '')[-2000:])
                p=_run_ffmpeg_command(plan['encode_command'],perf)
                if p.returncode!=0:raise RuntimeError('FFmpeg 编码失败：\n'+(p.stderr or '')[-3000:]+'\n\nsequence 文件夹已保留，可使用 repair_failed_video_export.bat 直接重新编码，无需重新堆栈。')
                bundle['video_path']=video_path;video_paths.append(str(video_path))
                if (not prof['save_sequence']) and bool(prof.get('delete_sequence_after_video_only',True)):shutil.rmtree(bundle['seq'],ignore_errors=True)
                self.queue.put(('tl_progress',85.0+(vidx/max(1,len(vidflows)))*15.0))
            perf.finalize('Completed',run_dir,extra={'output_groups':len(profile_dirs),'frames_per_group':total})
            self.queue.put(('tl_done_multi',(str(run_dir),video_paths,total,[b['folder_name'] for b in profile_dirs])))
        except InterruptedError:
            if outpipe is not None:
                try:outpipe.cancel()
                except Exception:pass
            try:
                perf.finalize('Cancelled',run_dir) if 'perf' in locals() else setattr(self,'_active_memory_policy',None)
            except Exception:pass
            self.queue.put(('tl_cancelled',str(run_dir) if run_dir else ''))
        except Exception as e:
            if outpipe is not None:
                try:outpipe.cancel()
                except Exception:pass
            try:
                perf.finalize('Failed',run_dir,error=str(e)) if 'perf' in locals() else setattr(self,'_active_memory_policy',None)
            except Exception:pass
            self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=4)))

    def _poll(self):
        try:
            while True:
                kind,val=self.queue.get_nowait()
                if kind=='reference':
                    master,idx,group=val; self.reference_master=master; self.reference_index=idx; self.reference_group=list(group)
                    try:
                        strength,black=estimate_asinh_params(master); self.p_stretch_strength.set(round(float(strength),4)); self.p_stretch_black.set(round(float(black),6))
                    except Exception:pass
                    # Linear masters are too dark for a useful visual check; Auto Stretch here is display-only.
                    try:
                        disp=apply_asinh_stretch(master,self.p_stretch_strength.get(),self.p_stretch_black.get())
                    except Exception:disp=master
                    self.reference_proxy_drag,self.reference_proxy_drag_scale=make_float_preview_proxy(master,640)
                    self.reference_proxy_fast,self.reference_proxy_fast_scale=make_float_preview_proxy(master,1000)
                    self.reference_proxy_hq,self.reference_proxy_hq_scale=make_float_preview_proxy(master,1800)
                    self._invalidate_tl_curve_hist()
                    self._show_preview(disp); self.preview_title.set(f'参考堆栈 #{idx+1} · 输入 {group[0]+1}–{group[-1]+1} · Auto Stretch 仅用于显示')
                    self.status.set('参考堆栈完成。现在在第 2 步逐段调参数并预览。'); self.pipeline_locked=False; self.lock_status.set('处理方案尚未锁定'); self.start_btn.configure(state='disabled')
                    self._draw_tl_curve_editor(); self._schedule_live_preview(force=True)
                elif kind=='stage_preview':
                    img,name=val; self._show_preview(img); self.preview_title.set(name); self.status.set('参考图预览完成：'+name)
                elif kind=='stage_preview_live':
                    token,img,name=val
                    self._live_preview_running=False
                    if token == self._live_preview_token:
                        self._show_preview(img); self.preview_title.set(name); self.status.set('实时预览已更新')
                    if self._live_preview_pending:
                        self._live_preview_pending=False
                        self._schedule_live_preview(force=True)
                elif kind=='preview':self._show_preview(val); self.status.set('预览完成')
                elif kind=='tl_status':self.status.set(val)
                elif kind=='tl_processing':
                    d=val;tot=max(1,int(d.get('total',1)));done=int(d.get('done',0));self.processing_progress.set(min(100.0,done/tot*100.0));eta=d.get('eta');etxt=_format_seconds_short(eta) if eta is not None else '—';self.output_pipeline_text.set(f'Processing：{done}/{tot} · {float(d.get("fps",0.0)):.2f} fps · ETA {etxt}')
                elif kind=='tl_output':
                    d=val;tot=max(1,int(d.get('total',1)));done=int(d.get('completed',0));self.writing_progress.set(min(100.0,done/tot*100.0));self.progress.set(min(85.0,done/tot*85.0));eta=d.get('eta');etxt=_format_seconds_short(eta) if eta is not None else '—';wf=float(d.get('recent_writer_fps') or d.get('writer_fps') or 0.0);state='等待处理' if d.get('writer_idle') else f'Writer {wf:.2f} fps';self.output_pipeline_text.set(f'写入：{done}/{tot} · 队列 {d.get("queued",0)}/{d.get("capacity",0)} · {state} · 总 ETA {etxt}')
                elif kind=='tl_progress':self.progress.set(val)
                elif kind=='tl_done':
                    run,video,count=val; self.start_btn.configure(state='normal'); self.cancel_btn.configure(state='disabled'); self.progress.set(100); self.processing_progress.set(100); self.writing_progress.set(100); self.output_pipeline_text.set('写入：完成'); self.status.set(f'完成 · {count} 帧 · {run}')
                    msg=f'堆栈延时生成完成。\n\n输出帧：{count}\n目录：\n{run}'
                    if video:msg+=f'\n\n视频：\n{video}'
                    messagebox.showinfo(APP_NAME,msg,parent=self)
                elif kind=='tl_done_multi':
                    run,videos,count,names=val;self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.progress.set(100);self.processing_progress.set(100);self.writing_progress.set(100);self.output_pipeline_text.set('写入：完成');self.status.set(f'完成 · {len(names)} 个输出组 × {count} 帧 · {run}')
                    msg=f'堆栈延时生成完成。\n\n输出组：{len(names)}\n每组帧数：{count}\n目录：\n{run}'
                    if videos:msg+='\n\n视频：\n'+'\n'.join(videos)
                    messagebox.showinfo(APP_NAME,msg,parent=self)
                elif kind=='tl_cancelled':
                    self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.status.set('已取消');self.output_pipeline_text.set('写入：已取消')
                    messagebox.showinfo(APP_NAME,'批量生成已取消。\n已完成的最终文件不会删除；未写入的队列帧已释放。',parent=self)
                elif kind=='error':
                    self._live_preview_running=False;self._live_preview_pending=False;self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.status.set('处理失败');self.output_pipeline_text.set('写入：失败/已停止');messagebox.showerror(APP_NAME,val,parent=self)
        except Empty:pass
        if self.winfo_exists():self.after(80,self._poll)

