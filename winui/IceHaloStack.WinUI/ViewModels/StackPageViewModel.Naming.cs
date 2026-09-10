using System.Globalization;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class StackPageViewModel
{
    private bool TryApplyOutputNaming(out string error)
    {
        error = string.Empty;
        if (Groups.Count == 0)
        {
            error = "请先建立至少一个堆栈分组。";
            return false;
        }
        if (string.IsNullOrWhiteSpace(OutputDirectory))
        {
            error = "请先选择批量 TIFF 输出目录。";
            return false;
        }

        string directory;
        try
        {
            directory = Path.GetFullPath(OutputDirectory);
        }
        catch (Exception exception)
        {
            error = $"输出目录无效：{exception.Message}";
            return false;
        }
        if (!Directory.Exists(directory))
        {
            error = "输出目录不存在。请通过“选择目录…”选择一个现有文件夹。";
            return false;
        }

        try
        {
            var used = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var group in Groups)
            {
                var stem = BuildOutputStem(group);
                group.OutputPath = MakeUniqueTiffPath(directory, stem, used);
            }
            return true;
        }
        catch (Exception exception)
        {
            error = $"文件命名规则无效：{exception.Message}";
            return false;
        }
    }

    private string BuildOutputStem(StackGroupItem group)
    {
        var pattern = Path.GetFileNameWithoutExtension(OutputFileNamePattern?.Trim() ?? string.Empty);
        if (string.IsNullOrWhiteSpace(pattern))
            throw new InvalidOperationException("请输入文件命名规则。");

        var replaced = OutputTokenPattern.Replace(pattern, match =>
        {
            var name = match.Groups["name"].Value.ToLowerInvariant();
            var format = match.Groups["format"].Success ? match.Groups["format"].Value : null;
            return name switch
            {
                "group" => FormatNumber(group.GroupNumber, format),
                "start" => FormatNumber(group.StartFrame, format),
                "end" => FormatNumber(group.EndFrame, format),
                "center" => FormatNumber(group.CenterFrame, format),
                "count" => FormatNumber(group.FrameCount, format),
                "method" => StackMethod,
                "name" or "material" => string.IsNullOrWhiteSpace(group.MaterialName)
                    ? $"素材_{group.GroupNumber:000}"
                    : group.MaterialName.Trim(),
                "window" => FormatNumber(group.FrameCount, format),
                _ => throw new InvalidOperationException($"不支持的标记：{{{name}}}"),
            };
        });

        var invalid = Path.GetInvalidFileNameChars();
        var sanitized = new string(replaced.Select(character => invalid.Contains(character) ? '_' : character).ToArray())
            .Trim(' ', '.');
        if (string.IsNullOrWhiteSpace(sanitized))
            throw new InvalidOperationException("命名规则没有生成有效的文件名。");
        return sanitized;
    }

    private static string FormatNumber(int value, string? format)
        => string.IsNullOrWhiteSpace(format)
            ? value.ToString(CultureInfo.InvariantCulture)
            : value.ToString(format, CultureInfo.InvariantCulture);

    private static string FormatNumber(double value, string? format)
        => string.IsNullOrWhiteSpace(format)
            ? value.ToString("0.##", CultureInfo.InvariantCulture)
            : value.ToString(format, CultureInfo.InvariantCulture);

    private static string MakeUniqueTiffPath(string directory, string stem, ISet<string> used)
    {
        var suffix = 1;
        while (true)
        {
            var fileName = suffix == 1 ? $"{stem}.tif" : $"{stem}_{suffix:000}.tif";
            var path = Path.Combine(directory, fileName);
            if (used.Add(path) && !File.Exists(path))
                return path;
            suffix++;
        }
    }

    private void RefreshOutputPathPreview()
    {
        try
        {
            if (Groups.Count == 0 || string.IsNullOrWhiteSpace(OutputDirectory))
            {
                OutputPathPreview = "选择输出目录后可批量生成 TIFF 文件名。";
                return;
            }
            var directory = Path.GetFullPath(OutputDirectory);
            OutputPathPreview = Path.Combine(directory, BuildOutputStem(Groups[0]) + ".tif");
        }
        catch (Exception)
        {
            OutputPathPreview = "命名规则或输出目录尚未有效。";
        }
    }
}
