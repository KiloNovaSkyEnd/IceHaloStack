using Microsoft.UI.Xaml.Controls;
using IceHaloStack_WinUI.ViewModels;
using System.Collections.Generic;
using System.IO;
using Windows.Storage.Pickers;
using WinRT.Interop;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace IceHaloStack_WinUI;

/// <summary>
/// The main content page displayed inside the application window.
/// </summary>
public sealed partial class MainPage : Page
{
    public MainPageViewModel ViewModel { get; } = new();

    public MainPage()
    {
        InitializeComponent();
    }

    private async void MainPage_Unloaded(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        await ViewModel.DisposeAsync();
    }

    private async void PickInput_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add(".tif");
        picker.FileTypeFilter.Add(".tiff");
        picker.FileTypeFilter.Add(".png");
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var file = await picker.PickSingleFileAsync();
        if (file is not null)
            ViewModel.InputPath = file.Path;
    }

    private async void PickOutput_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.PicturesLibrary,
            SuggestedFileName = string.IsNullOrWhiteSpace(ViewModel.InputPath)
                ? "IceHaloStack-processed"
                : $"{Path.GetFileNameWithoutExtension(ViewModel.InputPath)}-processed",
        };
        picker.FileTypeChoices.Add("PNG 图像", new List<string> { ".png" });
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var file = await picker.PickSaveFileAsync();
        if (file is not null)
            ViewModel.OutputPath = file.Path;
    }

    private void OpenStackPage_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
        => Frame.Navigate(typeof(StackPage));

    private void OpenTimelapsePage_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
        => Frame.Navigate(typeof(TimelapsePage));
}
