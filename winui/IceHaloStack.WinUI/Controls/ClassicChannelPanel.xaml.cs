using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
namespace IceHaloStack_WinUI.Controls;
public sealed partial class ClassicChannelPanel : UserControl
{
    public ClassicChannelPanel() => InitializeComponent();
    public ProcessingSettingsViewModel? ViewModel { get => (ProcessingSettingsViewModel?)GetValue(ViewModelProperty); set => SetValue(ViewModelProperty, value); }
    public static readonly DependencyProperty ViewModelProperty = DependencyProperty.Register(nameof(ViewModel), typeof(ProcessingSettingsViewModel), typeof(ClassicChannelPanel), new PropertyMetadata(null));
}
