using IceHaloStack_WinUI.Services;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class StackPageViewModel
{
    public async Task EnsureThumbnailAsync(StackInputItem item)
    {
        if (item.Thumbnail is not null || item.IsThumbnailLoading || _disposed)
            return;
        item.IsThumbnailLoading = true;
        try
        {
            var thumbnail = await ThumbnailDecodeService.LoadAsync(item.Path);
            if (!_disposed && Inputs.Contains(item))
                item.Thumbnail = thumbnail;
        }
        finally
        {
            item.IsThumbnailLoading = false;
        }
    }
}
