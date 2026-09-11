"""Shared FFmpeg arguments for reliable desktop video playback."""

from __future__ import annotations


H264_MAX_WIDTH = 3840
H264_MAX_HEIGHT = 2160


def h264_video_filter() -> str:
    """Limit H.264 to the broadly accelerated UHD envelope and even dimensions."""
    return (
        f"scale='min(iw,{H264_MAX_WIDTH})':'min(ih,{H264_MAX_HEIGHT})':"
        "force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:black,setsar=1"
    )


def h264_encode_args(fps) -> list[str]:
    """Return a CFR, short-GOP H.264 profile accepted by Windows hardware decoders."""
    rate = max(1.0, float(fps))
    gop = max(1, int(round(rate)))
    # UHD above 30 fps exceeds the Level 5.1 macroblock-rate envelope. Marking
    # such a stream as 5.1 can make Windows hardware decoders show partial old
    # reference frames (tearing/mosaic) while software decoders still look fine.
    level = "5.2" if rate > 30.0 else "5.1"
    return [
        "-vf", h264_video_filter(),
        "-fps_mode", "cfr",
        "-c:v", "libx264",
        "-preset", "medium",
        "-tune", "stillimage",
        "-crf", "16",
        "-profile:v", "high",
        "-level:v", level,
        "-g", str(gop),
        "-keyint_min", str(gop),
        "-sc_threshold", "0",
        # A closed one-second GOP with one reference and no B-frames is larger
        # than the previous stream, but avoids fragile reference-frame chains
        # in several Windows Media Foundation / GPU decoder combinations.
        "-bf", "0",
        "-refs", "1",
        "-pix_fmt", "yuv420p",
        "-x264-params", "open-gop=0:repeat-headers=1:colorprim=bt709:transfer=bt709:colormatrix=bt709:force-cfr=1",
        "-color_range", "tv",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        "-movflags", "+faststart",
        "-tag:v", "avc1",
    ]
