from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


GOLDEN_PATH = Path(__file__).with_name("stack_engine_v0_9_6_7_golden.npz")
GIB = 1024 ** 3


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def fixed_frames() -> list[np.ndarray]:
    yy, xx = np.indices((7, 9), dtype=np.float32)
    frames = []
    for index in range(6):
        base = 0.025 * (index + 1) + 0.013 * xx + 0.009 * yy
        frame = np.stack(
            (
                base * (1.0 + 0.04 * index),
                base + 0.006 * np.sin((xx + index) / 2.0),
                base * (0.91 + 0.03 * index) + 0.004 * np.cos(yy + index),
            ),
            axis=2,
        ).astype(np.float32)
        frames.append(frame)
    return frames


class Owner:
    def __init__(self, mode: str, frames: list[np.ndarray]):
        self.mode = Value(mode)
        self.frames = frames
        self.app = type("Sequence", (), {"files": list(range(len(frames)))})()
        self.cancel_event = threading.Event()
        self._active_frame_cache = None
        self._active_performance_monitor = None
        self._active_memory_policy = {
            "limit_bytes": 4 * GIB,
            "system_reserve_bytes": 0,
            "frame_cache_share": 0.5,
            "prefetch_count": 0,
            "strategy": "Balanced",
            "disk_cache": False,
        }
        self.decode_calls: list[int] = []
        self.compatibility_calls: list[tuple[tuple[int, ...], str]] = []

    def _decode(self, index, ref_lum=None):
        self.decode_calls.append(index)
        image = self.frames[index].copy()
        if ref_lum is not None:
            lum = app.robust_luminance(image)
            if lum > 1e-8:
                image *= float(ref_lum) / lum
        return image

    def _stack_group(self, indices, method, ref_lum=None):
        self.compatibility_calls.append((tuple(indices), method))
        master = None
        for count, index in enumerate(indices, 1):
            image = self._decode(index, ref_lum).astype(np.float32, copy=False)
            if master is None:
                master = image.copy()
            elif method == "maximum":
                np.maximum(master, image, out=master)
            else:
                master += (image - master) / float(count)
        return master


def _masters(mode, groups, method, compatibility=False):
    owner = Owner(mode, fixed_frames())
    values = list(app._iter_optimized_timelapse_masters(
        owner, groups, method, ref_lum=None, compatibility=compatibility
    ))
    assert owner._active_frame_cache is None
    return np.stack(values), owner


def characterize() -> dict[str, np.ndarray]:
    sliding = [[0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5]]
    cumulative = [[0], [0, 1, 2], [0, 1, 2, 3, 4], list(range(6))]
    leave_one_out = [[j for j in range(6) if j != i] for i in range(6)]
    rolling_mean, _ = _masters("滑动窗口（推荐：观察变化）", sliding, "mean")
    centered_mean, _ = _masters("中心窗口", sliding, "mean")
    cumulative_mean, _ = _masters("累计堆栈", cumulative, "mean")
    cumulative_maximum, _ = _masters("累计堆栈", cumulative, "maximum")
    loo_mean, _ = _masters("逐帧剔除", leave_one_out, "mean")
    compatibility_maximum, _ = _masters("滑动窗口（推荐：观察变化）", sliding, "maximum")
    forced_compatibility, _ = _masters("累计堆栈", cumulative, "mean", compatibility=True)
    return {
        "rolling_mean": rolling_mean,
        "centered_mean": centered_mean,
        "cumulative_mean": cumulative_mean,
        "cumulative_maximum": cumulative_maximum,
        "leave_one_out_mean": loo_mean,
        "compatibility_maximum": compatibility_maximum,
        "forced_compatibility": forced_compatibility,
        "robust_luminance": np.asarray([app.robust_luminance(fixed_frames()[3])], dtype=np.float64),
    }


class StackEngineCharacterizationTest(unittest.TestCase):
    def test_v0_9_6_7_numeric_behavior(self):
        actual = characterize()
        with np.load(GOLDEN_PATH) as expected:
            self.assertEqual(set(actual), set(expected.files))
            for key, value in actual.items():
                np.testing.assert_allclose(value, expected[key], rtol=1e-6, atol=1e-6, err_msg=key)
                self.assertEqual(value.dtype, expected[key].dtype, key)
                self.assertEqual(value.shape, expected[key].shape, key)

    def test_cache_hits_discards_and_closes(self):
        owner = Owner("滑动窗口", fixed_frames())
        policy = dict(owner._active_memory_policy, frame_cache_share=0.000001)
        cache = app.RAMFrameCache(owner, None, policy)
        first = cache.get(0)
        again = cache.get(0)
        self.assertIs(first, again)
        self.assertEqual(owner.decode_calls, [0])
        self.assertEqual(cache.stats()["hits"], 1)
        cache.discard(0)
        self.assertEqual(cache.stats()["frames"], 0)
        cache.close()
        self.assertEqual(cache.stats()["bytes"], 0)

    def test_engine_selection_and_incoming_frames(self):
        owner = Owner("滑动窗口", fixed_frames())
        self.assertEqual(app._timelapse_stack_engine_name(owner, "mean"), "Rolling Mean")
        self.assertEqual(app._timelapse_stack_engine_name(owner, "maximum"), "Compatibility Maximum")
        owner.mode.value = "累计堆栈"
        self.assertEqual(app._timelapse_stack_engine_name(owner, "mean"), "Incremental Mean")
        self.assertEqual(app._timelapse_stack_engine_name(owner, "maximum"), "Incremental Maximum")
        owner.mode.value = "逐帧剔除"
        self.assertEqual(app._timelapse_stack_engine_name(owner, "mean"), "Total-Sum Leave-One-Out Mean")
        self.assertEqual(app._next_window_incoming([[0, 1, 2], [1, 2, 3]], 0), [3])
        self.assertEqual(app._next_window_incoming([[0, 1, 2]], 0), [])

    def test_cancelled_iteration_raises(self):
        owner = Owner("滑动窗口", fixed_frames())
        owner.cancel_event.set()
        iterator = app._iter_optimized_timelapse_masters(owner, [[0, 1]], "mean")
        with self.assertRaises(InterruptedError):
            next(iterator)
        self.assertIsNone(owner._active_frame_cache)


if __name__ == "__main__":
    if "--write-golden" in sys.argv:
        np.savez_compressed(GOLDEN_PATH, **characterize())
        print(f"WROTE {GOLDEN_PATH.name}")
    else:
        unittest.main()
