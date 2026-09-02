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


class MainWindowContractTest(unittest.TestCase):
    def test_public_class_and_method_contract(self):
        window = app.App
        self.assertTrue(issubclass(window, tk.Tk))
        expected = {
            "__init__": ["self"],
            "add_files": ["self"],
            "add_folder": ["self"],
            "open_image": ["self"],
            "open_timelapse": ["self"],
            "open_storage_manager": ["self"],
            "detect_acceleration": ["self", "show_dialog"],
            "start_stack": ["self"],
            "toggle_stack_pause": ["self"],
            "cancel_stack": ["self"],
            "do_stretch": ["self"],
            "do_basic": ["self"],
            "do_curve": ["self"],
            "export_current": ["self"],
            "refresh_preview": ["self"],
            "_poll": ["self"],
        }
        for name, parameters in expected.items():
            self.assertEqual(
                list(inspect.signature(getattr(window, name)).parameters),
                parameters,
                name,
            )

    def test_window_keeps_expected_ui_collaborators(self):
        names = set(app.App.__dict__)
        self.assertTrue(
            {
                "_style",
                "_menu",
                "_ui",
                "_build_stack_tab",
                "_build_stretch_tab",
                "_build_basic_tab",
                "_build_channel_tab",
                "_build_curves_tab",
                "_build_detail_tab",
                "open_interface_settings",
                "open_hp_curve_dialog",
            }.issubset(names)
        )


if __name__ == "__main__":
    unittest.main()
