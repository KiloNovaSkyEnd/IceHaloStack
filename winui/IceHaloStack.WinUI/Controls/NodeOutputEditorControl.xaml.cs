using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
namespace IceHaloStack_WinUI.Controls;
public sealed partial class NodeOutputEditorControl : UserControl
{
    public NodeOutputEditorControl() => InitializeComponent();
    public NodeFlowViewModel? ViewModel { get => (NodeFlowViewModel?)GetValue(ViewModelProperty); set => SetValue(ViewModelProperty, value); }
    public static readonly DependencyProperty ViewModelProperty = DependencyProperty.Register(nameof(ViewModel), typeof(NodeFlowViewModel), typeof(NodeOutputEditorControl), new PropertyMetadata(null));
}
