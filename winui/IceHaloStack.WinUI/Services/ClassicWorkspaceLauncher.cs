using System.Diagnostics;

namespace IceHaloStack_WinUI.Services;

/// <summary>
/// Transitional full-feature bridge. Native pages keep using IPC services;
/// features not migrated yet open the canonical Tk workspace in its own process.
/// </summary>
internal static class ClassicWorkspaceLauncher
{
    public static void Launch()
    {
        var packagedClassic = Path.Combine(AppContext.BaseDirectory, "Classic", "IceHaloStack.exe");
        if (File.Exists(packagedClassic))
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = packagedClassic,
                WorkingDirectory = Path.GetDirectoryName(packagedClassic)!,
                UseShellExecute = false,
            })?.Dispose();
            return;
        }
        var root = EngineClientFactory.FindEngineRoot();
        var entryPoint = Path.Combine(root, "icehalostack.py");
        if (!File.Exists(entryPoint))
            throw new FileNotFoundException("未找到经典工作区入口。", entryPoint);

        var startInfo = new ProcessStartInfo
        {
            FileName = EngineClientFactory.ResolvePython(windowless: true),
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        startInfo.ArgumentList.Add(entryPoint);
        Process.Start(startInfo)?.Dispose();
    }
}
