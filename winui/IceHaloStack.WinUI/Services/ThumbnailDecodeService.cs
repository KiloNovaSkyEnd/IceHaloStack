using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage;
using Windows.Storage.FileProperties;

namespace IceHaloStack_WinUI.Services;

/// <summary>Asynchronously decodes a small preview only when a virtualized row becomes visible.</summary>
internal static class ThumbnailDecodeService
{
    public static async Task<BitmapImage?> LoadAsync(string path, uint size = 64)
    {
        try
        {
            var file = await StorageFile.GetFileFromPathAsync(path);
            using var thumbnail = await file.GetThumbnailAsync(
                ThumbnailMode.PicturesView, size, ThumbnailOptions.UseCurrentScale);
            if (thumbnail is null)
                return null;
            var image = new BitmapImage { DecodePixelWidth = (int)size };
            await image.SetSourceAsync(thumbnail);
            return image;
        }
        catch
        {
            return null;
        }
    }
}
