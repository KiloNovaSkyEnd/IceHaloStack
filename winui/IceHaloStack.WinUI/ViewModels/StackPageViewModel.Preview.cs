using CommunityToolkit.Mvvm.ComponentModel;
using Microsoft.UI.Xaml.Media.Imaging;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class StackPageViewModel
{
    private int _previewGeneration;
    private readonly List<string> _previewFiles = [];
    private string? _currentPreviewPath;
    [ObservableProperty] private bool _autoStretchPreview;

    partial void OnAutoStretchPreviewChanged(bool value) => _ = LoadSelectedPreviewAsync(SelectedInput);

    public async Task SaveCurrentPreviewAsync(string outputPath)
    {
        if (string.IsNullOrWhiteSpace(_currentPreviewPath) || !File.Exists(_currentPreviewPath))
            throw new InvalidOperationException("请先在帧列表中选择一张图像。");
        await using var source = File.OpenRead(_currentPreviewPath);
        await using var target = File.Create(outputPath);
        await source.CopyToAsync(target).ConfigureAwait(false);
    }

    private async Task LoadSelectedPreviewAsync(StackInputItem? item)
    {
        var generation = Interlocked.Increment(ref _previewGeneration);
        if (item is null || _disposed)
        {
            await DispatchToUiAsync(() =>
            {
                PreviewSource = null;
                _currentPreviewPath = null;
                HistogramBins.Clear();
            }).ConfigureAwait(false);
            return;
        }

        var outputPath = Path.Combine(Path.GetTempPath(), $"IceHaloStack-frame-preview-{Guid.NewGuid():N}.png");
        _previewFiles.Add(outputPath);
        try
        {
            var client = await _engineClientProvider.GetClientAsync().ConfigureAwait(false);
            var result = await client.RequestAsync(
                "image_preview",
                new Dictionary<string, object?>
                {
                    ["input_path"] = item.Path,
                    ["output_path"] = outputPath,
                    ["max_side"] = 2048,
                    ["auto_stretch"] = AutoStretchPreview,
                },
                timeout: TimeSpan.FromSeconds(90)).ConfigureAwait(false);
            if (result is null || generation != _previewGeneration || _disposed)
                return;

            var bins = result.Value.TryGetProperty("histogram", out var histogram)
                ? histogram.EnumerateArray().Select(value => Math.Clamp(value.GetDouble() * 86.0, 1.0, 86.0)).ToArray()
                : [];
            await DispatchToUiAsync(() =>
            {
                if (generation != _previewGeneration || _disposed)
                    return;
                PreviewSource = new BitmapImage(new Uri(outputPath));
                _currentPreviewPath = outputPath;
                HistogramBins.Clear();
                foreach (var bin in bins)
                    HistogramBins.Add(bin);
            }).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            if (generation == _previewGeneration && !_disposed)
                await DispatchToUiAsync(() => ShowError($"预览解码失败：{exception.Message}")).ConfigureAwait(false);
        }
    }

    private void DeletePreviewFiles()
    {
        foreach (var file in _previewFiles)
        {
            try { File.Delete(file); } catch { }
        }
        _previewFiles.Clear();
    }
}
