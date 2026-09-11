namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class ProcessingSettingsViewModel
{
    public void CopyFrom(ProcessingSettingsViewModel source)
    {
        ArgumentNullException.ThrowIfNull(source);
        var values = source.Sections.SelectMany(section => section.Parameters)
            .ToDictionary(parameter => parameter.Key, parameter => parameter.Value, StringComparer.Ordinal);
        foreach (var parameter in Sections.SelectMany(section => section.Parameters))
            if (values.TryGetValue(parameter.Key, out var value))
                parameter.Value = value;

        EnableStretch = source.EnableStretch;
        EnableBasic = source.EnableBasic;
        EnableUsm = source.EnableUsm;
        EnableBackground = source.EnableBackground;
        EnableCurves = source.EnableCurves;
        EnableHighPass = source.EnableHighPass;
        EnableEmboss = source.EnableEmboss;
        EnableChannelMixer = source.EnableChannelMixer;
        ChannelMonochrome = source.ChannelMonochrome;
        ChannelNoiseProtection = source.ChannelNoiseProtection;
        HighPassMode = source.HighPassMode;
        EmbossStyle = source.EmbossStyle;
        EmbossBlendMode = source.EmbossBlendMode;
        ChannelOutput = source.ChannelOutput;
        CurveEditor.CopyFrom(source.CurveEditor);
    }
}
