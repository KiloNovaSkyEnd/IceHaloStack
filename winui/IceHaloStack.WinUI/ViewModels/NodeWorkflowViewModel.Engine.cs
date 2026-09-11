using System.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using IceHaloStack.WinUI.Client;
using IceHaloStack_WinUI.Services;
using Microsoft.UI.Xaml.Media.Imaging;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class NodeWorkflowViewModel
{
    [RelayCommand(CanExecute = nameof(CanPreview))]
    private async Task GeneratePreviewAsync()
    {
        if (!CanPreview || SelectedFlow is null) return;
        var path = Path.Combine(Path.GetTempPath(), $"IceHaloStack-preview-{Guid.NewGuid():N}.png");
        _previewFiles.Add(path);
        IsBusy = true; Phase = "预览"; Status = "正在异步生成节点流程预览…";
        try
        {
            var client = await _engineClientProvider.GetClientAsync().ConfigureAwait(false);
            _task?.Dispose();
            var task = new IpcTaskViewModel(client, $"preview-{Guid.NewGuid():N}", DispatchToUiAsync);
            task.PropertyChanged += OnTaskChanged;
            _task = task;
            await task.StartAsync("node_workflow_preview", new Dictionary<string, object?>
            {
                ["input_paths"] = Queue.Inputs.Select(item => item.Path).ToArray(),
                ["group"] = Queue.Groups[Math.Clamp(ReferenceGroupIndex, 0, Queue.Groups.Count - 1)].FrameIndexes.ToArray(),
                ["method"] = Queue.StackMethod,
                ["backend"] = Queue.Compute.SelectedBackend, ["config"] = SelectedFlow.Processing.ToIpcConfig(),
                ["curve_points"] = SelectedFlow.Processing.ToCurvePoints(), ["max_side"] = 1200,
                ["output_path"] = path, ["ewb"] = ToEwbConfig(),
            }).ConfigureAwait(false);
            var result = await client.WaitForTaskAsync(task.TaskId).ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                IsBusy = false; CanCancel = false;
                if (!result.Ok) { FinishFailure("预览失败。", result.Error ?? "未知错误"); return; }
                PreviewSource = new BitmapImage(new Uri(path));
                Phase = "预览完成"; Status = "高质量代理预览已更新。";
            }).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() => FinishFailure("预览失败。", exception.Message)).ConfigureAwait(false);
        }
    }

    private bool CanPreview => CanEdit && SelectedFlow is not null && Queue.Inputs.Count > 0 && Queue.Groups.Count > 0;

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartExportAsync()
    {
        if (!CanStart) return;
        var enabled = Flows.Where(flow => flow.IsEnabled && (flow.SaveSequence || flow.SaveVideo)).ToArray();
        if (enabled.Any(flow => string.IsNullOrWhiteSpace(flow.Name)))
        {
            ShowError("流程名称不能为空。");
            return;
        }
        if (enabled.GroupBy(flow => flow.Name.Trim(), StringComparer.OrdinalIgnoreCase).Any(group => group.Count() > 1))
        {
            ShowError("启用的流程名称不能重复，否则导出文件会互相覆盖。");
            return;
        }
        Directory.CreateDirectory(OutputDirectory);
        IsBusy = true; CanCancel = false; HasError = false; ProgressPercent = 0;
        Phase = "连接"; Status = "正在连接节点工作流引擎…";
        try
        {
            var client = await _engineClientProvider.GetClientAsync().ConfigureAwait(false);
            _task?.Dispose();
            var task = new IpcTaskViewModel(client, $"node-{Guid.NewGuid():N}", DispatchToUiAsync);
            task.PropertyChanged += OnTaskChanged;
            _task = task;
            var parameters = new Dictionary<string, object?>
            {
                ["input_paths"] = Queue.Inputs.Select(item => item.Path).ToArray(),
                ["groups"] = Queue.Groups.Select(group => group.FrameIndexes.ToArray()).ToArray(),
                ["method"] = Queue.StackMethod,
                ["backend"] = Queue.Compute.SelectedBackend,
                ["output_directory"] = OutputDirectory,
                ["ewb"] = ToEwbConfig(),
                ["flows"] = enabled.Select(flow => flow.ToIpcFlow()).ToArray(),
            };
            await task.StartAsync("node_workflow_export", parameters).ConfigureAwait(false);
            _ = ObserveResultAsync(client, task);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() => FinishFailure("无法启动节点工作流。", exception.Message)).ConfigureAwait(false);
        }
    }

    [RelayCommand(CanExecute = nameof(CanCancel))]
    private async Task CancelAsync()
    {
        if (_task is null || !CanCancel) return;
        await _task.CancelAsync().ConfigureAwait(false);
    }

    private async Task ObserveResultAsync(IpcClient client, IpcTaskViewModel task)
    {
        try
        {
            var result = await client.WaitForTaskAsync(task.TaskId).ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                if (!ReferenceEquals(task, _task)) return;
                IsBusy = false; CanCancel = false;
                if (result.Ok)
                {
                    ProgressPercent = 100; Phase = "完成";
                    Status = $"原生节点工作流导出完成：{OutputDirectory}";
                }
                else if (result.Cancelled) { Phase = "已取消"; Status = "节点工作流已取消。"; }
                else FinishFailure("节点工作流导出失败。", result.Error ?? "未知错误");
            }).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() => FinishFailure("节点引擎连接中断。", exception.Message)).ConfigureAwait(false);
        }
    }

    private void OnTaskChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (sender is not IpcTaskViewModel task || !ReferenceEquals(task, _task)) return;
        ProgressPercent = task.ProgressPercent;
        IsBusy = task.IsBusy;
        CanCancel = task.CanCancel;
        if (!string.IsNullOrWhiteSpace(task.Phase)) Phase = task.Phase;
        if (!string.IsNullOrWhiteSpace(task.Message)) Status = task.Message;
    }

    private void FinishFailure(string status, string error)
    {
        IsBusy = false; CanCancel = false; Phase = "失败"; Status = status; ShowError(error);
    }

    private static Task DispatchToUiAsync(Action action)
    {
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!App.DispatcherQueue.TryEnqueue(() => { try { action(); done.SetResult(); } catch (Exception e) { done.SetException(e); } }))
            done.SetException(new InvalidOperationException("WinUI 调度器已关闭。"));
        return done.Task;
    }
}
