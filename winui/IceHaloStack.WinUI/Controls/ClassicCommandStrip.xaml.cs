using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class ClassicCommandStrip : UserControl
{
    public ClassicCommandStrip()
    {
        InitializeComponent();
        Loaded += (_, _) => ApplyLanguage(Services.UiPreferencesService.Current.Language);
    }

    public event RoutedEventHandler? AddImagesRequested;
    public event RoutedEventHandler? AddFolderRequested;
    public event RoutedEventHandler? RemoveSelectedRequested;
    public event RoutedEventHandler? StartRequested;
    public event RoutedEventHandler? CancelRequested;
    public event RoutedEventHandler? PauseRequested;
    public event RoutedEventHandler? UseCurrentRequested;
    public event RoutedEventHandler? UndoRequested;
    public event RoutedEventHandler? RedoRequested;
    public event RoutedEventHandler? AutoStretchRequested;
    public event RoutedEventHandler? OpenTimelapseRequested;
    public event RoutedEventHandler? ChooseOutputRequested;
    public event RoutedEventHandler? OpenImageRequested;
    public event RoutedEventHandler? SavePreviewRequested;
    public event RoutedEventHandler? ClearProjectRequested;
    public event RoutedEventHandler? ExitRequested;
    public event RoutedEventHandler? SelectAllRequested;
    public event RoutedEventHandler? ResetProcessingRequested;
    public event RoutedEventHandler? FitPreviewRequested;
    public event EventHandler<string>? ProcessingSectionRequested;
    public event EventHandler<string>? ThemeRequested;
    public event EventHandler<string>? FontRequested;
    public event EventHandler<string>? LanguageRequested;
    public event EventHandler<string>? HelpRequested;

    private void AddImages_Click(object sender, RoutedEventArgs e) => AddImagesRequested?.Invoke(this, e);
    private void AddFolder_Click(object sender, RoutedEventArgs e) => AddFolderRequested?.Invoke(this, e);
    private void RemoveSelected_Click(object sender, RoutedEventArgs e) => RemoveSelectedRequested?.Invoke(this, e);
    private void Start_Click(object sender, RoutedEventArgs e) => StartRequested?.Invoke(this, e);
    private void Cancel_Click(object sender, RoutedEventArgs e) => CancelRequested?.Invoke(this, e);
    private void Pause_Click(object sender, RoutedEventArgs e) => PauseRequested?.Invoke(this, e);
    private void UseCurrent_Click(object sender, RoutedEventArgs e) => UseCurrentRequested?.Invoke(this, e);
    private void Undo_Click(object sender, RoutedEventArgs e) => UndoRequested?.Invoke(this, e);
    private void Redo_Click(object sender, RoutedEventArgs e) => RedoRequested?.Invoke(this, e);
    private void AutoStretch_Click(object sender, RoutedEventArgs e) => AutoStretchRequested?.Invoke(this, e);
    private void OpenTimelapse_Click(object sender, RoutedEventArgs e) => OpenTimelapseRequested?.Invoke(this, e);
    private void ChooseOutput_Click(object sender, RoutedEventArgs e) => ChooseOutputRequested?.Invoke(this, e);
    private void OpenImage_Click(object sender, RoutedEventArgs e) => OpenImageRequested?.Invoke(this, e);
    private void SavePreview_Click(object sender, RoutedEventArgs e) => SavePreviewRequested?.Invoke(this, e);
    private void ClearProject_Click(object sender, RoutedEventArgs e) => ClearProjectRequested?.Invoke(this, e);
    private void Exit_Click(object sender, RoutedEventArgs e) => ExitRequested?.Invoke(this, e);
    private void SelectAll_Click(object sender, RoutedEventArgs e) => SelectAllRequested?.Invoke(this, e);
    private void ResetProcessing_Click(object sender, RoutedEventArgs e) => ResetProcessingRequested?.Invoke(this, e);
    private void FitPreview_Click(object sender, RoutedEventArgs e) => FitPreviewRequested?.Invoke(this, e);
    private void ProcessingSection_Click(object sender, RoutedEventArgs e) => ProcessingSectionRequested?.Invoke(this, (sender as FrameworkElement)?.Tag?.ToString() ?? "stack");
    private void Theme_Click(object sender, RoutedEventArgs e) => ThemeRequested?.Invoke(this, (sender as FrameworkElement)?.Tag?.ToString() ?? "Default");
    private void Font_Click(object sender, RoutedEventArgs e) => FontRequested?.Invoke(this, (sender as FrameworkElement)?.Tag?.ToString() ?? "DengXian");
    private void Language_Click(object sender, RoutedEventArgs e)
    {
        var language = (sender as FrameworkElement)?.Tag?.ToString() ?? "zh-CN";
        ApplyLanguage(language);
        LanguageRequested?.Invoke(this, language);
    }
    private void Help_Click(object sender, RoutedEventArgs e) => HelpRequested?.Invoke(this, (sender as FrameworkElement)?.Tag?.ToString() ?? "about");
}
