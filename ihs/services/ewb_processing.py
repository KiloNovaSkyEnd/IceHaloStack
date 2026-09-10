"""Headless pre-stack deflicker/exposure/white-balance preparation."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace

from ..exposure_wb import (
    _ewb_apply_to_frame, _ewb_build_correction_table, _ewb_default_config, _ewb_measure_proxy,
)
from ..image_io import make_float_preview_proxy
from .contracts import ProgressEvent, ServiceCancelled
from .processing import _cancelled


def prepare_ewb_frames(frames, supplied: Mapping[str, object] | None, *, progress=None, cancellation=None):
    config = _ewb_default_config()
    if supplied is not None and not isinstance(supplied, Mapping):
        raise ValueError("ewb 必须是对象。")
    if supplied:
        config.update(supplied)
    if not any(config.get(key, False) for key in ("deflicker_enabled", "exposure_enabled", "wb_enabled")):
        return frames
    exposure, red_log, blue_log = [], [], []
    total = len(frames)
    for index, frame in enumerate(frames):
        if _cancelled(cancellation):
            raise ServiceCancelled("去闪/曝光/白平衡分析已取消。")
        proxy, _ = make_float_preview_proxy(frame, int(config.get("proxy_max_side", 512)))
        e, r, b = _ewb_measure_proxy(proxy, config)
        exposure.append(e); red_log.append(r); blue_log.append(b)
        if progress is not None:
            progress(ProgressEvent("ewb", index + 1, total, f"分析去闪/曝光/白平衡 {index + 1}/{total}"))
    table = _ewb_build_correction_table(exposure, red_log, blue_log, config)
    owner = SimpleNamespace(_ewb_table=table)
    return [_ewb_apply_to_frame(owner, frame, index) for index, frame in enumerate(frames)]
