"""UI-independent image export service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..image_io import read_linear_rgb, save_timelapse_sequence_frame_atomic
from .contracts import (
    CancellationToken,
    ExportRequest,
    ProgressCallback,
    ProgressEvent,
    ServiceCancelled,
)


class ExportService:
    """Write one processed frame without relying on a UI-owned queue."""

    def __init__(
        self,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
    ):
        self.progress = progress
        self.cancellation = cancellation

    def _check_cancelled(self) -> None:
        if self.cancellation is not None:
            checker = getattr(self.cancellation, "is_cancelled", None)
            if checker is None:
                checker = getattr(self.cancellation, "is_set", None)
            if checker is not None and checker():
                raise ServiceCancelled("导出已取消。")

    def _emit(self, event: ProgressEvent) -> None:
        if self.progress is not None:
            self.progress(event)

    def save(self, request: ExportRequest) -> Path:
        """Atomically encode one image and return its resolved output path."""
        self._check_cancelled()
        path = Path(request.path)
        if path.exists() and path.is_dir():
            raise IsADirectoryError(str(path))
        self._emit(ProgressEvent("export", 0, 1, "开始导出", {"path": str(path)}))
        save_timelapse_sequence_frame_atomic(
            path,
            request.image,
            fmt=request.format,
            png_compression=request.png_compression,
        )
        self._check_cancelled()
        self._emit(ProgressEvent("export", 1, 1, "导出完成", {"path": str(path)}))
        return path

    def save_image(self, path, image: Any, *, format="PNG 8-bit", png_compression="Balanced") -> Path:
        return self.save(ExportRequest(path, image, format, png_compression))

    def load(self, path):
        """Read an exported image through the same linear-light decoder."""
        self._check_cancelled()
        return read_linear_rgb(path)
