using System.ComponentModel;
using System.Text.Json;
using CommunityToolkit.Mvvm.Input;
using IceHaloStack.WinUI.Client;
using IceHaloStack_WinUI.Services;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class StackPageViewModel
{
    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartStackAsync()
    {
        if (_disposed)
            return;
        var validationError = GetRequestValidationError();
        if (validationError is not null)
        {
            ShowError(validationError);
            Status = "请修正堆栈队列后再开始。";
            RefreshCommandAvailability();
            return;
        }

        ClearError();
        IsBusy = true;
        CanCancel = false;
        ProgressPercent = 0.0;
        IsPaused = false;
        Phase = "连接";
        Status = "正在连接 Python 图像堆栈引擎…";
        RefreshWorkspaceState();

        try
        {
            var client = await _engineClientProvider.GetClientAsync().ConfigureAwait(false);
            DetachTask();
            var task = new IpcTaskViewModel(
                client,
                $"winui-stack-{Guid.NewGuid():N}",
                DispatchToUiAsync);
            task.PropertyChanged += OnTaskPropertyChanged;
            _task = task;

            var parameters = new Dictionary<string, object?>
            {
                ["input_paths"] = Inputs.Select(item => item.Path).ToArray(),
                ["groups"] = Groups.Select(group => group.FrameIndexes.ToArray()).ToArray(),
                ["output_paths"] = Groups.Select(group => group.OutputPath).ToArray(),
                ["method"] = StackMethod,
                ["backend"] = Compute.SelectedBackend,
                ["format"] = "TIFF 32-bit Float",
                ["config"] = Processing.ToIpcConfig(),
                ["curve_points"] = Processing.ToCurvePoints(),
            };
            if (Video.Enabled)
                parameters["video"] = Video.ToIpcRequest();
            await task.StartAsync("stack_files", parameters).ConfigureAwait(false);

            await DispatchToUiAsync(() => RefreshFromTask(task)).ConfigureAwait(false);
            _ = ObserveTerminalResultAsync(client, task);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() =>
            {
                IsBusy = false;
                CanCancel = false;
                Phase = "失败";
                Status = "无法提交堆栈任务。";
                ShowError(exception.Message);
                RefreshWorkspaceState();
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
        Video.PropertyChanged -= OnVideoPropertyChanged;
        DetachTask();
        foreach (var input in Inputs)
            input.PropertyChanged -= OnInputPropertyChanged;
        foreach (var group in Groups)
            group.PropertyChanged -= OnGroupPropertyChanged;
        DeletePreviewFiles();
        await _engineClientProvider.DisposeAsync().ConfigureAwait(false);
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
                    if (result.Result is { } resultPayload
                        && resultPayload.TryGetProperty("backend", out var backendPayload))
                        Compute.ApplyTaskBackend(backendPayload);
                    ProgressPercent = 100.0;
                    Phase = "完成";
                    Status = DescribeSuccess(result);
                    IsPaused = false;
                }
                else if (result.Cancelled)
                {
                    ClearError();
                    Phase = "已取消";
                    Status = "堆栈任务已取消。";
                    IsPaused = false;
                }
                else
                {
                    Phase = "失败";
                    Status = "Python 引擎报告堆栈任务失败。";
                    ShowError(result.Error ?? "未返回错误详情。");
                }
                RefreshWorkspaceState();
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
                Status = "与 Python 图像堆栈引擎的连接已中断。";
                ShowError(exception.Message);
                RefreshWorkspaceState();
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
            && payload.TryGetProperty("output_paths", out var paths)
            && paths.ValueKind == JsonValueKind.Array)
        {
            var saved = paths.EnumerateArray()
                .Where(path => path.ValueKind == JsonValueKind.String)
                .Select(path => path.GetString())
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .ToArray();
            var video = payload.TryGetProperty("video_path", out var videoPath)
                && videoPath.ValueKind == JsonValueKind.String
                ? videoPath.GetString()
                : null;
            var summary = saved.Length switch
            {
                0 => "堆栈完成。",
                1 => $"堆栈完成：{saved[0]}",
                _ => $"已完成 {saved.Length} 个堆栈输出。",
            };
            return string.IsNullOrWhiteSpace(video) ? summary : $"{summary} 视频：{video}";
        }
        return "堆栈完成。";
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

    private void DetachTask()
    {
        if (_task is null)
            return;
        _task.PropertyChanged -= OnTaskPropertyChanged;
        _task.Dispose();
        _task = null;
    }
}
