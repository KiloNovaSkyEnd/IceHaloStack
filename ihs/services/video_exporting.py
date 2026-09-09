"""UI-independent video encoding through the bundled FFmpeg runtime."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..dependencies import get_ffmpeg_executable
from ..image_io import prepare_video_frame
from .contracts import ProgressCallback, ProgressEvent, ServiceCancelled, ServiceError, VideoExportRequest
from .processing import _cancelled


_FORMAT_ARGS = {
    "MP4 H.264": (".mp4", ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]),
    "MOV H.264": (".mov", ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]),
    "MOV ProRes": (".mov", ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]),
    "GIF": (".gif", ["-vf", "fps=15", "-loop", "0"]),
}


class VideoExportService:
    """Encode final frames directly over stdin; no intermediate frame cache."""

    def __init__(self, *, progress: ProgressCallback | None = None, cancellation=None):
        self.progress = progress
        self.cancellation = cancellation

    def _emit(self, completed: int, total: int, message: str) -> None:
        if self.progress is not None:
            self.progress(ProgressEvent("video", completed, total, message))

    def _check_cancelled(self) -> None:
        if _cancelled(self.cancellation):
            raise ServiceCancelled("视频编码已取消。")

    def save(self, request: VideoExportRequest) -> Path:
        frames = list(request.frames)
        if not frames:
            raise ServiceError("视频至少需要一帧图像。")
        if request.format not in _FORMAT_ARGS:
            raise ServiceError(f"不支持的视频格式：{request.format}。")
        if float(request.fps) <= 0:
            raise ServiceError("视频帧率必须大于 0。")

        suffix, codec_args = _FORMAT_ARGS[request.format]
        path = Path(request.path).expanduser().resolve()
        if path.suffix.lower() != suffix:
            raise ServiceError(f"{request.format} 输出必须使用 {suffix} 扩展名。")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.stem}.ihs_tmp{path.suffix}")
        temporary.unlink(missing_ok=True)

        ffmpeg = get_ffmpeg_executable()
        if not ffmpeg:
            raise ServiceError("未找到 FFmpeg；请安装运行依赖 imageio-ffmpeg。")

        first = self._prepare(frames[0], request)
        width, height = first.size
        command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s:v",
            f"{width}x{height}",
            "-r",
            str(float(request.fps)),
            "-i",
            "-",
            "-an",
            *codec_args,
            str(temporary),
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            assert process.stdin is not None
            total = len(frames)
            for index, frame in enumerate(frames, 1):
                self._check_cancelled()
                prepared = first if index == 1 else self._prepare(frame, request)
                if prepared.size != (width, height):
                    raise ServiceError("视频帧尺寸不一致。")
                process.stdin.write(prepared.convert("RGB").tobytes())
                self._emit(index, total, f"编码视频帧 {index}/{total}")
            process.stdin.close()
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            return_code = process.wait()
            if return_code != 0:
                raise ServiceError("FFmpeg 编码失败：" + stderr[-3000:])
            self._check_cancelled()
            os.replace(temporary, path)
            return path
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            temporary.unlink(missing_ok=True)
            raise
        finally:
            if process.stderr is not None:
                process.stderr.close()

    @staticmethod
    def _prepare(frame, request: VideoExportRequest):
        return prepare_video_frame(
            frame,
            request.resolution,
            request.custom_width,
            request.custom_height,
            request.fit_mode,
        )
