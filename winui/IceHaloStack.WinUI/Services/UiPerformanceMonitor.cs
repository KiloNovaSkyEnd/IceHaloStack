using System.Diagnostics;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;

namespace IceHaloStack_WinUI.Services;

internal sealed record UiFrameSnapshot(
    double FramesPerSecond,
    double AverageMilliseconds,
    double P95Milliseconds,
    double MaximumMilliseconds,
    int HitchCount);

internal sealed record UiNavigationMeasurement(string Page, double Milliseconds);

/// <summary>
/// Samples compositor render intervals and measures navigation through the
/// first rendered frame. It performs no disk I/O and publishes at most once
/// per second, keeping instrumentation out of the UI hot path.
/// </summary>
internal sealed class UiPerformanceMonitor : IDisposable
{
    private const int SampleCapacity = 600;
    private readonly Queue<double> _frameTimes = new(SampleCapacity);
    private Frame? _frame;
    private long _lastFrameTimestamp;
    private long _snapshotTimestamp;
    private long _navigationTimestamp;
    private string _navigationPage = string.Empty;
    private bool _awaitingNavigationFrame;
    private TaskCompletionSource<UiNavigationMeasurement>? _navigationCompletion;

    public event Action<UiFrameSnapshot>? SnapshotUpdated;
    public event Action<UiNavigationMeasurement>? NavigationMeasured;

    public UiFrameSnapshot? LatestSnapshot { get; private set; }

    public void Start(Frame frame)
    {
        if (_frame is not null)
            throw new InvalidOperationException("UI performance monitor is already running.");
        _frame = frame;
        _lastFrameTimestamp = Stopwatch.GetTimestamp();
        _snapshotTimestamp = _lastFrameTimestamp;
        frame.Navigating += OnNavigating;
        frame.Navigated += OnNavigated;
        CompositionTarget.Rendering += OnRendering;
    }

    public Task<UiNavigationMeasurement> MeasureNavigationAsync(Func<bool> navigate)
    {
        ArgumentNullException.ThrowIfNull(navigate);
        if (_navigationCompletion is not null)
            throw new InvalidOperationException("A navigation measurement is already active.");

        var completion = new TaskCompletionSource<UiNavigationMeasurement>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        _navigationCompletion = completion;
        if (!navigate())
        {
            _navigationCompletion = null;
            completion.SetException(new InvalidOperationException("Frame rejected navigation."));
        }
        return completion.Task;
    }

    public void Dispose()
    {
        CompositionTarget.Rendering -= OnRendering;
        if (_frame is not null)
        {
            _frame.Navigating -= OnNavigating;
            _frame.Navigated -= OnNavigated;
            _frame = null;
        }
        _navigationCompletion?.TrySetCanceled();
        _navigationCompletion = null;
    }

    private void OnNavigating(object sender, NavigatingCancelEventArgs args)
    {
        _navigationTimestamp = Stopwatch.GetTimestamp();
        _navigationPage = args.SourcePageType?.Name ?? "UnknownPage";
        _awaitingNavigationFrame = false;
    }

    private void OnNavigated(object sender, NavigationEventArgs args)
    {
        _navigationPage = args.SourcePageType?.Name ?? _navigationPage;
        _awaitingNavigationFrame = true;
    }

    private void OnRendering(object? sender, object args)
    {
        var now = Stopwatch.GetTimestamp();
        var frameMilliseconds = ElapsedMilliseconds(_lastFrameTimestamp, now);
        _lastFrameTimestamp = now;
        if (frameMilliseconds > 0 && frameMilliseconds < 1000)
        {
            if (_frameTimes.Count == SampleCapacity)
                _frameTimes.Dequeue();
            _frameTimes.Enqueue(frameMilliseconds);
        }

        if (_awaitingNavigationFrame)
        {
            _awaitingNavigationFrame = false;
            var measurement = new UiNavigationMeasurement(
                _navigationPage,
                ElapsedMilliseconds(_navigationTimestamp, now));
            Debug.WriteLine($"[UI PERF] Navigation {measurement.Page}: {measurement.Milliseconds:F1} ms");
            NavigationMeasured?.Invoke(measurement);
            _navigationCompletion?.TrySetResult(measurement);
            _navigationCompletion = null;
        }

        if (ElapsedMilliseconds(_snapshotTimestamp, now) < 1000 || _frameTimes.Count == 0)
            return;
        _snapshotTimestamp = now;
        var ordered = _frameTimes.Order().ToArray();
        var average = ordered.Average();
        var p95Index = Math.Clamp((int)Math.Ceiling(ordered.Length * 0.95) - 1, 0, ordered.Length - 1);
        var snapshot = new UiFrameSnapshot(
            FramesPerSecond: average <= 0 ? 0 : 1000.0 / average,
            AverageMilliseconds: average,
            P95Milliseconds: ordered[p95Index],
            MaximumMilliseconds: ordered[^1],
            HitchCount: ordered.Count(value => value >= 50));
        LatestSnapshot = snapshot;
        SnapshotUpdated?.Invoke(snapshot);
    }

    private static double ElapsedMilliseconds(long start, long end)
        => (end - start) * 1000.0 / Stopwatch.Frequency;
}
