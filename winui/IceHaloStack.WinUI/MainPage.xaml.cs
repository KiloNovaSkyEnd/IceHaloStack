using IceHaloStack_WinUI.Services;
using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace IceHaloStack_WinUI;

/// <summary>The WinUI-native port of the original Classic workspace shell.</summary>
public sealed partial class MainPage : Page
{
    private static readonly HashSet<string> ImageExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp",
        ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2",
    };

    public StackPageViewModel ViewModel { get; } = new();

    public MainPage()
    {
        InitializeComponent();
        PageLifetimeRegistry.Register(ViewModel);
    }

    private void MainPage_Loaded(object sender, RoutedEventArgs e)
    {
        UiPreferencesService.Current.Apply(this);
        ViewModel.EnsureComputeProbeStarted();
    }

    private async void PickInputs_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        foreach (var extension in ImageExtensions.OrderBy(value => value))
            picker.FileTypeFilter.Add(extension);
        InitializeWithWindow.Initialize(picker, App.WindowHandle);

        var files = await picker.PickMultipleFilesAsync();
        if (files.Count > 0)
            ViewModel.AddInputPaths(files.Select(file => file.Path));
    }

    private async void PickFolder_Click(object sender, RoutedEventArgs e)
    {
        var picker = CreateFolderPicker();
        var folder = await picker.PickSingleFolderAsync();
        if (folder is null)
            return;

        var paths = Directory.EnumerateFiles(folder.Path, "*", SearchOption.TopDirectoryOnly)
            .Where(path => ImageExtensions.Contains(Path.GetExtension(path)))
            .OrderBy(path => path, StringComparer.CurrentCultureIgnoreCase);
        ViewModel.AddInputPaths(paths);
    }

    private void RemoveSelected_Click(object sender, RoutedEventArgs e) => ViewModel.RemoveMarkedInputs();

    private async void OpenImage_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        foreach (var extension in ImageExtensions.OrderBy(value => value)) picker.FileTypeFilter.Add(extension);
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var file = await picker.PickSingleFileAsync();
        if (file is null) return;
        ViewModel.AddInputPaths([file.Path]);
        ViewModel.SelectedInput = ViewModel.Inputs.FirstOrDefault(item => string.Equals(item.Path, file.Path, StringComparison.OrdinalIgnoreCase));
    }

    private async void SavePreview_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileSavePicker { SuggestedStartLocation = PickerLocationId.PicturesLibrary, SuggestedFileName = "IceHaloStack_preview" };
        picker.FileTypeChoices.Add("PNG 图像", [".png"]);
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var file = await picker.PickSaveFileAsync();
        if (file is null) return;
        try { await ViewModel.SaveCurrentPreviewAsync(file.Path); }
        catch (Exception exception) { await ShowDialogAsync("无法保存预览", exception.Message); }
    }

    private void ClearProject_Click(object sender, RoutedEventArgs e) => ViewModel.ClearProject();
    private void Exit_Click(object sender, RoutedEventArgs e) => App.Window.Close();
    private void SelectAll_Click(object sender, RoutedEventArgs e) => ViewModel.SelectAllInputs();
    private void ResetProcessing_Click(object sender, RoutedEventArgs e) => ViewModel.Processing.ResetCommand.Execute(null);
    private void ProcessingSection_Requested(object? sender, string section) => ProcessingTabs.SelectSection(section);
    private void FitPreview_Click(object sender, RoutedEventArgs e) => PreviewPane.FitToWindow();

    private void Theme_Requested(object? sender, string theme)
    {
        UiPreferencesService.Current.SetTheme(theme);
        UiPreferencesService.Current.Apply(this);
    }

    private void Font_Requested(object? sender, string font)
    {
        UiPreferencesService.Current.SetFont(font);
        UiPreferencesService.Current.Apply(this);
    }

    private async void Language_Requested(object? sender, string language)
    {
        UiPreferencesService.Current.SetLanguage(language);
        UiPreferencesService.Current.Apply(this);
        await ShowDialogAsync(language == "en" ? "Language" : "界面语言",
            language == "en" ? "English menus, commands, and locale are active. Engine progress messages retain their original wording."
                             : "已切换为中文菜单、命令和界面区域设置。");
    }

    private async void Help_Requested(object? sender, string topic)
    {
        if (topic == "performance")
        {
            await ShowDialogAsync("单独堆栈与性能", "平均值堆栈可选自动、GPU 或 CPU。自动模式会先完成设备自检，有可用 GPU 时优先使用；处理在 Python 引擎线程运行，WinUI 界面可继续滚动和取消。");
            return;
        }
        if (topic == "storage")
        {
            var temp = Path.GetTempPath();
            var files = Directory.EnumerateFiles(temp, "IceHaloStack-*", SearchOption.TopDirectoryOnly).ToArray();
            var bytes = files.Sum(path => { try { return new FileInfo(path).Length; } catch { return 0L; } });
            await ShowDialogAsync("存储与缓存管理", $"当前会话预览缓存：{files.Length} 个文件，{bytes / 1024d / 1024d:F1} MiB。\n关闭 IceHaloStack 时会清理本会话生成的预览文件。");
            return;
        }
        await ShowDialogAsync("关于 IceHaloStack", "IceHaloStack v0.9.6.8c\nWinUI 3 原生界面 + 独立 Python 图像引擎。");
    }

    private async Task ShowDialogAsync(string title, string content)
        => await new ContentDialog { XamlRoot = XamlRoot, Title = title, Content = content, CloseButtonText = "确定" }.ShowAsync();

    private void StartStack_Click(object sender, RoutedEventArgs e)
    {
        if (ViewModel.StartStackCommand.CanExecute(null))
            ViewModel.StartStackCommand.Execute(null);
    }

    private void Cancel_Click(object sender, RoutedEventArgs e)
    {
        if (ViewModel.CancelCommand.CanExecute(null))
            ViewModel.CancelCommand.Execute(null);
    }

    private void Pause_Click(object sender, RoutedEventArgs e)
    {
        if (ViewModel.TogglePauseCommand.CanExecute(null)) ViewModel.TogglePauseCommand.Execute(null);
    }

    private void UseCurrent_Click(object sender, RoutedEventArgs e)
    {
        if (ViewModel.UseCurrentCommand.CanExecute(null)) ViewModel.UseCurrentCommand.Execute(null);
    }

    private void Undo_Click(object sender, RoutedEventArgs e)
    {
        if (ViewModel.Processing.CanUndo) ViewModel.Processing.Undo();
    }

    private void Redo_Click(object sender, RoutedEventArgs e)
    {
        if (ViewModel.Processing.CanRedo) ViewModel.Processing.Redo();
    }

    private void AutoStretch_Click(object sender, RoutedEventArgs e)
        => ViewModel.AutoStretchPreview = !ViewModel.AutoStretchPreview;

    private void OpenTimelapse_Click(object sender, RoutedEventArgs e)
    {
        if (ViewModel.CanNavigate)
            Frame.Navigate(typeof(NodeWorkflowPage));
    }

    private async void PickOutputDirectory_Click(object sender, RoutedEventArgs e)
    {
        var folder = await CreateFolderPicker().PickSingleFolderAsync();
        if (folder is null)
            return;
        ViewModel.OutputDirectory = folder.Path;
        ViewModel.ApplyOutputNaming();
    }

    private static FolderPicker CreateFolderPicker()
    {
        var picker = new FolderPicker { SuggestedStartLocation = PickerLocationId.PicturesLibrary };
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, App.WindowHandle);
        return picker;
    }
}
