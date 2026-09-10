using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class ComputeSettingsViewModel : ObservableObject
{
    public IReadOnlyList<ComputeBackendOption> Options { get; } =
    [
        new("auto", "自动（GPU 优先）"),
        new("gpu", "GPU（失败回退 CPU）"),
        new("cpu", "仅 CPU"),
    ];

    [ObservableProperty] private string _selectedBackend = "auto";
    [ObservableProperty] private string _status = "等待后台自检；自动模式会优先使用通过自检的 GPU。";
    [ObservableProperty] private bool _isProbing;

    public void ApplyCapabilities(JsonElement payload)
    {
        var automatic = payload.TryGetProperty("automatic_selection", out var selected)
            ? selected.GetString() ?? "cpu"
            : "cpu";
        var gpuDescription = payload.TryGetProperty("gpu", out var gpu)
            && gpu.TryGetProperty("description", out var description)
            ? description.GetString()
            : null;
        Status = automatic == "gpu"
            ? $"GPU 自检通过：{gpuDescription}"
            : $"当前自动选择 CPU：{gpuDescription}";
    }

    public void ApplyTaskBackend(JsonElement payload)
    {
        var selected = payload.TryGetProperty("selected", out var selectedElement)
            ? selectedElement.GetString() ?? "cpu"
            : "cpu";
        var description = payload.TryGetProperty("description", out var descriptionElement)
            ? descriptionElement.GetString() ?? string.Empty
            : string.Empty;
        Status = $"本次实际使用：{selected.ToUpperInvariant()} · {description}";
    }
}
