from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app
import ihs.output_pipeline as output_pipeline


class VideoOutputCommandTest(unittest.TestCase):
    def test_v0_9_6_7_command_contract(self):
        root = Path("export")
        sequence = root / "sequence"
        pattern = sequence / "frame_%06d.png"
        plans = {
            fmt: output_pipeline._build_ffmpeg_video_plan(
                "ffmpeg.exe", fmt, "23.976", pattern, root, "halo", sequence
            )
            for fmt in ("MP4 H.264", "MOV H.264", "MOV ProRes", "GIF")
        }
        self.assertEqual(plans["MP4 H.264"]["video_path"], root / "halo.mp4")
        self.assertEqual(plans["MOV H.264"]["video_path"], root / "halo.mov")
        self.assertEqual(plans["MOV ProRes"]["video_path"], root / "halo_ProRes.mov")
        self.assertEqual(plans["GIF"]["video_path"], root / "halo.gif")
        self.assertTrue(any(
            "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:black" in arg
            for arg in plans["MP4 H.264"]["encode_command"]
        ))
        h264 = plans["MP4 H.264"]["encode_command"]
        self.assertIn("libx264", h264)
        self.assertIn("cfr", h264)
        self.assertIn("5.1", h264)
        self.assertIn("bt709", h264)
        self.assertIn("avc1", h264)
        self.assertIn("min(iw,3840)", h264[h264.index("-vf") + 1])
        self.assertIn("min(ih,2160)", h264[h264.index("-vf") + 1])
        self.assertEqual(h264[h264.index("-g") + 1], "48")
        self.assertEqual(plans["MOV ProRes"]["encode_command"][-6:-1], [
            "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le",
        ])
        self.assertIn("palettegen=stats_mode=diff", plans["GIF"]["palette_command"])
        self.assertIn("paletteuse=dither=sierra2_4a", plans["GIF"]["encode_command"])
        self.assertIsNone(output_pipeline._build_ffmpeg_video_plan(
            "ffmpeg", "unknown", 24, pattern, root, "halo", sequence
        ))

    def test_runner_preserves_subprocess_and_performance_contract(self):
        class Perf:
            def __init__(self):
                self.touches = []
                self.stages = []

            def touch(self, label):
                self.touches.append(label)

            def add_stage(self, label, seconds):
                self.stages.append((label, seconds))

        perf = Perf()
        completed = SimpleNamespace(returncode=0, stderr="")
        with mock.patch.object(output_pipeline.subprocess, "run", return_value=completed) as run:
            actual = output_pipeline._run_ffmpeg_command(["ffmpeg", "-version"], perf)
        self.assertIs(actual, completed)
        run.assert_called_once_with(
            ["ffmpeg", "-version"], capture_output=True, text=True,
            creationflags=getattr(output_pipeline.subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(perf.touches, ["ffmpeg"])
        self.assertEqual(len(perf.stages), 1)
        self.assertEqual(perf.stages[0][0], "ffmpeg")


if __name__ == "__main__":
    unittest.main()
