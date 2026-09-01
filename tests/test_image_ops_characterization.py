from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as ihs


GOLDEN_PATH = Path(__file__).with_name("image_ops_v0_9_6_7_golden.npz")


def fixed_image() -> np.ndarray:
    rng = np.random.default_rng(967)
    image = rng.uniform(0.01, 0.96, size=(24, 32, 3)).astype(np.float32)
    image[0, 0] = (0.0, 0.5, 1.0)
    image[-1, -1] = (1.0, 0.0, 0.25)
    return image


def active_base_config() -> dict:
    cfg = {
        "exposure": 0.35,
        "contrast": 22.0,
        "highlights": -31.0,
        "shadows": 28.0,
        "whites": 11.0,
        "blacks": -9.0,
        "temperature": 17.0,
        "tint": -12.0,
        "texture": 19.0,
        "clarity": 14.0,
        "dehaze": 9.0,
        "base_curve": True,
        "hsl_hue": 7.0,
        "hsl_sat": 13.0,
        "hsl_lum": -8.0,
        "cg_shadow_h": 215.0,
        "cg_shadow_s": 18.0,
        "cg_mid_h": 42.0,
        "cg_mid_s": 9.0,
        "cg_high_h": 28.0,
        "cg_high_s": 15.0,
        "cg_balance": 6.0,
        "detail_sharpen": 24.0,
        "detail_radius": 1.4,
        "luma_nr": 8.0,
        "chroma_nr": 12.0,
        "opt_distortion": 7.0,
        "opt_vignette": -11.0,
        "opt_ca": 6.0,
        "cal_red_h": 4.0,
        "cal_red_s": 7.0,
        "cal_green_h": -3.0,
        "cal_green_s": 5.0,
        "cal_blue_h": 6.0,
        "cal_blue_s": -8.0,
        "_proxy_scale": 0.75,
    }
    for color in ("red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"):
        cfg[f"mix_{color}_h"] = 0.0
        cfg[f"mix_{color}_s"] = 0.0
        cfg[f"mix_{color}_l"] = 0.0
    cfg.update(mix_red_h=5.0, mix_red_s=12.0, mix_blue_l=-9.0, mix_aqua_h=-4.0)
    return cfg


def characterize() -> dict[str, np.ndarray]:
    image = fixed_image()
    curve = [(0.0, 0.0), (0.18, 0.11), (0.55, 0.68), (1.0, 1.0)]
    curve_points = {
        "RGB": curve,
        "红色": [(0.0, 0.0), (0.5, 0.56), (1.0, 1.0)],
        "绿色": [(0.0, 0.0), (1.0, 1.0)],
        "蓝色": [(0.0, 0.0), (1.0, 1.0)],
        "亮度": [(0.0, 0.0), (1.0, 1.0)],
    }
    grading = {
        "cg_balance": -12.0,
        "cg_shadow_h": 218.0,
        "cg_shadow_s": 24.0,
        "cg_mid_h": 36.0,
        "cg_mid_s": -11.0,
        "cg_high_h": 51.0,
        "cg_high_s": 17.0,
    }
    return {
        "input": image,
        "asinh": ihs.apply_asinh_stretch(image, 13.5, 0.018),
        "basic": ihs.apply_basic(image, 0.42, 23, -37, 31, 12, -14, 18, -9, 16, 7),
        "curve_rgb": ihs.apply_curve_lut(image, ihs.build_curve_lut(curve, 256), "RGB"),
        "curve_red": ihs.apply_curve_lut(image, ihs.build_curve_lut(curve, 256), "红色"),
        "hsl": ihs.apply_global_hsl(image, 19, 27, -13),
        "grading": ihs.apply_color_grading(image, grading),
        "usm": ihs.apply_usm(image, 86, 1.7, 0.012),
        "highpass": ihs.apply_highpass(image, 3.2, 74, "Soft Light"),
        "emboss": ihs.apply_emboss(image, -128, 1.6, 83, 61, "Overlay", "Photoshop Emboss"),
        "channel": ihs.apply_channel_mixer(image, "蓝色", False, -18, 37, 112, 3, True, 28, 0.9),
        "channel_mono": ihs.apply_channel_mixer(image, "灰色", True, 41, 33, 26, -2, False, 0, 0.8),
        "base_active": ihs.apply_base_editor(image, active_base_config(), curve_points),
        "base_neutral": ihs.apply_base_editor(image, {}, None),
    }


class ImageOpsCharacterizationTest(unittest.TestCase):
    def test_v0_9_6_7_pixels_are_unchanged(self):
        self.assertTrue(GOLDEN_PATH.exists(), f"missing golden fixture: {GOLDEN_PATH}")
        actual = characterize()
        with np.load(GOLDEN_PATH, allow_pickle=False) as expected:
            self.assertEqual(set(expected.files), set(actual))
            for name, value in actual.items():
                self.assertEqual(value.dtype, expected[name].dtype, name)
                self.assertEqual(value.shape, expected[name].shape, name)
                np.testing.assert_allclose(value, expected[name], rtol=1e-6, atol=1e-6, err_msg=name)


if __name__ == "__main__":
    if "--generate" in sys.argv:
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(GOLDEN_PATH, **characterize())
        print(f"generated {GOLDEN_PATH}")
    else:
        unittest.main()
