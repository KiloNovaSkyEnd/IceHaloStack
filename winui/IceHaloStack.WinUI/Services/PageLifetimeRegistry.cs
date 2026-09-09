namespace IceHaloStack_WinUI.Services;

/// <summary>
/// Owns cached page resources for the window lifetime. Navigation may unload
/// a cached page visually, but its engine client must remain reusable until
/// the application window closes.
/// </summary>
internal static class PageLifetimeRegistry
{
    private static readonly HashSet<IAsyncDisposable> Resources = [];

    public static void Register(IAsyncDisposable resource)
    {
        ArgumentNullException.ThrowIfNull(resource);
        Resources.Add(resource);
    }

    public static async ValueTask DisposeAllAsync()
    {
        var resources = Resources.ToArray();
        Resources.Clear();
        foreach (var resource in resources)
        {
            try
            {
                await resource.DisposeAsync().ConfigureAwait(false);
            }
            catch
            {
                // Window shutdown must continue even if an engine child has
                // already exited or a pipe is no longer reachable.
            }
        }
    }
}
