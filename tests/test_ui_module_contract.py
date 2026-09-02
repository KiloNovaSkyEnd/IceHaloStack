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
import ihs.node_workflow as node_workflow
import ihs.ui.appearance as appearance
import ihs.ui.exposure_wb_window as exposure_wb_window
import ihs.ui.performance_panel as performance_panel


class UiModuleContractTest(unittest.TestCase):
    def test_remaining_helper_signatures(self):
        expected = {
            "_init_timelapse_memory_vars": ["owner"],
            "_build_timelapse_memory_panel": ["owner", "parent", "wraplength", "show_dag"],
            "_init_ewb_vars": ["owner"],
            "_ewb_config_snapshot": ["owner"],
            "_ewb_enabled": ["owner"],
            "_ewb_require_analysis": ["owner"],
            "_ewb_settings_dialog": ["owner"],
            "_ewb_open_workspace": ["owner", "focus_curves"],
            "_build_ewb_panel": ["owner", "parent", "wraplength"],
            "scale_timelapse_cfg_for_proxy": ["cfg", "scale"],
            "apply_timelapse_pipeline": ["img", "cfg", "curve_points", "stop_after"],
        }
        for name, parameters in expected.items():
            self.assertEqual(list(inspect.signature(getattr(app, name)).parameters), parameters, name)
        self.assertTrue(issubclass(app.AngleDial, tk.Canvas))
        self.assertEqual(
            list(inspect.signature(app.AngleDial.__init__).parameters),
            ["self", "parent", "variable", "command", "release_command", "reset_value", "size", "kwargs"],
        )

    def test_proxy_radius_scaling_is_non_mutating(self):
        source = {
            "bg_radius": 10.0, "usm_radius": 2.0, "hp_radius": 0.2,
            "emboss_height": 0.1, "channel_noise_radius": 0.8,
        }
        actual = app.scale_timelapse_cfg_for_proxy(source, 0.25)
        self.assertEqual(source["bg_radius"], 10.0)
        self.assertEqual(actual["_proxy_scale"], 0.25)
        self.assertEqual(actual["bg_radius"], 2.5)
        self.assertEqual(actual["usm_radius"], 0.5)
        self.assertEqual(actual["hp_radius"], 0.1)
        self.assertEqual(actual["emboss_height"], 0.1)
        self.assertEqual(actual["channel_noise_radius"], 0.2)

    def test_helpers_are_reexported_from_their_new_modules(self):
        self.assertIs(app.AngleDial, appearance.AngleDial)
        self.assertIs(app._init_ewb_vars, exposure_wb_window._init_ewb_vars)
        self.assertIs(app._ewb_open_workspace, exposure_wb_window._ewb_open_workspace)
        self.assertIs(app._build_ewb_panel, exposure_wb_window._build_ewb_panel)
        self.assertIs(app._init_timelapse_memory_vars, performance_panel._init_timelapse_memory_vars)
        self.assertIs(app._build_timelapse_memory_panel, performance_panel._build_timelapse_memory_panel)
        self.assertIs(app.scale_timelapse_cfg_for_proxy, node_workflow.scale_timelapse_cfg_for_proxy)
        self.assertIs(app.apply_timelapse_pipeline, node_workflow.apply_timelapse_pipeline)


if __name__ == "__main__":
    unittest.main()
