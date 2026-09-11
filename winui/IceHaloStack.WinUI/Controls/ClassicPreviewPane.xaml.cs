using System.Globalization;
using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class ClassicPreviewPane : UserControl
{
    public ClassicPreviewPane() => InitializeComponent();

    public StackPageViewModel? ViewModel
    {
        get => (StackPageViewModel?)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty = DependencyProperty.Register(
        nameof(ViewModel), typeof(StackPageViewModel), typeof(ClassicPreviewPane), new PropertyMetadata(null));

    private void Fit_Click(object sender, RoutedEventArgs e) => PreviewScroller.ChangeView(0, 0, 1);

    public void FitToWindow() => PreviewScroller.ChangeView(0, 0, 1);

    private void Zoom_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.Tag is string text
            && float.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var zoom))
            PreviewScroller.ChangeView(null, null, zoom);
    }
}
