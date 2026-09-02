from __future__ import annotations

import inspect
import sys
import tkinter as tk
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app
import ihs.ui.node_window as node_window
from ihs.ui.node_window import TimelapseNodeWindow as ExtractedNodeWindow


class NodeWindowContractTest(unittest.TestCase):
    def test_node_window_has_no_legacy_dependency_binding(self):
        self.assertFalse(hasattr(node_window, "_LEGACY_DEPENDENCY_NAMES"))
        self.assertFalse(hasattr(node_window, "bind_legacy_dependencies"))
        expected_modules = {
            "AngleDial": "ihs.ui.appearance",
            "_build_ewb_panel": "ihs.ui.exposure_wb_window",
            "_build_timelapse_memory_panel": "ihs.ui.performance_panel",
            "scale_timelapse_cfg_for_proxy": "ihs.node_workflow",
        }
        for name, module in expected_modules.items():
            self.assertEqual(getattr(node_window, name).__module__, module, name)

    def test_companion_class_contract(self):
        expected = {
            "LocalNodeEditorHistory": (
                object, ["self", "owner", "window", "flow", "label"],
                ("_capture_now", "_restore", "_undo_key", "_redo_key"),
            ),
            "FlowCurveDialog": (
                tk.Toplevel, ["self", "owner", "flow"],
                ("_apply_close", "_cancel_close", "_draw", "_reset_all"),
            ),
            "BaseCurveDialog": (
                tk.Toplevel, ["self", "owner", "flow"],
                ("_apply_close", "_cancel_close", "_draw", "_reset_all"),
            ),
            "StandaloneHPCurveDialog": (
                tk.Toplevel, ["self", "owner"],
                ("_apply_close", "_cancel_close", "_draw", "_reset_all"),
            ),
        }
        for name, (base, parameters, methods) in expected.items():
            cls = getattr(app, name)
            self.assertIs(cls, getattr(node_window, name), name)
            self.assertEqual(cls.__module__, "ihs.ui.node_window", name)
            self.assertTrue(issubclass(cls, base), name)
            self.assertEqual(list(inspect.signature(cls.__init__).parameters), parameters, name)
            for method in methods:
                self.assertTrue(hasattr(cls, method), f"{name}.{method}")

    def test_public_class_and_method_contract(self):
        window = app.TimelapseNodeWindow
        self.assertIs(window, ExtractedNodeWindow)
        self.assertEqual(window.__module__, "ihs.ui.node_window")
        self.assertTrue(issubclass(window, tk.Toplevel))
        self.assertEqual(window.NODE_ORDER, app._NODE_WORKFLOW_ORDER)
        expected = {
            "__init__": ["self", "app"],
            "_workflow_state": ["self"],
            "workflow_undo_action": ["self"],
            "workflow_redo_action": ["self"],
            "_apply_single_flow_node": ["self", "out", "node", "flow"],
            "_apply_flow_pipeline": ["self", "img", "flow"],
            "_apply_flow_pipeline_preview_cached": [
                "self", "img", "flow", "quality", "token", "stop_node",
            ],
            "_preset_payload": ["self", "f"],
            "_flow_from_payload": ["self", "data"],
            "_batch_worker": ["self", "st"],
            "_poll": ["self"],
        }
        for name, parameters in expected.items():
            self.assertTrue(hasattr(window, name), name)
            self.assertEqual(
                list(inspect.signature(getattr(window, name)).parameters),
                parameters,
                name,
            )


if __name__ == "__main__":
    unittest.main()
