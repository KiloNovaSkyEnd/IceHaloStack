using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class NodeStageEditorControl : UserControl
{
    private bool _configuring;

    public NodeStageEditorControl()
    {
        InitializeComponent();
        Loaded += (_, _) => Configure();
    }

    public ProcessingSettingsViewModel? ViewModel { get; set; }
    public string StageKey { get; set; } = string.Empty;

    private void Configure()
    {
        if (ViewModel is null)
            return;
        _configuring = true;
        try
        {
            var state = Resolve();
            Parameters.Section = state.Section;
            EnabledSwitch.IsOn = state.Enabled;
            if (StageKey == "highpass")
                ConfigureMode(ModeBox, "混合模式", ViewModel.HighPassModes, ViewModel.HighPassMode);
            else if (StageKey == "emboss")
            {
                ConfigureMode(ModeBox, "浮雕类型", ViewModel.EmbossStyles, ViewModel.EmbossStyle);
                ConfigureMode(SecondaryModeBox, "混合模式", ViewModel.EmbossBlendModes, ViewModel.EmbossBlendMode);
            }
        }
        finally { _configuring = false; }
    }

    private (ProcessingSection Section, bool Enabled) Resolve() => StageKey switch
    {
        "stretch" => (ViewModel!.StretchSection, ViewModel.EnableStretch),
        "usm" => (ViewModel!.Sections[10], ViewModel.EnableUsm),
        "background" => (ViewModel!.Sections[11], ViewModel.EnableBackground),
        "curves" => (ViewModel!.CurvesSection, ViewModel.EnableCurves),
        "highpass" => (ViewModel!.Sections[13], ViewModel.EnableHighPass),
        "emboss" => (ViewModel!.Sections[14], ViewModel.EnableEmboss),
        "channel" => (ViewModel!.ChannelSection, ViewModel.EnableChannelMixer),
        _ => throw new InvalidOperationException($"未知节点阶段：{StageKey}"),
    };

    private void Enabled_Toggled(object sender, RoutedEventArgs e)
    {
        if (_configuring || ViewModel is null)
            return;
        switch (StageKey)
        {
            case "stretch": ViewModel.EnableStretch = EnabledSwitch.IsOn; break;
            case "usm": ViewModel.EnableUsm = EnabledSwitch.IsOn; break;
            case "background": ViewModel.EnableBackground = EnabledSwitch.IsOn; break;
            case "curves": ViewModel.EnableCurves = EnabledSwitch.IsOn; break;
            case "highpass": ViewModel.EnableHighPass = EnabledSwitch.IsOn; break;
            case "emboss": ViewModel.EnableEmboss = EnabledSwitch.IsOn; break;
            case "channel": ViewModel.EnableChannelMixer = EnabledSwitch.IsOn; break;
        }
    }

    private static void ConfigureMode(ComboBox box, string header, IEnumerable<string> values, string selected)
    {
        box.Header = header;
        box.ItemsSource = values;
        box.SelectedItem = selected;
        box.Visibility = Visibility.Visible;
    }

    private void Mode_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_configuring || ViewModel is null || ModeBox.SelectedItem is not string value)
            return;
        if (StageKey == "highpass") ViewModel.HighPassMode = value;
        else if (StageKey == "emboss") ViewModel.EmbossStyle = value;
    }

    private void SecondaryMode_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_configuring && ViewModel is not null && StageKey == "emboss"
            && SecondaryModeBox.SelectedItem is string value)
            ViewModel.EmbossBlendMode = value;
    }
}
