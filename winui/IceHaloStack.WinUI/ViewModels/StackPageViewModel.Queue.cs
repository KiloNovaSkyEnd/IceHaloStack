namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class StackPageViewModel
{
    public void SelectAllInputs()
    {
        if (!EnsureEditable("堆栈任务运行时不能修改选择。")) return;
        foreach (var input in Inputs) input.IsSelected = true;
        SelectedInput = Inputs.FirstOrDefault();
        Status = $"已选中 {Inputs.Count} 帧。";
        RefreshWorkspaceState();
    }

    public void RemoveMarkedInputs()
    {
        if (!EnsureEditable("堆栈任务运行时不能修改图像队列。")) return;
        var selected = Inputs.Where(item => item.IsSelected).ToArray();
        if (selected.Length == 0 && SelectedInput is not null) selected = [SelectedInput];
        foreach (var input in selected)
        {
            Inputs.Remove(input);
            input.PropertyChanged -= OnInputPropertyChanged;
        }
        ReindexAndSynchronizeGroups();
        SelectedInput = Inputs.FirstOrDefault();
        Status = selected.Length == 0 ? "没有选中可移除的帧。" : $"已移除 {selected.Length} 帧。";
        RefreshWorkspaceState();
    }

    public void ClearProject()
    {
        if (!EnsureEditable("堆栈任务运行时不能清空工程。")) return;
        foreach (var input in Inputs) input.PropertyChanged -= OnInputPropertyChanged;
        foreach (var group in Groups) group.PropertyChanged -= OnGroupPropertyChanged;
        Inputs.Clear(); Groups.Clear(); SelectedInput = null; PreviewSource = null; HistogramBins.Clear();
        Status = "工程已清空。"; ClearError(); RefreshWorkspaceState();
    }

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
                path = Path.GetFullPath(candidate);
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
                ShowError("没有可加入的图像；所选路径不存在或无效。");
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

    public void AddGroupFromSelected()
    {
        if (!EnsureEditable("堆栈任务运行时不能修改分组。"))
            return;

        var ids = Inputs.Where(item => item.IsSelected).Select(item => item.Id).ToArray();
        if (ids.Length == 0)
        {
            ShowError("请先勾选至少一张图像，再建立自定义分组。");
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
            ShowError("请先在输入队列中选择一张图像。");
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
            ShowError("请先在输入队列中选择一张图像。");
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
            ShowError("请先选择至少一张输入图像。");
            Status = "没有输入图像，无法生成分组。";
            RefreshWorkspaceState();
            return;
        }

        GroupingMode = mode;
        WindowSize = Math.Clamp(windowSize, 1, Inputs.Count);
        GroupingStep = Math.Max(1, step);
        GenerateGroupsCore(showStatus: true);
    }

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
            group.OutputPath = string.IsNullOrWhiteSpace(path) ? string.Empty : Path.GetFullPath(path);
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
        if (!string.IsNullOrWhiteSpace(OutputDirectory) && Directory.Exists(OutputDirectory) && Groups.Count > 0)
            TryApplyOutputNaming(out _);

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
        var group = new StackGroupItem(Groups.Count + 1, inputIds, CreateInputIndexLookup(), originMode);
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
        => Inputs.Select((input, index) => (input.Id, index)).ToDictionary(item => item.Id, item => item.index);
}
