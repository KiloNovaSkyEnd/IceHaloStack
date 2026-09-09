using System.ComponentModel;
using System.Collections.Generic;
using System.IO;
using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace IceHaloStack_WinUI;

/// <summary>Exports an automatically grouped stack-master TIFF sequence.</summary>
public sealed partial class TimelapsePage : Page
{
    private bool _initializingGroupingControls;

    public TimelapsePageViewModel ViewModel { get; } = new();

    public TimelapsePage()
    {
        InitializeComponent();
        ViewModel.Workspace.PropertyChanged += OnWorkspacePropertyChanged;
    }

    private void TimelapsePage_Loaded(object sender, RoutedEventArgs e)
    {
        _initializingGroupingControls = true;
        try
        {
            GroupingWindowSizeBox.Value = ViewModel.Workspace.WindowSize;
            GroupingStepBox.Value = ViewModel.Workspace.GroupingStep;
        }
        finally
        {
            _initializingGroupingControls = false;
        }
    }

    private async void TimelapsePage_Unloaded(object sender, RoutedEventArgs e)
    {
        ViewModel.Workspace.PropertyChanged -= OnWorkspacePropertyChanged;
        await ViewModel.DisposeAsync();
    }

    private void Back_Click(object sender, RoutedEventArgs e)
    {
        if (Frame?.CanGoBack == true)
            Frame.GoBack();
    }

    private async void PickInputs_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add(".tif");
        picker.FileTypeFilter.Add(".tiff");
        picker.FileTypeFilter.Add(".png");
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");
        InitializeWithWindow.Initialize(picker, App.WindowHandle);

        var files = await picker.PickMultipleFilesAsync();
        if (files.Count > 0)
            ViewModel.AddInputPaths(files.Select(file => file.Path));
    }

    private void RemoveSelectedInput_Click(object sender, RoutedEventArgs e)
        => ViewModel.Workspace.RemoveSelectedInput();

    private void MoveInputUp_Click(object sender, RoutedEventArgs e)
        => ViewModel.Workspace.MoveSelectedInput(-1);

    private void MoveInputDown_Click(object sender, RoutedEventArgs e)
        => ViewModel.Workspace.MoveSelectedInput(1);

    private void GroupingWindowSizeBox_ValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_initializingGroupingControls || !ViewModel.Workspace.CanEdit || !IsFinitePositive(args.NewValue))
            return;
        ViewModel.Workspace.WindowSize = ToPositiveWholeFrameCount(args.NewValue);
    }

    private void GroupingStepBox_ValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_initializingGroupingControls || !ViewModel.Workspace.CanEdit || !IsFinitePositive(args.NewValue))
            return;
        ViewModel.Workspace.GroupingStep = ToPositiveWholeFrameCount(args.NewValue);
    }

    private void GenerateGroups_Click(object sender, RoutedEventArgs e)
        => ViewModel.Workspace.GenerateGroups();

    private async void PickOutputDirectory_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.PicturesLibrary,
        };
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, App.WindowHandle);

        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null)
            ViewModel.Workspace.OutputDirectory = folder.Path;
    }

    private void ApplyOutputNaming_Click(object sender, RoutedEventArgs e)
        => ViewModel.Workspace.ApplyOutputNaming();

    private async void PickVideoOutput_Click(object sender, RoutedEventArgs e)
    {
        var video = ViewModel.Workspace.Video;
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.VideosLibrary,
            SuggestedFileName = "IceHaloStack-timelapse",
        };
        picker.FileTypeChoices.Add("MP4 H.264", new List<string> { ".mp4" });
        picker.FileTypeChoices.Add("MOV", new List<string> { ".mov" });
        picker.FileTypeChoices.Add("GIF", new List<string> { ".gif" });
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var file = await picker.PickSaveFileAsync();
        if (file is null)
            return;
        video.OutputPath = file.Path;
        video.Format = Path.GetExtension(file.Path).ToLowerInvariant() switch
        {
            ".mov" when video.Format == "MOV ProRes" => "MOV ProRes",
            ".mov" => "MOV H.264",
            ".gif" => "GIF",
            _ => "MP4 H.264",
        };
        video.Enabled = true;
    }

    private void OnWorkspacePropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName != nameof(StackPageViewModel.WindowSize)
            && args.PropertyName != nameof(StackPageViewModel.GroupingStep))
            return;

        _initializingGroupingControls = true;
        try
        {
            if (args.PropertyName == nameof(StackPageViewModel.WindowSize))
                GroupingWindowSizeBox.Value = ViewModel.Workspace.WindowSize;
            else
                GroupingStepBox.Value = ViewModel.Workspace.GroupingStep;
        }
        finally
        {
            _initializingGroupingControls = false;
        }
    }

    private static bool IsFinitePositive(double value)
        => !double.IsNaN(value) && !double.IsInfinity(value) && value >= 1.0;

    private static int ToPositiveWholeFrameCount(double value)
        => Math.Max(1, (int)Math.Round(value, MidpointRounding.AwayFromZero));
}
