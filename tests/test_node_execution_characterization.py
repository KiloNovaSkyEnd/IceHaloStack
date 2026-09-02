from __future__ import annotations

import copy
import sys
import unittest
from collections import Counter
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


GOLDEN_PATH = Path(__file__).with_name("node_execution_v0_9_6_7_golden.npz")
GIB = 1024 ** 3


def fixed_image():
    yy, xx = np.indices((24, 28), dtype=np.float32)
    base = 0.03 + 0.021 * xx + 0.014 * yy
    return np.stack((
        base * (0.94 + 0.04 * np.sin(xx / 4.0)),
        base * (1.01 + 0.03 * np.cos(yy / 3.0)),
        base * (0.89 + 0.05 * np.sin((xx + yy) / 6.0)),
    ), axis=2).astype(np.float32)


def active_cfg():
    cfg = {
        "stretch": True, "stretch_strength": 4.5, "stretch_black": 0.012,
        "basic": True, "exposure": 0.18, "contrast": 16.0,
        "highlights": -21.0, "shadows": 19.0, "whites": 7.0, "blacks": -6.0,
        "temperature": 9.0, "tint": -4.0, "texture": 11.0,
        "clarity": 8.0, "dehaze": 5.0, "base_curve": True,
        "hsl_hue": 3.0, "hsl_sat": 6.0, "hsl_lum": -2.0,
        "cg_shadow_h": 220.0, "cg_shadow_s": 5.0,
        "cg_mid_h": 35.0, "cg_mid_s": 4.0,
        "cg_high_h": 45.0, "cg_high_s": 3.0, "cg_balance": 8.0,
        "detail_sharpen": 7.0, "detail_radius": 1.1,
        "luma_nr": 3.0, "chroma_nr": 2.0,
        "opt_distortion": 1.0, "opt_vignette": -2.0, "opt_ca": 1.0,
        "cal_red_h": 1.0, "cal_red_s": 2.0, "cal_green_h": -1.0,
        "cal_green_s": 1.0, "cal_blue_h": 2.0, "cal_blue_s": -2.0,
        "usm": True, "usm_amount": 62.0, "usm_radius": 1.4,
        "usm_threshold": 0.8, "usm_passes": 2,
        "bgr": True, "background": True, "bg_radius": 5.0,
        "bg_strength": 21.0, "curves": True,
        "highpass": True, "hp_radius": 2.2, "hp_amount": 28.0,
        "hp_mode": "Overlay",
        "emboss": True, "emboss_angle": -118.0, "emboss_height": 1.2,
        "emboss_amount": 24.0, "emboss_opacity": 18.0,
        "emboss_blend": "Soft Light", "emboss_style": "Photoshop Emboss",
        "br": True, "channel": True, "channel_output": "灰色",
        "channel_mono": True, "channel_red": 38.0, "channel_green": 42.0,
        "channel_blue": 20.0, "channel_constant": 1.0,
        "channel_noise": True, "channel_noise_strength": 13.0,
        "channel_noise_radius": 0.7,
    }
    for color in ("red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"):
        for axis in ("h", "s", "l"):
            cfg[f"mix_{color}_{axis}"] = 0.0
    cfg["mix_blue_s"] = 7.0
    cfg["mix_yellow_l"] = -4.0
    return cfg


def active_flow(name="Active"):
    nodes = [key for key, _ in app.TimelapseNodeWindow.NODE_ORDER]
    curves = {key: [(0.0, 0.0), (1.0, 1.0)] for key in ("RGB", "红色", "绿色", "蓝色", "亮度")}
    curves["RGB"] = [(0.0, 0.0), (0.38, 0.31), (0.72, 0.79), (1.0, 1.0)]
    base_curves = copy.deepcopy(curves)
    base_curves["RGB"] = [(0.0, 0.0), (0.45, 0.40), (1.0, 1.0)]
    return {
        "name": name,
        "cfg": active_cfg(),
        "curves": curves,
        "base_curves": base_curves,
        "present_nodes": nodes,
        "layout": {},
        "edges": [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)],
        "output": {"export_enabled": True, "save_sequence": True},
    }


def harness():
    window = object.__new__(app.TimelapseNodeWindow)
    defaults = active_cfg()
    window._default_cfg = lambda: copy.deepcopy(defaults)
    window._active_performance_monitor = None
    return window


def characterize():
    window = harness()
    flow = window._normalize_flow(active_flow())
    image = fixed_image()
    result = {}
    for node in ("stretch", "basic", "usm", "bgr", "highpass", "emboss", "br"):
        result[f"node_{node}"] = window._apply_single_flow_node(image.copy(), node, flow)
    result["full_pipeline"] = window._apply_flow_pipeline(image, flow)

    twin = copy.deepcopy(flow)
    plans, occurrences, _ = window._prepare_shared_node_dag([flow, twin])
    remaining = Counter(occurrences)
    cache = {}
    cache_state = {"bytes": 0, "peak": 0}
    stats = {"hits": 0, "computes": 0, "stores": 0, "budget_skips": 0}
    policy = {
        "strategy": "Balanced", "limit_bytes": 4 * GIB,
        "system_reserve_bytes": 0,
    }
    first = window._execute_shared_flow(
        image, flow, plans[0], remaining, cache, cache_state, stats, policy
    )
    window._release_shared_flow_refs(plans[0], remaining, cache, cache_state)
    second = window._execute_shared_flow(
        image, twin, plans[1], remaining, cache, cache_state, stats, policy
    )
    window._release_shared_flow_refs(plans[1], remaining, cache, cache_state)
    result["dag_first"] = first
    result["dag_second"] = second
    result["dag_stats"] = np.asarray([
        stats["hits"], stats["computes"], stats["stores"], stats["budget_skips"],
        cache_state["bytes"], len(cache), len(remaining),
    ], dtype=np.int64)
    return result


class NodeExecutionCharacterizationTest(unittest.TestCase):
    def test_v0_9_6_7_pixel_behavior(self):
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
