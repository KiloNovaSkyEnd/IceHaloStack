using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using IceHaloStack_WinUI.Services;
using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace IceHaloStack_WinUI;

/// <summary>
/// Collects source images into explicit stack groups and submits them through
/// the local IPC-backed Python stack service.
/// </summary>
public sealed partial class StackPage : Page
{
    private bool _initializingGroupingControls;
    private bool _isSubscribed;

    public StackPageViewModel ViewModel { get; } = new();

    public StackPage()
    {
        InitializeComponent();
        PageLifetimeRegistry.Register(ViewModel);
    }

    private void StackPage_Loaded(object sender, RoutedEventArgs e)
    {
        if (!_isSubscribed)
        {
            ViewModel.PropertyChanged += OnViewModelPropertyChanged;
            _isSubscribed = true;
        }
        ViewModel.EnsureComputeProbeStarted();
        // NumberBox.Value is a double while the queue model intentionally
        // stores whole frame counts.  Seed the controls once in code-behind
        // rather than relying on a lossy two-way XAML conversion.
        _initializingGroupingControls = true;
        try
        {
            GroupingWindowSizeBox.Value = ViewModel.WindowSize;
            GroupingStepBox.Value = ViewModel.GroupingStep;
        }
        finally
        {
            _initializingGroupingControls = false;
        }
    }

    private async void InputThumbnail_Loaded(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is StackInputItem item)
            await ViewModel.EnsureThumbnailAsync(item);
    }

    private void StackPage_Unloaded(object sender, RoutedEventArgs e)
    {
        if (!_isSubscribed)
            return;
        ViewModel.PropertyChanged -= OnViewModelPropertyChanged;
        _isSubscribed = false;
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

    private void AddGroup_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.AddGroupFromSelected();
    }

    private void RemoveSelectedInput_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.RemoveSelectedInput();
    }

    private void MoveInputUp_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.MoveSelectedInput(-1);
    }

    private void MoveInputDown_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.MoveSelectedInput(1);
    }

    private void GroupingWindowSizeBox_ValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_initializingGroupingControls || !ViewModel.CanEdit || !IsFinitePositive(args.NewValue))
            return;

        ViewModel.WindowSize = ToPositiveWholeFrameCount(args.NewValue);
    }

    private void GroupingStepBox_ValueChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
    {
        if (_initializingGroupingControls || !ViewModel.CanEdit || !IsFinitePositive(args.NewValue))
            return;

        ViewModel.GroupingStep = ToPositiveWholeFrameCount(args.NewValue);
    }

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName != nameof(StackPageViewModel.WindowSize)
            && args.PropertyName != nameof(StackPageViewModel.GroupingStep))
            return;

        // The model clamps values after a queue change; keep the NumberBoxes
        // truthful without feeding their programmatic values back into it.
        _initializingGroupingControls = true;
        try
        {
            if (args.PropertyName == nameof(StackPageViewModel.WindowSize))
                GroupingWindowSizeBox.Value = ViewModel.WindowSize;
            else
                GroupingStepBox.Value = ViewModel.GroupingStep;
        }
        finally
        {
            _initializingGroupingControls = false;
        }
    }

    private void GenerateGroups_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.GenerateGroups();
    }

    private async void PickOutputDirectory_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.PicturesLibrary,
        };
        // FolderPicker requires at least one type filter even though it does
        // not filter folders.
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, App.WindowHandle);

        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null)
            ViewModel.OutputDirectory = folder.Path;
    }

    private void ApplyOutputNaming_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.ApplyOutputNaming();
    }

    private async void PickGroupOutput_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is not StackGroupItem group)
            return;

        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.PicturesLibrary,
            SuggestedFileName = string.IsNullOrWhiteSpace(group.OutputPath)
                ? $"IceHaloStack-stack-{group.GroupNumber}"
                : Path.GetFileNameWithoutExtension(group.OutputPath),
        };
        picker.FileTypeChoices.Add("TIFF 32-bit Float", new List<string> { ".tif" });
        InitializeWithWindow.Initialize(picker, App.WindowHandle);

        var file = await picker.PickSaveFileAsync();
        if (file is not null)
            ViewModel.UpdateGroupOutput(group, file.Path);
    }

    private void RemoveGroup_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is StackGroupItem group)
            ViewModel.RemoveGroup(group);
    }

    private static bool IsFinitePositive(double value)
    {
        return !double.IsNaN(value) && !double.IsInfinity(value) && value >= 1.0;
    }

    private static int ToPositiveWholeFrameCount(double value)
    {
        return Math.Max(1, (int)Math.Round(value, MidpointRounding.AwayFromZero));
    }
}
