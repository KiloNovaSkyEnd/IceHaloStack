namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class ProcessingSettingsViewModel
{
    private static readonly HashSet<string> NonBaseKeys =
    [
        "stretch_strength", "stretch_black", "curve_contrast",
        "detail_radius", "cg_shadow_h", "cg_mid_h", "cg_high_h", "cg_balance",
        "usm_amount", "usm_radius", "usm_threshold", "usm_passes",
        "bg_radius", "bg_strength", "hp_radius", "hp_amount",
        "emboss_angle", "emboss_height", "emboss_amount", "emboss_opacity",
        "channel_red", "channel_green", "channel_blue", "channel_constant",
        "channel_noise_strength", "channel_noise_radius",
    ];

    public Dictionary<string, object?> ToIpcConfig()
    {
        var values = Sections.SelectMany(section => section.Parameters)
            .ToDictionary(parameter => parameter.Key, parameter => parameter.Value, StringComparer.Ordinal);
        var config = new Dictionary<string, object?>(StringComparer.Ordinal);

        AddStage(config, values, "stretch", EnableStretch, "stretch_strength", "stretch_black");
        var activeBase = EnableBasic && values.Any(pair => !NonBaseKeys.Contains(pair.Key) && Math.Abs(pair.Value) > 1e-7);
        config["basic"] = activeBase;
        if (activeBase)
        {
            foreach (var pair in values.Where(pair => !NonBaseKeys.Contains(pair.Key) && Math.Abs(pair.Value) > 1e-7))
                config[pair.Key] = pair.Value;
            if (values.TryGetValue("detail_radius", out var detailRadius))
                config["detail_radius"] = detailRadius;
            if (new[] { "cg_shadow_s", "cg_mid_s", "cg_high_s" }.Any(key => Math.Abs(values[key]) > 1e-7))
                foreach (var key in new[] { "cg_shadow_h", "cg_mid_h", "cg_high_h", "cg_balance" })
                    config[key] = values[key];
        }

        AddStage(config, values, "usm", EnableUsm, "usm_amount", "usm_radius", "usm_threshold", "usm_passes");
        AddStage(config, values, "background", EnableBackground, "bg_radius", "bg_strength");
        config["curves"] = EnableCurves;
        AddStage(config, values, "highpass", EnableHighPass, "hp_radius", "hp_amount");
        AddStage(config, values, "emboss", EnableEmboss, "emboss_angle", "emboss_height", "emboss_amount", "emboss_opacity");
        AddStage(config, values, "channel", EnableChannelMixer, "channel_red", "channel_green", "channel_blue", "channel_constant", "channel_noise_strength", "channel_noise_radius");
        config["bgr"] = EnableBackground || EnableCurves;
        config["br"] = EnableChannelMixer;
        if (EnableHighPass)
            config["hp_mode"] = HighPassMode;
        if (EnableEmboss)
        {
            config["emboss_style"] = EmbossStyle;
            config["emboss_blend"] = EmbossBlendMode;
        }
        if (EnableChannelMixer)
        {
            config["channel_output"] = ChannelOutput;
            config["channel_mono"] = ChannelMonochrome;
            config["channel_noise"] = ChannelNoiseProtection;
        }
        return config;
    }

    public Dictionary<string, object?> ToCurvePoints()
    {
        if (!EnableCurves)
            return [];
        return CurveEditor.ToIpcCurvePoints();
    }

    private static void AddStage(
        IDictionary<string, object?> config,
        IReadOnlyDictionary<string, double> values,
        string stage,
        bool enabled,
        params string[] keys)
    {
        config[stage] = enabled;
        if (!enabled)
            return;
        foreach (var key in keys)
            if (values.TryGetValue(key, out var value))
                config[key] = value;
    }
}
