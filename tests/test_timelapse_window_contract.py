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
import ihs.ui.timelapse_window as timelapse_window


class TimelapseWindowContractTest(unittest.TestCase):
    def test_entry_reexports_extracted_window(self):
        self.assertIs(app.TimelapseWindow, timelapse_window.TimelapseWindow)
        self.assertEqual(app.TimelapseWindow.__module__, "ihs.ui.timelapse_window")
        self.assertTrue(issubclass(app.TimelapseWindow, tk.Toplevel))

    def test_public_method_contract(self):
        expected = {
            "__init__": ["self", "app"],
            "_init_vars": ["self"],
            "_build_ui": ["self"],
            "_snapshot_cfg": ["self"],
            "_iter_masters": ["self", "groups", "method", "ref_lum"],
            "start_batch": ["self"],
            "cancel": ["self"],
            "_batch_worker": ["self", "s"],
            "_poll": ["self"],
        }
        for name, parameters in expected.items():
            self.assertEqual(
                list(inspect.signature(getattr(app.TimelapseWindow, name)).parameters),
                parameters,
                name,
            )

    def test_module_owns_timelapse_dependencies(self):
        for name in (
            "_iter_optimized_timelapse_masters",
            "AsyncOutputPipeline",
            "_build_ewb_panel",
            "_build_timelapse_memory_panel",
            "apply_timelapse_pipeline",
            "ImageProcessingService",
        ):
            self.assertTrue(hasattr(timelapse_window, name), name)


if __name__ == "__main__":
    unittest.main()
