using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

internal static class NodeParameterEditorFactory
{
    public static FrameworkElement Create(NodeWorkflowNode node, NodeFlowViewModel flow, StackPageViewModel queue)
        => node.Key switch
        {
            "stack" => StackSummary(queue),
            "basic" => new ClassicBasePanel { ViewModel = flow.Processing, MinWidth = 520 },
            "bgr" => BgrEditor(flow.Processing),
            "channel" => new ClassicChannelPanel { ViewModel = flow.Processing, MinWidth = 460 },
            "output" => new NodeOutputEditorControl { ViewModel = flow },
            "stretch" or "usm" or "highpass" or "emboss" =>
                new NodeStageEditorControl { ViewModel = flow.Processing, StageKey = node.Key },
            _ => new TextBlock { Text = $"节点 {node.Key} 尚无可编辑参数。", TextWrapping = TextWrapping.Wrap },
        };

    private static FrameworkElement BgrEditor(ProcessingSettingsViewModel processing) => new StackPanel
    {
        MinWidth = 520,
        Spacing = 8,
        Children =
        {
            new NodeStageEditorControl { ViewModel = processing, StageKey = "background" },
            new ClassicCurvesPanel { ViewModel = processing },
        },
    };

    private static FrameworkElement StackSummary(StackPageViewModel queue) => new StackPanel
    {
        MinWidth = 430,
        Spacing = 8,
        Children =
        {
            new TextBlock { Text = "Stack 使用左侧“参考堆栈”参数。", TextWrapping = TextWrapping.Wrap },
            new TextBlock { Text = $"输入：{queue.InputCount} 帧 · 分组：{queue.GroupCount} · 方法：{queue.StackMethod}" },
            new TextBlock { Text = $"计算后端：{queue.Compute.SelectedBackend}" },
        },
    };
}
