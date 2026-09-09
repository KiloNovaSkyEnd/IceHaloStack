using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using IceHaloStack.WinUI.Client;
using IceHaloStack_WinUI.Services;

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

    public ObservableCollection<StackInputItem> Inputs { get; } = [];

    public ObservableCollection<StackGroupItem> Groups { get; } = [];

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

    /// <summary>Adds files in picker order.  The first batch becomes an all-images group.</summary>
    public void AddInputPaths(IEnumerable<string> paths)
    {
        ArgumentNullException.ThrowIfNull(paths);
        if (!EnsureEditable("堆栈任务运行时不能修改图像队列。"))
            return;

        var wasEmpty = Inputs.Count == 0;
        var knownPaths = new HashSet<string>(Inputs.Select(item => item.Path), StringComparer.OrdinalIgnoreCase);
        var added = 0;
        var invalid = 0;
        foreach (var candidate in paths)
        {
            if (string.IsNullOrWhiteSpace(candidate))
                continue;
            string path;
            try
            {
                path = System.IO.Path.GetFullPath(candidate);
            }
            catch (Exception)
            {
                invalid++;
                continue;
            }
            if (!File.Exists(path))
            {
                invalid++;
                continue;
            }
            if (!knownPaths.Add(path))
                continue;

            var input = new StackInputItem(Guid.NewGuid(), Inputs.Count, path, isSelected: true);
            input.PropertyChanged += OnInputPropertyChanged;
            Inputs.Add(input);
            added++;
        }

        if (added == 0)
        {
            if (invalid > 0)
            {
                ShowError("没有可加入的图像；所选路径不存在或无效。" );
                Status = "未向堆栈队列添加图像。";
            }
            RefreshWorkspaceState();
            return;
        }

        ReindexAndSynchronizeGroups();
        ClearError();
        if (wasEmpty)
        {
            WindowSize = Math.Min(15, Inputs.Count);
            GroupingMode = StackGroupingMode.AllImages;
            GenerateGroupsCore(showStatus: false);
            ClearInputSelection();
            Status = $"已加入 {added} 张图像，并建立默认的全部图像分组。请选择 TIFF 输出位置。";
        }
        else
        {
            Status = $"已加入 {added} 张图像。可勾选建立自定义分组，或使用自动分组预设。";
        }
        RefreshWorkspaceState();
    }

    /// <summary>Create one manual group from the currently checked inputs.</summary>
    public void AddGroupFromSelected()
    {
        if (!EnsureEditable("堆栈任务运行时不能修改分组。"))
            return;

        var ids = Inputs.Where(item => item.IsSelected).Select(item => item.Id).ToArray();
        if (ids.Length == 0)
        {
            ShowError("请先勾选至少一张图像，再建立自定义分组。" );
            Status = "等待选择用于堆栈的图像。";
            RefreshWorkspaceState();
            return;
        }

        AddGroup(ids, originMode: null);
        ClearInputSelection();
        ClearError();
        Status = $"已建立包含 {ids.Length} 张图像的自定义分组。请选择 TIFF 输出位置。";
        RefreshWorkspaceState();
    }

    public void RemoveSelectedInput()
    {
        if (SelectedInput is null)
        {
            ShowError("请先在输入队列中选择一张图像。" );
            return;
        }
        RemoveInput(SelectedInput);
    }

    public void RemoveInput(StackInputItem input)
    {
        ArgumentNullException.ThrowIfNull(input);
        if (!EnsureEditable("堆栈任务运行时不能修改图像队列。"))
            return;

        var index = Inputs.IndexOf(input);
        if (index < 0)
            return;

        Inputs.RemoveAt(index);
        input.PropertyChanged -= OnInputPropertyChanged;
        ReindexAndSynchronizeGroups();
        SelectedInput = Inputs.Count == 0 ? null : Inputs[Math.Min(index, Inputs.Count - 1)];
        ClearError();
        Status = Groups.Count == 0
            ? "已移除图像；所有关联分组已清空。请重新建立分组。"
            : "已移除图像；所有分组仍引用原来的其余图像。";
        RefreshWorkspaceState();
    }

    public void MoveSelectedInput(int delta)
    {
        if (SelectedInput is null)
        {
            ShowError("请先在输入队列中选择一张图像。" );
            return;
        }
        MoveInput(SelectedInput, delta);
    }

    public void MoveInputUp(StackInputItem input) => MoveInput(input, -1);

    public void MoveInputDown(StackInputItem input) => MoveInput(input, 1);

    private void MoveInput(StackInputItem input, int delta)
    {
        ArgumentNullException.ThrowIfNull(input);
        if (!EnsureEditable("堆栈任务运行时不能修改图像队列。"))
            return;
        var source = Inputs.IndexOf(input);
        var target = source + delta;
        if (source < 0 || target < 0 || target >= Inputs.Count)
            return;

        Inputs.Move(source, target);
        ReindexAndSynchronizeGroups();
        SelectedInput = input;
        ClearError();
        Status = "已调整输入顺序；分组继续引用相同的图像文件。";
        RefreshWorkspaceState();
    }

    /// <summary>Replace the group queue using the selected automatic preset.</summary>
    public void GenerateGroups() => GenerateGroupsForPreset();

    public void GenerateGroupsForPreset()
        => GenerateGroupsForPreset(GroupingMode, WindowSize, GroupingStep);

    public void GenerateGroupsForPreset(StackGroupingMode mode, int windowSize)
        => GenerateGroupsForPreset(mode, windowSize, GroupingStep);

    public void GenerateGroupsForPreset(StackGroupingMode mode, int windowSize, int step)
    {
        if (!EnsureEditable("堆栈任务运行时不能修改分组。"))
            return;
        if (Inputs.Count == 0)
        {
            ShowError("请先选择至少一张输入图像。" );
            Status = "没有输入图像，无法生成分组。";
            RefreshWorkspaceState();
            return;
        }

        GroupingMode = mode;
        WindowSize = Math.Clamp(windowSize, 1, Inputs.Count);
        GroupingStep = Math.Max(1, step);
        GenerateGroupsCore(showStatus: true);
    }

    /// <summary>Apply the selected directory and naming pattern to every group.</summary>
    public void ApplyOutputNaming()
    {
        if (!EnsureEditable("堆栈任务运行时不能修改输出队列。"))
            return;
        if (!TryApplyOutputNaming(out var error))
        {
            ShowError(error);
            Status = "请修正输出目录或文件命名规则。";
        }
        else
        {
            ClearError();
            Status = $"已为 {Groups.Count} 个分组生成 TIFF 输出路径。";
        }
        RefreshWorkspaceState();
    }

    public void UpdateGroupOutput(StackGroupItem group, string path)
    {
        ArgumentNullException.ThrowIfNull(group);
        ArgumentNullException.ThrowIfNull(path);
        if (!Groups.Contains(group) || !EnsureEditable("堆栈任务运行时不能修改输出队列。"))
            return;

        try
        {
            group.OutputPath = string.IsNullOrWhiteSpace(path)
                ? string.Empty
                : System.IO.Path.GetFullPath(path);
            ClearError();
            Status = string.IsNullOrWhiteSpace(group.OutputPath)
                ? $"分组 {group.GroupNumber} 尚未设置输出位置。"
                : $"已设置分组 {group.GroupNumber} 的 TIFF 输出位置。";
        }
        catch (Exception exception)
        {
            ShowError($"输出路径无效：{exception.Message}");
        }
        finally
        {
            RefreshWorkspaceState();
        }
    }

    public void RemoveGroup(StackGroupItem group)
    {
        ArgumentNullException.ThrowIfNull(group);
        if (!EnsureEditable("堆栈任务运行时不能修改分组。"))
            return;
        if (!Groups.Remove(group))
            return;

        group.PropertyChanged -= OnGroupPropertyChanged;
        RenumberGroups();
        ClearError();
        Status = Groups.Count == 0
            ? "分组队列已清空。请建立自定义分组或使用自动预设。"
            : "已移除分组。";
        RefreshWorkspaceState();
    }

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartStackAsync()
    {
        if (_disposed)
            return;
        var validationError = GetRequestValidationError();
        if (validationError is not null)
        {
            ShowError(validationError);
            Status = "请修正堆栈队列后再开始。";
            RefreshCommandAvailability();
            return;
        }

        ClearError();
        IsBusy = true;
        CanCancel = false;
        ProgressPercent = 0.0;
        Phase = "连接";
        Status = "正在连接 Python 图像堆栈引擎…";
        RefreshWorkspaceState();

        try
        {
            var client = await GetClientAsync().ConfigureAwait(false);
            DetachTask();
            var task = new IpcTaskViewModel(
                client,
                $"winui-stack-{Guid.NewGuid():N}",
                DispatchToUiAsync);
            task.PropertyChanged += OnTaskPropertyChanged;
            _task = task;

            await task.StartAsync(
                "stack_files",
                new Dictionary<string, object?>
                {
                    ["input_paths"] = Inputs.Select(item => item.Path).ToArray(),
                    ["groups"] = Groups.Select(group => group.FrameIndexes.ToArray()).ToArray(),
                    ["output_paths"] = Groups.Select(group => group.OutputPath).ToArray(),
                    ["method"] = StackMethod,
                    ["format"] = "TIFF 32-bit Float",
                }).ConfigureAwait(false);

            await DispatchToUiAsync(() => RefreshFromTask(task)).ConfigureAwait(false);
            _ = ObserveTerminalResultAsync(client, task);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() =>
            {
                IsBusy = false;
                CanCancel = false;
                Phase = "失败";
                Status = "无法提交堆栈任务。";
                ShowError(exception.Message);
                RefreshWorkspaceState();
            }).ConfigureAwait(false);
        }
    }

    [RelayCommand(CanExecute = nameof(CanCancel))]
    private async Task CancelAsync()
    {
        if (_task is null || !CanCancel)
            return;
        try
        {
            await _task.CancelAsync().ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                Phase = "取消";
                Status = "已请求取消，正在等待 Python 引擎安全结束…";
                RefreshFromTask(_task);
            }).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() => ShowError(exception.Message)).ConfigureAwait(false);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed)
            return;
        _disposed = true;
        DetachTask();
        foreach (var input in Inputs)
            input.PropertyChanged -= OnInputPropertyChanged;
        foreach (var group in Groups)
            group.PropertyChanged -= OnGroupPropertyChanged;
        if (_client is not null)
        {
            await _client.DisposeAsync().ConfigureAwait(false);
            _client = null;
        }
    }

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

    private void GenerateGroupsCore(bool showStatus)
    {
        var count = Inputs.Count;
        if (count == 0)
            return;
        var window = Math.Clamp(WindowSize, 1, count);
        var step = Math.Max(1, GroupingStep);
        WindowSize = window;
        GroupingStep = step;

        var generated = new List<(IReadOnlyList<Guid> InputIds, StackGroupingMode OriginMode)>();
        switch (GroupingMode)
        {
            case StackGroupingMode.AllImages:
                generated.Add((Inputs.Select(input => input.Id).ToArray(), StackGroupingMode.AllImages));
                break;

            case StackGroupingMode.FixedWindow:
                for (var start = 0; start + window <= count; start += window)
                    generated.Add((Inputs.Skip(start).Take(window).Select(input => input.Id).ToArray(), StackGroupingMode.FixedWindow));
                break;

            case StackGroupingMode.SlidingWindow:
            case StackGroupingMode.CenteredWindow:
                for (var start = 0; start + window <= count; start += step)
                    generated.Add((Inputs.Skip(start).Take(window).Select(input => input.Id).ToArray(), GroupingMode));
                break;
        }

        ReplaceGroups(generated);
        if (!string.IsNullOrWhiteSpace(OutputDirectory)
            && Directory.Exists(OutputDirectory)
            && Groups.Count > 0)
        {
            // A valid configured naming rule follows regenerated groups so no
            // stale group-to-output pairing survives a new preset.
            TryApplyOutputNaming(out _);
        }

        ClearError();
        if (showStatus)
        {
            var label = GroupingModes.First(option => option.Value == GroupingMode).DisplayName;
            Status = $"已按“{label}”生成 {Groups.Count} 个完整分组。";
        }
        RefreshWorkspaceState();
    }

    private void ReplaceGroups(IEnumerable<(IReadOnlyList<Guid> InputIds, StackGroupingMode OriginMode)> generated)
    {
        foreach (var group in Groups)
            group.PropertyChanged -= OnGroupPropertyChanged;
        Groups.Clear();
        var lookup = CreateInputIndexLookup();
        foreach (var item in generated)
        {
            var group = new StackGroupItem(Groups.Count + 1, item.InputIds, lookup, item.OriginMode);
            group.PropertyChanged += OnGroupPropertyChanged;
            Groups.Add(group);
        }
    }

    private void AddGroup(IEnumerable<Guid> inputIds, StackGroupingMode? originMode)
    {
        var group = new StackGroupItem(
            Groups.Count + 1,
            inputIds,
            CreateInputIndexLookup(),
            originMode);
        group.PropertyChanged += OnGroupPropertyChanged;
        Groups.Add(group);
    }

    private void ReindexAndSynchronizeGroups()
    {
        if (Inputs.Count == 0)
            WindowSize = 1;
        else if (WindowSize > Inputs.Count)
            WindowSize = Inputs.Count;

        var lookup = new Dictionary<Guid, int>();
        for (var index = 0; index < Inputs.Count; index++)
        {
            Inputs[index].SourceIndex = index;
            lookup[Inputs[index].Id] = index;
        }

        foreach (var group in Groups.ToArray())
        {
            if (group.Remap(lookup))
                continue;
            group.PropertyChanged -= OnGroupPropertyChanged;
            Groups.Remove(group);
        }
        RenumberGroups();
    }

    private Dictionary<Guid, int> CreateInputIndexLookup()
        => Inputs.Select((input, index) => (input.Id, index))
            .ToDictionary(item => item.Id, item => item.index);

    private bool TryApplyOutputNaming(out string error)
    {
        error = string.Empty;
        if (Groups.Count == 0)
        {
            error = "请先建立至少一个堆栈分组。";
            return false;
        }
        if (string.IsNullOrWhiteSpace(OutputDirectory))
        {
            error = "请先选择批量 TIFF 输出目录。";
            return false;
        }

        string directory;
        try
        {
            directory = System.IO.Path.GetFullPath(OutputDirectory);
        }
        catch (Exception exception)
        {
            error = $"输出目录无效：{exception.Message}";
            return false;
        }
        if (!Directory.Exists(directory))
        {
            error = "输出目录不存在。请通过“选择目录…”选择一个现有文件夹。";
            return false;
        }

        try
        {
            var used = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var group in Groups)
            {
                var stem = BuildOutputStem(group);
                var path = MakeUniqueTiffPath(directory, stem, used);
                group.OutputPath = path;
            }
            return true;
        }
        catch (Exception exception)
        {
            error = $"文件命名规则无效：{exception.Message}";
            return false;
        }
    }

    private string BuildOutputStem(StackGroupItem group)
    {
        var pattern = System.IO.Path.GetFileNameWithoutExtension(OutputFileNamePattern?.Trim() ?? string.Empty);
        if (string.IsNullOrWhiteSpace(pattern))
            throw new InvalidOperationException("请输入文件命名规则。" );

        var replaced = OutputTokenPattern.Replace(pattern, match =>
        {
            var name = match.Groups["name"].Value.ToLowerInvariant();
            var format = match.Groups["format"].Success ? match.Groups["format"].Value : null;
            return name switch
            {
                "group" => FormatNumber(group.GroupNumber, format),
                "start" => FormatNumber(group.StartFrame, format),
                "end" => FormatNumber(group.EndFrame, format),
                "center" => FormatNumber(group.CenterFrame, format),
                "count" => FormatNumber(group.FrameCount, format),
                "method" => StackMethod,
                "window" => FormatNumber(group.FrameCount, format),
                _ => throw new InvalidOperationException($"不支持的标记：{{{name}}}"),
            };
        });

        var invalid = System.IO.Path.GetInvalidFileNameChars();
        var sanitized = new string(replaced.Select(character => invalid.Contains(character) ? '_' : character).ToArray())
            .Trim(' ', '.');
        if (string.IsNullOrWhiteSpace(sanitized))
            throw new InvalidOperationException("命名规则没有生成有效的文件名。" );
        return sanitized;
    }

    private static string FormatNumber(int value, string? format)
        => string.IsNullOrWhiteSpace(format)
            ? value.ToString(CultureInfo.InvariantCulture)
            : value.ToString(format, CultureInfo.InvariantCulture);

    private static string FormatNumber(double value, string? format)
        => string.IsNullOrWhiteSpace(format)
            ? value.ToString("0.##", CultureInfo.InvariantCulture)
            : value.ToString(format, CultureInfo.InvariantCulture);

    private static string MakeUniqueTiffPath(string directory, string stem, ISet<string> used)
    {
        var suffix = 1;
        while (true)
        {
            var fileName = suffix == 1 ? $"{stem}.tif" : $"{stem}_{suffix:000}.tif";
            var path = System.IO.Path.Combine(directory, fileName);
            if (used.Add(path) && !File.Exists(path))
                return path;
            suffix++;
        }
    }

    private void RefreshOutputPathPreview()
    {
        try
        {
            if (Groups.Count == 0 || string.IsNullOrWhiteSpace(OutputDirectory))
            {
                OutputPathPreview = "选择输出目录后可批量生成 TIFF 文件名。";
                return;
            }
            var directory = System.IO.Path.GetFullPath(OutputDirectory);
            OutputPathPreview = System.IO.Path.Combine(directory, BuildOutputStem(Groups[0]) + ".tif");
        }
        catch (Exception)
        {
            OutputPathPreview = "命名规则或输出目录尚未有效。";
        }
    }

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

    private async Task<IpcClient> GetClientAsync()
    {
        if (_client is { IsAlive: true })
            return _client;
        if (_client is not null)
        {
            await _client.DisposeAsync().ConfigureAwait(false);
            _client = null;
        }

        var client = EngineClientFactory.CreateDevelopmentClient();
        try
        {
            await client.StartAsync().ConfigureAwait(false);
            await client.PingAsync(TimeSpan.FromSeconds(12)).ConfigureAwait(false);
            _client = client;
            return client;
        }
        catch
        {
            await client.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }

    private async Task ObserveTerminalResultAsync(IpcClient client, IpcTaskViewModel task)
    {
        try
        {
            var result = await client.WaitForTaskAsync(task.TaskId).ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                if (!ReferenceEquals(task, _task))
                    return;
                RefreshFromTask(task);
                if (result.Ok)
                {
                    ProgressPercent = 100.0;
                    Phase = "完成";
                    Status = DescribeSuccess(result);
                }
                else if (result.Cancelled)
                {
                    ClearError();
                    Phase = "已取消";
                    Status = "堆栈任务已取消。";
                }
                else
                {
                    Phase = "失败";
                    Status = "Python 引擎报告堆栈任务失败。";
                    ShowError(result.Error ?? "未返回错误详情。" );
                }
                RefreshWorkspaceState();
            }).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() =>
            {
                if (!ReferenceEquals(task, _task))
                    return;
                IsBusy = false;
                CanCancel = false;
                Phase = "失败";
                Status = "与 Python 图像堆栈引擎的连接已中断。";
                ShowError(exception.Message);
                RefreshWorkspaceState();
            }).ConfigureAwait(false);
        }
    }

    private void OnTaskPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (sender is IpcTaskViewModel task && ReferenceEquals(task, _task))
            RefreshFromTask(task);
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

    private void RefreshFromTask(IpcTaskViewModel task)
    {
        ProgressPercent = task.ProgressPercent;
        IsBusy = task.IsBusy;
        CanCancel = task.CanCancel;
        if (!string.IsNullOrWhiteSpace(task.Phase))
            Phase = task.Phase;
        if (!string.IsNullOrWhiteSpace(task.Message))
            Status = task.Message;
        if (task.State != IpcTaskState.Cancelled && !string.IsNullOrWhiteSpace(task.Error))
            ShowError(task.Error);
        RefreshCommandAvailability();
    }

    private static string DescribeSuccess(IpcTaskResult result)
    {
        if (result.Result is { } payload
            && payload.TryGetProperty("output_paths", out var paths)
            && paths.ValueKind == JsonValueKind.Array)
        {
            var saved = paths.EnumerateArray()
                .Where(path => path.ValueKind == JsonValueKind.String)
                .Select(path => path.GetString())
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .ToArray();
            return saved.Length switch
            {
                0 => "堆栈完成。",
                1 => $"堆栈完成：{saved[0]}",
                _ => $"已完成 {saved.Length} 个堆栈输出。",
            };
        }
        return "堆栈完成。";
    }

    private static Task DispatchToUiAsync(Action action)
    {
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!App.DispatcherQueue.TryEnqueue(() =>
        {
            try
            {
                action();
                completion.SetResult();
            }
            catch (Exception exception)
            {
                completion.SetException(exception);
            }
        }))
        {
            completion.SetException(new InvalidOperationException("WinUI 调度器已关闭。"));
        }
        return completion.Task;
    }

    private string? GetRequestValidationError()
    {
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

    private void DetachTask()
    {
        if (_task is null)
            return;
        _task.PropertyChanged -= OnTaskPropertyChanged;
        _task.Dispose();
        _task = null;
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
