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
        for page in ("StackPage.xaml", "TimelapsePage.xaml"):
            text = (WINUI / page).read_text(encoding="utf-8")
            self.assertIn("ProcessingSettingsControl", text, page)

    def test_classic_parameter_tabs_use_split_native_panels(self):
        tabs = (WINUI / "Controls" / "ClassicProcessingTabs.xaml").read_text(encoding="utf-8")
        for panel in ("ClassicStretchPanel", "ClassicBasePanel", "ClassicDetailPanel", "ClassicChannelPanel", "ClassicCurvesPanel"):
            self.assertIn(panel, tabs)
            self.assertTrue((WINUI / "Controls" / f"{panel}.xaml").is_file())
            self.assertTrue((WINUI / "Controls" / f"{panel}.xaml.cs").is_file())
        self.assertTrue((WINUI / "Controls" / "ParameterSectionControl.xaml").is_file())

    def test_curves_and_node_editors_are_native_and_split(self):
        curves = (WINUI / "Controls" / "CurveEditorControl.cs").read_text(encoding="utf-8")
        for behavior in ("AddPoint", "IsRightButtonPressed", "CapturePointer", "IsEndpoint"):
            self.assertIn(behavior, curves)
        serialization = (WINUI / "ViewModels" / "ProcessingSettingsViewModel.Serialization.cs").read_text(encoding="utf-8")
        self.assertIn("CurveEditor.ToIpcCurvePoints()", serialization)
        self.assertNotIn("var shadow =", serialization)
        self.assertNotIn("var highlight =", serialization)
        factory = (WINUI / "Controls" / "NodeParameterEditorFactory.cs").read_text(encoding="utf-8")
        for node in ("stack", "basic", "bgr", "channel", "output", "stretch", "usm", "highpass", "emboss"):
            self.assertIn(f'"{node}"', factory)

    def test_classic_workspace_is_composed_from_small_controls(self):
        main_page = (WINUI / "MainPage.xaml").read_text(encoding="utf-8")
        expected = {
            "ClassicCommandStrip",
            "ClassicFramesPane",
            "ClassicPreviewPane",
            "ClassicProcessingTabs",
        }
        for control in expected:
            self.assertIn(control, main_page)
            self.assertTrue((WINUI / "Controls" / f"{control}.xaml").is_file())
            self.assertTrue((WINUI / "Controls" / f"{control}.xaml.cs").is_file())

        oversized = {
            path.relative_to(WINUI).as_posix(): path.stat().st_size
            for path in (WINUI / "Controls").glob("Classic*")
            if path.stat().st_size > 16_000
        }
        self.assertEqual(oversized, {})
        self.assertFalse((WINUI / "Services" / "ClassicWorkspaceLauncher.cs").exists())
        self.assertNotIn("ClassicWorkspaceLauncher", (WINUI / "MainPage.xaml.cs").read_text(encoding="utf-8"))

    def test_heavy_processing_controls_are_created_only_when_expanded(self):
        for page in ("StackPage.xaml", "TimelapsePage.xaml"):
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

    def test_winui_release_cannot_bundle_classic_or_unbounded_runtimes(self):
        release = (ROOT / "build_winui_release.ps1").read_text(encoding="utf-8")
        self.assertNotIn("IncludeClassic", release)
        self.assertNotIn('IceHaloStack.spec")', release)
        self.assertIn("MaximumUnpackedMiB", release)
        self.assertIn('"Classic", "venv", "site-packages", "pip-cache", "build"', release)
        engine = (ROOT / "IceHaloStackEngine.spec").read_text(encoding="utf-8")
        for fragment in ("cupyx\\\\", "opencv_videoio_ffmpeg", "pil\\\\_avif"):
            self.assertIn(fragment, engine.lower())

    def test_v0_9_6_8c_release_identity_is_locked(self):
        release = (ROOT / "build_winui_release.ps1").read_text(encoding="utf-8")
        constants = (ROOT / "ihs" / "constants.py").read_text(encoding="utf-8")
        project = (WINUI / "IceHaloStack.WinUI.csproj").read_text(encoding="utf-8")
        manifest = (WINUI / "Package.appxmanifest").read_text(encoding="utf-8")
        title = (WINUI / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        self.assertIn('$ReleaseVersion = "v0.9.6.8c"', release)
        self.assertNotIn("[string]$ReleaseVersion", release)
        self.assertIn("VERSION = '0.9.6.8c'", constants)
        self.assertIn("<Version>0.9.6.8-c</Version>", project)
        self.assertIn('Version="0.9.6.83"', manifest)
        self.assertIn("IceHaloStack v0.9.6.8c", title)

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

        frames = (WINUI / "Controls" / "ClassicFramesPane.xaml").read_text(encoding="utf-8")
        self.assertIn("<ItemsStackPanel", frames)
        self.assertIn('x:DataType="viewModels:StackInputItem"', frames)

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
        self.assertTrue((services / "IEngineClientProvider.cs").is_file())
        self.assertTrue((services / "EngineClientProvider.cs").is_file())

    def test_node_export_readiness_is_split_and_ewb_independent(self):
        state = (WINUI / "ViewModels" / "NodeWorkflowViewModel.ExportState.cs").read_text(encoding="utf-8")
        self.assertIn("GetExportValidationError", state)
        validation = state.split("private string? GetExportValidationError()", 1)[1]
        self.assertNotIn("DeflickerEnabled", validation)
        self.assertNotIn("ExposureSmoothingEnabled", validation)
        self.assertNotIn("WhiteBalanceSmoothingEnabled", validation)
        page = (WINUI / "NodeWorkflowPage.xaml").read_text(encoding="utf-8")
        self.assertIn("ExportBlockReason", page)

    def test_classic_controls_and_ewb_timeline_are_native(self):
        command_xaml = (WINUI / "Controls" / "ClassicCommandStrip.xaml").read_text(encoding="utf-8")
        command_code = (WINUI / "Controls" / "ClassicCommandStrip.xaml.cs").read_text(encoding="utf-8")
        for action in ("Undo_Click", "Redo_Click", "Pause_Click", "UseCurrent_Click", "AutoStretch_Click", "Font_Click", "Language_Click"):
            self.assertIn(action, command_xaml)
            self.assertIn(action, command_code)

        preview = (WINUI / "Controls" / "EwbPreviewPane.xaml").read_text(encoding="utf-8")
        for feature in ("原始", "修正后", "左右对比", "ThumbnailList", "CurrentFrameNumber", "PlaybackFps", "EwbTrendChartControl"):
            self.assertIn(feature, preview)
        self.assertTrue((WINUI / "Controls" / "EwbTrendChartControl.cs").is_file())
        self.assertTrue((WINUI / "Services" / "UiPreferencesService.cs").is_file())

    def test_new_native_sources_remain_small(self):
        oversized = {
            path.relative_to(WINUI).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
            for path in self.source_files()
            if len(path.read_text(encoding="utf-8").splitlines()) >= 500
        }
        self.assertEqual(oversized, {})


if __name__ == "__main__":
    unittest.main()
