using System.Collections.ObjectModel;
using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using IceHaloStack.WinUI.Client;
using IceHaloStack_WinUI.Services;
using Microsoft.UI.Xaml.Media.Imaging;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class EwbWorkspaceViewModel : ObservableObject, IDisposable
{
    private readonly IEngineClientProvider _engineClientProvider;
    private IpcTaskViewModel? _task;
    private JsonElement? _table;
    private readonly List<string> _previewFiles = [];
    private int _previewGeneration;
    private bool _disposed;

    public EwbWorkspaceViewModel(IEngineClientProvider engineClientProvider)
        => _engineClientProvider = engineClientProvider;

    public ObservableCollection<EwbFrameItem> Frames { get; } = [];
    [ObservableProperty] private EwbFrameItem? _selectedFrame;
    [ObservableProperty] private bool _deflickerEnabled;
    [ObservableProperty] private bool _exposureSmoothingEnabled;
    [ObservableProperty] private bool _whiteBalanceSmoothingEnabled;
    [ObservableProperty] private double _deflickerStrength = 100;
    [ObservableProperty] private int _deflickerRadius = 3;
    [ObservableProperty] private double _exposureStrength = 100;
    [ObservableProperty] private int _exposureRadius = 20;
    [ObservableProperty] private double _exposureMaxEv = 0.7;
    [ObservableProperty] private double _whiteBalanceStrength = 100;
    [ObservableProperty] private int _whiteBalanceRadius = 30;
    [ObservableProperty] private double _whiteBalanceMaxPercent = 15;
    [ObservableProperty] private double _anchorInfluence = 100;
    [ObservableProperty] private double _smoothingAmount = 50;
    [ObservableProperty] private bool _multiPassEnabled;
    [ObservableProperty] private int _smoothingPasses = 2;
    [ObservableProperty] private string _analysisRegion = "自动有效区域";
    [ObservableProperty] private double _roiX = 10;
    [ObservableProperty] private double _roiY = 10;
    [ObservableProperty] private double _roiWidth = 80;
    [ObservableProperty] private double _roiHeight = 80;
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private double _progressPercent;
    [ObservableProperty] private string _status = "添加帧后分析曝光与白平衡。";
    [ObservableProperty] private string _error = string.Empty;
    [ObservableProperty] private BitmapImage? _previewSource;
    [ObservableProperty] private BitmapImage? _originalPreviewSource;
    [ObservableProperty] private int _currentFrameNumber = 1;
    [ObservableProperty] private double _playbackFps = 12;
    [ObservableProperty] private bool _isPlaying;

    public IReadOnlyList<double> ExposureMetricSeries { get; private set; } = [];
    public IReadOnlyList<double> ExposureSmoothSeries { get; private set; } = [];
    public IReadOnlyList<double> ExposureTargetSeries { get; private set; } = [];
    public IReadOnlyList<double> TemperatureMetricSeries { get; private set; } = [];
    public IReadOnlyList<double> TemperatureSmoothSeries { get; private set; } = [];
    public IReadOnlyList<double> TemperatureTargetSeries { get; private set; } = [];
    public IReadOnlyList<double> TintMetricSeries { get; private set; } = [];
    public IReadOnlyList<double> TintSmoothSeries { get; private set; } = [];
    public IReadOnlyList<double> TintTargetSeries { get; private set; } = [];

    public bool HasError => !string.IsNullOrWhiteSpace(Error);
    public bool CanRun => !_disposed && !IsBusy && Frames.Count > 0;
    public bool HasTable => _table.HasValue;
    public IReadOnlyList<string> AnalysisRegions { get; } = ["自动有效区域", "全画面", "自定义 ROI"];

    public void SetInputPaths(IEnumerable<string> paths)
    {
        var normalized = paths.Where(File.Exists).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (Frames.Select(frame => frame.Path).SequenceEqual(normalized, StringComparer.OrdinalIgnoreCase)) return;
        Frames.Clear();
        for (var index = 0; index < normalized.Length; index++) Frames.Add(new EwbFrameItem(index, normalized[index]));
        SelectedFrame = Frames.FirstOrDefault();
        _table = null;
        PreviewSource = null;
        OriginalPreviewSource = null;
        CurrentFrameNumber = Frames.Count > 0 ? 1 : 0;
        Status = Frames.Count == 0 ? "请先在节点工作流添加图像。" : $"已读取 {Frames.Count} 帧，等待分析。";
        RefreshCommands();
    }

    public Dictionary<string, object?> ToIpcConfig() => new()
    {
        ["deflicker_enabled"] = DeflickerEnabled,
        ["exposure_enabled"] = ExposureSmoothingEnabled,
        ["wb_enabled"] = WhiteBalanceSmoothingEnabled,
        ["deflicker_strength"] = DeflickerStrength,
        ["deflicker_radius"] = DeflickerRadius,
        ["exposure_strength"] = ExposureStrength,
        ["exposure_radius"] = ExposureRadius,
        ["exposure_max_ev"] = ExposureMaxEv,
        ["wb_strength"] = WhiteBalanceStrength,
        ["wb_radius"] = WhiteBalanceRadius,
        ["wb_max_percent"] = WhiteBalanceMaxPercent,
        ["anchor_influence"] = AnchorInfluence,
        ["smoothing_amount"] = SmoothingAmount,
        ["multi_pass_enabled"] = MultiPassEnabled,
        ["smoothing_passes"] = SmoothingPasses,
        ["analysis_region"] = AnalysisRegion,
        ["roi_x"] = RoiX, ["roi_y"] = RoiY, ["roi_w"] = RoiWidth, ["roi_h"] = RoiHeight,
        ["anchors"] = Frames.Where(frame => frame.IsKeyframe).Select(frame => new Dictionary<string, object?>
        {
            ["frame"] = frame.FrameNumber, ["exposure"] = frame.ExposureCorrection,
            ["temperature"] = frame.TemperatureCorrection, ["tint"] = frame.TintCorrection,
            ["contrast"] = frame.Contrast, ["highlights"] = frame.Highlights,
            ["shadows"] = frame.Shadows, ["whites"] = frame.Whites, ["blacks"] = frame.Blacks,
        }).ToArray(),
    };

    [RelayCommand(CanExecute = nameof(CanRun))]
    private Task AnalyzeAsync() => RunTableTaskAsync("ewb_analyze_frames", new()
    {
        ["input_paths"] = Frames.Select(frame => frame.Path).ToArray(), ["config"] = ToIpcConfig(),
    }, "正在分析所有帧…");

    [RelayCommand(CanExecute = nameof(CanRebuild))]
    private Task RebuildAsync()
    {
        var table = _table!.Value;
        return RunTableTaskAsync("ewb_build_corrections", new()
        {
            ["exposure_metric"] = table.GetProperty("exposure_metric"),
            ["rlog_metric"] = table.GetProperty("rlog_metric"),
            ["blog_metric"] = table.GetProperty("blog_metric"),
            ["config"] = ToIpcConfig(),
        }, "正在根据关键帧重建过渡…");
    }

    private bool CanRebuild => CanRun && HasTable;

    [RelayCommand(CanExecute = nameof(CanEditKeyframe))]
    private void ToggleKeyframe()
    {
        if (SelectedFrame is null) return;
        SelectedFrame.IsKeyframe = !SelectedFrame.IsKeyframe;
        Status = SelectedFrame.IsKeyframe ? $"第 {SelectedFrame.FrameNumber} 帧已设为关键帧。" : $"已移除第 {SelectedFrame.FrameNumber} 帧关键帧。";
        RebuildCommand.NotifyCanExecuteChanged();
    }

    private bool CanEditKeyframe => !_disposed && !IsBusy && SelectedFrame is not null;

    [RelayCommand(CanExecute = nameof(CanEditKeyframe))]
    private void PreviousFrame()
    {
        if (SelectedFrame is null) return;
        SelectedFrame = Frames[Math.Max(0, SelectedFrame.Index - 1)];
        if (PreviewCommand.CanExecute(null)) PreviewCommand.Execute(null);
    }

    [RelayCommand(CanExecute = nameof(CanEditKeyframe))]
    private void NextFrame()
    {
        if (SelectedFrame is null) return;
        SelectedFrame = Frames[Math.Min(Frames.Count - 1, SelectedFrame.Index + 1)];
        if (PreviewCommand.CanExecute(null)) PreviewCommand.Execute(null);
    }

    [RelayCommand(CanExecute = nameof(CanEditKeyframe))]
    private void CreateKeyframeGuide()
    {
        foreach (var frame in Frames) frame.IsKeyframe = false;
        foreach (var index in new[] { 0, Frames.Count / 2, Frames.Count - 1 }.Distinct()) Frames[index].IsKeyframe = true;
        Status = "已在首帧、中间帧和尾帧建立关键帧向导。";
    }

    [RelayCommand(CanExecute = nameof(CanEditKeyframe))]
    private void SynchronizeKeyframes()
    {
        if (SelectedFrame is null) return;
        SelectedFrame.IsKeyframe = true;
        foreach (var frame in Frames.Where(frame => frame.IsKeyframe))
        {
            frame.ExposureCorrection = SelectedFrame.ExposureCorrection;
            frame.TemperatureCorrection = SelectedFrame.TemperatureCorrection;
            frame.TintCorrection = SelectedFrame.TintCorrection;
            frame.Contrast = SelectedFrame.Contrast; frame.Highlights = SelectedFrame.Highlights;
            frame.Shadows = SelectedFrame.Shadows; frame.Whites = SelectedFrame.Whites; frame.Blacks = SelectedFrame.Blacks;
        }
        Status = "已将当前调整同步到全部关键帧。";
    }

    [RelayCommand(CanExecute = nameof(CanEditKeyframe))]
    private void ResetKeyframes()
    {
        foreach (var frame in Frames)
        {
            frame.IsKeyframe = false; frame.ExposureCorrection = frame.TemperatureCorrection = frame.TintCorrection = 0;
            frame.Contrast = frame.Highlights = frame.Shadows = frame.Whites = frame.Blacks = 0;
        }
        Status = "已重置所有关键帧调整。";
    }

    [RelayCommand(CanExecute = nameof(CanRebuild))]
    private Task ResmoothAsync() => RunTableTaskAsync("ewb_resmooth_corrections", new()
    {
        ["table"] = _table!.Value, ["config"] = ToIpcConfig(),
    }, "正在再次平滑当前过渡…");

    [RelayCommand(CanExecute = nameof(CanCancel))]
    private async Task CancelAsync()
    {
        if (_task is not null) await _task.CancelAsync().ConfigureAwait(false);
    }

    private bool CanCancel => !_disposed && IsBusy && _task is not null;

    [RelayCommand(CanExecute = nameof(CanPreview))]
    private async Task PreviewAsync()
    {
        if (SelectedFrame is null || !_table.HasValue) return;
        var frame = SelectedFrame;
        var generation = Interlocked.Increment(ref _previewGeneration);
        var target = Path.Combine(Path.GetTempPath(), $"IceHaloStack-ewb-{Guid.NewGuid():N}.png");
        var originalTarget = Path.Combine(Path.GetTempPath(), $"IceHaloStack-ewb-original-{Guid.NewGuid():N}.png");
        _previewFiles.Add(target); _previewFiles.Add(originalTarget);
        var result = await RunTaskAsync("ewb_preview_frame", new()
        {
            ["input_path"] = frame.Path, ["output_path"] = target,
            ["original_output_path"] = originalTarget,
            ["frame_index"] = frame.Index, ["table"] = _table.Value, ["max_side"] = IsPlaying ? 640 : 1200,
        }, "正在生成修正预览…").ConfigureAwait(false);
        if (result is null) return;
        if (generation != _previewGeneration)
        {
            await DispatchToUiAsync(() =>
            {
                if (PreviewCommand.CanExecute(null)) PreviewCommand.Execute(null);
            }).ConfigureAwait(false);
            return;
        }
        await DispatchToUiAsync(() =>
        {
            if (generation != _previewGeneration) return;
            PreviewSource = new BitmapImage(new Uri(target));
            OriginalPreviewSource = new BitmapImage(new Uri(originalTarget));
        }).ConfigureAwait(false);
    }

    private bool CanPreview => CanRebuild && SelectedFrame is not null;

    partial void OnSelectedFrameChanged(EwbFrameItem? value)
    {
        Interlocked.Increment(ref _previewGeneration);
        if (value is not null && CurrentFrameNumber != value.FrameNumber) CurrentFrameNumber = value.FrameNumber;
        ToggleKeyframeCommand.NotifyCanExecuteChanged();
        PreviewCommand.NotifyCanExecuteChanged();
    }
    partial void OnCurrentFrameNumberChanged(int value)
    {
        if (value < 1 || value > Frames.Count) return;
        var frame = Frames[value - 1];
        if (!ReferenceEquals(SelectedFrame, frame)) SelectedFrame = frame;
    }
    partial void OnIsBusyChanged(bool value) => RefreshCommands();
    partial void OnErrorChanged(string value) => OnPropertyChanged(nameof(HasError));

    private void RefreshCommands()
    {
        OnPropertyChanged(nameof(CanRun)); OnPropertyChanged(nameof(HasTable));
        AnalyzeCommand.NotifyCanExecuteChanged(); RebuildCommand.NotifyCanExecuteChanged();
        ResmoothCommand.NotifyCanExecuteChanged(); CancelCommand.NotifyCanExecuteChanged();
        ToggleKeyframeCommand.NotifyCanExecuteChanged(); PreviewCommand.NotifyCanExecuteChanged();
        PreviousFrameCommand.NotifyCanExecuteChanged(); NextFrameCommand.NotifyCanExecuteChanged();
        CreateKeyframeGuideCommand.NotifyCanExecuteChanged(); SynchronizeKeyframesCommand.NotifyCanExecuteChanged(); ResetKeyframesCommand.NotifyCanExecuteChanged();
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true; _task?.Dispose();
        foreach (var file in _previewFiles) { try { File.Delete(file); } catch { } }
        RefreshCommands();
    }

    public void AdvancePlayback()
    {
        if (Frames.Count == 0 || IsBusy) return;
        var next = SelectedFrame is null ? 0 : (SelectedFrame.Index + 1) % Frames.Count;
        SelectedFrame = Frames[next];
        if (PreviewCommand.CanExecute(null)) PreviewCommand.Execute(null);
    }

    public async Task EnsureThumbnailAsync(EwbFrameItem frame)
    {
        if (frame.Thumbnail is not null || frame.IsThumbnailLoading) return;
        frame.IsThumbnailLoading = true;
        try { frame.Thumbnail = await ThumbnailDecodeService.LoadAsync(frame.Path, 96); }
        finally { frame.IsThumbnailLoading = false; }
    }
}
