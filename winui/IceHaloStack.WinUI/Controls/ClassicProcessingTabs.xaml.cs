using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class ClassicProcessingTabs : UserControl
{
    private bool _loaded;

    public ClassicProcessingTabs()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    public StackPageViewModel? ViewModel
    {
        get => (StackPageViewModel?)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty = DependencyProperty.Register(
        nameof(ViewModel), typeof(StackPageViewModel), typeof(ClassicProcessingTabs), new PropertyMetadata(null));

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (_loaded || ViewModel is null)
            return;
        _loaded = true;
        WindowSizeBox.Value = ViewModel.WindowSize;
        StepBox.Value = ViewModel.GroupingStep;
    }

    private void WindowSize_ValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_loaded && ViewModel is not null && IsPositive(args.NewValue))
            ViewModel.WindowSize = Math.Max(1, (int)Math.Round(args.NewValue));
    }

    private void Step_ValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_loaded && ViewModel is not null && IsPositive(args.NewValue))
            ViewModel.GroupingStep = Math.Max(1, (int)Math.Round(args.NewValue));
    }

    private void GenerateGroups_Click(object sender, RoutedEventArgs e) => ViewModel?.GenerateGroups();
    private void ApplyNaming_Click(object sender, RoutedEventArgs e) => ViewModel?.ApplyOutputNaming();

    public void SelectSection(string section)
    {
        ProcessingTabView.SelectedIndex = section switch
        {
            "stretch" => 1, "basic" => 2, "detail" => 3,
            "channel" => 4, "curves" => 5, _ => 0,
        };
    }

    private static bool IsPositive(double value) => !double.IsNaN(value) && !double.IsInfinity(value) && value >= 1;
}
