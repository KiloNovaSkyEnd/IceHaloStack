using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
namespace IceHaloStack_WinUI.Controls;
public sealed partial class ClassicCurvesPanel : UserControl
{
    public ClassicCurvesPanel() => InitializeComponent();
    public ProcessingSettingsViewModel? ViewModel { get => (ProcessingSettingsViewModel?)GetValue(ViewModelProperty); set => SetValue(ViewModelProperty, value); }
    public static readonly DependencyProperty ViewModelProperty = DependencyProperty.Register(nameof(ViewModel), typeof(ProcessingSettingsViewModel), typeof(ClassicCurvesPanel), new PropertyMetadata(null));
    private void Channel_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.Tag is string channel && ViewModel is not null)
            ViewModel.CurveEditor.SelectChannel(channel);
    }
    private void ResetCurve_Click(object sender, RoutedEventArgs e) => ViewModel?.CurveEditor.ResetSelected();
    private void ResetAll_Click(object sender, RoutedEventArgs e) => ViewModel?.CurveEditor.ResetAll();
}
