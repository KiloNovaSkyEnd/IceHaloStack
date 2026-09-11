from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ihs.image_io import read_linear_rgb, save_tiff, srgb_to_linear
from ihs.image_ops import apply_asinh_stretch
from ihs.services import (
    AsyncJsonLineHost,
    IpcClient,
    IpcProcessExited,
    IpcProtocolError,
    IpcRemoteError,
    JsonLineHost,
    JsonProtocolError,
    JsonRequest,
    JsonServiceAdapter,
    JsonTaskManager,
)
from ihs.services.contracts import ProgressEvent, ServiceCancelled


class ServicesIPCTest(unittest.TestCase):
    def setUp(self):
        yy, xx = np.indices((8, 10), dtype=np.float32)
        base = 0.08 + 0.01 * xx + 0.015 * yy
        self.image = np.stack((base, base * 0.9, base * 1.1), axis=2).astype(np.float32)

    def test_request_validation_and_ping(self):
        request = JsonRequest.from_json('{"id":"p1","method":"ping"}')
        self.assertEqual(request.request_id, "p1")
        self.assertEqual(JsonServiceAdapter().dispatch(request)["protocol"], "ihs-jsonl-v1")
        with self.assertRaises(JsonProtocolError):
            JsonRequest.from_json('{"id":1,"params":{}}')

    def test_process_file_dispatch_uses_services(self):
        with tempfile.TemporaryDirectory(prefix="ihs_ipc_") as folder:
            root = Path(folder)
            source = root / "source.tif"
            target = root / "output.png"
            save_tiff(source, self.image, float32=True)
            events = []
            adapter = JsonServiceAdapter(progress=events.append)
            result = adapter.dispatch(
                {
                    "id": 7,
                    "method": "process_file",
                    "params": {
                        "input_path": str(source),
                        "output_path": str(target),
                        "config": {"stretch": False},
                    },
                }
            )
            self.assertEqual(result["output_path"], str(target))
            self.assertEqual(result["shape"], [8, 10, 3])
            self.assertTrue(target.exists())
            expected = srgb_to_linear(np.round(np.clip(self.image, 0, 1) * 255.0) / 255.0)
            np.testing.assert_allclose(read_linear_rgb(target), expected, rtol=0, atol=1e-7)
            self.assertTrue(events)
            self.assertEqual(events[-1].phase, "export")

    def test_image_preview_returns_bounded_image_and_histogram(self):
        with tempfile.TemporaryDirectory(prefix="ihs_ipc_preview_") as folder:
            root = Path(folder)
            source = root / "source.tif"
            target = root / "preview.png"
            save_tiff(source, self.image, float32=True)
            result = JsonServiceAdapter().dispatch({
                "id": "preview",
                "method": "image_preview",
                "params": {
                    "input_path": str(source),
                    "output_path": str(target),
                    "max_side": 128,
                },
            })
            self.assertTrue(target.is_file())
            self.assertEqual(result["shape"], [8, 10, 3])
            self.assertEqual(len(result["histogram"]), 64)
            self.assertAlmostEqual(max(result["histogram"]), 1.0)
            self.assertLessEqual(max(result["preview_shape"][:2]), 128)

    def test_json_line_host_streams_progress_then_response(self):
        input_stream = io.StringIO('{"id":1,"method":"ping"}\n')
        output_stream = io.StringIO()
        JsonLineHost(stdin=input_stream, stdout=output_stream).serve_forever()
        lines = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["id"], 1)
        self.assertTrue(lines[0]["ok"])

    def test_stack_files_dispatch_writes_requested_outputs(self):
        with tempfile.TemporaryDirectory(prefix="ihs_ipc_stack_") as folder:
            root = Path(folder)
            sources = [root / "a.tif", root / "b.tif"]
            targets = [root / "master.tif"]
            save_tiff(sources[0], self.image, float32=True)
            save_tiff(sources[1], self.image * 2.0, float32=True)
            result = JsonServiceAdapter().dispatch(
                {
                    "id": "stack",
                    "method": "stack_files",
                    "params": {
                        "input_paths": [str(path) for path in sources],
                        "groups": [[0, 1]],
                        "output_paths": [str(path) for path in targets],
                        "method": "mean",
                        "format": "TIFF 32-bit Float",
                    },
                }
            )
            self.assertEqual(result["count"], 1)
            np.testing.assert_allclose(read_linear_rgb(targets[0]), self.image * 1.5, rtol=0, atol=0)

    def test_stack_files_applies_the_shared_processing_pipeline(self):
        with tempfile.TemporaryDirectory(prefix="ihs_ipc_stack_pipeline_") as folder:
            root = Path(folder)
            sources = [root / "a.tif", root / "b.tif"]
            target = root / "master.tif"
            save_tiff(sources[0], self.image, float32=True)
            save_tiff(sources[1], self.image, float32=True)
            result = JsonServiceAdapter().dispatch(
                {
                    "id": "stack-pipeline",
                    "method": "stack_files",
                    "params": {
                        "input_paths": [str(path) for path in sources],
                        "groups": [[0, 1]],
                        "output_paths": [str(target)],
                        "method": "mean",
                        "format": "TIFF 32-bit Float",
                        "config": {
                            "stretch": True,
                            "stretch_strength": 2.0,
                            "stretch_black": 0.0,
                        },
                    },
                }
            )
            self.assertEqual(result["count"], 1)
            np.testing.assert_allclose(
                read_linear_rgb(target),
                apply_asinh_stretch(self.image, 2.0, 0.0),
                rtol=0,
                atol=2e-6,
            )

    def test_json_line_host_returns_protocol_error(self):
        output_stream = io.StringIO()
        host = JsonLineHost(stdin=io.StringIO('{"id":2,"method":"missing"}\n'), stdout=output_stream)
        host.serve_forever()
        response = json.loads(output_stream.getvalue())
        self.assertEqual(response["id"], 2)
        self.assertFalse(response["ok"])
        self.assertIn("不支持", response["error"])

    def test_task_manager_cancel_emits_task_scoped_result(self):
        started = threading.Event()

        def runner(_operation, _params, cancellation, progress):
            started.set()
            progress(ProgressEvent("custom", 0, 1, "running"))
            while not cancellation.is_cancelled():
                time.sleep(0.005)
            raise ServiceCancelled("synthetic cancellation")

        manager = JsonTaskManager(runner=runner)
        manager.start("task-1", "custom", {})
        self.assertTrue(started.wait(1.0))
        self.assertEqual(manager.cancel("task-1"), "cancelling")
        events = []
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            event = manager.poll_events(timeout=0.05)
            if event is not None:
                events.append(event)
                if event.get("type") == "result":
                    break
        self.assertTrue(any(event.get("type") == "progress" for event in events))
        result = next(event for event in events if event.get("type") == "result")
        self.assertEqual(result["task_id"], "task-1")
        self.assertFalse(result["ok"])
        self.assertTrue(result["cancelled"])

    def test_async_host_start_and_cancel_protocol(self):
        def runner(_operation, _params, cancellation, _progress):
            while not cancellation.is_cancelled():
                time.sleep(0.005)
            raise ServiceCancelled("synthetic cancellation")

        output = io.StringIO()
        host = AsyncJsonLineHost(
            stdin=io.StringIO(
                '{"id":"start-req","method":"start","params":{"task_id":"task-2","operation":"custom","params":{}}}\n'
                '{"id":"cancel-req","method":"cancel","params":{"task_id":"task-2"}}\n'
            ),
            stdout=output,
            tasks=JsonTaskManager(runner=runner),
        )
        host.serve_forever()
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(lines[0]["id"], "start-req")
        self.assertEqual(lines[0]["result"]["task_id"], "task-2")
        self.assertEqual(lines[1]["id"], "cancel-req")
        result = next(line for line in lines if line.get("type") == "result")
        self.assertEqual(result["task_id"], "task-2")
        self.assertTrue(result["cancelled"])

    def test_ipc_client_real_subprocess_ping_and_task(self):
        """Exercise the complete client -> child -> task event loop."""
        with tempfile.TemporaryDirectory(prefix="ihs_ipc_client_") as folder:
            root = Path(folder)
            source = root / "source.tif"
            target = root / "output.png"
            save_tiff(source, self.image, float32=True)
            with IpcClient(
                command=(sys.executable, "-m", "ihs.services.ipc"),
                cwd=ROOT,
                request_timeout=5.0,
            ) as client:
                ping = client.ping()
                self.assertEqual(ping["protocol"], "ihs-jsonl-v1")
                task_id = client.start_task(
                    "process_file",
                    {
                        "input_path": str(source),
                        "output_path": str(target),
                        "config": {"stretch": False},
                    },
                    task_id="real-task-1",
                )
                events = []
                result = client.wait_task(task_id, timeout=10.0, on_event=events.append)
                self.assertTrue(result["ok"])
                self.assertEqual(result["task_id"], task_id)
                self.assertTrue(target.exists())
                self.assertTrue(any(event["type"] == "progress" for event in events))
                self.assertEqual(client.task_status(task_id), "completed")

    def test_ipc_client_surfaces_remote_error_without_killing_process(self):
        with IpcClient(
            command=(sys.executable, "-m", "ihs.services.ipc"),
            cwd=ROOT,
            request_timeout=5.0,
        ) as client:
            with self.assertRaises(IpcRemoteError) as context:
                client.request("missing")
            self.assertIn("只接受", str(context.exception))
            self.assertTrue(client.is_alive())

    def test_ipc_client_cancel_round_trip_with_real_child(self):
        runner = (
            "import time\n"
            "from ihs.services.contracts import ServiceCancelled\n"
            "from ihs.services.ipc import AsyncJsonLineHost, JsonTaskManager\n"
            "def run(_operation, _params, cancellation, _progress):\n"
            "    while not cancellation.is_cancelled():\n"
            "        time.sleep(0.005)\n"
            "    raise ServiceCancelled('synthetic cancellation')\n"
            "AsyncJsonLineHost(tasks=JsonTaskManager(runner=run)).serve_forever()\n"
        )
        with IpcClient(
            command=(sys.executable, "-c", runner),
            cwd=ROOT,
            request_timeout=5.0,
        ) as client:
            task_id = client.start_task("custom", task_id="cancel-task")
            ack = client.cancel_task(task_id)
            self.assertEqual(ack["task_id"], task_id)
            result = client.wait_task(task_id, timeout=5.0)
            self.assertFalse(result["ok"])
            self.assertTrue(result["cancelled"])
            self.assertEqual(client.task_status(task_id), "cancelled")

    def test_task_manager_pause_resume_and_use_current_controls(self):
        entered = threading.Event()
        finish = threading.Event()

        def runner(_operation, _params, cancellation, _progress):
            entered.set()
            while not cancellation.use_current_requested():
                cancellation.wait_if_paused()
                time.sleep(0.002)
            finish.set()
            return {"partial": True}

        manager = JsonTaskManager(runner=runner)
        manager.start("controlled", "custom")
        self.assertTrue(entered.wait(1))
        self.assertEqual(manager.pause("controlled"), "paused")
        self.assertEqual(manager.resume("controlled"), "running")
        self.assertEqual(manager.use_current("controlled"), "finishing-current")
        self.assertTrue(finish.wait(1))

    def test_ipc_client_reports_malformed_child_output(self):
        code = "import sys; sys.stdout.write('not-json\\n'); sys.stdout.flush()"
        with IpcClient(
            command=(sys.executable, "-c", code),
            cwd=ROOT,
            request_timeout=5.0,
        ) as client:
            with self.assertRaises(IpcProtocolError):
                client.ping()
            event = client.poll_event(timeout=1.0)
            self.assertEqual(event["type"], "transport_error")

    def test_ipc_client_reports_child_exit_before_response(self):
        with IpcClient(
            command=(sys.executable, "-c", "raise SystemExit(7)"),
            cwd=ROOT,
            request_timeout=5.0,
        ) as client:
            with self.assertRaises(IpcProcessExited):
                client.ping()


if __name__ == "__main__":
    unittest.main()
