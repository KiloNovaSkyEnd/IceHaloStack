using Microsoft.UI.Xaml;
using IceHaloStack_WinUI.Services;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace IceHaloStack_WinUI;

/// <summary>
/// The application window. This hosts a Frame that displays pages. Add your
/// UI and logic to MainPage.xaml / MainPage.xaml.cs instead of here so you
/// can use Page features such as navigation events and the Loaded lifecycle.
/// </summary>
public sealed partial class MainWindow : Window
{
    private readonly UiPerformanceMonitor _performanceMonitor = new();

    public MainWindow()
    {
        InitializeComponent();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        AppWindow.SetIcon("Assets/AppIcon.ico");

        Title = "IceHaloStack v0.9.6.8c · WinUI 3";
        _performanceMonitor.SnapshotUpdated += OnPerformanceSnapshotUpdated;
        _performanceMonitor.Start(RootFrame);
        Closed += OnClosed;
        RootFrame.Navigate(typeof(MainPage));
    }

    internal void StartPerformanceSmokeIfRequested()
        => _ = UiPerformanceSmokeRunner.RunIfRequestedAsync(this, RootFrame, _performanceMonitor);

    private void OnPerformanceSnapshotUpdated(UiFrameSnapshot snapshot)
    {
        if (!string.Equals(
                Environment.GetEnvironmentVariable("ICEHALOSTACK_SHOW_PERF"),
                "1",
                StringComparison.Ordinal))
            return;
        PerformanceOverlay.Visibility = Visibility.Visible;
        PerformanceText.Text = $"{snapshot.FramesPerSecond:F0} FPS · avg {snapshot.AverageMilliseconds:F1} ms · "
            + $"P95 {snapshot.P95Milliseconds:F1} ms · hitch {snapshot.HitchCount}";
    }

    private void OnClosed(object sender, WindowEventArgs args)
    {
        Closed -= OnClosed;
        _performanceMonitor.SnapshotUpdated -= OnPerformanceSnapshotUpdated;
        _performanceMonitor.Dispose();
    }
}
