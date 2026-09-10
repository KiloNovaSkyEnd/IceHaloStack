using System.Diagnostics;

namespace IceHaloStack.WinUI.Client;

/// <summary>Coalesces high-frequency worker updates before they reach the UI dispatcher.</summary>
internal sealed class ProgressUpdateCoalescer<T> : IDisposable
{
    private readonly object _gate = new();
    private readonly Action<T> _sink;
    private readonly TimeSpan _interval;
    private readonly Timer _timer;
    private T? _pending;
    private bool _hasPending;
    private long _lastEmission;
    private bool _disposed;

    public ProgressUpdateCoalescer(Action<T> sink, TimeSpan? interval = null)
    {
        _sink = sink;
        _interval = interval ?? TimeSpan.FromMilliseconds(80);
        _timer = new Timer(OnTimer, null, Timeout.InfiniteTimeSpan, Timeout.InfiniteTimeSpan);
    }

    public void Submit(T item)
    {
        T? immediate = default;
        lock (_gate)
        {
            if (_disposed)
                return;
            var elapsed = Stopwatch.GetElapsedTime(_lastEmission);
            if (!_hasPending && elapsed >= _interval)
            {
                _lastEmission = Stopwatch.GetTimestamp();
                immediate = item;
            }
            else
            {
                _pending = item;
                _hasPending = true;
                var delay = elapsed >= _interval ? TimeSpan.Zero : _interval - elapsed;
                _timer.Change(delay, Timeout.InfiniteTimeSpan);
            }
        }
        if (immediate is not null)
            _sink(immediate);
    }

    public void Flush()
    {
        T? latest = default;
        lock (_gate)
        {
            if (_disposed || !_hasPending)
                return;
            latest = _pending;
            _pending = default;
            _hasPending = false;
            _lastEmission = Stopwatch.GetTimestamp();
            _timer.Change(Timeout.InfiniteTimeSpan, Timeout.InfiniteTimeSpan);
        }
        if (latest is not null)
            _sink(latest);
    }

    public void Dispose()
    {
        lock (_gate)
        {
            if (_disposed)
                return;
            _disposed = true;
            _pending = default;
            _hasPending = false;
        }
        _timer.Dispose();
    }

    private void OnTimer(object? state) => Flush();
}
