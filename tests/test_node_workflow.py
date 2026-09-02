from __future__ import annotations

import copy
import sys
import unittest
from collections import Counter
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


GIB = 1024 ** 3


def default_cfg():
    return {
        "stretch": True,
        "stretch_strength": 8.0,
        "stretch_black": 0.0,
        "basic": True,
        "exposure": 0.0,
        "contrast": 0.0,
        "bgr": False,
        "background": False,
        "curves": False,
        "usm": False,
        "usm_amount": 100.0,
        "usm_radius": 2.0,
        "usm_threshold": 0.0,
        "usm_passes": 1,
        "highpass": False,
        "emboss": False,
        "br": False,
        "channel": False,
    }


def harness():
    window = object.__new__(app.TimelapseNodeWindow)
    window._default_cfg = lambda: copy.deepcopy(default_cfg())
    return window


def flow(name="Flow", usm_amount=100.0):
    return {
        "name": name,
        "cfg": {
            "stretch": True,
            "stretch_strength": 8.0,
            "stretch_black": 0.0,
            "basic": True,
            "exposure": 0.2,
            "contrast": 5.0,
            "usm": True,
            "usm_amount": usm_amount,
            "usm_radius": 2.0,
            "usm_threshold": 0.0,
            "usm_passes": 1,
        },
        "curves": {"RGB": [(0.0, 0.0), (1.0, 1.0)]},
        "base_curves": {"RGB": [(0.0, 0.0), (1.0, 1.0)]},
        "present_nodes": ["stack", "stretch", "basic", "usm", "output"],
        "layout": {},
        "edges": [
            ("stack", "stretch"),
            ("stretch", "basic"),
            ("basic", "usm"),
            ("usm", "output"),
        ],
        "output": {"export_enabled": True},
    }


class NodeWorkflowTest(unittest.TestCase):
    def test_normalize_flow_repairs_structure_in_place(self):
        window = harness()
        source = {
            "name": "Legacy",
            "cfg": {"stretch": False},
            "present_nodes": ["basic", "invalid", "basic"],
            "layout": {"background": (1, 2), "basic": (9, 10)},
            "edges": [("basic", "basic"), ("invalid", "output"), ("basic", "output")],
        }
        actual = window._normalize_flow(source)
        self.assertIs(actual, source)
        self.assertEqual(actual["present_nodes"], ["stack", "basic", "output"])
        self.assertEqual(actual["edges"], [("basic", "output")])
        self.assertNotIn("background", actual["layout"])
        self.assertEqual(actual["layout"]["basic"], (9, 10))
        self.assertIn("stack", actual["layout"])
        self.assertFalse(actual["cfg"]["stretch"])
        self.assertEqual(actual["cfg"]["usm_amount"], 100.0)
        self.assertTrue(actual["output"]["delete_sequence_after_video_only"])
        self.assertEqual(set(actual["base_curves"]), {"RGB", "红色", "绿色", "蓝色", "亮度"})

    def test_execution_order_disconnected_nodes_and_cycle(self):
        window = harness()
        connected = window._normalize_flow(flow())
        self.assertEqual(window._flow_exec_order(connected), ["stretch", "basic", "usm"])
        disconnected = copy.deepcopy(connected)
        disconnected["edges"] = [("stack", "stretch"), ("stretch", "output"), ("basic", "usm")]
        self.assertEqual(window._flow_exec_order(disconnected), ["stretch"])
        cyclic = copy.deepcopy(connected)
        cyclic["edges"].append(("usm", "basic"))
        with self.assertRaisesRegex(ValueError, "存在循环"):
            window._flow_exec_order(cyclic)

    def test_cache_signature_uses_only_pixel_relevant_parameters(self):
        window = harness()
        first = window._normalize_flow(flow())
        second = copy.deepcopy(first)
        second["cfg"]["unused_legacy_value"] = 999
        second["output"]["fps"] = 60
        self.assertEqual(
            window._preview_node_signature(first, "usm"),
            window._preview_node_signature(second, "usm"),
        )
        second["cfg"]["usm_amount"] = 101.0
        self.assertNotEqual(
            window._preview_node_signature(first, "usm"),
            window._preview_node_signature(second, "usm"),
        )
        reordered = copy.deepcopy(first)
        reordered["base_curves"] = dict(reversed(list(first["base_curves"].items())))
        self.assertEqual(
            window._preview_node_signature(first, "basic"),
            window._preview_node_signature(reordered, "basic"),
        )

    def test_shared_dag_plan_and_metadata(self):
        window = harness()
        plans, occurrences, metadata = window._prepare_shared_node_dag([
            flow("A", 100.0), flow("B", 125.0),
        ])
        self.assertEqual([node for _, node in plans[0]], ["stretch", "basic", "usm"])
        self.assertEqual([node for _, node in plans[1]], ["stretch", "basic", "usm"])
        self.assertEqual(metadata["naive_nodes"], 6)
        self.assertEqual(metadata["shared_keys"], 2)
        self.assertEqual(metadata["reusable_uses"], 2)
        self.assertEqual(metadata["reusable_by_node"], {"stretch": 1, "basic": 1})
        self.assertEqual(metadata["parameter_reuse_by_node"], {"stretch": 1, "basic": 1})
        self.assertEqual(sorted(occurrences.values()), [1, 1, 2, 2])

    def test_cache_cap_and_reference_release(self):
        window = harness()
        self.assertEqual(window._shared_dag_cache_cap({"strategy": "Memory Saver", "limit_bytes": GIB}), int(GIB * 0.08))
        self.assertEqual(window._shared_dag_cache_cap({"strategy": "Balanced", "limit_bytes": GIB}), int(GIB * 0.16))
        self.assertEqual(window._shared_dag_cache_cap({"strategy": "Maximum Performance", "limit_bytes": GIB}), int(GIB * 0.22))
        key = (("MASTER",), "basic", "signature")
        steps = [(key, "basic")]
        remaining = Counter({key: 1})
        cached = np.zeros((3, 4, 3), dtype=np.float32)
        cache = {key: cached}
        state = {"bytes": cached.nbytes, "peak": cached.nbytes}
        window._release_shared_flow_refs(steps, remaining, cache, state)
        self.assertEqual(remaining, Counter())
        self.assertEqual(cache, {})
        self.assertEqual(state["bytes"], 0)

    def test_preset_payload_round_trip_and_validation(self):
        window = harness()
        window._new_flow = lambda name: window._normalize_flow(flow(name))
        source = window._normalize_flow(flow("Preset", 137.0))
        source["output"].update({
            "save_video": True, "video_format": "MOV ProRes", "fps": 25.0,
        })
        payload = window._preset_payload(source)
        self.assertEqual(payload["format"], "IceHaloStackFlowPreset")
        self.assertEqual(payload["version"], 5)
        self.assertEqual(payload["name"], "Preset")
        self.assertEqual(payload["cfg"]["usm_amount"], 137.0)
        self.assertEqual(payload["output"]["video_format"], "MOV ProRes")
        payload["cfg"]["usm_amount"] = 88.0
        self.assertEqual(source["cfg"]["usm_amount"], 137.0)
        loaded = window._flow_from_payload(payload)
        self.assertEqual(loaded["name"], "Preset")
        self.assertEqual(loaded["cfg"]["usm_amount"], 88.0)
        self.assertEqual(loaded["output"]["fps"], 25.0)
        self.assertTrue(loaded["output"]["delete_sequence_after_video_only"])
        with self.assertRaisesRegex(ValueError, "不是有效"):
            window._flow_from_payload({"format": "Other"})


if __name__ == "__main__":
    unittest.main()
