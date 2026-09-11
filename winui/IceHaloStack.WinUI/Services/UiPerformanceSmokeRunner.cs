using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Services;

/// <summary>Opt-in cold/warm page navigation benchmark for release QA.</summary>
internal static class UiPerformanceSmokeRunner
{
    private const string OutputEnvironmentVariable = "ICEHALOSTACK_PERF_SMOKE_PATH";

    public static async Task RunIfRequestedAsync(
        Window window,
        Frame frame,
        UiPerformanceMonitor monitor)
    {
        var outputPath = Environment.GetEnvironmentVariable(OutputEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(outputPath))
            return;

        await Task.Delay(350);
        var progressPath = Path.GetFullPath(outputPath) + ".progress.txt";
        File.WriteAllText(progressPath, "started\n");
        var measurements = new List<UiNavigationMeasurement>();
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Stack cold", () => frame.Navigate(typeof(StackPage))));
        var coldStackPage = frame.Content;
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Main from Stack", GoBack));
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Stack warm", () => frame.Navigate(typeof(StackPage))));
        var stackPageReused = ReferenceEquals(coldStackPage, frame.Content);
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Main from Stack warm", GoBack));
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Timelapse cold", () => frame.Navigate(typeof(TimelapsePage))));
        var coldTimelapsePage = frame.Content;
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Main from Timelapse", GoBack));
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Timelapse warm", () => frame.Navigate(typeof(TimelapsePage))));
        var timelapsePageReused = ReferenceEquals(coldTimelapsePage, frame.Content);
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Main from Timelapse warm", GoBack));
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Node cold", () => frame.Navigate(typeof(NodeWorkflowPage))));
        var coldNodePage = frame.Content;
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Main from Node", GoBack));
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Node warm", () => frame.Navigate(typeof(NodeWorkflowPage))));
        var nodePageReused = ReferenceEquals(coldNodePage, frame.Content);
        measurements.Add(await MeasureLoggedAsync(progressPath, monitor, "Main from Node warm", GoBack));

        // Keep a steady-state sample after the deliberate navigation hitches.
        // HitchCount still sees retained slow frames while FPS/P95 become useful.
        File.AppendAllText(progressPath, "begin steady-state sampling\n");
        await Task.Delay(5000);
        File.AppendAllText(progressPath, "end steady-state sampling\n");

        var fullPath = Path.GetFullPath(outputPath);
        var directory = Path.GetDirectoryName(fullPath);
        if (!string.IsNullOrWhiteSpace(directory))
            Directory.CreateDirectory(directory);
        var payload = new
        {
            generated_at = DateTimeOffset.Now,
            page_cache = new
            {
                stack_page_reused = stackPageReused,
                timelapse_page_reused = timelapsePageReused,
                node_workflow_page_reused = nodePageReused,
            },
            frame_snapshot = monitor.LatestSnapshot,
            measurements = measurements.Select((item, index) => new
            {
                sequence = index + 1,
                page = item.Page,
                milliseconds = Math.Round(item.Milliseconds, 2),
            }),
        };
        await File.WriteAllTextAsync(
            fullPath,
            JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
        File.AppendAllText(progressPath, "report-written\n");
        window.Close();

        bool GoBack()
        {
            if (!frame.CanGoBack)
                return false;
            frame.GoBack();
            return true;
        }
    }

    private static async Task<UiNavigationMeasurement> MeasureAsync(
        UiPerformanceMonitor monitor,
        Func<bool> navigate)
        => await monitor.MeasureNavigationAsync(navigate).WaitAsync(TimeSpan.FromSeconds(15));

    private static async Task<UiNavigationMeasurement> MeasureLoggedAsync(
        string progressPath, UiPerformanceMonitor monitor, string label, Func<bool> navigate)
    {
        File.AppendAllText(progressPath, $"begin {label}\n");
        var result = await MeasureAsync(monitor, navigate);
        File.AppendAllText(progressPath, $"end {label}: {result.Milliseconds:F2} ms\n");
        return result;
    }
}
