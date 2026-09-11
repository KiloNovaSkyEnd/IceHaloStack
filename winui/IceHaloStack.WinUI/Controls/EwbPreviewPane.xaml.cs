using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;
public sealed partial class EwbPreviewPane : UserControl
{
    private readonly DispatcherTimer _playbackTimer = new();

    public EwbPreviewPane()
    {
        InitializeComponent();
        _playbackTimer.Tick += (_, _) => (DataContext as EwbWorkspaceViewModel)?.AdvancePlayback();
        Unloaded += (_, _) => StopPlayback();
    }

    private void ViewMode_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (OriginalColumn is null || CorrectedColumn is null) return;
        var mode = (ViewModeBox.SelectedItem as ComboBoxItem)?.Content?.ToString();
        OriginalColumn.Width = new GridLength(mode == "修正后" ? 0 : 1, GridUnitType.Star);
        CorrectedColumn.Width = new GridLength(mode == "原始" ? 0 : 1, GridUnitType.Star);
    }

    private void Play_Click(object sender, RoutedEventArgs e)
    {
        if (_playbackTimer.IsEnabled) { StopPlayback(); return; }
        if (DataContext is not EwbWorkspaceViewModel viewModel || viewModel.Frames.Count == 0) return;
        _playbackTimer.Interval = TimeSpan.FromSeconds(1 / Math.Clamp(viewModel.PlaybackFps, 1, 60));
        viewModel.IsPlaying = true; PlayButton.Content = "暂停"; _playbackTimer.Start();
    }

    private void StopPlayback()
    {
        _playbackTimer.Stop();
        if (DataContext is EwbWorkspaceViewModel viewModel) viewModel.IsPlaying = false;
        if (PlayButton is not null) PlayButton.Content = "播放";
    }

    private async void Thumbnail_Loaded(object sender, RoutedEventArgs e)
    {
        if (sender is Image { DataContext: EwbFrameItem frame } && DataContext is EwbWorkspaceViewModel viewModel)
            await viewModel.EnsureThumbnailAsync(frame);
    }

    private void ThumbnailList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (DataContext is EwbWorkspaceViewModel viewModel && viewModel.PreviewCommand.CanExecute(null))
            viewModel.PreviewCommand.Execute(null);
    }

    private void PlaybackFps_Changed(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_playbackTimer.IsEnabled && double.IsFinite(args.NewValue))
            _playbackTimer.Interval = TimeSpan.FromSeconds(1 / Math.Clamp(args.NewValue, 1, 60));
    }
}
