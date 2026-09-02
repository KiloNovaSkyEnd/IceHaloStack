from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


def legacy_plan(ffmpeg, fmt, fps, pattern, output_root, base_name, sequence_dir):
    root = Path(output_root)
    sequence = Path(sequence_dir)
    common = [str(ffmpeg), "-y", "-framerate", str(fps), "-i", str(pattern)]
    palette_command = None
    if fmt == "MP4 H.264":
        video_path = root / f"{base_name}.mp4"
        command = common + app._ffmpeg_even_pad_args() + [
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", str(video_path),
        ]
    elif fmt == "MOV H.264":
        video_path = root / f"{base_name}.mov"
        command = common + app._ffmpeg_even_pad_args() + [
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", str(video_path),
        ]
    elif fmt == "MOV ProRes":
        video_path = root / f"{base_name}_ProRes.mov"
        command = common + app._ffmpeg_even_pad_args() + [
            "-c:v", "prores_ks", "-profile:v", "3",
            "-pix_fmt", "yuv422p10le", str(video_path),
        ]
    elif fmt == "GIF":
        video_path = root / f"{base_name}.gif"
        palette = sequence / "palette.png"
        palette_command = common + ["-vf", "palettegen=stats_mode=diff", str(palette)]
        command = common + [
            "-i", str(palette), "-lavfi", "paletteuse=dither=sierra2_4a",
            str(video_path),
        ]
    else:
        return None
    return {
        "video_path": video_path,
        "palette_command": palette_command,
        "encode_command": command,
    }


class VideoOutputCommandTest(unittest.TestCase):
    def test_v0_9_6_7_command_contract(self):
        root = Path("export")
        sequence = root / "sequence"
        pattern = sequence / "frame_%06d.png"
        plans = {
            fmt: legacy_plan("ffmpeg.exe", fmt, "23.976", pattern, root, "halo", sequence)
            for fmt in ("MP4 H.264", "MOV H.264", "MOV ProRes", "GIF")
        }
        self.assertEqual(plans["MP4 H.264"]["video_path"], root / "halo.mp4")
        self.assertEqual(plans["MOV H.264"]["video_path"], root / "halo.mov")
        self.assertEqual(plans["MOV ProRes"]["video_path"], root / "halo_ProRes.mov")
        self.assertEqual(plans["GIF"]["video_path"], root / "halo.gif")
        self.assertIn("pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:black", plans["MP4 H.264"]["encode_command"])
        self.assertEqual(plans["MP4 H.264"]["encode_command"][-8:-1], [
            "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        ])
        self.assertEqual(plans["MOV ProRes"]["encode_command"][-6:-1], [
            "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le",
        ])
        self.assertIn("palettegen=stats_mode=diff", plans["GIF"]["palette_command"])
        self.assertIn("paletteuse=dither=sierra2_4a", plans["GIF"]["encode_command"])
        self.assertIsNone(legacy_plan("ffmpeg", "unknown", 24, pattern, root, "halo", sequence))


if __name__ == "__main__":
    unittest.main()
