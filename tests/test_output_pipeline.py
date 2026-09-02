from __future__ import annotations

import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


GIB = 1024 ** 3
MIB = 1024 ** 2


class PerformanceRecorder:
    def __init__(self):
        self.touches = []
        self.stages = []
        self.counts = []
        self.output_stats = None

    def touch(self, label):
        self.touches.append(label)

    def add_stage(self, label, seconds):
        self.stages.append((label, seconds))

    def inc(self, label, amount):
        self.counts.append((label, amount))

    def record_output_stats(self, stats):
        self.output_stats = stats


class Owner:
    def __init__(self):
        self.cancel_event = threading.Event()
        self._active_output_pipeline = None
        self._active_performance_monitor = PerformanceRecorder()


def policy(strategy="Balanced"):
    return {"strategy": strategy, "limit_bytes": 2 * GIB}


class OutputPipelineTest(unittest.TestCase):
    def test_strategy_capacity_and_budget(self):
        cases = [
            ("Memory Saver", 1, max(96 * MIB, int(2 * GIB * 0.05))),
            ("Balanced", 2, max(96 * MIB, int(2 * GIB * 0.10))),
            ("Maximum Performance", 3, max(96 * MIB, int(2 * GIB * 0.16))),
        ]
        for strategy, capacity, budget in cases:
            owner = Owner()
            pipeline = app.AsyncOutputPipeline(owner, policy(strategy), queue.Queue(), "output", 0)
            self.assertEqual(pipeline.capacity, capacity)
            self.assertEqual(pipeline.byte_budget, budget)
            self.assertIs(owner._active_output_pipeline, pipeline)
            pipeline.finish()
            self.assertIsNone(owner._active_output_pipeline)

    def test_array_and_pil_writes_stats_events_and_detach(self):
        owner = Owner()
        events = queue.Queue()
        image = np.linspace(0.0, 1.0, 12 * 14 * 3, dtype=np.float32).reshape(12, 14, 3)
        pil = Image.fromarray(np.round(image * 255.0).astype(np.uint8), "RGB")
        with tempfile.TemporaryDirectory(prefix="ihs_output_pipeline_") as folder:
            root = Path(folder)
            pipeline = app.AsyncOutputPipeline(owner, policy(), events, "output", 2)
            pipeline.submit_array(root / "array.png", image, "PNG 8-bit", "Fast")
            pipeline.submit_pil_png(root / "pil.png", pil, compress_level=1)
            pipeline.finish()
            self.assertTrue((root / "array.png").exists())
            self.assertTrue((root / "pil.png").exists())
        stats = pipeline.stats()
        self.assertEqual(stats["submitted"], 2)
        self.assertEqual(stats["completed"], 2)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["queued"], 0)
        self.assertEqual(stats["queued_bytes"], 0)
        self.assertTrue(stats["writer_idle"])
        self.assertGreaterEqual(stats["peak_bytes"], image.nbytes)
        emitted = []
        while not events.empty():
            emitted.append(events.get_nowait())
        self.assertTrue(emitted)
        self.assertTrue(all(kind == "output" for kind, _ in emitted))
        perf = owner._active_performance_monitor
        self.assertEqual(perf.counts.count(("frames_written", 1)), 2)
        self.assertIsNotNone(perf.output_stats)
        self.assertEqual(perf.output_stats["completed"], 2)
        self.assertIsNone(owner._active_output_pipeline)

    def test_worker_error_propagates_and_detaches(self):
        owner = Owner()
        pipeline_module = sys.modules[app.AsyncOutputPipeline.__module__]
        real_writer = pipeline_module.save_timelapse_sequence_frame_atomic

        def fail_writer(*args, **kwargs):
            raise RuntimeError("synthetic write failure")

        pipeline_module.save_timelapse_sequence_frame_atomic = fail_writer
        try:
            pipeline = app.AsyncOutputPipeline(owner, policy(), queue.Queue(), "output", 1)
            pipeline.submit_array("ignored.png", np.zeros((2, 2, 3), dtype=np.float32))
            with self.assertRaisesRegex(RuntimeError, "synthetic write failure"):
                pipeline.finish()
            self.assertIsNotNone(pipeline.error)
            self.assertEqual(pipeline.stats()["queued_bytes"], 0)
        finally:
            pipeline_module.save_timelapse_sequence_frame_atomic = real_writer
            if owner._active_output_pipeline is not None:
                owner._active_output_pipeline.cancel()

    def test_cancelled_owner_rejects_submission(self):
        owner = Owner()
        pipeline = app.AsyncOutputPipeline(owner, policy(), queue.Queue(), "output", 1)
        owner.cancel_event.set()
        with self.assertRaises(InterruptedError):
            pipeline.submit_array("ignored.png", np.zeros((2, 2, 3), dtype=np.float32))
        pipeline.cancel()
        self.assertIsNone(owner._active_output_pipeline)


if __name__ == "__main__":
    unittest.main()
