
# IceHaloStacker

堆栈固定机位拍摄的冰晕延时，进行平均值 / 最大值堆栈、节点式处理、实时预览与延时导出。

## 当前架构（v0.9.6.7）

- `icehalostack.py` 只保留兼容入口、公开符号转发和程序启动。
- `ihs/` 承载可复用的图像、堆栈、节点、曝光/WB、性能和输出核心。
- `ihs/services/` 提供与 UI 无关的处理服务接口：图像处理/预览、分组堆栈、原子导出，以及统一的进度与取消契约。
- `ihs/ui/` 承载主窗口、堆栈延时窗口、节点窗口、曝光/WB 工作区、外观和存储窗口。
- `tests/` 通过核心行为测试和 UI 契约测试保护拆分过程中的既有行为。

入口文件中的兼容导出是刻意保留的：旧版脚本仍可通过 `import icehalostack` 访问原有名称，新的代码应直接依赖 `ihs` 下的具体模块。

### UI 解耦服务边界

服务只接收普通数据、帧解码器和回调，不创建窗口、不读取 Tk 变量，也不负责线程调度。PySide6、WinUI 3 或现有 Tk 界面都可以在自己的工作线程中调用同一组服务：

```python
from ihs.services import (
    CancellationSource, ImageProcessingService, PipelineRequest,
    ProgressEvent, StackRequest, StackService,
)

cancel = CancellationSource()
events: list[ProgressEvent] = []
processor = ImageProcessingService(progress=events.append, cancellation=cancel)
result = processor.process(PipelineRequest(image, config, curve_points=curves))

stacker = StackService(progress=events.append, cancellation=cancel)
masters = stacker.stack(StackRequest(((0, 1, 2),), method="mean"), decoder)
```

`CancellationSource`、`ProgressEvent`、`PipelineRequest`、`PreviewRequest`、`StackRequest` 和 `ExportRequest` 是跨 UI 的稳定数据契约。现有 Tk 工作区仍保留原有调度和状态管理，后续迁移可按窗口逐步替换为这些服务调用。

`TimelapseWindow` 和 `NodeWindow` 的批处理已经接入 `ImageProcessingService`：Tk 线程、队列、性能监控、Shared Node DAG 和 Async Output 生命周期保持原样，单帧像素处理通过服务调用完成。`ihs.services.ipc.AsyncJsonLineHost` 提供本地 JSON-lines 子进程接口（固定 UTF-8）：每行一个请求，先立即确认 `start`，随后按 `task_id` 推送 progress/result，并持续接受 `cancel`；同步 `JsonLineHost` 仍保留给简单脚本调用。

例如，WinUI 3 可发送以下请求启动一次文件处理（路径和参数均为 JSON）：

```json
{"id":1,"method":"process_file","params":{"input_path":"D:/frames/001.tif","output_path":"D:/out/001.png","config":{"stretch":true,"stretch_strength":8.0,"stretch_black":0.0},"format":"PNG 8-bit"}}
```

异步协议示例：

```json
{"id":"req-1","method":"start","params":{"task_id":"task-42","operation":"process_file","params":{"input_path":"D:/frames/001.tif","output_path":"D:/out/001.png","config":{"stretch":true}}}}
{"id":"req-2","method":"cancel","params":{"task_id":"task-42"}}
```

任务完成或取消时会收到 `{"type":"result","task_id":"task-42",...}`。当前取消粒度受底层 NumPy/编解码步骤限制，宿主仍应允许 worker 安全退出。

客户端闭环可直接使用 `ihs.services.ipc_client.IpcClient`：它负责启动子进程、匹配 `request_id`、分发任务事件，并在 `close()` 时安全回收子进程。`start_task()` 只等待启动确认，长任务通过 `wait_task(..., on_event=...)` 或 `poll_event()` 消费。

```python
from ihs.services import IpcClient

with IpcClient(cwd=project_root) as client:
    client.ping()
    task_id = client.start_task("process_file", params, task_id="task-42")
    result = client.wait_task(task_id, on_event=render_progress)
```

## v0.9.6.6 Windows 异步输出文件锁修复

- 序列帧使用每个任务唯一的临时文件，避免多实例或重试任务争用同一 `.ihs_tmp` 文件。
- Windows Defender、缩略图和索引服务短暂占用文件时，原子替换会渐进重试，不再立即中止整批导出。

## v0.9.6.5 白平衡粉绿闪烁修复

- 白平衡分析改为 4x4 空间分区等权中性样本统计，降低画面内容移动对色温/色调测量的干扰。
- 在 Temperature/Tint 二维色度空间联合清理和平滑，不再独立处理 R/G 与 B/G 导致绿—洋红误差叠加。
- 白平衡修正使用色度向量整体限幅，避免修正到达上限时变色。
- 独立去闪、曝光平滑、关键帧和累计再次平滑保持可用。

## v0.9.6.2 移除可变字体选项

- 从“设置 → 界面字体”、字体候选表和字体解析路径中移除该可变字体选项。
- 保留“等线”“微软雅黑 UI”和“系统默认”三个字体选项。
- 旧版配置如果仍保存已经移除的字体键，启动时会安全回退到“系统默认”，不会再加载该字体。
- Regular 字重约束继续应用于 Tk 命名字体、ttk 样式、显式控件字体和 Canvas 文字。

## v0.9.6.1 英文文字载体完整审计与 Regular 字体验证

- 修复节点延时工作区的流程列表数据项；英文界面下自动生成的“流程 1 / 流程 2 / 副本”现在显示为 `Flow 1 / Flow 2 / Copy`，切回中文可无损恢复。
- 修复性能与内存面板的“详情…”按钮、详情窗口标题、实时 RAM/Cache/DAG/Output 状态及节点画布说明的英文显示。
- 只读下拉框新增显示层双向本地化：用户看见英文选项，内部仍保留原有中文枚举值，避免影响堆栈、通道和输出逻辑。
- 运行时遍历主界面、节点工作区与详情窗口的标题、菜单、控件、StringVar、Listbox、Combobox、Notebook、Treeview 和 Canvas，共检查 507 条可见文本记录，英文残留中文为 0。
- 逐控件读取 Tk 实际字体属性；非 Regular（bold/semibold）字体数量为 0。

## v0.9.6.0 深浅主题、全局中英文与 Regular 字体

- “设置 → 界面设置”集中提供浅色/深色主题、中文/English 和界面字体选择，修改后立即同步到已经打开的所有窗口。
- 深色主题使用深色背景、深色输入区域和白色文字；浅色主题使用浅色背景、白色输入区域和黑色文字，并为 Windows 标题栏同步深浅外观。
- 界面语言支持运行时双向切换。中文模式保持原有中文文本；English 模式覆盖主界面、菜单、设置、曝光/白平衡工作区、标签页、表头、画布文字和动态状态标签。
- 主题、语言和字体都保存在本机 `settings.json`，重新启动后自动恢复。
- 所有 Tk 命名字体、ttk 样式、显式控件字体和 Canvas 文字统一强制为 Regular。

## v0.9.5.9 关键帧自动保存与累计再次平滑

- 已经标记为关键帧的帧会在调整曝光、色温或色调时自动保存数值；切换到其他帧再返回时保持刚才的调整。
- 普通帧不会因为误碰滑块而自动变成关键帧，仍需使用“设为 / 更新关键帧”明确创建。
- 首次应用平滑过渡后可点击“再次平滑当前结果”，每次点击都以上一轮完成结果为输入继续累计平滑，并显示累计次数。
- “再次平滑”与单轮内的“多遍平滑”相互独立；再次平滑会固定现有关键帧的目标值，不改变用户已经完成的关键帧调色。

## v0.9.5.8 平滑工作区预览缩放与参数页滚动

- 播放期间的内存缩略图会按预览区域主动放大，最大化窗口时不再缩成中央小图。
- 曝光 / 白平衡预览支持鼠标滚轮缩放、按住左键拖拽平移，按 `Z` 回到 Fit，交互与堆栈延时预览一致。
- 右侧关键帧、平滑、修正范围和分析区域合并为可滚动参数页；窗口未最大化时也能用滚轮访问底部参数。

## v0.9.5.7 应用关键帧并预览全序列平滑过渡

- 平滑区域新增“应用关键帧并生成平滑过渡”按钮。
- 应用时会包含当前关键帧尚未再次点击保存的最后一次调整，并根据关键帧位置插值所有非关键帧。
- 只要关键帧包含曝光或白平衡调整，应用按钮会自动启用对应的曝光/WB修正通道。
- 应用后预览模式自动切换为“平滑后”；拖动时间轴、点击帧列表或播放时可查看每一帧最终过渡效果。
- 应用后的关键帧与非关键帧统一使用最终 Correction Table，不再混用临时关键帧直调预览。
- 修改关键帧或平滑参数后会明确提示重新应用。

## v0.9.5.6 平滑工作区滑块双击复位

- 双击当前关键帧的“曝光 EV”滑块恢复 `0.0 EV`。
- 双击当前关键帧的“色温（相对）”或“色调（相对）”滑块恢复 `0`。
- 双击“平滑力度”滑块恢复默认值 `50`。
- 复位后立即刷新数值框、预览、平滑曲线与修正表。

## v0.9.5.5 关键帧列表蓝点修复

- 帧列表最左侧作为关键帧标记栏：关键帧显示蓝色圆点，普通帧保持空白。
- 修复 Windows Treeview 原生缩进挤占窄列后、关键帧图片被完全裁掉的问题。
- 标记栏加宽并使用带深蓝轮廓的高 DPI 圆点，选中行处于蓝色背景时仍可辨认。
- 生成、添加、取消和重置关键帧后，标记栏会随关键帧集合自动刷新。

## v0.9.5.4 全屏输入框与分析窗口修复

- 加宽“关键帧数量”和“多遍平滑遍数”输入框，数值居中并与上下箭头保留间距。
- 曝光/白平衡分析窗口改为非模态进度窗口；分析过程中仍可最大化、还原和操作后面的平滑工作区。
- 分析窗口增加“取消分析”按钮；关闭整个平滑工作区时会安全通知后台分析停止。

## v0.9.5.3 曝光 / 白平衡工作区响应性修复

- 修复打开平滑工作区时窗口空白并被 Windows 标记为“未响应”的问题。
- 切断帧列表“程序选中 → 选择事件 → 刷新预览 → 再次选中”的无限反馈循环。
- 工作区控件先完成绘制，随后分批建立和更新全帧列表，填表期间仍可正常处理窗口消息。
- 素材签名检查不再在 Tk 主线程逐文件读取磁盘元数据。
- 长序列曲线按画布可见像素抽样，避免向 Tk 一次传入过多坐标。
- 曝光/白平衡分析、关键帧和平滑修正算法保持不变，源文件仍为只读。

## v0.9.5.2 Keyframe-guided Exposure / White Balance Smoothing Workspace

本版把曝光 / 白平衡平滑工作区进一步改成关键帧驱动的交互方式：

- 工作区使用普通独立窗口，不再作为 transient 工具窗，因此 Windows 标题栏可正常使用最小化、最大化/还原和关闭。
- 右上角新增“关键帧向导”，用户可指定 1–50 个关键帧，程序按整个序列均匀生成/重置关键帧。
- 新增全帧列表：每个输入 Frame 都有独立行；关键帧在最左侧显示蓝点。点击最左侧即可单独设置/取消关键帧，点击其他列则跳转到该帧预览。
- 当前关键帧仍可独立调整 Exposure EV、相对 Temperature、相对 Tint；新增“同步当前调整到全部关键帧”，可把当前关键帧的三项调整一次同步到其它关键帧。
- 新增 LRTimelapse 风格“平滑力度”滑条（0–100）。50 对应上一版的基础平滑尺度，增大时自动扩大有效时间半径。
- 新增“多遍平滑”，可设置 1–10 遍；每一遍继续对曝光、R/G、B/G 时间趋势做零相位 Gaussian 平滑。
- 曲线区现在同时显示三类曲线：灰色为原始测量、青色虚线为自动平滑趋势、彩色实线为经过关键帧约束后的最终目标。蓝色菱形/标记表示关键帧。
- 曝光与白平衡的最大修正、基础半径、应用强度和关键帧影响继续保留，作为更精细的控制。
- Frame 列表只在 Correction Table 或关键帧集合变化时批量刷新数值；播放/拖动时间轴只更新当前选中行，避免 500+ 帧序列播放时反复重绘整个列表。
- 所有 full-resolution 修正继续遵守 `Source(read-only) → Decode → Linear RGB → Exposure/WB Correction → RAM Frame Cache → Rolling Stack`，不保存平滑后中间帧、不修改输入文件。


## 当前包内容

- `icehalostack.py`：兼容入口与启动器；实际窗口实现位于 `ihs/ui/`
- `ihs/`：应用核心、图像处理、堆栈引擎、输出管线和 Tk UI 模块
- `ihs/services/`：UI 无关的处理、堆栈、导出服务和 JSON/IPC 适配层
- `winui/IceHaloStack.WinUI.Client/`：WinUI 3 可引用的 C# IPC 客户端和进度绑定模型
- `winui/IceHaloStack.WinUI/`：可编译的 WinUI 3 前端；当前包含单张处理、显式分组图像堆栈，以及基于同一分组模型的堆栈延时 TIFF 序列导出页面，均支持实时进度与按任务 ID 取消
- `tests/`：核心行为、UI 契约和回归测试
- `requirements_runtime.txt`：运行时依赖
- `requirements_build.txt`：打包依赖
- `launch_IceHaloStack.bat`：直接启动脚本
- `build_release.bat`：一键构建 Windows EXE
- `IceHaloStack.spec`：PyInstaller 打包配置
- `assets/icon/icehalostack.ico`：软件图标（ICO）
- `assets/icon/icehalostack_icon.png`：软件图标（PNG）

## 推荐仓库结构

- 本目录是当前唯一正式源代码目录；将本文件夹全部内容上传到 GitHub 仓库根目录。
- 根目录中的历史版本目录和旧压缩包不属于当前构建输入。
- `dist/IceHaloStack/` 下生成的内容适合打包到 GitHub Releases。

## 本地运行

双击 `launch_IceHaloStack.bat`。

WinUI 3 前端预览版可在已安装 .NET 8 SDK 的环境中运行。将环境变量
`ICEHALOSTACK_PYTHON` 指向已安装 IceHaloStack 依赖的 Python 解释器后，执行：

```powershell
dotnet run --project .\winui\IceHaloStack.WinUI\IceHaloStack.WinUI.csproj --arch x64
```

首次手动配置开发环境时，可以先安装运行时依赖：

```text
python -m pip install -r requirements_runtime.txt
```

## 构建 Windows EXE

双击 `build_release.bat`。

构建成功后，输出位置通常为：

```
dist/IceHaloStack/IceHaloStack.exe
```

## 图标设计说明

图标采用简洁冰晕主题：中心太阳、22° 晕环、两侧幻日、下方弧线提示大气光学结构。

## v0.9.4.18a performance core

Node Stack Timelapse now shares the optimized stack engine with the traditional timelapse path. Sliding/centered Mean uses rolling updates, cumulative Mean/Maximum uses a single incremental pass, and intermediate stack masters remain RAM-only with no disk cache.


## v0.9.4.18b Memory Manager

- 实时显示系统总 RAM、已用 RAM、可用 RAM，以及 IceHaloStack 当前工作集。
- RAM Budget 支持 `Auto` / `Manual`，Manual 可直接指定 GB 上限；批量任务开始时锁定该预算。
- 性能策略：Memory Saver / Balanced / Maximum Performance。
- Sliding / Centered Mean 使用受 RAM Budget 约束的 RAM-only LRU Frame Cache，窗口帧可直接复用。
- 单线程 RAW Prefetch 会在当前 Master 进入节点处理时预解码下一窗口的新帧。
- Memory Pressure Protection 会在系统可用 RAM 或软件工作集接近限制时自动减少缓存、停止预读取。
- **Disk Cache 始终 OFF**：decoded RAW、Rolling Master、Frame Cache 均不会为了加速写到系统盘。RAM 不足时退化为重新解码，而不是落盘。
- 传统延时与节点延时继续共用同一 Rolling Stack / Memory Cache 核心。


## v0.9.4.18c Shared Node DAG + Manual RAM Slider + HiDPI

- Manual RAM Budget 现在同时支持可拖拽滑条和直接输入 GB；两种输入方式共享同一个值，并按系统安全预留自动限制最大值。
- Auto / Manual 切换时，Manual 控件会自动启用/禁用；批量任务仍在开始时锁定 RAM Budget。
- Node Stack Timelapse 新增 Shared Node DAG：多条输出流程中，上游链和当前节点参数完全相同的阶段只计算一次。
- 任意参数发生变化都会自动形成独立分支，不会错误共享。
- Shared Node DAG 缓存仅存在当前 Master 的 RAM 中；达到 RAM Budget / 系统内存压力时会放弃缓存并重新计算，绝不写入硬盘。
- 性能面板显示 Shared DAG Hit / Compute / RAM Peak / Budget Skip。
- Windows 启用 Per-Monitor DPI Awareness V2，并按实际显示器 DPI 配置 Tk scaling，改善高 DPI 屏幕中文字和 Canvas 节点文字发糊的问题。


## v0.9.4.18d Async Output Pipeline

- Final sequence frames are encoded/written by a dedicated output worker while the main batch thread continues stacking and node processing.
- RAM-aware bounded queue: Memory Saver = 1, Balanced = 2, Maximum Performance = 3 queued frames.
- Backpressure prevents the writer queue from growing without bound.
- Processing and Writing progress bars are shown separately, with output FPS and ETA.
- Atomic final-frame writes use a sibling `.ihs_tmp` file only during the active write, then rename it into place. This is not a persistent disk cache.
- Cancel stops new processing, releases queued unwritten frames, and allows the currently active file write to finish safely.
- Rolling Stack, RAM Frame Cache, Shared Node DAG and Async Output remain RAM-first; decoded RAW, stack masters and node caches are never spilled to disk.

## v0.9.4.18e Performance Monitor & Stability

- Performance Monitor 低开销记录批量任务的 Rolling Stack、RAW Decode、节点处理、输出准备、Output Queue 等待、最终文件编码/写盘和 FFmpeg 时间。
- 实时显示 Master 数、RAW Decode 次数、Frame Cache Hit Rate、Stack / Node / Write 累计耗时和 IceHaloStack Peak RAM。
- “性能详情”可随时查看完整统计；Node Timelapse 额外记录每类节点的计算耗时以及 Shared DAG Hit / Compute / Budget Skip。
- Stability Watchdog 监视最后有效活动时间：30 秒以上标记 Long operation，120 秒以上提示 Possible stall；仅诊断，不会强制杀死正在进行的长计算。
- 记录 Peak RSS、系统最低可用 RAM、Frame Cache Peak、Shared DAG Peak、Output Queue Peak 和内存压力事件。
- 可选“完成后保存性能报告”，关闭时不会创建任何性能文件；开启时只在最终输出目录写入很小的 JSON/TXT 诊断报告，不属于磁盘缓存。
- 完成、取消和错误路径都会释放 Performance Monitor、RAM Budget、Async Output 和 Frame Cache 引用，减少任务结束后状态残留。
- Disk Cache 继续保持 OFF；Performance Monitor 本身完全在 RAM 中工作。




## v0.9.4.18g Node Typography Fix
- Fixed ON/OFF state overlap with bilingual node labels under Windows HiDPI scaling.
- Node canvas now uses pixel-sized regular fonts and a larger separated state zone.
- Enforced regular font weight globally for Tk/ttk labels, buttons, tabs, LabelFrame captions, tree headings and menus.

## v0.9.4.18f UI Cleanup & Compact Layout

- 节点延时主界面改为“主界面简洁 + 详情单独展开”：RAM / DAG / Async Output / Performance / Stability 的长文本不再常驻左侧。
- Performance & Memory 主面板仅保留系统 RAM、IceHaloStack RAM、RAM 上限、Manual 滑条/输入框、策略和“详情…”按钮。
- 新增独立“性能与内存详情”窗口，实时显示 RAM Budget、Frame Cache、Shared Node DAG、Async Output、Memory Pressure、Performance Monitor 与 Stability。
- 参考堆栈摘要压缩为“预计输出 + Stack Engine”，移除中间 Master / Disk Cache 的说明段落。
- 节点画布长篇操作说明移到“节点画布操作…”弹窗；预览区移除常驻操作说明。
- Flow 历史说明文字从主界面移除，Undo / Redo 按钮本身继续保留快捷键提示。
- 主界面 Async Output 状态改为短格式，例如“写入：256/400 · 队列 2/2 · 1.72 fps”。
- 全程序显式 Segoe UI 字体统一为常规字重；标题可通过字号区分，但不再混用粗体/常规体。
- 保留 v0.9.4.18a–18e 的 Rolling Stack、RAM Manager、Shared DAG、Async Output、Performance Monitor、HiDPI 与 Zero Disk Cache 行为。


## v0.9.4.18h Global Regular Typography Audit

- 全程序字体策略升级为“仅 Regular”：所有应用控制的 Tk named fonts、ttk 控件样式和 Canvas 显式字体均强制 `weight=normal`。
- Windows 下统一优先使用 `Microsoft YaHei UI` 常规体，避免 Segoe UI 与中文 fallback 混用时出现视觉上“一部分更粗”的情况。
- 覆盖 Label、Button、Checkbutton、Radiobutton、Entry、Spinbox、Combobox、Notebook Tab、LabelFrame caption、Treeview heading、Menu、Listbox、节点 Canvas、预览 Canvas 与主要弹窗。
- Timelapse 与 Node Timelapse 创建后再次执行 Regular typography guard，防止 Windows native ttk theme 在 Toplevel 初始化后重新带入较重字重。
- 保留字号层级用于区分标题与正文，但字重统一为 Regular；不使用 Bold / Semibold。


## v0.9.4.18j Interface Font Selector

- 新增 `设置 → 界面字体`，可在运行中切换：等线、微软雅黑 UI、系统默认。
- 字体选择会立即应用到主界面、传统延时、节点延时、Canvas 节点/预览文字和后续新建窗口。
- 所有选项继续强制 Regular / normal 字重，不使用 Bold、Semibold 或 Demibold。
- 选择会保存到 `%LOCALAPPDATA%\IceHaloStack\settings.json`，下次启动自动恢复。该文件仅保存少量界面设置，不是图像/性能缓存。
- 软件不捆绑、下载或分享任何字体文件；若所选字体未安装，会保持当前字体并提示用户。

## v0.9.4.18i Single Stack UI Cleanup
- Removed persistent CUDA/backend diagnostic paragraphs from the single-stack panel.
- Removed persistent pause/recommendation paragraphs below live-stack controls.
- Kept backend selection, RAW decode workers and CUDA re-detection controls.
- Explicit CUDA re-detection now reports its result on demand instead of occupying the main UI.
- Moved detailed single-stack/performance guidance to Help.
- Retains the global Regular typography policy from v0.9.4.18h.


## v0.9.4.18k Realtime Node Preview Scheduler
- 420 px immediate current-node drag preview.
- 760 px complete-flow fast preview on release.
- 1600 px complete-flow HQ refinement after idle.
- Interactive preview is no longer blocked by HQ refinement.
- Node canvas redraw is suppressed during slider dragging.


## v0.9.4.18m Base Fast Path + Shared DAG Audit
- Base / 基础调色 now skips mathematically neutral HSL, Color Mixer, Color Grading, Detail, Optics and Calibration modules before any full-frame pixel conversion.
- Tone processing allocates only the masks required by controls that are actually non-zero.
- Color Mixer evaluates only adjusted color sectors instead of all eight sectors.
- Shared Node DAG signatures now contain only parameters actually read by each node, so irrelevant legacy cfg fields no longer break common-prefix reuse.
- Performance Monitor adds per-node compute count, average time and per-node DAG Hit/Compute audit.
- Windows process RAM measurement uses explicit 64-bit-safe K32GetProcessMemoryInfo / PSAPI signatures to fix the previous 0 B RSS display.
- All intermediate stack/node/cache data remain RAM-only; Disk Cache remains OFF.
