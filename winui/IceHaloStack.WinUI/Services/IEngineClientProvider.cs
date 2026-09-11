using IceHaloStack.WinUI.Client;

namespace IceHaloStack_WinUI.Services;

/// <summary>Owns a reusable connection to the packaged Python image engine.</summary>
public interface IEngineClientProvider : IAsyncDisposable
{
    Task<IpcClient> GetClientAsync(CancellationToken cancellationToken = default);
}
