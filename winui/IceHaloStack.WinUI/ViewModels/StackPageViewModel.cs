using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Text.RegularExpressions;
using CommunityToolkit.Mvvm.ComponentModel;
using IceHaloStack.WinUI.Client;

namespace IceHaloStack_WinUI.ViewModels;

/// <summary>
/// Bindable stack workspace.  It owns input order, explicit groups and output
/// naming, then sends the resulting JSON-compatible data to stack_files.
/// </summary>
public sealed partial class StackPageViewModel : ObservableObject, IAsyncDisposable
{
    private static readonly HashSet<string> SupportedMethods = new(StringComparer.Ordinal)
    {
        "mean",
        "maximum",
    };

    private static readonly Regex OutputTokenPattern = new(
        @"\{(?<name>[A-Za-z]+)(?::(?<format>[^{}]+))?\}",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private IpcClient? _client;
    private IpcTaskViewModel? _task;
    private bool _disposed;

    public StackPageViewModel()
    {
        Video.PropertyChanged += OnVideoPropertyChanged;
    }

    public ObservableCollection<StackInputItem> Inputs { get; } = [];

    public ObservableCollection<StackGroupItem> Groups { get; } = [];

    public ProcessingSettingsViewModel Processing { get; } = new();

    public VideoSettingsViewModel Video { get; } = new();

    public ObservableCollection<StackGroupingModeOption> GroupingModes { get; } =
    [
        new(StackGroupingMode.AllImages, "全部图像（一个 Master）"),
        new(StackGroupingMode.FixedWindow, "固定窗口（不重叠）"),
        new(StackGroupingMode.SlidingWindow, "滑动窗口"),
        new(StackGroupingMode.CenteredWindow, "中心窗口（按中点解释）"),
    ];

    [ObservableProperty]
    private StackInputItem? _selectedInput;

    [ObservableProperty]
    private string _stackMethod = "mean";

    [ObservableProperty]
    private StackGroupingMode _groupingMode = StackGroupingMode.AllImages;

    [ObservableProperty]
    private int _windowSize = 1;

    [ObservableProperty]
    private int _groupingStep = 1;

    [ObservableProperty]
    private string _outputDirectory = string.Empty;

    [ObservableProperty]
    private string _outputFileNamePattern = "stack_{group:000}_{start:000}-{end:000}";

    [ObservableProperty]
    private string _outputPathPreview = "选择输出目录后可批量生成 TIFF 文件名。";

    [ObservableProperty]
    private bool _isBusy;

    [ObservableProperty]
    private bool _canCancel;

    // Progress from stack_files is phase-local (decode / stack / export).
    [ObservableProperty]
    private double _progressPercent;

    [ObservableProperty]
    private string _phase = "准备就绪";

    [ObservableProperty]
    private string _status = "请选择多张图像；首批图像会自动建立一个堆栈分组。";

    [ObservableProperty]
    private string _error = string.Empty;

    [ObservableProperty]
    private bool _hasError;

    public int InputCount => Inputs.Count;

    public int GroupCount => Groups.Count;

    public int SelectedInputCount => Inputs.Count(item => item.IsSelected);

    public bool CanStart => !_disposed && !IsBusy && GetRequestValidationError() is null;

    /// <summary>Do not navigate away and dispose an active engine task.</summary>
    public bool CanNavigate => !_disposed && !IsBusy;

    public bool CanEditQueue => !_disposed && !IsBusy;

    public bool CanEdit => CanEditQueue;

    public bool CanRemoveSelectedInput => CanEdit && SelectedInput is not null && Inputs.Contains(SelectedInput);

    public bool CanMoveInputUp => CanEdit && SelectedInput is not null && Inputs.IndexOf(SelectedInput) > 0;

    public bool CanMoveInputDown => CanEdit && SelectedInput is not null
        && Inputs.IndexOf(SelectedInput) >= 0
        && Inputs.IndexOf(SelectedInput) < Inputs.Count - 1;

    partial void OnStackMethodChanged(string value)
    {
        if (!SupportedMethods.Contains(value))
        {
            StackMethod = "mean";
            return;
        }
        RefreshOutputPathPreview();
        RefreshCommandAvailability();
    }

    partial void OnGroupingModeChanged(StackGroupingMode value)
        => RefreshOutputPathPreview();

    partial void OnWindowSizeChanged(int value)
    {
        if (value < 1)
        {
            WindowSize = 1;
            return;
        }
        RefreshOutputPathPreview();
    }

    partial void OnGroupingStepChanged(int value)
    {
        if (value < 1)
        {
            GroupingStep = 1;
            return;
        }
        RefreshOutputPathPreview();
    }

    partial void OnOutputDirectoryChanged(string value) => RefreshOutputPathPreview();

    partial void OnOutputFileNamePatternChanged(string value) => RefreshOutputPathPreview();

    partial void OnSelectedInputChanged(StackInputItem? value)
    {
        OnPropertyChanged(nameof(CanRemoveSelectedInput));
        OnPropertyChanged(nameof(CanMoveInputUp));
        OnPropertyChanged(nameof(CanMoveInputDown));
    }

    partial void OnIsBusyChanged(bool value) => RefreshWorkspaceState();

    partial void OnCanCancelChanged(bool value) => RefreshCommandAvailability();

    private void ClearInputSelection()
    {
        foreach (var input in Inputs)
            input.IsSelected = false;
    }

    private void RenumberGroups()
    {
        for (var index = 0; index < Groups.Count; index++)
            Groups[index].SetGroupNumber(index + 1);
    }

    private bool EnsureEditable(string error)
    {
        if (CanEdit)
            return true;
        ShowError(error);
        return false;
    }

    private void OnInputPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName == nameof(StackInputItem.IsSelected))
            RefreshWorkspaceState();
    }

    private void OnGroupPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName is nameof(StackGroupItem.OutputPath)
            or nameof(StackGroupItem.FrameIndexes)
            or nameof(StackGroupItem.FrameSummary))
            RefreshWorkspaceState();
    }

    private void OnVideoPropertyChanged(object? sender, PropertyChangedEventArgs args)
        => RefreshCommandAvailability();

    private string? GetRequestValidationError()
    {
        var videoError = Video.Validate();
        if (videoError is not null)
            return videoError;
        if (Inputs.Count == 0)
            return "请先选择至少一张输入图像。";
        if (Groups.Count == 0)
            return "请至少建立一个堆栈分组。";
        if (!SupportedMethods.Contains(StackMethod))
            return "堆栈方式只能是 mean 或 maximum。";

        var inputPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var input in Inputs)
        {
            if (string.IsNullOrWhiteSpace(input.Path) || !File.Exists(input.Path))
                return $"输入图像不存在：{input.Path}";
            inputPaths.Add(System.IO.Path.GetFullPath(input.Path));
        }

        var outputPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var group in Groups)
        {
            if (group.FrameIndexes.Count == 0)
                return $"分组 {group.GroupNumber} 没有图像。";
            if (group.FrameIndexes.Any(index => index < 0 || index >= Inputs.Count))
                return $"分组 {group.GroupNumber} 含有无效图像索引。";
            if (string.IsNullOrWhiteSpace(group.OutputPath))
                return $"请为分组 {group.GroupNumber} 选择 TIFF 输出位置。";

            string output;
            try
            {
                output = System.IO.Path.GetFullPath(group.OutputPath);
            }
            catch (Exception exception)
            {
                return $"分组 {group.GroupNumber} 的输出路径无效：{exception.Message}";
            }
            var extension = System.IO.Path.GetExtension(output);
            if (!string.Equals(extension, ".tif", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(extension, ".tiff", StringComparison.OrdinalIgnoreCase))
                return $"分组 {group.GroupNumber} 的输出必须是 .tif 或 .tiff 文件。";
            if (!outputPaths.Add(output))
                return "不同分组不能写入同一个输出文件。";
            if (inputPaths.Contains(output))
                return "输出文件不能覆盖所选输入图像。";
        }
        return null;
    }

    private void ShowError(string message)
    {
        Error = message;
        HasError = !string.IsNullOrWhiteSpace(message);
    }

    private void ClearError()
    {
        Error = string.Empty;
        HasError = false;
    }

    private void RefreshWorkspaceState()
    {
        OnPropertyChanged(nameof(InputCount));
        OnPropertyChanged(nameof(GroupCount));
        OnPropertyChanged(nameof(SelectedInputCount));
        OnPropertyChanged(nameof(CanNavigate));
        OnPropertyChanged(nameof(CanEditQueue));
        OnPropertyChanged(nameof(CanEdit));
        OnPropertyChanged(nameof(CanRemoveSelectedInput));
        OnPropertyChanged(nameof(CanMoveInputUp));
        OnPropertyChanged(nameof(CanMoveInputDown));
        RefreshOutputPathPreview();
        RefreshCommandAvailability();
    }

    private void RefreshCommandAvailability()
    {
        StartStackCommand.NotifyCanExecuteChanged();
        CancelCommand.NotifyCanExecuteChanged();
    }
}
