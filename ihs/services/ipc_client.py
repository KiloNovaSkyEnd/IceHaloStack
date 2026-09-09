"""Client-side transport for the local JSON-lines service host.

This module deliberately contains no UI code.  It owns the child process,
serializes requests as UTF-8 JSON-lines, correlates request responses, and
routes task-scoped progress/result events to a queue that a Tk, PySide6, or
WinUI 3 adapter can consume on its own thread.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
import itertools
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from .ipc import JsonProtocolError, JsonResponse
from .contracts import ServiceError


class IpcClientError(ServiceError):
    """Base exception for client-side transport or remote service failures."""


class IpcTransportError(IpcClientError):
    """Raised when the child process or its JSON stream becomes unusable."""


class IpcProcessExited(IpcTransportError):
    """Raised when the service process exits before a response arrives."""


class IpcTimeoutError(IpcTransportError):
    """Raised when a request or task does not complete before its deadline."""


class IpcRemoteError(IpcClientError):
    """A valid JSON response reported ``ok: false``."""

    def __init__(self, message: str, *, request_id: str | int | None = None):
        super().__init__(message)
        self.request_id = request_id


class IpcProtocolError(IpcClientError):
    """Raised when the child emits a malformed or unexpected JSON message."""


class IpcClient:
    """Own one ``AsyncJsonLineHost`` child process.

    ``request`` is synchronous and returns the remote ``result`` mapping.
    ``start_task`` and ``cancel_task`` only wait for their short acknowledgements;
    long-running work is consumed with ``poll_event`` or ``wait_task``.
    """

    DEFAULT_MODULE = "ihs.services.ipc"

    def __init__(
        self,
        command: Sequence[str | Path] | None = None,
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        request_timeout: float = 30.0,
        stderr_history: int = 80,
    ):
        if command is None:
            command = (sys.executable, "-m", self.DEFAULT_MODULE)
        if isinstance(command, (str, bytes, Path)):
            raise TypeError("command 必须是参数序列，而不是单个字符串。")
        command = tuple(str(part) for part in command)
        if not command:
            raise ValueError("command 不能为空。")
        if float(request_timeout) <= 0:
            raise ValueError("request_timeout 必须大于 0。")
        self.command = command
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self.request_timeout = float(request_timeout)
        self._stderr_history_limit = max(1, int(stderr_history))

        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._write_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._pending: dict[str, queue.Queue[Any]] = {}
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._task_events: dict[str, queue.Queue[Any]] = {}
        self._task_states: dict[str, str] = {}
        self._task_results: dict[str, dict[str, Any]] = {}
        self._request_counter = itertools.count(1)
        self._task_counter = itertools.count(1)
        self._fatal: IpcTransportError | None = None
        self._stderr_lines: deque[str] = deque(maxlen=self._stderr_history_limit)
        self._closing = False
        self._closed = False

    def __enter__(self) -> "IpcClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> "IpcClient":
        """Start the child host, or return the already-running client."""
        with self._state_lock:
            if self._closed:
                raise IpcTransportError("IPC 客户端已经关闭。")
            if self._process is not None and self._process.poll() is None:
                return self
            if self._fatal is not None:
                raise self._fatal
            self._closing = False
            try:
                process = subprocess.Popen(
                    list(self.command),
                    cwd=self.cwd,
                    env=self.env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    bufsize=1,
                )
            except OSError as exc:
                raise IpcTransportError(f"无法启动 IPC 服务进程：{exc}") from exc
            self._process = process
            self._reader_thread = threading.Thread(
                target=self._read_stdout,
                args=(process,),
                name="IHS-IPC-Client-Reader",
                daemon=True,
            )
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                args=(process,),
                name="IHS-IPC-Client-Stderr",
                daemon=True,
            )
            self._reader_thread.start()
            self._stderr_thread.start()
        return self

    @property
    def process(self) -> subprocess.Popen[str] | None:
        """Return the underlying process for diagnostics, if started."""
        return self._process

    @property
    def returncode(self) -> int | None:
        process = self._process
        return None if process is None else process.poll()

    def is_alive(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    def stderr_tail(self) -> str:
        with self._state_lock:
            return "".join(self._stderr_lines)

    def close(self, *, timeout: float = 2.0) -> None:
        """Close stdin and stop the child, terminating it if it will not exit."""
        with self._state_lock:
            if self._closed:
                return
            self._closing = True
            self._closed = True
            process = self._process
            pending = list(self._pending.values())
            self._pending.clear()
        error = IpcTransportError("IPC 客户端已关闭。")
        for waiter in pending:
            try:
                waiter.put_nowait(error)
            except queue.Full:
                pass
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=max(0.0, float(timeout)))
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=1.0)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        for thread in (self._reader_thread, self._stderr_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _next_request_id(self) -> str:
        return f"client-{next(self._request_counter)}"

    def _next_task_id(self) -> str:
        return f"task-{next(self._task_counter)}"

    @staticmethod
    def _key(value: Any) -> str:
        return str(value)

    def _ensure_started(self) -> subprocess.Popen[str]:
        if self._closed:
            raise IpcTransportError("IPC 客户端已经关闭。")
        if self._process is None:
            self.start()
        process = self._process
        if process is None:
            raise IpcTransportError("IPC 服务进程尚未启动。")
        if process.poll() is not None:
            with self._state_lock:
                error = self._fatal or IpcProcessExited(
                    f"IPC 服务进程已退出（code={process.returncode}）。"
                )
            raise error
        return process

    def _send(self, payload: Mapping[str, Any]) -> None:
        process = self._ensure_started()
        line = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._write_lock:
            try:
                if process.stdin is None:
                    raise IpcTransportError("IPC 服务进程 stdin 不可用。")
                process.stdin.write(line)
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                error = IpcTransportError(f"写入 IPC 请求失败：{exc}")
                self._set_fatal(error)
                raise error from exc

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send one request and return its remote result mapping."""
        method = str(method).strip()
        if not method:
            raise JsonProtocolError("IPC method 不能为空。")
        if params is not None and not isinstance(params, Mapping):
            raise JsonProtocolError("IPC params 必须是 JSON 对象。")
        self._ensure_started()
        request_id = self._next_request_id()
        waiter: queue.Queue[Any] = queue.Queue(maxsize=1)
        key = self._key(request_id)
        with self._state_lock:
            if self._fatal is not None:
                raise self._fatal
            self._pending[key] = waiter
        try:
            self._send({"id": request_id, "method": method, "params": dict(params or {})})
            wait_seconds = self.request_timeout if timeout is None else max(0.0, float(timeout))
            try:
                message = waiter.get(timeout=wait_seconds)
            except queue.Empty as exc:
                raise IpcTimeoutError(
                    f"IPC 请求超时：method={method!r}, id={request_id!r}。"
                ) from exc
            if isinstance(message, Exception):
                raise message
            response = self._response_from_payload(message, request_id)
            if not response.ok:
                raise IpcRemoteError(response.error or "远程服务调用失败。", request_id=request_id)
            return dict(response.result or {})
        finally:
            with self._state_lock:
                self._pending.pop(key, None)

    @staticmethod
    def _response_from_payload(payload: Any, expected_id: str) -> JsonResponse:
        if not isinstance(payload, Mapping):
            raise IpcProtocolError("IPC 响应必须是 JSON 对象。")
        request_id = payload.get("id")
        if str(request_id) != str(expected_id):
            raise IpcProtocolError(f"IPC 响应 id 不匹配：{request_id!r}。")
        ok = payload.get("ok")
        if not isinstance(ok, bool):
            raise IpcProtocolError("IPC 响应缺少布尔 ok 字段。")
        result = payload.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise IpcProtocolError("IPC 响应 result 必须是 JSON 对象。")
        error = payload.get("error")
        if error is not None and not isinstance(error, str):
            raise IpcProtocolError("IPC 响应 error 必须是字符串。")
        return JsonResponse(request_id, ok, dict(result or {}) if result is not None else None, error)

    def ping(self, *, timeout: float | None = None) -> dict[str, Any]:
        return self.request("ping", timeout=timeout)

    def start_task(
        self,
        operation: str,
        params: Mapping[str, Any] | None = None,
        *,
        task_id: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Start a task and return its task ID after the start acknowledgement."""
        if params is not None and not isinstance(params, Mapping):
            raise JsonProtocolError("任务 params 必须是 JSON 对象。")
        task_id = self._next_task_id() if task_id is None else str(task_id).strip()
        if not task_id:
            raise JsonProtocolError("task_id 不能为空。")
        with self._state_lock:
            # Keep a bounded per-task history for ``wait_task``.  The global
            # event queue remains lossless for normal UI polling, while a UI
            # that only polls globally cannot make an unattended task queue
            # grow without bound.  Reusing an ID starts with a clean history.
            events = self._task_events.setdefault(task_id, queue.Queue(maxsize=256))
            while True:
                try:
                    events.get_nowait()
                except queue.Empty:
                    break
            self._task_states[task_id] = "starting"
            self._task_results.pop(task_id, None)
        try:
            result = self.request(
                "start",
                {"task_id": task_id, "operation": str(operation), "params": dict(params or {})},
                timeout=timeout,
            )
        except Exception:
            with self._state_lock:
                self._task_states.pop(task_id, None)
                self._task_events.pop(task_id, None)
            raise
        if str(result.get("task_id", task_id)) != task_id:
            raise IpcProtocolError("start 响应中的 task_id 不匹配。")
        with self._state_lock:
            self._task_states[task_id] = str(result.get("state", "started"))
        return task_id

    def cancel_task(self, task_id: str, *, timeout: float | None = None) -> dict[str, Any]:
        task_id = str(task_id).strip()
        if not task_id:
            raise JsonProtocolError("task_id 不能为空。")
        result = self.request("cancel", {"task_id": task_id}, timeout=timeout)
        with self._state_lock:
            self._task_states[task_id] = str(result.get("state", "cancelling"))
        return result

    def poll_event(self, *, timeout: float = 0.0) -> dict[str, Any] | None:
        """Return the next progress/result/transport event, if available."""
        try:
            return self._events.get(timeout=max(0.0, float(timeout)))
        except queue.Empty:
            return None

    def wait_task(
        self,
        task_id: str,
        *,
        timeout: float | None = None,
        on_event: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Wait for one task result while optionally observing its progress."""
        task_id = str(task_id).strip()
        with self._state_lock:
            events = self._task_events.get(task_id)
            if events is None:
                raise JsonProtocolError(f"不存在的 task_id：{task_id}。")
            cached_result = self._task_results.get(task_id)
        if cached_result is not None:
            if on_event is not None:
                on_event(cached_result)
            return dict(cached_result)
        wait_seconds = self.request_timeout if timeout is None else max(0.0, float(timeout))
        deadline = time.monotonic() + wait_seconds
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                event = events.get(timeout=remaining)
            except queue.Empty as exc:
                raise IpcTimeoutError(f"任务超时：task_id={task_id!r}。") from exc
            if isinstance(event, Exception):
                raise event
            if on_event is not None:
                on_event(event)
            if event.get("type") == "result":
                with self._state_lock:
                    self._task_states[task_id] = (
                        "completed"
                        if event.get("ok")
                        else ("cancelled" if event.get("cancelled") else "failed")
                    )
                return dict(event)

    def task_status(self, task_id: str) -> str | None:
        with self._state_lock:
            return self._task_states.get(str(task_id).strip())

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        error: IpcTransportError | None = None
        try:
            if process.stdout is None:
                raise IpcTransportError("IPC 服务进程 stdout 不可用。")
            for line in process.stdout:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise IpcProtocolError(f"IPC 返回无效 JSON：{exc}") from exc
                if not isinstance(payload, Mapping):
                    raise IpcProtocolError("IPC 返回必须是 JSON 对象。")
                kind = payload.get("type")
                if kind in {"progress", "result"} and "task_id" in payload:
                    event = dict(payload)
                    self._events.put(event)
                    task_id = str(payload["task_id"])
                    with self._state_lock:
                        waiter = self._task_events.get(task_id)
                    if waiter is not None:
                        self._put_task_event(waiter, event)
                    if kind == "result":
                        with self._state_lock:
                            self._task_results[task_id] = event
                            self._task_states[task_id] = (
                                "completed"
                                if payload.get("ok")
                                else ("cancelled" if payload.get("cancelled") else "failed")
                            )
                    continue
                request_id = payload.get("id")
                if request_id is None:
                    self._events.put(dict(payload))
                    continue
                with self._state_lock:
                    waiter = self._pending.get(self._key(request_id))
                if waiter is None:
                    self._events.put(dict(payload))
                else:
                    waiter.put(dict(payload))
        except IpcTransportError as exc:
            error = exc
        except Exception as exc:
            error = IpcProtocolError(str(exc))
        finally:
            if error is None and not self._closing:
                error = IpcProcessExited(
                    f"IPC 服务进程已退出（code={process.poll()}）。"
                )
            if error is not None and not self._closing:
                self._set_fatal(error)

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        try:
            for line in process.stderr:
                with self._state_lock:
                    self._stderr_lines.append(line)
        except (OSError, ValueError):
            pass

    def _set_fatal(self, error: IpcTransportError) -> None:
        with self._state_lock:
            if self._fatal is not None:
                return
            self._fatal = error
            pending = list(self._pending.values())
            self._pending.clear()
            task_waiters = list(self._task_events.values())
        for waiter in pending:
            try:
                waiter.put_nowait(error)
            except queue.Full:
                # A response may have won the race with process EOF.  Keep
                # that response available to the request caller instead of
                # blocking the reader thread while reporting the fatal state.
                pass
        for waiter in task_waiters:
            self._put_task_event(waiter, error)
        self._events.put({"type": "transport_error", "error": str(error)})

    @staticmethod
    def _put_task_event(waiter: queue.Queue[Any], event: Any) -> None:
        """Add a task event without letting stale progress block the reader."""
        try:
            waiter.put_nowait(event)
            return
        except queue.Full:
            pass
        # Prefer retaining the terminal result/error over old progress.
        try:
            waiter.get_nowait()
        except queue.Empty:
            pass
        try:
            waiter.put_nowait(event)
        except queue.Full:
            pass


__all__ = [
    "IpcClient",
    "IpcClientError",
    "IpcTransportError",
    "IpcProcessExited",
    "IpcTimeoutError",
    "IpcRemoteError",
    "IpcProtocolError",
]
