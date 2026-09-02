from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app
from test_node_execution_characterization import active_flow, fixed_image, harness


GOLDEN_PATH = Path(__file__).with_name("node_preview_v0_9_6_7_golden.npz")


def preview_harness():
    window = harness()
    window.preview_stage_cache = {}
    window.preview_stage_cache_order = []
    window.preview_cache_limit = 18
    window._preview_reference_serial = 7
    window.preview_token = 41
    return window


def characterize():
    window = preview_harness()
    image = fixed_image()
    flow = window._normalize_flow(active_flow("Preview"))

    fast_first = window._apply_flow_pipeline_preview_cached(
        image, flow, "fast", token=41
    )
    first_cache_size = len(window.preview_stage_cache)
    first_order = list(window.preview_stage_cache_order)
    first_values = dict(window.preview_stage_cache)

    fast_second = window._apply_flow_pipeline_preview_cached(
        image, flow, "fast", token=41
    )
    second_cache_size = len(window.preview_stage_cache)
    second_reused_same_entries = (
        first_order == window.preview_stage_cache_order
        and all(window.preview_stage_cache[key] is first_values[key] for key in first_order)
    )

    changed = copy.deepcopy(flow)
    changed["cfg"]["channel_red"] += 3.0
    fast_changed = window._apply_flow_pipeline_preview_cached(
        image, changed, "fast", token=41
    )
    changed_cache_size = len(window.preview_stage_cache)

    cache_before_hq = len(window.preview_stage_cache)
    hq = window._apply_flow_pipeline_preview_cached(image, flow, "hq", token=41)
    cache_after_hq = len(window.preview_stage_cache)
    stop_basic = window._apply_flow_pipeline_preview_cached(
        image, flow, "fast", token=41, stop_node="basic"
    )
    stale = window._apply_flow_pipeline_preview_cached(
        image, flow, "fast", token=40
    )

    return {
        "fast_first": fast_first,
        "fast_second": fast_second,
        "fast_changed": fast_changed,
        "hq": hq,
        "stop_basic": stop_basic,
        "cache_behavior": np.asarray([
            first_cache_size,
            second_cache_size,
            changed_cache_size,
            cache_before_hq,
            cache_after_hq,
            int(second_reused_same_entries),
            int(stale is None),
        ], dtype=np.int64),
    }


class NodePreviewCharacterizationTest(unittest.TestCase):
    def test_v0_9_6_7_preview_pixels_and_cache_behavior(self):
        actual = characterize()
        with np.load(GOLDEN_PATH) as expected:
            self.assertEqual(set(actual), set(expected.files))
            for key, value in actual.items():
                np.testing.assert_allclose(
                    value, expected[key], rtol=1e-6, atol=1e-6, err_msg=key
                )
                self.assertEqual(value.dtype, expected[key].dtype, key)
                self.assertEqual(value.shape, expected[key].shape, key)

    def test_preview_cache_is_lru_with_a_minimum_capacity_of_four(self):
        window = preview_harness()
        window.preview_cache_limit = 1
        for index in range(5):
            window._preview_cache_put(index, np.asarray([index], dtype=np.float32))
        self.assertEqual(window.preview_stage_cache_order, [1, 2, 3, 4])
        self.assertNotIn(0, window.preview_stage_cache)
        self.assertEqual(float(window._preview_cache_get(1)[0]), 1.0)
        self.assertEqual(window.preview_stage_cache_order, [2, 3, 4, 1])
        window._clear_preview_stage_cache()
        self.assertEqual(window.preview_stage_cache, {})
        self.assertEqual(window.preview_stage_cache_order, [])


if __name__ == "__main__":
    if "--write-golden" in sys.argv:
        np.savez_compressed(GOLDEN_PATH, **characterize())
        print(f"WROTE {GOLDEN_PATH.name}")
    else:
        unittest.main()
