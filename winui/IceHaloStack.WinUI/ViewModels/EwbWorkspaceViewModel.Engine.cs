using System.Text.Json;
using IceHaloStack.WinUI.Client;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class EwbWorkspaceViewModel
{
    private async Task RunTableTaskAsync(string method, Dictionary<string, object?> parameters, string message)
    {
        var result = await RunTaskAsync(method, parameters, message).ConfigureAwait(false);
        if (result is null) return;
        await DispatchToUiAsync(() => ApplyTable(result.Value)).ConfigureAwait(false);
        await PreviewAsync().ConfigureAwait(false);
    }

    private async Task<JsonElement?> RunTaskAsync(string method, Dictionary<string, object?> parameters, string message)
    {
        await DispatchToUiAsync(() => { IsBusy = true; Error = string.Empty; ProgressPercent = 0; Status = message; }).ConfigureAwait(false);
        try
        {
            var client = await _engineClientProvider.GetClientAsync().ConfigureAwait(false);
            _task?.Dispose();
            var task = new IpcTaskViewModel(client, $"ewb-{Guid.NewGuid():N}", DispatchToUiAsync);
            task.PropertyChanged += (_, _) =>
            {
                if (!ReferenceEquals(task, _task)) return;
                ProgressPercent = task.ProgressPercent;
                if (!string.IsNullOrWhiteSpace(task.Message)) Status = task.Message;
            };
            _task = task;
            await task.StartAsync(method, parameters).ConfigureAwait(false);
            var result = await client.WaitForTaskAsync(task.TaskId).ConfigureAwait(false);
            if (!result.Ok || result.Result is null)
            {
                await DispatchToUiAsync(() => { Error = result.Error ?? "引擎未返回结果。"; Status = "处理失败。"; }).ConfigureAwait(false);
                return null;
            }
            return result.Result.Value.Clone();
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() => { Error = exception.Message; Status = "无法完成曝光/白平衡处理。"; }).ConfigureAwait(false);
            return null;
        }
        finally
        {
            await DispatchToUiAsync(() => { IsBusy = false; RefreshCommands(); }).ConfigureAwait(false);
        }
    }

    private void ApplyTable(JsonElement table)
    {
        _table = table.Clone();
        var exposure = ReadArray(table, "exposure_metric");
        var ev = ReadArray(table, "ev_correction");
        ExposureMetricSeries = exposure;
        ExposureSmoothSeries = ReadArray(table, "exposure_smooth");
        ExposureTargetSeries = ReadArray(table, "exposure_target");
        TemperatureMetricSeries = ReadArray(table, "temp_metric");
        TemperatureSmoothSeries = ReadArray(table, "temp_smooth");
        TemperatureTargetSeries = ReadArray(table, "temp_target");
        TintMetricSeries = ReadArray(table, "tint_metric");
        TintSmoothSeries = ReadArray(table, "tint_smooth");
        TintTargetSeries = ReadArray(table, "tint_target");
        OnPropertyChanged(nameof(ExposureMetricSeries)); OnPropertyChanged(nameof(ExposureSmoothSeries)); OnPropertyChanged(nameof(ExposureTargetSeries));
        OnPropertyChanged(nameof(TemperatureMetricSeries)); OnPropertyChanged(nameof(TemperatureSmoothSeries)); OnPropertyChanged(nameof(TemperatureTargetSeries));
        OnPropertyChanged(nameof(TintMetricSeries)); OnPropertyChanged(nameof(TintSmoothSeries)); OnPropertyChanged(nameof(TintTargetSeries));
        var temp = ReadDelta(table, "temp_target", "temp_metric");
        var tint = ReadDelta(table, "tint_target", "tint_metric");
        for (var index = 0; index < Frames.Count; index++)
        {
            var frame = Frames[index];
            frame.MeasuredExposure = At(exposure, index);
            if (!frame.IsKeyframe)
            {
                frame.ExposureCorrection = At(ev, index);
                frame.TemperatureCorrection = At(temp, index);
                frame.TintCorrection = At(tint, index);
            }
        }
        ProgressPercent = 100; Status = $"已生成 {Frames.Count} 帧平滑修正，可继续编辑关键帧。";
        RefreshCommands();
    }

    private static double[] ReadArray(JsonElement root, string name) =>
        root.TryGetProperty(name, out var array) && array.ValueKind == JsonValueKind.Array
            ? array.EnumerateArray().Select(value => value.GetDouble()).ToArray() : [];

    private static double[] ReadDelta(JsonElement root, string targetName, string metricName)
    {
        var target = ReadArray(root, targetName); var metric = ReadArray(root, metricName);
        return target.Select((value, index) => value - At(metric, index)).ToArray();
    }

    private static double At(double[] values, int index) => index >= 0 && index < values.Length ? values[index] : 0;

    private static Task DispatchToUiAsync(Action action)
    {
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!App.DispatcherQueue.TryEnqueue(() => { try { action(); done.SetResult(); } catch (Exception e) { done.SetException(e); } }))
            done.SetException(new InvalidOperationException("WinUI 调度器已关闭。"));
        return done.Task;
    }
}
