using IceHaloStack_WinUI.Services;
using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace IceHaloStack_WinUI;

public sealed partial class NodeWorkflowPage : Page
{
    public NodeWorkflowViewModel ViewModel { get; } = new();

    public NodeWorkflowPage()
    {
        InitializeComponent();
        PageLifetimeRegistry.Register(ViewModel);
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        WindowSizeBox.Value = ViewModel.Queue.WindowSize;
        StepBox.Value = ViewModel.Queue.GroupingStep;
        ViewModel.Queue.EnsureComputeProbeStarted();
    }

    private void Back_Click(object sender, RoutedEventArgs e)
    {
        if (Frame?.CanGoBack == true) Frame.GoBack();
    }

    private async void PickInputs_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        foreach (var extension in new[] { ".tif", ".tiff", ".png", ".jpg", ".jpeg" })
            picker.FileTypeFilter.Add(extension);
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var files = await picker.PickMultipleFilesAsync();
        if (files.Count > 0) ViewModel.Queue.AddInputPaths(files.Select(file => file.Path));
    }

    private void GenerateGroups_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.Queue.GenerateGroupsForPreset(
            ViewModel.Queue.GroupingMode,
            Math.Max(1, (int)Math.Round(WindowSizeBox.Value)),
            Math.Max(1, (int)Math.Round(StepBox.Value)));
    }

    private async void PickOutput_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FolderPicker { SuggestedStartLocation = PickerLocationId.PicturesLibrary };
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null) ViewModel.OutputDirectory = folder.Path;
    }

    private async void InputThumbnail_Loaded(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is StackInputItem item)
            await ViewModel.Queue.EnsureThumbnailAsync(item);
    }
}
