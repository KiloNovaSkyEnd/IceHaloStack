"""UI-independent application services.

The modules in :mod:`ihs.services` are the public boundary between the image
processing engine and a desktop front-end.  They deliberately contain no
Tkinter, WinUI, or Qt imports.  A UI may provide scheduling, dialogs, and
binding code around these services without becoming a dependency of the
processing code.
"""

import importlib

from .contracts import (
    CancellationSource,
    CancellationToken,
    ExportRequest,
    VideoExportRequest,
    FrameProvider,
    PipelineRequest,
    PreviewRequest,
    ProgressCallback,
    ProgressEvent,
    ServiceCancelled,
    ServiceError,
    StackRequest,
)
from .video_exporting import VideoExportService
from .processing import ImageProcessingService
from .stacking import StackService
from .exporting import ExportService

_IPC_EXPORTS = frozenset(
    (
        "AsyncJsonLineHost",
        "JsonLineHost",
        "JsonProtocolError",
        "JsonRequest",
        "JsonResponse",
        "JsonServiceAdapter",
        "JsonTaskManager",
        "IpcClient",
        "IpcClientError",
        "IpcTransportError",
        "IpcProcessExited",
        "IpcTimeoutError",
        "IpcRemoteError",
        "IpcProtocolError",
    )
)
_IPC_CLIENT_EXPORTS = frozenset(
    (
        "IpcClient",
        "IpcClientError",
        "IpcTransportError",
        "IpcProcessExited",
        "IpcTimeoutError",
        "IpcRemoteError",
        "IpcProtocolError",
    )
)


def __getattr__(name):
    """Load the optional process adapter lazily.

    Keeping the process adapters lazy prevents the ``python -m
    ihs.services.ipc`` entrypoint from importing itself once through the
    package initializer and avoids spawning-related imports for core services.
    """
    if name in _IPC_EXPORTS:
        module_name = "ipc_client" if name in _IPC_CLIENT_EXPORTS else "ipc"
        module = importlib.import_module(f"{__name__}.{module_name}")
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CancellationSource",
    "CancellationToken",
    "ExportRequest",
    "VideoExportRequest",
    "FrameProvider",
    "ImageProcessingService",
    "PipelineRequest",
    "PreviewRequest",
    "ProgressCallback",
    "ProgressEvent",
    "ServiceCancelled",
    "ServiceError",
    "StackRequest",
    "StackService",
    "ExportService",
    "VideoExportService",
    "JsonLineHost",
    "AsyncJsonLineHost",
    "JsonProtocolError",
    "JsonRequest",
    "JsonResponse",
    "JsonServiceAdapter",
    "JsonTaskManager",
    "IpcClient",
    "IpcClientError",
    "IpcTransportError",
    "IpcProcessExited",
    "IpcTimeoutError",
    "IpcRemoteError",
    "IpcProtocolError",
]
