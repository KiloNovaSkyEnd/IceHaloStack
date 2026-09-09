namespace IceHaloStack_WinUI.ViewModels;

/// <summary>
/// First WinUI migration slice of the legacy timelapse workspace.  It reuses
/// the stack workspace verbatim and exports one TIFF master per generated
/// group; the legacy processing-chain preview and video encoder are separate
/// migration stages.
/// </summary>
public sealed class TimelapsePageViewModel : IAsyncDisposable
{
    public TimelapsePageViewModel()
    {
        Workspace = new StackPageViewModel
        {
            GroupingMode = StackGroupingMode.SlidingWindow,
            GroupingStep = 1,
            OutputFileNamePattern = "timelapse_{center:000.##}_{start:000}-{end:000}",
        };
    }

    /// <summary>Shared queue, grouping, naming and task-ID IPC model.</summary>
    public StackPageViewModel Workspace { get; }

    public string Title => "堆栈延时序列";

    public string Subtitle => "按时间窗口生成多个 Master，并批量导出为 TIFF 序列。";

    public string ScopeNote => "堆栈、完整固定处理链、TIFF 序列与 FFmpeg 视频均通过独立服务执行；高级节点图和关键帧平滑仍由经典工作区提供。";

    /// <summary>
    /// Sets the timelapse-oriented defaults only for the first selected batch.
    /// Subsequent queue edits remain explicit until the user regenerates groups.
    /// </summary>
    public void AddInputPaths(IEnumerable<string> paths)
    {
        ArgumentNullException.ThrowIfNull(paths);
        var wasEmpty = Workspace.Inputs.Count == 0;
        Workspace.AddInputPaths(paths);
        if (!wasEmpty || Workspace.Inputs.Count == 0)
            return;

        var defaultWindow = Math.Min(15, Workspace.Inputs.Count);
        Workspace.GenerateGroupsForPreset(
            StackGroupingMode.SlidingWindow,
            defaultWindow,
            step: 1);
    }

    public ValueTask DisposeAsync() => Workspace.DisposeAsync();
}
