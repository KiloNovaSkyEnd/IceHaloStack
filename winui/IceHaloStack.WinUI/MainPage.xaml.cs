using Microsoft.UI.Xaml.Controls;
using IceHaloStack_WinUI.ViewModels;
using IceHaloStack_WinUI.Services;
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
        PageLifetimeRegistry.Register(ViewModel);
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

    private async void OpenClassicWorkspace_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        try
        {
            ClassicWorkspaceLauncher.Launch();
        }
        catch (Exception exception)
        {
            var dialog = new ContentDialog
            {
                Title = "无法打开完整经典工作区",
                Content = exception.Message,
                CloseButtonText = "确定",
                XamlRoot = XamlRoot,
            };
            await dialog.ShowAsync();
        }
    }

    private void OpenTimelapsePage_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
        => Frame.Navigate(typeof(TimelapsePage));

    private void OpenNodeWorkflow_Click(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
        => Frame.Navigate(typeof(NodeWorkflowPage));
}
