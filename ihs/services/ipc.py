"""JSON-lines adapter for a future WinUI 3 or other process front-end.

The adapter is intentionally local and small: a caller sends one JSON object
per line and receives progress notifications followed by one response object.
It does not open a socket or create a UI; a WinUI host can run this module as a
child process and connect its stdin/stdout to the app's worker component.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, TextIO

from ..constants import VERSION
from .contracts import (
    CancellationToken,
    ExportRequest,
    PipelineRequest,
    ProgressCallback,
    ProgressEvent,
    ServiceCancelled,
    ServiceError,
    StackRequest,
    VideoExportRequest,
)
from .exporting import ExportService
from .processing import ImageProcessingService
from .stacking import StackService
from .stack_acceleration import inspect_backends
from .native_workspaces import ExposureSmoothingService, NodeWorkflowService, StorageInspectionService
from .node_exporting import NodeWorkflowExportService, NodeWorkflowPreviewService
from .video_exporting import VideoExportService


class JsonProtocolError(ServiceError):
    """Raised for malformed JSON-lines requests."""


@dataclass(frozen=True)
class JsonRequest:
    """Validated JSON-lines request envelope."""

    request_id: str | int | None
    method: str
    params: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JsonRequest":
        if not isinstance(payload, Mapping):
            raise JsonProtocolError("请求必须是 JSON 对象。")
        method = payload.get("method")
        if not isinstance(method, str) or not method.strip():
            raise JsonProtocolError("请求缺少 method。")
        params = payload.get("params", {})
        if not isinstance(params, Mapping):
            raise JsonProtocolError("params 必须是 JSON 对象。")
        request_id = payload.get("id")
        if request_id is not None and not isinstance(request_id, (str, int)):
            raise JsonProtocolError("id 只能是字符串、整数或 null。")
        return cls(request_id, method.strip(), dict(params))

    @classmethod
    def from_json(cls, line: str) -> "JsonRequest":
        try:
            payload = json.loads(line)
        except (TypeError, json.JSONDecodeError) as exc:
            raise JsonProtocolError(f"无效 JSON：{exc}") from exc
        return cls.from_dict(payload)


@dataclass(frozen=True)
class JsonResponse:
    """JSON-lines response envelope."""

    request_id: str | int | None
    ok: bool
    result: Mapping[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.request_id, "ok": bool(self.ok)}
        if self.ok:
            payload["result"] = dict(self.result or {})
        else:
            payload["error"] = self.error or "服务调用失败。"
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


class JsonServiceAdapter:
    """Map JSON requests to the same in-process services used by desktop UIs."""

    PROTOCOL = "ihs-jsonl-v1"

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

    def dispatch(self, request: JsonRequest | Mapping[str, Any]) -> dict[str, Any]:
        """Execute one request and return a JSON-compatible result payload."""
        if not isinstance(request, JsonRequest):
            request = JsonRequest.from_dict(request)
        if request.method == "ping":
            return {
                "protocol": self.PROTOCOL,
                "version": VERSION,
                "capabilities": ["ping", "compute_capabilities", "process_file", "stack_files", "node_workflow_export", "node_workflow_preview",
                                 "node_workflow_inspect", "ewb_build_corrections", "storage_inspect"],
            }
        if request.method == "compute_capabilities":
            return inspect_backends(refresh=bool(request.params.get("refresh", False)))
        if request.method == "node_workflow_inspect":
            return NodeWorkflowService().inspect(request.params.get("flow", {}))
        if request.method == "ewb_build_corrections":
            return ExposureSmoothingService().build(request.params)
        if request.method == "storage_inspect":
            paths = request.params.get("paths", [])
            if not isinstance(paths, list):
                raise JsonProtocolError("storage_inspect.paths 必须是数组。")
            return StorageInspectionService().inspect(paths)
        if request.method == "process_file":
            return self._process_file(request.params)
        if request.method == "stack_files":
            return self._stack_files(request.params)
        if request.method == "node_workflow_export":
            return NodeWorkflowExportService(progress=self._emit, cancellation=self.cancellation).save(request.params)
        if request.method == "node_workflow_preview":
            return NodeWorkflowPreviewService(progress=self._emit, cancellation=self.cancellation).save(request.params)
        raise JsonProtocolError(f"不支持的 method：{request.method}。")

    def _process_file(self, params: Mapping[str, Any]) -> dict[str, Any]:
        input_path = params.get("input_path")
        output_path = params.get("output_path")
        config = params.get("config", {})
        if not isinstance(input_path, (str, Path)) or not isinstance(output_path, (str, Path)):
            raise JsonProtocolError("process_file 需要 input_path 和 output_path。")
        if not isinstance(config, Mapping):
            raise JsonProtocolError("process_file.config 必须是 JSON 对象。")
        curves = params.get("curve_points")
        if curves is not None and not isinstance(curves, Mapping):
            raise JsonProtocolError("curve_points 必须是 JSON 对象。")
        processor = ImageProcessingService(
            progress=self._emit,
            cancellation=self.cancellation,
        )
        image = processor.load(input_path)
        output = processor.process(
            PipelineRequest(
                image,
                config,
                curves,
                params.get("stop_after"),
            )
        )
        exporter = ExportService(progress=self._emit, cancellation=self.cancellation)
        saved = exporter.save(
            ExportRequest(
                output_path,
                output,
                str(params.get("format", "PNG 8-bit")),
                str(params.get("png_compression", "Balanced")),
            )
        )
        return {
            "output_path": str(saved),
            "shape": [int(value) for value in output.shape],
            "dtype": str(output.dtype),
        }

    def _stack_files(self, params: Mapping[str, Any]) -> dict[str, Any]:
        inputs = params.get("input_paths")
        output_paths = params.get("output_paths")
        groups = params.get("groups")
        config = params.get("config", {})
        curves = params.get("curve_points")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(item, (str, Path)) for item in inputs):
            raise JsonProtocolError("stack_files.input_paths 必须是非空路径数组。")
        if not isinstance(groups, list) or not groups:
            raise JsonProtocolError("stack_files.groups 必须是非空分组数组。")
        if not all(
            isinstance(group, (list, tuple))
            and bool(group)
            and all(isinstance(index, int) and not isinstance(index, bool) for index in group)
            for group in groups
        ):
            raise JsonProtocolError("stack_files.groups 必须是非空整数分组数组。")
        if not isinstance(output_paths, list) or len(output_paths) != len(groups):
            raise JsonProtocolError("output_paths 数量必须与 groups 一致。")
        if not all(isinstance(path, (str, Path)) for path in output_paths):
            raise JsonProtocolError("stack_files.output_paths 必须是路径数组。")
        if not isinstance(config, Mapping):
            raise JsonProtocolError("stack_files.config 必须是 JSON 对象。")
        if curves is not None and not isinstance(curves, Mapping):
            raise JsonProtocolError("stack_files.curve_points 必须是 JSON 对象。")
        processor = ImageProcessingService(progress=self._emit, cancellation=self.cancellation)
        frames = [processor.load(path) for path in inputs]

        def decode(index: int):
            try:
                return frames[int(index)]
            except (IndexError, TypeError, ValueError) as exc:
                raise JsonProtocolError(f"堆栈帧索引无效：{index!r}。") from exc

        stacker = StackService(progress=self._emit, cancellation=self.cancellation)
        exporter = ExportService(progress=self._emit, cancellation=self.cancellation)
        video = params.get("video")
        if video is not None and not isinstance(video, Mapping):
            raise JsonProtocolError("stack_files.video 必须是 JSON 对象。")
        video_frames = [] if video is not None else None
        saved = []
        masters = stacker.iter_masters(
            StackRequest(
                groups,
                str(params.get("method", "mean")),
                backend=str(params.get("backend", "auto")),
            ),
            decode,
        )
        for path, master in zip(output_paths, masters):
            image = processor.process(PipelineRequest(master, config, curves))
            saved.append(exporter.save(
                ExportRequest(path, image, str(params.get("format", "PNG 8-bit")))
            ))
            if video_frames is not None:
                video_frames.append(image)
        result = {
            "output_paths": [str(path) for path in saved],
            "count": len(saved),
            "backend": stacker.backend_info.to_dict(),
        }
        if video is not None:
            video_path = video.get("output_path")
            if not isinstance(video_path, (str, Path)):
                raise JsonProtocolError("stack_files.video.output_path 不能为空。")
            encoded = VideoExportService(progress=self._emit, cancellation=self.cancellation).save(
                VideoExportRequest(
                    path=video_path,
                    frames=video_frames or [],
                    format=str(video.get("format", "MP4 H.264")),
                    fps=float(video.get("fps", 24.0)),
                    resolution=str(video.get("resolution", "原始分辨率")),
                    custom_width=int(video.get("custom_width", 1920)),
                    custom_height=int(video.get("custom_height", 1080)),
                    fit_mode=str(video.get("fit_mode", "Fill 裁切")),
                )
            )
            result["video_path"] = str(encoded)
        return result


@dataclass
class _TaskRecord:
    task_id: str
    operation: str
    cancellation: Any
    thread: threading.Thread
    state: str = "starting"


class JsonTaskManager:
    """Run JSON service operations in workers with task-scoped cancellation."""

    def __init__(self, *, runner=None):
        self._runner = runner or self._run_default
        self._tasks: dict[str, _TaskRecord] = {}
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._lock = threading.RLock()

    def _run_default(self, operation, params, cancellation, progress):
        adapter = JsonServiceAdapter(progress=progress, cancellation=cancellation)
        return adapter.dispatch(JsonRequest(None, operation, params))

    def _emit(self, payload: dict[str, Any]) -> None:
        self._events.put(payload)

    def start(self, task_id: str, operation: str, params: Mapping[str, Any] | None = None) -> None:
        task_id = str(task_id).strip()
        operation = str(operation).strip()
        if not task_id:
            raise JsonProtocolError("task_id 不能为空。")
        if not operation or operation in {"start", "cancel"}:
            raise JsonProtocolError("operation 必须是实际服务方法。")
        with self._lock:
            old = self._tasks.get(task_id)
            if old is not None and old.thread.is_alive():
                raise JsonProtocolError(f"task_id 已在运行：{task_id}。")
            cancellation = _CancellationAdapter()
            thread = threading.Thread(
                target=self._worker,
                args=(task_id, operation, dict(params or {}), cancellation),
                name=f"IHS-IPC-{task_id}",
                daemon=True,
            )
            self._tasks[task_id] = _TaskRecord(task_id, operation, cancellation, thread)
            thread.start()

    def _worker(self, task_id, operation, params, cancellation) -> None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is not None:
                record.state = "running"

        def progress(event: ProgressEvent) -> None:
            self._emit({"type": "progress", "task_id": task_id, "event": event.to_dict()})

        try:
            result = self._runner(operation, params, cancellation, progress)
            cancellation.raise_if_cancelled()
            payload = {"type": "result", "task_id": task_id, "ok": True, "result": result}
            state = "completed"
        except Exception as exc:
            cancelled = isinstance(exc, ServiceCancelled) or cancellation.is_cancelled()
            payload = {
                "type": "result",
                "task_id": task_id,
                "ok": False,
                "cancelled": bool(cancelled),
                "error": str(exc),
            }
            state = "cancelled" if cancelled else "failed"
        with self._lock:
            record = self._tasks.get(task_id)
            if record is not None:
                record.state = state
        self._emit(payload)

    def cancel(self, task_id: str) -> str:
        task_id = str(task_id).strip()
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise JsonProtocolError(f"不存在的 task_id：{task_id}。")
            if not record.thread.is_alive():
                return record.state
            record.cancellation.cancel()
            record.state = "cancelling"
            return record.state

    def poll_events(self, *, timeout: float = 0.0):
        try:
            return self._events.get(timeout=max(0.0, float(timeout)))
        except queue.Empty:
            return None

    def running(self) -> bool:
        with self._lock:
            return any(record.thread.is_alive() for record in self._tasks.values())


class _CancellationAdapter:
    """Private event-backed token used by :class:`JsonTaskManager`."""

    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self):
        if self.is_cancelled():
            raise ServiceCancelled("处理已取消。")


class JsonLineHost:
    """Synchronous stdin/stdout host for the local JSON-lines protocol."""

    def __init__(
        self,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        cancellation: CancellationToken | None = None,
    ):
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.cancellation = cancellation
        # JSON-lines is a process boundary, so make its text encoding
        # deterministic on Windows instead of inheriting the active ANSI code
        # page (which cannot represent Chinese progress/error messages).
        for stream in (self.stdin, self.stdout):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                try:
                    reconfigure(encoding="utf-8", errors="strict")
                except (TypeError, ValueError):
                    # Test doubles and custom streams may reject reconfigure;
                    # their own encoding contract remains in force.
                    pass

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.stdout.write(json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")) + "\n")
        self.stdout.flush()

    def handle_line(self, line: str) -> JsonResponse:
        request_id = None
        try:
            request = JsonRequest.from_json(line)
            request_id = request.request_id
            adapter = JsonServiceAdapter(
                cancellation=self.cancellation,
                progress=lambda event: self._write(
                    {"type": "progress", "id": request.request_id, "event": event.to_dict()}
                ),
            )
            return JsonResponse(request_id, True, adapter.dispatch(request))
        except Exception as exc:
            return JsonResponse(request_id, False, error=str(exc))

    def serve_forever(self) -> None:
        for line in self.stdin:
            if not line.strip():
                continue
            response = self.handle_line(line)
            self._write(response.to_dict())


class AsyncJsonLineHost(JsonLineHost):
    """JSON-lines host with ``start``/``progress``/``result``/``cancel``.

    A dedicated reader thread keeps stdin responsive while worker threads run
    image processing.  This is suitable for a WinUI 3 child process: the host
    acknowledges a start immediately, streams task-scoped progress, and keeps
    accepting cancellation commands.
    """

    def __init__(
        self,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        tasks: JsonTaskManager | None = None,
    ):
        super().__init__(stdin=stdin, stdout=stdout)
        self.tasks = tasks or JsonTaskManager()
        self._write_lock = threading.RLock()
        # On Windows, the first NumPy/native-extension import can block when
        # performed from a freshly-created worker thread.  Warm dependencies
        # on the host's main thread so ``start`` remains asynchronous without
        # stalling at the first decode progress event.  Keep ping usable even
        # when an optional runtime dependency is missing; the task will report
        # that service error normally.
        try:
            from ..dependencies import _deps

            _deps()
        except Exception:
            pass

    def _write(self, payload: Mapping[str, Any]) -> None:
        with self._write_lock:
            super()._write(payload)

    def handle_line(self, line: str) -> JsonResponse:
        request_id = None
        try:
            request = JsonRequest.from_json(line)
            request_id = request.request_id
            if request.method == "start":
                task_id = request.params.get("task_id")
                operation = request.params.get("operation")
                operation_params = request.params.get("params", {})
                if not isinstance(task_id, str) or not isinstance(operation, str):
                    raise JsonProtocolError("start 需要 task_id 和 operation。")
                if not isinstance(operation_params, Mapping):
                    raise JsonProtocolError("start.params 必须是 JSON 对象。")
                self.tasks.start(task_id, operation, operation_params)
                return JsonResponse(request_id, True, {"task_id": task_id, "state": "started"})
            if request.method == "cancel":
                task_id = request.params.get("task_id")
                if not isinstance(task_id, str):
                    raise JsonProtocolError("cancel 需要 task_id。")
                state = self.tasks.cancel(task_id)
                return JsonResponse(request_id, True, {"task_id": task_id, "state": state})
            if request.method == "ping":
                result = JsonServiceAdapter().dispatch(request)
                result["async_task_protocol"] = "start-cancel-v1"
                return JsonResponse(request_id, True, result)
            if request.method == "compute_capabilities":
                return JsonResponse(request_id, True, JsonServiceAdapter().dispatch(request))
            raise JsonProtocolError("异步主机只接受 start、cancel 和 ping。")
        except Exception as exc:
            return JsonResponse(request_id, False, error=str(exc))

    def _reader(self, inbox: queue.Queue):
        try:
            for line in self.stdin:
                inbox.put(line)
        finally:
            inbox.put(None)

    def _drain_events(self):
        while True:
            event = self.tasks.poll_events()
            if event is None:
                return
            self._write(event)

    def serve_forever(self) -> None:
        inbox: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._reader, args=(inbox,), name="IHS-IPC-Reader", daemon=True).start()
        eof = False
        while not eof or self.tasks.running():
            self._drain_events()
            try:
                line = inbox.get(timeout=0.05)
            except queue.Empty:
                continue
            if line is None:
                eof = True
                continue
            if line.strip():
                self._write(self.handle_line(line).to_dict())
        self._drain_events()


def main() -> None:
    """Run the JSON-lines host when launched as ``python -m ihs.services.ipc``."""
    AsyncJsonLineHost().serve_forever()


if __name__ == "__main__":
    main()
