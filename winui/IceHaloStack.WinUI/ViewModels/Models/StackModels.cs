using System.Globalization;
using CommunityToolkit.Mvvm.ComponentModel;
using Microsoft.UI.Xaml.Media.Imaging;

namespace IceHaloStack_WinUI.ViewModels;

/// <summary>Ways to derive explicit <c>stack_files.groups</c> from the input queue.</summary>
public enum StackGroupingMode
{
    AllImages,
    FixedWindow,
    SlidingWindow,
    CenteredWindow,
}

/// <summary>Display metadata for one selectable grouping mode.</summary>
public sealed record StackGroupingModeOption(StackGroupingMode Value, string DisplayName);

/// <summary>
/// One source file in the stack queue. Its stable <see cref="Id"/> lets groups
/// keep referring to the same file even when the queue is reordered.
/// </summary>
public sealed partial class StackInputItem : ObservableObject
{
    internal StackInputItem(Guid id, int sourceIndex, string path, bool isSelected = true)
    {
        Id = id;
        SourceIndex = sourceIndex;
        Path = path;
        FileName = System.IO.Path.GetFileName(path);
        IsSelected = isSelected;
    }

    public Guid Id { get; }

    /// <summary>One-based position displayed to people.</summary>
    public int Index => SourceIndex + 1;

    /// <summary>Current zero-based position used by the IPC request.</summary>
    [ObservableProperty]
    private int _sourceIndex;

    public string FileName { get; }

    public string Path { get; }

    [ObservableProperty]
    private bool _isSelected;

    [ObservableProperty]
    private BitmapImage? _thumbnail;

    [ObservableProperty]
    private bool _isThumbnailLoading;

    partial void OnSourceIndexChanged(int value) => OnPropertyChanged(nameof(Index));
}

/// <summary>
/// One pending master output. Membership is stored as stable input IDs;
/// <see cref="FrameIndexes"/> is recalculated whenever the queue changes.
/// </summary>
public sealed partial class StackGroupItem : ObservableObject
{
    private List<Guid> _inputIds;
    private int[] _frameIndexes = [];

    internal StackGroupItem(
        int groupNumber,
        IEnumerable<Guid> inputIds,
        IReadOnlyDictionary<Guid, int> indexLookup,
        StackGroupingMode? originMode = null)
    {
        GroupNumber = groupNumber;
        MaterialName = $"素材_{groupNumber:000}";
        OriginMode = originMode;
        _inputIds = inputIds.Distinct().ToList();
        Remap(indexLookup);
    }

    [ObservableProperty]
    private int _groupNumber;

    [ObservableProperty]
    private string _outputPath = string.Empty;

    /// <summary>User-owned label used to distinguish different material sets.</summary>
    [ObservableProperty]
    private string _materialName = string.Empty;

    [ObservableProperty]
    private string _frameSummary = string.Empty;

    /// <summary>The automatic preset that created this group, if any.</summary>
    public StackGroupingMode? OriginMode { get; }

    /// <summary>Current zero-based source indices required by stack_files.groups.</summary>
    public IReadOnlyList<int> FrameIndexes => _frameIndexes;

    public int FrameCount => _frameIndexes.Length;

    /// <summary>One-based first input position for display and output naming.</summary>
    public int StartFrame => _frameIndexes.Length == 0 ? 0 : _frameIndexes[0] + 1;

    /// <summary>One-based last input position for display and output naming.</summary>
    public int EndFrame => _frameIndexes.Length == 0 ? 0 : _frameIndexes[^1] + 1;

    /// <summary>One-based centre of the current span; may be a half-frame.</summary>
    public double CenterFrame => _frameIndexes.Length == 0
        ? 0.0
        : (StartFrame + EndFrame) / 2.0;

    internal void SetGroupNumber(int groupNumber) => GroupNumber = groupNumber;

    /// <summary>
    /// Drops deleted inputs and converts stable member IDs to current queue
    /// indices. Returns false if the group has no remaining member.
    /// </summary>
    internal bool Remap(IReadOnlyDictionary<Guid, int> indexLookup)
    {
        _inputIds = _inputIds
            .Where(indexLookup.ContainsKey)
            .Distinct()
            .ToList();
        var next = _inputIds
            .Select(id => indexLookup[id])
            .OrderBy(index => index)
            .ToArray();

        var indexesChanged = !_frameIndexes.SequenceEqual(next);
        _frameIndexes = next;
        FrameSummary = CreateFrameSummary(next, OriginMode);
        if (indexesChanged)
        {
            OnPropertyChanged(nameof(FrameIndexes));
            OnPropertyChanged(nameof(FrameCount));
            OnPropertyChanged(nameof(StartFrame));
            OnPropertyChanged(nameof(EndFrame));
            OnPropertyChanged(nameof(CenterFrame));
        }
        return _inputIds.Count > 0;
    }

    private static string CreateFrameSummary(
        IReadOnlyList<int> frameIndexes,
        StackGroupingMode? originMode)
    {
        if (frameIndexes.Count == 0)
            return "未选择图像";

        var displayed = frameIndexes.Select(index => (index + 1).ToString(CultureInfo.InvariantCulture)).ToArray();
        var list = displayed.Length <= 8
            ? string.Join("、", displayed)
            : string.Join("、", displayed.Take(8)) + "…";
        var summary = $"{displayed.Length} 张：帧 {list}";
        if (originMode == StackGroupingMode.CenteredWindow)
        {
            var center = (frameIndexes[0] + frameIndexes[^1] + 2) / 2.0;
            summary += $" · 中心时刻 {center.ToString("0.##", CultureInfo.InvariantCulture)}";
        }
        return summary;
    }
}
