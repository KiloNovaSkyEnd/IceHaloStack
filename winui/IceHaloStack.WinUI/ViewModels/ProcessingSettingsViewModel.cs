using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace IceHaloStack_WinUI.ViewModels;

/// <summary>
/// UI-neutral representation of the canonical Python processing pipeline.
/// Every native page shares this model instead of duplicating controls or
/// implementing image algorithms in C#.
/// </summary>
public sealed partial class ProcessingSettingsViewModel : ObservableObject
{
    private static readonly string[] MixerColors =
    [
        "red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta",
    ];

    public ProcessingSettingsViewModel()
    {
        Sections = new ObservableCollection<ProcessingSection>
        {
            Section("Stretch / 拉伸",
                Parameter("stretch_strength", "Asinh Strength", 0.1, 500, 0.5, 8),
                Parameter("stretch_black", "Black Point", 0, 0.05, 0.0005)),
            Section("Basic / 基本明暗",
                Parameter("exposure", "Exposure (EV)", -5, 5, 0.05),
                Parameter("contrast", "Contrast", -100, 100, 1),
                Parameter("highlights", "Highlights", -100, 100, 1),
                Parameter("shadows", "Shadows", -100, 100, 1),
                Parameter("whites", "Whites", -100, 100, 1),
                Parameter("blacks", "Blacks", -100, 100, 1)),
            Section("White Balance / 白平衡",
                Parameter("temperature", "Temperature", -100, 100, 1),
                Parameter("tint", "Tint", -100, 100, 1)),
            Section("Presence / 质感",
                Parameter("texture", "Texture", -100, 100, 1),
                Parameter("clarity", "Clarity", -100, 100, 1),
                Parameter("dehaze", "Dehaze", -100, 100, 1)),
            Section("HSL / 全局色相·饱和度·明度",
                Parameter("hsl_hue", "Hue", -180, 180, 1),
                Parameter("hsl_sat", "Saturation", -100, 100, 1),
                Parameter("hsl_lum", "Luminance", -100, 100, 1)),
            CreateColorMixerSection(),
            Section("Color Grading / 色彩分级",
                Parameter("cg_shadow_h", "Shadows Hue", 0, 360, 1),
                Parameter("cg_shadow_s", "Shadows Saturation", -100, 100, 1),
                Parameter("cg_mid_h", "Midtones Hue", 0, 360, 1),
                Parameter("cg_mid_s", "Midtones Saturation", -100, 100, 1),
                Parameter("cg_high_h", "Highlights Hue", 0, 360, 1),
                Parameter("cg_high_s", "Highlights Saturation", -100, 100, 1),
                Parameter("cg_balance", "Balance", -100, 100, 1)),
            Section("Detail / 细节",
                Parameter("detail_sharpen", "Sharpen", 0, 200, 1),
                Parameter("detail_radius", "Radius", 0.2, 10, 0.1, 1),
                Parameter("luma_nr", "Luma NR", 0, 100, 1),
                Parameter("chroma_nr", "Chroma NR", 0, 100, 1)),
            Section("Optics / 光学",
                Parameter("opt_distortion", "Distortion", -100, 100, 1),
                Parameter("opt_vignette", "Vignette", -100, 100, 1),
                Parameter("opt_ca", "CA correction", -100, 100, 1)),
            Section("Calibration / 校准",
                Parameter("cal_red_h", "Red Primary Hue", -100, 100, 1),
                Parameter("cal_red_s", "Red Primary Saturation", -100, 100, 1),
                Parameter("cal_green_h", "Green Primary Hue", -100, 100, 1),
                Parameter("cal_green_s", "Green Primary Saturation", -100, 100, 1),
                Parameter("cal_blue_h", "Blue Primary Hue", -100, 100, 1),
                Parameter("cal_blue_s", "Blue Primary Saturation", -100, 100, 1)),
            Section("USM / 反锐化蒙版",
                Parameter("usm_amount", "Amount %", 0, 500, 1, 100),
                Parameter("usm_radius", "Radius px", 0.1, 250, 0.1, 2),
                Parameter("usm_threshold", "Threshold", 0, 255, 1),
                Parameter("usm_passes", "Passes", 1, 10, 1, 1)),
            Section("Background / 背景抑制",
                Parameter("bg_radius", "Radius px", 1, 500, 1, 80),
                Parameter("bg_strength", "Strength %", 0, 200, 1, 100)),
            Section("Curves / 曲线",
                Parameter("curve_contrast", "S-Curve Contrast", -100, 100, 1)),
            Section("High Pass / 高反差保留",
                Parameter("hp_radius", "Radius px", 0.1, 250, 0.1, 10),
                Parameter("hp_amount", "Opacity %", 0, 100, 1, 100)),
            Section("Emboss / 浮雕",
                Parameter("emboss_angle", "Angle", -180, 180, 1, -128),
                Parameter("emboss_height", "Height", 0.1, 20, 0.1, 1),
                Parameter("emboss_amount", "Amount %", 0, 500, 1, 100),
                Parameter("emboss_opacity", "Opacity %", 0, 100, 1, 100)),
            Section("Channel Mixer / 通道混合器",
                Parameter("channel_red", "Red %", -200, 200, 1, 40),
                Parameter("channel_green", "Green %", -200, 200, 1, 40),
                Parameter("channel_blue", "Blue %", -200, 200, 1, 20),
                Parameter("channel_constant", "Constant %", -200, 200, 1),
                Parameter("channel_noise_strength", "Noise protection %", 0, 100, 1, 30),
                Parameter("channel_noise_radius", "Noise radius px", 0.1, 10, 0.1, 0.8)),
        };
        StretchSection = Sections[0];
        BaseSections = Sections.Skip(1).Take(9).ToArray();
        DetailSections = new[] { Sections[10], Sections[11], Sections[13], Sections[14] };
        CurvesSection = Sections[12];
        ChannelSection = Sections[15];
        InitializeHistory();
    }

    public ObservableCollection<ProcessingSection> Sections { get; }
    public CurveEditorViewModel CurveEditor { get; } = new();
    public ProcessingSection StretchSection { get; }
    public IReadOnlyList<ProcessingSection> BaseSections { get; }
    public IReadOnlyList<ProcessingSection> DetailSections { get; }
    public ProcessingSection CurvesSection { get; }
    public ProcessingSection ChannelSection { get; }
    public IReadOnlyList<string> HighPassModes { get; } = ["Overlay", "Soft Light", "Linear Light"];
    public IReadOnlyList<string> EmbossStyles { get; } = ["Photoshop Emboss", "Color Emboss", "Gray Emboss"];
    public IReadOnlyList<string> EmbossBlendModes { get; } = ["Normal", "Overlay", "Soft Light", "Linear Light"];
    public IReadOnlyList<string> ChannelOutputs { get; } = ["灰色", "红色", "绿色", "蓝色"];

    [ObservableProperty] private bool _enableStretch = true;
    [ObservableProperty] private bool _enableBasic = true;
    [ObservableProperty] private bool _enableUsm;
    [ObservableProperty] private bool _enableBackground;
    [ObservableProperty] private bool _enableCurves;
    [ObservableProperty] private bool _enableHighPass;
    [ObservableProperty] private bool _enableEmboss;
    [ObservableProperty] private bool _enableChannelMixer;
    [ObservableProperty] private bool _channelMonochrome = true;
    [ObservableProperty] private bool _channelNoiseProtection = true;
    [ObservableProperty] private string _highPassMode = "Overlay";
    [ObservableProperty] private string _embossStyle = "Photoshop Emboss";
    [ObservableProperty] private string _embossBlendMode = "Normal";
    [ObservableProperty] private string _channelOutput = "灰色";

    [RelayCommand]
    private void Reset()
    {
        foreach (var parameter in Sections.SelectMany(section => section.Parameters))
            parameter.Reset();
        EnableStretch = true;
        EnableBasic = true;
        EnableUsm = EnableBackground = EnableCurves = EnableHighPass = EnableEmboss = EnableChannelMixer = false;
        ChannelMonochrome = ChannelNoiseProtection = true;
        HighPassMode = "Overlay";
        EmbossStyle = "Photoshop Emboss";
        EmbossBlendMode = "Normal";
        ChannelOutput = "灰色";
        CurveEditor.ResetAll();
    }

    private ProcessingParameter Find(string key) => Sections
        .SelectMany(section => section.Parameters)
        .First(parameter => string.Equals(parameter.Key, key, StringComparison.Ordinal));

    private static ProcessingParameter Parameter(string key, string label, double min, double max, double step, double value = 0)
        => new(key, label, min, max, step, value);

    private static ProcessingSection Section(string title, params ProcessingParameter[] parameters)
        => new(title, parameters);

    private static ProcessingSection CreateColorMixerSection()
    {
        var parameters = MixerColors.SelectMany(color => new[]
        {
            Parameter($"mix_{color}_h", $"{color} Hue", -100, 100, 1),
            Parameter($"mix_{color}_s", $"{color} Saturation", -100, 100, 1),
            Parameter($"mix_{color}_l", $"{color} Luminance", -100, 100, 1),
        }).ToArray();
        return Section("Color Mixer / 颜色混合器", parameters);
    }
}
