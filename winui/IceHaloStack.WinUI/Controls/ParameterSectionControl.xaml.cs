using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class ParameterSectionControl : UserControl
{
    public ParameterSectionControl() => InitializeComponent();

    public ProcessingSection? Section
    {
        get => (ProcessingSection?)GetValue(SectionProperty);
        set => SetValue(SectionProperty, value);
    }

    public static readonly DependencyProperty SectionProperty = DependencyProperty.Register(
        nameof(Section), typeof(ProcessingSection), typeof(ParameterSectionControl), new PropertyMetadata(null));

    private void Parameter_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is ProcessingParameter parameter)
            parameter.Reset();
    }
}
