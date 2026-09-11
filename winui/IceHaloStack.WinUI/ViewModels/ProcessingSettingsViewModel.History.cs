using System.ComponentModel;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class ProcessingSettingsViewModel
{
    private readonly Stack<ProcessingSnapshot> _undo = new();
    private readonly Stack<ProcessingSnapshot> _redo = new();
    private ProcessingSnapshot? _lastSnapshot;
    private bool _restoring;

    public bool CanUndo => _undo.Count > 0;
    public bool CanRedo => _redo.Count > 0;

    private void InitializeHistory()
    {
        _lastSnapshot = CaptureSnapshot();
        PropertyChanged += TrackHistoryChange;
        foreach (var parameter in Sections.SelectMany(section => section.Parameters))
            parameter.PropertyChanged += TrackHistoryChange;
        CurveEditor.Changed += (_, _) => TrackHistoryChange(CurveEditor, new PropertyChangedEventArgs("CurvePoints"));
    }

    public void Undo()
    {
        if (!CanUndo) return;
        _redo.Push(CaptureSnapshot());
        RestoreSnapshot(_undo.Pop());
    }

    public void Redo()
    {
        if (!CanRedo) return;
        _undo.Push(CaptureSnapshot());
        RestoreSnapshot(_redo.Pop());
    }

    private void TrackHistoryChange(object? sender, PropertyChangedEventArgs args)
    {
        if (_restoring || string.IsNullOrEmpty(args.PropertyName) || args.PropertyName is nameof(CanUndo) or nameof(CanRedo)) return;
        if (_lastSnapshot is not null)
        {
            _undo.Push(_lastSnapshot);
            while (_undo.Count > 100) _undo.RemoveBottom();
        }
        _redo.Clear();
        _lastSnapshot = CaptureSnapshot();
        OnPropertyChanged(nameof(CanUndo)); OnPropertyChanged(nameof(CanRedo));
    }

    private ProcessingSnapshot CaptureSnapshot() => new(
        Sections.SelectMany(section => section.Parameters).ToDictionary(item => item.Key, item => item.Value),
        CurveEditor.Channels.ToDictionary(channel => channel.Name,
            channel => channel.Points.Select(point => new[] { point.Input, point.Output }).ToArray()),
        EnableStretch, EnableBasic, EnableUsm, EnableBackground, EnableCurves, EnableHighPass, EnableEmboss,
        EnableChannelMixer, ChannelMonochrome, ChannelNoiseProtection, HighPassMode, EmbossStyle, EmbossBlendMode, ChannelOutput);

    private void RestoreSnapshot(ProcessingSnapshot snapshot)
    {
        _restoring = true;
        try
        {
            foreach (var parameter in Sections.SelectMany(section => section.Parameters))
                if (snapshot.Values.TryGetValue(parameter.Key, out var value)) parameter.Value = value;
            foreach (var channel in CurveEditor.Channels)
            {
                channel.Points.Clear();
                if (snapshot.Curves.TryGetValue(channel.Name, out var points))
                    foreach (var point in points) channel.Points.Add(new CurvePointViewModel(point[0], point[1]));
            }
            EnableStretch = snapshot.EnableStretch; EnableBasic = snapshot.EnableBasic; EnableUsm = snapshot.EnableUsm;
            EnableBackground = snapshot.EnableBackground; EnableCurves = snapshot.EnableCurves; EnableHighPass = snapshot.EnableHighPass;
            EnableEmboss = snapshot.EnableEmboss; EnableChannelMixer = snapshot.EnableChannelMixer;
            ChannelMonochrome = snapshot.ChannelMonochrome; ChannelNoiseProtection = snapshot.ChannelNoiseProtection;
            HighPassMode = snapshot.HighPassMode; EmbossStyle = snapshot.EmbossStyle;
            EmbossBlendMode = snapshot.EmbossBlendMode; ChannelOutput = snapshot.ChannelOutput;
            _lastSnapshot = CaptureSnapshot();
        }
        finally { _restoring = false; }
        OnPropertyChanged(string.Empty); OnPropertyChanged(nameof(CanUndo)); OnPropertyChanged(nameof(CanRedo));
    }

    private sealed record ProcessingSnapshot(
        Dictionary<string, double> Values, Dictionary<string, double[][]> Curves,
        bool EnableStretch, bool EnableBasic, bool EnableUsm,
        bool EnableBackground, bool EnableCurves, bool EnableHighPass, bool EnableEmboss,
        bool EnableChannelMixer, bool ChannelMonochrome, bool ChannelNoiseProtection,
        string HighPassMode, string EmbossStyle, string EmbossBlendMode, string ChannelOutput);
}

internal static class StackHistoryExtensions
{
    public static void RemoveBottom<T>(this Stack<T> stack)
    {
        var items = stack.ToArray().Take(Math.Max(0, stack.Count - 1)).Reverse().ToArray();
        stack.Clear();
        foreach (var item in items) stack.Push(item);
    }
}
