from __future__ import annotations
import os, sys, threading, traceback, math, copy, time, subprocess, re, json, shutil, tempfile, gc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue, Empty, Full
from collections import OrderedDict, Counter, deque

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ihs.constants import APP_NAME, VERSION, RAW_EXTS, RASTER_EXTS, ALL_EXTS
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
    resize_float_percent_array,
    save_timelapse_sequence_frame_scaled, _atomic_temp_path,
    _atomic_replace_with_retry, save_timelapse_sequence_frame_atomic,
    save_pil_png_atomic, prepare_video_frame, make_float_preview_proxy,
)
from ihs.performance import (
    _GIB, _MIB, _fmt_bytes, _format_seconds_short, _system_memory_status,
    _process_memory_rss, _auto_ram_limit_bytes,
    _timelapse_memory_policy_snapshot, _manual_ram_bounds_gb,
    PerformanceMonitor, _format_performance_snapshot,
)
from ihs.stack_engine import (
    RAMFrameCache, _next_window_incoming,
    _iter_optimized_timelapse_masters, _timelapse_stack_engine_name,
    robust_luminance,
)
from ihs.output_pipeline import (
    AsyncOutputPipeline, _build_ffmpeg_video_plan, _run_ffmpeg_command,
)
from ihs.node_workflow import (
    NODE_ORDER as _NODE_WORKFLOW_ORDER,
    default_edges as _node_default_edges,
    normalize_flow as _normalize_node_flow,
    node_enabled as _node_flow_enabled,
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
)
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

# Typography policy: every application-controlled text element uses REGULAR weight.
# The user can select the UI family from Settings.  No font files are bundled;
# IceHaloStack only uses fonts already installed on the operating system.
from ihs.ui import appearance as _appearance
from ihs.ui.appearance import (
    FONT_CHOICES, LANGUAGE_CHOICES, THEME_CHOICES, THEME_PALETTES,
    _apply_ui_font_preference, _apply_ui_language, _apply_ui_theme,
    _configure_tk_high_dpi, _enforce_regular_typography,
    _install_combobox_selection_behavior, _make_vertical_scroll_area,
    _mousewheel_steps, _tr, _translate_flow_list_item, _translate_text, _ui_font,
)


def __getattr__(name):
    """Preserve legacy access to appearance state through the entry module."""
    try:return getattr(_appearance,name)
    except AttributeError:raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


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
    _ewb_make_thumbnail, _ewb_measurement_signature_for,
    _ewb_open_workspace, _ewb_rebuild_table, _ewb_require_analysis,
    _ewb_settings_dialog, _ewb_show_curves, _ewb_signature,
    _ewb_table_summary, _ewb_workspace_close, _init_ewb_vars,
    read_analysis_proxy,
)
from ihs.ui.appearance import AngleDial
from ihs.node_workflow import apply_timelapse_pipeline, scale_timelapse_cfg_for_proxy


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
            self.queue.put(('tl_status',f'堆栈引擎：{engine} · 曝光/WB平滑 {"ON" if _ewb_enabled(self) else "OFF"} · Async Output ON · Queue {outpipe.capacity} · RAM Budget {_fmt_bytes(pol.get("limit_bytes",0))} · Disk Cache OFF'))
            for i,master in enumerate(perf.wrap_masters(self._iter_masters(s['groups'],s['method'],ref)),1):
                if self.cancel_event.is_set():raise InterruptedError('cancelled')
                for bundle in profile_dirs:
                    if self.cancel_event.is_set():raise InterruptedError('cancelled')
                    prof=bundle['prof'];self.queue.put(('tl_status',f"处理输出帧 {i}/{total} · 输出组 {prof['index']} {prof['name']}…"))
                    perf.touch('node_pipeline');tn=time.monotonic();out=apply_timelapse_pipeline(master,prof['cfg'],s['curves']);perf.add_stage('node_processing',time.monotonic()-tn);perf.inc('processed_tasks',1)
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



from ihs.ui import node_window as _node_window_ui

LocalNodeEditorHistory = _node_window_ui.LocalNodeEditorHistory
FlowCurveDialog = _node_window_ui.FlowCurveDialog
BaseCurveDialog = _node_window_ui.BaseCurveDialog
StandaloneHPCurveDialog = _node_window_ui.StandaloneHPCurveDialog
TimelapseNodeWindow = _node_window_ui.TimelapseNodeWindow


from ihs.ui.storage_window import StorageManagerDialog


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.display_dpi=_configure_tk_high_dpi(self)
        self.title(f'{APP_NAME} {VERSION}')
        self.geometry('1460x860')
        self.minsize(1100,700)
        self.files=[]; self.queue=Queue(); self.worker=None
        self.stack_pause_event=threading.Event(); self.stack_stop_event=threading.Event(); self.stack_lock=threading.Lock()
        self.stack_running_mean=None; self.stack_count=0; self.stack_total=0; self.stack_out=None; self.stack_depth=None
        self.stack_preview_image=None; self.stack_active=False; self.stack_paused=False
        self.linear_master=None; self.working_image=None
        self.is_linear=True; self.image_path=None
        self.undo_stack=[]; self.redo_stack=[]; self.max_undo=8
        self.preview_photo=None
        self.auto_preview_var=tk.BooleanVar(value=True)
        self.normalize_var=tk.BooleanVar(value=False)
        self.stack_method=tk.StringVar(value='平均值 Mean')
        self.stack_range_start=tk.IntVar(value=1)
        self.stack_range_end=tk.IntVar(value=1)
        self.stack_range_info=tk.StringVar(value='当前堆栈区间：1 - 1（0 帧）')
        self.suggested_stretch_strength=8.0
        self.suggested_stretch_black=0.0
        self._var_trace_suspend=False
        self._last_channel_mono_state=False
        self.curve_points = {}
        self.curve_selected_idx = None
        self.hp_curve_points = {k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']}
        self._slider_dragging=False
        self._preview_after_id=None
        self._last_preview_request=0.0
        self._preview_generation=0
        self._last_display_preview=None
        # Main Base preview is computed off the Tk thread. Only the newest request
        # is allowed to render; stale slider-drag frames are discarded.
        self._main_preview_request_serial=0
        self._main_async_preview_running=False
        self._main_async_preview_pending=False
        self._main_async_preview_quality='drag'
        self.output_depth=tk.StringVar(value='32-bit float TIFF')
        self.status=tk.StringVar(value='等待导入冰晕延时序列')
        self.detail=tk.StringVar(value='LINEAR · 尚未生成 Master')
        self.progress=tk.DoubleVar(value=0)
        self.zoom=tk.DoubleVar(value=1.0)
        self.live_preview_var=tk.BooleanVar(value=True)
        self.preview_every=tk.IntVar(value=1)
        self.stack_counter_text=tk.StringVar(value='0 / 0 帧')
        self.compute_backend=tk.StringVar(value='自动')
        self.raw_workers=tk.IntVar(value=2)
        self.accel_status=tk.StringVar(value='尚未检测加速后端')
        self.ui_font_choice=tk.StringVar(value=_appearance.UI_FONT_PREFERENCE)
        self.ui_theme_choice=tk.StringVar(value=_appearance.UI_THEME_PREFERENCE)
        self.ui_language_choice=tk.StringVar(value=_appearance.UI_LANGUAGE)
        self._style(); self._menu(); self._ui(); _enforce_regular_typography(self); self.after_idle(lambda: _enforce_regular_typography(self)); self._install_global_mousewheel();_install_combobox_selection_behavior(self); self._setup_var_traces(); self.after(100,self._poll)
        self._ui_pref_map_after=None;self._ui_pref_map_targets=[];self.bind_all('<Map>',self._ui_preferences_mapped,add='+')
        self.after(250, self.detect_acceleration)

    def _install_global_mousewheel(self):
        """Route the wheel to the scrollable area under the pointer.

        Registered scroll pages use ``_ihs_scroll_target``. Native list/text
        widgets keep their own scrolling. Parameter controls use the surrounding
        page instead of consuming the wheel, so a small screen can always reach
        Apply / Export buttons without accidentally changing a value.
        """
        self.bind_all('<MouseWheel>', self._global_mousewheel, add='+')
        self.bind_all('<Button-4>', lambda e:self._global_mousewheel(e,1), add='+')
        self.bind_all('<Button-5>', lambda e:self._global_mousewheel(e,-1), add='+')
        # On Windows some themed controls may otherwise consume the wheel before
        # the application-wide handler sees it. Override only their wheel class
        # binding; keyboard/mouse-drag behavior remains unchanged.
        for cls in ('TScale','Scale','TEntry','Entry','TSpinbox','Spinbox','TCombobox'):
            try:
                self.bind_class(cls,'<MouseWheel>',self._global_mousewheel)
            except Exception:
                pass

    def _ui_preferences_mapped(self,event=None):
        # Combobox pop-downs and each child widget also emit <Map>.  Refreshing
        # the entire application for those events used to close/rebuild the
        # pop-down before its selection could commit and made every node dialog
        # appear to load slowly.  Only initialize a genuinely new top-level.
        if _appearance._I18N_APPLYING:return
        target=getattr(event,'widget',None)
        if target is not self and not isinstance(target,tk.Toplevel):return
        try:
            if not target.winfo_exists():return
            if target not in self._ui_pref_map_targets:self._ui_pref_map_targets.append(target)
        except Exception:return
        if getattr(self,'_ui_pref_map_after',None) is not None:return
        try:self._ui_pref_map_after=self.after_idle(self._refresh_open_ui_preferences)
        except Exception:pass

    def _refresh_open_ui_preferences(self):
        self._ui_pref_map_after=None;targets=list(getattr(self,'_ui_pref_map_targets',[]) or []);self._ui_pref_map_targets=[]
        for target in targets:
            try:
                if target.winfo_exists():_enforce_regular_typography(target)
            except Exception:pass

    def _global_mousewheel(self,event,linux_direction=None):
        w=getattr(event,'widget',None)
        if w is None:return None
        # List/Text/Tree widgets are already proper scroll containers. Let their
        # native class bindings handle the wheel instead of scrolling the page.
        if isinstance(w,(tk.Listbox,tk.Text,ttk.Treeview)):
            return None
        # Node canvas has a dedicated wheel handler (normal scroll, Ctrl zoom).
        tw=w
        while tw is not None:
            if isinstance(tw,tk.Canvas) and getattr(tw,'_ihs_node_canvas',False):
                return None
            target=getattr(tw,'_ihs_scroll_target',None)
            if target is not None:
                try:
                    steps=_mousewheel_steps(event,linux_direction)
                    if steps:
                        target.yview_scroll(steps,'units')
                    return 'break'
                except Exception:
                    return None
            try:
                tw=tw.master
            except Exception:
                break
        return None

    def _style(self):
        _apply_ui_theme(self,_appearance.UI_THEME_PREFERENCE,persist=False);s=ttk.Style(self)
        # Global regular-weight policy. Every text-bearing ttk class receives an
        # explicit regular font so native theme defaults cannot introduce a heavier
        # heading/caption/button weight.
        regular9=_ui_font(9)
        for sty in ('TLabel','TButton','TCheckbutton','TRadiobutton','TMenubutton',
                    'TEntry','TSpinbox','TCombobox','TNotebook.Tab','TLabelframe.Label',
                    'Treeview','Treeview.Heading','Toolbutton'):
            try: s.configure(sty, font=regular9)
            except Exception: pass
        s.configure('Title.TLabel', font=_ui_font(16))
        s.configure('Sub.TLabel', font=_ui_font(9), foreground=THEME_PALETTES[_appearance.UI_THEME_PREFERENCE]['muted'])
        s.configure('Primary.TButton', font=_ui_font(10), padding=(16,8))
        s.configure('Stage.TLabel',font=_ui_font(9))
        # Native vector fonts + Per-Monitor-V2 DPI awareness keep labels/canvas text
        # crisp instead of letting Windows bitmap-scale the whole Tk application.

    def _menu(self):
        bar=tk.Menu(self)
        f=tk.Menu(bar, tearoff=0)
        f.add_command(label='添加图片 / RAW...', command=self.add_files, accelerator='Ctrl+O')
        f.add_command(label='添加文件夹...', command=self.add_folder)
        f.add_command(label='打开单张 TIFF / 图片进入编辑...', command=self.open_image)
        f.add_separator(); f.add_command(label='保存当前图像...', command=self.export_current, accelerator='Ctrl+S')
        f.add_separator(); f.add_command(label='清空工程', command=self.clear_files)
        f.add_command(label='退出', command=self.destroy)
        bar.add_cascade(label='文件', menu=f)

        e=tk.Menu(bar, tearoff=0)
        e.add_command(label='撤销', command=self.undo, accelerator='Ctrl+Z')
        e.add_command(label='重做', command=self.redo, accelerator='Ctrl+Y')
        e.add_separator(); e.add_command(label='全选帧', command=self.select_all, accelerator='Ctrl+A')
        e.add_command(label='移除所选帧', command=self.remove_selected, accelerator='Delete')
        bar.add_cascade(label='编辑', menu=e)

        st=tk.Menu(bar, tearoff=0)
        st.add_command(label='开始线性堆栈', command=self.start_stack, accelerator='Ctrl+Enter')
        st.add_command(label='暂停 / 继续', command=self.toggle_stack_pause, accelerator='Space')
        st.add_command(label='使用当前结果并停止', command=self.use_current_stack)
        st.add_command(label='取消堆栈', command=self.cancel_stack)
        bar.add_cascade(label='堆栈', menu=st)

        tl=tk.Menu(bar, tearoff=0)
        tl.add_command(label='打开堆栈延时...', command=self.open_timelapse)
        bar.add_cascade(label='延时', menu=tl)

        lin=tk.Menu(bar, tearoff=0)
        lin.add_checkbutton(label='Auto Stretch 预览（不修改数据）', variable=self.auto_preview_var, command=self.refresh_preview)
        lin.add_command(label='Asinh 拉伸 → 非线性...', command=lambda:self.tabs.select(self.tab_stretch))
        bar.add_cascade(label='线性处理', menu=lin)

        adj=tk.Menu(bar, tearoff=0)
        adj.add_command(label='基础调整 / Camera Raw 风格', command=lambda:self.tabs.select(self.tab_basic))
        adj.add_command(label='通道混合器', command=lambda:self.tabs.select(self.tab_channel))
        bar.add_cascade(label='调整', menu=adj)

        fil=tk.Menu(bar, tearoff=0)
        fil.add_command(label='USM 锐化', command=lambda:self.tabs.select(self.tab_detail))
        fil.add_command(label='高反差保留', command=lambda:self.tabs.select(self.tab_detail))
        fil.add_command(label='浮雕', command=lambda:self.tabs.select(self.tab_detail))
        fil.add_command(label='曲线 / 对比度', command=lambda:self.tabs.select(self.tab_curves))
        bar.add_cascade(label='滤镜', menu=fil)

        view=tk.Menu(bar, tearoff=0)
        view.add_checkbutton(label='Auto Stretch 预览', variable=self.auto_preview_var, command=self.refresh_preview)
        view.add_command(label='适合窗口', command=self.refresh_preview)
        bar.add_cascade(label='视图', menu=view)

        settings=tk.Menu(bar,tearoff=0)
        font_menu=tk.Menu(settings,tearoff=0)
        for key,label in FONT_CHOICES.items():
            font_menu.add_radiobutton(label=label,variable=self.ui_font_choice,value=key,command=self._change_ui_font)
        settings.add_cascade(label='界面字体',menu=font_menu)
        theme_menu=tk.Menu(settings,tearoff=0)
        for key,label in THEME_CHOICES.items():theme_menu.add_radiobutton(label=label,variable=self.ui_theme_choice,value=key,command=self._change_ui_theme)
        settings.add_cascade(label='界面主题',menu=theme_menu)
        language_menu=tk.Menu(settings,tearoff=0)
        for key,label in LANGUAGE_CHOICES.items():language_menu.add_radiobutton(label=label,variable=self.ui_language_choice,value=key,command=self._change_ui_language)
        settings.add_cascade(label='界面语言',menu=language_menu)
        settings.add_separator();settings.add_command(label='界面设置...',command=self.open_interface_settings)
        bar.add_cascade(label='设置',menu=settings)

        h=tk.Menu(bar, tearoff=0)
        h.add_command(label='单独堆栈与性能说明...', command=self.show_single_stack_help)
        h.add_command(label='存储与缓存管理...', command=self.open_storage_manager)
        h.add_separator()
        h.add_command(label='关于 IceHaloStack', command=self.about)
        bar.add_cascade(label='帮助', menu=h)
        self.config(menu=bar)
        self.bind_all('<Control-o>', lambda e:self.add_files())
        self.bind_all('<Control-s>', lambda e:self.export_current())
        self.bind_all('<Control-a>', self._handle_ctrl_a)
        self.bind_all('<Delete>', lambda e:self.remove_selected())
        self.bind_all('<Control-Return>', lambda e:self.start_stack())
        self.bind_all('<Control-z>', lambda e:self.undo())
        self.bind_all('<Control-y>', lambda e:self.redo())
        self.bind_all('<space>', lambda e:self.toggle_stack_pause() if self.stack_active else None)

    def _change_ui_font(self):
        key=str(self.ui_font_choice.get() or 'system')
        previous=_appearance.UI_FONT_PREFERENCE
        ok,family=_apply_ui_font_preference(self,key,persist=True)
        if not ok:
            self.ui_font_choice.set(previous)
            label=FONT_CHOICES.get(key,key)
            messagebox.showinfo(APP_NAME,f'当前系统未检测到“{label}”。\n\n已保持当前字体，不会下载安装任何字体文件。',parent=self)
            return
        # Apply once more after idle so newly redrawn Canvas labels and native ttk
        # theme elements inherit the same family and regular weight.
        self.after_idle(lambda:_apply_ui_font_preference(self,key,persist=False))
        try:self.status.set(f'界面字体：{FONT_CHOICES.get(key,key)}')
        except Exception:pass

    def _change_ui_theme(self):
        key=str(self.ui_theme_choice.get() or 'light');_apply_ui_theme(self,key,persist=True);_enforce_regular_typography(self)
        try:self.status.set(_tr('界面主题')+': '+_tr(THEME_CHOICES.get(key,key)))
        except Exception:pass

    def _change_ui_language(self):
        key=str(self.ui_language_choice.get() or 'zh_CN');_apply_ui_language(self,key,persist=True);_enforce_regular_typography(self)
        try:self.status.set('Language: '+LANGUAGE_CHOICES.get(key,key) if key=='en' else '界面语言：中文')
        except Exception:pass

    def open_interface_settings(self):
        existing=getattr(self,'_interface_settings_window',None)
        try:
            if existing is not None and existing.winfo_exists():existing.lift();existing.focus_force();return
        except Exception:pass
        d=tk.Toplevel(self);self._interface_settings_window=d;d.title('界面设置');d.geometry('430x410');d.minsize(390,360);d.transient(self)
        def close():
            self._interface_settings_window=None
            try:d.destroy()
            except Exception:pass
        d.protocol('WM_DELETE_WINDOW',close);body=ttk.Frame(d,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='更改会立即应用到所有已打开窗口。',style='Sub.TLabel').pack(anchor='w',pady=(0,12))
        appearance=ttk.LabelFrame(body,text='外观',padding=10);appearance.pack(fill='x')
        for key,label in THEME_CHOICES.items():ttk.Radiobutton(appearance,text=label,variable=self.ui_theme_choice,value=key,command=self._change_ui_theme).pack(side='left',padx=(0,18))
        language=ttk.LabelFrame(body,text='语言',padding=10);language.pack(fill='x',pady=(10,0))
        for key,label in LANGUAGE_CHOICES.items():ttk.Radiobutton(language,text=label,variable=self.ui_language_choice,value=key,command=self._change_ui_language).pack(side='left',padx=(0,18))
        font=ttk.LabelFrame(body,text='字体',padding=10);font.pack(fill='x',pady=(10,0))
        for key,label in FONT_CHOICES.items():ttk.Radiobutton(font,text=label,variable=self.ui_font_choice,value=key,command=self._change_ui_font).pack(anchor='w',pady=2)
        ttk.Button(body,text='关闭设置',command=close).pack(side='bottom',anchor='e',pady=(14,0));_enforce_regular_typography(d)

    def _ui(self):
        root=ttk.Frame(self,padding=(10,8)); root.pack(fill='both',expand=True)
        head=ttk.Frame(root); head.pack(fill='x')
        ttk.Label(head,text='IceHaloStack',style='Title.TLabel').pack(side='left')
        ttk.Label(head,text='冰晕 RAW · 堆栈 · 处理',style='Sub.TLabel').pack(side='left',padx=(10,0),pady=(6,0))
        ttk.Label(head,text=f'v{VERSION}',style='Sub.TLabel').pack(side='right',pady=(6,0))
        ttk.Separator(root).pack(fill='x',pady=(7,7))

        toolbar=ttk.Frame(root); toolbar.pack(fill='x',pady=(0,6))
        ttk.Button(toolbar,text='＋ RAW / 图片',command=self.add_files).pack(side='left')
        ttk.Button(toolbar,text='＋ 文件夹',command=self.add_folder).pack(side='left',padx=4)
        ttk.Button(toolbar,text='▶ 开始堆栈',command=self.start_stack).pack(side='left',padx=(8,4))
        ttk.Button(toolbar,text='🎞 堆栈延时',command=self.open_timelapse).pack(side='left',padx=(0,4))
        self.toolbar_pause_btn=ttk.Button(toolbar,text='⏸ 暂停',command=self.toggle_stack_pause,state='disabled'); self.toolbar_pause_btn.pack(side='left',padx=2)
        self.toolbar_use_btn=ttk.Button(toolbar,text='✓ 使用当前',command=self.use_current_stack,state='disabled'); self.toolbar_use_btn.pack(side='left',padx=2)
        ttk.Separator(toolbar,orient='vertical').pack(side='left',fill='y',padx=6)
        ttk.Checkbutton(toolbar,text='Auto Stretch 预览',variable=self.auto_preview_var,command=self.refresh_preview).pack(side='left')
        ttk.Button(toolbar,text='↶ 撤销',command=self.undo).pack(side='left',padx=(10,3))
        ttk.Button(toolbar,text='↷ 重做',command=self.redo).pack(side='left')
        ttk.Button(toolbar,text='导出',command=self.export_current).pack(side='right')

        body=ttk.Panedwindow(root,orient='horizontal'); body.pack(fill='both',expand=True)
        left=ttk.Frame(body,width=260); center=ttk.Frame(body); right=ttk.Frame(body,width=340)
        body.add(left,weight=1); body.add(center,weight=5); body.add(right,weight=2)

        # Frames panel
        lf=ttk.LabelFrame(left,text='Frames',padding=5); lf.pack(fill='both',expand=True,padx=(0,6))
        self.listbox=tk.Listbox(lf,selectmode=tk.EXTENDED,font=_ui_font(9),activestyle='none')
        sy=ttk.Scrollbar(lf,orient='vertical',command=self.listbox.yview); self.listbox.configure(yscrollcommand=sy.set)
        self.listbox.pack(side='left',fill='both',expand=True); sy.pack(side='right',fill='y')
        lbar=ttk.Frame(left); lbar.pack(fill='x',padx=(0,6),pady=(5,0))
        self.count=ttk.Label(lbar,text='0 帧'); self.count.pack(side='left')
        ttk.Button(lbar,text='移除',command=self.remove_selected).pack(side='right')

        # Center preview
        preview_box=ttk.LabelFrame(center,text='图像预览',padding=3); preview_box.pack(fill='both',expand=True,padx=(0,6))
        phead=ttk.Frame(preview_box);phead.pack(fill='x',pady=(0,3))
        ttk.Label(phead,text='预览导航').pack(side='left')
        self.preview_zoom_text=tk.StringVar(value='Fit')
        pzoom=ttk.Frame(phead);pzoom.pack(side='right')
        for label,value in [('25%',0.25),('50%',0.50),('100%',1.0),('200%',2.0)]:
            ttk.Button(pzoom,text=label,width=5,command=lambda v=value:self._main_preview_set_zoom(v)).pack(side='left',padx=1)
        ttk.Button(pzoom,text='Fit',width=5,command=self._main_preview_fit).pack(side='left',padx=(2,0))
        ttk.Label(pzoom,textvariable=self.preview_zoom_text,width=10,anchor='e').pack(side='left',padx=(5,0))
        self.preview_canvas=tk.Canvas(preview_box,bg='#171717',highlightthickness=0)
        self.preview_canvas.pack(fill='both',expand=True)
        self.preview_zoom=1.0; self.preview_fit_mode=True; self.preview_pan=[0.0,0.0]; self.preview_pan_anchor=None
        self.preview_canvas.bind('<Configure>',lambda e:self._main_preview_redraw())
        self.preview_canvas.bind('<MouseWheel>',self._main_preview_wheel)
        self.preview_canvas.bind('<Button-4>',lambda e:self._main_preview_wheel_linux(e,1))
        self.preview_canvas.bind('<Button-5>',lambda e:self._main_preview_wheel_linux(e,-1))
        self.preview_canvas.bind('<ButtonPress-1>',self._main_preview_pan_start)
        self.preview_canvas.bind('<B1-Motion>',self._main_preview_pan_drag)
        self.preview_canvas.bind('<ButtonRelease-1>',self._main_preview_pan_end)
        self.preview_canvas.bind('z',lambda e:self._main_preview_fit())
        self.preview_canvas.bind('Z',lambda e:self._main_preview_fit())
        self.preview_canvas.create_text(20,20,anchor='nw',fill='#aaaaaa',font=_ui_font(11),text='堆栈完成后将在这里显示图像。',tags='placeholder')

        hist_box=ttk.LabelFrame(center,text='Histogram',padding=2); hist_box.pack(fill='x',padx=(0,6),pady=(6,0))
        self.hist_canvas=tk.Canvas(hist_box,height=92,bg='#101010',highlightthickness=0)
        self.hist_canvas.pack(fill='x')
        self.hist_canvas.bind('<Configure>',lambda e:self.draw_histogram())

        # Right edit tabs
        self.tabs=ttk.Notebook(right); self.tabs.pack(fill='both',expand=True); self.tabs.bind('<<NotebookTabChanged>>', lambda e:self.refresh_preview())
        self.tab_stack=ttk.Frame(self.tabs)
        self.tab_stretch=ttk.Frame(self.tabs)
        self.tab_basic=ttk.Frame(self.tabs)
        self.tab_channel=ttk.Frame(self.tabs)
        self.tab_curves=ttk.Frame(self.tabs)
        self.tab_detail=ttk.Frame(self.tabs)
        self.tabs.add(self.tab_stack,text='堆栈')
        self.tabs.add(self.tab_stretch,text='拉伸')
        self.tabs.add(self.tab_basic,text='基础')
        self.tabs.add(self.tab_detail,text='细节')
        self.tabs.add(self.tab_channel,text='通道')
        self.tabs.add(self.tab_curves,text='曲线')
        self._build_stack_tab(); self._build_stretch_tab(); self._build_basic_tab(); self._build_detail_tab(); self._build_channel_tab(); self._build_curves_tab()

        bottom=ttk.Frame(root); bottom.pack(fill='x',pady=(7,0))
        self.pb=ttk.Progressbar(bottom,variable=self.progress,maximum=100); self.pb.pack(side='left',fill='x',expand=True,padx=(0,10))
        ttk.Label(bottom,textvariable=self.status).pack(side='left',padx=(0,12))
        ttk.Label(bottom,textvariable=self.detail,style='Stage.TLabel').pack(side='right')

    def _scrollable_tab_body(self, outer):
        body=getattr(outer,'_ihs_scroll_body',None)
        if body is not None:
            return body
        body,canvas,shell=_make_vertical_scroll_area(outer,padding=10)
        outer._ihs_scroll_body=body
        outer._ihs_scroll_canvas=canvas
        return body

    def _build_stack_tab(self):
        t=self._scrollable_tab_body(self.tab_stack)
        ttk.Label(t,text='固定三脚架',font=_ui_font(11)).pack(anchor='w')
        ttk.Label(t,text='不进行几何对齐；适用于固定机位冰晕延时。',wraplength=280).pack(anchor='w',pady=(2,10))
        ttk.Label(t,text='组合方式').pack(anchor='w')
        ttk.Combobox(t,textvariable=self.stack_method,state='readonly',values=['平均值 Mean','最大值 Maximum']).pack(fill='x',pady=(4,8))
        ttk.Label(t,text='Mean：逐帧平均，适合降低随机噪声；Maximum：逐像素逐通道保留所有帧中的最大值。',style='Sub.TLabel',wraplength=280).pack(anchor='w',pady=(0,8))
        ttk.Separator(t).pack(fill='x',pady=8)
        ttk.Label(t,text='快速堆栈区间',font=_ui_font(10)).pack(anchor='w')
        ttk.Label(t,text='你可以只堆栈序列中的某一段，例如 1–50、50–100，而不是一次性把全部帧都堆完。',style='Sub.TLabel',wraplength=280).pack(anchor='w',pady=(2,6))
        rg=ttk.Frame(t); rg.pack(fill='x',pady=(0,4))
        ttk.Label(rg,text='起始帧').grid(row=0,column=0,sticky='w')
        ttk.Entry(rg,textvariable=self.stack_range_start,width=8,justify='right').grid(row=0,column=1,sticky='e',padx=(4,10))
        ttk.Label(rg,text='结束帧').grid(row=0,column=2,sticky='w')
        ttk.Entry(rg,textvariable=self.stack_range_end,width=8,justify='right').grid(row=0,column=3,sticky='e',padx=(4,0))
        ttk.Button(t,text='使用当前选中范围',command=self.use_selected_as_stack_range).pack(fill='x',pady=(2,4))
        ttk.Label(t,textvariable=self.stack_range_info,style='Stage.TLabel',wraplength=280).pack(anchor='w',pady=(0,6))
        ttk.Checkbutton(t,text='自动曝光归一化（实验性）',variable=self.normalize_var).pack(anchor='w')
        ttk.Separator(t).pack(fill='x',pady=12)
        ttk.Label(t,text='Master 输出').pack(anchor='w')
        ttk.Combobox(t,textvariable=self.output_depth,state='readonly',values=['16-bit TIFF','32-bit float TIFF']).pack(fill='x',pady=(4,10))
        self.start_stack_btn=ttk.Button(t,text='开始堆栈',style='Primary.TButton',command=self.start_stack); self.start_stack_btn.pack(fill='x')
        ttk.Separator(t).pack(fill='x',pady=12)
        ttk.Label(t,text='性能加速',font=_ui_font(10)).pack(anchor='w')
        perf=ttk.Frame(t); perf.pack(fill='x',pady=(5,2))
        ttk.Label(perf,text='计算后端').pack(side='left')
        ttk.Combobox(perf,textvariable=self.compute_backend,state='readonly',width=16,values=['自动','CPU','NVIDIA CUDA']).pack(side='right')
        perf2=ttk.Frame(t); perf2.pack(fill='x',pady=2)
        ttk.Label(perf2,text='RAW 并行解码').pack(side='left')
        ttk.Combobox(perf2,textvariable=self.raw_workers,state='readonly',width=6,values=[1,2,3,4]).pack(side='right')
        ttk.Button(t,text='重新检测 CUDA',command=lambda:self.detect_acceleration(show_dialog=True)).pack(fill='x',pady=(4,0))
        ttk.Separator(t).pack(fill='x',pady=12)
        ttk.Label(t,text='实时堆栈预览',font=_ui_font(10)).pack(anchor='w')
        ttk.Checkbutton(t,text='启用即时预览',variable=self.live_preview_var).pack(anchor='w',pady=(4,2))
        row=ttk.Frame(t); row.pack(fill='x',pady=2)
        ttk.Label(row,text='每').pack(side='left')
        ttk.Combobox(row,textvariable=self.preview_every,state='readonly',width=5,values=[1,2,5,10,20]).pack(side='left',padx=4)
        ttk.Label(row,text='帧刷新一次').pack(side='left')
        ttk.Label(t,textvariable=self.stack_counter_text,style='Stage.TLabel').pack(anchor='w',pady=(6,6))
        btnrow=ttk.Frame(t); btnrow.pack(fill='x')
        self.pause_btn=ttk.Button(btnrow,text='⏸ 暂停',command=self.toggle_stack_pause,state='disabled'); self.pause_btn.pack(side='left',fill='x',expand=True,padx=(0,3))
        self.use_btn=ttk.Button(btnrow,text='✓ 使用当前结果',command=self.use_current_stack,state='disabled'); self.use_btn.pack(side='left',fill='x',expand=True,padx=(3,0))
        self.cancel_btn=ttk.Button(t,text='取消堆栈',command=self.cancel_stack,state='disabled'); self.cancel_btn.pack(fill='x',pady=(5,0))

    def _build_stretch_tab(self):
        t=self._scrollable_tab_body(self.tab_stretch)
        ttk.Label(t,text='Linear → Nonlinear',font=_ui_font(11)).pack(anchor='w')
        ttk.Label(t,text='Auto Stretch 只是显示预览，不修改线性数据。\n“应用 Asinh”才真正转换到非线性。',wraplength=285).pack(anchor='w',pady=(3,12))
        self.stretch_strength=tk.DoubleVar(value=8.0)
        self.stretch_black=tk.DoubleVar(value=0.0)
        self._scale(t,'Asinh Strength',self.stretch_strength,0.1,500,0.5)
        self._scale(t,'Black Point',self.stretch_black,0,0.05,0.0005)
        ttk.Button(t,text='应用 Asinh 拉伸',style='Primary.TButton',command=self.do_stretch).pack(fill='x',pady=(12,4))
        ttk.Button(t,text='恢复 Linear Master',command=self.restore_linear_master).pack(fill='x')

    def _basic_defaults_dict(self):
        defaults={
            'exposure':0.0,'contrast':0.0,'highlights':0.0,'shadows':0.0,'whites':0.0,'blacks':0.0,
            'temperature':0.0,'tint':0.0,'texture':0.0,'clarity':0.0,'dehaze':0.0,
            'hsl_hue':0.0,'hsl_sat':0.0,'hsl_lum':0.0,
            'cg_shadow_h':0.0,'cg_shadow_s':0.0,'cg_mid_h':0.0,'cg_mid_s':0.0,'cg_high_h':0.0,'cg_high_s':0.0,'cg_balance':0.0,
            'detail_sharpen':0.0,'detail_radius':1.0,'luma_nr':0.0,'chroma_nr':0.0,
            'opt_distortion':0.0,'opt_vignette':0.0,'opt_ca':0.0,
            'cal_red_h':0.0,'cal_red_s':0.0,'cal_green_h':0.0,'cal_green_s':0.0,'cal_blue_h':0.0,'cal_blue_s':0.0,
        }
        for cname in ['red','orange','yellow','green','aqua','blue','purple','magenta']:
            defaults[f'mix_{cname}_h']=0.0;defaults[f'mix_{cname}_s']=0.0;defaults[f'mix_{cname}_l']=0.0
        return defaults

    def _basic_cfg_from_ui(self, proxy_scale=1.0):
        cfg={k:v.get() for k,v in self.basic_vars.items()}
        cfg['_proxy_scale']=float(proxy_scale)
        cfg['base_curve']=False
        return cfg

    def _basic_is_identity(self):
        if not hasattr(self,'basic_defaults') or not hasattr(self,'basic_vars'):
            return True
        for key,default in self.basic_defaults.items():
            try:
                if abs(float(self.basic_vars[key].get())-float(default))>1e-8:
                    return False
            except Exception:
                return False
        return True

    def _build_basic_tab(self):
        t=self._scrollable_tab_body(self.tab_basic)
        ttk.Label(t,text='Camera Raw 风格基础调整',font=_ui_font(11)).pack(anchor='w',pady=(0,6))
        ttk.Label(t,text='这里统一对齐延时处理中的 Base / 基础调色逻辑：面向堆栈并拉伸后的 TIFF / Float 图像，不调用 Adobe Camera Raw。可用鼠标滚轮浏览完整面板。',wraplength=300).pack(anchor='w',pady=(0,8))
        self.basic_defaults=self._basic_defaults_dict()
        self.basic_vars={k:tk.DoubleVar(value=v) for k,v in self.basic_defaults.items()}

        sec=ttk.LabelFrame(t,text='Basic / 基本明暗',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Exposure (EV)',self.basic_vars['exposure'],-5,5,0.05)
        for name,key in [('Contrast','contrast'),('Highlights','highlights'),('Shadows','shadows'),('Whites','whites'),('Blacks','blacks')]:
            self._scale(sec,name,self.basic_vars[key],-100,100,1)

        sec=ttk.LabelFrame(t,text='WB / 白平衡',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Temperature / 色温',self.basic_vars['temperature'],-100,100,1)
        self._scale(sec,'Tint / 色调',self.basic_vars['tint'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Presence / 质感',padding=7);sec.pack(fill='x',pady=4)
        for name,key in [('Texture / 纹理','texture'),('Clarity / 清晰度','clarity'),('Dehaze / 去朦胧','dehaze')]:
            self._scale(sec,name,self.basic_vars[key],-100,100,1)

        sec=ttk.LabelFrame(t,text='HSL / 全局色相·饱和度·明度',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Hue / 色相',self.basic_vars['hsl_hue'],-180,180,1)
        self._scale(sec,'Saturation / 饱和度',self.basic_vars['hsl_sat'],-100,100,1)
        self._scale(sec,'Luminance / 明度',self.basic_vars['hsl_lum'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Color Mixer / 颜色混合器',padding=7);sec.pack(fill='x',pady=4)
        color_labels=[('red','Red / 红'),('orange','Orange / 橙'),('yellow','Yellow / 黄'),('green','Green / 绿'),('aqua','Aqua / 青'),('blue','Blue / 蓝'),('purple','Purple / 紫'),('magenta','Magenta / 洋红')]
        for cname,clabel in color_labels:
            sub=ttk.LabelFrame(sec,text=clabel,padding=5);sub.pack(fill='x',pady=2)
            self._scale(sub,'Hue',self.basic_vars[f'mix_{cname}_h'],-100,100,1)
            self._scale(sub,'Saturation',self.basic_vars[f'mix_{cname}_s'],-100,100,1)
            self._scale(sub,'Luminance',self.basic_vars[f'mix_{cname}_l'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Color Grading / 色彩分级',padding=7);sec.pack(fill='x',pady=4)
        for prefix,label in [('shadow','Shadows / 阴影'),('mid','Midtones / 中间调'),('high','Highlights / 高光')]:
            sub=ttk.LabelFrame(sec,text=label,padding=5);sub.pack(fill='x',pady=2)
            self._scale(sub,'Hue / 色相',self.basic_vars[f'cg_{prefix}_h'],0,360,1)
            self._scale(sub,'Saturation / 饱和度',self.basic_vars[f'cg_{prefix}_s'],-100,100,1)
        self._scale(sec,'Balance / 平衡',self.basic_vars['cg_balance'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Detail / 细节',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Sharpen / 锐化',self.basic_vars['detail_sharpen'],0,200,1)
        self._scale(sec,'Radius / 半径 px',self.basic_vars['detail_radius'],0.2,10,0.1,reset_value=1.0)
        self._scale(sec,'Luma NR / 明度降噪',self.basic_vars['luma_nr'],0,100,1)
        self._scale(sec,'Chroma NR / 色彩降噪',self.basic_vars['chroma_nr'],0,100,1)

        sec=ttk.LabelFrame(t,text='Optics / 光学',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Distortion / 畸变',self.basic_vars['opt_distortion'],-100,100,1)
        self._scale(sec,'Vignette / 暗角',self.basic_vars['opt_vignette'],-100,100,1)
        self._scale(sec,'CA / 色差校正',self.basic_vars['opt_ca'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Calibration / 校准',padding=7);sec.pack(fill='x',pady=4)
        for prefix,label in [('red','Red Primary / 红原色'),('green','Green Primary / 绿原色'),('blue','Blue Primary / 蓝原色')]:
            sub=ttk.LabelFrame(sec,text=label,padding=5);sub.pack(fill='x',pady=2)
            self._scale(sub,'Hue / 色相',self.basic_vars[f'cal_{prefix}_h'],-100,100,1)
            self._scale(sub,'Saturation / 饱和度',self.basic_vars[f'cal_{prefix}_s'],-100,100,1)

        ttk.Button(t,text='应用基础调整',style='Primary.TButton',command=self.do_basic).pack(fill='x',pady=(10,3))
        ttk.Button(t,text='参数归零',command=self.reset_basic).pack(fill='x')

    def _build_channel_tab(self):
        t=self._scrollable_tab_body(self.tab_channel)
        ttk.Label(t,text='通道混合器',font=_ui_font(11)).pack(anchor='w',pady=(0,8))
        ttk.Label(t,text='可选择输出通道，并可开启单色模式。极端正/负通道权重会放大色差噪声，因此默认开启“色彩噪声保护”；它只预处理通道色差，不直接模糊亮度。关闭后即为纯数学通道混合。',wraplength=285).pack(anchor='w',pady=(0,10))
        self.channel_output=tk.StringVar(value='红色')
        self.channel_mono=tk.BooleanVar(value=False)
        self.channel_red=tk.DoubleVar(value=100.0)
        self.channel_green=tk.DoubleVar(value=0.0)
        self.channel_blue=tk.DoubleVar(value=0.0)
        self.channel_constant=tk.DoubleVar(value=0.0)
        self.channel_noise_protect=tk.BooleanVar(value=True)
        self.channel_noise_strength=tk.DoubleVar(value=30.0)
        self.channel_noise_radius=tk.DoubleVar(value=0.8)
        row=ttk.Frame(t); row.pack(fill='x',pady=(2,6))
        ttk.Label(row,text='输出通道').pack(side='left')
        channel_combo=ttk.Combobox(row,textvariable=self.channel_output,state='readonly',width=10,values=['灰色','红色','绿色','蓝色'])
        channel_combo.pack(side='right')
        channel_combo.bind('<<ComboboxSelected>>', lambda e:self.on_channel_output_changed())
        # The themed PhotoImage indicator can lose its selected-state image on
        # Windows after a theme/font refresh.  Use Tk's native indicator for this
        # important mode switch so a checked monochrome state is always visible.
        palette=THEME_PALETTES.get(_appearance.UI_THEME_PREFERENCE,THEME_PALETTES['light'])
        self.channel_mono_check=tk.Checkbutton(
            t,text='单色',variable=self.channel_mono,command=self.on_channel_mono_toggle,
            bg=palette['bg'],fg=palette['fg'],activebackground=palette['bg'],
            activeforeground=palette['fg'],selectcolor=palette['field'],
            highlightthickness=0,bd=0,font=_ui_font(9),anchor='w')
        self.channel_mono_check.pack(anchor='w',pady=(0,6))
        noise=ttk.LabelFrame(t,text='色彩噪声保护',padding=6); noise.pack(fill='x',pady=(0,7))
        ttk.Checkbutton(noise,text='启用（只平滑通道色差，尽量保留亮度细节）',variable=self.channel_noise_protect).pack(anchor='w',pady=(0,3))
        self._scale(noise,'强度 %',self.channel_noise_strength,0,100,1,reset_value=30.0)
        self._scale(noise,'半径 px',self.channel_noise_radius,0.1,5.0,0.1,reset_value=0.8)
        self._scale(t,'红色 %',self.channel_red,-200,200,1)
        self._scale(t,'绿色 %',self.channel_green,-200,200,1)
        self._scale(t,'蓝色 %',self.channel_blue,-200,200,1)
        self._scale(t,'常数 %',self.channel_constant,-100,100,1)
        btns=ttk.Frame(t); btns.pack(fill='x',pady=(10,4))
        ttk.Button(btns,text='应用通道混合器',style='Primary.TButton',command=self.do_channel_mixer).pack(side='left',fill='x',expand=True,padx=(0,3))
        ttk.Button(btns,text='参数归零 / 预设',command=self.reset_channel_mixer).pack(side='left',fill='x',expand=True,padx=(3,0))

    def _build_curves_tab(self):
        t=self._scrollable_tab_body(self.tab_curves)
        ttk.Label(t,text='Curves',font=_ui_font(11)).pack(anchor='w')
        ttk.Label(t,text='真正的控制点曲线编辑器：支持 RGB / 红 / 绿 / 蓝 / 亮度。点击添加点，控制点可横向/纵向拖动；下方黑/白三角可直接调整输入端点。右键删除中间控制点。',wraplength=285).pack(anchor='w',pady=(3,10))
        row=ttk.Frame(t); row.pack(fill='x',pady=(0,6))
        ttk.Label(row,text='通道').pack(side='left')
        self.curve_channel=tk.StringVar(value='RGB')
        cb=ttk.Combobox(row,textvariable=self.curve_channel,state='readonly',width=10,values=['RGB','红色','绿色','蓝色','亮度'])
        cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>', lambda e:self._on_curve_channel_changed())

        self.curve_canvas=tk.Canvas(t,width=290,height=310,bg='#202020',highlightthickness=1,highlightbackground='#404040')
        self.curve_canvas.pack(fill='x',pady=(2,6))
        self.curve_canvas.bind('<Button-1>', self._curve_click)
        self.curve_canvas.bind('<B1-Motion>', self._curve_drag)
        self.curve_canvas.bind('<ButtonRelease-1>', self._curve_release)
        self.curve_canvas.bind('<Button-3>', self._curve_right_click)
        self.curve_canvas.bind('<Configure>', lambda e:self._draw_curve_editor())

        vals=ttk.Frame(t); vals.pack(fill='x',pady=(0,6))
        self.curve_input_var=tk.DoubleVar(value=50.0)
        self.curve_output_var=tk.DoubleVar(value=50.0)
        self._labeled_entry(vals,'输入',self.curve_input_var).pack(side='left',fill='x',expand=True,padx=(0,4))
        self._labeled_entry(vals,'输出',self.curve_output_var).pack(side='left',fill='x',expand=True,padx=(4,0))
        self.curve_input_var.trace_add('write', lambda *a:self._curve_numeric_changed())
        self.curve_output_var.trace_add('write', lambda *a:self._curve_numeric_changed())

        btns=ttk.Frame(t); btns.pack(fill='x',pady=(2,2))
        ttk.Button(btns,text='重置当前通道',command=self.reset_current_curve).pack(side='left',fill='x',expand=True,padx=(0,4))
        ttk.Button(btns,text='重置全部通道',command=self.reset_all_curves).pack(side='left',fill='x',expand=True,padx=(4,0))
        ttk.Button(t,text='应用曲线',style='Primary.TButton',command=self.do_curve).pack(fill='x',pady=(10,0))
        self._init_curves()
        self.curve_axis_drag = None
        self.after(30, self._draw_curve_editor)

    def _build_detail_tab(self):
        t=self._scrollable_tab_body(self.tab_detail)

        ttk.Label(t,text='细节滤镜 · 实时预览',font=_ui_font(11)).pack(anchor='w',pady=(0,6))
        ttk.Label(t,text='高反差保留与浮雕默认关闭，只有在你主动开启后才会参与实时预览与应用。数值框支持双击后直接输入。向下滚动可看到完整浮雕参数。',wraplength=300).pack(anchor='w',pady=(0,8))

        # USM
        usm=ttk.LabelFrame(t,text='USM 锐化',padding=7); usm.pack(fill='x')
        self.usm_amount=tk.DoubleVar(value=0); self.usm_radius=tk.DoubleVar(value=2.0); self.usm_threshold=tk.DoubleVar(value=0.0)
        self._scale(usm,'Amount %',self.usm_amount,0,500,1)
        self._scale(usm,'Radius px',self.usm_radius,0.1,250,0.2)
        self._scale(usm,'Threshold',self.usm_threshold,0,255,1)
        ttk.Button(usm,text='应用 USM',command=self.do_usm).pack(fill='x',pady=(5,0))

        # High Pass
        hp=ttk.LabelFrame(t,text='高反差保留（PS 风格）',padding=7); hp.pack(fill='x',pady=(8,0))
        self.hp_enabled=tk.BooleanVar(value=False)
        ttk.Checkbutton(hp,text='启用高反差保留',variable=self.hp_enabled).pack(anchor='w',pady=(0,4))
        self.hp_radius=tk.DoubleVar(value=10.0)
        self.hp_amount=tk.DoubleVar(value=100.0)
        self.hp_mode=tk.StringVar(value='Overlay')
        self.hp_preview_type=tk.StringVar(value='滤镜本体')
        self.hp_curve_enabled=tk.BooleanVar(value=False)
        self._scale(hp,'Radius px',self.hp_radius,0.1,250,0.1)
        ttk.Label(hp,text='预览').pack(anchor='w',pady=(3,0))
        ttk.Combobox(hp,textvariable=self.hp_preview_type,state='readonly',values=['滤镜本体','混合到原图']).pack(fill='x',pady=(2,4))
        ttk.Label(hp,text='混合模式 / Opacity（仅“混合到原图”）').pack(anchor='w')
        ttk.Combobox(hp,textvariable=self.hp_mode,state='readonly',values=['Overlay','Soft Light','Linear Light']).pack(fill='x',pady=(2,3))
        self._scale(hp,'Opacity %',self.hp_amount,0,100,1)
        ttk.Checkbutton(hp,text='启用高反差保留曲线',variable=self.hp_curve_enabled).pack(anchor='w',pady=(6,2))
        ttk.Button(hp,text='打开 High Pass 曲线编辑器',command=self.open_hp_curve_dialog).pack(fill='x',pady=(0,4))
        ttk.Button(hp,text='应用 High Pass',command=self.do_highpass).pack(fill='x')

        # Emboss - Photoshop-style core parameters
        em=ttk.LabelFrame(t,text='浮雕（Photoshop 风格）',padding=7); em.pack(fill='x',pady=(8,0))
        self.emboss_enabled=tk.BooleanVar(value=False)
        self.emboss_preview=tk.BooleanVar(value=True)
        top=ttk.Frame(em); top.pack(fill='x',pady=(0,4))
        ttk.Checkbutton(top,text='启用浮雕',variable=self.emboss_enabled).pack(side='left')
        ttk.Checkbutton(top,text='预览',variable=self.emboss_preview).pack(side='right')
        self.emboss_angle=tk.DoubleVar(value=-128.0)
        self.emboss_height=tk.DoubleVar(value=1.0)
        self.emboss_strength=tk.DoubleVar(value=100.0)
        self.emboss_style=tk.StringVar(value='Photoshop Emboss')
        self.emboss_blend=tk.StringVar(value='Normal')
        self.emboss_opacity=tk.DoubleVar(value=100.0)
        r=ttk.Frame(em);r.pack(fill='x',pady=(2,4));ttk.Label(r,text='类型 / Style').pack(side='left');ttk.Combobox(r,textvariable=self.emboss_style,state='readonly',values=['Photoshop Emboss','Color Emboss','Gray Emboss'],width=18).pack(side='right')
        self._scale(em,'角度 (°)',self.emboss_angle,-180,180,1,reset_value=-128.0)
        dialrow=ttk.Frame(em);dialrow.pack(fill='x',pady=(2,5))
        ttk.Label(dialrow,text='方向 / Angle Dial\n拖动圆内方向杆改变角度\n双击圆盘恢复 -128°',foreground='#666').pack(side='left',anchor='w')
        AngleDial(dialrow,self.emboss_angle,command=lambda v:self._schedule_preview(immediate=False),release_command=lambda v:self._schedule_preview(immediate=True),reset_value=-128.0,size=72).pack(side='right',padx=(8,10))
        self._scale(em,'高度 (像素)',self.emboss_height,1,200,1)
        self._scale(em,'数量 (%)',self.emboss_strength,1,500,1)
        r=ttk.Frame(em);r.pack(fill='x',pady=(3,3));ttk.Label(r,text='混合模式 / Blend').pack(side='left');ttk.Combobox(r,textvariable=self.emboss_blend,state='readonly',values=['Normal','Overlay','Soft Light','Linear Light'],width=18).pack(side='right')
        self._scale(em,'不透明度 / Opacity %',self.emboss_opacity,0,100,1,reset_value=100.0)
        ttk.Label(em,text='Photoshop Emboss 为推荐 PS 风格；Color Emboss 保留现有彩色模式；Gray Emboss 保留旧版灰色模式。',foreground='#666').pack(anchor='w',pady=(2,3))
        ttk.Button(em,text='应用浮雕',command=self.do_emboss).pack(fill='x',pady=(5,8))

    def _labeled_entry(self,parent,label,var):
        frame=ttk.Frame(parent)
        ttk.Label(frame,text=label).pack(anchor='w')
        entry=ttk.Entry(frame,textvariable=var,width=8,justify='right')
        entry.pack(fill='x')

        def select_all(event=None):
            entry.focus_set()
            entry.selection_range(0,'end')
            entry.icursor('end')
            return 'break'

        # Keep the same keyboard behavior as the other parameter boxes.
        entry.bind('<Control-a>', select_all)
        entry.bind('<Control-A>', select_all)
        entry.bind('<Double-Button-1>', select_all)
        entry.bind('<Return>', lambda e:(self._curve_numeric_changed(), 'break')[1])
        return frame

    def _scale(self,parent,label,var,frm,to,res,reset_value=None):
        box=ttk.Frame(parent); box.pack(fill='x',pady=2)
        top=ttk.Frame(box); top.pack(fill='x')
        ttk.Label(top,text=label).pack(side='left')
        entry=ttk.Entry(top,width=10,justify='right')
        entry.pack(side='right')
        initial_value=float(var.get())
        if reset_value is None:
            reset_value = 0.0 if float(frm) <= 0.0 <= float(to) else initial_value

        def fmt_value(v):
            try:
                fv=float(v)
                if abs(res - round(res)) < 1e-9 and res >= 1:
                    return str(int(round(fv)))
                return f'{fv:.6f}'.rstrip('0').rstrip('.')
            except Exception:
                return str(v)

        def sync_from_var(*args):
            # While the user is typing, don't overwrite their edit.
            if entry.focus_get() == entry:
                return
            entry.delete(0,'end')
            entry.insert(0, fmt_value(var.get()))

        def commit_entry(event=None):
            txt=entry.get().strip()
            try:
                v=float(txt)
                if v < frm: v = frm
                if v > to: v = to
                var.set(v)
                entry.delete(0,'end')
                entry.insert(0, fmt_value(v))
            except Exception:
                entry.delete(0,'end')
                entry.insert(0, fmt_value(var.get()))
            return 'break' if event and getattr(event,'keysym','') == 'Return' else None

        # Expose the commit callback so a slider can safely commit the currently
        # focused numeric field before Tk's Scale class binding changes its value.
        entry._icehalo_commit = commit_entry

        click_state={'time':0}
        def begin_drag(event=None):
            # ttk::scale's class binding may move the thumb on the second click before
            # <Double-Button-1> becomes visible on some Windows themes. Detect the
            # second press ourselves at widget-binding priority and stop the class
            # binding after restoring the neutral/default value.
            now=int(getattr(event,'time',0) or 0)
            if now and click_state['time'] and 0 < now-click_state['time'] <= 420:
                click_state['time']=0
                return reset_slider(event)
            click_state['time']=now
            focused=self.focus_get()
            if isinstance(focused, (tk.Entry, ttk.Entry)):
                cb=getattr(focused, '_icehalo_commit', None)
                if cb is not None:
                    cb()
                try:
                    scale.focus_set()
                except Exception:
                    pass
            self._slider_dragging=True

        def end_drag(event=None):
            self._slider_dragging=False
            # Make sure the numeric box reflects the final slider value.
            try:
                entry.delete(0,'end')
                entry.insert(0, fmt_value(var.get()))
            except Exception:
                pass
            # Do not force a zero-delay HQ render for every slider mouse-up.  The
            # normal debounce combines a quick sequence of three or four edits.
            self._schedule_preview(immediate=False)

        def reset_slider(event=None):
            var.set(float(reset_value))
            try:
                scale.focus_set()
            except Exception:
                pass
            self._slider_dragging=False
            try:self.status.set(f'{label} 已恢复中性/默认值：{float(reset_value):g}')
            except Exception:pass
            self._schedule_preview(immediate=True)
            return 'break'

        def select_entry_all(event=None):
            entry.focus_set()
            entry.selection_range(0,'end')
            entry.icursor('end')
            return 'break'

        var.trace_add('write', lambda *a: sync_from_var())
        sync_from_var()
        entry.bind('<Return>', commit_entry)
        # FocusOut remains useful when moving between ordinary controls. The Scale
        # ButtonPress handler above commits first, so it can no longer overwrite dragging.
        entry.bind('<FocusOut>', commit_entry)
        entry.bind('<Control-a>', select_entry_all)
        entry.bind('<Control-A>', select_entry_all)
        entry.bind('<Double-Button-1>', select_entry_all)
        scale=ttk.Scale(box,from_=frm,to=to,variable=var)
        scale.pack(fill='x')
        scale.bind('<ButtonPress-1>', begin_drag, add='+')
        scale.bind('<ButtonRelease-1>', end_drag, add='+')
        scale.bind('<Double-Button-1>', reset_slider, add='+')
        return scale

    def _setup_var_traces(self):
        vars_to_watch = [self.auto_preview_var, self.live_preview_var, self.preview_every, self.stretch_strength, self.stretch_black,
            self.usm_amount, self.usm_radius, self.usm_threshold, self.hp_enabled, self.hp_radius, self.hp_amount, self.hp_mode, self.hp_preview_type, self.hp_curve_enabled,
            self.emboss_enabled, self.emboss_preview, self.emboss_angle, self.emboss_height, self.emboss_strength, self.emboss_style, self.emboss_blend, self.emboss_opacity,
            self.channel_output, self.channel_mono, self.channel_red, self.channel_green, self.channel_blue, self.channel_constant, self.channel_noise_protect, self.channel_noise_strength, self.channel_noise_radius]
        vars_to_watch += list(self.basic_vars.values())
        for var in vars_to_watch:
            var.trace_add('write', self._on_live_param_change)
        self.tabs.bind('<<NotebookTabChanged>>', lambda e:self.refresh_preview(), add='+')

    def _on_live_param_change(self, *args):
        if self._var_trace_suspend:
            return
        self._schedule_preview(immediate=False)

    def _schedule_preview(self, immediate=False):
        # Coalesce high-frequency Scale events. Base/Camera-Raw preview is expensive,
        # so it is rendered in a single-flight worker: while one frame is running we
        # remember only the newest requested state instead of queueing every mouse move.
        self._main_preview_request_serial += 1
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id=None
        # A short mouse-up debounce lets several quick adjustments collapse into
        # one Base render.  Immediate is reserved for explicit final refreshes.
        delay = 0 if immediate else (28 if self._slider_dragging else 140)
        self._preview_after_id=self.after(delay, self._run_scheduled_preview)

    def _run_scheduled_preview(self):
        self._preview_after_id=None
        try:
            current_tab=self.tabs.select()
        except Exception:
            current_tab=''
        # Base is the heaviest interactive panel. Never run its full preview pipeline
        # synchronously on the Tk/UI thread; doing so is what caused Not Responding.
        if (not self.is_linear) and current_tab == str(getattr(self,'tab_basic','')):
            self._request_async_basic_preview()
            return
        self.refresh_preview()

    def _request_async_basic_preview(self):
        serial=int(self._main_preview_request_serial)
        quality='drag' if self._slider_dragging else 'hq'
        if self._main_async_preview_running:
            self._main_async_preview_pending=True
            self._main_async_preview_quality=quality
            return
        base=self._preview_base_image()
        if base is None:
            return
        cfg=self._basic_cfg_from_ui(proxy_scale=float(getattr(self,'_preview_proxy_scale',1.0)))
        # The cached proxy is read-only for this worker: apply_base_editor creates its
        # own float working array before processing, so the master/proxy cache is safe.
        self._main_async_preview_running=True
        self._main_async_preview_pending=False
        self._main_async_preview_quality=quality
        def work():
            try:
                out=apply_base_editor(base,cfg,None)
                self.queue.put(('main_basic_preview',(serial,out,quality,None)))
            except Exception as e:
                self.queue.put(('main_basic_preview',(serial,None,quality,str(e))))
        threading.Thread(target=work,daemon=True).start()

    def _set_var_silently(self, var, value):
        self._var_trace_suspend = True
        try:
            var.set(value)
        finally:
            self._var_trace_suspend = False

    def estimate_current_stretch(self):
        if self.linear_master is None and self.working_image is None:
            return
        img = self.linear_master if self.linear_master is not None else self.working_image
        if img is None:
            return
        strength, black = estimate_asinh_params(img)
        self.suggested_stretch_strength = float(strength)
        self.suggested_stretch_black = float(black)
        self._set_var_silently(self.stretch_strength, round(float(strength), 4))
        self._set_var_silently(self.stretch_black, round(float(black), 6))
        self.refresh_preview()

    def reset_to_suggested_stretch(self):
        self._set_var_silently(self.stretch_strength, round(float(self.suggested_stretch_strength), 4))
        self._set_var_silently(self.stretch_black, round(float(self.suggested_stretch_black), 6))
        self.refresh_preview()

    def _init_curves(self):
        self.curve_points = {k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']}
        self.curve_selected_idx = None

    def _current_curve_points(self):
        ch = self.curve_channel.get() if hasattr(self, 'curve_channel') else 'RGB'
        return self.curve_points.setdefault(ch, [(0.0,0.0),(1.0,1.0)])

    def _curve_is_identity(self, channel=None):
        ch = channel or (self.curve_channel.get() if hasattr(self,'curve_channel') else 'RGB')
        pts = self.curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
        return len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6

    def _curves_any_active(self):
        return any(not self._curve_is_identity(ch) for ch in ['RGB','红色','绿色','蓝色','亮度'])

    def _curve_canvas_geometry(self):
        c = self.curve_canvas
        W = max(c.winfo_width(), 80); H = max(c.winfo_height(), 100)
        m = 18
        # Leave a strip below the graph for Photoshop-style input endpoint handles.
        bottom_strip = 20
        return W, H, m, W-2*m, H-2*m-bottom_strip

    def _curve_to_canvas(self, x, y):
        W,H,m,w,h = self._curve_canvas_geometry()
        return m + x*w, m + (1.0-y)*h

    def _canvas_to_curve(self, cx, cy):
        W,H,m,w,h = self._curve_canvas_geometry()
        x = (cx - m) / max(w,1)
        y = 1.0 - (cy - m) / max(h,1)
        return max(0.0,min(1.0,x)), max(0.0,min(1.0,y))

    def _nearest_curve_point(self, cx, cy, threshold=10):
        pts = self._current_curve_points()
        best=None; bestd=1e9
        for i,(x,y) in enumerate(pts):
            px,py = self._curve_to_canvas(x,y)
            d=((cx-px)**2+(cy-py)**2)**0.5
            if d < bestd:
                best=(i,px,py); bestd=d
        if best and bestd <= threshold:
            return best[0]
        return None

    def _set_curve_selected_point_vars(self):
        if self.curve_selected_idx is None:
            return
        pts = self._current_curve_points()
        if 0 <= self.curve_selected_idx < len(pts):
            x,y = pts[self.curve_selected_idx]
            self._set_var_silently(self.curve_input_var, round(x*255.0, 2))
            self._set_var_silently(self.curve_output_var, round(y*255.0, 2))

    def _draw_curve_editor(self):
        if not hasattr(self, 'curve_canvas'):
            return
        c=self.curve_canvas; c.delete('all')
        W,H,m,w,h = self._curve_canvas_geometry()
        # background grid
        c.create_rectangle(m,m,m+w,m+h, outline='#666666', fill='#222222')
        for i in range(1,4):
            x = m + w*i/4.0; y = m + h*i/4.0
            c.create_line(x,m,x,m+h, fill='#333333')
            c.create_line(m,y,m+w,y, fill='#333333')
        # diagonal identity
        c.create_line(m,m+h,m+w,m, fill='#555555', dash=(4,3))
        # histogram background for current channel
        try:
            np, *_ = _deps()
            img = self._preview_base_image()
            if img is not None:
                smp = np.clip(img[::8,::8],0,1)
                ch=self.curve_channel.get() if hasattr(self,'curve_channel') else 'RGB'
                if ch=='RGB': vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
                elif ch=='红色': vals=smp[...,0].ravel()
                elif ch=='绿色': vals=smp[...,1].ravel()
                elif ch=='蓝色': vals=smp[...,2].ravel()
                else: vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
                hist,_=np.histogram(vals,bins=160,range=(0,1))
                hist=np.log1p(hist.astype(np.float64)); mx=hist.max() or 1.0; hist/=mx
                # Filled gray waveform, closer to Photoshop/ACR Curves.
                poly=[m, m+h]
                ridge=[]
                for i,v in enumerate(hist):
                    x = m + (i/(len(hist)-1))*w
                    y = m+h - v*(h*0.78)
                    poly.extend([x,y]); ridge.extend([x,y])
                poly.extend([m+w, m+h])
                c.create_polygon(*poly, fill='#4a4a4a', outline='')
                c.create_line(*ridge, fill='#707070', width=1)
        except Exception:
            pass
        # Photoshop-style horizontal input endpoint sliders (black / white triangles).
        pts = self._current_curve_points()
        if len(pts) >= 2:
            bx,_ = self._curve_to_canvas(pts[0][0], pts[0][1])
            wx,_ = self._curve_to_canvas(pts[-1][0], pts[-1][1])
            axis_y = m+h+12
            c.create_polygon(bx-6,axis_y+6, bx+6,axis_y+6, bx,axis_y-4, fill='#111111', outline='#9a9a9a', tags=('curve_axis_black',))
            c.create_polygon(wx-6,axis_y+6, wx+6,axis_y+6, wx,axis_y-4, fill='#eeeeee', outline='#9a9a9a', tags=('curve_axis_white',))

        # curve line
        pts = self._current_curve_points()
        lut = build_curve_lut(pts, 256)
        line=[]
        for i,v in enumerate(lut):
            x = i/255.0
            cx,cy = self._curve_to_canvas(x, float(v))
            line.extend([cx,cy])
        c.create_line(*line, fill='#58a6ff', width=2, smooth=True)
        for i,(x,y) in enumerate(pts):
            cx,cy = self._curve_to_canvas(x,y)
            r = 4 if i != self.curve_selected_idx else 6
            fill = '#ffffff' if i==self.curve_selected_idx else '#b9d6ff'
            c.create_oval(cx-r,cy-r,cx+r,cy+r, fill=fill, outline='#1f6feb', width=1)

    def _on_curve_channel_changed(self):
        self.curve_selected_idx = None
        self._draw_curve_editor()
        self.refresh_preview()

    def _curve_click(self, event):
        pts = self._current_curve_points()
        # First test the bottom-axis black/white input handles.
        if len(pts) >= 2:
            W,H,m,w,h = self._curve_canvas_geometry()
            axis_y = m+h+12
            bx,_ = self._curve_to_canvas(pts[0][0], pts[0][1])
            wx,_ = self._curve_to_canvas(pts[-1][0], pts[-1][1])
            if abs(event.y-axis_y) <= 12 and abs(event.x-bx) <= 12:
                self.curve_axis_drag='black'; self.curve_selected_idx=0
                self._set_curve_selected_point_vars(); self._draw_curve_editor(); return
            if abs(event.y-axis_y) <= 12 and abs(event.x-wx) <= 12:
                self.curve_axis_drag='white'; self.curve_selected_idx=len(pts)-1
                self._set_curve_selected_point_vars(); self._draw_curve_editor(); return
        self.curve_axis_drag=None
        W,H,m,w,h = self._curve_canvas_geometry()
        if event.y > m+h:
            return
        idx = self._nearest_curve_point(event.x, event.y)
        if idx is None:
            x,y = self._canvas_to_curve(event.x, event.y)
            pts.append((x,y))
            pts.sort(key=lambda p:p[0])
            idx = min(range(len(pts)), key=lambda i: abs(pts[i][0]-x)+abs(pts[i][1]-y))
        self.curve_selected_idx = idx
        self._set_curve_selected_point_vars()
        self._draw_curve_editor()
        self.refresh_preview()

    def _curve_drag(self, event):
        if self.curve_selected_idx is None:
            return
        pts = self._current_curve_points()
        i = self.curve_selected_idx
        x,y = self._canvas_to_curve(event.x, event.y)
        if self.curve_axis_drag in ('black','white') and len(pts) >= 2:
            if self.curve_axis_drag == 'black':
                x = max(0.0, min(pts[1][0]-0.002, x))
                pts[0] = (x, pts[0][1])
                self.curve_selected_idx = 0
            else:
                x = max(pts[-2][0]+0.002, min(1.0, x))
                pts[-1] = (x, pts[-1][1])
                self.curve_selected_idx = len(pts)-1
            self._set_curve_selected_point_vars()
            self._draw_curve_editor()
            self._slider_dragging = True
            self._schedule_preview(immediate=False)
            return
        if i == 0:
            right = pts[1][0] - 0.002 if len(pts) > 1 else 0.998
            x = max(0.0, min(right, x))
        elif i == len(pts)-1:
            left = pts[-2][0] + 0.002 if len(pts) > 1 else 0.002
            x = max(left, min(1.0, x))
        else:
            left = pts[i-1][0] + 0.002
            right = pts[i+1][0] - 0.002
            x = max(left, min(right, x))
        pts[i] = (x,y)
        self._set_curve_selected_point_vars()
        self._draw_curve_editor()
        self.refresh_preview_fast()

    def _curve_release(self, event):
        self.curve_axis_drag = None
        self._slider_dragging = False
        self._schedule_preview(immediate=True)

    def _curve_right_click(self, event):
        idx = self._nearest_curve_point(event.x, event.y)
        pts = self._current_curve_points()
        if idx is None or idx in (0, len(pts)-1):
            return
        pts.pop(idx)
        self.curve_selected_idx = None
        self._draw_curve_editor()
        self.refresh_preview()

    def _curve_numeric_changed(self):
        if self._var_trace_suspend or self.curve_selected_idx is None:
            return
        pts = self._current_curve_points()
        i = self.curve_selected_idx
        if not (0 <= i < len(pts)):
            return
        try:
            x = float(self.curve_input_var.get())/255.0
            y = float(self.curve_output_var.get())/255.0
        except Exception:
            return
        x = max(0.0, min(1.0, x)); y = max(0.0, min(1.0, y))
        if i == 0:
            right = pts[1][0] - 0.002 if len(pts) > 1 else 0.998
            x = max(0.0, min(right, x))
        elif i == len(pts)-1:
            left = pts[-2][0] + 0.002 if len(pts) > 1 else 0.002
            x = max(left, min(1.0, x))
        else:
            left = pts[i-1][0] + 0.002
            right = pts[i+1][0] - 0.002
            x = max(left, min(right, x))
        pts[i] = (x,y)
        self._draw_curve_editor()
        self.refresh_preview()

    def reset_current_curve(self):
        ch = self.curve_channel.get()
        self.curve_points[ch] = [(0.0,0.0),(1.0,1.0)]
        self.curve_selected_idx = None
        self.curve_axis_drag = None
        self._draw_curve_editor()
        self.refresh_preview()

    def reset_all_curves(self):
        self._init_curves()
        self.curve_axis_drag = None
        self._draw_curve_editor()
        self.refresh_preview()

    def on_channel_mono_toggle(self):
        state = bool(self.channel_mono.get())
        self._last_channel_mono_state = state
        if state:
            self._set_var_silently(self.channel_output, '灰色')
            self._set_var_silently(self.channel_red, 40.0)
            self._set_var_silently(self.channel_green, 40.0)
            self._set_var_silently(self.channel_blue, 20.0)
            self._set_var_silently(self.channel_constant, 0.0)
        self.refresh_preview()

    def on_channel_output_changed(self):
        # If the user manually switches to gray output, keep that choice, but do not
        # force monochrome; presets are only forced when monochrome is enabled.
        self.refresh_preview()

    def reset_channel_mixer(self):
        if getattr(self, 'channel_mono', None) is not None and self.channel_mono.get():
            self._set_var_silently(self.channel_output, '灰色')
            self._set_var_silently(self.channel_red, 40.0)
            self._set_var_silently(self.channel_green, 40.0)
            self._set_var_silently(self.channel_blue, 20.0)
            self._set_var_silently(self.channel_constant, 0.0)
        else:
            out = getattr(self, 'channel_output', tk.StringVar(value='红色')).get()
            if out == '绿色':
                vals = (0.0, 100.0, 0.0)
            elif out == '蓝色':
                vals = (0.0, 0.0, 100.0)
            elif out == '灰色':
                vals = (40.0, 40.0, 20.0)
            else:
                vals = (100.0, 0.0, 0.0)
            self._set_var_silently(self.channel_red, vals[0])
            self._set_var_silently(self.channel_green, vals[1])
            self._set_var_silently(self.channel_blue, vals[2])
            self._set_var_silently(self.channel_constant, 0.0)
        self.refresh_preview()

    def do_channel_mixer(self):
        if not self._require_nonlinear():return
        self._push_undo()
        self.status.set('正在应用通道混合器…'); self.update_idletasks()
        self.working_image = apply_channel_mixer(
            self.working_image,
            output_channel=self.channel_output.get(),
            monochrome=self.channel_mono.get(),
            red=self.channel_red.get(),
            green=self.channel_green.get(),
            blue=self.channel_blue.get(),
            constant=self.channel_constant.get(),
            noise_protect=self.channel_noise_protect.get(),
            noise_strength=self.channel_noise_strength.get(),
            noise_radius=self.channel_noise_radius.get(),
        )
        self.reset_channel_mixer()
        self.status.set('通道混合器完成')

    def _preview_base_image(self):
        if self.stack_active and self.stack_preview_image is not None:
            img=self.stack_preview_image
            source_is_stack_proxy=True
        else:
            if self.working_image is None:
                return None
            img=self.working_image
            source_is_stack_proxy=False
        h,w=img.shape[:2]
        current_tab=self.tabs.select() if hasattr(self,'tabs') else ''
        detail_tab=(current_tab == str(getattr(self,'tab_detail','')))
        basic_tab=(current_tab == str(getattr(self,'tab_basic','')))
        # Dragging uses a small proxy but the SAME processing algorithms. Mouse-up
        # switches to a denser verification proxy. Base is intentionally capped below
        # the Detail page because Camera-Raw style processing runs many sequential
        # operations; this keeps feedback fast while proxy_scale preserves spatial
        # radii and avoids the old preview/final-strength mismatch.
        if self._slider_dragging:
            target_h,target_w=220,390
        elif detail_tab:
            target_h,target_w=1500,2600
        elif basic_tab:
            # Base may traverse WB, HSL, grading, detail, optics and calibration.
            # A 0.47 MP verification proxy is ample for the fit-sized canvas and
            # avoids repeatedly processing a 0.86 MP proxy after every small edit.
            target_h,target_w=520,900
        else:
            target_h,target_w=950,1600
        scale=min(1.0, target_h/float(max(h,1)), target_w/float(max(w,1)))
        # A live stack preview is already a reduced worker proxy; we do not know its
        # exact full-resolution ratio here, so treat it as the current source.
        if source_is_stack_proxy:
            self._preview_proxy_scale=1.0
            return img
        self._preview_proxy_scale=float(scale)
        if scale >= 0.999:
            return img
        nw=max(2,int(round(w*scale)));nh=max(2,int(round(h*scale)))
        # Resizing a 30–60 MP master on every Scale event can itself become the
        # bottleneck. Cache drag/HQ proxies while the underlying master is unchanged.
        cache=getattr(self,'_preview_proxy_cache',None)
        if not isinstance(cache,dict):
            cache={};self._preview_proxy_cache=cache
        key=(id(img),int(h),int(w),int(nh),int(nw))
        cached=cache.get(key)
        if cached is not None:
            return cached
        try:
            np,*_rest=_deps();cv2=_rest[-1]
            if cv2 is not None:
                out=cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA)
            else:
                Image=_rest[1];chans=[]
                for k in range(3):
                    ch=Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.BILINEAR)
                    chans.append(np.asarray(ch,dtype=np.float32))
                out=np.stack(chans,axis=2)
        except Exception:
            step=max(1,int(round(1.0/max(scale,1e-6))))
            out=img[::step,::step]
        cache[key]=out
        # Keep at most a few quality levels/source generations to bound RAM use.
        while len(cache)>4:
            try:cache.pop(next(iter(cache)))
            except Exception:break
        return out

    def _active_preview_image(self):
        np, *_ = _deps()
        img = self._preview_base_image()
        if img is None:
            return None
        out = img.copy()
        current_tab = self.tabs.select()
        if self.is_linear:
            if self.auto_preview_var.get():
                out = auto_stretch_for_display(out, self.stretch_strength.get(), self.stretch_black.get())
            return np.clip(out, 0, 1).astype(np.float32)
        if current_tab == str(self.tab_basic):
            if not self._basic_is_identity():
                out = apply_base_editor(out, self._basic_cfg_from_ui(proxy_scale=self._preview_proxy_scale), None)
        elif current_tab == str(self.tab_channel):
            if self.channel_mono.get() or self.channel_output.get() == '灰色' or any(abs(v.get()) > 1e-8 for v in [self.channel_red, self.channel_green, self.channel_blue, self.channel_constant]):
                out = apply_channel_mixer(out, self.channel_output.get(), self.channel_mono.get(), self.channel_red.get(), self.channel_green.get(), self.channel_blue.get(), self.channel_constant.get(), self.channel_noise_protect.get(), self.channel_noise_strength.get(), self.channel_noise_radius.get())
        elif current_tab == str(self.tab_detail):
            # Spatial parameters are defined in FULL-RESOLUTION pixels. The preview
            # proxy must scale Radius/Height or the preview will look much stronger
            # than the effect that is actually applied to the master.
            ps=max(float(getattr(self,'_preview_proxy_scale',1.0)),1e-4)
            if abs(self.usm_amount.get()) > 1e-8:
                out = apply_usm(out, self.usm_amount.get(), max(0.1,self.usm_radius.get()*ps), self.usm_threshold.get())
            if self.hp_enabled.get():
                hp_r=max(0.1,self.hp_radius.get()*ps)
                if self.hp_preview_type.get() == '滤镜本体':
                    out = highpass_filter(out, hp_r)
                elif abs(self.hp_amount.get()) > 1e-8:
                    out = apply_highpass(out, hp_r, self.hp_amount.get(), self.hp_mode.get())
                out = self._apply_hp_curve(out)
            if self.emboss_enabled.get() and self.emboss_preview.get():
                out = apply_emboss(out, self.emboss_angle.get(), max(0.1,self.emboss_height.get()*ps), self.emboss_strength.get(), self.emboss_opacity.get(), self.emboss_blend.get(), self.emboss_style.get())
        elif current_tab == str(self.tab_curves):
            ch = self.curve_channel.get()
            pts = self.curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
            if not self._curve_is_identity(ch):
                out = apply_curve_lut(out, build_curve_lut(pts, 256), ch)
        return np.clip(out, 0, 1).astype(np.float32)

    def add_files(self):
        pats=' '.join('*'+e for e in sorted(ALL_EXTS))
        ch=filedialog.askopenfilenames(title='选择冰晕延时序列',filetypes=[('图像 / RAW',pats),('所有文件','*.*')])
        self._append(ch)

    def add_folder(self):
        d=filedialog.askdirectory(title='选择包含延时序列的文件夹')
        if not d:return
        self._append([str(p) for p in Path(d).iterdir() if p.is_file() and p.suffix.lower() in ALL_EXTS])

    def open_image(self):
        p=filedialog.askopenfilename(title='打开图像进入编辑',filetypes=[('图像','*.tif *.tiff *.png *.jpg *.jpeg *.bmp')])
        if not p:return
        try:
            self.status.set('正在读取图像…'); self.update_idletasks()
            img=read_linear_rgb(p)
            self.linear_master=img.copy(); self.working_image=img.copy(); self.is_linear=True; self.image_path=p
            self.undo_stack.clear(); self.redo_stack.clear(); self.status.set('图像已载入'); self._update_state(); self.estimate_current_stretch(); self.refresh_preview()
        except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def _append(self, paths):
        old=set(self.files)
        for p in paths:
            if p not in old and Path(p).suffix.lower() in ALL_EXTS:
                self.files.append(p); old.add(p)
        self.files.sort(key=lambda x:Path(x).name.lower()); self.refresh_list()

    def refresh_list(self):
        self.listbox.delete(0,'end')
        for i,p in enumerate(self.files,1): self.listbox.insert('end',f'{i:04d}   {Path(p).name}')
        self.count.config(text=f'{len(self.files)} 帧')
        n=len(self.files)
        if n <= 0:
            self._set_var_silently(self.stack_range_start, 1)
            self._set_var_silently(self.stack_range_end, 1)
        else:
            s=int(self.stack_range_start.get() or 1)
            e=int(self.stack_range_end.get() or n)
            s=max(1,min(n,s)); e=max(1,min(n,e))
            if s>e: s,e=e,s
            if n==len(self.files):
                if self.stack_range_end.get() <= 1 and self.stack_range_start.get() == 1:
                    e=n
            self._set_var_silently(self.stack_range_start, s)
            self._set_var_silently(self.stack_range_end, e)
        self._update_stack_range_info()

    def _current_stack_range(self):
        n=len(self.files)
        if n <= 0:
            return 1, 1, []
        try:
            s=int(self.stack_range_start.get() or 1)
        except Exception:
            s=1
        try:
            e=int(self.stack_range_end.get() or n)
        except Exception:
            e=n
        s=max(1,min(n,s)); e=max(1,min(n,e))
        if s > e:
            s,e=e,s
        subset=self.files[s-1:e]
        return s,e,subset

    def _update_stack_range_info(self, *args):
        n=len(self.files)
        if n <= 0:
            self.stack_range_info.set('当前堆栈区间：无可用帧')
            return
        s,e,subset=self._current_stack_range()
        self.stack_range_info.set(f'当前堆栈区间：{s} - {e}（{len(subset)} 帧）')

    def use_selected_as_stack_range(self):
        sel=self.listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME,'请先在左侧 Frames 列表中选择你要堆栈的范围。\n\n例如先框选第 1–50 张，再点击“使用当前选中范围”。')
            return
        s=min(sel)+1; e=max(sel)+1
        self._set_var_silently(self.stack_range_start, s)
        self._set_var_silently(self.stack_range_end, e)
        self._update_stack_range_info()


    def _handle_ctrl_a(self, event=None):
        w = self.focus_get()
        # Parameter entry: Ctrl+A selects only the number inside that field.
        if isinstance(w, (tk.Entry, ttk.Entry)):
            try:
                w.selection_range(0, 'end')
                w.icursor('end')
            except Exception:
                pass
            return 'break'
        # Text-like widgets should keep their normal Select All behavior.
        if isinstance(w, tk.Text):
            try:
                w.tag_add('sel', '1.0', 'end-1c')
            except Exception:
                pass
            return 'break'
        self.select_all()
        return 'break'

    def select_all(self): self.listbox.selection_set(0,'end')
    def remove_selected(self):
        for i in reversed(self.listbox.curselection()): del self.files[i]
        self.refresh_list()
    def clear_files(self): self.files.clear(); self.refresh_list()
    def open_timelapse(self):
        if len(self.files) < 2:
            messagebox.showwarning(APP_NAME,'请先导入至少 2 帧延时序列。')
            return
        w=getattr(self,'timelapse_window',None)
        try:
            if w is not None and w.winfo_exists():
                w.lift(); w.focus_force(); return
        except Exception:
            pass
        self.timelapse_window=TimelapseNodeWindow(self)

    def open_storage_manager(self):
        StorageManagerDialog(self)

    def show_single_stack_help(self):
        messagebox.showinfo(
            '单独堆栈与性能说明',
            '计算后端：\n'
            '• 自动：CUDA 可用时可选择相应加速路径，否则使用 CPU。\n'
            '• CPU：使用 NumPy / CPU 计算。\n'
            '• NVIDIA CUDA：需要当前 IceHaloStack Python 环境中安装匹配的 CuPy。\n\n'
            'CUDA 检测不会安装或升级系统 CUDA Toolkit；RAW 解码仍主要依赖 CPU。'
            '高分辨率 RAW 可根据机器性能调整并行解码数量。\n\n'
            '实时堆栈预览：\n'
            '堆栈过程中可暂停检查当前结果，满意时可直接使用当前结果结束本次堆栈。\n\n'
            'Master 输出：\n'
            '需要保留线性高动态范围数据时，优先使用 32-bit float TIFF。'
        )

    def about(self):
        messagebox.showinfo('关于',f'{APP_NAME} {VERSION}\n\n冰晕专用 RAW / Mean + Maximum 堆栈 / 图像处理原型。\n当前已包含实时 Mean 堆栈预览、暂停/继续/使用当前结果、基于建议值的 Asinh 预览/拉伸、基础/细节/曲线实时预览、PS 风格 High Pass/Emboss、通道混合器，以及 Linear Master 导出。高反差保留/浮雕默认关闭，数值支持双击输入；浮雕采用 Photoshop 风格角度/高度/数量参数与角度圆盘，并提供 Photoshop Emboss、原有 Color Emboss、Gray Emboss、Blend Mode 与 Opacity；所有主调节页、节点参数页与延时左侧控制栏均支持鼠标滚轮滚动；主预览、延时参考预览、节点实时预览支持滚轮缩放，并可用 Z 一键回到 Fit。Base 实时预览采用单任务后台计算与过期帧丢弃，拖动滑块时不会在 UI 线程堆积计算。v0.4.0 加入预览防抖/拖动代理优化、滑块双击复位，并将 Asinh Strength 上限提高到 500。v0.5.0 加入并行 RAW 预解码与可选 NVIDIA CUDA/CuPy Mean 后端。v0.5.1 加入通用 CUDA Toolkit 检测与自动匹配 CuPy 安装，不修改系统 CUDA。v0.7.1 重构延时工作流；v0.7.6 在延时窗口内加入可直接拖动的 Curves 编辑器，并使用快速/高质量代理图显著提高参数拖动实时预览速度。 v0.9.4.14 将预览平移改为 Canvas Fast Pan，拖拽期间不再重新缩放或重建 PhotoImage。v0.9.5.2 将曝光 / 白平衡平滑工作区改为关键帧驱动界面：支持原生窗口最大化、关键帧向导、全帧列表蓝点切换、关键帧调整同步、LRTimelapse 风格平滑力度与 1–10 遍多遍平滑，并同时显示原始/自动平滑/关键帧目标三类曲线；修正仍以 RAM-only Correction Table 在 Stack 前应用到每个 Linear RGB 输入帧。')

    def _set_stack_controls(self, active=False, paused=False):
        self.stack_active=active; self.stack_paused=paused
        st = 'normal' if active else 'disabled'
        pause_text = '▶ 继续' if paused else '⏸ 暂停'
        for name in ('pause_btn','use_btn','cancel_btn','toolbar_pause_btn','toolbar_use_btn'):
            if hasattr(self,name): getattr(self,name).configure(state=st)
        if hasattr(self,'pause_btn'): self.pause_btn.configure(text=pause_text)
        if hasattr(self,'toolbar_pause_btn'): self.toolbar_pause_btn.configure(text=pause_text)

    def detect_acceleration(self, show_dialog=False):
        requested=self.compute_backend.get() if hasattr(self,'compute_backend') else '自动'
        if requested == 'CPU':
            ver, path, source = detect_system_cuda_toolkit()
            suffix = f' · 系统 Toolkit {ver} 保持不变' if ver else ''
            msg='CPU · NumPy CPU' + suffix
            self.accel_status.set(msg)
            if show_dialog:
                messagebox.showinfo('计算后端检测', msg)
            return
        ok, cuda_desc, _ = detect_cuda_backend()
        if ok:
            msg='CUDA 可用 · ' + cuda_desc
        else:
            prefix = 'CUDA 不可用 · ' if requested == 'NVIDIA CUDA' else '自动将使用 CPU · '
            msg=prefix + cuda_desc
        self.accel_status.set(msg)
        if show_dialog:
            messagebox.showinfo('计算后端检测', msg)

    def start_stack(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME,'堆栈正在进行中。可以暂停、继续，或使用当前结果。')
            return
        if len(self.files)<1:
            messagebox.showwarning(APP_NAME,'请至少导入 1 帧。'); return
        s,e,subset=self._current_stack_range()
        if len(subset) < 1:
            messagebox.showwarning(APP_NAME,'当前堆栈区间无可用帧。请检查起始帧和结束帧。'); return
        method=self.stack_method.get()
        method_key='maximum' if method.startswith('最大值') else 'mean'
        range_tag=f'_{s:04d}-{e:04d}'
        default_name=('IceHaloStack_Maximum' if method_key=='maximum' else 'IceHaloStack_Mean') + f'{range_tag}_LinearMaster_32f.tif'
        out=filedialog.asksaveasfilename(title='保存 Linear Master',defaultextension='.tif',filetypes=[('TIFF','*.tif *.tiff')],initialfile=default_name)
        if not out:return
        self.progress.set(0); self.status.set(f'正在准备实时堆栈… 区间 {s}-{e}')
        self.stack_pause_event.clear(); self.stack_stop_event.clear()
        self.stack_out=out; self.stack_depth=self.output_depth.get(); self.stack_count=0; self.stack_total=len(subset); self.stack_cancel_requested=False; self.active_stack_method=method_key
        self.active_stack_range=(s,e)
        self.stack_running_mean=None; self.stack_preview_image=None
        self.stack_counter_text.set(f'0 / {self.stack_total} 帧 · 区间 {s}-{e}')
        self._set_stack_controls(True,False)
        requested_backend=self.compute_backend.get()
        workers=max(1,min(4,int(self.raw_workers.get())))
        self.worker=threading.Thread(target=self._stack,args=(list(subset),out,self.normalize_var.get(),self.output_depth.get(),self.live_preview_var.get(),max(1,int(self.preview_every.get())),requested_backend,workers,method_key),daemon=True)
        self.worker.start()

    def toggle_stack_pause(self):
        if not self.stack_active:return
        if self.stack_pause_event.is_set():
            self.stack_pause_event.clear(); self._set_stack_controls(True,False)
            self.status.set(f'继续堆栈 · 当前 {self.stack_count}/{self.stack_total} 帧')
        else:
            self.stack_pause_event.set(); self._set_stack_controls(True,True)
            self.status.set(f'已暂停 · 当前 {self.stack_count}/{self.stack_total} 帧 · 可继续或使用当前结果')

    def use_current_stack(self):
        if not self.stack_active or self.stack_count < 1:return
        self.stack_pause_event.set(); self.stack_stop_event.set()
        self.status.set(f'正在固定当前 {self.stack_count} 帧结果…')
        self._set_stack_controls(False,False)

    def cancel_stack(self):
        if not self.stack_active:return
        if not messagebox.askyesno(APP_NAME,'取消本次堆栈？\n\n当前临时结果不会保存。'):return
        self.stack_cancel_requested=True; self.stack_stop_event.set(); self.stack_pause_event.clear(); self._set_stack_controls(False,False)
        self.status.set('正在取消堆栈…')

    def _stack(self, files, out, normalize, depth, live_preview=True, preview_every=1, requested_backend='自动', raw_workers=2, method='mean'):
        executor=None
        try:
            np,*_= _deps()
            backend, backend_desc, cp = choose_stack_backend(requested_backend)
            self.queue.put(('accel', (backend, backend_desc)))
            n=len(files); shape=None; ref_lum=None; stopped_by_user=False
            master_cpu=None; master_gpu=None
            raw_workers=max(1,min(int(raw_workers),4,n))
            decode_times=[]; stack_times=[]

            # Bounded prefetch: at most raw_workers decoded frames can coexist.
            # This uses threads because LibRaw/rawpy executes the heavy decoder in native code,
            # while avoiding large inter-process copies of 24–33 MP RGB arrays.
            executor=ThreadPoolExecutor(max_workers=raw_workers, thread_name_prefix='IceHaloRAW')
            futures={}
            next_submit=0
            def submit_one(i):
                if i < n and i not in futures:
                    futures[i]=executor.submit(read_linear_rgb, files[i])
            while next_submit < min(raw_workers,n):
                submit_one(next_submit); next_submit+=1

            processed=0
            for zero_idx,p in enumerate(files):
                idx=zero_idx+1
                while self.stack_pause_event.is_set() and not self.stack_stop_event.is_set():
                    time.sleep(0.05)
                if self.stack_stop_event.is_set():
                    stopped_by_user=True; break

                mode_name='Maximum' if method=='maximum' else 'Mean'
                self.queue.put(('status',f'{mode_name} · 并行解码 {idx}/{n}：{Path(p).name} · {backend}'))
                t0=time.perf_counter()
                fut=futures.pop(zero_idx)
                img=fut.result()
                decode_times.append(time.perf_counter()-t0)
                if next_submit < n:
                    submit_one(next_submit); next_submit+=1

                if shape is None:
                    shape=img.shape
                if img.shape!=shape:
                    raise RuntimeError(f'图像尺寸不一致：{Path(p).name}\n{img.shape} != {shape}')

                if normalize:
                    lum=robust_luminance(img)
                    if ref_lum is None: ref_lum=lum
                    if lum>1e-8: img=img*(ref_lum/lum)

                ts=time.perf_counter()
                if backend == 'CUDA' and cp is not None:
                    frame_gpu=cp.asarray(img, dtype=cp.float32)
                    if master_gpu is None:
                        master_gpu=frame_gpu.copy()
                    elif method == 'maximum':
                        cp.maximum(master_gpu, frame_gpu, out=master_gpu)
                    else:
                        # Incremental arithmetic mean; full master remains resident in VRAM.
                        master_gpu += (frame_gpu-master_gpu)/float(idx)
                    del frame_gpu
                else:
                    frame_cpu=img.astype(np.float32,copy=False)
                    if master_cpu is None:
                        master_cpu=frame_cpu.copy()
                    elif method == 'maximum':
                        np.maximum(master_cpu, frame_cpu, out=master_cpu)
                    else:
                        master_cpu += (frame_cpu-master_cpu)/float(idx)
                stack_times.append(time.perf_counter()-ts)
                processed=idx
                self.stack_count=idx

                self.queue.put(('progress',idx/n*100))
                self.queue.put(('stack_counter',(idx,n)))
                if live_preview and (idx==1 or idx%preview_every==0 or idx==n):
                    if backend == 'CUDA' and master_gpu is not None:
                        h,w=shape[:2]; step=max(1,int(max(h/1000,w/1500)))
                        proxy=cp.asnumpy(master_gpu[::step,::step])
                    else:
                        h,w=master_cpu.shape[:2]; step=max(1,int(max(h/1000,w/1500)))
                        proxy=master_cpu[::step,::step].copy()
                    self.queue.put(('live_preview',(proxy,idx,n)))

            if processed < 1:
                self.queue.put(('stack_cancelled',None)); return
            if stopped_by_user and getattr(self,'stack_cancel_requested',False):
                self.queue.put(('stack_cancelled',None)); return

            self.queue.put(('status','正在从计算后端生成最终 Master…'))
            if backend == 'CUDA' and master_gpu is not None:
                result=cp.asnumpy(master_gpu).astype(np.float32,copy=False)
                del master_gpu
                try: cp.get_default_memory_pool().free_all_blocks()
                except Exception: pass
            else:
                result=master_cpu.astype(np.float32,copy=True)

            save_tiff(out,result,float32=(depth=='32-bit float TIFF'))
            avg_decode=(sum(decode_times)/len(decode_times)) if decode_times else 0.0
            avg_stack=(sum(stack_times)/len(stack_times)) if stack_times else 0.0
            op_name='Maximum' if method=='maximum' else 'Mean'
            stats=f'{backend} · RAW等待均值 {avg_decode:.2f}s/帧 · {op_name} {avg_stack*1000:.1f}ms/帧 · 解码线程 {raw_workers}'
            self.queue.put(('stack_done',(out,result,processed,n,processed<n,stats,method)))
        except Exception as e:
            self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=4)))
        finally:
            if executor is not None:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
    def _push_undo(self):
        if self.working_image is None:return
        self.undo_stack.append((self.working_image.copy(), self.is_linear))
        if len(self.undo_stack)>self.max_undo: self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack or self.working_image is None:return
        self.redo_stack.append((self.working_image.copy(),self.is_linear))
        self.working_image,self.is_linear=self.undo_stack.pop(); self._update_state(); self.refresh_preview()

    def redo(self):
        if not self.redo_stack or self.working_image is None:return
        self.undo_stack.append((self.working_image.copy(),self.is_linear))
        self.working_image,self.is_linear=self.redo_stack.pop(); self._update_state(); self.refresh_preview()

    def restore_linear_master(self):
        if self.linear_master is None:return
        self._push_undo(); self.working_image=self.linear_master.copy(); self.is_linear=True; self._update_state(); self.estimate_current_stretch(); self.refresh_preview()

    def _require_image(self):
        if self.working_image is None:
            messagebox.showwarning(APP_NAME,'请先完成堆栈或打开一张图像。'); return False
        return True

    def _require_nonlinear(self):
        if not self._require_image(): return False
        if self.is_linear:
            messagebox.showwarning(APP_NAME,'当前仍是 LINEAR 图像。\n\n请先在“拉伸”标签中应用 Asinh 拉伸，再进行该非线性处理。')
            return False
        return True

    def do_stretch(self):
        if not self._require_image():return
        if not self.is_linear:
            if not messagebox.askyesno(APP_NAME,'当前已经是 NONLINEAR。仍要再次应用拉伸吗？'):return
        self._push_undo(); self.status.set('正在应用 Asinh 拉伸…'); self.update_idletasks()
        self.working_image=apply_asinh_stretch(self.working_image,self.stretch_strength.get(),self.stretch_black.get())
        self.is_linear=False; self._update_state(); self.refresh_preview(); self.status.set('Asinh 拉伸完成')

    def do_basic(self):
        if not self._require_nonlinear():return
        self._push_undo(); cfg=self._basic_cfg_from_ui(proxy_scale=1.0); self.status.set('正在应用基础调整…'); self.update_idletasks()
        self.working_image=apply_base_editor(self.working_image,cfg,None); self.reset_basic(); self.status.set('基础调整完成')

    def reset_basic(self):
        for key,default in self.basic_defaults.items():
            self._set_var_silently(self.basic_vars[key], default)
        self.refresh_preview()

    def do_curve(self):
        if not self._require_nonlinear():return
        if not self._curves_any_active():
            self.status.set('当前曲线未修改')
            return
        self._push_undo(); self.status.set('正在应用曲线…'); self.update_idletasks()
        for ch in ['RGB','红色','绿色','蓝色','亮度']:
            pts = self.curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
            if not self._curve_is_identity(ch):
                self.working_image = apply_curve_lut(self.working_image, build_curve_lut(pts, 256), ch)
        self.reset_all_curves(); self.status.set('曲线调整完成')

    def do_usm(self):
        if not self._require_nonlinear():return
        self._push_undo(); self.status.set('正在计算 USM…'); self.update_idletasks()
        self.working_image=apply_usm(self.working_image,self.usm_amount.get(),self.usm_radius.get(),self.usm_threshold.get()); self._set_var_silently(self.usm_amount, 0.0); self.refresh_preview(); self.status.set('USM 完成')

    def do_highpass(self):
        if not self._require_nonlinear():return
        if not self.hp_enabled.get():
            self.status.set('High Pass 未启用')
            return
        self._push_undo(); self.status.set('正在计算 High Pass…'); self.update_idletasks()
        if self.hp_preview_type.get() == '滤镜本体':
            self.working_image = highpass_filter(self.working_image, self.hp_radius.get())
        else:
            self.working_image = apply_highpass(self.working_image, self.hp_radius.get(), self.hp_amount.get(), self.hp_mode.get())
        self.working_image = self._apply_hp_curve(self.working_image)
        self._set_var_silently(self.hp_enabled, False)
        self.refresh_preview(); self.status.set('High Pass 完成')

    def do_emboss(self):
        if not self._require_nonlinear():return
        if not self.emboss_enabled.get():
            self.status.set('浮雕未启用')
            return
        self._push_undo(); self.status.set('正在计算浮雕…'); self.update_idletasks()
        self.working_image = apply_emboss(
            self.working_image,
            self.emboss_angle.get(),
            self.emboss_height.get(),
            self.emboss_strength.get(),
            self.emboss_opacity.get(),
            self.emboss_blend.get(),
            self.emboss_style.get()
        )
        self._set_var_silently(self.emboss_enabled, False)
        self.refresh_preview(); self.status.set('浮雕完成')

    def _hp_curve_is_identity(self, channel):
        pts=self.hp_curve_points.get(channel, [(0.0,0.0),(1.0,1.0)])
        return len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6

    def _hp_curve_active(self):
        return bool(getattr(self,'hp_curve_enabled',tk.BooleanVar(value=False)).get()) and any(not self._hp_curve_is_identity(ch) for ch in ['RGB','红色','绿色','蓝色','亮度'])

    def _apply_hp_curve(self, img):
        if not self._hp_curve_active():
            return img
        out=img
        for ch in ['RGB','红色','绿色','蓝色','亮度']:
            pts=self.hp_curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
            if not self._hp_curve_is_identity(ch):
                out=apply_curve_lut(out, build_curve_lut(pts, 256), ch)
        return out

    def _hp_curve_hist_source(self):
        np,*_= _deps()
        img=self._preview_base_image()
        if img is None:
            return None
        return np.clip(img.astype(np.float32),0,1)

    def open_hp_curve_dialog(self):
        if not self._require_nonlinear():
            return
        StandaloneHPCurveDialog(self)

    def _update_state(self):
        if self.working_image is None:
            self.detail.set('LINEAR · 尚未生成 Master'); return
        h,w=self.working_image.shape[:2]
        stage='LINEAR · 32-bit Float' if self.is_linear else 'NONLINEAR · 32-bit Float'
        self.detail.set(f'{stage} · {w}×{h}')

    def _main_preview_current_scale(self):
        img=getattr(self,'_last_display_preview',None)
        if img is None:return max(0.01,float(getattr(self,'preview_zoom',1.0)))
        h,w=img.shape[:2];c=self.preview_canvas;cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);fit=min(cw/max(w,1),ch/max(h,1))
        return fit if getattr(self,'preview_fit_mode',True) else max(0.01,float(getattr(self,'preview_zoom',1.0)))
    def _main_preview_update_zoom_text(self,scale=None):
        if not hasattr(self,'preview_zoom_text'):return
        if getattr(self,'preview_fit_mode',True):self.preview_zoom_text.set('Fit')
        else:
            sc=self._main_preview_current_scale() if scale is None else float(scale);self.preview_zoom_text.set(f'{sc*100:.0f}%')
    def _main_preview_wheel(self,e):
        try:self._main_preview_zoom_step(1 if getattr(e,'delta',0)>0 else -1,getattr(e,'x',None),getattr(e,'y',None))
        except Exception:pass
        return 'break'
    def _main_preview_wheel_linux(self,e,direction):self._main_preview_zoom_step(direction,getattr(e,'x',None),getattr(e,'y',None));return 'break'
    def _main_preview_set_zoom(self,scale):
        old=self._main_preview_current_scale();new=max(0.05,min(20.0,float(scale)));self._main_preview_adjust_pan(old,new,None,None);self.preview_zoom=new;self.preview_fit_mode=False;self._main_preview_update_zoom_text(new);self._main_preview_redraw();self.preview_canvas.focus_set();return 'break'
    def _main_preview_zoom_step(self,direction,x=None,y=None):
        old=self._main_preview_current_scale();factor=1.12 if direction>0 else 1/1.12;new=max(0.05,min(20.0,old*factor))
        if abs(new-old)<1e-9:return
        self._main_preview_adjust_pan(old,new,x,y);self.preview_zoom=new;self.preview_fit_mode=False;self._main_preview_update_zoom_text(new);self._main_preview_redraw();self.status.set(f'预览缩放：{new*100:.0f}% · Z 回到 Fit')
    def _main_preview_adjust_pan(self,old_scale,new_scale,x=None,y=None):
        try:
            c=self.preview_canvas;cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];mx=cw/2 if x is None else float(x);my=ch/2 if y is None else float(y);rx=mx-(cw/2+px);ry=my-(ch/2+py);ratio=new_scale/max(old_scale,1e-9);self.preview_pan=[mx-cw/2-rx*ratio,my-ch/2-ry*ratio]
        except Exception:self.preview_pan=[0.0,0.0]
    def _main_preview_pan_start(self,e):
        self.preview_canvas.focus_set()
        if getattr(self,'preview_fit_mode',True):self.preview_pan_anchor=None;return 'break'
        self.preview_pan_anchor=(float(e.x),float(e.y),float(self.preview_pan[0]),float(self.preview_pan[1]));return 'break'
    def _main_preview_pan_drag(self,e):
        if not self.preview_pan_anchor:return 'break'
        x0,y0,px0,py0=self.preview_pan_anchor
        self.preview_pan=[px0+float(e.x)-x0,py0+float(e.y)-y0]
        self._main_preview_move_canvas_image_fast()
        return 'break'

    def _main_preview_move_canvas_image_fast(self):
        try:
            c=self.preview_canvas;item=getattr(self,'preview_image_item',None)
            if not item:return
            cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2]
            c.coords(item,int(cw/2+px),int(ch/2+py))
        except Exception:pass
    def _main_preview_pan_end(self,e):self.preview_pan_anchor=None;return 'break'
    def _main_preview_fit(self):
        self.preview_fit_mode=True;self.preview_pan=[0.0,0.0];self._main_preview_update_zoom_text();self._main_preview_redraw();self.preview_canvas.focus_set();self.status.set('预览已回到 Fit');return 'break'
    def _main_preview_redraw(self):
        disp=getattr(self,'_last_display_preview',None)
        if disp is None:
            if self.working_image is None and self.stack_preview_image is None:return
            self.refresh_preview();return
        self._render_main_preview(disp,update_hist=False)

    def _render_main_preview(self,disp,update_hist=True):
        try:
            np,_,Image,ImageTk,*_=_deps();cw=max(self.preview_canvas.winfo_width(),100);ch=max(self.preview_canvas.winfo_height(),100);h,w=disp.shape[:2];fit=min(cw/max(w,1),ch/max(h,1));scale=fit if getattr(self,'preview_fit_mode',True) else max(0.05,float(getattr(self,'preview_zoom',1.0)));nw=max(1,int(w*scale));nh=max(1,int(h*scale))
            src_key=(id(disp),h,w)
            if getattr(self,'_main_preview_pil_source_key',None)!=src_key:
                self._main_preview_pil_source=Image.fromarray((np.clip(disp,0,1)*255).astype(np.uint8),'RGB');self._main_preview_pil_source_key=src_key
            pil=self._main_preview_pil_source
            if (nw,nh)!=(w,h):pil=pil.resize((nw,nh),Image.Resampling.BILINEAR if self._slider_dragging else Image.Resampling.LANCZOS)
            self.preview_photo=ImageTk.PhotoImage(pil);self.preview_canvas.delete('all');px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];cx=int(cw/2+px);cy=int(ch/2+py);self.preview_image_item=self.preview_canvas.create_image(cx,cy,image=self.preview_photo,anchor='center',tags=('preview_image',))
            if self.is_linear:badge='LINEAR · AUTO STRETCH PREVIEW' if self.auto_preview_var.get() else 'LINEAR · UNSTRETCHED'
            else:badge=f'NONLINEAR · 实时预览：{self.tabs.tab(self.tabs.select(), "text")}'
            self._main_preview_update_zoom_text(scale);zlabel='Fit' if getattr(self,'preview_fit_mode',True) else f'{scale*100:.0f}%';self.preview_canvas.create_text(10,10,anchor='nw',fill='#eeeeee',font=_ui_font(9),text=badge,tags=('preview_overlay',));self.preview_canvas.create_text(10,28,anchor='nw',fill='#d0d0d0',font=_ui_font(8),text=f'{zlabel} · 滚轮缩放 · 拖拽平移 · Z Fit',tags=('preview_overlay',))
            if update_hist and not self._slider_dragging:self.draw_histogram()
        except Exception as e:self.status.set('预览失败：'+str(e))

    def refresh_preview_fast(self):
        # Reuse the global debounced preview scheduler while curve points are dragged.
        self._slider_dragging = True
        self._schedule_preview(immediate=False)

    def refresh_preview(self):
        if self.working_image is None and self.stack_preview_image is None:return
        try:
            np, _, Image, ImageTk, *_ = _deps()
            disp = self._active_preview_image()
            if disp is None:
                return
            self._last_display_preview = disp
            self._render_main_preview(disp,update_hist=True)
        except Exception as e:
            self.status.set('预览失败：'+str(e))

    def draw_histogram(self):
        if not hasattr(self,'hist_canvas'):return
        c=self.hist_canvas; c.delete('all')
        if self.working_image is None and self.stack_preview_image is None:return
        try:
            np,*_= _deps(); img=getattr(self,'_last_display_preview',None)
            if img is None:
                img=self._active_preview_image()
            if img is None:
                return
            smp=np.clip(img[::8,::8],0,1)
            W=max(c.winfo_width(),100); H=max(c.winfo_height(),60)
            colors=['#ff6b6b','#6bff77','#6ba8ff']
            for k,col in enumerate(colors):
                hist,_=np.histogram(smp[...,k],bins=256,range=(0,1))
                hist=hist.astype(np.float64); hist=np.log1p(hist); m=hist.max() or 1; hist/=m
                pts=[]
                for i,v in enumerate(hist): pts.extend([i/(255)*(W-1), H-2-v*(H-6)])
                c.create_line(*pts,fill=col,width=1)
        except Exception: pass

    def export_current(self):
        if not self._require_image():return
        dlg=tk.Toplevel(self);dlg.title('批量导出处理分支');dlg.transient(self);dlg.grab_set();dlg.resizable(False,False)
        body=ttk.Frame(dlg,padding=14);body.pack(fill='both',expand=True)
        ttk.Label(body,text='以当前图像为共同输入，勾选要一次生成的独立处理结果。',wraplength=470).pack(anchor='w',pady=(0,8))
        ttk.Label(body,text='“USM → 通道”和“USM → 浮雕”是两条分支，互不串联。',foreground='#666666').pack(anchor='w',pady=(0,10))
        choices=[
            ('current','当前图像（不增加处理）',False),
            ('usm','仅 USM',True),
            ('usm_channel','USM → 通道混合器',True),
            ('usm_emboss','USM → 浮雕',True),
            ('usm_channel_emboss','USM → 通道混合器 → 浮雕',False),
        ]
        selected={key:tk.BooleanVar(value=default) for key,_label,default in choices}
        for key,label,_default in choices:ttk.Checkbutton(body,text=label,variable=selected[key]).pack(anchor='w',pady=2)
        name=tk.StringVar(value='IceHaloStack');fmt=tk.StringVar(value='16-bit TIFF')
        row=ttk.Frame(body);row.pack(fill='x',pady=(12,3));ttk.Label(row,text='文件名前缀').pack(side='left');ttk.Entry(row,textvariable=name,width=28).pack(side='right')
        row=ttk.Frame(body);row.pack(fill='x',pady=3);ttk.Label(row,text='格式').pack(side='left');ttk.Combobox(row,textvariable=fmt,state='readonly',width=18,values=['16-bit TIFF','PNG','JPEG']).pack(side='right')
        ttk.Label(body,text=f'当前 USM：Amount {self.usm_amount.get():g}% · Radius {self.usm_radius.get():g}px；分支使用当前通道与浮雕参数。',foreground='#666666',wraplength=470).pack(anchor='w',pady=(8,3))

        def start_export():
            enabled=[key for key,_label,_default in choices if selected[key].get()]
            if not enabled:
                messagebox.showwarning(APP_NAME,'请至少勾选一个处理结果。',parent=dlg);return
            folder=filedialog.askdirectory(title='选择批量导出文件夹',parent=dlg)
            if not folder:return
            prefix=re.sub(r'[<>:"/\\|?*]+','_',name.get().strip()) or 'IceHaloStack'
            params={
                'usm':(float(self.usm_amount.get()),float(self.usm_radius.get()),float(self.usm_threshold.get())),
                'channel':(self.channel_output.get(),bool(self.channel_mono.get()),float(self.channel_red.get()),float(self.channel_green.get()),float(self.channel_blue.get()),float(self.channel_constant.get()),bool(self.channel_noise_protect.get()),float(self.channel_noise_strength.get()),float(self.channel_noise_radius.get())),
                'emboss':(float(self.emboss_angle.get()),float(self.emboss_height.get()),float(self.emboss_strength.get()),float(self.emboss_opacity.get()),self.emboss_blend.get(),self.emboss_style.get()),
            }
            source=self.working_image.copy();format_name=fmt.get();dlg.destroy()
            self.status.set(f'正在批量导出 {len(enabled)} 个处理分支…')
            def work():
                try:
                    np,_,Image,*_=_deps();base=np.clip(source,0,1).astype(np.float32,copy=False)
                    usm_img=None
                    if any(k!='current' for k in enabled):usm_img=apply_usm(base,*params['usm'])
                    suffix={'current':'Current','usm':'USM','usm_channel':'USM_Channel','usm_emboss':'USM_Emboss','usm_channel_emboss':'USM_Channel_Emboss'}
                    written=[]
                    for key in enabled:
                        out=base if key=='current' else usm_img
                        if key in ('usm_channel','usm_channel_emboss'):out=apply_channel_mixer(out,*params['channel'])
                        if key in ('usm_emboss','usm_channel_emboss'):out=apply_emboss(out,*params['emboss'])
                        ext='.tif' if format_name=='16-bit TIFF' else ('.png' if format_name=='PNG' else '.jpg')
                        path=Path(folder)/f'{prefix}_{suffix[key]}{ext}';out=np.clip(out,0,1)
                        if ext=='.tif':save_tiff(str(path),out,float32=False)
                        elif ext=='.png':Image.fromarray((out*255).astype(np.uint8),'RGB').save(path)
                        else:Image.fromarray((out*255).astype(np.uint8),'RGB').save(path,quality=96,subsampling=0)
                        written.append(str(path))
                    self.queue.put(('variant_export_done',(folder,written)))
                except Exception as e:self.queue.put(('variant_export_error',str(e)))
            threading.Thread(target=work,daemon=True).start()
        buttons=ttk.Frame(body);buttons.pack(fill='x',pady=(12,0));ttk.Button(buttons,text='取消',command=dlg.destroy).pack(side='right');ttk.Button(buttons,text='选择文件夹并导出',style='Primary.TButton',command=start_export).pack(side='right',padx=(0,7))
        dlg.update_idletasks();dlg.geometry(f'+{self.winfo_rootx()+180}+{self.winfo_rooty()+100}')

    def _poll(self):
        try:
            while True:
                kind,val=self.queue.get_nowait()
                if kind=='status':
                    self.status.set(val)
                elif kind=='progress':
                    self.progress.set(val)
                elif kind=='stack_counter':
                    idx,total=val
                    self.stack_count=idx
                    self.stack_total=total
                    self.stack_counter_text.set(f'{idx} / {total} 帧')
                elif kind=='live_preview':
                    proxy,idx,total=val
                    # The worker sends only a reduced-resolution float32 proxy.
                    # Keep the full-resolution running mean in the worker; redraw only this proxy in Tk.
                    self.stack_preview_image=proxy
                    self.stack_count=idx
                    self.stack_total=total
                    self.stack_counter_text.set(f'{idx} / {total} 帧')
                    self.refresh_preview()
                elif kind=='stack_cancelled':
                    self.stack_preview_image=None
                    self._set_stack_controls(False,False)
                    self.progress.set(0)
                    self.stack_counter_text.set(f'0 / {self.stack_total} 帧')
                    self.status.set('堆栈已取消')
                elif kind=='accel':
                    backend,desc=val
                    self.accel_status.set((backend+' · '+desc) if backend=='CUDA' else ('CPU · '+desc))
                elif kind=='main_basic_preview':
                    serial,out,quality,err=val
                    self._main_async_preview_running=False
                    newest=(int(serial)==int(self._main_preview_request_serial))
                    try:still_basic=((not self.is_linear) and self.tabs.select()==str(self.tab_basic))
                    except Exception:still_basic=False
                    if err is None and out is not None and newest and still_basic:
                        self._last_display_preview=out
                        self._render_main_preview(out,update_hist=(quality!='drag'))
                    # If the user moved again while the worker was busy, launch exactly
                    # one new frame using the latest parameter snapshot. Old frames are
                    # never replayed, so dragging cannot build an unbounded backlog.
                    if int(self._main_preview_request_serial) > int(serial) or self._main_async_preview_pending:
                        self._main_async_preview_pending=False
                        try:self.after(0,self._run_scheduled_preview)
                        except Exception:pass
                    elif err:
                        self.status.set('预览计算失败：'+str(err))
                elif kind=='variant_export_done':
                    folder,written=val
                    self.status.set(f'批量导出完成：{len(written)} 个结果')
                    messagebox.showinfo(APP_NAME,f'批量导出完成。\n\n共 {len(written)} 个处理结果：\n{folder}',parent=self)
                elif kind=='variant_export_error':
                    self.status.set('批量导出失败')
                    messagebox.showerror(APP_NAME,'批量导出失败：\n'+str(val),parent=self)
                elif kind=='stack_done':
                    out,result,count,total,stopped_early,perf_stats,stack_method=val
                    self.progress.set(count/total*100 if total else 100)
                    self.linear_master=result.copy()
                    self.working_image=result.copy()
                    self.stack_preview_image=None
                    self.is_linear=True
                    self.image_path=out
                    self.stack_count=count
                    self.stack_total=total
                    self.stack_counter_text.set(f'{count} / {total} 帧')
                    self._set_stack_controls(False,False)
                    self.undo_stack.clear(); self.redo_stack.clear()
                    self._update_state(); self.estimate_current_stretch(); self.refresh_preview()
                    if stopped_early:
                        self.status.set(f'已使用当前结果 · {count}/{total} 帧 · {perf_stats}')
                        mode_cn='最大值' if stack_method=='maximum' else '平均值'
                        messagebox.showinfo(APP_NAME,f'已使用当前 {count}/{total} 帧的{mode_cn}堆栈结果。\n\n已保存 Master：\n{out}\n\n现在可以继续进行线性处理和拉伸。')
                    else:
                        self.progress.set(100)
                        mode_cn='最大值' if stack_method=='maximum' else '平均值'
                        self.status.set(mode_cn+'堆栈完成 · '+perf_stats)
                        messagebox.showinfo(APP_NAME,f'Linear {mode_cn}堆栈完成。\n\n已保存 Master：\n{out}\n\n现在可以直接在线性预览中检查结果，然后进入“拉伸”。')
                elif kind=='error':
                    self.stack_preview_image=None
                    self._set_stack_controls(False,False)
                    self.status.set('处理失败')
                    messagebox.showerror(APP_NAME,val)
        except Empty:
            pass
        self.after(50,self._poll)


if __name__=='__main__':
    try:
        App().mainloop()
    except Exception as e:
        root=tk.Tk(); root.withdraw(); messagebox.showerror('IceHaloStack 启动失败',str(e)+'\n\n'+traceback.format_exc(limit=4))
