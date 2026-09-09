using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class ProcessingParameter : ObservableObject
{
    public ProcessingParameter(string key, string label, double minimum, double maximum, double step, double defaultValue = 0)
    {
        Key = key;
        Label = label;
        Minimum = minimum;
        Maximum = maximum;
        Step = step;
        DefaultValue = defaultValue;
        Value = defaultValue;
    }

    public string Key { get; }
    public string Label { get; }
    public double Minimum { get; }
    public double Maximum { get; }
    public double Step { get; }
    public double DefaultValue { get; }

    [ObservableProperty]
    private double _value;

    public void Reset() => Value = DefaultValue;
}

public sealed class ProcessingSection
{
    public ProcessingSection(string title, params ProcessingParameter[] parameters)
    {
        Title = title;
        Parameters = new ObservableCollection<ProcessingParameter>(parameters);
    }

    public string Title { get; }
    public ObservableCollection<ProcessingParameter> Parameters { get; }
}
