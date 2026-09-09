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
        var engineRoot = FindEngineRoot();
        var python = Environment.GetEnvironmentVariable(PythonEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(python))
            python = "python";

        return new IpcClient(
            executable: python,
            arguments: new[] { "-m", "ihs.services.ipc" },
            workingDirectory: engineRoot,
            requestTimeout: TimeSpan.FromSeconds(30));
    }

    private static string FindEngineRoot()
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
