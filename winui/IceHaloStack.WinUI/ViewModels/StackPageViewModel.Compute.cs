using CommunityToolkit.Mvvm.Input;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class StackPageViewModel
{
    private bool _computeProbeStarted;

    public void EnsureComputeProbeStarted()
    {
        if (_computeProbeStarted || _disposed)
            return;
        _computeProbeStarted = true;
        _ = ProbeComputeAsync(refresh: false);
    }

    [RelayCommand]
    private Task RefreshComputeAsync() => ProbeComputeAsync(refresh: true);

    private async Task ProbeComputeAsync(bool refresh)
    {
        if (Compute.IsProbing || _disposed)
            return;
        await DispatchToUiAsync(() => Compute.IsProbing = true).ConfigureAwait(false);
        try
        {
            var client = await GetClientAsync().ConfigureAwait(false);
            var result = await client.RequestAsync(
                "compute_capabilities",
                new Dictionary<string, object?> { ["refresh"] = refresh },
                timeout: TimeSpan.FromSeconds(15)).ConfigureAwait(false);
            if (result is { } payload)
                await DispatchToUiAsync(() => Compute.ApplyCapabilities(payload)).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            await DispatchToUiAsync(() => Compute.Status = $"后端自检失败，将使用 CPU：{exception.Message}")
                .ConfigureAwait(false);
        }
        finally
        {
            await DispatchToUiAsync(() => Compute.IsProbing = false).ConfigureAwait(false);
        }
    }
}
