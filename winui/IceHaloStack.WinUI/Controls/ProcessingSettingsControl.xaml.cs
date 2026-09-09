using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class ProcessingSettingsControl : UserControl
{
    private ProcessingSettingsViewModel? _viewModel;

    public ProcessingSettingsControl()
    {
        InitializeComponent();
    }

    public ProcessingSettingsViewModel? ViewModel
    {
        get => _viewModel;
        set
        {
            _viewModel = value;
            Root.DataContext = value;
        }
    }
}
