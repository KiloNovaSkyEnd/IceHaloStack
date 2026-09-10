"""UI-independent image processing service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..image_io import make_float_preview_proxy, read_linear_rgb
from ..node_workflow import (
    apply_flow_pipeline,
    apply_timelapse_pipeline,
    execute_shared_flow,
    scale_timelapse_cfg_for_proxy,
)
from .contracts import (
    CancellationToken,
    PipelineRequest,
    PreviewRequest,
    ProgressCallback,
    ServiceCancelled,
    ProgressEvent,
)
from .pipeline_config import compact_pipeline_config


def _cancelled(token: CancellationToken | None) -> bool:
    if token is None:
        return False
    checker = getattr(token, "is_cancelled", None)
    if checker is not None:
        return bool(checker())
    # A threading.Event is accepted as a compatibility adapter for the
    # existing Tk worker; new front-ends should use CancellationSource.
    event_checker = getattr(token, "is_set", None)
    return bool(event_checker is not None and event_checker())


class ImageProcessingService:
    """Facade over the canonical image/node workflow functions.

    The service accepts plain data and callbacks only.  It does not know how a
    task is scheduled or how progress is rendered, so the same object can be
    called by Tkinter, PySide6, WinUI 3, or a command-line worker.
    """

    def __init__(
        self,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
    ):
        self.progress = progress
        self.cancellation = cancellation

    def _emit(self, event: ProgressEvent) -> None:
        if self.progress is not None:
            self.progress(event)

    def _check_cancelled(self) -> None:
        if _cancelled(self.cancellation):
            raise ServiceCancelled("处理已取消。")

    def process(self, request: PipelineRequest):
        """Run the canonical fixed-order timelapse pipeline."""
        if not isinstance(request.config, Mapping):
            raise TypeError("PipelineRequest.config 必须是映射。")
        self._check_cancelled()
        self._emit(ProgressEvent("processing", 0, 1, "开始处理"))
        config = compact_pipeline_config(request.config)
        output = apply_timelapse_pipeline(
            request.image,
            config,
            curve_points=request.curve_points,
            stop_after=request.stop_after,
        )
        self._check_cancelled()
        self._emit(ProgressEvent("processing", 1, 1, "处理完成"))
        return output

    def process_image(
        self,
        image: Any,
        config: Mapping[str, Any],
        *,
        curve_points=None,
        stop_after: str | None = None,
    ):
        """Convenience form of :meth:`process` for UI command handlers."""
        return self.process(PipelineRequest(image, config, curve_points, stop_after))

    def process_flow(self, image: Any, flow: Mapping[str, Any]):
        """Execute a normalized node flow without requiring a window object."""
        self._check_cancelled()
        self._emit(ProgressEvent("flow", 0, 1, "开始执行节点流程"))
        output = apply_flow_pipeline(image, flow)
        self._check_cancelled()
        self._emit(ProgressEvent("flow", 1, 1, "节点流程完成"))
        return output

    def process_shared_flow(
        self,
        master: Any,
        flow: Mapping[str, Any],
        steps,
        remaining,
        cache,
        cache_state,
        stats,
        policy,
        *,
        performance=None,
    ):
        """Execute one Shared Node DAG branch through the service boundary.

        ``cache``/``stats`` are deliberately supplied by the caller so the
        existing RAM budget and performance monitor remain authoritative while
        the window no longer calls the node engine directly.
        """
        self._check_cancelled()
        output = execute_shared_flow(
            master,
            flow,
            steps,
            remaining,
            cache,
            cache_state,
            stats,
            policy,
            perf=performance,
        )
        self._check_cancelled()
        return output

    def preview(self, request: PreviewRequest):
        """Create a float proxy and process it using scaled pixel parameters.

        The returned tuple is ``(image, scale)``.  ``scale`` is the proxy-to-
        source ratio and is supplied explicitly so a front-end never has to
        infer it from dimensions.
        """
        if request.max_side <= 0:
            raise ValueError("PreviewRequest.max_side 必须大于 0。")
        self._check_cancelled()
        self._emit(ProgressEvent("preview", 0, 2, "生成预览代理"))
        proxy, scale = make_float_preview_proxy(request.image, request.max_side)
        self._check_cancelled()
        config = scale_timelapse_cfg_for_proxy(compact_pipeline_config(request.config), scale)
        self._emit(ProgressEvent("preview", 1, 2, "处理预览代理"))
        output = apply_timelapse_pipeline(
            proxy,
            config,
            curve_points=request.curve_points,
            stop_after=request.stop_after,
        )
        self._check_cancelled()
        self._emit(ProgressEvent("preview", 2, 2, "预览完成"))
        return output, scale

    def load(self, path):
        """Decode a supported image into linear-light float RGB."""
        self._check_cancelled()
        self._emit(ProgressEvent("decode", 0, 1, "读取图像"))
        image = read_linear_rgb(path)
        self._check_cancelled()
        self._emit(ProgressEvent("decode", 1, 1, "读取完成"))
        return image
