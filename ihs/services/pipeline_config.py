"""Normalize fixed-pipeline configuration before touching image pixels."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


BASE_ACTIVITY_KEYS = (
    "exposure", "contrast", "highlights", "shadows", "whites", "blacks",
    "temperature", "tint", "texture", "clarity", "dehaze",
    "hsl_hue", "hsl_sat", "hsl_lum",
    "cg_shadow_s", "cg_mid_s", "cg_high_s",
    "detail_sharpen", "luma_nr", "chroma_nr",
    "opt_distortion", "opt_vignette", "opt_ca",
    "cal_red_h", "cal_red_s", "cal_green_h", "cal_green_s",
    "cal_blue_h", "cal_blue_s",
)
BASE_ACTIVITY_KEYS += tuple(
    f"mix_{color}_{axis}"
    for color in ("red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta")
    for axis in ("h", "s", "l")
)

STAGE_PARAMETER_KEYS = {
    "stretch": ("stretch_strength", "stretch_black"),
    "usm": ("usm_amount", "usm_radius", "usm_threshold", "usm_passes"),
    "background": ("bg_radius", "bg_strength"),
    "highpass": ("hp_radius", "hp_amount", "hp_mode"),
    "emboss": ("emboss_angle", "emboss_height", "emboss_amount", "emboss_opacity", "emboss_blend", "emboss_style"),
    "channel": ("channel_output", "channel_mono", "channel_red", "channel_green", "channel_blue", "channel_constant", "channel_noise", "channel_noise_strength", "channel_noise_radius"),
}


def _nonzero(value: Any) -> bool:
    try:
        return abs(float(value)) > 1e-7
    except (TypeError, ValueError):
        return True


def has_active_base(config: Mapping[str, Any]) -> bool:
    """Return whether Base contains an adjustment that changes pixels."""
    if any(_nonzero(config.get(key, 0.0)) for key in BASE_ACTIVITY_KEYS):
        return True
    if not bool(config.get("base_curve", False)):
        return False
    curves = config.get("_base_curves_runtime")
    if not isinstance(curves, Mapping):
        return False
    identity = ((0.0, 0.0), (1.0, 1.0))
    return any(tuple(tuple(point) for point in points) != identity for points in curves.values())


def compact_pipeline_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Drop inactive-stage parameters and disable a neutral Base stage."""
    result = dict(config)
    result["basic"] = bool(result.get("basic", False)) and has_active_base(result)
    if not result["basic"]:
        for key in BASE_ACTIVITY_KEYS:
            result.pop(key, None)
        for key in ("detail_radius", "cg_shadow_h", "cg_mid_h", "cg_high_h", "cg_balance"):
            result.pop(key, None)

    for stage, keys in STAGE_PARAMETER_KEYS.items():
        enabled = bool(result.get(stage, False))
        result[stage] = enabled
        if not enabled:
            for key in keys:
                result.pop(key, None)
    result["curves"] = bool(result.get("curves", False))
    result["bgr"] = bool(result["background"] or result["curves"])
    result["br"] = bool(result["channel"])
    return result
