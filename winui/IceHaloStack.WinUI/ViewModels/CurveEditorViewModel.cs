using System.Collections.ObjectModel;
using System.Collections.Specialized;
using CommunityToolkit.Mvvm.ComponentModel;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class CurvePointViewModel : ObservableObject
{
    public CurvePointViewModel(double input, double output) => (_input, _output) = (input, output);
    [ObservableProperty] private double _input;
    [ObservableProperty] private double _output;
}

public sealed class CurveChannelViewModel
{
    public CurveChannelViewModel(string name) => Name = name;
    public string Name { get; }
    public ObservableCollection<CurvePointViewModel> Points { get; } =
    [
        new(0, 0),
        new(1, 1),
    ];
}

public sealed partial class CurveEditorViewModel : ObservableObject
{
    public CurveEditorViewModel()
    {
        Channels = new[] { "RGB", "红色", "绿色", "蓝色", "亮度" }
            .Select(name => new CurveChannelViewModel(name)).ToArray();
        _selectedChannel = Channels[0];
        foreach (var channel in Channels)
        {
            channel.Points.CollectionChanged += Points_CollectionChanged;
            foreach (var point in channel.Points) point.PropertyChanged += Point_PropertyChanged;
        }
    }

    public event EventHandler? Changed;

    public IReadOnlyList<CurveChannelViewModel> Channels { get; }

    [ObservableProperty]
    private CurveChannelViewModel _selectedChannel;

    public void SelectChannel(string name)
    {
        SelectedChannel = Channels.FirstOrDefault(channel => channel.Name == name) ?? Channels[0];
    }

    public void ResetSelected() => Reset(SelectedChannel);

    public void ResetAll()
    {
        foreach (var channel in Channels)
            Reset(channel);
    }

    public Dictionary<string, object?> ToIpcCurvePoints() => Channels.ToDictionary(
        channel => channel.Name,
        channel => (object?)channel.Points
            .OrderBy(point => point.Input)
            .Select(point => new[] { Clamp(point.Input), Clamp(point.Output) })
            .ToArray(),
        StringComparer.Ordinal);

    public void CopyFrom(CurveEditorViewModel source)
    {
        foreach (var target in Channels)
        {
            var origin = source.Channels.First(channel => channel.Name == target.Name);
            target.Points.Clear();
            foreach (var point in origin.Points.OrderBy(point => point.Input))
                target.Points.Add(new CurvePointViewModel(point.Input, point.Output));
        }
        SelectChannel(source.SelectedChannel.Name);
    }

    private static void Reset(CurveChannelViewModel channel)
    {
        channel.Points.Clear();
        channel.Points.Add(new CurvePointViewModel(0, 0));
        channel.Points.Add(new CurvePointViewModel(1, 1));
    }

    private static double Clamp(double value) => Math.Clamp(value, 0.0, 1.0);

    private void Points_CollectionChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        if (e.OldItems is not null)
            foreach (CurvePointViewModel point in e.OldItems) point.PropertyChanged -= Point_PropertyChanged;
        if (e.NewItems is not null)
            foreach (CurvePointViewModel point in e.NewItems) point.PropertyChanged += Point_PropertyChanged;
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private void Point_PropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
        => Changed?.Invoke(this, EventArgs.Empty);
}
