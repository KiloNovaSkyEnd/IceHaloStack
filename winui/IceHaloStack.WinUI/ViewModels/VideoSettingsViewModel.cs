using CommunityToolkit.Mvvm.ComponentModel;

namespace IceHaloStack_WinUI.ViewModels;

/// <summary>Bindable options for the shared FFmpeg video-export service.</summary>
public sealed partial class VideoSettingsViewModel : ObservableObject
{
    public IReadOnlyList<string> Formats { get; } = ["MP4 H.264", "MOV H.264", "MOV ProRes", "GIF"];
    public IReadOnlyList<string> Resolutions { get; } = ["原始分辨率", "16:9 4K", "4:3 4K", "自定义"];
    public IReadOnlyList<string> FitModes { get; } = ["Fill 裁切", "Fit 黑边", "Stretch 拉伸"];

    [ObservableProperty] private bool _enabled;
    [ObservableProperty] private string _outputPath = string.Empty;
    [ObservableProperty] private string _format = "MP4 H.264";
    [ObservableProperty] private double _framesPerSecond = 24;
    [ObservableProperty] private string _resolution = "原始分辨率";
    [ObservableProperty] private int _customWidth = 1920;
    [ObservableProperty] private int _customHeight = 1080;
    [ObservableProperty] private string _fitMode = "Fill 裁切";

    public Dictionary<string, object?> ToIpcRequest() => new()
    {
        ["output_path"] = OutputPath,
        ["format"] = Format,
        ["fps"] = FramesPerSecond,
        ["resolution"] = Resolution,
        ["custom_width"] = CustomWidth,
        ["custom_height"] = CustomHeight,
        ["fit_mode"] = FitMode,
    };

    public string? Validate()
    {
        if (!Enabled)
            return null;
        if (string.IsNullOrWhiteSpace(OutputPath))
            return "启用视频导出后必须选择视频输出位置。";
        if (FramesPerSecond <= 0 || double.IsNaN(FramesPerSecond) || double.IsInfinity(FramesPerSecond))
            return "视频帧率必须大于 0。";
        var expected = Format switch
        {
            "MP4 H.264" => ".mp4",
            "MOV H.264" or "MOV ProRes" => ".mov",
            "GIF" => ".gif",
            _ => string.Empty,
        };
        if (string.IsNullOrEmpty(expected))
            return "视频格式无效。";
        if (!string.Equals(Path.GetExtension(OutputPath), expected, StringComparison.OrdinalIgnoreCase))
            return $"{Format} 输出必须使用 {expected} 扩展名。";
        if (Resolution == "自定义" && (CustomWidth < 2 || CustomHeight < 2))
            return "自定义视频尺寸必须至少为 2×2。";
        return null;
    }
}
