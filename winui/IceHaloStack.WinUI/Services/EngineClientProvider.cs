using IceHaloStack.WinUI.Client;

namespace IceHaloStack_WinUI.Services;

/// <summary>Keeps one warm engine process per workspace and replaces dead connections.</summary>
public sealed class EngineClientProvider : IEngineClientProvider
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private IpcClient? _client;
    private bool _disposed;

    public async Task<IpcClient> GetClientAsync(CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_client is { IsAlive: true })
                return _client;
            if (_client is not null)
                await _client.DisposeAsync().ConfigureAwait(false);

            var client = EngineClientFactory.CreateDevelopmentClient();
            try
            {
                await client.StartAsync(cancellationToken).ConfigureAwait(false);
                await client.PingAsync(TimeSpan.FromSeconds(12), cancellationToken).ConfigureAwait(false);
                _client = client;
                return client;
            }
            catch
            {
                await client.DisposeAsync().ConfigureAwait(false);
                throw;
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed)
            return;
        _disposed = true;
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (_client is not null)
            {
                await _client.DisposeAsync().ConfigureAwait(false);
                _client = null;
            }
        }
        finally
        {
            _gate.Release();
            _gate.Dispose();
        }
    }
}
