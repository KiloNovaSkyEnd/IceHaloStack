using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json;

namespace IceHaloStack.WinUI.Client;

/// <summary>
/// Bindable state for one task.  The optional dispatcher is supplied by the
/// WinUI host so this transport assembly remains independent of Microsoft.UI.
/// </summary>
public sealed class IpcTaskViewModel : INotifyPropertyChanged, IDisposable
{
    private readonly IpcClient _client;
    private readonly Func<Action, Task>? _dispatchToUi;
    private IpcTaskState _state = IpcTaskState.Starting;
    private string _phase = string.Empty;
    private string _message = string.Empty;
    private int _completed;
    private int _total;
    private double? _fraction;
    private string? _error;
    private JsonElement? _result;
    private bool _disposed;

    public IpcTaskViewModel(
        IpcClient client,
        string taskId,
        Func<Action, Task>? dispatchToUi = null)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
        if (string.IsNullOrWhiteSpace(taskId))
            throw new ArgumentException("task_id 不能为空。", nameof(taskId));
        TaskId = taskId.Trim();
        _dispatchToUi = dispatchToUi;
        _client.ProgressReceived += OnProgressReceived;
        _client.TaskCompleted += OnTaskCompleted;
        _client.TransportError += OnTransportError;
        State = _client.GetTaskState(TaskId);
        if (_client.TryGetTaskResult(TaskId, out var terminal))
            ApplyTerminal(terminal);
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string TaskId { get; }
    public IpcTaskState State
    {
        get => _state;
        private set => SetField(ref _state, value);
    }

    public string StateLabel => State switch
    {
        IpcTaskState.Starting => "Starting",
        IpcTaskState.Started => "Started",
        IpcTaskState.Running => "Running",
        IpcTaskState.Cancelling => "Cancelling",
        IpcTaskState.Completed => "Completed",
        IpcTaskState.Cancelled => "Cancelled",
        IpcTaskState.Failed => "Failed",
        _ => "Unknown",
    };

    public string Phase
    {
        get => _phase;
        private set => SetField(ref _phase, value);
    }

    public string Message
    {
        get => _message;
        private set => SetField(ref _message, value);
    }

    public int Completed
    {
        get => _completed;
        private set
        {
            if (SetField(ref _completed, value))
                OnPropertyChanged(nameof(ProgressPercent));
        }
    }

    public int Total
    {
        get => _total;
        private set
        {
            if (SetField(ref _total, value))
                OnPropertyChanged(nameof(ProgressPercent));
        }
    }

    public double? Fraction
    {
        get => _fraction;
        private set
        {
            if (SetField(ref _fraction, value))
                OnPropertyChanged(nameof(ProgressPercent));
        }
    }

    /// <summary>Percentage value suitable for a WinUI ProgressBar (0..100).</summary>
    public double ProgressPercent
        => Fraction is { } fraction
            ? Math.Clamp(fraction * 100.0, 0.0, 100.0)
            : Total > 0
                ? Math.Clamp(Completed * 100.0 / Total, 0.0, 100.0)
                : 0.0;

    public bool IsBusy
        => State is IpcTaskState.Starting
            or IpcTaskState.Started
            or IpcTaskState.Running
            or IpcTaskState.Cancelling;

    public bool CanCancel
        => State is IpcTaskState.Starting
            or IpcTaskState.Started
            or IpcTaskState.Running;

    public string? Error
    {
        get => _error;
        private set => SetField(ref _error, value);
    }

    public JsonElement? Result
    {
        get => _result;
        private set => SetField(ref _result, value);
    }

    public async Task StartAsync(
        string operation,
        object? parameters = null,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        if (IsBusy)
            throw new InvalidOperationException($"任务正在运行：task_id={TaskId}。");
        PostToUi(() =>
        {
            State = IpcTaskState.Starting;
            Phase = string.Empty;
            Message = string.Empty;
            Completed = 0;
            Total = 0;
            Fraction = null;
            Error = null;
            Result = null;
        });
        try
        {
            await _client.StartTaskAsync(
                operation,
                parameters,
                TaskId,
                timeout,
                cancellationToken).ConfigureAwait(false);
            PostToUi(() =>
            {
                // A very fast task may have emitted progress (or even its
                // terminal result) before the start acknowledgement reaches
                // this continuation. Never regress that newer state.
                if (State == IpcTaskState.Starting)
                    State = IpcTaskState.Started;
            });
        }
        catch (Exception error)
        {
            PostToUi(() =>
            {
                State = IpcTaskState.Failed;
                Error = error.Message;
            });
            throw;
        }
    }

    public async Task CancelAsync(
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        if (!CanCancel)
            return;
        await _client.CancelTaskAsync(TaskId, timeout, cancellationToken).ConfigureAwait(false);
        PostToUi(() => State = IpcTaskState.Cancelling);
    }

    public void Dispose()
    {
        if (_disposed)
            return;
        _disposed = true;
        _client.ProgressReceived -= OnProgressReceived;
        _client.TaskCompleted -= OnTaskCompleted;
        _client.TransportError -= OnTransportError;
        GC.SuppressFinalize(this);
    }

    private void OnProgressReceived(IpcProgressEvent progress)
    {
        if (!string.Equals(progress.TaskId, TaskId, StringComparison.Ordinal))
            return;
        PostToUi(() =>
        {
            State = IpcTaskState.Running;
            Phase = progress.Phase;
            Completed = progress.Completed;
            Total = progress.Total;
            Fraction = progress.Fraction;
            Message = progress.Message;
        });
    }

    private void OnTaskCompleted(IpcTaskResult result)
    {
        if (!string.Equals(result.TaskId, TaskId, StringComparison.Ordinal))
            return;
        PostToUi(() => ApplyTerminal(result));
    }

    private void ApplyTerminal(IpcTaskResult result)
    {
        State = result.State;
        Error = result.Error;
        Result = result.Result;
        if (result.Ok)
        {
            Completed = Math.Max(Completed, Total);
            Fraction = 1.0;
        }
    }

    private void OnTransportError(Exception error)
    {
        if (!IsBusy)
            return;
        PostToUi(() =>
        {
            State = IpcTaskState.Failed;
            Error = error.Message;
        });
    }

    private void PostToUi(Action action)
    {
        if (_disposed)
            return;
        if (_dispatchToUi is null)
        {
            action();
            return;
        }
        _ = DispatchAsync(() =>
        {
            if (!_disposed)
                action();
        });
    }

    private async Task DispatchAsync(Action action)
    {
        try
        {
            await _dispatchToUi!(action).ConfigureAwait(false);
        }
        catch (Exception error)
        {
            // A dispatcher can disappear while a window is closing.  Keep the
            // IPC reader alive; the next lifecycle owner can inspect the error.
            if (!_disposed)
                Error = error.Message;
        }
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
            return false;
        field = value;
        OnPropertyChanged(propertyName);
        if (propertyName == nameof(State))
        {
            OnPropertyChanged(nameof(StateLabel));
            OnPropertyChanged(nameof(IsBusy));
            OnPropertyChanged(nameof(CanCancel));
        }
        return true;
    }

    private void OnPropertyChanged(string? propertyName)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
