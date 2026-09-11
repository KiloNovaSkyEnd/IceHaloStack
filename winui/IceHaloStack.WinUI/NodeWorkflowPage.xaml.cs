using IceHaloStack_WinUI.Controls;
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
        NodeGraph.NodeInvoked += OnNodeInvoked;
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

    private void OpenEwb_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.PrepareEwbWorkspace();
        Frame?.Navigate(typeof(EwbKeyframePage), ViewModel.Ewb);
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

    private void GenerateReference_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.ReferenceGroupIndex = Math.Max(0, (int)Math.Round(ReferenceIndexBox.Value) - 1);
        if (ViewModel.GeneratePreviewCommand.CanExecute(null))
            ViewModel.GeneratePreviewCommand.Execute(null);
    }

    private async void OnNodeInvoked(object? sender, NodeWorkflowNode node)
    {
        if (ViewModel.SelectedFlow is null) return;
        var editor = NodeParameterEditorFactory.Create(node, ViewModel.SelectedFlow, ViewModel.Queue);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"{node.Title.Replace('\n', ' ')} 参数",
            Content = new ScrollViewer { Content = editor, MaxHeight = 620 },
            CloseButtonText = "完成",
        };
        await dialog.ShowAsync();
    }

    private async void NodeHelp_Click(object sender, RoutedEventArgs e)
    {
        await new ContentDialog
        {
            XamlRoot = XamlRoot, Title = "节点画布操作",
            Content = "单击节点编辑参数；拖动节点调整布局；滚轮或滚动条移动画布。拖动只更新合成层，不启动图像处理。",
            CloseButtonText = "确定",
        }.ShowAsync();
    }

    private void PreviewZoom_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: string value } && float.TryParse(value,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out var zoom))
            PreviewScroller.ChangeView(null, null, zoom, false);
    }

    private void PreviewFit_Click(object sender, RoutedEventArgs e)
        => PreviewScroller.ChangeView(0, 0, 1, false);

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
