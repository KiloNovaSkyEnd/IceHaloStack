namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class NodeWorkflowViewModel
{
    public bool CanStart => GetExportValidationError() is null;

    public string ExportBlockReason => GetExportValidationError() ?? "已满足批量导出条件。";

    private string? GetExportValidationError()
    {
        if (_disposed)
            return "工作区已经关闭。";
        if (IsBusy)
            return "当前任务尚未结束。";
        if (Queue.Inputs.Count == 0)
            return "请先添加输入图像。";
        if (Queue.Groups.Count == 0)
            return "请先生成至少一个堆栈分组。";
        if (Queue.Groups.Any(group => group.FrameIndexes.Count == 0))
            return "存在空的堆栈分组，请重新生成分组。";
        if (string.IsNullOrWhiteSpace(OutputDirectory))
            return "请选择批量导出目录。";
        try
        {
            _ = Path.GetFullPath(OutputDirectory);
        }
        catch (Exception exception)
        {
            return $"导出目录无效：{exception.Message}";
        }

        var enabled = Flows.Where(flow => flow.IsEnabled).ToArray();
        if (enabled.Length == 0)
            return "请至少启用一个流程。";
        var exporting = enabled.Where(flow => flow.SaveSequence || flow.SaveVideo).ToArray();
        if (exporting.Length == 0)
            return "启用流程中没有选择序列或视频输出。";
        if (exporting.Any(flow => string.IsNullOrWhiteSpace(flow.Name)))
            return "启用流程的名称不能为空。";
        if (exporting.GroupBy(flow => flow.Name.Trim(), StringComparer.OrdinalIgnoreCase).Any(group => group.Count() > 1))
            return "启用流程的名称不能重复。";
        if (exporting.Any(flow => flow.SaveVideo
            && (double.IsNaN(flow.FramesPerSecond) || double.IsInfinity(flow.FramesPerSecond)
                || flow.FramesPerSecond <= 0 || flow.FramesPerSecond > 240)))
            return "视频帧率必须大于 0 且不超过 240 FPS。";

        // EWB switches deliberately do not participate here. The engine can
        // prepare these corrections headlessly, so toggling them can never
        // leave the export command permanently disabled.
        return null;
    }
}
