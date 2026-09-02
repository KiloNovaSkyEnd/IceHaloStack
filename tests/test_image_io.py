from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as ihs


class ImageIOTest(unittest.TestCase):
    def setUp(self):
        y, x = np.mgrid[0:12, 0:16]
        self.image = np.stack(
            ((x + 1) / 18.0, (y + 2) / 15.0, (x + y + 3) / 31.0), axis=2
        ).astype(np.float32)
        self.original = self.image.copy()

    def tearDown(self):
        np.testing.assert_array_equal(self.image, self.original)

    def test_srgb_linear_round_trip(self):
        srgb = np.linspace(0.0, 1.0, 257, dtype=np.float32)
        restored = ihs.linear_to_srgb(ihs.srgb_to_linear(srgb))
        np.testing.assert_allclose(restored, srgb, rtol=1e-5, atol=1e-6)
        self.assertEqual(restored.dtype, np.float32)

    def test_tiff_round_trips(self):
        _, tifffile, *_ = ihs._deps()
        with tempfile.TemporaryDirectory(prefix="ihs_image_io_") as folder:
            folder = Path(folder)
            f32 = folder / "float.tif"
            u16 = folder / "u16.tif"
            ihs.save_tiff(f32, self.image, float32=True)
            ihs.save_tiff(u16, self.image, float32=False)
            np.testing.assert_allclose(ihs.read_linear_rgb(f32), self.image, rtol=0, atol=0)
            expected_u16 = np.round(np.clip(self.image, 0, 1) * 65535.0).astype(np.uint16)
            np.testing.assert_array_equal(tifffile.imread(u16), expected_u16)
            np.testing.assert_allclose(ihs.read_linear_rgb(u16), self.image, rtol=0, atol=1 / 65535.0)

    def test_png_atomic_write_and_read(self):
        with tempfile.TemporaryDirectory(prefix="ihs_image_io_") as folder:
            target = Path(folder) / "frame.png"
            ihs.save_timelapse_sequence_frame_atomic(target, self.image, "PNG 8-bit", "Fast")
            expected_srgb = np.round(np.clip(self.image, 0, 1) * 255.0).astype(np.float32) / 255.0
            expected_linear = ihs.srgb_to_linear(expected_srgb)
            np.testing.assert_allclose(ihs.read_linear_rgb(target), expected_linear, rtol=0, atol=1e-7)
            self.assertFalse(list(target.parent.glob("*.ihs_tmp.*")))

    def test_resize_and_video_frame_shapes(self):
        resized = ihs.resize_float_percent_array(self.image, 50)
        self.assertEqual(resized.shape, (6, 8, 3))
        self.assertEqual(resized.dtype, np.float32)
        unchanged = ihs.resize_float_percent_array(self.image, 100)
        self.assertIs(unchanged, self.image)
        fill = ihs.prepare_video_frame(self.image, "自定义", 10, 8, "Fill 裁切")
        fit = ihs.prepare_video_frame(self.image, "自定义", 10, 8, "Fit 黑边")
        stretch = ihs.prepare_video_frame(self.image, "自定义", 10, 8, "Stretch 拉伸")
        self.assertEqual(fill.size, (10, 8))
        self.assertEqual(fit.size, (10, 8))
        self.assertEqual(stretch.size, (10, 8))

    def test_float_preview_proxy(self):
        large = np.tile(self.image, (30, 30, 1))
        proxy, scale = ihs.make_float_preview_proxy(large, 256)
        self.assertLess(scale, 1.0)
        self.assertEqual(max(proxy.shape[:2]), 256)
        self.assertEqual(proxy.dtype, np.float32)
        self.assertTrue(np.isfinite(proxy).all())


if __name__ == "__main__":
    unittest.main()
