using CommunityToolkit.Mvvm.ComponentModel;
using Microsoft.UI.Xaml.Media.Imaging;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class EwbFrameItem : ObservableObject
{
    public EwbFrameItem(int index, string path)
    {
        Index = index;
        Path = path;
    }

    public int Index { get; }
    public int FrameNumber => Index + 1;
    public string Path { get; }
    public string FileName => System.IO.Path.GetFileName(Path);
    [ObservableProperty] private bool _isKeyframe;
    [ObservableProperty] private double _measuredExposure;
    [ObservableProperty] private double _exposureCorrection;
    [ObservableProperty] private double _temperatureCorrection;
    [ObservableProperty] private double _tintCorrection;
    [ObservableProperty] private double _contrast;
    [ObservableProperty] private double _highlights;
    [ObservableProperty] private double _shadows;
    [ObservableProperty] private double _whites;
    [ObservableProperty] private double _blacks;
    [ObservableProperty] private BitmapImage? _thumbnail;
    [ObservableProperty] private bool _isThumbnailLoading;
}
