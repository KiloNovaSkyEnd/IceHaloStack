using IceHaloStack.WinUI.Client;

namespace IceHaloStack_WinUI.Services;

/// <summary>
/// Locates the Python source engine for development runs and creates the
/// long-lived client process used by WinUI pages. Release packaging will place
/// an engine worker next to the app; that resolver can replace this one without
/// changing the page or its ViewModel.
/// </summary>
internal static class EngineClientFactory
{
    private const string PythonEnvironmentVariable = "ICEHALOSTACK_PYTHON";
    private const string EngineRootEnvironmentVariable = "ICEHALOSTACK_ENGINE_ROOT";

    public static IpcClient CreateDevelopmentClient()
    {
        var packagedEngine = Path.Combine(AppContext.BaseDirectory, "Engine", "IceHaloStackEngine.exe");
        if (File.Exists(packagedEngine))
        {
            return new IpcClient(
                executable: packagedEngine,
                arguments: Array.Empty<string>(),
                workingDirectory: Path.GetDirectoryName(packagedEngine)!,
                requestTimeout: TimeSpan.FromSeconds(30));
        }
        var engineRoot = FindEngineRoot();
        var python = ResolvePython(windowless: false);

        return new IpcClient(
            executable: python,
            arguments: new[] { "-m", "ihs.services.ipc" },
            workingDirectory: engineRoot,
            requestTimeout: TimeSpan.FromSeconds(30));
    }

    internal static string ResolvePython(bool windowless)
    {
        var configured = Environment.GetEnvironmentVariable(PythonEnvironmentVariable);
        if (!string.IsNullOrWhiteSpace(configured))
            return configured;

        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var scripts = Path.Combine(localAppData, "IceHaloStackRuntime0946", "venv", "Scripts");
        var preferred = Path.Combine(scripts, windowless ? "pythonw.exe" : "python.exe");
        if (File.Exists(preferred))
            return preferred;
        var fallback = Path.Combine(scripts, "python.exe");
        return File.Exists(fallback) ? fallback : "python";
    }

    internal static string FindEngineRoot()
    {
        var configured = Environment.GetEnvironmentVariable(EngineRootEnvironmentVariable);
        if (!string.IsNullOrWhiteSpace(configured))
        {
            var fullPath = Path.GetFullPath(configured);
            if (HasIpcModule(fullPath))
                return fullPath;
            throw new DirectoryNotFoundException(
                $"{EngineRootEnvironmentVariable} 未指向包含 ihs/services/ipc.py 的目录：{fullPath}");
        }

        for (var directory = new DirectoryInfo(AppContext.BaseDirectory);
             directory is not null;
             directory = directory.Parent)
        {
            if (HasIpcModule(directory.FullName))
                return directory.FullName;
        }

        throw new DirectoryNotFoundException(
            "未找到 Python 图像处理引擎。请设置 ICEHALOSTACK_ENGINE_ROOT 指向源码根目录。");
    }

    private static bool HasIpcModule(string root)
        => File.Exists(Path.Combine(root, "ihs", "services", "ipc.py"));
}
