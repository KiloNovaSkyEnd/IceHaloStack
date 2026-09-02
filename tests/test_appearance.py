from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


class AppearanceContractTest(unittest.TestCase):
    def test_flow_name_translation_preserves_custom_names(self):
        self.assertEqual(app._translate_flow_list_item("流程 12", "en"), "Flow 12")
        self.assertEqual(app._translate_flow_list_item("● 2  流程 3 副本 副本", "en"), "● 2  Flow 3 Copy Copy")
        self.assertEqual(app._translate_flow_list_item("自定义流程", "en"), "自定义流程")
        self.assertEqual(app._translate_flow_list_item("流程 4", "zh_CN"), "流程 4")

    def test_font_tuple_and_mousewheel_behavior(self):
        self.assertEqual(app._ui_font(11), (app.UI_FONT_FAMILY, 11, "normal"))
        self.assertEqual(app._ui_font(13, pixel=True), (app.UI_FONT_FAMILY, -13, "normal"))
        self.assertEqual(app._mousewheel_steps(SimpleNamespace(delta=120)), -3)
        self.assertEqual(app._mousewheel_steps(SimpleNamespace(delta=-240)), 6)
        self.assertEqual(app._mousewheel_steps(SimpleNamespace(delta=1)), -3)
        self.assertEqual(app._mousewheel_steps(SimpleNamespace(delta=0)), 0)
        self.assertEqual(app._mousewheel_steps(SimpleNamespace(delta=0), 1), -3)
        self.assertEqual(app._mousewheel_steps(SimpleNamespace(delta=0), -1), 3)

    def test_helper_signatures(self):
        expected = {
            "_translate_flow_list_item": ["text", "language"],
            "_ui_font": ["size", "pixel"],
            "_enforce_regular_typography": ["root"],
            "_make_vertical_scroll_area": ["parent", "padding"],
            "_mousewheel_steps": ["event", "linux_direction"],
        }
        for name, parameters in expected.items():
            self.assertEqual(
                list(inspect.signature(getattr(app, name)).parameters), parameters, name
            )


if __name__ == "__main__":
    unittest.main()
