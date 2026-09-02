from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as perf


GIB = 1024 ** 3


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class Owner:
    def __init__(self):
        self.memory_limit_mode = Value("Manual")
        self.memory_limit_gb = Value(30.0)
        self.memory_strategy = Value("Maximum Performance")
        self._active_frame_cache = None
        self._active_output_pipeline = None
        self._active_performance_monitor = None
        self._active_memory_policy = {"sentinel": True}
        self._last_performance_snapshot = None


class PerformanceTest(unittest.TestCase):
    def setUp(self):
        self.real_system = perf._system_memory_status
        self.real_rss = perf._process_memory_rss
        self.real_auto = perf._auto_ram_limit_bytes
        perf._system_memory_status = lambda: (16 * GIB, 10 * GIB)
        perf._process_memory_rss = lambda: 1 * GIB
        perf._auto_ram_limit_bytes = lambda: 6 * GIB

    def tearDown(self):
        perf._system_memory_status = self.real_system
        perf._process_memory_rss = self.real_rss
        perf._auto_ram_limit_bytes = self.real_auto

    def test_format_helpers(self):
        self.assertEqual(perf._fmt_bytes(1536), "2 KB")
        self.assertEqual(perf._fmt_bytes(GIB), "1.00 GB")
        self.assertEqual(perf._fmt_bytes("bad"), "—")
        self.assertEqual(perf._format_seconds_short(65), "01:05")
        self.assertEqual(perf._format_seconds_short(3661), "01:01:01")

    def test_manual_policy_is_bounded_and_strategy_is_preserved(self):
        policy = perf._timelapse_memory_policy_snapshot(Owner())
        self.assertEqual(policy["limit_bytes"], 12 * GIB)
        self.assertEqual(policy["system_reserve_bytes"], 4 * GIB)
        self.assertEqual(policy["strategy"], "Maximum Performance")
        self.assertEqual(policy["frame_cache_share"], 0.65)
        self.assertEqual(policy["prefetch_count"], 4)
        self.assertFalse(policy["disk_cache"])
        self.assertEqual(perf._manual_ram_bounds_gb(), (1.0, 12.0))

    def test_monitor_snapshot_and_reports(self):
        owner = Owner()
        policy = {"limit_bytes": 8 * GIB, "strategy": "Balanced"}
        monitor = perf.PerformanceMonitor(owner, "Rolling Mean", policy, "Node Timelapse", True)
        monitor.inc("processed_tasks", 3)
        monitor.inc("raw_decodes", 5)
        monitor.add_stage("raw_decode", 1.25)
        monitor.add_stage("output_prepare", 0.4)
        monitor.record_node("basic", 0.75)
        monitor.record_cache_stats({"hits": 7, "misses": 3, "evictions": 2, "bytes": 2048})
        monitor.record_output_stats({"completed": 4, "peak_bytes": 4096})
        monitor.record_dag_stats({
            "hits": 6,
            "computes": 2,
            "budget_skips": 1,
            "peak_bytes": 8192,
            "hits_by_node": {"basic": 6},
            "computes_by_node": {"basic": 2},
            "reusable_by_node": {"basic": 6},
        })
        list(monitor.wrap_masters(["a", "b"]))
        with tempfile.TemporaryDirectory(prefix="ihs_performance_") as folder:
            snapshot = monitor.finalize("Complete", folder, extra={"mode": "test"})
            report_dir = Path(folder)
            self.assertEqual(len(list(report_dir.glob("performance_report_*.json"))), 1)
            self.assertEqual(len(list(report_dir.glob("performance_report_*.txt"))), 1)
            text = next(report_dir.glob("performance_report_*.txt")).read_text(encoding="utf-8")
            self.assertIn("Rolling Mean", text)
            self.assertIn("DAG Hit 6", text)
        self.assertEqual(snapshot["status"], "Complete")
        self.assertEqual(snapshot["masters"], 2)
        self.assertEqual(snapshot["processed_tasks"], 3)
        self.assertEqual(snapshot["raw_decodes"], 5)
        self.assertEqual(snapshot["frames_written"], 4)
        self.assertAlmostEqual(snapshot["frame_cache_hit_rate"], 0.7)
        self.assertEqual(snapshot["dag_hits"], 6)
        self.assertEqual(snapshot["extra"], {"mode": "test"})
        self.assertIsNone(owner._active_performance_monitor)
        self.assertIsNone(owner._active_memory_policy)
        self.assertIs(owner._last_performance_snapshot, snapshot)

    def test_disabled_report_does_not_write(self):
        owner = Owner()
        monitor = perf.PerformanceMonitor(owner, "Compatibility", {}, save_report=False)
        with tempfile.TemporaryDirectory(prefix="ihs_performance_") as folder:
            monitor.finalize("Cancelled", folder)
            self.assertFalse(list(Path(folder).iterdir()))


if __name__ == "__main__":
    unittest.main()

