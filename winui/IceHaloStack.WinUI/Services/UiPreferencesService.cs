using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace IceHaloStack_WinUI.Services;

internal sealed class UiPreferencesService
{
    private static readonly string SettingsPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "IceHaloStack", "ui-settings.json");

    public static UiPreferencesService Current { get; } = Load();
    public string Font { get; set; } = "DengXian";
    public string Language { get; set; } = "zh-CN";
    public string Theme { get; set; } = "Default";

    public void SetFont(string value) { Font = value; Save(); }
    public void SetLanguage(string value) { Language = value; Save(); }
    public void SetTheme(string value) { Theme = value; Save(); }

    public void Apply(FrameworkElement root)
    {
        root.Language = Language == "en" ? "en-US" : "zh-CN";
        root.RequestedTheme = Theme switch
        {
            "Light" => ElementTheme.Light, "Dark" => ElementTheme.Dark, _ => ElementTheme.Default,
        };
        if (root is Control control)
            control.FontFamily = Font switch
            {
                "Microsoft YaHei UI" => new FontFamily("Microsoft YaHei UI"),
                "Microsoft YaHei" => new FontFamily("Microsoft YaHei"),
                "System" => new FontFamily("Segoe UI"),
                _ => new FontFamily("DengXian"),
            };
    }

    private static UiPreferencesService Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
                return JsonSerializer.Deserialize<UiPreferencesService>(File.ReadAllText(SettingsPath)) ?? new();
        }
        catch { }
        return new();
    }

    private void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
            File.WriteAllText(SettingsPath, JsonSerializer.Serialize(this));
        }
        catch { }
    }
}
