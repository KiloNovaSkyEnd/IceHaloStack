using Microsoft.UI.Xaml.Controls;

namespace IceHaloStack_WinUI.Controls;

public sealed partial class ClassicCommandStrip
{
    private static readonly IReadOnlyDictionary<string, string> English = new Dictionary<string, string>
    {
        ["文件"] = "File", ["编辑"] = "Edit", ["堆栈"] = "Stack", ["堆栈延时"] = "Stack Timelapse",
        ["线性处理"] = "Linear Processing", ["调整"] = "Adjustments", ["滤镜"] = "Filters", ["视图"] = "View",
        ["设置"] = "Settings", ["帮助"] = "Help", ["添加图像…"] = "Add Images…", ["添加文件夹…"] = "Add Folder…",
        ["打开单张 TIFF / 图片进入编辑…"] = "Open TIFF / Image for Editing…", ["保存当前预览…"] = "Save Current Preview…",
        ["选择输出目录…"] = "Choose Output Folder…", ["清空工程"] = "Clear Project", ["退出"] = "Exit",
        ["撤销"] = "Undo", ["重做"] = "Redo", ["全选帧"] = "Select All Frames", ["移除所选帧"] = "Remove Selected Frames",
        ["复位全部处理参数"] = "Reset All Processing", ["开始堆栈"] = "Start Stack", ["暂停 / 继续"] = "Pause / Resume",
        ["使用当前结果并停止"] = "Use Current Result and Stop", ["取消当前任务"] = "Cancel Current Task",
        ["节点工作流…"] = "Node Workflow…", ["Auto Stretch 预览（不修改数据）"] = "Auto Stretch Preview (display only)",
        ["Asinh 拉伸 → 非线性…"] = "Asinh Stretch → Nonlinear…", ["基础调整 / Camera Raw 风格"] = "Basic / Camera Raw Style",
        ["通道混合器"] = "Channel Mixer", ["USM 锐化 / 高反差保留 / 浮雕"] = "USM / High Pass / Emboss",
        ["曲线 / 对比度"] = "Curves / Contrast", ["Auto Stretch 预览"] = "Auto Stretch Preview", ["适合窗口"] = "Fit to Window",
        ["界面主题"] = "UI Theme", ["跟随系统"] = "System", ["浅色"] = "Light", ["深色"] = "Dark",
        ["界面字体"] = "UI Font", ["等线"] = "DengXian", ["微软雅黑 UI"] = "Microsoft YaHei UI",
        ["微软雅黑"] = "Microsoft YaHei", ["系统默认"] = "System Default", ["界面语言"] = "Language", ["中文"] = "Chinese",
        ["单独堆栈与性能说明…"] = "Stack & Performance Guide…", ["存储与缓存管理…"] = "Storage & Cache Manager…",
        ["关于 IceHaloStack"] = "About IceHaloStack", ["添加图像"] = "Add Images", ["添加文件夹"] = "Add Folder",
        ["移除"] = "Remove", ["暂停/继续"] = "Pause/Resume", ["使用当前"] = "Use Current", ["取消"] = "Cancel",
        ["输出目录"] = "Output Folder",
    };

    public void ApplyLanguage(string language)
    {
        var english = string.Equals(language, "en", StringComparison.OrdinalIgnoreCase);
        foreach (var item in ClassicMenu.Items)
        {
            item.Title = Translate(item.Title, english);
            TranslateMenuItems(item.Items, english);
        }
        foreach (var command in ClassicToolbar.PrimaryCommands.OfType<AppBarButton>())
            command.Label = Translate(command.Label, english);
    }

    private static void TranslateMenuItems(IEnumerable<MenuFlyoutItemBase> items, bool english)
    {
        foreach (var item in items)
        {
            if (item is MenuFlyoutItem leaf) leaf.Text = Translate(leaf.Text, english);
            else if (item is MenuFlyoutSubItem sub)
            {
                sub.Text = Translate(sub.Text, english);
                TranslateMenuItems(sub.Items, english);
            }
        }
    }

    private static string Translate(string text, bool english)
    {
        if (english) return English.TryGetValue(text, out var translated) ? translated : text;
        return English.FirstOrDefault(pair => pair.Value == text).Key ?? text;
    }
}
