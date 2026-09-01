IceHaloStack v0.9.4.7 使用说明

【v0.9.4.7 彩色浮雕 / Color Emboss】
- 默认浮雕改为 Color Emboss：平坦区域保持原图 RGB/色彩，不再整幅变成黑白灰。
- 保留 Gray Emboss：需要经典 Photoshop 风格中性灰浮雕时可切换。
- Emboss 新增 Blend Mode：Normal / Overlay / Soft Light / Linear Light。
- Emboss 新增 Opacity 0–100%。
- 单图编辑、旧延时面板、节点工作流三条路径使用同一套 Emboss 数学与预览逻辑。
- Angle Dial、滑块、数值框继续联动；预览仍按代理图比例缩放 Height，避免预览与最终应用强度不一致。

==============================================

本版仍以 v0.9.4 为图像处理基线；没有加入后续 GPU 版本的处理架构。
继续保留 Smart Launcher / EXE 构建能力；v0.9.4.5 重点修复 USM/Emboss 预览一致性并加入 Photoshop 风格角度圆盘。

推荐 Python：
- Python 3.14 64-bit（优先）
- Python 3.13 64-bit
- Python 3.12 64-bit

直接运行：
1. Windows 安装上述任意一种 64 位 Python。
2. 解压程序。
3. 双击 launch_IceHaloStack.bat。

启动器会自动：
- 优先寻找 3.14，其次 3.13、3.12；
- 创建 IceHaloStack 私有 venv；
- pip 缺失时自动 ensurepip 修复；
- 安装缺少的 NumPy / Pillow / tifffile / rawpy / OpenCV / imageio-ffmpeg；
- 检查 Tkinter、LibRaw、FFmpeg；
- 显示完整环境状态；
- 启动 IceHaloStack。

私有环境位置：
%LOCALAPPDATA%\IceHaloStackRuntime0942\venv

环境诊断：
双击 check_environment.bat

环境损坏时：
双击 repair_environment.bat
它只会删除并重建 IceHaloStack 自己的 venv，不会删除系统 Python。

生成独立 EXE：
双击 build_release.bat
成功后：
dist\IceHaloStack\IceHaloStack.exe

发布给别人时请复制整个 dist\IceHaloStack 文件夹，而不是只复制 EXE。


【v0.9.4.3 小屏幕/全局滚轮】
主窗口全部调节页、节点延时左侧整栏、节点参数窗口、Flow/Base Curves 均可用鼠标滚轮滚动。节点画布：滚轮上下、Shift+滚轮横向、Ctrl+滚轮缩放。


【v0.9.4.5 USM / Emboss 预览与交互】
- USM Radius、High Pass Radius、Emboss Height 在预览代理上按缩放比例换算，避免预览比最终应用明显更重。
- Detail 页：拖动时快速代理，松开后高精度代理；代理缓存减少重复缩图。
- Node Timelapse：HQ 参考预览最长边提高到约 2600。
- Emboss 改为中性灰浮雕主体 + 边缘保留原图颜色。
- Emboss Angle 同时支持数值框、蓝色滑块、圆形 Angle Dial；三者联动。


【v0.9.4.5 视频编码修复】
H.264/ProRes 编码会自动将奇数宽高补至最近偶数尺寸（最多 1 像素黑边），图像序列尺寸不变。
如果旧任务已完成图像处理、只在 FFmpeg 阶段失败，运行 repair_failed_video_export.bat，选择失败的 IceHaloStack_Timelapse 输出目录即可直接重新编码，无需重新堆栈。