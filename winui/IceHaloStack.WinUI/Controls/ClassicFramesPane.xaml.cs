using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class ClassicFramesPane : UserControl
{
    public ClassicFramesPane() => InitializeComponent();

    public StackPageViewModel? ViewModel
    {
        get => (StackPageViewModel?)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty = DependencyProperty.Register(
        nameof(ViewModel), typeof(StackPageViewModel), typeof(ClassicFramesPane), new PropertyMetadata(null));

    private async void Thumbnail_Loaded(object sender, RoutedEventArgs e)
    {
        if (ViewModel is not null && (sender as FrameworkElement)?.DataContext is StackInputItem item)
            await ViewModel.EnsureThumbnailAsync(item);
    }

    private void MoveUp_Click(object sender, RoutedEventArgs e) => ViewModel?.MoveSelectedInput(-1);
    private void MoveDown_Click(object sender, RoutedEventArgs e) => ViewModel?.MoveSelectedInput(1);
}
