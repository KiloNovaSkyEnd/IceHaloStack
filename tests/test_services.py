from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ihs.services import (
    CancellationSource,
    ExportRequest,
    ExportService,
    ImageProcessingService,
    PipelineRequest,
    PreviewRequest,
    ProgressEvent,
    ServiceCancelled,
    StackRequest,
    StackService,
    VideoExportRequest,
    VideoExportService,
)
from ihs.image_io import read_linear_rgb, srgb_to_linear
from ihs.node_workflow import apply_timelapse_pipeline


class ServicesTest(unittest.TestCase):
    def setUp(self):
        yy, xx = np.indices((12, 16), dtype=np.float32)
        base = 0.08 + 0.01 * xx + 0.015 * yy
        self.image = np.stack((base, base * 0.9, base * 1.1), axis=2).astype(np.float32)
        self.config = {"stretch": True, "stretch_strength": 2.0, "stretch_black": 0.0}

    def test_progress_event_fraction(self):
        event = ProgressEvent("x", 1, 4, metadata={"item": 2})
        self.assertEqual(event.fraction, 0.25)
        self.assertEqual(json.loads(json.dumps(event.to_dict()))["fraction"], 0.25)
        self.assertIsNone(ProgressEvent("x", 1, 0).fraction)
        self.assertEqual(ProgressEvent("x", 99, 4).fraction, 1.0)

    def test_cancellation_is_transport_neutral(self):
        source = CancellationSource()
        self.assertFalse(source.is_cancelled())
        source.cancel()
        self.assertTrue(source.is_cancelled())
        with self.assertRaises(ServiceCancelled):
            ImageProcessingService(cancellation=source).process(
                PipelineRequest(self.image, self.config)
            )
        source.reset()
        result = ImageProcessingService(cancellation=source).process(
            PipelineRequest(self.image, self.config)
        )
        self.assertEqual(result.shape, self.image.shape)

    def test_standard_threading_event_is_accepted_during_migration(self):
        import threading

        event = threading.Event()
        event.set()
        with self.assertRaises(ServiceCancelled):
            ImageProcessingService(cancellation=event).process(
                PipelineRequest(self.image, self.config)
            )

    def test_processing_matches_core_and_emits_events(self):
        events = []
        service = ImageProcessingService(progress=events.append)
        request = PipelineRequest(self.image, self.config)
        actual = service.process(request)
        expected = apply_timelapse_pipeline(self.image, dict(self.config))
        np.testing.assert_allclose(actual, expected, rtol=0, atol=0)
        self.assertEqual([event.phase for event in events], ["processing", "processing"])
        self.assertEqual(events[-1].fraction, 1.0)

    def test_preview_returns_scale_and_proxy(self):
        events = []
        service = ImageProcessingService(progress=events.append)
        large = np.tile(self.image, (30, 30, 1))
        preview, scale = service.preview(PreviewRequest(large, self.config, max_side=256))
        self.assertEqual(preview.dtype, np.float32)
        self.assertEqual(max(preview.shape[:2]), 256)
        self.assertLess(scale, 1.0)
        self.assertEqual(events[-1].phase, "preview")
        self.assertEqual(events[-1].fraction, 1.0)

    def test_stack_service_mean_maximum_and_progress(self):
        frames = [self.image, self.image * 2.0, self.image * 0.5]
        events = []

        def decode(index, _reference=None):
            return frames[index]

        service = StackService(progress=events.append)
        request = StackRequest(((0, 1), (1, 2)), "mean")
        masters = service.stack(request, decode)
        np.testing.assert_allclose(masters[0], (frames[0] + frames[1]) / 2.0, rtol=0, atol=0)
        np.testing.assert_allclose(masters[1], (frames[1] + frames[2]) / 2.0, rtol=1e-6, atol=1e-7)
        maximum = service.stack(StackRequest(((0, 1, 2),), "maximum"), decode)[0]
        np.testing.assert_array_equal(maximum, np.maximum(np.maximum(frames[0], frames[1]), frames[2]))
        self.assertEqual([event.completed for event in events[:2]], [1, 2])

    def test_stack_service_rejects_invalid_group_and_cancels(self):
        service = StackService()
        with self.assertRaises(ValueError):
            service.stack(StackRequest(((),)), lambda index: self.image)
        source = CancellationSource()
        source.cancel()
        with self.assertRaises(ServiceCancelled):
            StackService(cancellation=source).stack(StackRequest(((0,),)), lambda index: self.image)

    def test_export_service_is_atomic_and_readable(self):
        events = []
        with tempfile.TemporaryDirectory(prefix="ihs_services_") as folder:
            target = Path(folder) / "frame.png"
            result = ExportService(progress=events.append).save(
                ExportRequest(target, self.image, "PNG 8-bit", "Fast")
            )
            self.assertEqual(result, target)
            self.assertTrue(target.exists())
            expected = srgb_to_linear(np.round(np.clip(self.image, 0, 1) * 255.0) / 255.0)
            np.testing.assert_allclose(read_linear_rgb(target), expected, rtol=0, atol=1e-7)
            self.assertFalse(list(Path(folder).glob("*.ihs_tmp.*")))
        self.assertEqual([event.phase for event in events], ["export", "export"])

    def test_video_export_service_streams_frames_without_sequence_cache(self):
        events = []
        with tempfile.TemporaryDirectory(prefix="ihs_video_service_") as folder:
            target = Path(folder) / "preview.mp4"
            result = VideoExportService(progress=events.append).save(
                VideoExportRequest(target, [self.image, self.image * 0.8], fps=12)
            )
            self.assertEqual(result, target)
            self.assertGreater(target.stat().st_size, 0)
            self.assertFalse(list(Path(folder).glob("*.ihs_tmp.*")))
        self.assertEqual(events[-1].phase, "video")
        self.assertEqual(events[-1].fraction, 1.0)

    def test_services_package_does_not_import_ui_modules(self):
        import ihs.services as services

        self.assertTrue(services.__file__.endswith("ihs\\services\\__init__.py"))
        self.assertFalse(any(name.startswith("ihs.ui") for name in services.__dict__))


if __name__ == "__main__":
    unittest.main()
