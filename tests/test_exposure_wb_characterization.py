from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


GOLDEN_PATH = Path(__file__).with_name("exposure_wb_v0_9_6_7_golden.npz")
ARRAY_KEYS = (
    "exposure_smooth",
    "rlog_smooth",
    "blog_smooth",
    "exposure_target",
    "rlog_target",
    "blog_target",
    "flicker_metric",
    "deflicker_correction",
    "temp_metric",
    "tint_metric",
    "temp_target",
    "tint_target",
    "ev_correction",
    "r_gain",
    "b_gain",
    "contrast_correction",
    "highlights_correction",
    "shadows_correction",
    "whites_correction",
    "blacks_correction",
)


def _fixed_proxy() -> np.ndarray:
    yy, xx = np.indices((48, 64), dtype=np.float32)
    base = 0.04 + 0.58 * (xx / 63.0) + 0.16 * (yy / 47.0)
    image = np.stack(
        (
            base * (0.92 + 0.06 * np.sin(xx / 7.0)),
            base * (1.01 + 0.04 * np.cos(yy / 6.0)),
            base * (0.87 + 0.05 * np.sin((xx + yy) / 9.0)),
        ),
        axis=2,
    ).astype(np.float32)
    image[5, 7] = np.asarray([np.nan, 0.2, 0.3], dtype=np.float32)
    image[12, 21] = 1.0
    return image


def characterize() -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    proxy = _fixed_proxy()
    full = app._ewb_measure_proxy(proxy, {"analysis_region": "全画面"})
    auto = app._ewb_measure_proxy(proxy, {"analysis_region": "自动有效区域"})
    roi_cfg = {
        "analysis_region": "自定义 ROI",
        "roi_x": 12.5,
        "roi_y": 18.75,
        "roi_w": 62.5,
        "roi_h": 56.25,
    }
    roi = app._ewb_analysis_crop(proxy, roi_cfg)
    result["measure_full"] = np.asarray(full, dtype=np.float64)
    result["measure_auto"] = np.asarray(auto, dtype=np.float64)
    result["measure_roi"] = np.asarray(app._ewb_measure_proxy(proxy, roi_cfg), dtype=np.float64)
    result["roi_shape"] = np.asarray(roi.shape, dtype=np.int64)

    x = np.arange(41, dtype=np.float64)
    exposure = 0.12 * np.sin(x / 4.3) + 0.025 * np.cos(x / 1.7)
    rlog = 0.035 * np.cos(x / 5.1) + 0.009 * ((-1.0) ** x)
    blog = -0.027 * np.sin(x / 6.2) + 0.007 * ((-1.0) ** x)
    exposure[[9, 27]] += np.asarray([0.8, -0.65])
    rlog[18] += 0.32
    blog[18] -= 0.28
    result["median"] = app._ewb_median_filter_1d(exposure, 3)
    result["clean_exposure"] = app._ewb_clean_outliers(exposure, 12)
    clean_r, clean_b = app._ewb_clean_chroma_joint(rlog, blog, 12)
    result["clean_rlog"] = clean_r
    result["clean_blog"] = clean_b
    smooth_r, smooth_b = app._ewb_smooth_chroma_joint(clean_r, clean_b, 7, 2)
    result["smooth_rlog"] = smooth_r
    result["smooth_blog"] = smooth_b
    result["gaussian"] = app._ewb_gaussian_smooth_1d(exposure, 6)
    result["temp_tint_delta"] = np.asarray(app._ewb_temp_tint_to_log_delta(35, -22))
    temp, tint = app._ewb_log_to_temp_tint(rlog, blog)
    result["temp_axis"] = temp
    result["tint_axis"] = tint

    anchors = [
        {"frame": 1, "exposure": -0.18, "temperature": -24, "tint": 7,
         "contrast": -12, "highlights": 18, "shadows": -25, "whites": 4, "blacks": -6},
        {"frame": 19, "exposure": 0.31, "temperature": 14, "tint": -9,
         "contrast": 38, "highlights": -21, "shadows": 33, "whites": 17, "blacks": -20},
        {"frame": 41, "exposure": 0.08, "temperature": 28, "tint": 11,
         "contrast": 13, "highlights": 6, "shadows": 9, "whites": -8, "blacks": 10},
    ]
    cfg = app._ewb_default_config()
    cfg.update(
        exposure_enabled=True,
        wb_enabled=True,
        deflicker_enabled=True,
        deflicker_strength=67.0,
        exposure_strength=83.0,
        exposure_radius=6,
        exposure_max_ev=1.8,
        wb_strength=76.0,
        wb_radius=8,
        wb_max_percent=28.0,
        anchor_influence=72.0,
        smoothing_amount=65.0,
        multi_pass_enabled=True,
        smoothing_passes=2,
        anchors=anchors,
    )
    table = app._ewb_build_correction_table(exposure, rlog, blog, cfg)
    for key in ARRAY_KEYS:
        result["table_" + key] = np.asarray(table[key])
    additional = app._ewb_apply_additional_smoothing_round(table, cfg)
    for key in ARRAY_KEYS:
        result["additional_" + key] = np.asarray(additional[key])

    disabled = app._ewb_default_config()
    disabled_table = app._ewb_build_correction_table(exposure, rlog, blog, disabled, [])
    result["disabled_ev"] = disabled_table["ev_correction"]
    result["disabled_r_gain"] = disabled_table["r_gain"]
    result["disabled_b_gain"] = disabled_table["b_gain"]

    source = np.linspace(0.01, 1.1, 15 * 17 * 3, dtype=np.float32).reshape(15, 17, 3)
    result["applied_frame"] = app._ewb_apply_to_frame(SimpleNamespace(_ewb_table=table), source, 18)
    result["unchanged_frame"] = app._ewb_apply_to_frame(SimpleNamespace(_ewb_table=None), source, 18)
    return result


class ExposureWhiteBalanceCharacterizationTest(unittest.TestCase):
    def test_v0_9_6_7_numeric_behavior(self):
        actual = characterize()
        with np.load(GOLDEN_PATH) as expected:
            self.assertEqual(set(actual), set(expected.files))
            for key, value in actual.items():
                np.testing.assert_allclose(value, expected[key], rtol=1e-6, atol=1e-6, err_msg=key)
                self.assertEqual(value.dtype, expected[key].dtype, key)
                self.assertEqual(value.shape, expected[key].shape, key)


if __name__ == "__main__":
    if "--write-golden" in sys.argv:
        np.savez_compressed(GOLDEN_PATH, **characterize())
        print(f"WROTE {GOLDEN_PATH.name}")
    else:
        unittest.main()
