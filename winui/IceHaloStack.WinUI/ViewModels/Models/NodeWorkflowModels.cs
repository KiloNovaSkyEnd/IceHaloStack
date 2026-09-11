using System.Collections.ObjectModel;
using System.ComponentModel;
using CommunityToolkit.Mvvm.ComponentModel;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class NodeWorkflowNode : ObservableObject
{
    public NodeWorkflowNode(string key, string title, double x, double y)
        => (Key, Title, X, Y) = (key, title, x, y);

    public string Key { get; }
    public string Title { get; }
    [ObservableProperty] private bool _isEnabled = true;
    [ObservableProperty] private double _x;
    [ObservableProperty] private double _y;
}

public sealed partial class NodeFlowViewModel : ObservableObject
{
    public NodeFlowViewModel(string name)
    {
        _name = name;
        Processing.PropertyChanged += OnProcessingChanged;
        Nodes =
        [
            new("stack", "Stack\n堆栈", 190, 35),
            new("stretch", "Stretch\n拉伸", 190, 135),
            new("basic", "Base\n基础调色", 190, 235),
            new("usm", "USM\n锐化", 190, 335),
            new("bgr", "BGR\n背景/曲线", 440, 335),
            new("highpass", "High Pass\n高反差", 440, 235),
            new("emboss", "Emboss\n浮雕", 440, 135),
            new("channel", "Channel\n通道", 440, 35),
            new("output", "Output\n输出", 690, 35),
        ];
        SyncNodes();
    }

    [ObservableProperty] private string _name;
    [ObservableProperty] private bool _isEnabled = true;
    [ObservableProperty] private bool _saveSequence = true;
    [ObservableProperty] private bool _saveVideo;
    [ObservableProperty] private string _videoFormat = "MP4 H.264";
    [ObservableProperty] private double _framesPerSecond = 24;
    public ProcessingSettingsViewModel Processing { get; } = new();
    public ObservableCollection<NodeWorkflowNode> Nodes { get; }
    public IReadOnlyList<string> VideoFormats { get; } = ["MP4 H.264", "MOV H.264", "MOV ProRes", "GIF"];

    public NodeFlowViewModel Clone(string name)
    {
        var copy = new NodeFlowViewModel(name)
        {
            IsEnabled = IsEnabled, SaveSequence = SaveSequence, SaveVideo = SaveVideo,
            VideoFormat = VideoFormat, FramesPerSecond = FramesPerSecond,
        };
        copy.Processing.CopyFrom(Processing);
        for (var index = 0; index < Math.Min(Nodes.Count, copy.Nodes.Count); index++)
        {
            copy.Nodes[index].X = Nodes[index].X;
            copy.Nodes[index].Y = Nodes[index].Y;
        }
        return copy;
    }

    public Dictionary<string, object?> ToIpcFlow() => new()
    {
        ["name"] = Name,
        ["enabled"] = IsEnabled,
        ["save_sequence"] = SaveSequence,
        ["save_video"] = SaveVideo,
        ["video_format"] = VideoFormat,
        ["fps"] = FramesPerSecond,
        ["config"] = Processing.ToIpcConfig(),
        ["curve_points"] = Processing.ToCurvePoints(),
    };

    private void OnProcessingChanged(object? sender, PropertyChangedEventArgs e) => SyncNodes();

    private void SyncNodes()
    {
        var enabled = new Dictionary<string, bool>
        {
            ["stack"] = true, ["stretch"] = Processing.EnableStretch,
            ["basic"] = Processing.EnableBasic, ["usm"] = Processing.EnableUsm,
            ["bgr"] = Processing.EnableBackground || Processing.EnableCurves, ["highpass"] = Processing.EnableHighPass,
            ["emboss"] = Processing.EnableEmboss, ["channel"] = Processing.EnableChannelMixer,
            ["output"] = true,
        };
        foreach (var node in Nodes)
            node.IsEnabled = enabled[node.Key];
    }
}
