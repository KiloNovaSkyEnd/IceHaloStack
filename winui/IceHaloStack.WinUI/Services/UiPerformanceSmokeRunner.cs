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
        var measurements = new List<UiNavigationMeasurement>();
        measurements.Add(await MeasureAsync(monitor, () => frame.Navigate(typeof(StackPage))));
        var coldStackPage = frame.Content;
        measurements.Add(await MeasureAsync(monitor, GoBack));
        measurements.Add(await MeasureAsync(monitor, () => frame.Navigate(typeof(StackPage))));
        var stackPageReused = ReferenceEquals(coldStackPage, frame.Content);
        measurements.Add(await MeasureAsync(monitor, GoBack));
        measurements.Add(await MeasureAsync(monitor, () => frame.Navigate(typeof(TimelapsePage))));
        var coldTimelapsePage = frame.Content;
        measurements.Add(await MeasureAsync(monitor, GoBack));
        measurements.Add(await MeasureAsync(monitor, () => frame.Navigate(typeof(TimelapsePage))));
        var timelapsePageReused = ReferenceEquals(coldTimelapsePage, frame.Content);
        measurements.Add(await MeasureAsync(monitor, GoBack));

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
}
