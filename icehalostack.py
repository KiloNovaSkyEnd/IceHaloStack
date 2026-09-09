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
from ihs.services import (
    CancellationSource, CancellationToken, ExportRequest, ExportService,
    FrameProvider, ImageProcessingService, PipelineRequest, PreviewRequest,
    ProgressCallback, ProgressEvent, ServiceCancelled, ServiceError,
    StackRequest, StackService, JsonLineHost, JsonProtocolError, JsonRequest,
    JsonResponse, JsonServiceAdapter, AsyncJsonLineHost, JsonTaskManager,
    IpcClient, IpcClientError, IpcTransportError, IpcProcessExited,
    IpcTimeoutError, IpcRemoteError, IpcProtocolError,
)


from ihs.ui.timelapse_window import TimelapseWindow



from ihs.ui import node_window as _node_window_ui

LocalNodeEditorHistory = _node_window_ui.LocalNodeEditorHistory
FlowCurveDialog = _node_window_ui.FlowCurveDialog
BaseCurveDialog = _node_window_ui.BaseCurveDialog
StandaloneHPCurveDialog = _node_window_ui.StandaloneHPCurveDialog
TimelapseNodeWindow = _node_window_ui.TimelapseNodeWindow


from ihs.ui.storage_window import StorageManagerDialog


from ihs.ui.main_window import App


if __name__=='__main__':
    try:
        App().mainloop()
    except Exception as e:
        root=tk.Tk(); root.withdraw(); messagebox.showerror('IceHaloStack 启动失败',str(e)+'\n\n'+traceback.format_exc(limit=4))
