"""Small, stable contracts shared by the UI-independent services."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, Union


PathLike = Union[str, Path]
ProgressCallback = Callable[["ProgressEvent"], None]


class CancellationToken(Protocol):
    """Read-only cancellation contract accepted by long-running services."""

    def is_cancelled(self) -> bool:
        ...


class CancellationSource:
    """Thread-safe cancellation source that can be owned by a UI or task runner."""

    def __init__(self, event: threading.Event | None = None):
        self._event = event if event is not None else threading.Event()

    @property
    def event(self) -> threading.Event:
        """Expose the event for adapters that already speak ``threading.Event``."""
        return self._event

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise ServiceCancelled("处理已取消。")


class ServiceError(RuntimeError):
    """Base exception for an invalid service request or engine failure."""


class ServiceCancelled(InterruptedError, ServiceError):
    """Raised when a service observes a cancellation request."""


@dataclass(frozen=True)
class ProgressEvent:
    """A transport-neutral progress notification.

    ``total <= 0`` means that the total is unknown.  The optional metadata is
    intentionally opaque so a future UI can display engine-specific details
    without changing the common contract.
    """

    phase: str
    completed: int = 0
    total: int = 0
    message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def fraction(self) -> float | None:
        if self.total <= 0:
            return None
        return min(1.0, max(0.0, float(self.completed) / float(self.total)))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly event payload for a future IPC adapter."""
        return {
            "phase": self.phase,
            "completed": int(self.completed),
            "total": int(self.total),
            "fraction": self.fraction,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PipelineRequest:
    """Request for the canonical timelapse processing chain."""

    image: Any
    config: Mapping[str, Any]
    curve_points: Mapping[str, Sequence[Sequence[float]]] | None = None
    stop_after: str | None = None


@dataclass(frozen=True)
class PreviewRequest:
    """Request for a reduced float preview of a processed image."""

    image: Any
    config: Mapping[str, Any]
    curve_points: Mapping[str, Sequence[Sequence[float]]] | None = None
    max_side: int = 1200
    stop_after: str | None = None


@dataclass(frozen=True)
class StackRequest:
    """Frame groups and reduction method for one stack operation."""

    groups: Sequence[Sequence[int]]
    method: str = "mean"
    reference_luminance: float | None = None


class FrameProvider(Protocol):
    """Minimal frame decoder needed by :class:`StackService`."""

    def decode(self, index: int, reference_luminance: float | None = None) -> Any:
        ...


@dataclass(frozen=True)
class ExportRequest:
    """Request for one atomic image output."""

    path: PathLike
    image: Any
    format: str = "PNG 8-bit"
    png_compression: str = "Balanced"


@dataclass(frozen=True)
class VideoExportRequest:
    """Request for encoding processed RGB frames without a disk-frame cache."""

    path: PathLike
    frames: Sequence[Any]
    format: str = "MP4 H.264"
    fps: float = 24.0
    resolution: str = "原始分辨率"
    custom_width: int = 1920
    custom_height: int = 1080
    fit_mode: str = "Fill 裁切"
