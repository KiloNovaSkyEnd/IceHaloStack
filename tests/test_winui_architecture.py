from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINUI = ROOT / "winui" / "IceHaloStack.WinUI"


class WinUIArchitectureTest(unittest.TestCase):
    @staticmethod
    def source_files():
        return [path for path in WINUI.rglob("*.cs") if not {"bin", "obj"}.intersection(path.parts)]

    def test_stack_models_have_one_authoritative_declaration(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in self.source_files())
        for name in ("StackGroupingMode", "StackGroupingModeOption", "StackInputItem", "StackGroupItem"):
            declarations = re.findall(rf"\b(?:class|record|enum)\s+{name}\b", source)
            self.assertEqual(len(declarations), 1, f"{name} must have one declaration")

    def test_winui_viewmodels_remain_split_by_responsibility(self):
        oversized = {
            path.relative_to(WINUI).as_posix(): path.stat().st_size
            for path in self.source_files()
            if "ViewModels" in path.parts
            if path.stat().st_size > 16_000
        }
        self.assertEqual(oversized, {})
        expected = {
            "StackPageViewModel.Engine.cs",
            "StackPageViewModel.Naming.cs",
            "StackPageViewModel.Queue.cs",
            "ProcessingSettingsViewModel.cs",
            "VideoSettingsViewModel.cs",
        }
        self.assertTrue(expected.issubset({path.name for path in (WINUI / "ViewModels").rglob("*.cs")}))

    def test_shared_processing_control_is_used_by_all_native_workflows(self):
        for page in ("MainPage.xaml", "StackPage.xaml", "TimelapsePage.xaml"):
            text = (WINUI / page).read_text(encoding="utf-8")
            self.assertIn("ProcessingSettingsControl", text, page)

    def test_heavy_processing_controls_are_created_only_when_expanded(self):
        for page in ("MainPage.xaml", "StackPage.xaml", "TimelapsePage.xaml"):
            text = (WINUI / page).read_text(encoding="utf-8")
            self.assertIn(
                'x:Load="{x:Bind ProcessingExpander.IsExpanded, Mode=OneWay}"',
                text,
                page,
            )

        control = (WINUI / "Controls" / "ProcessingSettingsControl.xaml").read_text(encoding="utf-8")
        self.assertIn('x:Load="{x:Bind IsExpanded, Mode=OneWay}"', control)
        window = (WINUI / "MainWindow.xaml").read_text(encoding="utf-8")
        self.assertNotIn("<MicaBackdrop", window)

    def test_release_is_self_contained(self):
        project = (WINUI / "IceHaloStack.WinUI.csproj").read_text(encoding="utf-8")
        self.assertIn("<WindowsAppSDKSelfContained", project)
        self.assertIn("<SelfContained", project)

    def test_pages_keep_lists_in_a_finite_virtualized_viewport(self):
        for page in ("MainPage.xaml", "StackPage.xaml", "TimelapsePage.xaml"):
            text = (WINUI / page).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"<Page\b[\s\S]*?>\s*<ScrollViewer>", page)
            self.assertIn('NavigationCacheMode="Required"', text, page)

        for page in ("StackPage.xaml", "TimelapsePage.xaml"):
            text = (WINUI / page).read_text(encoding="utf-8")
            self.assertGreaterEqual(text.count("<ItemsStackPanel"), 2, page)
            self.assertIn('x:DataType="viewModels:StackInputItem"', text, page)
            self.assertIn('x:DataType="viewModels:StackGroupItem"', text, page)

        timelapse = (WINUI / "TimelapsePage.xaml").read_text(encoding="utf-8")
        self.assertIn(
            'x:Load="{x:Bind VideoExportExpander.IsExpanded, Mode=OneWay}"',
            timelapse,
        )

    def test_ui_performance_instrumentation_stays_in_services(self):
        services = WINUI / "Services"
        self.assertTrue((services / "UiPerformanceMonitor.cs").is_file())
        self.assertTrue((services / "UiPerformanceSmokeRunner.cs").is_file())
        self.assertTrue((services / "PageLifetimeRegistry.cs").is_file())


if __name__ == "__main__":
    unittest.main()
