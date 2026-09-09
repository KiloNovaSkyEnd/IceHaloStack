"""UI-independent stack/reduction service."""

from __future__ import annotations

from collections.abc import Callable
import inspect
from typing import Any

from ..dependencies import _deps
from .contracts import (
    CancellationToken,
    FrameProvider,
    ProgressCallback,
    ProgressEvent,
    ServiceCancelled,
    StackRequest,
)


def _is_cancelled(token: CancellationToken | None) -> bool:
    if token is None:
        return False
    checker = getattr(token, "is_cancelled", None)
    if checker is not None:
        return bool(checker())
    event_checker = getattr(token, "is_set", None)
    return bool(event_checker is not None and event_checker())


def _decode(provider: FrameProvider | Callable[..., Any], index: int, reference_luminance):
    if callable(provider):
        # Accept both ``decode(index)`` and ``decode(index, ref_lum)`` without
        # catching a TypeError raised by the decoder's own implementation.
        try:
            parameters = list(inspect.signature(provider).parameters.values())
            positional = [
                parameter for parameter in parameters
                if parameter.kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            accepts_varargs = any(
                parameter.kind == inspect.Parameter.VAR_POSITIONAL
                for parameter in parameters
            )
            if accepts_varargs or len(positional) >= 2:
                return provider(index, reference_luminance)
            return provider(index)
        except (TypeError, ValueError):
            # Some extension callables do not expose a signature; use the
            # full decoder contract for those objects.
            return provider(index, reference_luminance)
    return provider.decode(index, reference_luminance)


class StackService:
    """Reduce caller-supplied frame groups using a minimal decoder contract.

    Groups are explicit rather than inferred from UI variables.  This keeps
    rolling, cumulative, and leave-one-out modes compatible: the existing UI
    can continue to construct its groups while another front-end can construct
    them from its own model.  The reduction is deterministic and uses the same
    incremental mean/maximum equations as the legacy stack engine.
    """

    METHODS = frozenset(("mean", "maximum"))

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
        if _is_cancelled(self.cancellation):
            raise ServiceCancelled("堆栈处理已取消。")

    def iter_masters(self, request: StackRequest, provider: FrameProvider | Callable[..., Any]):
        """Yield one float32 RGB master per requested group."""
        method = str(request.method).lower()
        if method not in self.METHODS:
            raise ValueError(f"不支持的堆栈方法：{request.method!r}。")
        groups = tuple(tuple(group) for group in request.groups)
        total = len(groups)
        np, *_ = _deps()
        for group_index, group in enumerate(groups, 1):
            self._check_cancelled()
            if not group:
                raise ValueError(f"第 {group_index} 个堆栈分组为空。")
            master = None
            for frame_count, index in enumerate(group, 1):
                self._check_cancelled()
                image = np.asarray(
                    _decode(provider, int(index), request.reference_luminance),
                    dtype=np.float32,
                )
                if image.ndim != 3 or image.shape[-1] != 3:
                    raise ValueError(f"帧 {index} 不是 H×W×3 RGB 数据：{image.shape}。")
                if master is None:
                    master = image.copy()
                elif image.shape != master.shape:
                    raise ValueError(
                        f"堆栈分组中的帧尺寸不一致：{master.shape} 与 {image.shape}。"
                    )
                elif method == "maximum":
                    np.maximum(master, image, out=master)
                else:
                    master += (image - master) / float(frame_count)
            self._check_cancelled()
            self._emit(
                ProgressEvent(
                    "stack",
                    group_index,
                    total,
                    f"完成堆栈 {group_index}/{total}",
                    {"group_index": group_index - 1, "frame_count": len(group)},
                )
            )
            yield master.astype(np.float32, copy=False)

    def stack(self, request: StackRequest, provider: FrameProvider | Callable[..., Any]):
        """Materialize :meth:`iter_masters` as a list for simple callers."""
        return list(self.iter_masters(request, provider))
