using System.ComponentModel;
using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using IceHaloStack.WinUI.Client;
using IceHaloStack_WinUI.Services;

namespace IceHaloStack_WinUI.ViewModels;

/// <summary>
/// UI state for the first WinUI migration page: a single image-processing
/// request sent to the Python engine through the local IPC client.
/// </summary>
public sealed partial class MainPageViewModel : ObservableObject, IAsyncDisposable
{
    private IpcClient? _client;
    private IpcTaskViewModel? _task;
    private bool _disposed;

    [ObservableProperty]
    private string _inputPath = string.Empty;

    [ObservableProperty]
    private string _outputPath = string.Empty;

    [ObservableProperty]
    private bool _enableStretch;

    [ObservableProperty]
    private double _stretchStrength = 8.0;

    [ObservableProperty]
    private bool _isBusy;

    [ObservableProperty]
    private bool _canCancel;

    [ObservableProperty]
    private double _progressPercent;

    [ObservableProperty]
    private string _phase = "准备就绪";

    [ObservableProperty]
    private string _status = "请选择输入图像和 PNG 输出位置。";

    [ObservableProperty]
    private string _error = string.Empty;

    [ObservableProperty]
    private bool _hasError;

    public bool CanStart => !IsBusy && HasValidPaths();

    /// <summary>Keep page navigation from disposing an active engine task.</summary>
    public bool CanNavigate => !IsBusy;

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartProcessingAsync()
    {
        if (!CanStart || _disposed)
            return;

        ClearError();
        IsBusy = true;
        CanCancel = false;
        ProgressPercent = 0.0;
        Phase = "连接";
        Status = "正在连接 Python 图像处理引擎…";
        RefreshCommandAvailability();

        try
        {
            var client = await GetClientAsync();
            DetachTask();
            var task = new IpcTaskViewModel(
                client,
                $"winui-{Guid.NewGuid():N}",
                DispatchToUiAsync);
            task.PropertyChanged += OnTaskPropertyChanged;
            _task = task;

            await task.StartAsync(
                "process_file",
                new Dictionary<string, object?>
                {
                    ["input_path"] = InputPath,
                    ["output_path"] = OutputPath,
                    ["config"] = new Dictionary<string, object?>
                    {
                        ["stretch"] = EnableStretch,
                        ["stretch_strength"] = StretchStrength,
                    },
                    ["format"] = "PNG 8-bit",
                });

            RefreshFromTask(task);
            _ = ObserveTerminalResultAsync(client, task);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() =>
            {
                IsBusy = false;
                CanCancel = false;
                Phase = "失败";
                Status = "无法提交处理任务。";
                ShowError(exception.Message);
                RefreshCommandAvailability();
            }).ConfigureAwait(false);
        }
    }

    [RelayCommand(CanExecute = nameof(CanCancel))]
    private async Task CancelAsync()
    {
        if (_task is null || !CanCancel)
            return;

        try
        {
            await _task.CancelAsync().ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                Phase = "取消";
                Status = "已请求取消，正在等待 Python 引擎安全结束…";
                RefreshFromTask(_task);
            }).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() => ShowError(exception.Message)).ConfigureAwait(false);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed)
            return;
        _disposed = true;
        DetachTask();
        if (_client is not null)
        {
            await _client.DisposeAsync().ConfigureAwait(false);
            _client = null;
        }
    }

    partial void OnInputPathChanged(string value) => RefreshCommandAvailability();
    partial void OnOutputPathChanged(string value) => RefreshCommandAvailability();
    partial void OnIsBusyChanged(bool value)
    {
        OnPropertyChanged(nameof(CanNavigate));
        RefreshCommandAvailability();
    }
    partial void OnCanCancelChanged(bool value) => RefreshCommandAvailability();

    private async Task<IpcClient> GetClientAsync()
    {
        if (_client is { IsAlive: true })
            return _client;

        if (_client is not null)
        {
            await _client.DisposeAsync().ConfigureAwait(false);
            _client = null;
        }

        var client = EngineClientFactory.CreateDevelopmentClient();
        try
        {
            await client.StartAsync().ConfigureAwait(false);
            await client.PingAsync(TimeSpan.FromSeconds(12)).ConfigureAwait(false);
            _client = client;
            return client;
        }
        catch
        {
            await client.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }

    private async Task ObserveTerminalResultAsync(IpcClient client, IpcTaskViewModel task)
    {
        try
        {
            var result = await client.WaitForTaskAsync(task.TaskId).ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                if (!ReferenceEquals(task, _task))
                    return;
                RefreshFromTask(task);
                if (result.Ok)
                {
                    ProgressPercent = 100.0;
                    Phase = "完成";
                    Status = DescribeSuccess(result);
                }
                else if (result.Cancelled)
                {
                    ClearError();
                    Phase = "已取消";
                    Status = "处理任务已取消。";
                }
                else
                {
                    Phase = "失败";
                    Status = "Python 引擎报告任务失败。";
                    ShowError(result.Error ?? "未返回错误详情。");
                }
                RefreshCommandAvailability();
            }).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() =>
            {
                if (!ReferenceEquals(task, _task))
                    return;
                IsBusy = false;
                CanCancel = false;
                Phase = "失败";
                Status = "与 Python 图像处理引擎的连接已中断。";
                ShowError(exception.Message);
                RefreshCommandAvailability();
            }).ConfigureAwait(false);
        }
    }

    private void OnTaskPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (sender is IpcTaskViewModel task && ReferenceEquals(task, _task))
            RefreshFromTask(task);
    }

    private void RefreshFromTask(IpcTaskViewModel task)
    {
        ProgressPercent = task.ProgressPercent;
        IsBusy = task.IsBusy;
        CanCancel = task.CanCancel;
        if (!string.IsNullOrWhiteSpace(task.Phase))
            Phase = task.Phase;
        if (!string.IsNullOrWhiteSpace(task.Message))
            Status = task.Message;
        if (task.State != IpcTaskState.Cancelled && !string.IsNullOrWhiteSpace(task.Error))
            ShowError(task.Error);
        RefreshCommandAvailability();
    }

    private static string DescribeSuccess(IpcTaskResult result)
    {
        if (result.Result is { } payload
            && payload.TryGetProperty("output_path", out var path)
            && path.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(path.GetString()))
            return $"处理完成：{path.GetString()}";
        return "处理完成。";
    }

    private static Task DispatchToUiAsync(Action action)
    {
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!App.DispatcherQueue.TryEnqueue(() =>
        {
            try
            {
                action();
                completion.SetResult();
            }
            catch (Exception exception)
            {
                completion.SetException(exception);
            }
        }))
        {
            completion.SetException(new InvalidOperationException("WinUI 调度器已关闭。"));
        }
        return completion.Task;
    }

    private bool HasValidPaths()
    {
        if (string.IsNullOrWhiteSpace(InputPath) || string.IsNullOrWhiteSpace(OutputPath))
            return false;
        try
        {
            var outputDirectory = Path.GetDirectoryName(Path.GetFullPath(OutputPath));
            return File.Exists(InputPath)
                && string.Equals(Path.GetExtension(OutputPath), ".png", StringComparison.OrdinalIgnoreCase)
                && !string.IsNullOrWhiteSpace(outputDirectory)
                && Directory.Exists(outputDirectory);
        }
        catch (Exception)
        {
            return false;
        }
    }

    private void ShowError(string message)
    {
        Error = message;
        HasError = !string.IsNullOrWhiteSpace(message);
    }

    private void ClearError()
    {
        Error = string.Empty;
        HasError = false;
    }

    private void DetachTask()
    {
        if (_task is null)
            return;
        _task.PropertyChanged -= OnTaskPropertyChanged;
        _task.Dispose();
        _task = null;
    }

    private void RefreshCommandAvailability()
    {
        StartProcessingCommand.NotifyCanExecuteChanged();
        CancelCommand.NotifyCanExecuteChanged();
    }
}
