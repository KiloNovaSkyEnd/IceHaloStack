from __future__ import annotations
import os, sys, threading, traceback, math, copy, time, subprocess, re, json, shutil, tempfile, gc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue, Empty, Full
from collections import OrderedDict, Counter, deque

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = 'IceHaloStack'
VERSION = '0.9.6.7'
RAW_EXTS = {'.arw','.cr2','.cr3','.nef','.nrw','.raf','.rw2','.orf','.pef','.dng','.srw','.3fr','.erf','.kdc','.mos','.mrw','.raw','.rwl','.sr2'}
RASTER_EXTS = {'.tif','.tiff','.png','.jpg','.jpeg','.bmp'}
ALL_EXTS = RAW_EXTS | RASTER_EXTS

# Typography policy: every application-controlled text element uses REGULAR weight.
# The user can select the UI family from Settings.  No font files are bundled;
# IceHaloStack only uses fonts already installed on the operating system.
FONT_CHOICES = OrderedDict([
    ('dengxian', '等线'),
    ('yahei_ui', '微软雅黑 UI'),
    ('system', '系统默认'),
])
THEME_CHOICES = OrderedDict([('light','浅色'),('dark','深色')])
LANGUAGE_CHOICES = OrderedDict([('zh_CN','中文'),('en','English')])


def _settings_file_path():
    """Small persistent UI-settings file. This is configuration, never image/cache data."""
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME') or (Path.home() / '.config'))
    return base / 'IceHaloStack' / 'settings.json'


def _load_ui_setting(name,default,valid):
    try:
        data=json.loads(_settings_file_path().read_text(encoding='utf-8'))
        value=str(data.get(name,default))
        return value if value in valid else default
    except Exception:
        return default


def _load_ui_font_preference():
    """Load a supported family; obsolete/unknown saved choices use System Default."""
    try:
        data=json.loads(_settings_file_path().read_text(encoding='utf-8'))
        value=str(data.get('ui_font','dengxian'))
        return value if value in FONT_CHOICES else 'system'
    except Exception:
        return 'dengxian'


def _save_ui_setting(name,value):
    try:
        path=_settings_file_path(); path.parent.mkdir(parents=True,exist_ok=True)
        data={}
        if path.exists():
            try:data=json.loads(path.read_text(encoding='utf-8'))
            except Exception:data={}
        data[name]=value
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,path)
        return True
    except Exception:
        return False


def _save_ui_font_preference(key):return _save_ui_setting('ui_font',key)


UI_FONT_PREFERENCE = _load_ui_font_preference()
UI_FONT_FAMILY = 'DengXian' if os.name == 'nt' else 'TkDefaultFont'
SYSTEM_UI_FONT_FAMILY = None
UI_THEME_PREFERENCE = _load_ui_setting('ui_theme','light',THEME_CHOICES)
UI_LANGUAGE = _load_ui_setting('ui_language','zh_CN',LANGUAGE_CHOICES)


# Exact translations cover primary application, Timelapse, node workflow and
# Exposure/WB workspace controls.  A conservative phrase fallback below also
# translates changing counts/status messages while leaving filenames and user
# content untouched.
EN_TRANSLATIONS = {
    '文件':'File','编辑':'Edit','堆栈':'Stack','延时':'Timelapse','线性处理':'Linear Processing','调整':'Adjustments','滤镜':'Filters','视图':'View','设置':'Settings','帮助':'Help',
    '添加图片 / RAW...':'Add Images / RAW...','添加文件夹...':'Add Folder...','打开单张 TIFF / 图片进入编辑...':'Open TIFF / Image for Editing...','保存当前图像...':'Save Current Image...','清空工程':'Clear Project','退出':'Exit',
    '撤销':'Undo','重做':'Redo','全选帧':'Select All Frames','移除所选帧':'Remove Selected Frames','开始线性堆栈':'Start Linear Stack','暂停 / 继续':'Pause / Resume','使用当前结果并停止':'Use Current Result and Stop','取消堆栈':'Cancel Stack','打开堆栈延时...':'Open Stack Timelapse...',
    '界面字体':'UI Font','界面主题':'UI Theme','界面语言':'Language','界面设置...':'Interface Settings...','浅色':'Light','深色':'Dark','中文':'Chinese','等线':'DengXian','微软雅黑':'Microsoft YaHei','微软雅黑 UI':'Microsoft YaHei UI','系统默认':'System Default','关于 IceHaloStack':'About IceHaloStack','存储与缓存管理...':'Storage & Cache Manager...','单独堆栈与性能说明...':'Single Stack & Performance Guide...',
    '冰晕 RAW · 堆栈 · 处理':'Ice Halo RAW · Stack · Process','＋ RAW / 图片':'＋ RAW / Images','＋ 文件夹':'＋ Folder','▶ 开始堆栈':'▶ Start Stack','🎞 堆栈延时':'🎞 Stack Timelapse','⏸ 暂停':'⏸ Pause','▶ 继续':'▶ Resume','✓ 使用当前':'✓ Use Current','↶ 撤销':'↶ Undo','↷ 重做':'↷ Redo','导出':'Export','移除':'Remove',
    '图像预览':'Image Preview','预览导航':'Preview Navigation','适合窗口':'Fit to Window','堆栈完成后将在这里显示图像。':'The image will appear here after stacking.','等待导入冰晕延时序列':'Waiting for an ice-halo timelapse sequence','LINEAR · 尚未生成 Master':'LINEAR · Master not generated',
    '曝光 / 白平衡平滑':'Exposure / White Balance Smoothing','曝光 / 白平衡平滑工作区':'Exposure / White Balance Smoothing Workspace','曝光平滑':'Exposure Smoothing','白平衡平滑':'White Balance Smoothing','重新分析素材':'Re-analyze Footage','完成':'Done','关键帧向导':'Keyframe Wizard','关键帧数量':'Keyframe Count','生成 / 重置':'Generate / Reset','同步当前调整到全部关键帧':'Sync Current Adjustments to All Keyframes','帧 / Frames':'Frames','文件名':'Filename',
    '当前帧 / 关键帧':'Current Frame / Keyframe','当前帧是关键帧（调整自动保存）':'Current frame is a keyframe (edits auto-save)','当前帧不是关键帧（需先设为关键帧）':'Current frame is not a keyframe (set it first)','曝光 EV':'Exposure EV','色温（相对）':'Temperature (Relative)','色调（相对）':'Tint (Relative)','对比度':'Contrast','高光':'Highlights','阴影':'Shadows','白色色阶':'Whites','黑色色阶':'Blacks','设为 / 更新关键帧':'Set / Update Keyframe','取消关键帧':'Remove Keyframe',
    '去闪':'Deflicker','去闪 / 曝光 / 白平衡':'Deflicker / Exposure / White Balance','打开去闪与平滑工作区…':'Open Deflicker and Smoothing Workspace...','平滑':'Smoothing','平滑力度':'Smoothing Strength','多遍平滑':'Multi-pass Smoothing','遍数':'Passes','应用关键帧并生成平滑过渡':'Apply Keyframes and Generate Smooth Transition','再次平滑当前结果':'Smooth Current Result Again','平滑与修正范围':'Smoothing and Correction Range','高级去闪与分析设置（通常无需修改） ▸':'Advanced Deflicker and Analysis Settings (Usually Unnecessary) ▸','高级去闪与分析设置（通常无需修改） ▾':'Advanced Deflicker and Analysis Settings (Usually Unnecessary) ▾','去闪、平滑与修正范围':'Deflicker, Smoothing and Correction Range','去闪检测半径':'Deflicker Detection Radius','去闪强度':'Deflicker Strength','曝光基础半径':'Exposure Base Radius','曝光应用强度':'Exposure Strength','曝光最大修正':'Maximum Exposure Correction','WB 基础半径':'WB Base Radius','WB 应用强度':'WB Strength','WB 最大通道修正':'Maximum WB Channel Correction','关键帧影响':'Keyframe Influence','分析区域':'Analysis Region','自动有效区域':'Automatic Valid Region','全画面':'Full Frame','自定义 ROI':'Custom ROI',
    '原始':'Original','平滑后':'Smoothed','修正后':'Corrected','左右对比':'Side-by-side','▶ 播放':'▶ Play','Ⅱ 暂停':'Ⅱ Pause','预览 FPS':'Preview FPS','平滑趋势':'Smooth Trend','关键帧目标':'Keyframe Target','白平衡 冷↔暖':'White Balance Cool↔Warm','白平衡 绿↔洋红':'White Balance Green↔Magenta','低分辨率播放预览':'Low-resolution Playback Preview','正在加载高分辨率静帧预览…':'Loading High-resolution Still Preview...','正在加载高级调色控件…':'Loading Advanced Color Controls...',
    '关键帧调整会自动保存；点击下方按钮生成全序列过渡':'Keyframe edits auto-save; use the button below to generate the full-sequence transition','当前调整尚未应用；普通帧需先设为关键帧才会保存':'Current edit is not applied; regular frames must be set as keyframes before they are saved',
    '参考堆栈':'Reference Stack','生成参考堆栈':'Generate Reference Stack','打开平滑工作区…':'Open Smoothing Workspace...','快速堆栈区间':'Quick Stack Range','起始帧':'Start Frame','结束帧':'End Frame','使用当前选中范围':'Use Current Selection','堆栈方式':'Stack Method','平均值 Mean':'Mean','最大值 Maximum':'Maximum','自动曝光归一化（实验性）':'Auto Exposure Normalization (Experimental)','第 1 步：生成参考堆栈':'Step 1: Generate Reference Stack','第 2 步 · 在参考图上搭建处理链':'Step 2 · Build Processing Chain on Reference','第 3 步 · 批量生成与视频输出':'Step 3 · Batch Generation and Video Output',
    '节点流程 / Flows':'Node Flows','＋ 新建':'＋ New','复制流程':'Duplicate Flow','删除流程：':'Delete Flow:','流程名称':'Flow Name','保存当前预设':'Save Current Preset','加载预设为新流程':'Load Preset as New Flow','批量导入预设':'Batch Import Presets','当前流程实时预览 / Live Preview':'Current Flow Live Preview','节点画布操作…':'Node Canvas Actions...','自动 U 字形排列 / Arrange U-Shape':'Arrange U-Shape Automatically','自动纵向排列 / Arrange Top-to-Bottom':'Arrange Top-to-Bottom Automatically','新建节点 / New Node':'New Node','删除节点 / Delete ':'Delete Node','应用 / Apply':'Apply','取消 / Cancel':'Cancel',
    '输出模式 / Export Mode':'Export Mode','序列 + 视频 / Sequence + Video · ':'Sequence + Video · ','仅序列 / Sequence Only · ':'Sequence Only · ','仅视频 / Video Only · ':'Video Only · ','禁用导出':'Disable Export','序列格式 / Sequence Format':'Sequence Format','视频格式 / Video Format':'Video Format','视频分辨率':'Video Resolution','命名模板':'Naming Template','开始批量生成':'Start Batch Generation','开始批量导出所有启用流程':'Export All Enabled Flows','保存性能报告 JSON/TXT':'Save Performance Report JSON/TXT',
    '基础':'Basic','细节':'Detail','曲线':'Curves','拉伸':'Stretch','输出':'Output','亮度':'Luminance','红色':'Red','绿色':'Green','蓝色':'Blue','色温':'Temperature','色调':'Tint','预览':'Preview','启用':'Enable','取消':'Cancel','关闭':'Close','删除':'Delete','复制':'Copy','打开':'Open','选择...':'Choose...','所有文件':'All Files',
    '当前程序目录':'Current Program Directory','当前 Python Runtime':'Current Python Runtime','旧版 Runtime：':'Legacy Runtime:','旧版 Build：':'Legacy Build:','Windows TEMP（总占用，仅显示）':'Windows TEMP (Total Usage, Display Only)','刷新统计':'Refresh Statistics','全选安全项':'Select All Safe Items','取消选择':'Clear Selection','清理所选':'Clean Selected','一键安全清理':'One-click Safe Cleanup','路径 / 状态':'Path / Status','类型 / Style':'Type / Style','占用':'Usage',
    '界面设置':'Interface Settings','外观':'Appearance','语言':'Language','字体':'Font','更改会立即应用到所有已打开窗口。':'Changes apply immediately to all open windows.','关闭设置':'Close Settings',
    'RAW 并行解码':'Parallel RAW Decode','USM 锐化':'USM Sharpen','细节滤镜 · 实时预览':'Detail Filters · Live Preview','启用即时预览':'Enable Instant Preview','启用浮雕':'Enable Emboss','启用高反差保留':'Enable High Pass','启用高反差保留曲线':'Enable High Pass Curve','帧刷新一次':'frames per refresh','打开 High Pass 曲线编辑器':'Open High Pass Curve Editor','输出通道':'Output Channels','参数归零':'Reset Parameters','参数归零 / 预设':'Reset Parameters / Presets','性能加速':'Performance Acceleration','✓ 使用当前结果':'✓ Use Current Result','单色':'Monochrome','固定三脚架':'Fixed Tripod','实时堆栈预览':'Live Stack Preview','常数 %':'Constant %','应用 Asinh 拉伸':'Apply Asinh Stretch','应用 High Pass':'Apply High Pass','应用 USM':'Apply USM','应用基础调整':'Apply Basic Adjustments','应用曲线':'Apply Curves','应用浮雕':'Apply Emboss','应用通道混合器':'Apply Channel Mixer','开始堆栈':'Start Stack','恢复 Linear Master':'Restore Linear Master','每':'Every','浮雕（Photoshop 风格）':'Emboss (Photoshop Style)','组合方式':'Combination Method','色彩噪声保护':'Chroma Noise Protection','角度 (°)':'Angle (°)','高度 (像素)':'Height (pixels)','计算后端':'Compute Backend','通道':'Channel','通道混合器':'Channel Mixer','重新检测 CUDA':'Detect CUDA Again','重置当前通道':'Reset Current Channel','重置全部通道':'Reset All Channels','高反差保留（PS 风格）':'High Pass (PS Style)','当前堆栈区间：1 - 1（0 帧）':'Current stack range: 1–1 (0 frames)','LINEAR · 尚未生成 Master':'LINEAR · Master not generated','Camera Raw 风格基础调整':'Camera Raw-style Basic Adjustments',
    'Auto Stretch 只是显示预览，不修改线性数据。\n“应用 Asinh”才真正转换到非线性。':'Auto Stretch affects display only and does not modify linear data.\n“Apply Asinh” performs the actual nonlinear conversion.',
    'Mean：逐帧平均，适合降低随机噪声；Maximum：逐像素逐通道保留所有帧中的最大值。':'Mean averages frames to reduce random noise; Maximum keeps the greatest per-pixel channel value across all frames.',
    'Photoshop Emboss 为推荐 PS 风格；Color Emboss 保留现有彩色模式；Gray Emboss 保留旧版灰色模式。':'Photoshop Emboss is the recommended PS-style mode; Color Emboss preserves color; Gray Emboss keeps the legacy neutral-gray mode.',
    '不进行几何对齐；适用于固定机位冰晕延时。':'No geometric alignment; intended for fixed-tripod ice-halo timelapses.',
    '你可以只堆栈序列中的某一段，例如 1–50、50–100，而不是一次性把全部帧都堆完。':'You can stack only part of the sequence, such as 1–50 or 50–100, instead of all frames at once.',
    '可选择输出通道，并可开启单色模式。极端正/负通道权重会放大色差噪声，因此默认开启“色彩噪声保护”；它只预处理通道色差，不直接模糊亮度。关闭后即为纯数学通道混合。':'Choose output channels and optional monochrome mode. Extreme channel weights can amplify chroma noise, so Chroma Noise Protection is enabled by default; it smooths chroma differences without blurring luminance.',
    '混合模式 / Opacity（仅“混合到原图”）':'Blend Mode / Opacity (Blend into Original only)',
    '真正的控制点曲线编辑器：支持 RGB / 红 / 绿 / 蓝 / 亮度。点击添加点，控制点可横向/纵向拖动；下方黑/白三角可直接调整输入端点。右键删除中间控制点。':'True control-point curve editor for RGB, Red, Green, Blue and Luminance. Click to add, drag to adjust, use the black/white triangles for endpoints, and right-click intermediate points to delete.',
    '这里统一对齐延时处理中的 Base / 基础调色逻辑：面向堆栈并拉伸后的 TIFF / Float 图像，不调用 Adobe Camera Raw。可用鼠标滚轮浏览完整面板。':'Matches the timelapse Base-adjustment pipeline for stacked and stretched TIFF/float images; Adobe Camera Raw is not used. Scroll to browse the full panel.',
    '高反差保留与浮雕默认关闭，只有在你主动开启后才会参与实时预览与应用。数值框支持双击后直接输入。向下滚动可看到完整浮雕参数。':'High Pass and Emboss are disabled by default and affect preview/output only when enabled. Double-click numeric fields to type values; scroll down for all Emboss settings.',
    '启用（只平滑通道色差，尽量保留亮度细节）':'Enable (smooth channel chroma only; preserve luminance detail)',
    '详情…':'Details...','详情...':'Details...','完整性能报告…':'Full Performance Report...','IceHaloStack · 性能与内存详情':'IceHaloStack · Performance & Memory Details','RAM 上限':'RAM Limit','策略':'Strategy','参考输出帧':'Reference Output Frame',
    '当前流程节点画布 / Node Canvas · 单击节点编辑参数':'Current Flow Node Canvas · Click a node to edit parameters','生成参考堆栈后，这里会显示当前流程的实时预览。':'The live preview of the current flow will appear here after generating a reference stack.','时间窗口已改变，请重新生成参考堆栈':'Time window changed; regenerate the reference stack','参考堆栈已失效':'Reference stack is outdated',
    '写入：空闲':'Writing: Idle','写入：完成':'Writing: Complete','写入：准备启动…':'Writing: Preparing...','写入：已取消':'Writing: Cancelled','写入：失败/已停止':'Writing: Failed / Stopped','第 1 步：生成参考堆栈':'Step 1: Generate Reference Stack','尚未生成参考堆栈':'Reference stack not generated',
    '当前堆栈区间：无可用帧':'Current stack range: no available frames','保存性能报告 JSON/TXT':'Save Performance Report JSON/TXT','缓存策略 / Cache Policy':'Cache Policy','中间 Master、RAW Decode Cache 与 Node Cache 仅驻留 RAM；Disk Cache = OFF。RAM 紧张时自动减少缓存或重新解码源文件。':'Intermediate Masters, RAW Decode Cache and Node Cache remain in RAM only; Disk Cache is OFF. When RAM is constrained, caches are reduced or source files are decoded again.',
    '新建流程':'New Flow','复制流程':'Duplicate Flow','节点操作':'Node Action','没有可撤回的节点操作':'No node action to undo','没有可重做的节点操作':'No node action to redo','已应用：':'Applied:','已撤回：':'Undone:','已重做：':'Redone:','可撤回':'Undo available','可重做':'Redo available',
    'Auto Stretch 预览（不修改数据）':'Auto Stretch Preview (Display Only)','Asinh 拉伸 → 非线性...':'Asinh Stretch → Nonlinear...','基础调整 / Camera Raw 风格':'Basic Adjustments / Camera Raw Style','高反差保留':'High Pass','浮雕':'Emboss','曲线 / 对比度':'Curves / Contrast',
    '滑动窗口（推荐：观察变化）':'Rolling Window (Recommended: Observe Changes)','中心窗口（按中央时刻理解）':'Centered Window (Centered on Time)','累计堆栈（观察信号生长）':'Cumulative Stack (Observe Signal Growth)','逐帧剔除（贡献分析）':'Leave-one-out Frames (Contribution Analysis)',
    '滤镜本体':'Filter Only','混合到原图':'Blend with Original','不生成视频':'No Video','原始分辨率':'Original Resolution','自定义':'Custom','Fill 裁切':'Fill / Crop','Fit 黑边':'Fit / Letterbox','Stretch 拉伸':'Stretch','只保存序列':'Sequence Only','只保存视频':'Video Only','同时保存序列+视频':'Sequence + Video',
    '窗口大小':'Window Size','步长':'Step','单击编辑 · Shift 拖拽连线 · 右键菜单 · Ctrl+滚轮缩放 · 100%':'Click to Edit · Shift-drag to Connect · Right-click Menu · Ctrl+Wheel to Zoom · 100%',
    'Frame Cache：空闲 · 批量任务开始后按 RAM Budget 动态启用':'Frame Cache: Idle · Enabled dynamically by RAM Budget when a batch starts','Shared Node DAG：空闲':'Shared Node DAG: Idle','Async Output：空闲 · 批量任务时启用 RAM-aware bounded queue':'Async Output: Idle · RAM-aware bounded queue is enabled during batch processing',
    '选择延时输出目录':'Choose Timelapse Output Folder','保存流程预设':'Save Flow Preset','加载流程预设为新流程':'Load Flow Preset as New Flow','批量导入流程预设':'Batch Import Flow Presets','IceHaloStack 流程预设':'IceHaloStack Flow Preset','选择冰晕延时序列':'Choose Ice-halo Timelapse Sequence','选择包含延时序列的文件夹':'Choose Folder Containing Timelapse Sequence','打开图像进入编辑':'Open Image for Editing','图像 / RAW':'Images / RAW','图像':'Images','导出当前图像':'Export Current Image','关于':'About','计算后端检测':'Compute Backend Detection','IceHaloStack 启动失败':'IceHaloStack Startup Failed',
}

EN_PHRASES = OrderedDict(sorted({
    '关键帧调整已自动保存':'Keyframe edit auto-saved','关键帧已改变':'Keyframes changed','平滑参数已改变':'Smoothing settings changed','分析区域已改变':'Analysis region changed','请重新应用过渡':'please apply the transition again','请应用平滑过渡':'please apply the smooth transition','需要重新分析':'analysis required','正在分析':'Analyzing','分析完成':'Analysis complete','分析失败':'Analysis failed','正在准备':'Preparing','正在处理':'Processing','正在生成':'Generating','正在应用':'Applying','正在计算':'Computing','正在编码':'Encoding','正在取消':'Cancelling','已取消':'Cancelled','已完成':'Completed','已应用':'Applied','已分析':'Analyzed','未分析':'Not analyzed','未启用':'Disabled','失败':'Failed','错误':'Error',
    '批量任务开始后按':'when a batch starts, based on','批量任务时':'during batch processing','动态启用':'dynamically enabled','可调范围':'adjustable range','有效上限':'effective limit','已用':'used','可用':'available','空闲':'idle','预计':'estimated','窗口大小':'window size','步长':'step','右键菜单':'right-click menu','单击编辑':'click to edit','拖拽连线':'drag to connect','滚轮缩放':'wheel to zoom','策略':'strategy',
    '再次平滑':'Additional smoothing','关键帧':'keyframe','白平衡':'white balance','曝光':'exposure','平滑':'smoothing','修正':'correction','当前帧':'current frame','帧':'frames','文件夹':'folder','文件':'file','图像':'image','输出':'output','输入':'input','预览':'preview','参数':'parameters','设置':'settings','界面':'interface','主题':'theme','语言':'language','字体':'font','浅色':'light','深色':'dark','完成':'done','取消':'cancel','启用':'enable','禁用':'disable','打开':'open','保存':'save','选择':'select','移除':'remove','自动':'automatic','当前':'current','结果':'result','范围':'range','数量':'count','强度':'strength','半径':'radius','模式':'mode','方式':'method','状态':'status','流程':'flow','节点':'node','序列':'sequence','视频':'video','性能':'performance','内存':'memory','缓存':'cache','曲线':'curves','基础':'basic','细节':'detail','帮助':'help','关于':'about','原始':'original','色温':'temperature','色调':'tint','亮度':'luminance','红色':'red','绿色':'green','蓝色':'blue','灰色':'gray','全画面':'full frame','自定义':'custom','保持不变':'unchanged',
}.items(),key=lambda kv:len(kv[0]),reverse=True))


def _contains_cjk(text):return bool(re.search(r'[\u3400-\u9fff]',str(text)))


def _translate_text(text,language=None):
    language=language or UI_LANGUAGE;text=str(text)
    if language!='en' or not text:return text
    if text in EN_TRANSLATIONS:return EN_TRANSLATIONS[text]
    text=re.sub(r'流程\s*(\d+)',lambda m:'Flow '+m.group(1),text)
    text=text.replace(' 副本',' Copy')
    # Prefer an already-supplied all-English side of bilingual labels.
    for line in text.splitlines():
        clean=line.strip()
        if clean and not _contains_cjk(clean) and re.search(r'[A-Za-z]',clean):return clean
        if '/' in clean:
            candidates=[part.strip() for part in clean.split('/') if part.strip()]
            candidates=[part for part in candidates if not _contains_cjk(part) and re.search(r'[A-Za-z]',part)]
            if candidates:return max(candidates,key=len)
    out=text
    for zh,en in EN_PHRASES.items():out=out.replace(zh,en)
    out=re.sub(r'(\d+)\s*frames',r'\1 frames',out)
    return out


def _tr(text):return _translate_text(text,UI_LANGUAGE)


def _translate_flow_list_item(text,language=None):
    """Translate generated flow names while preserving arbitrary user names."""
    language=language or UI_LANGUAGE;text=str(text)
    if language!='en':return text
    match=re.fullmatch(r'(?P<prefix>[●○]\s+\d+\s+)?流程\s*(?P<number>\d+)(?P<copies>(?:\s*副本)*)',text)
    if not match:return text
    copies=len(re.findall(r'副本',match.group('copies') or ''))
    return (match.group('prefix') or '')+'Flow '+match.group('number')+(' Copy'*copies)


THEME_PALETTES = {
    'light':{'bg':'#f3f3f3','panel':'#ffffff','field':'#ffffff','fg':'#111111','muted':'#5f6368','border':'#c7c7c7','button':'#f7f7f7','active':'#e7e7e7','select':'#0b65c2','selectfg':'#ffffff','trough':'#d9d9d9'},
    'dark':{'bg':'#202124','panel':'#292a2d','field':'#303134','fg':'#f1f3f4','muted':'#bdc1c6','border':'#5f6368','button':'#35363a','active':'#45464b','select':'#2f81f7','selectfg':'#ffffff','trough':'#4a4b50'},
}


def _set_windows_titlebar_dark(widget,dark):
    if os.name!='nt':return
    try:
        import ctypes
        widget.update_idletasks();hwnd=widget.winfo_id();value=ctypes.c_int(1 if dark else 0)
        for attr in (20,19):
            try:
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,attr,ctypes.byref(value),ctypes.sizeof(value))==0:break
            except Exception:pass
    except Exception:pass


def _configure_theme_styles(root,key):
    p=THEME_PALETTES.get(key,THEME_PALETTES['light']);st=ttk.Style(root)
    try:st.theme_use('clam')
    except Exception:pass
    common={'background':p['bg'],'foreground':p['fg'],'bordercolor':p['border'],'lightcolor':p['border'],'darkcolor':p['border'],'font':_ui_font(9)}
    try:st.configure('.',**common)
    except Exception:pass
    for name in ('TFrame','TLabel','TPanedwindow','TSeparator'):
        try:st.configure(name,background=p['bg'],foreground=p['fg'])
        except Exception:pass
    try:st.configure('TLabelframe',background=p['bg'],bordercolor=p['border'],relief='solid');st.configure('TLabelframe.Label',background=p['bg'],foreground=p['fg'],font=_ui_font(9))
    except Exception:pass
    for name in ('TButton','Toolbutton','TMenubutton'):
        try:
            st.configure(name,background=p['button'],foreground=p['fg'],bordercolor=p['border'],focuscolor=p['select'],font=_ui_font(9))
            st.map(name,background=[('active',p['active']),('pressed',p['select'])],foreground=[('disabled',p['muted']),('pressed',p['selectfg'])])
        except Exception:pass
    for name in ('TCheckbutton','TRadiobutton'):
        try:st.configure(name,background=p['bg'],foreground=p['fg'],indicatorcolor=p['field'],font=_ui_font(9));st.map(name,background=[('active',p['bg'])],foreground=[('disabled',p['muted'])],indicatorcolor=[('selected',p['select']),('active',p['active'])])
        except Exception:pass
    for name in ('TEntry','TSpinbox','TCombobox'):
        try:st.configure(name,fieldbackground=p['field'],background=p['field'],foreground=p['fg'],insertcolor=p['fg'],bordercolor=p['border'],arrowcolor=p['fg'],font=_ui_font(9));st.map(name,fieldbackground=[('readonly',p['field']),('disabled',p['bg'])],foreground=[('disabled',p['muted'])],selectbackground=[('focus',p['field']),('readonly',p['field'])],selectforeground=[('focus',p['fg']),('readonly',p['fg'])])
        except Exception:pass
    try:st.configure('Treeview',background=p['field'],fieldbackground=p['field'],foreground=p['fg'],bordercolor=p['border'],font=_ui_font(9));st.map('Treeview',background=[('selected',p['select'])],foreground=[('selected',p['selectfg'])]);st.configure('Treeview.Heading',background=p['button'],foreground=p['fg'],bordercolor=p['border'],font=_ui_font(9));st.map('Treeview.Heading',background=[('active',p['active'])])
    except Exception:pass
    try:st.configure('TNotebook',background=p['bg'],bordercolor=p['border']);st.configure('TNotebook.Tab',background=p['button'],foreground=p['fg'],font=_ui_font(9));st.map('TNotebook.Tab',background=[('selected',p['panel']),('active',p['active'])],foreground=[('selected',p['fg'])])
    except Exception:pass
    try:st.configure('TScale',background=p['bg'],troughcolor=p['trough'],bordercolor=p['border'],lightcolor=p['select'],darkcolor=p['select']);st.configure('Horizontal.TProgressbar',background=p['select'],troughcolor=p['trough'],bordercolor=p['border']);st.configure('Vertical.TScrollbar',background=p['button'],troughcolor=p['bg'],arrowcolor=p['fg'],bordercolor=p['border']);st.configure('Horizontal.TScrollbar',background=p['button'],troughcolor=p['bg'],arrowcolor=p['fg'],bordercolor=p['border']);st.configure('IHS.Vertical.TScrollbar',background=p['button'],troughcolor=p['trough'],bordercolor=p['border'],arrowcolor=p['fg'])
    except Exception:pass
    # Page scroll areas use one uninterrupted track and thumb. Native Clam
    # arrows divide a tall page scrollbar into several visual segments.
    try:st.layout('IHS.Vertical.TScrollbar',[('Vertical.Scrollbar.trough',{'sticky':'ns','children':[('Vertical.Scrollbar.thumb',{'expand':'1','sticky':'nswe'})]})])
    except Exception:pass
    _configure_checkbutton_checkmark(root,st,key,p)
    try:st.configure('Title.TLabel',background=p['bg'],foreground=p['fg'],font=_ui_font(16));st.configure('Sub.TLabel',background=p['bg'],foreground=p['muted'],font=_ui_font(9));st.configure('Primary.TButton',background=p['select'],foreground=p['selectfg'],font=_ui_font(10),padding=(16,8));st.map('Primary.TButton',background=[('active','#3b8eea' if key=='dark' else '#0958a8'),('pressed','#074b91')],foreground=[('disabled',p['muted'])]);st.configure('Stage.TLabel',background=p['bg'],foreground=p['fg'],font=_ui_font(9))
    except Exception:pass


def _configure_checkbutton_checkmark(root,style,key,p):
    """Replace the Clam X indicator with an explicit checkmark image."""
    try:
        element=f'IHS.{key}.Checkbutton.indicator'
        store=getattr(root,'_ihs_checkmark_images',{})
        if element not in style.element_names():
            size=16;off=tk.PhotoImage(master=root,width=size,height=size);on=tk.PhotoImage(master=root,width=size,height=size)
            off.put(p['field'],to=(0,0,size,size));on.put(p['select'],to=(0,0,size,size))
            for image in (off,on):
                image.put(p['border'],to=(0,0,size,1));image.put(p['border'],to=(0,size-1,size,size));image.put(p['border'],to=(0,0,1,size));image.put(p['border'],to=(size-1,0,size,size))
            # A two-pixel white ✓ that remains legible at normal/high DPI.
            for x,y in ((3,8),(4,9),(5,10),(6,11),(7,10),(8,9),(9,8),(10,7),(11,6),(12,5)):
                on.put('#ffffff',to=(x,y,x+2,min(size,y+2)))
            style.element_create(element,'image',off,('selected',on),sticky='w')
            store[element]=(off,on);root._ihs_checkmark_images=store
        def replace(nodes):
            out=[]
            for name,opts in nodes:
                opts=dict(opts)
                if 'children' in opts:opts['children']=replace(opts['children'])
                out.append((element if name.endswith('.indicator') else name,opts))
            return out
        style.layout('TCheckbutton',replace(style.layout('TCheckbutton')))
    except Exception:pass


def _install_combobox_selection_behavior(root):
    """Keep a chosen value readable instead of leaving its text blue-selected."""
    if getattr(root,'_ihs_combobox_behavior_installed',False):return
    root._ihs_combobox_behavior_installed=True
    def clear_selection(event):
        widget=getattr(event,'widget',None)
        if widget is None:return
        def finish():
            try:widget.selection_clear();widget.icursor('end')
            except Exception:pass
        try:widget.after_idle(finish)
        except Exception:pass
    try:root.bind_class('TCombobox','<<ComboboxSelected>>',clear_selection,add='+')
    except Exception:pass


def _theme_widget_tree(root,key):
    p=THEME_PALETTES.get(key,THEME_PALETTES['light']);known_ui_bgs={x[c] for x in THEME_PALETTES.values() for c in ('bg','panel','field','button','active','trough')}
    def visit(w):
        try:
            if isinstance(w,(tk.Tk,tk.Toplevel)):
                w.configure(background=p['bg']);_set_windows_titlebar_dark(w,key=='dark')
            elif isinstance(w,tk.Menu):w.configure(background=p['panel'],foreground=p['fg'],activebackground=p['select'],activeforeground=p['selectfg'],selectcolor=p['select'])
            elif isinstance(w,tk.Listbox):
                w.configure(background=p['field'],foreground=p['fg'],selectbackground=p['select'],selectforeground=p['selectfg'],highlightbackground=p['border'],highlightcolor=p['select'])
            elif isinstance(w,(tk.Text,tk.Entry,tk.Spinbox)):
                w.configure(background=p['field'],foreground=p['fg'],insertbackground=p['fg'],selectbackground=p['select'],selectforeground=p['selectfg'],highlightbackground=p['border'],highlightcolor=p['select'])
            elif isinstance(w,tk.Canvas):
                current=str(w.cget('background')).lower()
                if current in known_ui_bgs or current in ('systembuttonface','#d9d9d9','white','#ffffff') or getattr(w,'_ihs_scroll_target',None) is w:w.configure(background=p['bg'])
            for child in w.winfo_children():visit(child)
        except Exception:pass
    visit(root)
    try:
        menu_name=root.cget('menu')
        if menu_name:visit(root.nametowidget(menu_name))
    except Exception:pass


def _apply_ui_theme(root,key,persist=False):
    global UI_THEME_PREFERENCE
    key=key if key in THEME_CHOICES else 'light';UI_THEME_PREFERENCE=key
    try:
        p=THEME_PALETTES[key];root.tk_setPalette(background=p['bg'],foreground=p['fg'],activeBackground=p['active'],activeForeground=p['fg'],highlightColor=p['select'],selectBackground=p['select'],selectForeground=p['selectfg'])
    except Exception:pass
    _configure_theme_styles(root,key);_theme_widget_tree(root,key)
    if persist:_save_ui_setting('ui_theme',key)
    return True


def _translate_menu(menu,language):
    try:
        sources=getattr(menu,'_ihs_i18n_entries',{});end=menu.index('end')
        if end is None:return
        for i in range(int(end)+1):
            try:
                kind=menu.type(i)
                if kind=='separator':continue
                label=menu.entrycget(i,'label')
                if i not in sources:sources[i]=label
                menu.entryconfigure(i,label=_translate_text(sources[i],language))
                if kind=='cascade':
                    sub=menu.entrycget(i,'menu')
                    if sub:_translate_menu(menu.nametowidget(sub),language)
            except Exception:pass
        menu._ihs_i18n_entries=sources
    except Exception:pass


def _language_widget_tree(root,language):
    def localize_textvariable(w):
        if not isinstance(w,(tk.Label,ttk.Label)):return
        try:
            if hasattr(w,'_ihs_i18n_text_source_var'):
                source=w._ihs_i18n_text_source_var;proxy=w._ihs_i18n_text_proxy
            else:
                name=str(w.cget('textvariable') or '')
                if not name:return
                source=tk.StringVar(master=w,name=name);proxy=tk.StringVar(master=w)
                def sync(*_):
                    try:proxy.set(_translate_text(source.get(),UI_LANGUAGE))
                    except Exception:pass
                trace_id=source.trace_add('write',sync);w._ihs_i18n_text_source_var=source;w._ihs_i18n_text_proxy=proxy;w._ihs_i18n_text_trace=trace_id;w.configure(textvariable=proxy)
            proxy.set(_translate_text(source.get(),language))
        except Exception:pass
    def localize_flow_list(w):
        """Translate generated flow names stored as Listbox rows, not widget text."""
        if not isinstance(w,tk.Listbox) or not getattr(w,'_ihs_translate_flow_items',False):return
        try:
            size=int(w.size());sources=list(getattr(w,'_ihs_i18n_item_sources',()))
            if len(sources)!=size:sources=[w.get(i) for i in range(size)]
            selected=tuple(int(i) for i in w.curselection())
            try:active=int(w.index('active'))
            except Exception:active=selected[0] if selected else 0
            try:top=int(w.nearest(0))
            except Exception:top=0
            w.delete(0,'end')
            for source in sources:w.insert('end',_translate_flow_list_item(source,language))
            for i in selected:
                if 0<=i<size:w.selection_set(i)
            if size:
                w.activate(max(0,min(size-1,active)));w.see(max(0,min(size-1,top)))
            w._ihs_i18n_item_sources=sources
        except Exception:pass
    def localize_combobox(w):
        """Localize readonly choices without changing their semantic StringVar values."""
        if not isinstance(w,ttk.Combobox):return
        try:
            data=getattr(w,'_ihs_i18n_combobox',None)
            if data is None:
                values=tuple(str(v) for v in w.cget('values'))
                if not any(_contains_cjk(v) for v in values):return
                name=str(w.cget('textvariable') or '')
                if not name:return
                source=tk.StringVar(master=w,name=name);proxy=tk.StringVar(master=w)
                data={'source':source,'proxy':proxy,'values':values,'busy':False}
                def display_values():return tuple(_translate_text(v,UI_LANGUAGE) for v in data['values'])
                def from_source(*_):
                    if data['busy']:return
                    data['busy']=True
                    try:
                        raw=str(source.get());display=dict(zip(data['values'],display_values())).get(raw,_translate_text(raw,UI_LANGUAGE));proxy.set(display)
                    finally:data['busy']=False
                def to_source(*_):
                    if data['busy']:return
                    data['busy']=True
                    try:
                        shown=str(proxy.get());mapping=dict(zip(display_values(),data['values']));source.set(mapping.get(shown,shown))
                    finally:data['busy']=False
                data['source_trace']=source.trace_add('write',from_source);data['proxy_trace']=proxy.trace_add('write',to_source)
                w._ihs_i18n_combobox=data
            values=tuple(_translate_text(v,language) for v in data['values'])
            data['busy']=True
            try:
                if tuple(str(v) for v in w.cget('values'))!=values:w.configure(values=values)
                # Set this after ``values``: on Windows ttk, refreshing the values
                # list may reconnect the entry to its construction-time variable.
                if str(w.cget('textvariable'))!=str(data['proxy']):w.tk.call(w._w,'configure','-textvariable',str(data['proxy']))
                raw=str(data['source'].get());data['proxy'].set(dict(zip(data['values'],values)).get(raw,_translate_text(raw,language)))
            finally:data['busy']=False
        except Exception:pass
    def visit(w):
        try:
            if isinstance(w,(tk.Tk,tk.Toplevel)):
                title=w.title()
                if not hasattr(w,'_ihs_i18n_title'):w._ihs_i18n_title=title
                w.title(_translate_text(w._ihs_i18n_title,language))
            if isinstance(w,tk.Menu):_translate_menu(w,language)
            else:
                try:text=w.cget('text')
                except Exception:text=None
                if text is not None:
                    if not hasattr(w,'_ihs_i18n_source'):w._ihs_i18n_source=text
                    try:
                        translated=_translate_text(w._ihs_i18n_source,language)
                        if str(text)!=str(translated):w.configure(text=translated)
                    except Exception:pass
            localize_textvariable(w)
            localize_flow_list(w)
            localize_combobox(w)
            if isinstance(w,ttk.Notebook):
                sources=getattr(w,'_ihs_i18n_tabs',{})
                for tab in w.tabs():
                    text=w.tab(tab,'text')
                    if tab not in sources:sources[tab]=text
                    w.tab(tab,text=_translate_text(sources[tab],language))
                w._ihs_i18n_tabs=sources
            if isinstance(w,ttk.Treeview):
                sources=getattr(w,'_ihs_i18n_headings',{})
                for col in ('#0',)+tuple(w.cget('columns')):
                    try:
                        text=w.heading(col,'text')
                        if col not in sources:sources[col]=text
                        w.heading(col,text=_translate_text(sources[col],language))
                    except Exception:pass
                w._ihs_i18n_headings=sources
            if isinstance(w,tk.Canvas):
                sources=getattr(w,'_ihs_i18n_canvas_sources',{})
                for item in w.find_all():
                    if w.type(item)!='text':continue
                    text=w.itemcget(item,'text')
                    if item not in sources:sources[item]=text
                    try:
                        translated=_translate_text(sources[item],language)
                        if str(text)!=str(translated):w.itemconfigure(item,text=translated)
                    except Exception:pass
                w._ihs_i18n_canvas_sources=sources
            for child in w.winfo_children():visit(child)
        except Exception:pass
    visit(root)
    try:
        menu_name=root.cget('menu')
        if menu_name:_translate_menu(root.nametowidget(menu_name),language)
    except Exception:pass


def _apply_ui_language(root,language,persist=False):
    global UI_LANGUAGE,_I18N_APPLYING
    language=language if language in LANGUAGE_CHOICES else 'zh_CN';UI_LANGUAGE=language;_I18N_APPLYING=True
    try:_language_widget_tree(root,language)
    finally:_I18N_APPLYING=False
    if persist:_save_ui_setting('ui_language',language)
    return True


# Keep text changed later by playback/progress callbacks in the selected language.
# The original source string is retained on each widget/Canvas item, so switching
# back to Chinese restores the exact existing Chinese UI rather than translating
# the English text backwards.
_I18N_APPLYING=False
_ORIG_TK_CONFIGURE=tk.Misc.configure
_ORIG_TTK_CONFIGURE=ttk.Widget.configure
_ORIG_CANVAS_CREATE_TEXT=tk.Canvas.create_text
_ORIG_CANVAS_ITEMCONFIGURE=tk.Canvas.itemconfigure


def _i18n_configure(original,self,cnf=None,**kw):
    if not _I18N_APPLYING:
        source=None
        if isinstance(cnf,dict) and 'text' in cnf:
            cnf=dict(cnf);source=cnf['text'];cnf['text']=_translate_text(source)
        if 'text' in kw:
            source=kw['text'];kw['text']=_translate_text(source)
        if source is not None:
            try:self._ihs_i18n_source=str(source)
            except Exception:pass
    return original(self,cnf,**kw)


def _i18n_tk_configure(self,cnf=None,**kw):return _i18n_configure(_ORIG_TK_CONFIGURE,self,cnf,**kw)
def _i18n_ttk_configure(self,cnf=None,**kw):return _i18n_configure(_ORIG_TTK_CONFIGURE,self,cnf,**kw)


def _i18n_canvas_create_text(self,*args,**kw):
    source=kw.get('text',None)
    if source is not None:kw['text']=_translate_text(source)
    item=_ORIG_CANVAS_CREATE_TEXT(self,*args,**kw)
    if source is not None:
        try:
            sources=getattr(self,'_ihs_i18n_canvas_sources',{});sources[item]=str(source);self._ihs_i18n_canvas_sources=sources
        except Exception:pass
    return item


def _i18n_canvas_itemconfigure(self,tagOrId,cnf=None,**kw):
    if not _I18N_APPLYING:
        source=None
        if isinstance(cnf,dict) and 'text' in cnf:
            cnf=dict(cnf);source=cnf['text'];cnf['text']=_translate_text(source)
        if 'text' in kw:
            source=kw['text'];kw['text']=_translate_text(source)
        if source is not None:
            try:
                sources=getattr(self,'_ihs_i18n_canvas_sources',{})
                for item in self.find_withtag(tagOrId):sources[item]=str(source)
                self._ihs_i18n_canvas_sources=sources
            except Exception:pass
    return _ORIG_CANVAS_ITEMCONFIGURE(self,tagOrId,cnf,**kw)


tk.Misc.configure=_i18n_tk_configure;tk.Misc.config=_i18n_tk_configure
ttk.Widget.configure=_i18n_ttk_configure;ttk.Widget.config=_i18n_ttk_configure
tk.Canvas.create_text=_i18n_canvas_create_text;tk.Canvas.itemconfigure=_i18n_canvas_itemconfigure;tk.Canvas.itemconfig=_i18n_canvas_itemconfigure


def _font_candidates(key):
    return {
        'dengxian': ('DengXian','等线'),
        'yahei_ui': ('Microsoft YaHei UI','Microsoft YaHei','微软雅黑'),
    }.get(key,())


def _resolve_ui_font_family(root, key):
    """Return (actual_family, available). System Default is always available."""
    global SYSTEM_UI_FONT_FAMILY
    try:
        import tkinter.font as tkfont
        if SYSTEM_UI_FONT_FAMILY is None:
            SYSTEM_UI_FONT_FAMILY=tkfont.nametofont('TkDefaultFont',root=root).actual('family')
        if key == 'system':
            return (SYSTEM_UI_FONT_FAMILY or tkfont.nametofont('TkDefaultFont',root=root).actual('family'), True)
        families=set(tkfont.families(root))
        # Case-insensitive map helps across localized Windows installations.
        fmap={str(x).casefold():str(x) for x in families}
        for candidate in _font_candidates(key):
            actual=fmap.get(candidate.casefold())
            if actual:
                return actual, True
        return (SYSTEM_UI_FONT_FAMILY or tkfont.nametofont('TkDefaultFont',root=root).actual('family'), False)
    except Exception:
        return (SYSTEM_UI_FONT_FAMILY or 'TkDefaultFont', key == 'system')


def _ui_font(size=9, pixel=False):
    """Return an explicit regular-weight font tuple using the selected UI family."""
    n = -abs(int(size)) if pixel else int(size)
    family = UI_FONT_FAMILY if UI_FONT_FAMILY != 'TkDefaultFont' else 'TkDefaultFont'
    return (family, n, 'normal')


def _configure_ui_style_fonts(root):
    """Update every application ttk style without introducing bold/semibold text."""
    try:
        st=ttk.Style(root)
        sizes={
            'TLabel':9,'TButton':9,'TCheckbutton':9,'TRadiobutton':9,'TMenubutton':9,
            'TEntry':9,'TSpinbox':9,'TCombobox':9,'TNotebook.Tab':9,'TLabelframe.Label':9,
            'Treeview':9,'Treeview.Heading':9,'Toolbutton':9,
            'Title.TLabel':16,'Sub.TLabel':9,'Primary.TButton':10,'Stage.TLabel':9,
        }
        for sty,size in sizes.items():
            try:st.configure(sty,font=_ui_font(size))
            except Exception:pass
    except Exception:
        pass


def _retarget_widget_fonts(widget):
    """Retarget explicit widget/Canvas font tuples to the newly selected family.

    Existing sizes are preserved, while weight/slant are normalized.  This is what
    makes a font change visible immediately without restarting open Timelapse windows.
    """
    try:
        import tkinter.font as tkfont
        # Explicit widget fonts (tk widgets and ttk widgets that set their own font).
        try:
            spec=widget.cget('font')
        except Exception:
            spec=''
        if spec:
            try:
                f=tkfont.Font(root=widget,font=spec)
                a=f.actual(); size=int(a.get('size',9) or 9)
                widget.configure(font=(UI_FONT_FAMILY,size,'normal'))
            except Exception:
                pass
        if isinstance(widget,tk.Canvas):
            try:
                for item in widget.find_all():
                    if widget.type(item)!='text':continue
                    spec=widget.itemcget(item,'font')
                    if not spec:continue
                    try:
                        f=tkfont.Font(root=widget,font=spec);a=f.actual();size=int(a.get('size',9) or 9)
                        widget.itemconfigure(item,font=(UI_FONT_FAMILY,size,'normal'))
                    except Exception:pass
            except Exception:
                pass
        try:
            children=widget.winfo_children()
        except Exception:
            children=[]
        for child in children:
            _retarget_widget_fonts(child)
    except Exception:
        pass


def _apply_ui_font_preference(root, key, persist=False):
    """Apply one of the four user-facing font choices to all currently open UI."""
    global UI_FONT_PREFERENCE, UI_FONT_FAMILY
    family,available=_resolve_ui_font_family(root,key)
    if not available and key!='system':
        return False,family
    UI_FONT_PREFERENCE=key; UI_FONT_FAMILY=family
    try:
        import tkinter.font as tkfont
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont',
                     'TkCaptionFont','TkSmallCaptionFont','TkTooltipFont','TkFixedFont','TkIconFont'):
            try:
                tkfont.nametofont(name,root=root).configure(
                    family=family,weight='normal',slant='roman',underline=0,overstrike=0)
            except Exception:pass
    except Exception:
        pass
    _configure_ui_style_fonts(root)
    _retarget_widget_fonts(root)
    # Toplevels created by the app are normally descendants, but explicitly scan the
    # interpreter's top-level list as a guard for dialogs/windows created with no master.
    try:
        for name in root.tk.call('winfo','children','.'):
            try:
                w=root.nametowidget(name)
                if w is not root:_retarget_widget_fonts(w)
            except Exception:pass
    except Exception:pass
    _enforce_regular_typography(root)
    if persist:_save_ui_font_preference(key)
    return True,family


def _enable_windows_high_dpi_awareness():
    """Enable crisp per-monitor rendering before the first Tk window exists."""
    if os.name != 'nt':
        return False
    try:
        import ctypes
        # Windows 10+: PER_MONITOR_AWARE_V2. This prevents Windows bitmap-DPI
        # virtualization, the main cause of blurry Tk/Canvas text on 125–250% displays.
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_bool
        if fn(ctypes.c_void_p(-4)):
            return True
    except Exception:
        pass
    try:
        import ctypes
        # Windows 8.1 fallback.
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) in (0, None):
            return True
    except Exception:
        pass
    try:
        import ctypes
        return bool(ctypes.windll.user32.SetProcessDPIAware())
    except Exception:
        return False


def _configure_tk_high_dpi(root):
    """Match Tk point scaling to the physical DPI of the current Windows monitor."""
    dpi = 96
    if os.name == 'nt':
        try:
            import ctypes
            root.update_idletasks()
            dpi = int(ctypes.windll.user32.GetDpiForWindow(root.winfo_id()) or 96)
        except Exception:
            try:
                import ctypes
                dpi = int(ctypes.windll.user32.GetDpiForSystem() or 96)
            except Exception:
                dpi = 96
    try:
        root.tk.call('tk', 'scaling', max(1.0, float(dpi) / 72.0))
    except Exception:
        pass
    try:
        import tkinter.font as tkfont
        global UI_FONT_FAMILY, UI_FONT_PREFERENCE, SYSTEM_UI_FONT_FAMILY
        # Capture the untouched OS/Tk default before changing any named font.
        if SYSTEM_UI_FONT_FAMILY is None:
            try:SYSTEM_UI_FONT_FAMILY=tkfont.nametofont('TkDefaultFont',root=root).actual('family')
            except Exception:SYSTEM_UI_FONT_FAMILY='Segoe UI' if os.name=='nt' else 'TkDefaultFont'
        resolved,available=_resolve_ui_font_family(root,UI_FONT_PREFERENCE)
        if not available and UI_FONT_PREFERENCE!='system':
            UI_FONT_PREFERENCE='system'; resolved,_=_resolve_ui_font_family(root,'system')
        UI_FONT_FAMILY=resolved
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont','TkCaptionFont','TkSmallCaptionFont','TkTooltipFont','TkFixedFont','TkIconFont'):
            try:
                # Keep the whole application typographically uniform.  Some Tk/ttk
                # themes may give TkHeadingFont or LabelFrame captions a heavier weight by default;
                # explicitly force every named UI font back to regular weight.
                tkfont.nametofont(name, root=root).configure(
                    family=UI_FONT_FAMILY, weight='normal', slant='roman',
                    underline=0, overstrike=0)
            except Exception:
                pass
        try:
            root.option_add('*Font', 'TkDefaultFont')
            root.option_add('*Menu.font', 'TkMenuFont')
        except Exception:
            pass
    except Exception:
        pass
    return dpi


def _enforce_regular_typography(root):
    """Best-effort runtime guard: normalize named fonts and ttk styles.

    This is deliberately idempotent and may be called after dialogs are created or
    after a theme change. It does not change font sizes; it only prevents non-normal
    weight/slant from entering application-controlled text.
    """
    try:
        import tkinter.font as tkfont
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont',
                     'TkCaptionFont','TkSmallCaptionFont','TkTooltipFont','TkFixedFont','TkIconFont'):
            try:
                f=tkfont.nametofont(name, root=root)
                if UI_FONT_FAMILY != 'TkDefaultFont':
                    f.configure(family=UI_FONT_FAMILY)
                f.configure(weight='normal',slant='roman',underline=0,overstrike=0)
            except Exception:
                pass
        _configure_ui_style_fonts(root)
    except Exception:
        pass
    # Normalize explicit per-widget/Canvas fonts too.  This closes the remaining
    # path where a native heading or copied explicit font could retain semibold
    # even though all Tk named fonts were already regular.
    _retarget_widget_fonts(root)
    _theme_widget_tree(root,UI_THEME_PREFERENCE)
    _apply_ui_language(root,UI_LANGUAGE,persist=False)


# Must run before App()/Toplevel creates the first HWND.
_WINDOWS_HIGH_DPI_ENABLED = _enable_windows_high_dpi_awareness()


def _make_vertical_scroll_area(parent, padding=0):
    """Create a reusable vertically scrollable content area.

    The returned content frame is tagged with ``_ihs_scroll_target`` so the
    application-wide mouse-wheel router can scroll it even when the pointer
    is over labels, buttons, scales, entries or curve canvases.
    """
    shell = ttk.Frame(parent)
    shell.pack(fill='both', expand=True)
    canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview,style='IHS.Vertical.TScrollbar')
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    content = ttk.Frame(canvas, padding=padding)
    window_id = canvas.create_window((0, 0), window=content, anchor='nw')

    def sync_scrollregion(event=None):
        try:
            box = canvas.bbox('all')
            if box:
                canvas.configure(scrollregion=box)
        except Exception:
            pass

    def fit_width(event):
        try:
            canvas.itemconfigure(window_id, width=max(1, event.width))
        except Exception:
            pass

    content.bind('<Configure>', sync_scrollregion, add='+')
    canvas.bind('<Configure>', fit_width, add='+')
    content._ihs_scroll_target = canvas
    shell._ihs_scroll_target = canvas
    canvas._ihs_scroll_target = canvas
    canvas._ihs_scroll_shell = shell
    content._ihs_scroll_shell = shell
    return content, canvas, shell


def _mousewheel_steps(event, linux_direction=None):
    """Return Tk yview units; positive means scroll down."""
    if linux_direction is not None:
        return -3 if linux_direction > 0 else 3
    delta = int(getattr(event, 'delta', 0) or 0)
    if delta == 0:
        return 0
    # Windows normally reports multiples of 120, high-resolution mice/trackpads
    # can report smaller values. Keep at least one visible scroll step.
    mag = max(1, abs(delta) // 120)
    return (-3 * mag) if delta > 0 else (3 * mag)


def _deps():
    try:
        import numpy as np
        import tifffile
        from PIL import Image, ImageTk, ImageFilter
        try:
            import rawpy
        except Exception:
            rawpy = None
        try:
            import cv2
        except Exception:
            cv2 = None
        return np, tifffile, Image, ImageTk, ImageFilter, rawpy, cv2
    except Exception as e:
        raise RuntimeError('缺少运行依赖。请使用“启动 IceHaloStack.bat”。\n\n' + str(e))




_GIB = 1024 ** 3
_MIB = 1024 ** 2


def _fmt_bytes(n):
    try:
        n = max(0.0, float(n))
    except Exception:
        return '—'
    if n >= _GIB:
        return f'{n/_GIB:.2f} GB'
    if n >= _MIB:
        return f'{n/_MIB:.0f} MB'
    if n >= 1024:
        return f'{n/1024:.0f} KB'
    return f'{n:.0f} B'



def _format_seconds_short(seconds):
    try:
        sec=max(0,int(round(float(seconds))))
    except Exception:
        return '—'
    h,rem=divmod(sec,3600);m,ss=divmod(rem,60)
    return f'{h:02d}:{m:02d}:{ss:02d}' if h else f'{m:02d}:{ss:02d}'


def _system_memory_status():
    """Return (total_bytes, available_bytes) without an extra dependency."""
    # Windows target: GlobalMemoryStatusEx reports ullAvailPhys directly.
    if os.name == 'nt':
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]
            st = MEMORYSTATUSEX(); st.dwLength = ctypes.sizeof(st)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullTotalPhys), int(st.ullAvailPhys)
        except Exception:
            pass
    # Linux / WSL fallback, useful for development/testing.
    try:
        vals = {}
        with open('/proc/meminfo', 'r', encoding='utf-8') as f:
            for line in f:
                if ':' not in line: continue
                k, v = line.split(':', 1)
                vals[k] = int(v.strip().split()[0]) * 1024
        total = int(vals.get('MemTotal', 0)); avail = int(vals.get('MemAvailable', vals.get('MemFree', 0)))
        if total > 0: return total, max(0, avail)
    except Exception:
        pass
    # Generic POSIX fallback.
    try:
        page = int(os.sysconf('SC_PAGE_SIZE')); total = int(os.sysconf('SC_PHYS_PAGES')) * page
        avail = int(os.sysconf('SC_AVPHYS_PAGES')) * page
        return total, max(0, avail)
    except Exception:
        return 0, 0


def _process_memory_rss():
    """Best-effort current process resident memory, bytes.

    On Windows use K32GetProcessMemoryInfo with explicit 64-bit-safe ctypes
    signatures.  Older builds relied on ctypes defaults, which can return 0 on
    some 64-bit Windows/Python combinations even while large RAM caches exist.
    """
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes
            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t),
                    ('PrivateUsage', ctypes.c_size_t),
                ]
            counters=PROCESS_MEMORY_COUNTERS_EX(); counters.cb=ctypes.sizeof(counters)
            kernel32=ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.GetCurrentProcess.argtypes=[]; kernel32.GetCurrentProcess.restype=wintypes.HANDLE
            handle=kernel32.GetCurrentProcess()
            fn=getattr(kernel32,'K32GetProcessMemoryInfo',None)
            if fn is not None:
                fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),wintypes.DWORD]
                fn.restype=wintypes.BOOL
                if fn(handle,ctypes.byref(counters),ctypes.sizeof(counters)):
                    return int(counters.WorkingSetSize)
            psapi=ctypes.WinDLL('psapi', use_last_error=True)
            fn=psapi.GetProcessMemoryInfo
            fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),wintypes.DWORD]
            fn.restype=wintypes.BOOL
            if fn(handle,ctypes.byref(counters),ctypes.sizeof(counters)):
                return int(counters.WorkingSetSize)
        except Exception:
            pass
    try:
        with open('/proc/self/statm', 'r', encoding='utf-8') as f:
            parts=f.read().split()
        if len(parts) >= 2:
            return int(parts[1]) * int(os.sysconf('SC_PAGE_SIZE'))
    except Exception:
        pass
    try:
        import resource
        val=float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return int(val if sys.platform == 'darwin' else val*1024)
    except Exception:
        return 0

def _auto_ram_limit_bytes():
    total, avail = _system_memory_status(); rss = _process_memory_rss()
    if total <= 0:
        return max(int(4*_GIB), int(rss + 2*_GIB))
    reserve = max(int(4*_GIB), int(total * 0.15))
    free_for_app = max(512*_MIB, avail - reserve)
    # Keep Auto conservative: use at most ~55% of physical RAM while allowing
    # current process RSS plus 70% of safely available headroom.
    target = int(rss + free_for_app * 0.70)
    target = min(target, int(total * 0.55), max(int(1*_GIB), total - reserve))
    return max(int(1*_GIB), target)


def _timelapse_memory_policy_snapshot(owner):
    total, avail = _system_memory_status(); rss = _process_memory_rss()
    reserve = max(int(4*_GIB), int(total * 0.15)) if total else int(4*_GIB)
    mode = str(owner.memory_limit_mode.get()) if hasattr(owner,'memory_limit_mode') else 'Auto'
    strategy = str(owner.memory_strategy.get()) if hasattr(owner,'memory_strategy') else 'Balanced'
    if mode == 'Manual':
        try: requested = float(owner.memory_limit_gb.get())
        except Exception: requested = 4.0
        requested = max(1.0, requested)
        limit = int(requested * _GIB)
        if total > 0: limit = min(limit, max(int(1*_GIB), total - reserve))
    else:
        limit = _auto_ram_limit_bytes()
    # Frame-cache share of the software budget. Scratch buffers, rolling sum,
    # node processing and output remain outside this cache allowance.
    shares = {'Memory Saver':0.22, 'Balanced':0.45, 'Maximum Performance':0.65}
    prefetch = {'Memory Saver':0, 'Balanced':2, 'Maximum Performance':4}
    return {
        'limit_bytes': max(int(1*_GIB), int(limit)),
        'system_total_bytes': int(total), 'system_available_bytes': int(avail),
        'system_reserve_bytes': int(reserve), 'rss_at_start_bytes': int(rss),
        'strategy': strategy, 'frame_cache_share': shares.get(strategy,0.45),
        'prefetch_count': prefetch.get(strategy,2), 'disk_cache': False,
    }


def _manual_ram_bounds_gb():
    total, _ = _system_memory_status()
    if total <= 0:
        return 1.0, 64.0
    reserve=max(int(4*_GIB),int(total*0.15))
    hi=max(1.0,(max(int(1*_GIB),total-reserve))/_GIB)
    return 1.0, max(1.0, round(hi,1))


def _init_timelapse_memory_vars(owner):
    total, _ = _system_memory_status(); suggested = _auto_ram_limit_bytes()/_GIB
    lo,hi=_manual_ram_bounds_gb();suggested=max(lo,min(hi,suggested))
    owner.memory_limit_mode = tk.StringVar(value='Auto')
    owner.memory_limit_gb = tk.DoubleVar(value=max(lo, round(suggested, 1)))
    owner.memory_limit_value_text = tk.StringVar(value=f'{owner.memory_limit_gb.get():.1f} GB')
    owner.memory_limit_range_text = tk.StringVar(value=f'Manual 可调范围：{lo:.1f}–{hi:.1f} GB')
    owner.memory_strategy = tk.StringVar(value='Balanced')
    owner.memory_system_pct = tk.DoubleVar(value=0.0)
    owner.memory_app_pct = tk.DoubleVar(value=0.0)
    owner.memory_system_text = tk.StringVar(value='System RAM：读取中…')
    owner.memory_app_text = tk.StringVar(value='IceHaloStack RAM：读取中…')
    owner.memory_cache_text = tk.StringVar(value='Frame Cache：空闲')
    owner.memory_dag_text = tk.StringVar(value='Shared Node DAG：空闲')
    owner.memory_output_text = tk.StringVar(value='Async Output：空闲')
    owner.memory_budget_text = tk.StringVar(value='RAM Budget：Auto')
    owner.memory_pressure_text = tk.StringVar(value='Memory Pressure：Normal · Disk Cache OFF')
    owner.performance_monitor_text = tk.StringVar(value='Performance：空闲 · 开始批量任务后记录 Stack / Node / Output / FFmpeg / RAM')
    owner.stability_text = tk.StringVar(value='Stability：Idle')
    owner.performance_save_report = tk.BooleanVar(value=False)
    owner._memory_manual_entry = None
    owner._memory_manual_scale = None
    owner._memory_manual_min_gb = lo
    owner._memory_manual_max_gb = hi
    owner._memory_monitor_after = None
    owner._active_memory_policy = None
    owner._active_frame_cache = None
    owner._active_output_pipeline = None
    owner._active_performance_monitor = None
    owner._last_performance_snapshot = None
    owner._timelapse_details_window = None


def _manual_ram_value_changed(owner, value=None):
    try:
        v=float(value if value is not None else owner.memory_limit_gb.get())
        owner.memory_limit_value_text.set(f'{v:.1f} GB')
    except Exception:
        owner.memory_limit_value_text.set('— GB')


def _commit_manual_ram_value(owner, event=None):
    try:v=float(owner.memory_limit_gb.get())
    except Exception:v=float(getattr(owner,'_memory_manual_min_gb',1.0))
    lo=float(getattr(owner,'_memory_manual_min_gb',1.0));hi=float(getattr(owner,'_memory_manual_max_gb',64.0))
    v=round(max(lo,min(hi,v))*10.0)/10.0
    try:owner.memory_limit_gb.set(v)
    except Exception:pass
    _manual_ram_value_changed(owner,v)
    _update_memory_monitor(owner)
    return None


def _memory_limit_mode_changed(owner):
    manual=(owner.memory_limit_mode.get() == 'Manual')
    try:
        if owner._memory_manual_entry is not None: owner._memory_manual_entry.configure(state='normal' if manual else 'disabled')
        if owner._memory_manual_scale is not None: owner._memory_manual_scale.configure(state='normal' if manual else 'disabled')
    except Exception:
        pass
    if manual:_commit_manual_ram_value(owner)
    else:_update_memory_monitor(owner)


def _build_timelapse_memory_panel(owner, parent, wraplength=430, show_dag=False):
    """Compact memory controls for the main timelapse UI.

    v0.9.4.18f intentionally keeps verbose cache/DAG/performance diagnostics out
    of the main workflow.  Those values remain live and are available from the
    separate Details window.
    """
    box=ttk.LabelFrame(parent,text='性能与内存 / Performance & Memory',padding=7);box.pack(fill='x',pady=(8,0))
    ttk.Label(box,textvariable=owner.memory_system_text,wraplength=wraplength).pack(anchor='w')
    ttk.Progressbar(box,variable=owner.memory_system_pct,maximum=100).pack(fill='x',pady=(2,5))
    ttk.Label(box,textvariable=owner.memory_app_text,wraplength=wraplength).pack(anchor='w')
    ttk.Progressbar(box,variable=owner.memory_app_pct,maximum=100).pack(fill='x',pady=(2,5))

    ttl=ttk.Frame(box);ttl.pack(fill='x',pady=(2,0))
    ttk.Label(ttl,text='RAM 上限').pack(side='left')
    ttk.Label(ttl,textvariable=owner.memory_limit_value_text).pack(side='right')
    modes=ttk.Frame(box);modes.pack(fill='x',pady=(1,2))
    ttk.Radiobutton(modes,text='Auto',variable=owner.memory_limit_mode,value='Auto',command=lambda:_memory_limit_mode_changed(owner)).pack(side='left')
    ttk.Radiobutton(modes,text='Manual',variable=owner.memory_limit_mode,value='Manual',command=lambda:_memory_limit_mode_changed(owner)).pack(side='left',padx=(8,0))

    lo=float(getattr(owner,'_memory_manual_min_gb',1.0));hi=float(getattr(owner,'_memory_manual_max_gb',64.0))
    slider_row=ttk.Frame(box);slider_row.pack(fill='x',pady=(0,1))
    scale=ttk.Scale(slider_row,from_=lo,to=hi,orient='horizontal',variable=owner.memory_limit_gb,command=lambda v:_manual_ram_value_changed(owner,v),state='disabled')
    scale.pack(side='left',fill='x',expand=True,padx=(0,6))
    ent=ttk.Entry(slider_row,textvariable=owner.memory_limit_gb,width=7,justify='right',state='disabled');ent.pack(side='left');ttk.Label(slider_row,text='GB').pack(side='left',padx=(3,0))
    owner._memory_manual_entry=ent;owner._memory_manual_scale=scale
    bounds=ttk.Frame(box);bounds.pack(fill='x',pady=(0,3))
    ttk.Label(bounds,text=f'{lo:.1f} GB',foreground='#777').pack(side='left')
    ttk.Label(bounds,text=f'{hi:.1f} GB',foreground='#777').pack(side='right')
    scale.bind('<ButtonRelease-1>',lambda e:_commit_manual_ram_value(owner),add='+')
    scale.bind('<KeyRelease>',lambda e:_commit_manual_ram_value(owner),add='+')
    ent.bind('<Return>',lambda e:_commit_manual_ram_value(owner),add='+')
    ent.bind('<FocusOut>',lambda e:_commit_manual_ram_value(owner),add='+')

    st=ttk.Frame(box);st.pack(fill='x',pady=(2,0));ttk.Label(st,text='策略').pack(side='left')
    ttk.Combobox(st,textvariable=owner.memory_strategy,state='readonly',width=22,values=['Memory Saver','Balanced','Maximum Performance']).pack(side='right')

    actions=ttk.Frame(box);actions.pack(fill='x',pady=(6,0))
    ttk.Button(actions,text='详情…',command=lambda:_show_timelapse_details(owner,show_dag=show_dag)).pack(side='right')
    owner.memory_strategy.trace_add('write',lambda *a:_update_memory_monitor(owner))
    owner.memory_limit_gb.trace_add('write',lambda *a:_manual_ram_value_changed(owner))
    _manual_ram_value_changed(owner)
    _update_memory_monitor(owner)
    return box


def _show_timelapse_details(owner, show_dag=False):
    """Open verbose diagnostics in a separate live window instead of the main UI."""
    old=getattr(owner,'_timelapse_details_window',None)
    try:
        if old is not None and old.winfo_exists():
            old.deiconify();old.lift();old.focus_force();return
    except Exception:
        pass
    win=tk.Toplevel(owner);owner._timelapse_details_window=win
    win.title('IceHaloStack · 性能与内存详情')
    win.geometry('620x650');win.minsize(500,460)
    outer=ttk.Frame(win,padding=12);outer.pack(fill='both',expand=True)
    body,canvas,_shell=_make_vertical_scroll_area(outer,padding=0)

    mem=ttk.LabelFrame(body,text='内存 / Memory',padding=8);mem.pack(fill='x')
    for var in (owner.memory_system_text,owner.memory_app_text,owner.memory_budget_text,owner.memory_cache_text):
        ttk.Label(mem,textvariable=var,wraplength=560).pack(anchor='w',pady=2)
    ttk.Label(mem,textvariable=owner.memory_pressure_text,wraplength=560).pack(anchor='w',pady=2)
    ttk.Label(mem,textvariable=owner.memory_limit_range_text,wraplength=560).pack(anchor='w',pady=2)

    if show_dag:
        dag=ttk.LabelFrame(body,text='共享节点 / Shared Node DAG',padding=8);dag.pack(fill='x',pady=(8,0))
        ttk.Label(dag,textvariable=owner.memory_dag_text,wraplength=560).pack(anchor='w')

    out=ttk.LabelFrame(body,text='异步输出 / Async Output',padding=8);out.pack(fill='x',pady=(8,0))
    ttk.Label(out,textvariable=owner.memory_output_text,wraplength=560).pack(anchor='w')

    perf=ttk.LabelFrame(body,text='性能与稳定性 / Performance & Stability',padding=8);perf.pack(fill='x',pady=(8,0))
    ttk.Label(perf,textvariable=owner.performance_monitor_text,wraplength=560).pack(anchor='w',pady=2)
    ttk.Label(perf,textvariable=owner.stability_text,wraplength=560).pack(anchor='w',pady=2)
    ttk.Checkbutton(perf,text='保存性能报告 JSON/TXT',variable=owner.performance_save_report).pack(anchor='w',pady=(6,0))
    row=ttk.Frame(perf);row.pack(fill='x',pady=(7,0))
    ttk.Button(row,text='完整性能报告…',command=lambda:_show_performance_details(owner)).pack(side='right')

    storage=ttk.LabelFrame(body,text='缓存策略 / Cache Policy',padding=8);storage.pack(fill='x',pady=(8,0))
    ttk.Label(storage,text='中间 Master、RAW Decode Cache 与 Node Cache 仅驻留 RAM；Disk Cache = OFF。RAM 紧张时自动减少缓存或重新解码源文件。',wraplength=560).pack(anchor='w')
    ttk.Button(outer,text='关闭',command=win.destroy).pack(anchor='e',pady=(8,0))
    def closed():
        try:owner._timelapse_details_window=None
        except Exception:pass
        win.destroy()
    win.protocol('WM_DELETE_WINDOW',closed)

def _update_memory_monitor(owner):
    try:
        total, avail = _system_memory_status(); rss = _process_memory_rss(); used=max(0,total-avail)
        # Do not read Tk variables from the worker. This function only runs on UI thread.
        policy = getattr(owner,'_active_memory_policy',None) or _timelapse_memory_policy_snapshot(owner)
        limit = max(1, int(policy['limit_bytes']))
        owner.memory_system_pct.set((used/total*100.0) if total else 0.0)
        owner.memory_app_pct.set(min(100.0, rss/limit*100.0))
        owner.memory_system_text.set(f'System RAM：已用 {_fmt_bytes(used)} / {_fmt_bytes(total)} · 可用 {_fmt_bytes(avail)}')
        owner.memory_app_text.set(f'IceHaloStack：{_fmt_bytes(rss)} / {_fmt_bytes(limit)}')
        if owner.memory_limit_mode.get() == 'Auto':
            owner.memory_limit_value_text.set(f'Auto · {limit/_GIB:.1f} GB')
        else:
            try: owner.memory_limit_value_text.set(f'{float(owner.memory_limit_gb.get()):.1f} GB')
            except Exception: owner.memory_limit_value_text.set('— GB')
        owner.memory_budget_text.set(f'RAM Budget：{owner.memory_limit_mode.get()} · 有效上限 {_fmt_bytes(limit)} · 策略 {owner.memory_strategy.get()}')
        cache=getattr(owner,'_active_frame_cache',None)
        if cache is not None:
            st=cache.stats()
            owner.memory_cache_text.set(f'Frame Cache：{_fmt_bytes(st["bytes"])} · {st["frames"]} 帧 · Hit {st["hits"]} / Miss {st["misses"]} / Evict {st["evictions"]} · Prefetch {st["prefetch_pending"]}')
            owner.memory_pressure_text.set(f'Memory Pressure：{st["pressure"]} · Disk Cache OFF')
        else:
            owner.memory_cache_text.set('Frame Cache：空闲 · 批量任务开始后按 RAM Budget 动态启用')
            reserve=policy['system_reserve_bytes']; pressure='High' if avail and avail<reserve else 'Normal'
            owner.memory_pressure_text.set(f'Memory Pressure：{pressure} · Disk Cache OFF')
        outpipe=getattr(owner,'_active_output_pipeline',None)
        if outpipe is not None:
            ost=outpipe.stats()
            wf=float(ost.get('recent_writer_fps') or ost.get('writer_fps') or 0.0)
            state='空闲/等待处理' if ost.get('writer_idle') else '写入中'
            owner.memory_output_text.set(f'Async Output：{state} · Queue {ost["queued"]}/{ost["capacity"]} · Written {ost["completed"]}/{ost["total"]} · Writer {wf:.2f} fps')
        else:
            owner.memory_output_text.set('Async Output：空闲 · 批量任务时启用 RAM-aware bounded queue')
        perf=getattr(owner,'_active_performance_monitor',None)
        snap=None
        if perf is not None:
            perf.sample_resources();snap=perf.snapshot()
        elif getattr(owner,'_last_performance_snapshot',None):
            snap=dict(owner._last_performance_snapshot)
        if snap:
            hit=float(snap.get('frame_cache_hit_rate',0.0))*100.0
            owner.performance_monitor_text.set(f'Performance：{snap.get("status","Running")} · Elapsed {_format_seconds_short(snap.get("elapsed_seconds",0))} · Master {snap.get("masters",0)} · RAW Decode {snap.get("raw_decodes",0)} · Cache Hit {hit:.1f}% · Stack {snap.get("stack_seconds",0.0):.1f}s · Node {snap.get("node_seconds",0.0):.1f}s · Write {snap.get("output_write_seconds",0.0):.1f}s · Peak RAM {_fmt_bytes(snap.get("peak_rss_bytes",0))}')
            owner.stability_text.set(str(snap.get('stability_text','Stability：Running')))
        else:
            owner.performance_monitor_text.set('Performance：空闲 · 开始批量任务后记录 Stack / Node / Output / FFmpeg / RAM')
            owner.stability_text.set('Stability：Idle')
    except Exception:
        pass
    try:
        if owner.winfo_exists():
            if getattr(owner,'_memory_monitor_after',None) is not None:
                try: owner.after_cancel(owner._memory_monitor_after)
                except Exception: pass
            owner._memory_monitor_after=owner.after(750,lambda:_update_memory_monitor(owner))
    except Exception:
        pass


class PerformanceMonitor:
    """Low-overhead in-memory profiler and non-destructive watchdog for timelapse jobs."""
    def __init__(self, owner, engine, policy, kind='Timelapse', save_report=False):
        self.owner=owner;self.engine=str(engine);self.kind=str(kind);self.policy=dict(policy or {});self.save_report=bool(save_report)
        self.lock=threading.RLock();self.started=time.monotonic();self.ended=None;self.status='Running';self.last_activity=self.started;self.last_activity_label='start';self.error=''
        self.counters=Counter();self.stage_seconds=Counter();self.node_seconds=Counter();self.node_counts=Counter();self.pressure_events=Counter()
        self.peak_rss_bytes=_process_memory_rss();_total,avail=_system_memory_status();self.min_system_available_bytes=int(avail or 0)
        self.peak_frame_cache_bytes=0;self.peak_dag_bytes=0;self.peak_output_queue_bytes=0;self.final_frame_cache_stats={};self.final_output_stats={};self.final_dag_stats={}
        owner._active_performance_monitor=self

    def touch(self,label='activity'):
        with self.lock:self.last_activity=time.monotonic();self.last_activity_label=str(label)

    def add_stage(self,name,seconds,count=0):
        sec=max(0.0,float(seconds or 0.0))
        with self.lock:
            self.stage_seconds[str(name)]+=sec
            if count:self.counters[str(name)+'_count']+=int(count)
            self.last_activity=time.monotonic();self.last_activity_label=str(name)

    def inc(self,name,n=1):
        with self.lock:self.counters[str(name)]+=int(n);self.last_activity=time.monotonic();self.last_activity_label=str(name)

    def record_node(self,node,seconds):
        sec=max(0.0,float(seconds or 0.0))
        with self.lock:
            self.node_seconds[str(node)]+=sec;self.node_counts[str(node)]+=1;self.stage_seconds['node_processing']+=sec;self.counters['node_computes']+=1;self.last_activity=time.monotonic();self.last_activity_label='node:'+str(node)

    def record_pressure(self,pressure):
        with self.lock:self.pressure_events[str(pressure)]+=1

    def record_cache_stats(self,st):
        if not st:return
        with self.lock:self.final_frame_cache_stats=dict(st);self.peak_frame_cache_bytes=max(self.peak_frame_cache_bytes,int(st.get('bytes',0)))

    def record_output_stats(self,st):
        if not st:return
        with self.lock:self.final_output_stats=dict(st);self.peak_output_queue_bytes=max(self.peak_output_queue_bytes,int(st.get('peak_bytes',st.get('queued_bytes',0))))

    def record_dag_stats(self,st):
        if not st:return
        with self.lock:self.final_dag_stats=dict(st);self.peak_dag_bytes=max(self.peak_dag_bytes,int(st.get('peak_bytes',0)))

    def sample_resources(self):
        rss=_process_memory_rss();_total,avail=_system_memory_status();cache=getattr(self.owner,'_active_frame_cache',None);out=getattr(self.owner,'_active_output_pipeline',None)
        with self.lock:
            self.peak_rss_bytes=max(self.peak_rss_bytes,int(rss or 0))
            if avail>0:self.min_system_available_bytes=int(avail) if self.min_system_available_bytes<=0 else min(self.min_system_available_bytes,int(avail))
        try:
            if cache is not None:self.record_cache_stats(cache.stats())
        except Exception:pass
        try:
            if out is not None:self.record_output_stats(out.stats())
        except Exception:pass

    def wrap_masters(self,iterable):
        it=iter(iterable)
        while True:
            self.touch('stack_wait');t=time.monotonic()
            try:master=next(it)
            except StopIteration:return
            self.add_stage('stack',time.monotonic()-t);self.inc('masters',1);yield master

    def _stability(self,now=None):
        now=time.monotonic() if now is None else now;age=max(0.0,now-self.last_activity)
        if self.status!='Running':return f'Stability：{self.status}'
        if age>=120:return f'Stability：Possible stall / 长操作超过 {int(age)}s · 当前阶段 {self.last_activity_label} · 仅提示，不会强制终止'
        if age>=30:return f'Stability：Long operation · {int(age)}s · 当前阶段 {self.last_activity_label}'
        return f'Stability：Running · 最近活动 {age:.1f}s 前 · {self.last_activity_label}'

    def snapshot(self):
        self.sample_resources();now=self.ended or time.monotonic()
        with self.lock:
            c=dict(self.counters);st=dict(self.stage_seconds);nodes=dict(self.node_seconds);node_counts=dict(self.node_counts);fc=dict(self.final_frame_cache_stats);out=dict(self.final_output_stats);dag=dict(self.final_dag_stats);hits=int(fc.get('hits',0));misses=int(fc.get('misses',0));den=hits+misses
            return {'version':VERSION,'kind':self.kind,'engine':self.engine,'status':self.status,'elapsed_seconds':max(0.0,now-self.started),'masters':int(c.get('masters',0)),'processed_tasks':int(c.get('processed_tasks',0)),'raw_decodes':int(c.get('raw_decodes',0)),'frames_written':int(out.get('completed',c.get('frames_written',0))),'raw_decode_seconds':float(st.get('raw_decode',0.0)),'stack_seconds':float(st.get('stack',0.0)),'node_seconds':float(st.get('node_processing',0.0)),'output_prepare_seconds':float(st.get('output_prepare',0.0)),'output_backpressure_seconds':float(st.get('output_backpressure',0.0)),'output_write_seconds':float(st.get('output_write',0.0)),'ffmpeg_seconds':float(st.get('ffmpeg',0.0)),'peak_rss_bytes':int(self.peak_rss_bytes),'min_system_available_bytes':int(self.min_system_available_bytes),'peak_frame_cache_bytes':int(self.peak_frame_cache_bytes),'peak_dag_bytes':int(self.peak_dag_bytes),'peak_output_queue_bytes':int(self.peak_output_queue_bytes),'frame_cache_hits':hits,'frame_cache_misses':misses,'frame_cache_evictions':int(fc.get('evictions',0)),'frame_cache_hit_rate':(hits/den if den else 0.0),'dag_hits':int(dag.get('hits',0)),'dag_computes':int(dag.get('computes',0)),'dag_budget_skips':int(dag.get('budget_skips',0)),'dag_hits_by_node':dict(dag.get('hits_by_node',{})),'dag_computes_by_node':dict(dag.get('computes_by_node',{})),'dag_reusable_by_node':dict(dag.get('reusable_by_node',{})),'node_seconds_by_type':nodes,'node_compute_count_by_type':node_counts,'pressure_events':dict(self.pressure_events),'last_activity':self.last_activity_label,'stability_text':self._stability(now),'ram_budget_bytes':int(self.policy.get('limit_bytes',0)),'memory_strategy':self.policy.get('strategy',''),'disk_cache':False,'error':self.error}

    def finalize(self,status,run_dir=None,error='',extra=None):
        self.sample_resources()
        with self.lock:self.status=str(status);self.error=str(error or '');self.ended=time.monotonic();self.last_activity=self.ended;self.last_activity_label='finalize'
        snap=self.snapshot()
        if extra:snap['extra']=dict(extra)
        self.owner._last_performance_snapshot=snap
        if self.save_report and run_dir:
            try:self._write_report(Path(run_dir),snap)
            except Exception:pass
        if getattr(self.owner,'_active_performance_monitor',None) is self:self.owner._active_performance_monitor=None
        self.owner._active_memory_policy=None
        return snap

    @staticmethod
    def _write_report(run_dir,snap):
        run_dir.mkdir(parents=True,exist_ok=True);jp=run_dir/f'performance_report_v{VERSION}.json';tp=run_dir/f'performance_report_v{VERSION}.txt';jp.write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding='utf-8');tp.write_text(_format_performance_snapshot(snap),encoding='utf-8')


def _format_performance_snapshot(s):
    if not s:return '尚无性能数据。'
    lines=[f'IceHaloStack {s.get("version",VERSION)} Performance Monitor',f'Status: {s.get("status","—")}',f'Engine: {s.get("engine","—")}',f'Elapsed: {_format_seconds_short(s.get("elapsed_seconds",0))}','',f'Masters: {s.get("masters",0)}',f'Processed tasks: {s.get("processed_tasks",0)}',f'RAW decodes: {s.get("raw_decodes",0)} · {s.get("raw_decode_seconds",0.0):.3f}s',f'Stack: {s.get("stack_seconds",0.0):.3f}s',f'Node processing: {s.get("node_seconds",0.0):.3f}s',f'Output preparation: {s.get("output_prepare_seconds",0.0):.3f}s',f'Output queue wait / backpressure: {s.get("output_backpressure_seconds",0.0):.3f}s',f'Output encode/write: {s.get("output_write_seconds",0.0):.3f}s',f'FFmpeg: {s.get("ffmpeg_seconds",0.0):.3f}s',f'Frames written: {s.get("frames_written",0)}','',f'Peak IceHaloStack RAM: {_fmt_bytes(s.get("peak_rss_bytes",0))}',f'RAM Budget: {_fmt_bytes(s.get("ram_budget_bytes",0))}',f'Min system available RAM: {_fmt_bytes(s.get("min_system_available_bytes",0))}',f'Peak Frame Cache: {_fmt_bytes(s.get("peak_frame_cache_bytes",0))}',f'Frame Cache: Hit {s.get("frame_cache_hits",0)} / Miss {s.get("frame_cache_misses",0)} / Evict {s.get("frame_cache_evictions",0)} · Hit rate {float(s.get("frame_cache_hit_rate",0))*100:.1f}%',f'Shared DAG: Hit {s.get("dag_hits",0)} / Compute {s.get("dag_computes",0)} / Budget Skip {s.get("dag_budget_skips",0)} · Peak {_fmt_bytes(s.get("peak_dag_bytes",0))}',f'Output Queue Peak: {_fmt_bytes(s.get("peak_output_queue_bytes",0))}','',str(s.get('stability_text','')),'Disk Cache: OFF']
    nodes=s.get('node_seconds_by_type') or {}
    if nodes:
        counts=s.get('node_compute_count_by_type') or {};dh=s.get('dag_hits_by_node') or {};dc=s.get('dag_computes_by_node') or {}
        lines+=['','Node timing / DAG audit:']
        for k,v in sorted(nodes.items(),key=lambda kv:-float(kv[1])):
            n=int(counts.get(k,0));avg=(float(v)/n if n else 0.0)
            lines.append(f'  {k}: {float(v):.3f}s · Compute {n} · Avg {avg:.3f}s · DAG Hit {int(dh.get(k,0))} / Compute {int(dc.get(k,0))}')
    reusable=s.get('dag_reusable_by_node') or {}
    if reusable:lines+=['','DAG reusable uses by node:']+[f'  {k}: {int(v)}' for k,v in sorted(reusable.items())]
    if s.get('error'):lines+=['','Error:',str(s.get('error'))]
    return '\n'.join(lines)


def _show_performance_details(owner):
    perf=getattr(owner,'_active_performance_monitor',None);snap=perf.snapshot() if perf is not None else getattr(owner,'_last_performance_snapshot',None);messagebox.showinfo('Performance Monitor',_format_performance_snapshot(snap),parent=owner)


class RAMFrameCache:
    """Bounded RAM-only decoded-frame cache introduced in v0.9.4.18b and retained in v0.9.4.18g.

    It never serializes frames or masters. Under pressure it evicts LRU frames,
    disables prefetch, and falls back to re-decoding source files when needed.
    """
    def __init__(self, owner, ref_lum, policy):
        self.owner=owner; self.ref_lum=ref_lum; self.policy=dict(policy or {})
        self.limit_bytes=max(int(1*_GIB),int(self.policy.get('limit_bytes',4*_GIB)))
        self.cache_ceiling=max(0,int(self.limit_bytes*float(self.policy.get('frame_cache_share',0.45))))
        self.prefetch_count=max(0,int(self.policy.get('prefetch_count',2)))
        self.cache=OrderedDict();self.bytes_used=0;self.hits=0;self.misses=0;self.evictions=0
        self.lock=threading.RLock();self.futures={};self.executor=None;self.closed=False;self.pressure='Normal';self.estimated_frame_bytes=0
        if self.prefetch_count>0:
            self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='IHS-RAM-Prefetch')

    def _decode_direct(self,idx):
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:perf.touch('raw_decode')
        t=time.monotonic();img=self.owner._decode(idx,self.ref_lum).astype(_deps()[0].float32,copy=False)
        if perf is not None:perf.add_stage('raw_decode',time.monotonic()-t);perf.inc('raw_decodes',1)
        return img

    def _touch_pressure(self):
        total,avail=_system_memory_status();rss=_process_memory_rss();reserve=int(self.policy.get('system_reserve_bytes',4*_GIB))
        critical=(avail>0 and avail<max(512*_MIB,reserve//2)) or rss>self.limit_bytes*0.97
        high=(avail>0 and avail<reserve) or rss>self.limit_bytes*0.90
        elevated=rss>self.limit_bytes*0.80
        new='Critical' if critical else ('High' if high else ('Elevated' if elevated else 'Normal'))
        self.pressure=new
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:perf.record_pressure(new)
        if critical:self.trim_to(int(self.cache_ceiling*0.10))
        elif high:self.trim_to(int(self.cache_ceiling*0.40))
        if critical or high:
            # Native NumPy/rawpy buffers are normally released promptly; GC helps
            # Python containers relinquish references before the next decode.
            gc.collect()
        return new

    def trim_to(self,target):
        target=max(0,int(target))
        with self.lock:
            while self.cache and self.bytes_used>target:
                _,img=self.cache.popitem(last=False);self.bytes_used=max(0,self.bytes_used-int(getattr(img,'nbytes',0)));self.evictions+=1

    def discard(self,idx):
        """Release a frame known to be outside the future rolling window."""
        with self.lock:
            img=self.cache.pop(idx,None)
            if img is not None:self.bytes_used=max(0,self.bytes_used-int(getattr(img,'nbytes',0)))
            fut=self.futures.pop(idx,None)
        if fut is not None:
            try:fut.cancel()
            except Exception:pass

    def _store(self,idx,img):
        nb=int(getattr(img,'nbytes',0));self.estimated_frame_bytes=max(self.estimated_frame_bytes,nb)
        if nb<=0 or nb>self.cache_ceiling:return img
        self._touch_pressure()
        # Leave process headroom for rolling sum, node scratch and output buffers.
        rss=_process_memory_rss()
        if rss>self.limit_bytes*0.90 or self.pressure in ('High','Critical'):
            return img
        with self.lock:
            old=self.cache.pop(idx,None)
            if old is not None:self.bytes_used=max(0,self.bytes_used-int(getattr(old,'nbytes',0)))
            while self.cache and self.bytes_used+nb>self.cache_ceiling:
                _,victim=self.cache.popitem(last=False);self.bytes_used=max(0,self.bytes_used-int(getattr(victim,'nbytes',0)));self.evictions+=1
            if self.bytes_used+nb<=self.cache_ceiling:
                self.cache[idx]=img;self.bytes_used+=nb
        return img

    def get(self,idx):
        with self.lock:
            img=self.cache.pop(idx,None)
            if img is not None:
                self.cache[idx]=img;self.hits+=1;return img
            fut=self.futures.pop(idx,None)
        if fut is not None:
            try:
                img=fut.result();self.hits+=1;return self._store(idx,img)
            except Exception:
                pass
        self.misses+=1;img=self._decode_direct(idx);return self._store(idx,img)

    def _prefetch_decode(self,idx):
        if self.closed:return None
        return self._decode_direct(idx)

    def prefetch(self,indices):
        if self.closed or self.executor is None or self.prefetch_count<=0:return
        pressure=self._touch_pressure()
        if pressure in ('High','Critical'):return
        todo=[]
        with self.lock:
            for idx in indices:
                if idx in self.cache or idx in self.futures:continue
                todo.append(idx)
                if len(todo)>=self.prefetch_count:break
            # Bound outstanding decoded results as well as active work.
            room=max(0,self.prefetch_count-len(self.futures));todo=todo[:room]
            for idx in todo:self.futures[idx]=self.executor.submit(self._prefetch_decode,idx)

    def stats(self):
        with self.lock:
            return {'bytes':int(self.bytes_used),'frames':len(self.cache),'hits':int(self.hits),'misses':int(self.misses),'evictions':int(self.evictions),'prefetch_pending':len(self.futures),'pressure':self.pressure}

    def close(self):
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:
            try:perf.record_cache_stats(self.stats())
            except Exception:pass
        self.closed=True
        with self.lock:
            fs=list(self.futures.values());self.futures.clear();self.cache.clear();self.bytes_used=0
        for f in fs:
            try:f.cancel()
            except Exception:pass
        if self.executor is not None:
            try:self.executor.shutdown(wait=False,cancel_futures=True)
            except TypeError:self.executor.shutdown(wait=False)
            except Exception:pass
        self.executor=None;gc.collect()


def _next_window_incoming(groups, pos):
    if pos+1>=len(groups):return []
    cur=list(groups[pos]);nxt=list(groups[pos+1]);curset=set(cur)
    return [i for i in nxt if i not in curset]


def _iter_optimized_timelapse_masters(owner, groups, method, ref_lum=None, compatibility=False):
    """Yield timelapse masters using the v0.9.4.18g RAM-only performance core.

    The Stack Engine from 0.9.4.18a remains mathematically unchanged, while
    decoded source frames can now be reused by a bounded LRU ring/cache and a
    one-worker prefetch queue. The cache obeys the user's RAM Budget and never
    spills to disk. If RAM is tight, frames are simply re-decoded.
    """
    np, *_ = _deps()
    if not groups:
        return

    if compatibility:
        for g in groups:
            if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
            yield owner._stack_group(g, method, ref_lum)
        return

    policy=getattr(owner,'_active_memory_policy',None) or {
        'limit_bytes':_auto_ram_limit_bytes(),'system_reserve_bytes':max(int(4*_GIB),int((_system_memory_status()[0] or 0)*0.15)),
        'frame_cache_share':0.45,'prefetch_count':2,'strategy':'Balanced','disk_cache':False,
    }
    cache=RAMFrameCache(owner,ref_lum,policy)
    owner._active_frame_cache=cache
    mode=owner.mode.get()

    try:
        # Sliding / centered Mean: first sum once, then subtract outgoing and add
        # incoming frames. With enough RAM, outgoing frames are cache hits.
        if method == 'mean' and (mode.startswith('滑动') or mode.startswith('中心')):
            first=list(groups[0]);total=None
            for idx in first:
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                img=cache.get(idx)
                if total is None: total=img.copy()
                else: total+=img
            if total is None:return
            prev=first
            cache.prefetch(_next_window_incoming(groups,0))
            yield (total/float(len(first))).astype(np.float32,copy=False)
            for pos,g0 in enumerate(groups[1:],1):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                g=list(g0);prev_set=set(prev);curr_set=set(g)
                outgoing=[idx for idx in prev if idx not in curr_set]
                incoming=[idx for idx in g if idx not in prev_set]
                for idx in outgoing:
                    total-=cache.get(idx);cache.discard(idx)
                for idx in incoming: total+=cache.get(idx)
                cache.prefetch(_next_window_incoming(groups,pos))
                yield (total/float(len(g))).astype(np.float32,copy=False)
                prev=g
            return

        # Cumulative Mean / Maximum: one forward pass. Prefetch the next source
        # frames while the caller processes the current output master.
        if mode.startswith('累计'):
            target_ends=[len(g) for g in groups];target_pos=0;processed=0;master=None
            nfiles=len(owner.app.files)
            for idx in range(nfiles):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                img=cache.get(idx);processed+=1
                if master is None: master=img.copy()
                elif method=='maximum': np.maximum(master,img,out=master)
                else: master+=(img-master)/float(processed)
                cache.discard(idx)
                if target_pos<len(target_ends) and processed==target_ends[target_pos]:
                    cache.prefetch(range(idx+1,min(nfiles,idx+1+max(1,cache.prefetch_count))))
                    yield master.copy();target_pos+=1
                    if target_pos>=len(target_ends):break
            return

        # Leave-one-out Mean: build total once; excluded frames are cache hits
        # when budget permits and otherwise are safely re-decoded.
        if method=='mean' and mode.startswith('逐帧剔除'):
            n=len(owner.app.files)
            if n<2:return
            total=None
            for idx in range(n):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                img=cache.get(idx)
                if total is None:total=img.copy()
                else:total+=img
            all_indices=set(range(n))
            for pos,g in enumerate(groups):
                if owner.cancel_event.is_set(): raise InterruptedError('cancelled')
                excluded=list(all_indices.difference(g))
                if len(excluded)!=1:
                    yield owner._stack_group(g,method,ref_lum);continue
                if pos+1<len(groups):
                    nex=list(all_indices.difference(groups[pos+1]));cache.prefetch(nex[:1])
                img=cache.get(excluded[0])
                yield ((total-img)/float(n-1)).astype(np.float32,copy=False)
            return

        # Maximum sliding/centered/LOO remains exact compatibility path in b.
        for g in groups:
            if owner.cancel_event.is_set():raise InterruptedError('cancelled')
            yield owner._stack_group(g,method,ref_lum)
    finally:
        try:cache.close()
        finally:
            owner._active_frame_cache=None


def _timelapse_stack_engine_name(owner, method):
    """Human-readable engine name for status/diagnostics."""
    mode = owner.mode.get()
    if method == 'mean' and (mode.startswith('滑动') or mode.startswith('中心')):
        return 'Rolling Mean'
    if mode.startswith('累计'):
        return 'Incremental Maximum' if method == 'maximum' else 'Incremental Mean'
    if method == 'mean' and mode.startswith('逐帧剔除'):
        return 'Total-Sum Leave-One-Out Mean'
    if method == 'maximum' and (mode.startswith('滑动') or mode.startswith('中心') or mode.startswith('逐帧剔除')):
        return 'Compatibility Maximum'
    return 'Compatibility'


def detect_system_cuda_toolkit():
    """Detect a system CUDA Toolkit without changing it.

    Priority: CUDA_PATH -> nvcc on PATH -> Program Files CUDA directories.
    nvidia-smi's 'CUDA Version' is deliberately NOT used because that is the
    maximum CUDA version supported by the driver, not necessarily the installed Toolkit.
    Returns (version_string_or_None, path_or_None, source_string).
    """
    candidates = []
    env_path = os.environ.get('CUDA_PATH')
    if env_path:
        candidates.append((env_path, 'CUDA_PATH'))

    try:
        p = subprocess.run(['nvcc', '--version'], capture_output=True, text=True, timeout=3, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        text = (p.stdout or '') + '\n' + (p.stderr or '')
        m = re.search(r'release\s+(\d+\.\d+)', text, re.I)
        if m:
            nvcc_path = None
            try:
                w = subprocess.run(['where', 'nvcc'], capture_output=True, text=True, timeout=2, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if w.returncode == 0 and w.stdout.strip():
                    nvcc_path = str(Path(w.stdout.splitlines()[0].strip()).resolve().parent.parent)
            except Exception:
                pass
            return m.group(1), nvcc_path, 'nvcc'
    except Exception:
        pass

    for path, source in candidates:
        m = re.search(r'v?(\d+\.\d+)', str(path))
        if m and Path(path).exists():
            return m.group(1), str(path), source
        nvcc = Path(path) / 'bin' / 'nvcc.exe'
        if nvcc.exists():
            try:
                p = subprocess.run([str(nvcc), '--version'], capture_output=True, text=True, timeout=3, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                m2 = re.search(r'release\s+(\d+\.\d+)', (p.stdout or '') + (p.stderr or ''), re.I)
                if m2:
                    return m2.group(1), str(path), source
            except Exception:
                pass

    pf = os.environ.get('ProgramFiles', r'C:\Program Files')
    root = Path(pf) / 'NVIDIA GPU Computing Toolkit' / 'CUDA'
    if root.exists():
        found=[]
        for d in root.glob('v*'):
            m=re.match(r'v(\d+)\.(\d+)', d.name, re.I)
            if m:
                found.append(((int(m.group(1)), int(m.group(2))), d))
        if found:
            found.sort(reverse=True)
            (maj,minr), d=found[0]
            return f'{maj}.{minr}', str(d), 'Program Files'
    return None, None, 'not found'


def detect_nvidia_driver():
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if p.returncode==0 and p.stdout.strip():
            first=p.stdout.strip().splitlines()[0].split(',')
            if len(first)>=3:
                return first[0].strip(), first[1].strip(), first[2].strip()
    except Exception:
        pass
    return None, None, None


def detect_cuda_backend():
    """Return (available, description, cupy_module_or_None). CuPy is optional."""
    toolkit_ver, toolkit_path, toolkit_source = detect_system_cuda_toolkit()
    try:
        import cupy as cp
        count = int(cp.cuda.runtime.getDeviceCount())
        if count < 1:
            base = f'系统 CUDA {toolkit_ver}' if toolkit_ver else '系统 CUDA 未检测到'
            return False, base + ' · 未检测到 CUDA GPU', None
        dev = cp.cuda.Device(0)
        props = cp.cuda.runtime.getDeviceProperties(dev.id)
        name = props.get('name', b'NVIDIA GPU')
        if isinstance(name, bytes):
            name = name.decode(errors='replace')
        free_b, total_b = cp.cuda.runtime.memGetInfo()
        try:
            rt = int(cp.cuda.runtime.runtimeGetVersion())
            runtime_ver = f'{rt//1000}.{(rt%1000)//10}'
        except Exception:
            runtime_ver = '?'
        tk = f' · Toolkit {toolkit_ver}' if toolkit_ver else ''
        desc = f'{name} · VRAM {total_b/1024**3:.1f} GB · CuPy {cp.__version__} · Runtime {runtime_ver}{tk}'
        return True, desc, cp
    except Exception as e:
        gpu, drv, mem = detect_nvidia_driver()
        parts=[]
        if gpu: parts.append(gpu)
        if drv: parts.append('Driver '+drv)
        if toolkit_ver: parts.append('Toolkit '+toolkit_ver)
        parts.append('CuPy 未就绪：'+e.__class__.__name__)
        return False, ' · '.join(parts), None


def choose_stack_backend(requested='自动'):
    if requested in ('自动','NVIDIA CUDA'):
        ok, desc, cp = detect_cuda_backend()
        if ok:
            return 'CUDA', desc, cp
        if requested == 'NVIDIA CUDA':
            return 'CPU', desc + '，已回退 CPU', None
    return 'CPU', 'NumPy CPU', None

def srgb_to_linear(arr):
    np, *_ = _deps()
    a = 0.055
    return np.where(arr <= 0.04045, arr/12.92, ((arr+a)/(1+a))**2.4).astype(np.float32)


def linear_to_srgb(arr):
    np, *_ = _deps()
    x = np.clip(arr, 0, 1)
    a = 0.055
    return np.where(x <= 0.0031308, 12.92*x, (1+a)*np.power(x,1/2.4)-a).astype(np.float32)


def read_linear_rgb(path: str):
    np, tifffile, Image, *_rest = _deps()
    rawpy = _rest[2]
    p = Path(path); ext = p.suffix.lower()
    if ext in RAW_EXTS:
        if rawpy is None:
            raise RuntimeError('RAW 解码组件 rawpy 未正确安装。')
        with rawpy.imread(str(p)) as raw:
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                use_auto_wb=False,
                no_auto_bright=True,
                gamma=(1,1),
                output_bps=16,
            )
        return rgb16.astype(np.float32) / 65535.0

    if ext in {'.tif','.tiff'}:
        arr = np.asarray(tifffile.imread(str(p)))
        if arr.ndim == 2:
            arr = np.repeat(arr[...,None], 3, axis=2)
        elif arr.ndim == 3 and arr.shape[-1] >= 3:
            arr = arr[...,:3]
        else:
            raise RuntimeError(f'不支持的 TIFF 数据形状：{arr.shape}')
        if np.issubdtype(arr.dtype, np.integer):
            arr = arr.astype(np.float32) / float(np.iinfo(arr.dtype).max)
        else:
            arr = arr.astype(np.float32)
        return arr

    if ext in {'.png','.jpg','.jpeg','.bmp'}:
        with Image.open(str(p)) as im:
            arr = np.asarray(im.convert('RGB'), dtype=np.float32) / 255.0
        return srgb_to_linear(arr)
    raise RuntimeError(f'不支持的文件格式：{p.suffix}')


def robust_luminance(img):
    np, *_ = _deps()
    lum = 0.2126*img[...,0] + 0.7152*img[...,1] + 0.0722*img[...,2]
    sample = lum[::8, ::8]
    q20, q80 = np.quantile(sample, [0.20, 0.80])
    core = sample[(sample >= q20) & (sample <= q80)]
    return float(np.median(core if core.size else sample))




# -----------------------------------------------------------------------------
# v0.9.5.2 — Keyframe-guided Exposure / White Balance Smoothing Workspace
# Global pre-stack correction. Source files are read-only. Analysis metrics,
# anchor points, correction tables, thumbnails and preview proxies stay in RAM.
# Every frame that enters the Stack Engine is corrected in linear RGB first.
# -----------------------------------------------------------------------------

def _ewb_default_config():
    return {
        'exposure_enabled': False,
        'wb_enabled': False,
        'deflicker_enabled': False,
        'deflicker_strength': 100.0,
        'deflicker_radius': 3,
        'exposure_strength': 100.0,
        'exposure_radius': 20,
        'exposure_max_ev': 0.70,
        'wb_strength': 100.0,
        'wb_radius': 30,
        'wb_max_percent': 15.0,
        'anchor_influence': 100.0,
        'smoothing_amount': 50.0,
        'multi_pass_enabled': False,
        'smoothing_passes': 2,
        'additional_smoothing_rounds': 0,
        'analysis_region': '自动有效区域',
        'roi_x': 10.0,
        'roi_y': 10.0,
        'roi_w': 80.0,
        'roi_h': 80.0,
        'proxy_max_side': 512,
        'preview_proxy_max_side': 800,
        'thumbnail_max_side': 144,
    }


def _init_ewb_vars(owner):
    d=_ewb_default_config()
    owner.ewb_exposure_enabled=tk.BooleanVar(value=d['exposure_enabled'])
    owner.ewb_wb_enabled=tk.BooleanVar(value=d['wb_enabled'])
    owner.ewb_deflicker_enabled=tk.BooleanVar(value=d['deflicker_enabled'])
    owner.ewb_deflicker_strength=tk.DoubleVar(value=d['deflicker_strength'])
    owner.ewb_deflicker_radius=tk.IntVar(value=d['deflicker_radius'])
    owner.ewb_exposure_strength=tk.DoubleVar(value=d['exposure_strength'])
    owner.ewb_exposure_radius=tk.IntVar(value=d['exposure_radius'])
    owner.ewb_exposure_max_ev=tk.DoubleVar(value=d['exposure_max_ev'])
    owner.ewb_wb_strength=tk.DoubleVar(value=d['wb_strength'])
    owner.ewb_wb_radius=tk.IntVar(value=d['wb_radius'])
    owner.ewb_wb_max_percent=tk.DoubleVar(value=d['wb_max_percent'])
    owner.ewb_anchor_influence=tk.DoubleVar(value=d['anchor_influence'])
    owner.ewb_smoothing_amount=tk.DoubleVar(value=d['smoothing_amount'])
    owner.ewb_multi_pass_enabled=tk.BooleanVar(value=d['multi_pass_enabled'])
    owner.ewb_smoothing_passes=tk.IntVar(value=d['smoothing_passes'])
    owner.ewb_analysis_region=tk.StringVar(value=d['analysis_region'])
    owner.ewb_roi_x=tk.DoubleVar(value=d['roi_x']); owner.ewb_roi_y=tk.DoubleVar(value=d['roi_y'])
    owner.ewb_roi_w=tk.DoubleVar(value=d['roi_w']); owner.ewb_roi_h=tk.DoubleVar(value=d['roi_h'])
    owner.ewb_status=tk.StringVar(value='未启用')
    owner._ewb_measurements=None
    owner._ewb_measurement_signature=None
    owner._ewb_table=None
    owner._ewb_display_table=None
    owner._ewb_correction_signature=None
    owner._ewb_analysis_running=False
    owner._ewb_analysis_dialog=None
    owner._ewb_analysis_cancel=None
    owner._ewb_anchors=[]
    owner._ewb_additional_smoothing_rounds=0
    owner._ewb_proxy_cache=OrderedDict()
    owner._ewb_proxy_cache_limit=20


def _ewb_config_snapshot(owner):
    def gv(name,default):
        try:return getattr(owner,name).get()
        except Exception:return default
    d=_ewb_default_config()
    d.update({
        'exposure_enabled':bool(gv('ewb_exposure_enabled',False)),
        'wb_enabled':bool(gv('ewb_wb_enabled',False)),
        'deflicker_enabled':bool(gv('ewb_deflicker_enabled',False)),
        'deflicker_strength':max(0.0,min(100.0,float(gv('ewb_deflicker_strength',d['deflicker_strength'])))),
        'deflicker_radius':max(1,min(60,int(gv('ewb_deflicker_radius',d['deflicker_radius'])))),
        'exposure_strength':max(0.0,min(100.0,float(gv('ewb_exposure_strength',d['exposure_strength'])))),
        'exposure_radius':max(1,int(gv('ewb_exposure_radius',d['exposure_radius']))),
        'exposure_max_ev':max(0.0,min(5.0,float(gv('ewb_exposure_max_ev',d['exposure_max_ev'])))),
        'wb_strength':max(0.0,min(100.0,float(gv('ewb_wb_strength',d['wb_strength'])))),
        'wb_radius':max(1,int(gv('ewb_wb_radius',d['wb_radius']))),
        'wb_max_percent':max(0.0,min(100.0,float(gv('ewb_wb_max_percent',d['wb_max_percent'])))),
        'anchor_influence':max(0.0,min(100.0,float(gv('ewb_anchor_influence',d['anchor_influence'])))),
        'smoothing_amount':max(0.0,min(100.0,float(gv('ewb_smoothing_amount',d['smoothing_amount'])))),
        'multi_pass_enabled':bool(gv('ewb_multi_pass_enabled',d['multi_pass_enabled'])),
        'smoothing_passes':max(1,min(10,int(gv('ewb_smoothing_passes',d['smoothing_passes'])))),
        'additional_smoothing_rounds':max(0,int(getattr(owner,'_ewb_additional_smoothing_rounds',d['additional_smoothing_rounds']) or 0)),
        'analysis_region':str(gv('ewb_analysis_region',d['analysis_region'])),
        'roi_x':max(0.0,min(100.0,float(gv('ewb_roi_x',d['roi_x'])))),
        'roi_y':max(0.0,min(100.0,float(gv('ewb_roi_y',d['roi_y'])))),
        'roi_w':max(1.0,min(100.0,float(gv('ewb_roi_w',d['roi_w'])))),
        'roi_h':max(1.0,min(100.0,float(gv('ewb_roi_h',d['roi_h'])))),
        'anchors':copy.deepcopy(getattr(owner,'_ewb_anchors',[]) or []),
    })
    if d['roi_x']+d['roi_w']>100:d['roi_w']=max(1.0,100.0-d['roi_x'])
    if d['roi_y']+d['roi_h']>100:d['roi_h']=max(1.0,100.0-d['roi_y'])
    return d


def _ewb_enabled(owner):
    try:
        if owner.ewb_exposure_enabled.get() or owner.ewb_wb_enabled.get() or owner.ewb_deflicker_enabled.get():return True
        return any(any(abs(float(a.get(k,0.0)))>1e-9 for k in _EWB_TONE_KEYS) for a in (getattr(owner,'_ewb_anchors',[]) or []))
    except Exception:return False


def _ewb_files_signature(owner):
    """Return a cheap identity for the sequence currently loaded by the app.

    File metadata used to be read here for every signature comparison.  This
    function is called from several Tk callbacks, so a sequence on a slow disk
    could make a newly-created workspace stop painting while hundreds of
    synchronous ``stat`` calls completed.  The input list is owned by the app
    and is replaced whenever the imported sequence changes; its normalized path
    snapshot is therefore the correct in-session invalidation key and performs
    no disk I/O on the UI thread.
    """
    return tuple(os.path.normcase(os.path.abspath(str(x))) for x in list(getattr(owner.app,'files',[]) or []))


def _ewb_measurement_signature_for(owner,cfg=None):
    cfg=cfg or _ewb_config_snapshot(owner)
    analysis=(cfg.get('analysis_region'),round(float(cfg.get('roi_x',0)),4),round(float(cfg.get('roi_y',0)),4),round(float(cfg.get('roi_w',100)),4),round(float(cfg.get('roi_h',100)),4),int(cfg.get('proxy_max_side',512)))
    return (_ewb_files_signature(owner),analysis)


def _ewb_anchor_signature(anchors):
    clean=[]
    for a in anchors or []:
        try:
            clean.append((int(a.get('frame',0)),round(float(a.get('exposure',0.0)),6),round(float(a.get('temperature',0.0)),6),round(float(a.get('tint',0.0)),6),round(float(a.get('contrast',0.0)),6),round(float(a.get('highlights',0.0)),6),round(float(a.get('shadows',0.0)),6),round(float(a.get('whites',0.0)),6),round(float(a.get('blacks',0.0)),6)))
        except Exception:pass
    return tuple(sorted(clean))


def _ewb_correction_signature_for(owner,cfg=None):
    cfg=cfg or _ewb_config_snapshot(owner)
    keys=('exposure_enabled','wb_enabled','deflicker_enabled','deflicker_strength','deflicker_radius','exposure_strength','exposure_radius','exposure_max_ev','wb_strength','wb_radius','wb_max_percent','anchor_influence','smoothing_amount','multi_pass_enabled','smoothing_passes','additional_smoothing_rounds')
    vals=tuple((k,cfg.get(k)) for k in keys)
    return (_ewb_measurement_signature_for(owner,cfg),vals,_ewb_anchor_signature(cfg.get('anchors',[])))


def _ewb_signature(owner):
    return _ewb_correction_signature_for(owner)


def _ewb_invalidate(owner, reason='设置已改变', analysis=False, preserve_rounds=False):
    if not preserve_rounds:owner._ewb_additional_smoothing_rounds=0
    if analysis:
        owner._ewb_measurements=None;owner._ewb_measurement_signature=None
        owner._ewb_display_table=None
        try:owner._ewb_proxy_cache.clear()
        except Exception:pass
    # Keep the last curve snapshot visible while keyframes/settings are edited.
    # It is display-only: frame correction always reads _ewb_table, which is
    # cleared here, so stale values can never leak into export or preview.
    if not analysis and getattr(owner,'_ewb_table',None) is not None:owner._ewb_display_table=owner._ewb_table
    owner._ewb_table=None;owner._ewb_correction_signature=None
    try:owner.ewb_status.set((reason+'，需要重新分析') if analysis and _ewb_enabled(owner) else (reason if _ewb_enabled(owner) else '未启用'))
    except Exception:pass
    # A reference master made from a different pre-stack correction is invalid.
    try:
        if owner.reference_master is not None:
            owner.reference_master=None
            if hasattr(owner,'preview_title'):owner.preview_title.set('曝光/白平衡平滑设置已改变，请重新生成参考堆栈')
            if hasattr(owner,'pipeline_locked'):owner.pipeline_locked=False
            if hasattr(owner,'start_btn'):owner.start_btn.configure(state='disabled')
    except Exception:pass
    try:
        if hasattr(owner,'_draw_graph'):owner._draw_graph()
    except Exception:pass


def _ewb_resize_float(img,max_side=512):
    np,_,Image,_,_,_,cv2=_deps();h,w=img.shape[:2];m=max(h,w)
    if m<=max_side:return img.astype(np.float32,copy=False)
    scale=float(max_side)/float(m);nw=max(2,int(round(w*scale)));nh=max(2,int(round(h*scale)))
    if cv2 is not None:return cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA).astype(np.float32,copy=False)
    chans=[np.asarray(Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.BILINEAR),dtype=np.float32) for k in range(3)]
    return np.stack(chans,axis=2)


def read_analysis_proxy(path,max_side=512):
    """Decode a low-resolution linear RGB proxy without writing temporary files."""
    np,tifffile,Image,*rest=_deps();rawpy=rest[2];pp=Path(path);ext=pp.suffix.lower()
    if ext in RAW_EXTS:
        if rawpy is None:raise RuntimeError('RAW 解码组件 rawpy 未正确安装。')
        with rawpy.imread(str(pp)) as raw:
            rgb16=raw.postprocess(use_camera_wb=True,use_auto_wb=False,no_auto_bright=True,gamma=(1,1),output_bps=16,half_size=True)
        return _ewb_resize_float(rgb16.astype(np.float32)/65535.0,max_side)
    if ext in {'.jpg','.jpeg','.png','.bmp'}:
        with Image.open(str(pp)) as im:
            im=im.convert('RGB');im.thumbnail((max_side,max_side),Image.Resampling.BILINEAR);arr=np.asarray(im,dtype=np.float32)/255.0
        return srgb_to_linear(arr)
    return _ewb_resize_float(read_linear_rgb(str(pp)),max_side)


def _ewb_analysis_crop(img,cfg):
    if cfg.get('analysis_region')!='自定义 ROI':return img
    h,w=img.shape[:2];x0=int(round(w*cfg['roi_x']/100.0));y0=int(round(h*cfg['roi_y']/100.0));x1=int(round(w*(cfg['roi_x']+cfg['roi_w'])/100.0));y1=int(round(h*(cfg['roi_y']+cfg['roi_h'])/100.0))
    x0=max(0,min(w-1,x0));y0=max(0,min(h-1,y0));x1=max(x0+1,min(w,x1));y1=max(y0+1,min(h,y1));return img[y0:y1,x0:x1]


def _ewb_measure_proxy(img,cfg):
    """Return robust exposure and spatially balanced chroma metrics.

    A global RGB median follows scene composition.  Moving cloud edges or a
    coloured object can then be mistaken for a WB change and the correction
    itself creates green/magenta flicker.  Equal-weight cells plus the least
    chromatic samples in each cell make the statistic follow the illuminant.
    """
    np,*_=_deps();x=_ewb_analysis_crop(img,cfg).astype(np.float32,copy=False)
    if x.size<12:raise RuntimeError('曝光/白平衡分析区域太小。')
    r=x[...,0];g=x[...,1];b=x[...,2];lum=0.2126*r+0.7152*g+0.0722*b
    finite=np.isfinite(lum)&np.isfinite(r)&np.isfinite(g)&np.isfinite(b);maxc=np.maximum(np.maximum(r,g),b);minc=np.minimum(np.minimum(r,g),b)
    valid=finite&(lum>1e-5)&(maxc<0.985)&(g>1e-5)&(r>1e-5)&(b>1e-5);vals=lum[valid]
    if vals.size<64:valid=finite&(lum>1e-6)&(maxc<0.998)&(g>1e-6)&(r>1e-6)&(b>1e-6);vals=lum[valid]
    if vals.size<16:raise RuntimeError('当前帧没有足够的有效像素用于曝光/白平衡分析。')
    qlo,qhi=np.quantile(vals,[0.12,0.88]);valid&=(lum>=qlo)&(lum<=qhi)
    if cfg.get('analysis_region')=='自动有效区域':
        sat=(maxc-minc)/np.maximum(maxc,1e-5);auto=valid&(sat<0.88)
        if int(np.count_nonzero(auto))>=64:valid=auto
    exposure=float(np.median(np.log2(np.maximum(lum[valid],1e-7))))
    h,w=x.shape[:2];cell_r=[];cell_b=[]
    for gy in range(4):
        y0=gy*h//4;y1=(gy+1)*h//4
        for gx in range(4):
            x0=gx*w//4;x1=(gx+1)*w//4;vm=valid[y0:y1,x0:x1]
            if int(np.count_nonzero(vm))<24:continue
            cr=np.log(np.maximum(r[y0:y1,x0:x1][vm],1e-7)/np.maximum(g[y0:y1,x0:x1][vm],1e-7))
            cb=np.log(np.maximum(b[y0:y1,x0:x1][vm],1e-7)/np.maximum(g[y0:y1,x0:x1][vm],1e-7))
            chroma=np.hypot(cr-cb,0.70*(cr+cb));cut=float(np.quantile(chroma,0.40));keep=chroma<=cut
            if int(np.count_nonzero(keep))>=8:cr=cr[keep];cb=cb[keep]
            cell_r.append(float(np.median(cr)));cell_b.append(float(np.median(cb)))
    if len(cell_r)>=3:return exposure,float(np.median(cell_r)),float(np.median(cell_b))
    rr=np.maximum(r[valid],1e-7);gg=np.maximum(g[valid],1e-7);bb=np.maximum(b[valid],1e-7)
    return exposure,float(np.median(np.log(rr/gg))),float(np.median(np.log(bb/gg)))


def _ewb_median_filter_1d(values,radius):
    np,*_=_deps();a=np.asarray(values,dtype=np.float64);n=len(a);r=max(1,int(radius));out=np.empty_like(a)
    for i in range(n):out[i]=np.median(a[max(0,i-r):min(n,i+r+1)])
    return out


def _ewb_clean_outliers(values,radius):
    np,*_=_deps();a=np.asarray(values,dtype=np.float64);r=max(2,min(15,int(radius)//3 or 2));med=_ewb_median_filter_1d(a,r);resid=np.abs(a-med);mad=_ewb_median_filter_1d(resid,r);sigma=1.4826*np.maximum(mad,1e-8);out=a.copy();mask=resid>3.5*sigma;out[mask]=med[mask];return out


def _ewb_clean_chroma_joint(rlog,blog,radius):
    """Reject chroma outliers as temperature/tint vectors, not two channels."""
    np,*_=_deps();r=np.asarray(rlog,dtype=np.float64);b=np.asarray(blog,dtype=np.float64)
    temp=0.5*(r-b);tint=0.5*(r+b);rad=max(2,min(15,int(radius)//3 or 2))
    mt=_ewb_median_filter_1d(temp,rad);mi=_ewb_median_filter_1d(tint,rad)
    distance=np.hypot(temp-mt,tint-mi);mad=_ewb_median_filter_1d(distance,rad)
    bad=distance>3.25*1.4826*np.maximum(mad,1e-6)
    temp=temp.copy();tint=tint.copy();temp[bad]=mt[bad];tint[bad]=mi[bad]
    return temp+tint,tint-temp


def _ewb_smooth_chroma_joint(rlog,blog,radius,passes):
    """Smooth the physical temperature/tint axes and reconstruct R/G, B/G."""
    np,*_=_deps();r=np.asarray(rlog,dtype=np.float64);b=np.asarray(blog,dtype=np.float64)
    temp=0.5*(r-b);tint=0.5*(r+b)
    for _pass in range(max(1,int(passes))):
        temp=_ewb_gaussian_smooth_1d(temp,radius);tint=_ewb_gaussian_smooth_1d(tint,radius)
    return temp+tint,tint-temp


def _ewb_gaussian_smooth_1d(values,radius):
    np,*_=_deps();a=np.asarray(values,dtype=np.float64);n=len(a);r=max(1,min(max(1,n-1),int(radius)))
    if n<3 or r<=1:return a.copy()
    sigma=max(1.0,r/2.5);x=np.arange(-r,r+1,dtype=np.float64);k=np.exp(-0.5*(x/sigma)**2);k/=np.sum(k);pad=np.pad(a,(r,r),mode='reflect' if n>1 else 'edge');return np.convolve(pad,k,mode='valid')


def _ewb_temp_tint_to_log_delta(temperature,tint):
    """Relative UI Temperature/Tint (-100..100), not Kelvin, to log chroma deltas."""
    t=max(-100.0,min(100.0,float(temperature)))/100.0*0.18
    m=max(-100.0,min(100.0,float(tint)))/100.0*0.10
    return t+m,-t+m


def _ewb_log_to_temp_tint(rlog,blog):
    np,*_=_deps();r=np.asarray(rlog,dtype=np.float64);b=np.asarray(blog,dtype=np.float64)
    # Display-only relative axes. They are intentionally not advertised as Kelvin/Mired.
    return (r-b)*50.0,(r+b)*50.0


def _ewb_anchor_residual_curve(base,raw,anchors,key,converter=None):
    np,*_=_deps();n=len(base)
    if not anchors:return np.zeros(n,dtype=np.float64)
    xs=[];ys=[]
    for a in sorted(anchors,key=lambda z:int(z.get('frame',0))):
        idx=max(0,min(n-1,int(a.get('frame',1))-1))
        if converter is None:desired=float(raw[idx])+float(a.get(key,0.0))
        else:desired=float(raw[idx])+float(converter(a)[key])
        xs.append(idx);ys.append(desired-float(base[idx]))
    if len(xs)==1:return np.full(n,ys[0],dtype=np.float64)
    # Duplicate frame anchors: keep the last value.
    uniq={int(x):float(y) for x,y in zip(xs,ys)};xs=np.array(sorted(uniq),dtype=np.float64);ys=np.array([uniq[int(x)] for x in xs],dtype=np.float64)
    return np.interp(np.arange(n,dtype=np.float64),xs,ys,left=ys[0],right=ys[-1])


_EWB_TONE_KEYS=('contrast','highlights','shadows','whites','blacks')


def _ewb_direct_anchor_curve(n,anchors,key,influence=1.0):
    """Interpolate one ACR-style keyframe control across every source frame."""
    np,*_=_deps()
    if n<1 or not anchors:return np.zeros(max(0,n),dtype=np.float64)
    uniq={}
    for a in sorted(anchors,key=lambda z:int(z.get('frame',0))):
        idx=max(0,min(n-1,int(a.get('frame',1))-1));uniq[idx]=float(a.get(key,0.0))*float(influence)
    xs=np.asarray(sorted(uniq),dtype=np.float64);ys=np.asarray([uniq[int(x)] for x in xs],dtype=np.float64)
    if len(xs)==1:return np.full(n,ys[0],dtype=np.float64)
    return np.interp(np.arange(n,dtype=np.float64),xs,ys,left=ys[0],right=ys[-1])


def _ewb_smooth_direct_anchor_curve(values,anchors,key,radius,passes,amount,influence=1.0):
    """Smooth a direct tone curve while keeping every keyframe value exact."""
    np,*_=_deps();base=np.asarray(values,dtype=np.float64);out=base.copy()
    if amount>1e-9:
        for _pass in range(max(1,int(passes))):out=_ewb_gaussian_smooth_1d(out,radius)
    n=len(out)
    for a in anchors or []:
        idx=max(0,min(n-1,int(a.get('frame',1))-1));out[idx]=float(a.get(key,0.0))*float(influence)
    return out


def _ewb_build_correction_table(exposure,rlog,blog,cfg,anchors=None,progress=None):
    np,*_=_deps();e=np.asarray(exposure,dtype=np.float64);r=np.asarray(rlog,dtype=np.float64);b=np.asarray(blog,dtype=np.float64);n=len(e)
    if n<1:raise RuntimeError('没有可分析的帧。')
    anchors=copy.deepcopy(anchors if anchors is not None else cfg.get('anchors',[]))
    if progress is not None:progress(8,'正在清理曝光与白平衡测量曲线…')
    ec=_ewb_clean_outliers(e,cfg['exposure_radius']);rc,bc=_ewb_clean_chroma_joint(r,b,cfg['wb_radius'])
    amount=max(0.0,min(100.0,float(cfg.get('smoothing_amount',50.0))))
    scale=amount/50.0
    eradius=max(1,int(round(float(cfg['exposure_radius'])*max(0.05,scale))))
    wradius=max(1,int(round(float(cfg['wb_radius'])*max(0.05,scale))))
    passes=max(1,min(10,int(cfg.get('smoothing_passes',2)))) if cfg.get('multi_pass_enabled') else 1
    if amount<=1e-9:
        es=ec.copy();rs=rc.copy();bs=bc.copy()
    else:
        es=ec.copy()
        for _pass in range(passes):es=_ewb_gaussian_smooth_1d(es,eradius)
        rs,bs=_ewb_smooth_chroma_joint(rc,bc,wradius,passes)
    if progress is not None:progress(38,'正在生成曝光与白平衡过渡…')
    et=es.copy();rt=rs.copy();bt=bs.copy()
    influence=float(cfg.get('anchor_influence',100.0))/100.0
    if anchors and influence>0:
        er=_ewb_anchor_residual_curve(et,e,anchors,'exposure')
        def conv(a):
            dr,db=_ewb_temp_tint_to_log_delta(a.get('temperature',0.0),a.get('tint',0.0));return {'r':dr,'b':db}
        rr=_ewb_anchor_residual_curve(rt,r,anchors,'r',conv);br=_ewb_anchor_residual_curve(bt,b,anchors,'b',conv)
        et=et+influence*er;rt=rt+influence*rr;bt=bt+influence*br
    # Separate slow exposure drift from short frame-to-frame flicker.  At 100%
    # for both controls this still resolves to the original target-minus-input
    # correction, while Deflicker can now work independently without flattening
    # intentional sunrise/sunset brightness changes.
    local_e=_ewb_gaussian_smooth_1d(e,int(cfg.get('deflicker_radius',3)))
    flicker=e-local_e
    ev=np.zeros(n,dtype=np.float64)
    if cfg.get('exposure_enabled'):ev+=(et-local_e)*(float(cfg['exposure_strength'])/100.0)
    if cfg.get('deflicker_enabled'):ev-=flicker*(float(cfg.get('deflicker_strength',100.0))/100.0)
    ev=np.clip(ev,-float(cfg['exposure_max_ev']),float(cfg['exposure_max_ev']))
    p=max(0.0,float(cfg['wb_max_percent']))/100.0;loglim=math.log1p(p) if p>0 else 0.0
    dr=(rt-r)*(float(cfg['wb_strength'])/100.0) if cfg.get('wb_enabled') else np.zeros(n);db=(bt-b)*(float(cfg['wb_strength'])/100.0) if cfg.get('wb_enabled') else np.zeros(n)
    # Limit the correction as one chroma vector. Independent channel clipping
    # changes its hue at the limit and is visible as green/magenta pumping.
    if loglim>0:
        mag=np.hypot(dr,db);scale_lim=np.minimum(1.0,loglim/np.maximum(mag,1e-12));dr*=scale_lim;db*=scale_lim
    else:dr*=0;db*=0
    tone={}
    for pos,key in enumerate(_EWB_TONE_KEYS):
        direct=_ewb_direct_anchor_curve(n,anchors,key,influence)
        tone[key+'_correction']=_ewb_smooth_direct_anchor_curve(direct,anchors,key,eradius,passes,amount,influence).astype(np.float32)
        if progress is not None:progress(48+int((pos+1)*32/len(_EWB_TONE_KEYS)),f'正在插值 {key} 关键帧参数…')
    temp_raw,tint_raw=_ewb_log_to_temp_tint(r,b);temp_smooth,tint_smooth=_ewb_log_to_temp_tint(rs,bs);temp_target,tint_target=_ewb_log_to_temp_tint(rt,bt)
    result={'exposure_metric':e.astype(np.float32),'rlog_metric':r.astype(np.float32),'blog_metric':b.astype(np.float32),'exposure_smooth':es.astype(np.float32),'rlog_smooth':rs.astype(np.float32),'blog_smooth':bs.astype(np.float32),'exposure_target':et.astype(np.float32),'rlog_target':rt.astype(np.float32),'blog_target':bt.astype(np.float32),'flicker_metric':flicker.astype(np.float32),'deflicker_correction':(-flicker*(float(cfg.get('deflicker_strength',100.0))/100.0)).astype(np.float32),'temp_metric':temp_raw.astype(np.float32),'tint_metric':tint_raw.astype(np.float32),'temp_smooth':temp_smooth.astype(np.float32),'tint_smooth':tint_smooth.astype(np.float32),'temp_target':temp_target.astype(np.float32),'tint_target':tint_target.astype(np.float32),'ev_correction':ev.astype(np.float32),'r_gain':np.exp(dr).astype(np.float32),'b_gain':np.exp(db).astype(np.float32),'config':copy.deepcopy(cfg),'anchors':copy.deepcopy(anchors),'count':n,'smoothing_amount':amount,'smoothing_passes':passes,'additional_smoothing_rounds':0}
    result.update(tone)
    if progress is not None:progress(88,'正在完成修正表…')
    return result


def _ewb_apply_additional_smoothing_round(table,cfg):
    """Smooth an already-generated transition one more cumulative round.

    This is intentionally different from ``multi_pass_enabled``.  Multi-pass
    controls how a single round is calculated; this function takes that round's
    finished target curves as its new input.  Existing keyframe values are pinned
    after the filter so repeated smoothing never silently changes the grades the
    user set on those keyframes.
    """
    np,*_=_deps();amount=max(0.0,min(100.0,float(cfg.get('smoothing_amount',50.0))));scale=amount/50.0
    eradius=max(1,int(round(float(cfg.get('exposure_radius',20))*max(0.05,scale))));wradius=max(1,int(round(float(cfg.get('wb_radius',30))*max(0.05,scale))))
    passes=max(1,min(10,int(cfg.get('smoothing_passes',2)))) if cfg.get('multi_pass_enabled') else 1
    et0=np.asarray(table['exposure_target'],dtype=np.float64);rt0=np.asarray(table['rlog_target'],dtype=np.float64);bt0=np.asarray(table['blog_target'],dtype=np.float64)
    es=et0.copy();rs=rt0.copy();bs=bt0.copy()
    if amount>1e-9:
        for _pass in range(passes):es=_ewb_gaussian_smooth_1d(es,eradius)
        rs,bs=_ewb_smooth_chroma_joint(rs,bs,wradius,passes)
    et=es.copy();rt=rs.copy();bt=bs.copy();n=len(et)
    # Preserve the exact output target already reached at every keyframe.  This
    # also respects a non-100% keyframe influence from the first smoothing round.
    for a in table.get('anchors',[]) or []:
        idx=max(0,min(n-1,int(a.get('frame',1))-1));et[idx]=et0[idx];rt[idx]=rt0[idx];bt[idx]=bt0[idx]
    e=np.asarray(table['exposure_metric'],dtype=np.float64);r=np.asarray(table['rlog_metric'],dtype=np.float64);b=np.asarray(table['blog_metric'],dtype=np.float64)
    local_e=_ewb_gaussian_smooth_1d(e,int(cfg.get('deflicker_radius',3)));flicker=e-local_e;ev=np.zeros(n,dtype=np.float64)
    if cfg.get('exposure_enabled'):ev+=(et-local_e)*(float(cfg.get('exposure_strength',100.0))/100.0)
    if cfg.get('deflicker_enabled'):ev-=flicker*(float(cfg.get('deflicker_strength',100.0))/100.0)
    ev=np.clip(ev,-float(cfg.get('exposure_max_ev',0.7)),float(cfg.get('exposure_max_ev',0.7)))
    p=max(0.0,float(cfg.get('wb_max_percent',15.0)))/100.0;loglim=math.log1p(p) if p>0 else 0.0
    dr=(rt-r)*(float(cfg.get('wb_strength',100.0))/100.0) if cfg.get('wb_enabled') else np.zeros(n);db=(bt-b)*(float(cfg.get('wb_strength',100.0))/100.0) if cfg.get('wb_enabled') else np.zeros(n)
    if loglim>0:
        mag=np.hypot(dr,db);scale_lim=np.minimum(1.0,loglim/np.maximum(mag,1e-12));dr*=scale_lim;db*=scale_lim
    else:dr*=0;db*=0
    temp_smooth,tint_smooth=_ewb_log_to_temp_tint(rs,bs);temp_target,tint_target=_ewb_log_to_temp_tint(rt,bt);out=dict(table)
    out.update({'exposure_smooth':es.astype(np.float32),'rlog_smooth':rs.astype(np.float32),'blog_smooth':bs.astype(np.float32),'exposure_target':et.astype(np.float32),'rlog_target':rt.astype(np.float32),'blog_target':bt.astype(np.float32),'flicker_metric':flicker.astype(np.float32),'deflicker_correction':(-flicker*(float(cfg.get('deflicker_strength',100.0))/100.0)).astype(np.float32),'temp_smooth':temp_smooth.astype(np.float32),'tint_smooth':tint_smooth.astype(np.float32),'temp_target':temp_target.astype(np.float32),'tint_target':tint_target.astype(np.float32),'ev_correction':ev.astype(np.float32),'r_gain':np.exp(dr).astype(np.float32),'b_gain':np.exp(db).astype(np.float32),'config':copy.deepcopy(cfg),'additional_smoothing_rounds':int(table.get('additional_smoothing_rounds',0))+1})
    for key in _EWB_TONE_KEYS:
        name=key+'_correction';before=np.asarray(table.get(name,np.zeros(n)),dtype=np.float64);after=before.copy()
        if amount>1e-9:
            for _pass in range(passes):after=_ewb_gaussian_smooth_1d(after,eradius)
        for a in table.get('anchors',[]) or []:
            idx=max(0,min(n-1,int(a.get('frame',1))-1));after[idx]=before[idx]
        out[name]=after.astype(np.float32)
    return out

def _ewb_make_thumbnail(proxy,max_side=144):
    np,*_=_deps();x=_ewb_resize_float(proxy,max_side);disp=np.clip(linear_to_srgb(np.clip(x,0,None)),0,1);return np.round(disp*255.0).astype(np.uint8)


def _ewb_analyze_files(files,cfg,progress=None,cancel_event=None):
    exp=[];rr=[];bb=[];thumbs=[];n=len(files)
    for i,path in enumerate(files):
        if cancel_event is not None and cancel_event.is_set():raise InterruptedError('cancelled')
        proxy=read_analysis_proxy(path,int(cfg.get('proxy_max_side',512)));e,r,b=_ewb_measure_proxy(proxy,cfg);exp.append(e);rr.append(r);bb.append(b);thumbs.append(_ewb_make_thumbnail(proxy,int(cfg.get('thumbnail_max_side',144))))
        if progress is not None:progress(i+1,n,Path(path).name)
    return {'exposure_metric':_deps()[0].asarray(exp,dtype=_deps()[0].float32),'rlog_metric':_deps()[0].asarray(rr,dtype=_deps()[0].float32),'blog_metric':_deps()[0].asarray(bb,dtype=_deps()[0].float32),'thumbs':thumbs,'count':n,'config':copy.deepcopy(cfg)}


def _ewb_build_table_from_snapshot(measurements,cfg,progress=None):
    table=_ewb_build_correction_table(measurements['exposure_metric'],measurements['rlog_metric'],measurements['blog_metric'],cfg,cfg.get('anchors',[]),progress=progress)
    rounds=max(0,int(cfg.get('additional_smoothing_rounds',0)))
    for pos in range(rounds):
        table=_ewb_apply_additional_smoothing_round(table,cfg)
        if progress is not None:progress(89+int((pos+1)*8/max(1,rounds)),f'正在累计第 {pos+1} 轮再次平滑…')
    return table


def _ewb_rebuild_table(owner):
    m=getattr(owner,'_ewb_measurements',None);cfg=_ewb_config_snapshot(owner)
    if not m:return None
    if getattr(owner,'_ewb_measurement_signature',None)!=_ewb_measurement_signature_for(owner,cfg):return None
    table=_ewb_build_table_from_snapshot(m,cfg)
    owner._ewb_table=table;owner._ewb_display_table=table;owner._ewb_correction_signature=_ewb_correction_signature_for(owner,cfg)
    try:owner.ewb_status.set(_ewb_table_summary(table))
    except Exception:pass
    return table


def _ewb_apply_to_frame(owner,img,idx):
    """The only pre-stack correction step. It never modifies source files or clips HDR values."""
    table=getattr(owner,'_ewb_table',None)
    if table is None:return img
    try:
        if idx<0 or idx>=int(table.get('count',0)):return img
        ev=float(table['ev_correction'][idx]);rg=float(table['r_gain'][idx]);bg=float(table['b_gain'][idx]);tone={}
        for key in _EWB_TONE_KEYS:
            values=table.get(key+'_correction');tone[key]=float(values[idx]) if values is not None and idx<len(values) else 0.0
        if abs(ev)<1e-9 and abs(rg-1.0)<1e-9 and abs(bg-1.0)<1e-9 and all(abs(v)<1e-9 for v in tone.values()):return img
        out=img.astype(_deps()[0].float32,copy=True);out*=float(2.0**ev);out[...,0]*=rg;out[...,2]*=bg
        if any(abs(v)>1e-9 for v in tone.values()):out=apply_basic(out,0.0,tone['contrast'],tone['highlights'],tone['shadows'],tone['whites'],tone['blacks'],0.0,0.0,0.0,0.0)
        return out
    except Exception:return img


def _ewb_table_summary(table):
    if not table:return '未分析'
    np,*_=_deps();ev=np.asarray(table['ev_correction']);rg=np.asarray(table['r_gain']);bg=np.asarray(table['b_gain']);maxev=float(np.max(np.abs(ev))) if ev.size else 0.0;maxwb=max(float(np.max(np.abs(rg-1))) if rg.size else 0.0,float(np.max(np.abs(bg-1))) if bg.size else 0.0)*100.0;maxtone=max((float(np.max(np.abs(np.asarray(table.get(k+'_correction',[0.0]))))) for k in _EWB_TONE_KEYS),default=0.0);rounds=max(0,int(table.get('additional_smoothing_rounds',0) or 0));round_text=f' · 再次平滑 {rounds}' if rounds else ''
    return f'已分析 {int(table.get("count",0))} 帧 · 关键帧 {len(table.get("anchors",[]))}{round_text} · 曝光 ±{maxev:.2f} EV · WB ±{maxwb:.1f}% · 基础明暗 ±{maxtone:.0f}'


def _ewb_analyze_async(owner,on_done=None,parent=None):
    files=list(getattr(owner.app,'files',[]) or [])
    if not files:return
    if getattr(owner,'_ewb_analysis_running',False):
        existing=getattr(owner,'_ewb_analysis_dialog',None)
        try:existing.lift();existing.focus_force()
        except Exception:pass
        return
    cfg=_ewb_config_snapshot(owner);owner._ewb_analysis_running=True;parent=parent or owner
    dlg=tk.Toplevel(parent);dlg.title('分析曝光 / 白平衡');dlg.geometry('540x178');dlg.resizable(False,False);dlg.transient(parent)
    # Deliberately do not call grab_set().  Analysis is asynchronous, and a Tk
    # grab unnecessarily disables the workspace title bar (maximize/restore)
    # for the entire decode.  The running guard above still prevents duplicates.
    txt=tk.StringVar(value=f'准备分析 {len(files)} 帧…');pct=tk.DoubleVar(value=0.0);q=Queue();cancel=threading.Event()
    owner._ewb_analysis_dialog=dlg;owner._ewb_analysis_cancel=cancel
    body=ttk.Frame(dlg,padding=(14,14));body.pack(fill='both',expand=True)
    ttk.Label(body,textvariable=txt,wraplength=500).pack(fill='x',pady=(0,8));ttk.Progressbar(body,variable=pct,maximum=100).pack(fill='x')
    actions=ttk.Frame(body);actions.pack(fill='x',pady=(12,0));cancel_btn=ttk.Button(actions,text='取消分析');cancel_btn.pack(side='right')
    def close_req():
        cancel.set();txt.set('正在取消分析…')
        try:cancel_btn.configure(state='disabled')
        except Exception:pass
    cancel_btn.configure(command=close_req)
    dlg.protocol('WM_DELETE_WINDOW',close_req)
    def progress(i,n,name):q.put(('progress',(i,n,name)))
    def work():
        try:q.put(('done',_ewb_analyze_files(files,cfg,progress,cancel)))
        except InterruptedError:q.put(('cancel',None))
        except Exception as e:q.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
    threading.Thread(target=work,daemon=True).start()
    def finish_dialog():
        if getattr(owner,'_ewb_analysis_dialog',None) is dlg:owner._ewb_analysis_dialog=None
        if getattr(owner,'_ewb_analysis_cancel',None) is cancel:owner._ewb_analysis_cancel=None
        try:
            if dlg.winfo_exists():dlg.destroy()
        except Exception:pass
    def message_parent():
        try:
            if parent.winfo_exists():return parent
        except Exception:pass
        return owner
    def poll():
        try:
            while True:
                kind,val=q.get_nowait()
                if kind=='progress':i,n,name=val;pct.set(i/max(1,n)*100.0);txt.set(f'分析 {i}/{n}：{name}')
                elif kind=='done':
                    owner._ewb_measurements=val;owner._ewb_measurement_signature=_ewb_measurement_signature_for(owner,cfg);owner._ewb_analysis_running=False;_ewb_rebuild_table(owner);finish_dialog()
                    try:
                        if hasattr(owner,'_draw_graph'):owner._draw_graph()
                    except Exception:pass
                    if on_done:
                        try:on_done()
                        except Exception:pass
                    return
                elif kind=='cancel':owner._ewb_analysis_running=False;finish_dialog();return
                elif kind=='error':owner._ewb_analysis_running=False;finish_dialog();messagebox.showerror(APP_NAME,'分析失败：\n'+val,parent=message_parent());return
        except Empty:pass
        try:
            if owner.winfo_exists():owner.after(80,poll)
        except Exception:pass
    owner.after(80,poll);_enforce_regular_typography(dlg)


def _ewb_require_analysis(owner):
    if not _ewb_enabled(owner):return True
    cfg=_ewb_config_snapshot(owner)
    if getattr(owner,'_ewb_measurements',None) is not None and getattr(owner,'_ewb_measurement_signature',None)==_ewb_measurement_signature_for(owner,cfg):
        if getattr(owner,'_ewb_table',None) is None or getattr(owner,'_ewb_correction_signature',None)!=_ewb_correction_signature_for(owner,cfg):_ewb_rebuild_table(owner)
        return getattr(owner,'_ewb_table',None) is not None
    owner.ewb_status.set('需要分析')
    if messagebox.askyesno(APP_NAME,'已启用曝光 / 白平衡平滑，但当前素材尚未完成分析。\n\n现在打开平滑工作区吗？',parent=owner):_ewb_open_workspace(owner)
    return False


def _ewb_get_preview_proxy(owner,idx,max_side=800):
    cache=getattr(owner,'_ewb_proxy_cache',None)
    if cache is None:owner._ewb_proxy_cache=OrderedDict();cache=owner._ewb_proxy_cache
    key=(int(idx),int(max_side))
    img=cache.pop(key,None)
    if img is not None:cache[key]=img;return img
    files=list(getattr(owner.app,'files',[]) or [])
    if idx<0 or idx>=len(files):return None
    img=read_analysis_proxy(files[idx],max_side).astype(_deps()[0].float32,copy=False);cache[key]=img
    lim=max(4,int(getattr(owner,'_ewb_proxy_cache_limit',20)))
    while len(cache)>lim:cache.popitem(last=False)
    return img


def _ewb_apply_preview_adjustment(img,exposure=0.0,temperature=0.0,tint=0.0,contrast=0.0,highlights=0.0,shadows=0.0,whites=0.0,blacks=0.0):
    np,*_=_deps();dr,db=_ewb_temp_tint_to_log_delta(temperature,tint);out=img.astype(np.float32,copy=True);out*=float(2.0**float(exposure));out[...,0]*=math.exp(dr);out[...,2]*=math.exp(db)
    tone=(float(contrast),float(highlights),float(shadows),float(whites),float(blacks))
    if any(abs(v)>1e-9 for v in tone):out=apply_basic(out,0.0,*tone,0.0,0.0,0.0,0.0)
    return out


def _ewb_settings_dialog(owner):
    # v0.9.5.2: settings are part of the visual sequence/keyframe workspace.
    _ewb_open_workspace(owner)


def _ewb_show_curves(owner):
    _ewb_open_workspace(owner,focus_curves=True)


def _ewb_open_workspace(owner,focus_curves=False):
    files=list(getattr(owner.app,'files',[]) or [])
    if not files:messagebox.showinfo(APP_NAME,'请先导入输入序列。',parent=owner);return
    if getattr(owner,'_ewb_workspace',None) is not None:
        try:owner._ewb_workspace.lift();owner._ewb_workspace.focus_force();return
        except Exception:owner._ewb_workspace=None
    np,_,Image,ImageTk,*_=_deps();n=len(files)
    d=tk.Toplevel(owner);owner._ewb_workspace=d;d.title('曝光 / 白平衡平滑工作区');d.geometry('1420x920');d.minsize(1080,720);d.resizable(True,True)
    d.protocol('WM_DELETE_WINDOW',lambda:(_ewb_workspace_close(owner,d)))
    current=tk.IntVar(value=max(1,min(n,n//2 if n>1 else 1)));fps=tk.DoubleVar(value=10.0);view_mode=tk.StringVar(value='修正后');frame_text=tk.StringVar(value=f'正在准备 {n} 帧…');play_state={'running':False,'after':None,'epoch':0,'advancing':False};preview_state={'photo':None,'token':0,'img':None,'after':None,'loading':False,'pending':None,'quality':'empty','transition_applied':False,'fit':True,'zoom':1.0,'pan':[0.0,0.0],'pan_anchor':None,'image_item':None,'display_rect':None,'edit_frame':max(0,int(current.get())-1),'edit_loading':False};curve_state={'selected':current.get()};transition_state={'busy':False,'token':0}
    edit_exposure=tk.DoubleVar(value=0.0);edit_temp=tk.DoubleVar(value=0.0);edit_tint=tk.DoubleVar(value=0.0);edit_contrast=tk.DoubleVar(value=0.0);edit_highlights=tk.DoubleVar(value=0.0);edit_shadows=tk.DoubleVar(value=0.0);edit_whites=tk.DoubleVar(value=0.0);edit_blacks=tk.DoubleVar(value=0.0)
    edit_tone_vars={'contrast':edit_contrast,'highlights':edit_highlights,'shadows':edit_shadows,'whites':edit_whites,'blacks':edit_blacks}

    top=ttk.Frame(d,padding=(10,8));top.pack(fill='x')
    ttk.Checkbutton(top,text='去闪',variable=owner.ewb_deflicker_enabled,command=lambda:_ewb_workspace_param_changed(owner,False,refresh_all)).pack(side='left')
    ttk.Checkbutton(top,text='曝光平滑',variable=owner.ewb_exposure_enabled,command=lambda:_ewb_workspace_param_changed(owner,False,refresh_all)).pack(side='left')
    ttk.Checkbutton(top,text='白平衡平滑',variable=owner.ewb_wb_enabled,command=lambda:_ewb_workspace_param_changed(owner,False,refresh_all)).pack(side='left',padx=(12,0))
    ttk.Button(top,text='重新分析素材',command=lambda:_ewb_analyze_async(owner,on_done=refresh_all,parent=d)).pack(side='left',padx=(16,0))
    ttk.Label(top,textvariable=owner.ewb_status).pack(side='left',padx=12)
    done_btn=ttk.Button(top,text='完成');done_btn.pack(side='right')

    main=ttk.Panedwindow(d,orient='horizontal');main.pack(fill='both',expand=True,padx=10,pady=(0,8));left=ttk.Frame(main);right_host=ttk.Frame(main,width=320);main.add(left,weight=4);main.add(right_host,weight=2)
    # The settings column can be taller than the restored window.  Put the whole
    # column in the application's standard scrolling page so the wheel reaches
    # every smoothing/range/ROI control without requiring maximize.
    right,right_scroll_canvas,right_scroll_shell=_make_vertical_scroll_area(right_host)
    preview=tk.Canvas(left,bg='#111',highlightthickness=0,height=430);preview.pack(fill='both',expand=True)
    nav=ttk.Frame(left);nav.pack(fill='x',pady=(7,3));prev_btn=ttk.Button(nav,text='◀',width=4);prev_btn.pack(side='left');play_btn=ttk.Button(nav,text='▶ 播放',width=8);play_btn.pack(side='left',padx=4);next_btn=ttk.Button(nav,text='▶',width=4);next_btn.pack(side='left')
    ttk.Label(nav,textvariable=frame_text).pack(side='left',padx=10);ttk.Label(nav,text='预览 FPS').pack(side='right',padx=(8,3));fps_box=ttk.Combobox(nav,textvariable=fps,values=[1,2,5,10,15,24,30],width=6);fps_box.pack(side='right')
    modebox=ttk.Frame(nav);modebox.pack(side='right',padx=8)
    for txt,val in [('原始','原始'),('平滑后','修正后'),('左右对比','左右对比')]:ttk.Radiobutton(modebox,text=txt,value=val,variable=view_mode,command=lambda:_ewb_workspace_request_preview()).pack(side='left')
    timeline=tk.Scale(left,from_=1,to=n,orient='horizontal',variable=current,showvalue=0,resolution=1,highlightthickness=0);timeline.pack(fill='x')
    film=ttk.Frame(left);film.pack(fill='x',pady=(3,6));thumb_canvas=tk.Canvas(film,height=92,bg='#191919',highlightthickness=0);thumb_canvas.pack(fill='x')
    curves=tk.Canvas(left,height=285,bg='#111',highlightthickness=0);curves.pack(fill='x',pady=(0,4))

    # LRTimelapse-inspired keyframe workflow. The workspace remains an independent
    # top-level window with a native maximize button; keyframe management is placed
    # at the upper-right and every source frame is visible in the frame table.
    keyframe_count=tk.IntVar(value=max(2,min(12,len(getattr(owner,'_ewb_anchors',[]) or []) or 5)))
    wizard=ttk.LabelFrame(right,text='关键帧向导',padding=8);wizard.pack(fill='x')
    wr=ttk.Frame(wizard);wr.pack(fill='x')
    ttk.Label(wr,text='关键帧数量').pack(side='left')
    key_spin=ttk.Spinbox(wr,from_=1,to=min(50,n),textvariable=keyframe_count,width=9,justify='center');key_spin.pack(side='left',padx=6,ipadx=3)
    ttk.Button(wr,text='生成 / 重置',command=lambda:_ewb_workspace_generate_keyframes()).pack(side='left')
    ttk.Button(wr,text='同步当前调整到全部关键帧',command=lambda:_ewb_workspace_sync_keyframes()).pack(side='right')

    frame_box=ttk.LabelFrame(right,text='帧 / Frames',padding=5);frame_box.pack(fill='both',expand=True,pady=(7,0))
    fl_wrap=ttk.Frame(frame_box);fl_wrap.pack(fill='both',expand=True)
    frame_list=ttk.Treeview(fl_wrap,columns=('frame','ev','temp','tint','file'),show='tree headings',selectmode='browse',height=12)
    frame_list.heading('#0',text='');frame_list.column('#0',width=44,minwidth=44,stretch=False,anchor='center')
    for col,text,width,anchor in [('frame','Frame',54,'e'),('ev','曝光',64,'e'),('temp','色温',58,'e'),('tint','色调',58,'e'),('file','文件名',180,'w')]:
        frame_list.heading(col,text=text);frame_list.column(col,width=width,minwidth=42,stretch=(col=='file'),anchor=anchor)
    fl_scroll=ttk.Scrollbar(fl_wrap,orient='vertical',command=frame_list.yview);frame_list.configure(yscrollcommand=fl_scroll.set);frame_list.pack(side='left',fill='both',expand=True);fl_scroll.pack(side='right',fill='y')
    # Treeview's #0 column reserves native tree indentation before the item
    # image.  The old 24 px column clipped a 10 px marker completely on the
    # Windows theme.  A 44 px gutter leaves room for both indentation and this
    # high-DPI marker.  The dark rim stays visible on the blue selection bar.
    blue_dot=tk.PhotoImage(width=14,height=14);blank_dot=tk.PhotoImage(width=14,height=14)
    for yy in range(14):
        for xx in range(14):
            dist2=(xx-6.5)**2+(yy-6.5)**2
            if dist2<=36.0:blue_dot.put('#0b4f9c' if dist2>20.25 else '#2f93ff',(xx,yy))
    d._ewb_blue_dot=blue_dot;d._ewb_blank_dot=blank_dot
    frame_list_state={
        'syncing':False,'built':False,'stamp':None,'populating':False,
        'updating':False,'populate_token':0,'update_token':0,
        'pending_select':None,'ignore_select_iid':None,
    }

    sec=ttk.LabelFrame(right,text='当前帧 / 关键帧',padding=8);sec.pack(fill='x',pady=(7,0))
    anchor_status=tk.StringVar(value='当前帧不是关键帧');ttk.Label(sec,textvariable=anchor_status).pack(anchor='w')
    def slider_row(parent,label,var,lo,hi,res,reset_value=0.0):
        row=ttk.Frame(parent);row.pack(fill='x',pady=3);ttk.Label(row,text=label,width=15).pack(side='left');sld=ttk.Scale(row,from_=lo,to=hi,variable=var,command=lambda _=None:_ewb_workspace_anchor_changed());sld.pack(side='left',fill='x',expand=True,padx=5);ent=ttk.Entry(row,textvariable=var,width=8,justify='right');ent.pack(side='right');ent.bind('<Return>',lambda _e:_ewb_workspace_anchor_changed());ent.bind('<FocusOut>',lambda _e:_ewb_workspace_anchor_changed())
        def reset_slider(_event=None):
            var.set(float(reset_value));_ewb_workspace_anchor_changed();return 'break'
        sld.bind('<Double-Button-1>',reset_slider,add='+');return sld
    slider_row(sec,'曝光 EV',edit_exposure,-3.0,3.0,0.01,0.0);slider_row(sec,'色温（相对）',edit_temp,-100,100,1,0.0);slider_row(sec,'色调（相对）',edit_tint,-100,100,1,0.0)
    slider_row(sec,'对比度',edit_contrast,-100,100,1,0.0);slider_row(sec,'高光',edit_highlights,-100,100,1,0.0);slider_row(sec,'阴影',edit_shadows,-100,100,1,0.0);slider_row(sec,'白色色阶',edit_whites,-100,100,1,0.0);slider_row(sec,'黑色色阶',edit_blacks,-100,100,1,0.0)
    arbtn=ttk.Frame(sec);arbtn.pack(fill='x',pady=(7,0));ttk.Button(arbtn,text='设为 / 更新关键帧',command=lambda:_ewb_workspace_save_anchor()).pack(side='left');ttk.Button(arbtn,text='取消关键帧',command=lambda:_ewb_workspace_delete_anchor()).pack(side='left',padx=5)
    anchors_text=tk.StringVar(value='关键帧：0');ttk.Label(sec,textvariable=anchors_text).pack(anchor='w',pady=(6,0))

    smooth=ttk.LabelFrame(right,text='平滑',padding=8);smooth.pack(fill='x',pady=(7,0))
    amount_row=ttk.Frame(smooth);amount_row.pack(fill='x');ttk.Label(amount_row,text='平滑力度').pack(side='left')
    smooth_value=tk.StringVar(value=f'{float(owner.ewb_smoothing_amount.get()):.0f}');ttk.Label(amount_row,textvariable=smooth_value,width=4,anchor='e').pack(side='right')
    smooth_scale=ttk.Scale(smooth,from_=0,to=100,variable=owner.ewb_smoothing_amount);smooth_scale.pack(fill='x',pady=(3,5))
    def smoothing_drag(_v=None):smooth_value.set(f'{float(owner.ewb_smoothing_amount.get()):.0f}');_ewb_workspace_param_changed(owner,False,refresh_all)
    smooth_scale.configure(command=smoothing_drag)
    def reset_smoothing(_event=None):
        owner.ewb_smoothing_amount.set(float(_ewb_default_config()['smoothing_amount']));smooth_value.set(f'{float(owner.ewb_smoothing_amount.get()):.0f}');_ewb_workspace_param_changed(owner,False,refresh_all);return 'break'
    smooth_scale.bind('<Double-Button-1>',reset_smoothing,add='+')
    mp=ttk.Frame(smooth);mp.pack(fill='x')
    ttk.Checkbutton(mp,text='多遍平滑',variable=owner.ewb_multi_pass_enabled,command=lambda:_ewb_workspace_param_changed(owner,False,refresh_all)).pack(side='left')
    ttk.Label(mp,text='遍数').pack(side='left',padx=(12,3));pass_spin=ttk.Spinbox(mp,from_=1,to=10,textvariable=owner.ewb_smoothing_passes,width=9,justify='center');pass_spin.pack(side='left',ipadx=3);pass_spin.bind('<Return>',lambda _e:_ewb_workspace_param_changed(owner,False,refresh_all));pass_spin.bind('<FocusOut>',lambda _e:_ewb_workspace_param_changed(owner,False,refresh_all))
    transition_status=tk.StringVar(value='关键帧调整会自动保存；点击下方按钮生成全序列过渡')
    apply_transition_btn=ttk.Button(smooth,text='应用关键帧并生成平滑过渡',style='Primary.TButton',command=lambda:_ewb_workspace_apply_transition());apply_transition_btn.pack(fill='x',pady=(9,3))
    transition_progress=tk.DoubleVar(value=0.0);transition_progressbar=ttk.Progressbar(smooth,mode='determinate',maximum=100.0,variable=transition_progress);transition_progressbar.pack(fill='x',pady=(1,3))
    resmooth_btn=ttk.Button(smooth,text='再次平滑当前结果',command=lambda:_ewb_workspace_resmooth(),state='disabled');resmooth_btn.pack(fill='x',pady=(3,3))
    ttk.Label(smooth,textvariable=transition_status,foreground='#666',wraplength=320).pack(fill='x')

    advanced_open=tk.BooleanVar(value=False)
    advanced_toggle=ttk.Button(right,text='高级去闪与分析设置（通常无需修改） ▸');advanced_toggle.pack(fill='x',pady=(7,0))
    advanced_body=ttk.Frame(right)
    ttk.Label(advanced_body,text='用于控制短周期闪烁检测、修正上限和分析区域。默认值适合大多数序列。',foreground='#666',wraplength=330).pack(fill='x',pady=(6,2))
    def toggle_advanced():
        advanced_open.set(not advanced_open.get())
        advanced_toggle.configure(text='高级去闪与分析设置（通常无需修改） '+('▾' if advanced_open.get() else '▸'))
        if advanced_open.get():advanced_body.pack(fill='x')
        else:advanced_body.pack_forget()
        try:right_scroll_canvas.after_idle(lambda:right_scroll_canvas.configure(scrollregion=right_scroll_canvas.bbox('all')))
        except Exception:pass
    advanced_toggle.configure(command=toggle_advanced)
    adv=ttk.LabelFrame(advanced_body,text='去闪、平滑与修正范围',padding=8);adv.pack(fill='x',pady=(3,0))
    def numeric_row(parent,label,var,unit=''):
        row=ttk.Frame(parent);row.pack(fill='x',pady=2);ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=var,width=8,justify='right').pack(side='right');ttk.Label(row,text=unit).pack(side='right',padx=4)
    numeric_row(adv,'去闪检测半径',owner.ewb_deflicker_radius,'frames');numeric_row(adv,'去闪强度',owner.ewb_deflicker_strength,'%');numeric_row(adv,'曝光基础半径',owner.ewb_exposure_radius,'frames');numeric_row(adv,'曝光应用强度',owner.ewb_exposure_strength,'%');numeric_row(adv,'曝光最大修正',owner.ewb_exposure_max_ev,'EV');numeric_row(adv,'WB 基础半径',owner.ewb_wb_radius,'frames');numeric_row(adv,'WB 应用强度',owner.ewb_wb_strength,'%');numeric_row(adv,'WB 最大通道修正',owner.ewb_wb_max_percent,'%');numeric_row(adv,'关键帧影响',owner.ewb_anchor_influence,'%')
    for child in adv.winfo_children():
        for w in child.winfo_children():
            if isinstance(w,ttk.Entry):w.bind('<Return>',lambda _e:_ewb_workspace_param_changed(owner,False,refresh_all));w.bind('<FocusOut>',lambda _e:_ewb_workspace_param_changed(owner,False,refresh_all))

    region=ttk.LabelFrame(advanced_body,text='分析区域',padding=8);region.pack(fill='x',pady=(7,0));ttk.Combobox(region,textvariable=owner.ewb_analysis_region,state='readonly',values=['自动有效区域','全画面','自定义 ROI']).pack(fill='x')
    rg=ttk.Frame(region);rg.pack(fill='x',pady=(5,0))
    for col,(lab,var) in enumerate([('X',owner.ewb_roi_x),('Y',owner.ewb_roi_y),('W',owner.ewb_roi_w),('H',owner.ewb_roi_h)]):ttk.Label(rg,text=lab).grid(row=0,column=col*2);e=ttk.Entry(rg,textvariable=var,width=5);e.grid(row=0,column=col*2+1,padx=(2,5));e.bind('<FocusOut>',lambda _e:_ewb_workspace_param_changed(owner,True,refresh_all))
    region.winfo_children()[0].bind('<<ComboboxSelected>>',lambda _e:_ewb_workspace_param_changed(owner,True,refresh_all))

    def _ewb_workspace_request_preview(*_,force_hq=False):
        idx=max(0,min(n-1,int(current.get())-1));preview_state['token']+=1;token=preview_state['token'];preview_state['pending']=idx;frame_text.set(f'Frame {idx+1}/{n} · {Path(files[idx]).name}');_ewb_workspace_load_anchor_values(idx);_ewb_workspace_draw_thumbs(idx);_ewb_workspace_draw_curves(idx);_ewb_workspace_refresh_frame_list(idx)
        # During playback use the RAM-only analysis thumbnail immediately. This makes
        # 10/24/30 fps browsing independent of RAW decode speed. Paused viewing then
        # upgrades to an 800 px linear proxy asynchronously.
        m=getattr(owner,'_ewb_measurements',None);thumbs=m.get('thumbs',[]) if m else []
        if play_state['running'] and not force_hq and idx<len(thumbs):
            try:
                preview_state['quality']='playback';preview_state['img']=srgb_to_linear(thumbs[idx].astype(np.float32)/255.0);_ewb_workspace_draw_preview(idx);return
            except Exception:pass
        preview_state['quality']='hq_pending'
        if preview_state.get('img') is not None:_ewb_workspace_draw_preview(idx)
        if preview_state.get('after') is not None:
            try:d.after_cancel(preview_state['after'])
            except Exception:pass
        def launch():
            if not d.winfo_exists() or token!=preview_state['token']:return
            if preview_state['loading']:
                preview_state['after']=d.after(35,launch);return
            preview_state['loading']=True;q=Queue()
            def work():
                try:q.put(_ewb_get_preview_proxy(owner,idx,int(_ewb_default_config()['preview_proxy_max_side'])))
                except Exception:q.put(None)
            threading.Thread(target=work,daemon=True).start()
            def poll():
                try:img=q.get_nowait()
                except Empty:
                    if d.winfo_exists():d.after(25,poll)
                    return
                preview_state['loading']=False
                if token==preview_state['token'] and img is not None:
                    preview_state['quality']='hq';preview_state['img']=img;_ewb_workspace_draw_preview(idx)
                elif d.winfo_exists() and preview_state.get('pending') is not None:
                    preview_state['after']=d.after(10,_ewb_workspace_request_preview)
            poll()
        preview_state['after']=d.after(45,launch)

    def _ewb_workspace_preview_fit_scale(width=None,height=None,image_size=None):
        W=max(1,int(preview.winfo_width() if width is None else width));H=max(1,int(preview.winfo_height() if height is None else height))
        if image_size is None:
            img=preview_state.get('img')
            if img is None:return 1.0
            ih,iw=img.shape[:2]
            if view_mode.get()=='左右对比':iw*=2
        else:iw,ih=image_size
        return min(W/max(1,iw),H/max(1,ih))

    def _ewb_workspace_preview_adjust_pan(old_factor,new_factor,x=None,y=None):
        try:
            W=max(1,preview.winfo_width());H=max(1,preview.winfo_height());px,py=preview_state.get('pan',[0.0,0.0])[:2]
            mx=W/2 if x is None else float(x);my=H/2 if y is None else float(y);ratio=float(new_factor)/max(float(old_factor),1e-9)
            rx=mx-(W/2+px);ry=my-(H/2+py);preview_state['pan']=[mx-W/2-rx*ratio,my-H/2-ry*ratio]
        except Exception:preview_state['pan']=[0.0,0.0]

    def _ewb_workspace_preview_wheel(event,direction=None):
        try:
            preview.focus_set();direction=(1 if int(getattr(event,'delta',0) or 0)>0 else -1) if direction is None else int(direction)
            old=1.0 if preview_state.get('fit',True) else float(preview_state.get('zoom',1.0));new=max(0.10,min(20.0,old*(1.12 if direction>0 else 1/1.12)))
            if abs(new-old)>1e-9:
                _ewb_workspace_preview_adjust_pan(old,new,getattr(event,'x',None),getattr(event,'y',None));preview_state['fit']=False;preview_state['zoom']=new;_ewb_workspace_anchor_preview()
        except Exception:pass
        return 'break'

    def _ewb_workspace_preview_pan_start(event):
        preview.focus_set()
        if preview_state.get('fit',True):preview_state['pan_anchor']=None;return 'break'
        px,py=preview_state.get('pan',[0.0,0.0])[:2];preview_state['pan_anchor']=(float(event.x),float(event.y),float(px),float(py));return 'break'

    def _ewb_workspace_preview_pan_drag(event):
        anchor=preview_state.get('pan_anchor')
        if anchor is None:return 'break'
        x0,y0,px0,py0=anchor;preview_state['pan']=[px0+float(event.x)-x0,py0+float(event.y)-y0]
        try:
            item=preview_state.get('image_item');W=max(1,preview.winfo_width());H=max(1,preview.winfo_height());px,py=preview_state['pan']
            if item:preview.coords(item,int(W/2+px),int(H/2+py))
        except Exception:pass
        return 'break'

    def _ewb_workspace_preview_pan_end(_event=None):preview_state['pan_anchor']=None;return 'break'

    def _ewb_workspace_preview_fit(event=None):
        # Preserve Ctrl+Z for any future text/undo handling; plain Z is Fit.
        if event is not None and (int(getattr(event,'state',0) or 0)&0x4):return None
        preview_state['fit']=True;preview_state['zoom']=1.0;preview_state['pan']=[0.0,0.0];preview_state['pan_anchor']=None;_ewb_workspace_anchor_preview()
        try:preview.focus_set()
        except Exception:pass
        return 'break'

    def _ewb_workspace_draw_preview(idx):
        img=preview_state.get('img')
        if img is None:return
        mode=view_mode.get();display=img
        if mode=='修正后' and getattr(owner,'_ewb_table',None) is not None:
            display=_ewb_apply_to_frame(owner,img,idx)
        elif mode=='左右对比' and getattr(owner,'_ewb_table',None) is not None:
            corr=_ewb_apply_to_frame(owner,img,idx);display=np.concatenate([img,corr],axis=1)
        # Before Apply, a keyframe shows the user's temporary direct adjustment.
        # After Apply, every frame (including anchors) must use the final table so
        # scrubbing/playback is an exact preview of the stack input corrections.
        edit_values=(float(edit_exposure.get()),float(edit_temp.get()),float(edit_tint.get()),float(edit_contrast.get()),float(edit_highlights.get()),float(edit_shadows.get()),float(edit_whites.get()),float(edit_blacks.get()))
        if mode=='修正后' and not preview_state.get('transition_applied',False) and any(abs(v)>1e-9 for v in edit_values):
            display=_ewb_apply_preview_adjustment(img,*edit_values)
        arr=np.round(np.clip(linear_to_srgb(np.clip(display,0,None)),0,1)*255).astype(np.uint8);im=Image.fromarray(arr,'RGB');W=max(100,preview.winfo_width());H=max(100,preview.winfo_height());iw,ih=im.size;fit=_ewb_workspace_preview_fit_scale(W,H,(iw,ih));factor=1.0 if preview_state.get('fit',True) else float(preview_state.get('zoom',1.0));scale=max(0.01,fit*factor);nw=max(1,int(round(iw*scale)));nh=max(1,int(round(ih*scale)))
        # Explicit resize is intentional: unlike PIL.thumbnail(), this also
        # enlarges the RAM playback proxy so maximizing the window uses the
        # available preview area instead of leaving a 144 px image in the center.
        if (nw,nh)!=(iw,ih):im=im.resize((nw,nh),Image.Resampling.LANCZOS)
        photo=ImageTk.PhotoImage(im);preview_state['photo']=photo;preview.delete('all');px,py=preview_state.get('pan',[0.0,0.0])[:2];cx=W/2+px;cy=H/2+py;preview_state['image_item']=preview.create_image(int(cx),int(cy),image=photo,anchor='center',tags=('ewb_preview_image',));preview_state['display_rect']=(int(cx-nw/2),int(cy-nh/2),nw,nh)
        if mode=='左右对比':preview.create_text(W//4,18,text='原始',fill='#ddd',font=_ui_font(9,pixel=True));preview.create_text(W*3//4,18,text='修正后',fill='#ddd',font=_ui_font(9,pixel=True))
        zoom_text='Fit' if preview_state.get('fit',True) else f'{factor*100:.0f}% Fit';preview.create_text(10,H-10,anchor='sw',text=zoom_text+' · 滚轮缩放 · 拖拽平移 · Z Fit',fill='#e0e0e0',font=_ui_font(9,pixel=True),tags=('ewb_preview_overlay',))
        quality=preview_state.get('quality')
        if quality=='playback':preview.create_text(W-10,H-10,anchor='se',text='低分辨率播放预览',fill='#e8c76a',font=_ui_font(9,pixel=True),tags=('ewb_preview_overlay',))
        elif quality=='hq_pending':preview.create_text(W-10,H-10,anchor='se',text='正在加载高分辨率静帧预览…',fill='#e8c76a',font=_ui_font(9,pixel=True),tags=('ewb_preview_overlay',))

    def _ewb_workspace_anchor_preview(*_):
        idx=max(0,min(n-1,int(current.get())-1));
        if preview_state.get('img') is not None:_ewb_workspace_draw_preview(idx)

    def _ewb_workspace_mark_pending(text='关键帧或平滑参数已改变，请重新应用过渡'):
        preview_state['transition_applied']=False;owner._ewb_additional_smoothing_rounds=0;transition_status.set(text)
        try:transition_progress.set(0.0)
        except Exception:pass
        try:resmooth_btn.configure(state='disabled')
        except Exception:pass

    def _ewb_workspace_commit_anchor_edits():
        """Persist the visible controls into their existing keyframe immediately."""
        if preview_state.get('edit_loading',False):return False
        idx=max(0,min(n-1,int(preview_state.get('edit_frame',int(current.get())-1))))
        anchor=next((a for a in getattr(owner,'_ewb_anchors',[]) if int(a.get('frame',0))==idx+1),None)
        if anchor is None:return False
        values=(float(edit_exposure.get()),float(edit_temp.get()),float(edit_tint.get()))+tuple(float(edit_tone_vars[k].get()) for k in _EWB_TONE_KEYS);keys=('exposure','temperature','tint')+_EWB_TONE_KEYS;old=tuple(float(anchor.get(k,0.0)) for k in keys)
        if all(abs(a-b)<=1e-9 for a,b in zip(values,old)):return False
        anchor.update(dict(zip(keys,values)));_ewb_workspace_mark_pending(f'关键帧 {idx+1} 的调整已自动保存，请应用平滑过渡');_ewb_invalidate(owner,'关键帧调整已自动保存',analysis=False)
        try:_ewb_workspace_draw_curves(idx);_ewb_workspace_refresh_frame_list(idx)
        except Exception:pass
        return True

    def _ewb_workspace_anchor_changed(*_):
        if not _ewb_workspace_commit_anchor_edits():_ewb_workspace_mark_pending('当前调整尚未应用；普通帧需先设为关键帧才会保存')
        _ewb_workspace_anchor_preview()

    def _ewb_workspace_load_anchor_values(idx):
        if int(preview_state.get('edit_frame',idx))!=int(idx):_ewb_workspace_commit_anchor_edits()
        preview_state['edit_loading']=True
        a=next((x for x in getattr(owner,'_ewb_anchors',[]) if int(x.get('frame',0))==idx+1),None)
        if a:
            edit_exposure.set(float(a.get('exposure',0.0)));edit_temp.set(float(a.get('temperature',0.0)));edit_tint.set(float(a.get('tint',0.0)))
            for key,var in edit_tone_vars.items():var.set(float(a.get(key,0.0)))
            anchor_status.set('当前帧是关键帧（调整自动保存）')
        else:
            edit_exposure.set(0.0);edit_temp.set(0.0);edit_tint.set(0.0)
            for var in edit_tone_vars.values():var.set(0.0)
            anchor_status.set('当前帧不是关键帧（需先设为关键帧）')
        preview_state['edit_frame']=int(idx);preview_state['edit_loading']=False
        anchors_text.set(f'关键帧：{len(getattr(owner,"_ewb_anchors",[]) or [])}')

    def _ewb_workspace_save_anchor():
        idx=max(0,min(n-1,int(current.get())-1));a={'frame':idx+1,'exposure':float(edit_exposure.get()),'temperature':float(edit_temp.get()),'tint':float(edit_tint.get())};a.update({k:float(v.get()) for k,v in edit_tone_vars.items()});arr=[x for x in getattr(owner,'_ewb_anchors',[]) if int(x.get('frame',0))!=idx+1];arr.append(a);arr.sort(key=lambda x:int(x['frame']));owner._ewb_anchors=arr;_ewb_workspace_mark_pending('关键帧已保存，请应用平滑过渡');_ewb_invalidate(owner,'关键帧已改变',analysis=False);refresh_all()

    def _ewb_workspace_delete_anchor():
        idx=max(0,min(n-1,int(current.get())-1));owner._ewb_anchors=[x for x in getattr(owner,'_ewb_anchors',[]) if int(x.get('frame',0))!=idx+1];_ewb_workspace_mark_pending('关键帧已删除，请重新应用平滑过渡');_ewb_invalidate(owner,'关键帧已改变',analysis=False);refresh_all()

    def _ewb_workspace_apply_transition():
        if transition_state.get('busy'):return
        _ewb_workspace_commit_anchor_edits();owner._ewb_additional_smoothing_rounds=0
        anchors=list(getattr(owner,'_ewb_anchors',[]) or [])
        if not anchors and not owner.ewb_deflicker_enabled.get():messagebox.showinfo(APP_NAME,'请先生成并调整至少一个关键帧，或启用“去闪”。',parent=d);return
        # Include an unsaved edit when Apply is pressed while the current frame is
        # already an anchor; this prevents the last adjusted keyframe being missed.
        idx=max(0,min(n-1,int(current.get())-1));current_anchor=next((a for a in anchors if int(a.get('frame',0))==idx+1),None)
        if current_anchor is not None:
            current_anchor['exposure']=float(edit_exposure.get());current_anchor['temperature']=float(edit_temp.get());current_anchor['tint']=float(edit_tint.get());current_anchor.update({k:float(v.get()) for k,v in edit_tone_vars.items()});anchors.sort(key=lambda a:int(a.get('frame',0)));owner._ewb_anchors=anchors
        has_exposure=any(abs(float(a.get('exposure',0.0)))>1e-9 for a in anchors);has_wb=any(abs(float(a.get('temperature',0.0)))+abs(float(a.get('tint',0.0)))>1e-9 for a in anchors)
        has_tone=any(any(abs(float(a.get(k,0.0)))>1e-9 for k in _EWB_TONE_KEYS) for a in anchors)
        # Keyframe grading is an explicit request to use the corresponding
        # correction channel.  This avoids adjusted anchors appearing only on the
        # keyframe itself when the top smoothing checkboxes were still unchecked.
        if has_exposure:owner.ewb_exposure_enabled.set(True)
        if has_wb:owner.ewb_wb_enabled.set(True)
        if not (owner.ewb_exposure_enabled.get() or owner.ewb_wb_enabled.get() or owner.ewb_deflicker_enabled.get() or has_tone):
            messagebox.showinfo(APP_NAME,'所有关键帧仍是默认参数。请先调整曝光、白平衡或基础明暗参数。',parent=d);return
        cfg=_ewb_config_snapshot(owner);measurements=getattr(owner,'_ewb_measurements',None)
        if measurements is None or getattr(owner,'_ewb_measurement_signature',None)!=_ewb_measurement_signature_for(owner,cfg):
            preview_state['transition_applied']=False;transition_status.set('需要先完成素材分析；分析完成后请再次点击应用')
            if not getattr(owner,'_ewb_analysis_running',False):_ewb_analyze_async(owner,on_done=lambda:transition_status.set('分析完成，请点击应用关键帧并生成平滑过渡'),parent=d)
            return
        _ewb_invalidate(owner,'正在应用关键帧平滑过渡',analysis=False);cfg=_ewb_config_snapshot(owner);expected_signature=_ewb_correction_signature_for(owner,cfg)
        snapshot={k:np.asarray(measurements[k]).copy() for k in ('exposure_metric','rlog_metric','blog_metric')};transition_state['busy']=True;transition_state['token']+=1;token=transition_state['token'];transition_progress.set(2.0);transition_status.set('正在准备关键帧平滑过渡…');apply_transition_btn.configure(state='disabled');resmooth_btn.configure(state='disabled');q=Queue()
        def report(value,text):q.put(('progress',float(value),str(text)))
        def work():
            try:q.put(('done',_ewb_build_table_from_snapshot(snapshot,cfg,progress=report)))
            except Exception as exc:q.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()
        def finish_busy():
            transition_state['busy']=False
            try:apply_transition_btn.configure(state='normal')
            except Exception:pass
        def poll():
            if not d.winfo_exists() or token!=transition_state.get('token'):return
            try:item=q.get_nowait()
            except Empty:d.after(25,poll);return
            kind=item[0]
            if kind=='progress':
                transition_progress.set(max(2.0,min(96.0,float(item[1]))));transition_status.set(item[2]);d.after(10,poll);return
            if kind=='error':
                finish_busy();transition_progress.set(0.0);preview_state['transition_applied']=False;transition_status.set('生成平滑过渡失败：'+item[1]);return
            table=item[1]
            if expected_signature!=_ewb_correction_signature_for(owner):
                finish_busy();transition_progress.set(0.0);preview_state['transition_applied']=False;transition_status.set('生成期间参数已改变，请重新点击应用');return
            owner._ewb_table=table;owner._ewb_display_table=table;owner._ewb_correction_signature=expected_signature;owner.ewb_status.set(_ewb_table_summary(table));preview_state['transition_applied']=True;view_mode.set('修正后');transition_progress.set(100.0);finish_busy();resmooth_btn.configure(state='normal');transition_status.set(f'已完成：{len(anchors)} 个关键帧 → {n} 帧；可预览全部过渡，也可继续“再次平滑”')
            if preview_state.get('img') is not None:_ewb_workspace_draw_preview(idx)
            refresh_all()
        d.after(10,poll)

    def _ewb_workspace_resmooth():
        _ewb_workspace_commit_anchor_edits()
        if not preview_state.get('transition_applied',False) or getattr(owner,'_ewb_table',None) is None:
            messagebox.showinfo(APP_NAME,'请先点击“应用关键帧并生成平滑过渡”，再对生成的结果继续平滑。',parent=d);return
        previous=max(0,int(getattr(owner,'_ewb_additional_smoothing_rounds',0) or 0));owner._ewb_additional_smoothing_rounds=previous+1;_ewb_invalidate(owner,'正在再次平滑当前结果',analysis=False,preserve_rounds=True);table=_ewb_rebuild_table(owner)
        if table is None:
            owner._ewb_additional_smoothing_rounds=previous;preview_state['transition_applied']=False;resmooth_btn.configure(state='disabled');transition_status.set('再次平滑失败：需要重新分析素材并应用关键帧');return
        rounds=int(table.get('additional_smoothing_rounds',previous+1));preview_state['transition_applied']=True;view_mode.set('修正后');resmooth_btn.configure(state='normal');transition_status.set(f'已在当前结果上再次平滑 {rounds} 次；可继续点击以累计下一轮')
        idx=max(0,min(n-1,int(current.get())-1));_ewb_workspace_draw_curves(idx);_ewb_workspace_refresh_frame_list(idx)
        if preview_state.get('img') is not None:_ewb_workspace_draw_preview(idx)

    def _ewb_workspace_param_changed(_owner,analysis,callback):
        _ewb_workspace_mark_pending('分析区域已改变，请重新分析并应用' if analysis else '平滑参数已改变，请重新应用过渡')
        _ewb_invalidate(_owner,'分析区域已改变' if analysis else '平滑参数已改变',analysis=analysis)
        callback()

    def _ewb_workspace_draw_thumbs(idx):
        thumb_canvas.delete('all');m=getattr(owner,'_ewb_measurements',None);thumbs=m.get('thumbs',[]) if m else [];W=max(300,thumb_canvas.winfo_width());slot=96;count=max(3,int(W//slot));start=max(0,min(n-count,idx-count//2));photos=[]
        for j in range(start,min(n,start+count)):
            x=(j-start)*slot+slot//2
            if j<len(thumbs):
                try:ph=ImageTk.PhotoImage(Image.fromarray(thumbs[j],'RGB'));photos.append(ph);thumb_canvas.create_image(x,38,image=ph,anchor='center')
                except Exception:pass
            thumb_canvas.create_text(x,78,text=str(j+1),fill='#fff' if j==idx else '#aaa',font=_ui_font(8,pixel=True));
            if any(int(a.get('frame',0))==j+1 for a in getattr(owner,'_ewb_anchors',[])):thumb_canvas.create_polygon(x-5,4,x,0,x+5,4,x,8,fill='#2f93ff',outline='')
        thumb_canvas._ewb_photos=photos;thumb_canvas._ewb_start=start;thumb_canvas._ewb_slot=slot

    def _ewb_workspace_draw_curves(idx):
        curves.delete('all');table=getattr(owner,'_ewb_table',None) or getattr(owner,'_ewb_display_table',None);W=max(320,curves.winfo_width());H=max(240,curves.winfo_height());padx=48;pady=18
        if not table:curves.create_text(W//2,H//2,text='分析素材后显示曝光与白平衡曲线',fill='#aaa',font=_ui_font(10,pixel=True));return
        exp=np.asarray(table['exposure_metric']);exps=np.asarray(table.get('exposure_smooth',table['exposure_target']));expt=np.asarray(table['exposure_target']);tm=np.asarray(table['temp_metric']);tms=np.asarray(table.get('temp_smooth',table['temp_target']));tmt=np.asarray(table['temp_target']);ti=np.asarray(table['tint_metric']);tis=np.asarray(table.get('tint_smooth',table['tint_target']));tit=np.asarray(table['tint_target'])
        # Drawing more points than horizontal pixels only makes Tk create very
        # large Tcl argument lists.  Decimation keeps long sequences responsive
        # without changing the visible curve at the current canvas resolution.
        point_count=max(1,min(len(exp),max(320,int(W-padx-8))))
        sample_idx=np.unique(np.linspace(0,max(0,len(exp)-1),point_count).astype(np.int64)) if len(exp) else np.asarray([],dtype=np.int64)
        panels=[('曝光 EV',exp,exps,expt,'#6fb1ff'),('白平衡 冷↔暖',tm,tms,tmt,'#ffad66'),('白平衡 绿↔洋红',ti,tis,tit,'#d58cff')];ph=H/3.0;xs=np.linspace(padx,W-8,max(1,len(sample_idx)))
        curves.create_line(padx,7,padx+22,7,fill='#666');curves.create_text(padx+27,7,text='原始',fill='#999',anchor='w',font=_ui_font(7,pixel=True));curves.create_line(padx+72,7,padx+94,7,fill='#38d6ff',dash=(4,2));curves.create_text(padx+99,7,text='平滑趋势',fill='#38d6ff',anchor='w',font=_ui_font(7,pixel=True));curves.create_line(padx+170,7,padx+192,7,fill='#ffd166',width=2);curves.create_text(padx+197,7,text='关键帧目标',fill='#ffd166',anchor='w',font=_ui_font(7,pixel=True))
        for pi,(name,raw,smoothv,target,col) in enumerate(panels):
            y0=pi*ph+pady;y1=(pi+1)*ph-8;lo=float(min(np.min(raw),np.min(smoothv),np.min(target)));hi=float(max(np.max(raw),np.max(smoothv),np.max(target)));span=max(hi-lo,1e-6);curves.create_text(5,y0,anchor='nw',text=name,fill='#ddd',font=_ui_font(8,pixel=True));curves.create_line(padx,y1,W-8,y1,fill='#333');rp=[];sp=[];tp=[]
            for x,a,sv,bv in zip(xs,raw[sample_idx],smoothv[sample_idx],target[sample_idx]):rp.extend((float(x),float(y1-(a-lo)/span*(y1-y0))));sp.extend((float(x),float(y1-(sv-lo)/span*(y1-y0))));tp.extend((float(x),float(y1-(bv-lo)/span*(y1-y0))))
            if len(rp)>=4:curves.create_line(*rp,fill='#666',width=1);curves.create_line(*sp,fill='#38d6ff',width=1,dash=(4,2));curves.create_line(*tp,fill=col,width=2)
            xsel=float(padx+(W-8-padx)*(max(0,min(len(raw)-1,idx))/max(1,len(raw)-1)));curves.create_line(xsel,y0,xsel,y1,fill='#eee',dash=(2,3))
            for a in getattr(owner,'_ewb_anchors',[]):
                ai=max(0,min(len(raw)-1,int(a.get('frame',1))-1));xa=float(padx+(W-8-padx)*(ai/max(1,len(raw)-1)));curves.create_polygon(xa-4,y0+3,xa,y0-1,xa+4,y0+3,xa,y0+7,fill='#2f93ff',outline='')

    def _curve_click(e):
        table=getattr(owner,'_ewb_table',None) or getattr(owner,'_ewb_display_table',None)
        if not table:return
        _ewb_workspace_stop_playback(False);W=max(320,curves.winfo_width());idx=int(round((e.x-44)/max(1,W-52)*(n-1)));current.set(max(1,min(n,idx+1)));_ewb_workspace_request_preview(force_hq=True)
    curves.bind('<Button-1>',_curve_click)

    def _thumb_click(e):
        try:
            _ewb_workspace_stop_playback(False);start=int(getattr(thumb_canvas,'_ewb_start',0));slot=int(getattr(thumb_canvas,'_ewb_slot',96));j=start+max(0,int(e.x//max(1,slot)));current.set(max(1,min(n,j+1)));_ewb_workspace_request_preview(force_hq=True)
        except Exception:pass
    thumb_canvas.bind('<Button-1>',_thumb_click)

    def _ewb_workspace_refresh_frame_list(select_idx=None,rebuild=False):
        if not d.winfo_exists():return
        table=getattr(owner,'_ewb_table',None) or getattr(owner,'_ewb_display_table',None);anchor_list=list(getattr(owner,'_ewb_anchors',[]) or []);anchors={int(a.get('frame',0)):a for a in anchor_list};stamp=(id(table),_ewb_anchor_signature(anchor_list))
        if select_idx is not None:frame_list_state['pending_select']=max(0,min(n-1,int(select_idx)))

        def row_values(i,table_snapshot,anchor_snapshot):
            ev=tv=tiv=''
            if table_snapshot is not None:
                try:ev=f"{float(table_snapshot['ev_correction'][i]):+.2f}";tv=f"{float(table_snapshot['temp_target'][i]-table_snapshot['temp_metric'][i]):+.1f}";tiv=f"{float(table_snapshot['tint_target'][i]-table_snapshot['tint_metric'][i]):+.1f}"
                except Exception:pass
            return blue_dot if (i+1) in anchor_snapshot else blank_dot,(i+1,ev,tv,tiv,Path(files[i]).name)

        def apply_pending_selection():
            pending=frame_list_state.get('pending_select')
            if pending is None:return
            iid=str(pending+1)
            if not frame_list.exists(iid):return
            frame_list_state['syncing']=True
            try:
                # ``selection_set`` emits <<TreeviewSelect>> after this callback
                # returns.  Calling it again for the already-selected row creates
                # an endless preview -> selection -> preview event loop.
                if frame_list.selection()!=(iid,):
                    frame_list_state['ignore_select_iid']=iid;frame_list.selection_set(iid)
                frame_list.focus(iid);frame_list.see(iid);frame_list_state['pending_select']=None
            except Exception:pass
            frame_list_state['syncing']=False

        if rebuild:
            frame_list_state['populate_token']+=1;frame_list_state['update_token']+=1
            frame_list_state['populating']=False;frame_list_state['updating']=False;frame_list_state['built']=False;frame_list_state['stamp']=None
            children=frame_list.get_children()
            if children:frame_list.delete(*children)

        if not frame_list_state['built']:
            if frame_list_state['populating']:return
            frame_list_state['populating']=True;frame_list_state['populate_token']+=1;token=frame_list_state['populate_token'];snapshot_stamp=stamp;table_snapshot=table;anchor_snapshot=anchors
            def populate_chunk(start=0):
                if not d.winfo_exists() or token!=frame_list_state['populate_token']:return
                stop=min(n,start+120);frame_list_state['syncing']=True
                try:
                    for i in range(start,stop):
                        img,values=row_values(i,table_snapshot,anchor_snapshot);frame_list.insert('', 'end', iid=str(i+1), text='', image=img,values=values)
                finally:frame_list_state['syncing']=False
                if stop<n:d.after(1,lambda:populate_chunk(stop));return
                frame_list_state['populating']=False;frame_list_state['built']=True;frame_list_state['stamp']=snapshot_stamp;apply_pending_selection()
                # Analysis/keyframes may have changed while the rows were being added.
                d.after_idle(lambda:_ewb_workspace_refresh_frame_list(frame_list_state.get('pending_select')))
            d.after_idle(populate_chunk);return

        if frame_list_state.get('stamp')!=stamp:
            frame_list_state['update_token']+=1;token=frame_list_state['update_token'];frame_list_state['updating']=True;table_snapshot=table;anchor_snapshot=anchors
            def update_chunk(start=0):
                if not d.winfo_exists() or token!=frame_list_state['update_token']:return
                stop=min(n,start+180)
                for i in range(start,stop):
                    try:
                        img,values=row_values(i,table_snapshot,anchor_snapshot);frame_list.item(str(i+1),image=img,values=values)
                    except Exception:pass
                if stop<n:d.after(1,lambda:update_chunk(stop));return
                frame_list_state['updating']=False;frame_list_state['stamp']=stamp;apply_pending_selection()
            d.after_idle(update_chunk);return
        apply_pending_selection()

    def _ewb_workspace_toggle_keyframe(frame_no):
        frame_no=max(1,min(n,int(frame_no)));arr=list(getattr(owner,'_ewb_anchors',[]) or []);found=next((a for a in arr if int(a.get('frame',0))==frame_no),None)
        if found is not None:arr=[a for a in arr if int(a.get('frame',0))!=frame_no]
        else:arr.append({'frame':frame_no,'exposure':0.0,'temperature':0.0,'tint':0.0,**{k:0.0 for k in _EWB_TONE_KEYS}})
        arr.sort(key=lambda a:int(a.get('frame',0)));owner._ewb_anchors=arr;_ewb_workspace_mark_pending('关键帧集合已改变，请应用平滑过渡');_ewb_invalidate(owner,'关键帧已改变',analysis=False);refresh_all()

    def _frame_list_click(e):
        row=frame_list.identify_row(e.y);col=frame_list.identify_column(e.x)
        if row and col=='#0':_ewb_workspace_stop_playback(False);_ewb_workspace_toggle_keyframe(int(row));return 'break'
    frame_list.bind('<Button-1>',_frame_list_click,add='+')
    def _frame_list_select(_e=None):
        if frame_list_state['syncing']:return
        sel=frame_list.selection()
        if not sel:return
        ignored=frame_list_state.pop('ignore_select_iid',None)
        if ignored is not None and sel==(ignored,):return
        try:_ewb_workspace_stop_playback(False);current.set(int(sel[0]));_ewb_workspace_request_preview(force_hq=True)
        except Exception:pass
    frame_list.bind('<<TreeviewSelect>>',_frame_list_select)

    def _ewb_workspace_generate_keyframes():
        count=max(1,min(min(50,n),int(keyframe_count.get() or 1)));old={int(a.get('frame',0)):a for a in getattr(owner,'_ewb_anchors',[]) or []}
        frames=[max(1,(n+1)//2)] if count==1 else sorted(set(int(round(x)) for x in np.linspace(1,n,count)))
        arr=[]
        for fno in frames:
            a=copy.deepcopy(old.get(fno,{'frame':fno,'exposure':0.0,'temperature':0.0,'tint':0.0,**{k:0.0 for k in _EWB_TONE_KEYS}}));a['frame']=fno
            for key in _EWB_TONE_KEYS:a.setdefault(key,0.0)
            arr.append(a)
        owner._ewb_anchors=arr;_ewb_workspace_mark_pending('关键帧向导已更新，请调整并应用平滑过渡');_ewb_invalidate(owner,'关键帧向导已更新',analysis=False);refresh_all()

    def _ewb_workspace_sync_keyframes():
        idx=max(0,min(n-1,int(current.get())-1));arr=list(getattr(owner,'_ewb_anchors',[]) or [])
        if not arr:messagebox.showinfo(APP_NAME,'请先用关键帧向导或蓝点设置至少一个关键帧。',parent=d);return
        if not any(int(a.get('frame',0))==idx+1 for a in arr):messagebox.showinfo(APP_NAME,'当前帧不是关键帧。请先点击帧列表最左侧把它设为关键帧。',parent=d);return
        values={'exposure':float(edit_exposure.get()),'temperature':float(edit_temp.get()),'tint':float(edit_tint.get()),**{k:float(v.get()) for k,v in edit_tone_vars.items()}}
        for a in arr:a.update(values)
        owner._ewb_anchors=arr;_ewb_workspace_mark_pending('关键帧调整已同步，请应用平滑过渡');_ewb_invalidate(owner,'关键帧调整已同步',analysis=False);refresh_all()

    def _step(delta):_ewb_workspace_stop_playback(False);current.set(max(1,min(n,int(current.get())+delta)));_ewb_workspace_request_preview(force_hq=True)
    prev_btn.configure(command=lambda:_step(-1));next_btn.configure(command=lambda:_step(1))
    def _ewb_workspace_stop_playback(upgrade=True):
        play_state['epoch']+=1;play_state['running']=False;play_state['advancing']=False;after_id=play_state.get('after');play_state['after']=None;play_btn.configure(text='▶ 播放')
        if after_id is not None:
            try:d.after_cancel(after_id)
            except Exception:pass
        # Invalidate every queued thumbnail render and replace it with one HQ still.
        preview_state['token']+=1
        if upgrade and d.winfo_exists():_ewb_workspace_request_preview(force_hq=True)

    def _play_tick(epoch):
        if not play_state['running'] or epoch!=play_state.get('epoch') or not d.winfo_exists():return
        v=int(current.get())+1
        if v>n:v=1
        play_state['advancing']=True
        try:current.set(v);_ewb_workspace_request_preview()
        finally:play_state['advancing']=False
        if not play_state['running'] or epoch!=play_state.get('epoch'):return
        delay=max(10,int(1000.0/max(0.1,float(fps.get() or 10.0))));play_state['after']=d.after(delay,lambda:_play_tick(epoch))
    def _toggle_play(_event=None):
        if play_state['running']:_ewb_workspace_stop_playback(True)
        else:
            play_state['epoch']+=1;epoch=play_state['epoch'];play_state['running']=True;play_btn.configure(text='Ⅱ 暂停');_play_tick(epoch)
        return 'break'
    def _timeline_changed(_value=None):
        if not play_state.get('advancing'):_ewb_workspace_stop_playback(False)
        _ewb_workspace_request_preview(force_hq=not play_state['running'])
    play_btn.configure(command=_toggle_play)
    timeline.configure(command=_timeline_changed)
    preview.bind('<Configure>',lambda _e:_ewb_workspace_anchor_preview())
    preview.bind('<MouseWheel>',_ewb_workspace_preview_wheel,add='+')
    preview.bind('<Button-4>',lambda e:_ewb_workspace_preview_wheel(e,1),add='+')
    preview.bind('<Button-5>',lambda e:_ewb_workspace_preview_wheel(e,-1),add='+')
    preview.bind('<ButtonPress-1>',_ewb_workspace_preview_pan_start,add='+')
    preview.bind('<B1-Motion>',_ewb_workspace_preview_pan_drag,add='+')
    preview.bind('<ButtonRelease-1>',_ewb_workspace_preview_pan_end,add='+')
    d.bind('<KeyPress-z>',_ewb_workspace_preview_fit,add='+');d.bind('<KeyPress-Z>',_ewb_workspace_preview_fit,add='+')
    for widget in (d,preview,frame_list,timeline,thumb_canvas,curves):widget.bind('<space>',_toggle_play,add='+')
    curves.bind('<Configure>',lambda _e:_ewb_workspace_draw_curves(max(0,int(current.get())-1)))
    thumb_canvas.bind('<Configure>',lambda _e:_ewb_workspace_draw_thumbs(max(0,int(current.get())-1)))

    def refresh_all():
        if not d.winfo_exists():return
        _ewb_workspace_request_preview(force_hq=not play_state['running'])

    # Make nested callbacks visible to the lambdas above before first event.
    locals_map=locals()
    done_btn.configure(command=lambda:(_ewb_workspace_commit_anchor_edits(),_ewb_workspace_stop_playback(False),_ewb_workspace_close(owner,d)))
    d.protocol('WM_DELETE_WINDOW',lambda:(_ewb_workspace_commit_anchor_edits(),_ewb_workspace_stop_playback(False),_ewb_workspace_close(owner,d)))
    _enforce_regular_typography(d)
    # Paint the complete widget skeleton before any sequence-sized work starts.
    # Frame rows are populated in small callbacks below, so Windows continues to
    # receive messages even with a very large input sequence.
    try:d.update_idletasks()
    except Exception:pass
    d.after(40,refresh_all)
    cfg=_ewb_config_snapshot(owner)
    valid=getattr(owner,'_ewb_measurements',None) is not None and getattr(owner,'_ewb_measurement_signature',None)==_ewb_measurement_signature_for(owner,cfg)
    if not valid:d.after(150,lambda:_ewb_analyze_async(owner,on_done=refresh_all,parent=d))
    if focus_curves:d.after(300,lambda:curves.focus_set())


def _ewb_workspace_close(owner,d):
    # An analysis dialog is a non-modal child of this workspace.  If the whole
    # workspace is closed, stop its worker cleanly; maximize/restore does not
    # enter this path and therefore leaves analysis running normally.
    try:
        cancel=getattr(owner,'_ewb_analysis_cancel',None)
        if cancel is not None:cancel.set()
    except Exception:pass
    try:
        if getattr(owner,'_ewb_workspace',None) is d:owner._ewb_workspace=None
    except Exception:pass
    try:d.destroy()
    except Exception:pass


def _build_ewb_panel(owner,parent,wraplength=430):
    box=ttk.LabelFrame(parent,text='去闪 / 曝光 / 白平衡',padding=7);box.pack(fill='x',pady=(7,0));row=ttk.Frame(box);row.pack(fill='x');ttk.Checkbutton(row,text='去闪',variable=owner.ewb_deflicker_enabled,command=lambda:_ewb_invalidate(owner,'去闪开关已改变')).pack(side='left');ttk.Checkbutton(row,text='曝光平滑',variable=owner.ewb_exposure_enabled,command=lambda:_ewb_invalidate(owner,'平滑开关已改变')).pack(side='left',padx=(10,0));ttk.Checkbutton(row,text='白平衡平滑',variable=owner.ewb_wb_enabled,command=lambda:_ewb_invalidate(owner,'平滑开关已改变')).pack(side='left',padx=(10,0));row=ttk.Frame(box);row.pack(fill='x',pady=(6,2));ttk.Button(row,text='打开去闪与平滑工作区…',command=lambda:_ewb_open_workspace(owner)).pack(side='left');ttk.Label(box,textvariable=owner.ewb_status,foreground='#666',wraplength=wraplength).pack(anchor='w',pady=(3,0));return box

def save_tiff(path: str, img, float32=False):
    np, tifffile, *_ = _deps()
    if float32:
        tifffile.imwrite(path, img.astype(np.float32), photometric='rgb')
    else:
        out = np.round(np.clip(img,0,1)*65535.0).astype(np.uint16)
        tifffile.imwrite(path, out, photometric='rgb')


def estimate_asinh_params(img):
    """Estimate suggested Asinh stretch parameters from a linear image."""
    np, *_ = _deps()
    lum = 0.2126*img[...,0] + 0.7152*img[...,1] + 0.0722*img[...,2]
    smp = lum[::8,::8].astype(np.float32)
    lo = float(np.quantile(smp, 0.002))
    hi = float(np.quantile(smp, 0.999))
    black = max(0.0, lo * 0.98)
    norm = max(hi - black, 1e-6)
    mid = float(np.quantile(np.clip((smp - black) / norm, 0, None), 0.60))
    mid = min(max(mid, 1e-6), 0.99)
    target = 0.32
    def f(s):
        return float(np.arcsinh(s*mid) / np.arcsinh(s))
    lo_s, hi_s = 0.05, 500.0
    for _ in range(36):
        m = (lo_s + hi_s) / 2.0
        if f(m) > target:
            hi_s = m
        else:
            lo_s = m
    strength = max(0.1, min((lo_s + hi_s) / 2.0, 500.0))
    return float(strength), float(black)


def auto_stretch_for_display(img, strength=None, black=None):
    """Display-only stretch using the same Asinh model as the real stretch."""
    if strength is None or black is None:
        strength, black = estimate_asinh_params(img)
    return apply_asinh_stretch(img, strength, black)


def apply_asinh_stretch(img, strength=8.0, black=0.0):
    np, *_ = _deps()
    x = np.maximum(img - black, 0.0)
    # robust normalization; preserves highlight headroom reasonably
    p = float(np.quantile(x[::8,::8], 0.9995))
    if p <= 1e-8: p = 1.0
    x = x / p
    s = max(float(strength), 0.01)
    y = np.arcsinh(s*x) / np.arcsinh(s)
    return np.clip(y,0,1).astype(np.float32)


def _blur(img, radius):
    np, *_rest = _deps(); cv2 = _rest[-1]
    radius = max(float(radius), 0.1)
    if cv2 is not None:
        sigma = max(radius, 0.1)
        return cv2.GaussianBlur(img, (0,0), sigmaX=sigma, sigmaY=sigma, borderType=cv2.BORDER_REFLECT)
    # fallback Pillow, slower and 8-bit internally for preview-like use
    Image = _rest[1]
    ImageFilter = _rest[3]
    arr8 = (np.clip(img,0,1)*255).astype(np.uint8)
    out = np.empty_like(img)
    pil = Image.fromarray(arr8, 'RGB').filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(pil,dtype=np.float32)/255.0


def apply_usm(img, amount=100.0, radius=2.0, threshold=0.0):
    np, *_ = _deps()
    blur = _blur(img, radius)
    detail = img - blur
    if threshold > 0:
        t = float(threshold)/255.0
        detail = np.where(np.abs(detail) >= t, detail, 0.0)
    out = img + (float(amount)/100.0)*detail
    return np.clip(out,0,1).astype(np.float32)


def overlay_blend(base, blend):
    np, *_ = _deps()
    return np.where(base <= 0.5, 2*base*blend, 1-2*(1-base)*(1-blend))


def softlight_blend(base, blend):
    np, *_ = _deps()
    return (1-2*blend)*base*base + 2*blend*base


def highpass_filter(img, radius=10.0, gain=1.0):
    """Photoshop-style High Pass filter output centered on neutral 50% gray."""
    np, *_ = _deps()
    blur = _blur(img, radius)
    # PS-like neutral gray carrier: low frequencies become 0.5, edges deviate around 0.5.
    hp = 0.5 + (img - blur) * float(gain)
    return np.clip(hp, 0, 1).astype(np.float32)


def apply_highpass(img, radius=10.0, amount=100.0, mode='Overlay'):
    """Apply High Pass as an effect layer blended back to the source."""
    np, *_ = _deps()
    hp = highpass_filter(img, radius, gain=1.0)
    if mode == 'Soft Light':
        mixed = softlight_blend(img, hp)
    elif mode == 'Linear Light':
        mixed = np.clip(img + 2*(hp-0.5),0,1)
    else:
        mixed = overlay_blend(img, hp)
    a = np.clip(float(amount)/100.0,0,1)
    return np.clip(img*(1-a)+mixed*a,0,1).astype(np.float32)


def _emboss_components(img, angle=135.0, height=1.0, amount=100.0):
    """Return source RGB, luminance, directional relief and gray emboss carrier."""
    np, *_rest = _deps(); cv2 = _rest[-1]
    x = np.clip(img.astype(np.float32), 0, 1)
    lum = (0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2]).astype(np.float32)
    a = math.radians(float(angle))
    h = max(float(height), 0.1)
    dx = math.cos(a) * h
    dy = -math.sin(a) * h
    if cv2 is not None:
        M1 = np.float32([[1,0, dx/2.0],[0,1, dy/2.0]])
        M2 = np.float32([[1,0,-dx/2.0],[0,1,-dy/2.0]])
        hi = cv2.warpAffine(lum, M1, (lum.shape[1],lum.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        lo = cv2.warpAffine(lum, M2, (lum.shape[1],lum.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        gx = cv2.Sobel(lum, cv2.CV_32F, 1, 0, ksize=3, borderType=cv2.BORDER_REFLECT)
        gy = cv2.Sobel(lum, cv2.CV_32F, 0, 1, ksize=3, borderType=cv2.BORDER_REFLECT)
        edge_mag = cv2.magnitude(gx, gy) * 0.25
    else:
        ix=int(round(dx/2.0)); iy=int(round(dy/2.0))
        hi=np.roll(np.roll(lum, iy, axis=0), ix, axis=1)
        lo=np.roll(np.roll(lum,-iy, axis=0),-ix, axis=1)
        gx=(np.roll(lum,-1,axis=1)-np.roll(lum,1,axis=1))*0.5
        gy=(np.roll(lum,-1,axis=0)-np.roll(lum,1,axis=0))*0.5
        edge_mag=np.sqrt(gx*gx+gy*gy)
    amount_scale=max(float(amount),0.0)/100.0
    directional=(hi-lo).astype(np.float32)
    relief=np.clip(0.5 + directional*(1.35*amount_scale), 0.0, 1.0)
    return x, lum, directional, relief, edge_mag, amount_scale


def _photoshop_emboss_filter(img, angle=135.0, height=1.0, amount=100.0):
    """PS-style Emboss approximation.

    Photoshop's published description of Emboss is a neutral/gray stamped
    surface whose edges retain the original fill color.  This implementation
    follows that visual model instead of merely preserving the source RGB
    everywhere.  Flat regions settle near 50% gray, directional relief creates
    the raised/recessed shading, and a broadened edge mask restores strong
    source chroma around the traced edges.
    """
    np, *_rest = _deps(); cv2 = _rest[-1]
    x = np.clip(img.astype(np.float32), 0, 1)
    lum = (0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2]).astype(np.float32)
    a = math.radians(float(angle))
    h = max(float(height), 0.1)
    dx = math.cos(a) * h
    dy = -math.sin(a) * h

    if cv2 is not None:
        M1=np.float32([[1,0, dx/2.0],[0,1, dy/2.0]])
        M2=np.float32([[1,0,-dx/2.0],[0,1,-dy/2.0]])
        lum_hi=cv2.warpAffine(lum,M1,(lum.shape[1],lum.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        lum_lo=cv2.warpAffine(lum,M2,(lum.shape[1],lum.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        rgb_hi=cv2.warpAffine(x,M1,(x.shape[1],x.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        rgb_lo=cv2.warpAffine(x,M2,(x.shape[1],x.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        gx=cv2.Sobel(lum,cv2.CV_32F,1,0,ksize=3,borderType=cv2.BORDER_REFLECT)
        gy=cv2.Sobel(lum,cv2.CV_32F,0,1,ksize=3,borderType=cv2.BORDER_REFLECT)
        edge=np.sqrt(gx*gx+gy*gy).astype(np.float32)
    else:
        ix=int(round(dx/2.0));iy=int(round(dy/2.0))
        lum_hi=np.roll(np.roll(lum,iy,axis=0),ix,axis=1)
        lum_lo=np.roll(np.roll(lum,-iy,axis=0),-ix,axis=1)
        rgb_hi=np.roll(np.roll(x,iy,axis=0),ix,axis=1)
        rgb_lo=np.roll(np.roll(x,-iy,axis=0),-ix,axis=1)
        gx=(np.roll(lum,-1,axis=1)-np.roll(lum,1,axis=1))*0.5
        gy=(np.roll(lum,-1,axis=0)-np.roll(lum,1,axis=0))*0.5
        edge=np.sqrt(gx*gx+gy*gy).astype(np.float32)

    amount_scale=max(float(amount),0.0)/100.0
    lum_dir=(lum_hi-lum_lo).astype(np.float32)
    rgb_dir=(rgb_hi-rgb_lo).astype(np.float32)

    # Neutral stamped carrier. Amount controls relief depth, as the PS Amount
    # control visually does, but the gain is compressed above 100% to avoid
    # premature clipping at the 500% end of the UI range.
    relief_gain=1.55*(0.65*min(amount_scale,1.0)+0.35*np.sqrt(max(amount_scale,0.0)))
    shade=np.clip(0.5 + lum_dir*relief_gain,0.0,1.0).astype(np.float32)

    # Edge tracing: combine Sobel energy with the directional difference and
    # broaden it slightly. This is the key difference from the old Gray mode:
    # Photoshop-like edges keep visibly more of the source fill color instead
    # of becoming almost monochrome.
    energy=np.abs(lum_dir)*(4.2+1.2*min(amount_scale,2.0)) + edge*(1.6+0.5*min(amount_scale,2.0))
    edge_mask=np.clip(energy,0.0,1.0).astype(np.float32)
    if cv2 is not None:
        sigma=max(0.35,min(3.0,h*0.32))
        edge_mask=cv2.GaussianBlur(edge_mask,(0,0),sigmaX=sigma,sigmaY=sigma,borderType=cv2.BORDER_REFLECT)
        edge_mask=np.clip(edge_mask*1.22,0.0,1.0)
    else:
        edge_mask=np.clip(edge_mask,0.0,1.0)

    source_chroma=x-lum[...,None]
    dir_lum=(0.2126*rgb_dir[...,0]+0.7152*rgb_dir[...,1]+0.0722*rgb_dir[...,2]).astype(np.float32)
    dir_chroma=rgb_dir-dir_lum[...,None]

    # At Amount=100, colored edge traces are deliberately strong.  Flat areas
    # remain neutral gray, matching the characteristic PS Emboss look, while
    # colored halo/cloud edges no longer wash out.
    color_gain=np.clip(0.62+0.38*min(amount_scale,1.0)+0.10*max(amount_scale-1.0,0.0),0.45,1.25)
    trace=(source_chroma*color_gain + dir_chroma*(0.30+0.12*min(amount_scale,2.0)))
    out=shade[...,None] + trace*edge_mask[...,None]

    # Very faint chroma shoulder around traced edges avoids the unnaturally
    # abrupt gray-to-color transition that made the previous mode look dull.
    shoulder=np.clip(edge_mask*0.38,0.0,0.38)[...,None]
    out += source_chroma*shoulder*(0.34+0.10*min(amount_scale,2.0))
    return np.clip(out,0,1).astype(np.float32)


def emboss_filter(img, angle=135.0, height=1.0, amount=100.0, style='Photoshop Emboss'):
    """Emboss filter body with PS-style, color-preserving and gray modes."""
    np, *_ = _deps()
    st=str(style or 'Photoshop Emboss').lower()
    if 'photoshop' in st or st.startswith('ps ') or 'ps-like' in st:
        return _photoshop_emboss_filter(img,angle,height,amount)
    x, lum, directional, relief, edge_mag, amount_scale = _emboss_components(img, angle, height, amount)
    if 'gray' in st or '灰' in st:
        chroma=x-lum[...,None]
        edge_mask=np.clip(edge_mag*(3.5 + 2.0*min(amount_scale,2.0)), 0.0, 1.0)[...,None]
        color_strength=np.clip(0.18 + 0.42*min(amount_scale,1.5), 0.0, 0.70)
        out=relief[...,None] + chroma*edge_mask*color_strength
        return np.clip(out,0,1).astype(np.float32)
    # Existing Color Emboss is intentionally preserved unchanged.
    target_lum=np.clip(lum + directional*(1.35*amount_scale),0.0,1.0)
    out=x + (target_lum-lum)[...,None]
    return np.clip(out,0,1).astype(np.float32)


def apply_emboss(img, angle=135.0, height=1.0, amount=100.0, opacity=100.0,
                 mode='Normal', style='Photoshop Emboss'):
    """Apply Emboss with selectable blend modes and opacity."""
    np, *_ = _deps()
    emb = emboss_filter(img, angle, height, amount, style=style)
    if mode == 'Overlay':
        mixed = overlay_blend(img, emb)
    elif mode == 'Soft Light':
        mixed = softlight_blend(img, emb)
    elif mode == 'Linear Light':
        st=str(style).lower()
        if 'gray' in st or '灰' in st or 'photoshop' in st or st.startswith('ps '):
            mixed = np.clip(img + 2*(emb-0.5),0,1)
        else:
            mixed = np.clip(img + 2*(emb-img),0,1)
    else:
        mixed = emb
    a = np.clip(float(opacity)/100.0,0,1)
    return np.clip(img*(1-a)+mixed*a,0,1).astype(np.float32)


class AngleDial(tk.Canvas):
    """Compact Photoshop-like angle control synchronized with a Tk variable."""
    def __init__(self, parent, variable, command=None, release_command=None,
                 reset_value=-128.0, size=76, **kwargs):
        super().__init__(parent, width=size, height=size, highlightthickness=0,
                         borderwidth=0, background=kwargs.pop('background', '#f0f0f0'), **kwargs)
        self.variable=variable; self.command=command; self.release_command=release_command
        self.reset_value=float(reset_value); self.size=int(size); self._trace_guard=False
        self.bind('<Button-1>', self._drag)
        self.bind('<B1-Motion>', self._drag)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Double-Button-1>', self._reset)
        try:self.variable.trace_add('write', lambda *a:self._draw())
        except Exception:pass
        self._draw()

    def _angle_from_event(self,event):
        c=self.size/2.0; dx=float(event.x)-c; dy=c-float(event.y)
        if abs(dx)+abs(dy)<1e-6:return float(self.variable.get())
        a=math.degrees(math.atan2(dy,dx))
        # Keep the UI in Photoshop's familiar -180..180 range.
        if a>180:a-=360
        if a<=-180:a+=360
        return float(round(a))

    def _drag(self,event):
        v=self._angle_from_event(event)
        try:self.variable.set(v)
        except Exception:return 'break'
        self._draw()
        if self.command is not None:
            try:self.command(v)
            except TypeError:self.command()
        return 'break'

    def _release(self,event):
        self._drag(event)
        if self.release_command is not None:
            try:self.release_command(float(self.variable.get()))
            except TypeError:self.release_command()
        return 'break'

    def _reset(self,event=None):
        try:self.variable.set(self.reset_value)
        except Exception:return 'break'
        self._draw()
        if self.release_command is not None:
            try:self.release_command(self.reset_value)
            except TypeError:self.release_command()
        elif self.command is not None:
            try:self.command(self.reset_value)
            except TypeError:self.command()
        return 'break'

    def _draw(self):
        try:a=math.radians(float(self.variable.get()))
        except Exception:a=0.0
        self.delete('all'); c=self.size/2.0; r=self.size*0.39
        self.create_oval(c-r,c-r,c+r,c+r,fill='#dddddd',outline='#777777',width=1)
        # Small crosshair/center, similar to Photoshop's compact direction control.
        self.create_line(c-r+5,c,c+r-5,c,fill='#aaaaaa')
        self.create_line(c,c-r+5,c,c+r-5,fill='#aaaaaa')
        ex=c+math.cos(a)*r*0.72; ey=c-math.sin(a)*r*0.72
        self.create_line(c,c,ex,ey,fill='#555555',width=2)
        self.create_oval(ex-3,ey-3,ex+3,ey+3,fill='#777777',outline='#555555')
        self.create_oval(c-2,c-2,c+2,c+2,fill='#666666',outline='')


def _smoothstep(a, b, x):
    np, *_ = _deps()
    t = np.clip((x-a)/max(b-a,1e-6), 0.0, 1.0)
    return t*t*(3.0-2.0*t)


def apply_basic(img, exposure=0.0, contrast=0.0, highlights=0.0, shadows=0.0,
                whites=0.0, blacks=0.0, vibrance=0.0, saturation=0.0,
                clarity=0.0, dehaze=0.0):
    """Camera-Raw-inspired basic tone adjustment with neutral fast paths.

    v0.9.4.18m avoids allocating tonal masks whose controls are neutral.  The
    active-control math is unchanged; only mathematically unused work is skipped.
    """
    np, *_ = _deps()
    ev=float(exposure); cv=float(contrast); hv0=float(highlights); sv0=float(shadows)
    wv0=float(whites); bv0=float(blacks); vib0=float(vibrance); sat0=float(saturation)
    cl0=float(clarity); dh0=float(dehaze)
    x=np.clip(img.astype(np.float32,copy=False),0,1)
    if abs(ev)>1e-7:
        x=np.clip(x*(2.0**ev),0,1).astype(np.float32,copy=False)
    else:
        # Keep callers isolated from in-place modifications further below.
        x=x.astype(np.float32,copy=True)

    tone_active=any(abs(v)>1e-7 for v in (cv,hv0,sv0,wv0,bv0))
    if tone_active:
        lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        y=lum.copy()
        if abs(sv0)>1e-7:
            sh_mask=1.0-_smoothstep(0.18,0.68,lum); sv=sv0/100.0
            if sv>=0:y += sv*0.55*sh_mask*(1.0-y)
            else:y += sv*0.38*sh_mask*y
        if abs(hv0)>1e-7:
            hi_mask=_smoothstep(0.35,0.88,lum); hv=hv0/100.0
            if hv>=0:y += hv*0.38*hi_mask*(1.0-y)
            else:y += hv*0.72*hi_mask*y
        if abs(wv0)>1e-7:
            white_mask=_smoothstep(0.68,0.98,lum); wv=wv0/100.0
            y += wv*0.42*white_mask*((1.0-y) if wv>=0 else y)
        if abs(bv0)>1e-7:
            black_mask=1.0-_smoothstep(0.02,0.34,lum); bv=bv0/100.0
            y += bv*0.42*black_mask*((1.0-y) if bv>=0 else y)
        c=cv/100.0
        if abs(c)>1e-7:
            shaped=0.5+0.5*np.tanh((y-0.5)*(2.0+2.6*abs(c)))/np.tanh(1.0+1.3*abs(c))
            if c>0:y=y*(1-c)+shaped*c
            else:y=y*(1+c)+(0.5+(y-0.5)*0.72)*(-c)
        y=np.clip(y,0,1)
        scale=y/np.maximum(lum,1e-5)
        x=np.clip(x*scale[...,None],0,1)

    if abs(cl0)>1e-7:
        blur=_blur(x,12.0);d=cl0/100.0
        l=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        protect=(1.0-0.55*_smoothstep(0.72,1.0,l))[...,None]
        x=x+d*0.75*(x-blur)*protect
    if abs(dh0)>1e-7:
        d=dh0/100.0;base=np.clip(x,0,1);local=_blur(base,48.0)
        l=np.clip(0.2126*base[...,0]+0.7152*base[...,1]+0.0722*base[...,2],0,1)
        if d>=0:
            protect=(1.0-0.72*_smoothstep(0.72,1.0,l))[...,None]
            enhanced=base+1.05*d*(base-local)*protect;bp=0.075*d
            enhanced=(enhanced-bp)/max(1.0-bp,0.25)
            x=base*(1.0-min(d,1.0)*0.25)+enhanced*min(d,1.0)*0.75
        else:
            haze=-d;x=base*(1.0-0.55*haze)+local*(0.55*haze)+0.045*haze

    if abs(sat0)>1e-7 or abs(vib0)>1e-7:
        x=np.clip(x,0,1);lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1);gray=lum[...,None]
        sat=sat0/100.0
        if abs(sat)>1e-7:x=gray+(x-gray)*(1.0+sat)
        vib=vib0/100.0
        if abs(vib)>1e-7:
            mx=x.max(axis=2);mn=x.min(axis=2);chroma=mx-mn;protect=np.clip(chroma/0.38,0,1);factor=1.0+vib*(1.0-protect);x=gray+(x-gray)*factor[...,None]
    return np.clip(x,0,1).astype(np.float32,copy=False)

def _rgb_to_hsv_np(rgb):
    np, *_ = _deps()
    x=np.clip(rgb,0,1).astype(np.float32)
    r,g,b=x[...,0],x[...,1],x[...,2]
    mx=np.maximum(np.maximum(r,g),b); mn=np.minimum(np.minimum(r,g),b); d=mx-mn
    h=np.zeros_like(mx,dtype=np.float32)
    nz=d>1e-8
    mr=(mx==r)&nz; mg=(mx==g)&nz; mb=(mx==b)&nz
    h[mr]=((g[mr]-b[mr])/d[mr])%6.0
    h[mg]=(b[mg]-r[mg])/d[mg]+2.0
    h[mb]=(r[mb]-g[mb])/d[mb]+4.0
    h=(h/6.0)%1.0
    sat=np.where(mx>1e-8,d/np.maximum(mx,1e-8),0.0).astype(np.float32)
    return h.astype(np.float32),sat,mx.astype(np.float32)


def _hsv_to_rgb_np(h,s,v):
    np, *_ = _deps()
    h=np.mod(h,1.0);s=np.clip(s,0,1);v=np.clip(v,0,1)
    q=h*6.0;i=np.floor(q).astype(np.int32)%6;f=q-np.floor(q)
    p=v*(1-s);qv=v*(1-f*s);t=v*(1-(1-f)*s)
    out=np.empty(h.shape+(3,),dtype=np.float32)
    choices=[(v,t,p),(qv,v,p),(p,v,t),(p,qv,v),(t,p,v),(v,p,qv)]
    for idx,(rr,gg,bb) in enumerate(choices):
        m=i==idx;out[...,0][m]=rr[m];out[...,1][m]=gg[m];out[...,2][m]=bb[m]
    return np.clip(out,0,1).astype(np.float32)


def apply_white_balance_post(img, temperature=0.0, tint=0.0):
    np, *_ = _deps()
    x=np.clip(img.astype(np.float32),0,1)
    t=np.clip(float(temperature)/100.0,-1,1);q=np.clip(float(tint)/100.0,-1,1)
    gains=np.array([np.exp(0.35*t+0.10*q),np.exp(-0.20*q),np.exp(-0.35*t+0.10*q)],dtype=np.float32)
    gains=gains/max(float((gains[0]*gains[1]*gains[2])**(1/3)),1e-6)
    return np.clip(x*gains[None,None,:],0,1).astype(np.float32)


def apply_presence_advanced(img, texture=0.0, clarity=0.0, dehaze=0.0, proxy_scale=1.0):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1);ps=max(float(proxy_scale),0.05)
    tex=float(texture)/100.0
    if abs(tex)>1e-7:
        blur=_blur(x,max(0.6,2.2*ps));detail=x-blur
        l=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        protect=(0.72+0.28*(1.0-_smoothstep(0.82,1.0,l)))[...,None]
        x=x+0.65*tex*detail*protect
    cl=float(clarity)/100.0
    if abs(cl)>1e-7:
        blur=_blur(np.clip(x,0,1),max(1.0,12.0*ps));detail=x-blur
        l=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        mid=(0.45+0.55*(1.0-np.abs(l-0.5)*1.35))[...,None]
        x=x+0.82*cl*detail*mid
    dh=float(dehaze)/100.0
    if abs(dh)>1e-7:
        base=np.clip(x,0,1);local=_blur(base,max(2.0,48.0*ps));l=np.clip(0.2126*base[...,0]+0.7152*base[...,1]+0.0722*base[...,2],0,1)
        if dh>=0:
            protect=(1.0-0.78*_smoothstep(0.72,1.0,l))[...,None]
            detail=base-local
            candidate=base+1.18*dh*detail*protect
            bp=0.085*dh*(1.0-0.45*_smoothstep(0.55,1.0,l))[...,None]
            candidate=(candidate-bp)/np.maximum(1.0-bp,0.25)
            x=base*(1.0-0.80*min(dh,1.0))+candidate*(0.80*min(dh,1.0))
        else:
            haze=-dh;x=base*(1.0-0.58*haze)+local*(0.58*haze)+0.05*haze
    return np.clip(x,0,1).astype(np.float32)


def apply_global_hsl(img, hue=0.0, saturation=0.0, luminance=0.0):
    np, *_ = _deps();h,s,v=_rgb_to_hsv_np(img)
    h=np.mod(h+float(hue)/360.0,1.0);s=np.clip(s*(1.0+float(saturation)/100.0),0,1)
    lv=float(luminance)/100.0
    if lv>=0:v=v+lv*0.45*(1-v)
    else:v=v+lv*0.45*v
    return _hsv_to_rgb_np(h,s,np.clip(v,0,1))


def _hue_weight(h,center_deg,width_deg=45.0):
    np, *_ = _deps();c=(float(center_deg)%360.0)/360.0;d=np.abs(h-c);d=np.minimum(d,1.0-d)
    return np.clip(1.0-d/(float(width_deg)/360.0),0,1).astype(np.float32)


def apply_color_mixer_hsl(img,cfg,prefix='mix_'):
    np, *_ = _deps()
    colors=[('red',0),('orange',30),('yellow',60),('green',120),('aqua',180),('blue',225),('purple',275),('magenta',320)]
    active=[]
    for name,center in colors:
        ha=float(cfg.get(prefix+name+'_h',0.0));sa=float(cfg.get(prefix+name+'_s',0.0));la=float(cfg.get(prefix+name+'_l',0.0))
        if abs(ha)>1e-7 or abs(sa)>1e-7 or abs(la)>1e-7:
            active.append((name,center,ha,sa/100.0,la/100.0))
    if not active:
        return img.astype(np.float32,copy=False)
    h,s,v=_rgb_to_hsv_np(img);base_h=h.copy();hue_delta=np.zeros_like(h);sat_factor=np.ones_like(s);vdelta=np.zeros_like(v)
    for name,center,ha,sa,la in active:
        w=_hue_weight(base_h,center,42.0)
        hue_delta+=w*(ha/360.0);sat_factor*=np.clip(1.0+w*sa,0.0,2.5);vdelta+=w*la
    h=np.mod(h+hue_delta,1.0);s=np.clip(s*sat_factor,0,1)
    v=np.where(vdelta>=0,v+0.38*vdelta*(1-v),v+0.38*vdelta*v)
    return _hsv_to_rgb_np(h,s,np.clip(v,0,1))

def _grade_tint(hue_deg,sat):
    np, *_ = _deps();h=np.array([[float(hue_deg)%360/360.0]],dtype=np.float32);ss=np.array([[np.clip(float(sat)/100.0,0,1)]],dtype=np.float32);vv=np.ones_like(h)
    return _hsv_to_rgb_np(h,ss,vv)[0,0]


def apply_color_grading(img,cfg):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1);lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
    bal=np.clip(float(cfg.get('cg_balance',0))/100.0,-1,1);pivot=0.5+0.18*bal
    sh=1.0-_smoothstep(max(0.05,pivot-0.30),pivot,lum);hi=_smoothstep(pivot,min(0.95,pivot+0.30),lum);mid=np.clip(1.0-sh-hi,0,1)
    out=x.copy()
    for name,mask in [('shadow',sh),('mid',mid),('high',hi)]:
        sat=float(cfg.get('cg_'+name+'_s',0));
        if abs(sat)<1e-7:continue
        col=_grade_tint(cfg.get('cg_'+name+'_h',0),abs(sat));delta=col-col.mean();strength=np.clip(abs(sat)/100.0,0,1)*0.24
        if sat<0:delta=-delta
        out=out+mask[...,None]*strength*delta[None,None,:]
    return np.clip(out,0,1).astype(np.float32)


def apply_detail_base(img,sharpen=0.0,radius=1.0,luma_nr=0.0,chroma_nr=0.0,proxy_scale=1.0):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1);ps=max(float(proxy_scale),0.05)
    lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
    ln=np.clip(float(luma_nr)/100.0,0,1)
    if ln>1e-7:
        bl=_blur(np.repeat(lum[...,None],3,axis=2),max(0.6,(0.8+2.0*ln)*ps))[...,0]
        lum2=lum*(1-0.78*ln)+bl*(0.78*ln);scale=lum2/np.maximum(lum,1e-5);x=np.clip(x*scale[...,None],0,1);lum=lum2
    cn=np.clip(float(chroma_nr)/100.0,0,1)
    if cn>1e-7:x=protect_channel_chroma_noise(x,cn*100,max(0.4,(0.6+1.6*cn)*ps))
    sh=float(sharpen)/100.0
    if abs(sh)>1e-7:
        lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1);bl=_blur(np.repeat(lum[...,None],3,axis=2),max(0.25,float(radius)*ps))[...,0];nl=np.clip(lum+sh*(lum-bl),0,1);x=np.clip(x*(nl/np.maximum(lum,1e-5))[...,None],0,1)
    return x.astype(np.float32)


def apply_optics_base(img,distortion=0.0,vignette=0.0,ca=0.0):
    np,*rest=_deps();cv2=rest[-1];x=np.clip(img.astype(np.float32),0,1);h,w=x.shape[:2]
    if cv2 is not None and (abs(float(distortion))>1e-7 or abs(float(ca))>1e-7):
        yy,xx=np.mgrid[0:h,0:w].astype(np.float32);xn=(xx-(w-1)/2)/max((w-1)/2,1);yn=(yy-(h-1)/2)/max((h-1)/2,1);r2=xn*xn+yn*yn
        d=np.clip(float(distortion)/100.0,-1,1)*0.18;fac=1.0+d*r2;mx=(xn*fac+1)*0.5*(w-1);my=(yn*fac+1)*0.5*(h-1)
        base=cv2.remap(x,mx.astype(np.float32),my.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        caa=np.clip(float(ca)/100.0,-1,1)*0.006
        if abs(caa)>1e-8:
            out=base.copy()
            for ch,sgn in [(0,1.0),(2,-1.0)]:
                f=1.0+sgn*caa*r2;cmx=(xn*f+1)*0.5*(w-1);cmy=(yn*f+1)*0.5*(h-1);out[...,ch]=cv2.remap(base[...,ch],cmx.astype(np.float32),cmy.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
            x=out
        else:x=base
    vg=np.clip(float(vignette)/100.0,-1,1)
    if abs(vg)>1e-7:
        yy,xx=np.mgrid[0:h,0:w].astype(np.float32);xn=(xx-(w-1)/2)/max((w-1)/2,1);yn=(yy-(h-1)/2)/max((h-1)/2,1);r=np.clip(np.sqrt(xn*xn+yn*yn)/1.4142,0,1);gain=1.0+vg*0.55*(r**2);x=np.clip(x*gain[...,None],0,1)
    return x.astype(np.float32)


def apply_calibration_base(img,cfg):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1)
    tmp={}
    for name,prefix in [('red','cal_red'),('green','cal_green'),('blue','cal_blue')]:
        tmp['mix_'+name+'_h']=float(cfg.get(prefix+'_h',0));tmp['mix_'+name+'_s']=float(cfg.get(prefix+'_s',0));tmp['mix_'+name+'_l']=0.0
    # Non-primary sectors remain neutral.
    for name in ['orange','yellow','aqua','purple','magenta']:
        tmp['mix_'+name+'_h']=tmp['mix_'+name+'_s']=tmp['mix_'+name+'_l']=0.0
    return apply_color_mixer_hsl(x,tmp)


def _base_activity(cfg,curve_points=None):
    """Return active Base submodules without touching image pixels."""
    def nz(k,default=0.0):
        try:return abs(float(cfg.get(k,default)))>1e-7
        except Exception:return True
    tone=any(nz(k) for k in ('exposure','contrast','highlights','shadows','whites','blacks'))
    wb=nz('temperature') or nz('tint')
    presence=any(nz(k) for k in ('texture','clarity','dehaze'))
    curve=False
    if bool(cfg.get('base_curve',False)) and curve_points:
        for ch in ('RGB','红色','绿色','蓝色','亮度'):
            pts=curve_points.get(ch,[(0.0,0.0),(1.0,1.0)])
            if not (len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6):
                curve=True;break
    hsl=any(nz(k) for k in ('hsl_hue','hsl_sat','hsl_lum'))
    mixer=False
    for c in ('red','orange','yellow','green','aqua','blue','purple','magenta'):
        if any(nz(f'mix_{c}_{a}') for a in ('h','s','l')):
            mixer=True;break
    grading=any(nz(k) for k in ('cg_shadow_s','cg_mid_s','cg_high_s'))
    detail=any(nz(k) for k in ('detail_sharpen','luma_nr','chroma_nr'))
    optics=any(nz(k) for k in ('opt_distortion','opt_vignette','opt_ca'))
    calibration=any(nz(k) for k in ('cal_red_h','cal_red_s','cal_green_h','cal_green_s','cal_blue_h','cal_blue_s'))
    return {'tone':tone,'wb':wb,'presence':presence,'curve':curve,'hsl':hsl,'mixer':mixer,'grading':grading,'detail':detail,'optics':optics,'calibration':calibration}


def apply_base_editor(img,cfg,curve_points=None):
    """Apply Base only where controls are active (v0.9.4.18m fast path).

    Neutral HSL, mixer, grading, detail, optics and calibration modules used to
    perform full-frame color conversions/mask construction anyway.  They now
    short-circuit before allocating pixel buffers.  Active module math is kept
    on the same production functions used by preview and final export.
    """
    np, *_ = _deps();out=np.clip(img.astype(np.float32,copy=False),0,1);ps=float(cfg.get('_proxy_scale',1.0));act=_base_activity(cfg,curve_points)
    # Make one private working buffer; subsequent neutral modules do no extra copies.
    out=out.astype(np.float32,copy=True)
    if act['tone']:
        out=apply_basic(out,cfg.get('exposure',0),cfg.get('contrast',0),cfg.get('highlights',0),cfg.get('shadows',0),cfg.get('whites',0),cfg.get('blacks',0),0,0,0,0)
    if act['wb']:
        out=apply_white_balance_post(out,cfg.get('temperature',0),cfg.get('tint',0))
    if act['presence']:
        out=apply_presence_advanced(out,cfg.get('texture',0),cfg.get('clarity',0),cfg.get('dehaze',0),ps)
    if act['curve']:
        for ch in ('RGB','红色','绿色','蓝色','亮度'):
            pts=curve_points.get(ch,[(0.0,0.0),(1.0,1.0)])
            identity=len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6
            if not identity:out=apply_curve_lut(out,build_curve_lut(pts,256),ch)
    if act['hsl']:
        out=apply_global_hsl(out,cfg.get('hsl_hue',0),cfg.get('hsl_sat',0),cfg.get('hsl_lum',0))
    if act['mixer']:
        out=apply_color_mixer_hsl(out,cfg)
    if act['grading']:
        out=apply_color_grading(out,cfg)
    if act['detail']:
        out=apply_detail_base(out,cfg.get('detail_sharpen',0),cfg.get('detail_radius',1),cfg.get('luma_nr',0),cfg.get('chroma_nr',0),ps)
    if act['optics']:
        out=apply_optics_base(out,cfg.get('opt_distortion',0),cfg.get('opt_vignette',0),cfg.get('opt_ca',0))
    if act['calibration']:
        out=apply_calibration_base(out,cfg)
    return out.astype(np.float32,copy=False)

def build_curve_lut(points, size=256):
    np, *_ = _deps()
    pts = sorted([(max(0.0,min(1.0,float(x))), max(0.0,min(1.0,float(y)))) for x,y in points], key=lambda p:p[0])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    grid = np.linspace(0.0, 1.0, size, dtype=np.float32)
    lut = np.interp(grid, xs, ys).astype(np.float32)
    return np.clip(lut, 0, 1)


def apply_curve_lut(img, lut, channel='RGB'):
    np, *_ = _deps()
    x = np.clip(img, 0, 1).astype(np.float32)
    idx = np.clip(np.round(x * (len(lut)-1)).astype(np.int32), 0, len(lut)-1)
    out = x.copy()
    if channel == 'RGB':
        out[...,0] = lut[idx[...,0]]
        out[...,1] = lut[idx[...,1]]
        out[...,2] = lut[idx[...,2]]
    elif channel in ('红色','绿色','蓝色'):
        mapping = {'红色':0, '绿色':1, '蓝色':2}
        c = mapping[channel]
        out[...,c] = lut[idx[...,c]]
    elif channel in ('亮度','Luminance'):
        lum = np.clip(0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2],0,1)
        lidx = np.clip(np.round(lum * (len(lut)-1)).astype(np.int32), 0, len(lut)-1)
        new_lum = lut[lidx]
        scale = new_lum / np.maximum(lum, 1e-6)
        out = np.clip(x * scale[...,None], 0, 1)
    return out.astype(np.float32)


def protect_channel_chroma_noise(img, strength=30.0, radius=0.8):
    """Reduce high-frequency inter-channel noise while preserving luminance detail.

    The luminance plane is kept from the original image. Only RGB chroma residuals
    (RGB - Y) are Gaussian-smoothed and blended back according to strength.
    This is especially useful for extreme Channel Mixer coefficients such as
    R=-200%, B=+200%, which otherwise strongly amplify color-difference noise.
    """
    np, *_ = _deps()
    x = np.clip(img.astype(np.float32), 0, 1)
    a = np.clip(float(strength)/100.0, 0.0, 1.0)
    if a <= 1e-8:
        return x
    lum = 0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2]
    chroma = x - lum[...,None]
    # _blur accepts RGB-like arrays; chroma can contain negatives, and OpenCV
    # preserves them in float32. The Pillow fallback clips, so offset around 0.5.
    try:
        np2, *_rest = _deps(); cv2 = _rest[-1]
        if cv2 is not None:
            smooth = cv2.GaussianBlur(chroma, (0,0), sigmaX=max(float(radius),0.1), sigmaY=max(float(radius),0.1), borderType=cv2.BORDER_REFLECT)
        else:
            smooth = _blur(np.clip(chroma + 0.5,0,1), radius) - 0.5
    except Exception:
        smooth = chroma
    protected_chroma = chroma*(1.0-a) + smooth*a
    return np.clip(lum[...,None] + protected_chroma, 0, 1).astype(np.float32)


def apply_channel_mixer(img, output_channel='红色', monochrome=False, red=100.0, green=0.0, blue=0.0, constant=0.0,
                        noise_protect=False, noise_strength=30.0, noise_radius=0.8):
    np, *_ = _deps()
    x = np.clip(img.astype(np.float32), 0, 1)
    if noise_protect:
        x = protect_channel_chroma_noise(x, noise_strength, noise_radius)
    r = x[...,0]
    g = x[...,1]
    b = x[...,2]
    mix = (float(red)/100.0)*r + (float(green)/100.0)*g + (float(blue)/100.0)*b + (float(constant)/100.0)
    mix = np.clip(mix, 0, 1).astype(np.float32)
    out = x.copy()
    if monochrome or output_channel == '灰色':
        out[...,0] = mix
        out[...,1] = mix
        out[...,2] = mix
    else:
        mapping = {'红色':0, '绿色':1, '蓝色':2}
        out[..., mapping.get(output_channel, 0)] = mix
    return np.clip(out, 0, 1).astype(np.float32)


def background_suppression(img, radius=80.0, strength=100.0):
    """Remove large-scale background while keeping local halo/cloud structures around mid-gray."""
    np, *_ = _deps()
    x = np.clip(img.astype(np.float32), 0, 1)
    bg = _blur(x, max(float(radius), 0.5))
    detail = x - bg
    out = 0.5 + detail * (max(float(strength), 0.0) / 100.0)
    return np.clip(out, 0, 1).astype(np.float32)


def get_ffmpeg_executable():
    """Use imageio-ffmpeg's bundled binary when available, then fall back to PATH/local ffmpeg."""
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and Path(p).exists():
            return str(p)
    except Exception:
        pass
    p = shutil.which('ffmpeg')
    if p:
        return p
    local = Path(__file__).resolve().parent / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if local.exists():
        return str(local)
    return None


def save_timelapse_sequence_frame(path, img, fmt='PNG 8-bit'):
    np, tifffile, Image, *_ = _deps()
    x = np.clip(img, 0, 1)
    if fmt == 'TIFF 32-bit Float':
        tifffile.imwrite(str(path), x.astype(np.float32), photometric='rgb')
    elif fmt == 'TIFF 16-bit':
        tifffile.imwrite(str(path), np.round(x*65535.0).astype(np.uint16), photometric='rgb')
    elif fmt == 'JPEG':
        Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB').save(str(path), quality=96, subsampling=0)
    else:
        Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB').save(str(path), compress_level=4)


def resize_pil_percent(pil, percent=100.0):
    _, _, Image, *_ = _deps()
    pct=max(1.0,float(percent))
    if abs(pct-100.0) < 1e-6:
        return pil
    sw,sh=pil.size
    nw=max(2,int(round(sw*pct/100.0))); nh=max(2,int(round(sh*pct/100.0)))
    nw -= nw % 2; nh -= nh % 2
    nw=max(2,nw); nh=max(2,nh)
    if (nw,nh)==(sw,sh):
        return pil
    return pil.resize((nw,nh), Image.Resampling.LANCZOS)



def resize_float_percent_array(img, percent=100.0):
    """Resize float RGB without an 8-bit round-trip; used before async output."""
    np, _, Image, *_rest = _deps();cv2=_rest[-1]
    pct=max(1.0,float(percent))
    if abs(pct-100.0)<1e-6:return img
    h,w=img.shape[:2];nw=max(2,int(round(w*pct/100.0)));nh=max(2,int(round(h*pct/100.0)))
    if cv2 is not None:
        return cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA).astype(np.float32,copy=False)
    chans=[np.asarray(Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.LANCZOS),dtype=np.float32) for k in range(3)]
    return np.stack(chans,axis=2)


def _ffmpeg_even_pad_args():
    """Pad at most one pixel on right/bottom so subsampled video codecs receive even dimensions.

    Sequence frames stay untouched; only the encoded video receives the padding.
    """
    return ['-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:black']


def save_timelapse_sequence_frame_scaled(path, img, fmt='PNG 8-bit', scale_percent=100.0):
    np, tifffile, Image, *_ = _deps()
    pct=max(1.0,float(scale_percent))
    if abs(pct-100.0) < 1e-6:
        return save_timelapse_sequence_frame(path, img, fmt)
    x = np.clip(img, 0, 1)
    pil = Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB')
    pil = resize_pil_percent(pil, pct)
    if fmt == 'TIFF 32-bit Float':
        arr = np.asarray(pil, dtype=np.float32) / 255.0
        tifffile.imwrite(str(path), arr.astype(np.float32), photometric='rgb')
    elif fmt == 'TIFF 16-bit':
        arr = np.asarray(pil, dtype=np.uint8)
        tifffile.imwrite(str(path), np.round(arr.astype(np.float32)/255.0*65535.0).astype(np.uint16), photometric='rgb')
    elif fmt == 'JPEG':
        pil.save(str(path), quality=96, subsampling=0)
    else:
        pil.save(str(path), compress_level=4)



def _atomic_temp_path(path):
    path=Path(path)
    # Never reuse a deterministic temporary name. Two app instances, a retry,
    # or a delayed scanner can otherwise contend for ``frame_N.ihs_tmp.png``.
    token=f'{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}'
    return path.with_name(path.stem+'.ihs_tmp.'+token+path.suffix)


def _atomic_replace_with_retry(tmp,path,timeout=5.0):
    """Replace an output after transient Windows sharing locks clear."""
    deadline=time.monotonic()+max(0.0,float(timeout));delay=0.025
    while True:
        try:
            os.replace(str(tmp),str(path));return
        except OSError as exc:
            # Windows Defender, Explorer thumbnails and indexing services can
            # briefly open a freshly encoded file without delete sharing.
            transient=isinstance(exc,PermissionError) or getattr(exc,'winerror',None) in (5,32,33)
            if not transient or time.monotonic()>=deadline:raise
            time.sleep(delay);delay=min(0.40,delay*1.7)


def save_timelapse_sequence_frame_atomic(path, img, fmt='PNG 8-bit', png_compression='Balanced'):
    """Write one final output frame atomically.

    The temporary sibling exists only while the final file is being encoded and
    is immediately renamed on success. This is not a stack/decode/node cache.
    """
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=_atomic_temp_path(path)
    try:
        try: tmp.unlink(missing_ok=True)
        except TypeError:
            if tmp.exists(): tmp.unlink()
        np, tifffile, Image, *_ = _deps()
        x=np.clip(img,0,1)
        if fmt=='TIFF 32-bit Float':
            tifffile.imwrite(str(tmp),x.astype(np.float32,copy=False),photometric='rgb')
        elif fmt=='TIFF 16-bit':
            tifffile.imwrite(str(tmp),np.round(x*65535.0).astype(np.uint16),photometric='rgb')
        elif fmt=='JPEG':
            Image.fromarray(np.round(x*255.0).astype(np.uint8),'RGB').save(str(tmp),format='JPEG',quality=96,subsampling=0)
        else:
            # v0.9.4.18l: prefer OpenCV's native PNG encoder when available.
            # It is lossless just like Pillow PNG, but is materially faster on
            # large 4K/6K frames in our benchmarks. Fall back to Pillow.
            levels={'Fast':1,'Balanced':3,'Maximum':9}
            level=int(levels.get(str(png_compression),3))
            u8=np.round(x*255.0).astype(np.uint8)
            cv2=_deps()[-1]
            wrote=False
            if cv2 is not None:
                try:
                    wrote=bool(cv2.imwrite(str(tmp),u8[...,::-1],[int(cv2.IMWRITE_PNG_COMPRESSION),level]))
                except Exception:
                    wrote=False
            if not wrote:
                Image.fromarray(u8,'RGB').save(str(tmp),format='PNG',compress_level=level)
        _atomic_replace_with_retry(tmp,path)
    except Exception:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass
        raise


def save_pil_png_atomic(path, pil, compress_level=3):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=_atomic_temp_path(path)
    try:
        try: tmp.unlink(missing_ok=True)
        except TypeError:
            if tmp.exists():tmp.unlink()
        pil.save(str(tmp),format='PNG',compress_level=int(max(0,min(9,compress_level))))
        _atomic_replace_with_retry(tmp,path)
    except Exception:
        try:tmp.unlink(missing_ok=True)
        except Exception:pass
        raise


class AsyncOutputPipeline:
    """RAM-aware bounded final-frame writer for v0.9.4.18l.

    Processing and image encoding/disk writing overlap. Queue capacity is small
    and controlled by the RAM strategy; no stack master, decoded RAW, or node
    intermediate is serialized to disk. Backpressure blocks the producer when
    the writer or disk cannot keep up.
    """
    def __init__(self, owner, policy, ui_queue, event_kind, total_tasks):
        self.owner=owner;self.policy=dict(policy or {});self.ui_queue=ui_queue;self.event_kind=str(event_kind)
        self.total_tasks=max(0,int(total_tasks));self.cancel_event=owner.cancel_event
        strategy=str(self.policy.get('strategy','Balanced'))
        self.capacity={'Memory Saver':1,'Balanced':2,'Maximum Performance':3}.get(strategy,2)
        self.limit_bytes=max(int(1*_GIB),int(self.policy.get('limit_bytes',4*_GIB)))
        share={'Memory Saver':0.05,'Balanced':0.10,'Maximum Performance':0.16}.get(strategy,0.10)
        self.byte_budget=max(96*_MIB,int(self.limit_bytes*share))
        self.q=Queue(maxsize=self.capacity);self.lock=threading.RLock();self.cond=threading.Condition(self.lock)
        self.queued_bytes=0;self.peak_bytes=0;self.submitted=0;self.completed=0;self.error=None;self.closed=False
        self.write_seconds=0.0;self.write_samples=deque(maxlen=12);self.writer_active=False;self.last_write_seconds=0.0
        self.started=time.monotonic();self.first_submit=None;self.last_path='';self._sentinel=object()
        self.thread=threading.Thread(target=self._worker,name='IHS-Async-Output',daemon=True);self.thread.start()
        owner._active_output_pipeline=self

    def _raise_if_failed(self):
        if self.error is not None:
            raise RuntimeError('异步输出失败 / Async output failed:\n'+str(self.error))

    def _estimate_bytes(self,obj):
        n=getattr(obj,'nbytes',None)
        if n is not None:
            try:return max(1,int(n))
            except Exception:pass
        try:
            w,h=obj.size;return max(1,int(w)*int(h)*3)
        except Exception:return 32*_MIB

    def _wait_memory_slot(self,nb):
        # A single large frame is always allowed; otherwise obey the queue byte budget.
        with self.cond:
            while not self.closed and self.error is None and not self.cancel_event.is_set():
                if self.queued_bytes==0 or self.queued_bytes+nb<=self.byte_budget:return
                self.cond.wait(timeout=0.08)
        if self.cancel_event.is_set():raise InterruptedError('cancelled')
        self._raise_if_failed()

    def submit_array(self,path,img,fmt='PNG 8-bit',png_compression='Balanced'):
        if self.closed:raise RuntimeError('AsyncOutputPipeline already closed')
        self._raise_if_failed();nb=self._estimate_bytes(img);perf=getattr(self.owner,'_active_performance_monitor',None);tw=time.monotonic();self._wait_memory_slot(nb)
        if perf is not None:perf.add_stage('output_backpressure',time.monotonic()-tw)
        task=('array',Path(path),img,str(fmt),str(png_compression),nb)
        while True:
            if self.cancel_event.is_set():raise InterruptedError('cancelled')
            self._raise_if_failed()
            try:self.q.put(task,timeout=0.08);break
            except Full:continue
        with self.cond:
            self.queued_bytes+=nb;self.peak_bytes=max(self.peak_bytes,self.queued_bytes);self.submitted+=1
            if self.first_submit is None:self.first_submit=time.monotonic()
        self._emit()

    def submit_pil_png(self,path,pil,compress_level=3):
        if self.closed:raise RuntimeError('AsyncOutputPipeline already closed')
        self._raise_if_failed();nb=self._estimate_bytes(pil);perf=getattr(self.owner,'_active_performance_monitor',None);tw=time.monotonic();self._wait_memory_slot(nb)
        if perf is not None:perf.add_stage('output_backpressure',time.monotonic()-tw)
        task=('pil_png',Path(path),pil,int(compress_level),'',nb)
        while True:
            if self.cancel_event.is_set():raise InterruptedError('cancelled')
            self._raise_if_failed()
            try:self.q.put(task,timeout=0.08);break
            except Full:continue
        with self.cond:
            self.queued_bytes+=nb;self.peak_bytes=max(self.peak_bytes,self.queued_bytes);self.submitted+=1
            if self.first_submit is None:self.first_submit=time.monotonic()
        self._emit()

    def _worker(self):
        try:
            while True:
                task=self.q.get()
                if task is self._sentinel:
                    self.q.task_done();break
                kind,path,obj,opt1,opt2,nb=task
                try:
                    if not self.cancel_event.is_set():
                        perf=getattr(self.owner,'_active_performance_monitor',None)
                        if perf is not None:perf.touch('output_write')
                        tw=time.monotonic()
                        with self.lock:self.writer_active=True
                        if kind=='array':save_timelapse_sequence_frame_atomic(path,obj,opt1,opt2)
                        else:save_pil_png_atomic(path,obj,opt1)
                        wdt=max(0.0,time.monotonic()-tw)
                        if perf is not None:perf.add_stage('output_write',wdt);perf.inc('frames_written',1)
                        with self.lock:
                            self.completed+=1;self.last_path=str(path);self.write_seconds+=wdt;self.last_write_seconds=wdt;self.write_samples.append(wdt);self.writer_active=False
                except Exception as e:
                    self.error=e
                finally:
                    with self.lock:self.writer_active=False
                    # Release queued image reference as soon as this file is done.
                    obj=None
                    with self.cond:
                        self.queued_bytes=max(0,self.queued_bytes-int(nb));self.cond.notify_all()
                    self.q.task_done();self._emit()
                if self.error is not None:break
        finally:
            # Drain unprocessed tasks after cancellation/error so join cannot deadlock.
            while True:
                try:t=self.q.get_nowait()
                except Empty:break
                try:
                    if t is not self._sentinel:
                        nb=t[-1]
                        with self.cond:self.queued_bytes=max(0,self.queued_bytes-int(nb));self.cond.notify_all()
                finally:self.q.task_done()
            self._emit()

    def _emit(self):
        try:self.ui_queue.put((self.event_kind,self.stats()))
        except Exception:pass

    def stats(self):
        with self.lock:
            elapsed=max(1e-6,time.monotonic()-(self.first_submit or self.started))
            # pipeline_fps is end-to-end completion throughput and includes time
            # when the writer is idle waiting for node processing. It must not be
            # presented as disk/write speed. writer_fps measures only active file
            # encoding+write time; recent_writer_fps uses the last 12 files.
            pipeline_fps=float(self.completed)/elapsed if self.completed else 0.0
            writer_fps=(float(self.completed)/self.write_seconds) if self.completed and self.write_seconds>1e-9 else 0.0
            recent_sum=sum(self.write_samples);recent_writer_fps=(len(self.write_samples)/recent_sum) if recent_sum>1e-9 else 0.0
            remain=max(0,self.total_tasks-self.completed);eta=(remain/pipeline_fps) if pipeline_fps>1e-9 else None
            idle=(not self.writer_active and self.q.qsize()==0)
            return {'queued':self.q.qsize(),'capacity':self.capacity,'queued_bytes':int(self.queued_bytes),'peak_bytes':int(self.peak_bytes),
                    'submitted':int(self.submitted),'completed':int(self.completed),'total':int(self.total_tasks),
                    'fps':pipeline_fps,'pipeline_fps':pipeline_fps,'writer_fps':writer_fps,'recent_writer_fps':recent_writer_fps,
                    'writer_active':bool(self.writer_active),'writer_idle':bool(idle),'write_seconds':float(self.write_seconds),
                    'last_write_seconds':float(self.last_write_seconds),'eta':eta,'byte_budget':int(self.byte_budget),
                    'last_path':self.last_path,'error':str(self.error) if self.error else ''}

    def finish(self):
        if self.closed:
            self._raise_if_failed();return
        self.closed=True
        # Enqueue sentinel only after all producer tasks. If writer failed, it has already drained.
        if self.error is None:
            while self.thread.is_alive():
                try:self.q.put(self._sentinel,timeout=0.08);break
                except Full:
                    if self.error is not None:break
        self.thread.join()
        self._raise_if_failed();self._detach()

    def cancel(self):
        self.closed=True
        # Worker finishes the currently encoded final file; queued future files are discarded.
        try:
            while True:
                t=self.q.get_nowait()
                try:
                    if t is not self._sentinel:
                        nb=t[-1]
                        with self.cond:self.queued_bytes=max(0,self.queued_bytes-int(nb));self.cond.notify_all()
                finally:self.q.task_done()
        except Empty:pass
        if self.thread.is_alive():
            try:self.q.put_nowait(self._sentinel)
            except Full:pass
            self.thread.join(timeout=30)
        self._detach()

    def _detach(self):
        perf=getattr(self.owner,'_active_performance_monitor',None)
        if perf is not None:
            try:perf.record_output_stats(self.stats())
            except Exception:pass
        if getattr(self.owner,'_active_output_pipeline',None) is self:self.owner._active_output_pipeline=None
        gc.collect()


def prepare_video_frame(img, preset='原始分辨率', custom_w=1920, custom_h=1080, fit_mode='Fill 裁切'):
    np, _, Image, *_ = _deps()
    x = np.clip(img, 0, 1)
    pil = Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB')
    sw, sh = pil.size
    if preset == '原始分辨率':
        tw, th = sw, sh
    elif preset.startswith('16:9'):
        tw, th = 3840, 2160
    elif preset.startswith('4:3'):
        tw, th = 2880, 2160
    else:
        tw, th = max(2,int(custom_w)), max(2,int(custom_h))
    # yuv420p encoders require even dimensions; keep video dimensions valid.
    tw -= tw % 2; th -= th % 2
    tw=max(2,tw); th=max(2,th)
    if (sw,sh)==(tw,th):
        return pil
    if fit_mode == 'Stretch 拉伸':
        return pil.resize((tw,th), Image.Resampling.LANCZOS)
    scale = max(tw/sw, th/sh) if fit_mode == 'Fill 裁切' else min(tw/sw, th/sh)
    nw=max(1,int(round(sw*scale))); nh=max(1,int(round(sh*scale)))
    resized=pil.resize((nw,nh), Image.Resampling.LANCZOS)
    if fit_mode == 'Fill 裁切':
        left=max(0,(nw-tw)//2); top=max(0,(nh-th)//2)
        return resized.crop((left,top,left+tw,top+th))
    canvas=Image.new('RGB',(tw,th),(0,0,0))
    canvas.paste(resized,((tw-nw)//2,(th-nh)//2))
    return canvas


def make_float_preview_proxy(img, max_side=1200):
    """Create a float32 RGB preview proxy without altering the full-resolution master."""
    np, tifffile, Image, ImageTk, ImageFilter, rawpy, cv2 = _deps()
    h,w=img.shape[:2]
    max_side=max(256,int(max_side))
    scale=min(1.0, max_side/float(max(h,w)))
    if scale >= 0.999:
        return img.astype(np.float32,copy=True), 1.0
    nw=max(2,int(round(w*scale))); nh=max(2,int(round(h*scale)))
    if cv2 is not None:
        out=cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA)
    else:
        chans=[]
        for k in range(3):
            ch=Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.BILINEAR)
            chans.append(np.asarray(ch,dtype=np.float32))
        out=np.stack(chans,axis=2)
    return np.clip(out,0,None).astype(np.float32), float(scale)


def scale_timelapse_cfg_for_proxy(cfg, scale):
    """Scale pixel-radius parameters so a reduced preview resembles full-resolution processing."""
    out=dict(cfg)
    scale=max(float(scale),1e-4)
    out['_proxy_scale']=scale
    for key,minimum in [('bg_radius',1.0),('usm_radius',0.1),('hp_radius',0.1),('emboss_height',0.1),('channel_noise_radius',0.1)]:
        if key in out:
            out[key]=max(minimum,float(out[key])*scale)
    return out


def apply_timelapse_pipeline(img, cfg, curve_points=None, stop_after=None):
    """Apply the locked timelapse processing chain.

    Fixed order used by the node workflow:
    Stack → Stretch / 拉伸 → Basic / 基础 → USM / 反锐化蒙版锐化
    → BGR / 背景+曲线（Background → Curves）
    → High Pass / 高反差保留 → Emboss / 浮雕
    → BR / 通道混合器（Channel Mixer） → Output / 输出

    stop_after is used by the reference-frame workflow so the user can inspect
    the result after each stage before batch rendering. Supported values:
    stretch, basic, usm, background_curves, highpass, emboss, channel.
    """
    np, *_ = _deps()
    out = img.astype(np.float32, copy=False)

    if cfg.get('stretch'):
        out = apply_asinh_stretch(out, cfg.get('stretch_strength',8.0), cfg.get('stretch_black',0.0))
    else:
        out = np.clip(out,0,1).astype(np.float32)
    if stop_after == 'stretch':
        return out

    if cfg.get('basic'):
        out = apply_base_editor(out,cfg,cfg.get('_base_curves_runtime'))
    if stop_after == 'basic':
        return out

    if cfg.get('usm'):
        passes=max(1,min(10,int(cfg.get('usm_passes',1))))
        for _ in range(passes):
            out = apply_usm(out, cfg.get('usm_amount',100.0), cfg.get('usm_radius',2.0), cfg.get('usm_threshold',0.0))
    if stop_after == 'usm':
        return out

    if cfg.get('background'):
        out = background_suppression(out, cfg.get('bg_radius',80.0), cfg.get('bg_strength',100.0))
    if cfg.get('curves') and curve_points:
        for ch in ['RGB','红色','绿色','蓝色','亮度']:
            pts = curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
            identity = len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6
            if not identity:
                out = apply_curve_lut(out, build_curve_lut(pts,256), ch)
    if stop_after == 'background_curves':
        return out

    if cfg.get('highpass'):
        out = apply_highpass(out, cfg.get('hp_radius',10.0), cfg.get('hp_amount',100.0), cfg.get('hp_mode','Overlay'))
    if stop_after == 'highpass':
        return out

    if cfg.get('emboss'):
        out = apply_emboss(out, cfg.get('emboss_angle',-128.0), cfg.get('emboss_height',1.0), cfg.get('emboss_amount',100.0), cfg.get('emboss_opacity',100.0), cfg.get('emboss_blend','Normal'), cfg.get('emboss_style','Photoshop Emboss'))
    if stop_after == 'emboss':
        return out

    if cfg.get('channel'):
        out = apply_channel_mixer(out, cfg.get('channel_output','灰色'), cfg.get('channel_mono',True),
                                  cfg.get('channel_red',40.0), cfg.get('channel_green',40.0), cfg.get('channel_blue',20.0), cfg.get('channel_constant',0.0),
                                  cfg.get('channel_noise',True), cfg.get('channel_noise_strength',30.0), cfg.get('channel_noise_radius',0.8))
    return out


class TimelapseWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app=app
        self.title(f'{APP_NAME} · 堆栈延时 v{VERSION}')
        self.geometry('1180x820')
        self.minsize(980,700)
        self.queue=Queue(); self.worker=None; self.cancel_event=threading.Event(); self.preview_photo=None
        self.curve_snapshot=copy.deepcopy(getattr(app,'curve_points',{}))
        self._init_vars(); self._build_ui(); _enforce_regular_typography(self); self.after_idle(lambda: _enforce_regular_typography(self)); self._initialize_profile_presets(); self._update_summary(); self.after(80,self._poll)

    def _init_vars(self):
        a=self.app
        self.mode=tk.StringVar(value='滑动窗口（推荐：观察变化）')
        self.stack_method=tk.StringVar(value='平均值 Mean')
        self.stack_range_start=tk.IntVar(value=1)
        self.stack_range_end=tk.IntVar(value=1)
        self.stack_range_info=tk.StringVar(value='当前堆栈区间：1 - 1（0 帧）')
        self.window_size=tk.IntVar(value=min(15,max(2,len(a.files))))
        self.step=tk.IntVar(value=1)
        self.normalize=tk.BooleanVar(value=bool(a.normalize_var.get()))
        self.summary=tk.StringVar(value='')
        self.mode_description=tk.StringVar(value='')
        self.preview_index=tk.IntVar(value=1)
        self.reference_master=None
        self.reference_group=None
        self.reference_index=None
        self.pipeline_locked=False
        self.lock_status=tk.StringVar(value='处理方案尚未锁定')
        _init_timelapse_memory_vars(self)
        _init_ewb_vars(self)
        self.normalize.set(False)  # v0.9.5 timelapse uses Exposure/WB Smoothing instead of legacy one-frame normalization.

        self.p_stretch=tk.BooleanVar(value=True)
        self.p_stretch_strength=tk.DoubleVar(value=float(getattr(a,'stretch_strength',tk.DoubleVar(value=8)).get()))
        self.p_stretch_black=tk.DoubleVar(value=float(getattr(a,'stretch_black',tk.DoubleVar(value=0)).get()))

        self.p_basic=tk.BooleanVar(value=True)
        bv=getattr(a,'basic_vars',{})
        def bget(key,default=0.0):
            try:return float(bv[key].get())
            except Exception:return float(default)
        self.p_exposure=tk.DoubleVar(value=bget('exposure')); self.p_contrast=tk.DoubleVar(value=bget('contrast'))
        self.p_highlights=tk.DoubleVar(value=bget('highlights')); self.p_shadows=tk.DoubleVar(value=bget('shadows'))
        self.p_whites=tk.DoubleVar(value=bget('whites')); self.p_blacks=tk.DoubleVar(value=bget('blacks'))
        self.p_clarity=tk.DoubleVar(value=bget('clarity')); self.p_dehaze=tk.DoubleVar(value=bget('dehaze'))
        self.p_vibrance=tk.DoubleVar(value=bget('vibrance')); self.p_saturation=tk.DoubleVar(value=bget('saturation'))

        self.p_bg=tk.BooleanVar(value=False); self.p_bg_radius=tk.DoubleVar(value=80.0); self.p_bg_strength=tk.DoubleVar(value=100.0)
        self.p_curves=tk.BooleanVar(value=False)
        self.p_usm=tk.BooleanVar(value=False); self.p_usm_amount=tk.DoubleVar(value=float(getattr(a,'usm_amount',tk.DoubleVar(value=100)).get() or 100)); self.p_usm_radius=tk.DoubleVar(value=float(getattr(a,'usm_radius',tk.DoubleVar(value=2)).get())); self.p_usm_threshold=tk.DoubleVar(value=float(getattr(a,'usm_threshold',tk.DoubleVar(value=0)).get())); self.p_usm_passes=tk.IntVar(value=1)
        self.p_hp=tk.BooleanVar(value=False); self.p_hp_radius=tk.DoubleVar(value=float(getattr(a,'hp_radius',tk.DoubleVar(value=10)).get())); self.p_hp_amount=tk.DoubleVar(value=float(getattr(a,'hp_amount',tk.DoubleVar(value=100)).get())); self.p_hp_mode=tk.StringVar(value=str(getattr(a,'hp_mode',tk.StringVar(value='Overlay')).get()))
        self.p_emboss=tk.BooleanVar(value=False); self.p_emboss_angle=tk.DoubleVar(value=float(getattr(a,'emboss_angle',tk.DoubleVar(value=-128)).get())); self.p_emboss_height=tk.DoubleVar(value=float(getattr(a,'emboss_height',tk.DoubleVar(value=1)).get())); self.p_emboss_amount=tk.DoubleVar(value=float(getattr(a,'emboss_strength',tk.DoubleVar(value=100)).get())); self.p_emboss_style=tk.StringVar(value=str(getattr(a,'emboss_style',tk.StringVar(value='Photoshop Emboss')).get())); self.p_emboss_blend=tk.StringVar(value=str(getattr(a,'emboss_blend',tk.StringVar(value='Normal')).get())); self.p_emboss_opacity=tk.DoubleVar(value=float(getattr(a,'emboss_opacity',tk.DoubleVar(value=100)).get()))
        self.p_channel=tk.BooleanVar(value=False); self.p_channel_output=tk.StringVar(value=str(getattr(a,'channel_output',tk.StringVar(value='灰色')).get())); self.p_channel_mono=tk.BooleanVar(value=bool(getattr(a,'channel_mono',tk.BooleanVar(value=True)).get()))
        self.p_channel_red=tk.DoubleVar(value=float(getattr(a,'channel_red',tk.DoubleVar(value=40)).get())); self.p_channel_green=tk.DoubleVar(value=float(getattr(a,'channel_green',tk.DoubleVar(value=40)).get())); self.p_channel_blue=tk.DoubleVar(value=float(getattr(a,'channel_blue',tk.DoubleVar(value=20)).get())); self.p_channel_constant=tk.DoubleVar(value=float(getattr(a,'channel_constant',tk.DoubleVar(value=0)).get()))
        self.p_channel_noise=tk.BooleanVar(value=bool(getattr(a,'channel_noise_protect',tk.BooleanVar(value=True)).get())); self.p_channel_noise_strength=tk.DoubleVar(value=float(getattr(a,'channel_noise_strength',tk.DoubleVar(value=30)).get())); self.p_channel_noise_radius=tk.DoubleVar(value=float(getattr(a,'channel_noise_radius',tk.DoubleVar(value=0.8)).get()))

        self.selected_profile_idx=tk.IntVar(value=0)
        self.export_profiles=[]
        profile_defaults=[
            ('01_平均值堆栈', '仅拉伸+调色', True),
            ('02_BG+Curves', '背景+曲线', True),
            ('03_USM+BG+Curves', 'USM+背景+曲线', True),
            ('04_ChannelMixer', '通道混合器', True),
            ('05_全部开启', '全部开启', True),
        ]
        for name,preset,enabled in profile_defaults:
            self.export_profiles.append({
                'enabled': tk.BooleanVar(value=enabled),
                'name': tk.StringVar(value=name),
                'preset': tk.StringVar(value=preset),
                'name_template': tk.StringVar(value='{index:02d}_{name}'),
                'save_sequence': tk.BooleanVar(value=True),
                'save_video': tk.BooleanVar(value=True),
                'delete_sequence_after_video_only': tk.BooleanVar(value=True),
                'video_format': tk.StringVar(value='MP4 H.264'),
                'scale_percent': tk.DoubleVar(value=100.0),
                'stretch': tk.BooleanVar(value=True),
                'basic': tk.BooleanVar(value=True),
                'background': tk.BooleanVar(value=False),
                'curves': tk.BooleanVar(value=False),
                'usm': tk.BooleanVar(value=False),
                'highpass': tk.BooleanVar(value=False),
                'emboss': tk.BooleanVar(value=False),
                'channel': tk.BooleanVar(value=False),
            })

        self.output_folder=tk.StringVar(value=str(Path.cwd()/'IceHaloStack_Timelapse_Output'))
        self.save_sequence=tk.BooleanVar(value=True)
        self.sequence_format=tk.StringVar(value='PNG 8-bit')
        self.video_format=tk.StringVar(value='MP4 H.264')
        self.fps=tk.DoubleVar(value=24.0)
        self.resolution=tk.StringVar(value='原始分辨率')
        self.custom_w=tk.IntVar(value=1920); self.custom_h=tk.IntVar(value=1080)
        self.fit_mode=tk.StringVar(value='Fill 裁切')
        self.progress=tk.DoubleVar(value=0.0); self.status=tk.StringVar(value='第 1 步：先生成一张参考堆栈')
        self.processing_progress=tk.DoubleVar(value=0.0);self.writing_progress=tk.DoubleVar(value=0.0)
        self.output_pipeline_text=tk.StringVar(value='写入：空闲')
        self.live_preview=tk.BooleanVar(value=True)
        self.live_preview_delay_ms=45
        self._live_preview_after_id=None
        self._live_preview_token=0
        self._live_preview_running=False
        self._live_preview_pending=False
        self._live_preview_requested_quality='fast'
        self.reference_proxy_drag=None
        self.reference_proxy_drag_scale=1.0
        self.reference_proxy_fast=None
        self.reference_proxy_fast_scale=1.0
        self.reference_proxy_hq=None
        self.reference_proxy_hq_scale=1.0
        self.tl_curve_channel=tk.StringVar(value='RGB')
        self.tl_curve_input=tk.DoubleVar(value=0.0)
        self.tl_curve_output=tk.DoubleVar(value=0.0)
        self.tl_curve_selected_idx=None
        self.tl_curve_axis_drag=None
        self._tl_curve_sync=False
        self._tl_curve_hist_source=None
        self._tl_curve_hist_cache={}
        self._tl_curve_hist_dirty=True

    def _entry_row(self,parent,label,var,width=10):
        r=ttk.Frame(parent); r.pack(fill='x',pady=2)
        ttk.Label(r,text=label).pack(side='left')
        e=ttk.Entry(r,textvariable=var,width=width,justify='right'); e.pack(side='right')
        def sel(ev=None): e.selection_range(0,'end'); e.icursor('end'); return 'break'
        e.bind('<Control-a>',sel); e.bind('<Control-A>',sel); e.bind('<Double-Button-1>',sel)
        return e

    def _slider_row(self,parent,label,var,frm,to,res=1.0,reset_value=None):
        """Numeric entry + draggable ttk.Scale for timelapse processing parameters."""
        box=ttk.Frame(parent); box.pack(fill='x',pady=2)
        top=ttk.Frame(box); top.pack(fill='x')
        ttk.Label(top,text=label).pack(side='left')
        e=ttk.Entry(top,width=10,justify='right'); e.pack(side='right')
        initial=float(var.get())
        if reset_value is None:
            reset_value = 0.0 if float(frm) <= 0.0 <= float(to) else initial

        def fmt(v):
            try:
                fv=float(v)
                if float(res) >= 1 and abs(float(res)-round(float(res))) < 1e-9:
                    return str(int(round(fv)))
                digits=4 if abs(float(res)) < 0.01 else (2 if abs(float(res)) < 1 else 1)
                return f'{fv:.{digits}f}'.rstrip('0').rstrip('.')
            except Exception:
                return str(v)

        editing={'active':False}
        def sync(*_):
            if editing['active'] and self.focus_get() == e:
                return
            e.delete(0,'end'); e.insert(0,fmt(var.get()))

        def commit(ev=None):
            try:
                v=float(e.get().strip())
                v=max(float(frm),min(float(to),v))
                var.set(v)
            except Exception:
                sync()
            editing['active']=False
            self._schedule_live_preview(force=True)
            return 'break' if ev is not None and getattr(ev,'keysym','')=='Return' else None

        def select_all(ev=None):
            editing['active']=True
            e.focus_set(); e.selection_range(0,'end'); e.icursor('end'); return 'break'

        def on_scale_move(value=None):
            sync()
            self._schedule_live_preview(dragging=True)

        scale=ttk.Scale(box,from_=frm,to=to,variable=var,command=on_scale_move)
        scale.pack(fill='x',pady=(1,0))

        def slider_press(ev=None):
            # Commit any typed value first, then move focus to Scale so FocusOut cannot
            # restore an old Entry value over the dragged slider position.
            if self.focus_get() == e:
                commit()
            try: scale.focus_set()
            except Exception: pass
            self._schedule_live_preview(dragging=True)

        def slider_release(ev=None):
            self._schedule_live_preview(force=True)

        def slider_reset(ev=None):
            var.set(float(reset_value))
            try: scale.focus_set()
            except Exception: pass
            self._schedule_live_preview(force=True)
            return 'break'

        var.trace_add('write',sync); sync()
        e.bind('<FocusIn>',lambda ev: editing.__setitem__('active',True))
        e.bind('<Return>',commit); e.bind('<FocusOut>',commit)
        e.bind('<Control-a>',select_all); e.bind('<Control-A>',select_all); e.bind('<Double-Button-1>',select_all)
        scale.bind('<ButtonPress-1>',slider_press,add='+')
        scale.bind('<ButtonRelease-1>',slider_release,add='+')
        scale.bind('<Double-Button-1>',slider_reset)
        return scale

    def _initialize_profile_presets(self):
        for i,p in enumerate(self.export_profiles):
            self._apply_profile_preset(i)
        self._rebuild_export_profiles_ui()

    def _new_export_profile(self, name=None, preset='自定义', enabled=True):
        idx=len(self.export_profiles)+1
        return {
            'enabled': tk.BooleanVar(value=enabled),
            'name': tk.StringVar(value=name or f'{idx:02d}_新输出组'),
            'preset': tk.StringVar(value=preset),
            'name_template': tk.StringVar(value='{index:02d}_{name}'),
            'save_sequence': tk.BooleanVar(value=True),
            'save_video': tk.BooleanVar(value=True),
            'video_format': tk.StringVar(value='MP4 H.264'),
            'scale_percent': tk.DoubleVar(value=100.0),
            'stretch': tk.BooleanVar(value=True),
            'basic': tk.BooleanVar(value=True),
            'background': tk.BooleanVar(value=False),
            'curves': tk.BooleanVar(value=False),
            'usm': tk.BooleanVar(value=False),
            'highpass': tk.BooleanVar(value=False),
            'emboss': tk.BooleanVar(value=False),
            'channel': tk.BooleanVar(value=False),
        }

    def _current_profile(self):
        if not self.export_profiles:
            return None
        idx=max(0,min(len(self.export_profiles)-1,int(self.selected_profile_idx.get() or 0)))
        self.selected_profile_idx.set(idx)
        return self.export_profiles[idx]

    def _apply_profile_preset(self, idx):
        p=self.export_profiles[idx]
        preset=p['preset'].get()
        mapping={
            '仅拉伸+调色': dict(stretch=True,basic=True,background=False,curves=False,usm=False,highpass=False,emboss=False,channel=False),
            '背景+曲线': dict(stretch=True,basic=True,background=True,curves=True,usm=False,highpass=False,emboss=False,channel=False),
            'USM+背景+曲线': dict(stretch=True,basic=True,background=True,curves=True,usm=True,highpass=False,emboss=False,channel=False),
            '通道混合器': dict(stretch=True,basic=True,background=False,curves=False,usm=False,highpass=False,emboss=False,channel=True),
            'USM+通道混合器': dict(stretch=True,basic=True,background=False,curves=False,usm=True,highpass=False,emboss=False,channel=True),
            '全部开启': dict(stretch=True,basic=True,background=True,curves=True,usm=True,highpass=True,emboss=True,channel=True),
            '自定义': None,
        }
        m=mapping.get(preset)
        if m:
            for k,v in m.items():
                p[k].set(bool(v))
        self._update_profile_summary(); self._draw_selected_profile_graph(); self._schedule_live_preview(force=True)

    def _build_export_profiles_ui(self, parent):
        self.export_box=ttk.LabelFrame(parent,text='多路序列导出（无限输出组）',padding=6); self.export_box.pack(fill='x',pady=(8,0))
        ttk.Label(self.export_box,text='这一版开始支持无限多个输出组。每个输出组都可以有自己的流程、预览、是否保存序列、是否保存视频、视频格式、命名模板，以及按原始比例缩小输出尺寸。下方节点画布会显示当前选中输出组的工作流。',foreground='#555555',wraplength=430).pack(anchor='w',pady=(0,6))
        tools=ttk.Frame(self.export_box); tools.pack(fill='x',pady=(0,4))
        ttk.Button(tools,text='＋ 新增输出组',command=self._add_export_profile).pack(side='left')
        ttk.Button(tools,text='－ 删除当前输出组',command=self._remove_selected_profile).pack(side='left',padx=(6,0))
        ttk.Button(tools,text='复制当前输出组',command=self._duplicate_selected_profile).pack(side='left',padx=(6,0))
        self.profile_rows=ttk.Frame(self.export_box); self.profile_rows.pack(fill='x')
        self.profile_summary=tk.StringVar(value='')
        ttk.Label(self.export_box,textvariable=self.profile_summary,foreground='#666666',wraplength=430).pack(anchor='w',pady=(6,4))
        self.profile_canvas_title=tk.StringVar(value='节点画布：未选择输出组')
        ttk.Label(self.export_box,textvariable=self.profile_canvas_title,font=_ui_font(9)).pack(anchor='w',pady=(2,2))
        self.profile_node_canvas=tk.Canvas(self.export_box,height=145,bg='#161616',highlightthickness=1,highlightbackground='#3a3a3a')
        self.profile_node_canvas.pack(fill='x',pady=(0,4))
        self.profile_node_canvas.bind('<Button-1>', self._on_profile_canvas_click)
        self._rebuild_export_profiles_ui()

    def _rebuild_export_profiles_ui(self):
        if not hasattr(self,'profile_rows'):
            return
        for w in self.profile_rows.winfo_children():
            w.destroy()
        presets=['仅拉伸+调色','背景+曲线','USM+背景+曲线','通道混合器','USM+通道混合器','全部开启','自定义']
        vfmts=['不生成视频','MP4 H.264','MOV H.264','MOV ProRes','GIF']
        for i,p in enumerate(self.export_profiles,1):
            row=ttk.LabelFrame(self.profile_rows,text=f'输出组 {i}',padding=4); row.pack(fill='x',pady=3)
            top=ttk.Frame(row); top.pack(fill='x')
            ttk.Radiobutton(top,text='预览',variable=self.selected_profile_idx,value=i-1,command=self._on_selected_profile_changed).pack(side='left')
            ttk.Checkbutton(top,text='启用',variable=p['enabled'],command=self._on_profile_option_changed).pack(side='left',padx=(4,0))
            ttk.Entry(top,textvariable=p['name'],width=16).pack(side='left',padx=(6,4))
            ttk.Label(top,text='预设').pack(side='left')
            cb=ttk.Combobox(top,textvariable=p['preset'],state='readonly',width=14,values=presets)
            cb.pack(side='left',padx=(4,8)); cb.bind('<<ComboboxSelected>>',lambda e,idx=i-1:self._apply_profile_preset(idx))
            ttk.Label(top,text='命名模板').pack(side='left')
            ttk.Entry(top,textvariable=p['name_template'],width=16).pack(side='left',padx=(4,0))
            io=ttk.Frame(row); io.pack(fill='x',pady=(4,0))
            ttk.Checkbutton(io,text='保存序列',variable=p['save_sequence'],command=self._on_profile_option_changed).pack(side='left')
            ttk.Checkbutton(io,text='保存视频',variable=p['save_video'],command=self._on_profile_option_changed).pack(side='left',padx=(8,0))
            ttk.Combobox(io,textvariable=p['video_format'],state='readonly',width=12,values=vfmts).pack(side='left',padx=(8,0))
            ttk.Label(io,text='缩放 %').pack(side='left',padx=(8,0))
            ttk.Entry(io,textvariable=p['scale_percent'],width=7,justify='right').pack(side='left',padx=(4,0))
            mods=ttk.Frame(row); mods.pack(fill='x',pady=(4,0))
            for key,label in [('stretch','拉伸'),('basic','调色'),('background','BG'),('curves','Curves'),('usm','USM'),('highpass','HighPass'),('emboss','Emboss'),('channel','ChannelMixer')]:
                ttk.Checkbutton(mods,text=label,variable=p[key],command=self._on_profile_option_changed).pack(side='left')
        self._update_profile_summary(); self._draw_selected_profile_graph()

    def _add_export_profile(self):
        self.export_profiles.append(self._new_export_profile())
        self.selected_profile_idx.set(len(self.export_profiles)-1)
        self._rebuild_export_profiles_ui(); self._schedule_live_preview(force=True)

    def _remove_selected_profile(self):
        if len(self.export_profiles) <= 1:
            messagebox.showinfo(APP_NAME,'至少保留 1 个输出组。',parent=self); return
        idx=max(0,min(len(self.export_profiles)-1,int(self.selected_profile_idx.get() or 0)))
        self.export_profiles.pop(idx)
        self.selected_profile_idx.set(max(0,min(idx,len(self.export_profiles)-1)))
        self._rebuild_export_profiles_ui(); self._schedule_live_preview(force=True)

    def _duplicate_selected_profile(self):
        p=self._current_profile()
        if p is None: return
        new=self._new_export_profile(name=p['name'].get()+'_副本', preset='自定义', enabled=p['enabled'].get())
        for k in ['name_template','save_sequence','save_video','delete_sequence_after_video_only','video_format','scale_percent','stretch','basic','background','curves','usm','highpass','emboss','channel']:
            try: new[k].set(p[k].get())
            except Exception: pass
        self.export_profiles.append(new)
        self.selected_profile_idx.set(len(self.export_profiles)-1)
        self._rebuild_export_profiles_ui(); self._schedule_live_preview(force=True)

    def _sanitize_profile_name(self, name, fallback='output'):
        bad='<>:"/' + '\\' + '|?*'
        txt=''.join(ch if ch not in bad else '_' for ch in str(name).strip())
        txt=' '.join(txt.split())
        return txt or fallback

    def _format_output_name(self, prof, method='mean', mode='timelapse'):
        raw_tpl = prof.get('name_template', '{index:02d}_{name}')
        tpl = str(raw_tpl.get() if hasattr(raw_tpl,'get') else raw_tpl) or '{index:02d}_{name}'
        raw_name = prof.get('name', 'output')
        name = self._sanitize_profile_name(raw_name.get() if hasattr(raw_name,'get') else raw_name, 'output')
        raw_index = prof.get('index', 1)
        index = int(raw_index.get() if hasattr(raw_index,'get') else raw_index)
        data={'index':index, 'name':name, 'method':method, 'mode':mode}
        try:
            out=tpl.format(**data)
        except Exception:
            out=f"{int(data['index']):02d}_{name}"
        return self._sanitize_profile_name(out, f"{int(data['index']):02d}_{name}")

    def _profile_to_cfg(self, base_cfg, p):
        cfg=dict(base_cfg)
        for k in ['stretch','basic','background','curves','usm','highpass','emboss','channel']:
            cfg[k]=bool(p[k].get())
        return cfg

    def _iter_enabled_export_profiles(self, base_cfg):
        out=[]
        for i,p in enumerate(self.export_profiles,1):
            save_seq=bool(p['save_sequence'].get())
            save_video=bool(p['save_video'].get()) and str(p['video_format'].get())!='不生成视频'
            if not bool(p['enabled'].get()):
                continue
            if not save_seq and not save_video:
                continue
            cfg=self._profile_to_cfg(base_cfg,p)
            name=self._sanitize_profile_name(p['name'].get(), f'output_{i:02d}')
            out.append({'index':i,'name':name,'cfg':cfg,'name_template':str(p['name_template'].get()),'save_sequence':save_seq,'save_video':save_video,'delete_sequence_after_video_only':bool(p['delete_sequence_after_video_only'].get()),'video_format':str(p['video_format'].get()),'scale_percent':max(1.0,float(p['scale_percent'].get() or 100.0))})
        return out

    def _update_profile_summary(self):
        lines=[]
        for i,p in enumerate(self.export_profiles,1):
            if not bool(p['enabled'].get()):
                continue
            mods=[]
            for key,label in [('stretch','拉伸'),('basic','调色'),('background','BG'),('curves','Curves'),('usm','USM'),('highpass','HighPass'),('emboss','Emboss'),('channel','ChannelMixer')]:
                if bool(p[key].get()): mods.append(label)
            saves=[]
            if bool(p['save_sequence'].get()): saves.append('序列')
            if bool(p['save_video'].get()) and str(p['video_format'].get())!='不生成视频': saves.append(str(p['video_format'].get()))
            lines.append(f"{i}. {self._sanitize_profile_name(p['name'].get(), f'output_{i:02d}')} → " + (' → '.join(mods) if mods else '仅保存线性结果') + ' ｜ 输出：' + (' + '.join(saves) if saves else '无') + f" ｜ 缩放 {float(p['scale_percent'].get() or 100.0):.0f}%")
        txt='；'.join(lines) if lines else '当前没有有效输出组。请启用输出组，并至少勾选保存序列或保存视频。'
        if hasattr(self,'profile_summary'): self.profile_summary.set(txt)

    def _on_profile_option_changed(self, *args):
        self._update_profile_summary(); self._draw_selected_profile_graph(); self._schedule_live_preview(force=True)

    def _on_selected_profile_changed(self):
        self._draw_selected_profile_graph(); self._schedule_live_preview(force=True)

    def _draw_selected_profile_graph(self):
        if not hasattr(self,'profile_node_canvas'):
            return
        c=self.profile_node_canvas; c.delete('all')
        p=self._current_profile()
        if p is None:
            return
        self.profile_canvas_title.set(f"节点画布：{self._sanitize_profile_name(p['name'].get(),'output')}（点击下方节点可切换启用/禁用）")
        W=max(c.winfo_width(),520); H=max(c.winfo_height(),145)
        y=H//2
        labels=[('stack','Stack',True),('stretch','Stretch',p['stretch'].get()),('basic','Basic',p['basic'].get()),('background','BG',p['background'].get()),('curves','Curves',p['curves'].get()),('usm','USM',p['usm'].get()),('highpass','HP',p['highpass'].get()),('emboss','Emboss',p['emboss'].get()),('channel','Mixer',p['channel'].get()),('output','Output',True)]
        xs=[]; n=len(labels)
        left=35; right=W-35
        step=(right-left)/max(1,n-1)
        self._profile_canvas_hit=[]
        for i,(key,label,enabled) in enumerate(labels):
            x=int(round(left+i*step)); xs.append(x)
        enabled_keys=[k for k,_,e in labels if e]
        # draw connections between enabled pipeline stages
        prev_x=None
        for (key,label,enabled),x in zip(labels,xs):
            if enabled:
                if prev_x is not None:
                    c.create_line(prev_x+36,y,x-36,y,fill='#5fb0ff',width=2,arrow='last')
                prev_x=x
        for (key,label,enabled),x in zip(labels,xs):
            fill='#2e8fff' if enabled else '#3a3a3a'
            outline='#bfe0ff' if enabled else '#777777'
            c.create_rectangle(x-36,y-20,x+36,y+20,fill=fill,outline=outline,width=2)
            c.create_text(x,y-1,text=label,fill='white' if enabled else '#cccccc',font=_ui_font(9))
            if key not in ('stack','output'):
                self._profile_canvas_hit.append((x-36,y-20,x+36,y+20,key))
        c.create_text(8,10,anchor='nw',text='固定顺序：Stack → Stretch → Basic → BG → Curves → USM → HighPass → Emboss → ChannelMixer → Output',fill='#bbbbbb',font=_ui_font(8))

    def _on_profile_canvas_click(self, event):
        p=self._current_profile()
        if p is None: return
        for x1,y1,x2,y2,key in getattr(self,'_profile_canvas_hit',[]):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                p[key].set(not bool(p[key].get()))
                self._on_profile_option_changed()
                return

    def _build_ui(self):
        root=ttk.Frame(self,padding=8); root.pack(fill='both',expand=True)
        top=ttk.Frame(root); top.pack(fill='x')
        ttk.Label(top,text='堆栈延时 / Stack Timelapse',font=_ui_font(15)).pack(side='left')
        ttk.Label(top,text=f'输入 {len(self.app.files)} 帧',foreground='#666666').pack(side='right')
        ttk.Separator(root).pack(fill='x',pady=7)
        pane=ttk.Panedwindow(root,orient='horizontal'); pane.pack(fill='both',expand=True)
        left_outer=ttk.Frame(pane); right=ttk.Frame(pane,padding=(8,0,0,0)); pane.add(left_outer,weight=3); pane.add(right,weight=4)
        canvas=tk.Canvas(left_outer,highlightthickness=0); sb=ttk.Scrollbar(left_outer,orient='vertical',command=canvas.yview,style='IHS.Vertical.TScrollbar'); canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
        left=ttk.Frame(canvas,padding=(2,0,8,0)); wid=canvas.create_window((0,0),window=left,anchor='nw')
        left.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all'))); canvas.bind('<Configure>',lambda e:canvas.itemconfigure(wid,width=e.width))
        canvas.bind('<Enter>',lambda e:canvas.bind_all('<MouseWheel>',lambda ev:canvas.yview_scroll(-1 if ev.delta>0 else 1,'units'))); canvas.bind('<Leave>',lambda e:canvas.unbind_all('<MouseWheel>'))

        gen=ttk.LabelFrame(left,text='第 1 步 · 生成参考堆栈',padding=8); gen.pack(fill='x')
        r=ttk.Frame(gen); r.pack(fill='x',pady=2); ttk.Label(r,text='生成模式').pack(side='left'); modecb=ttk.Combobox(r,textvariable=self.mode,state='readonly',width=28,values=['滑动窗口（推荐：观察变化）','中心窗口（按中央时刻理解）','累计堆栈（观察信号生长）','逐帧剔除（贡献分析）']); modecb.pack(side='right')
        ttk.Label(gen,textvariable=self.mode_description,foreground='#555555',wraplength=430,justify='left').pack(anchor='w',pady=(5,7))
        r=ttk.Frame(gen); r.pack(fill='x',pady=2); ttk.Label(r,text='堆栈方式').pack(side='left'); ttk.Combobox(r,textvariable=self.stack_method,state='readonly',width=24,values=['平均值 Mean','最大值 Maximum']).pack(side='right')
        self._entry_row(gen,'窗口大小（帧）',self.window_size); self._entry_row(gen,'步长（帧）',self.step)
        ttk.Label(gen,textvariable=self.summary,foreground='#555555',wraplength=430).pack(anchor='w',pady=(5,4))
        rr=ttk.Frame(gen); rr.pack(fill='x',pady=(5,0)); ttk.Label(rr,text='参考输出帧').pack(side='left'); self.preview_spin=ttk.Spinbox(rr,textvariable=self.preview_index,from_=1,to=1,width=8); self.preview_spin.pack(side='left',padx=6); ttk.Button(rr,text='生成参考堆栈',style='Primary.TButton',command=self.generate_reference).pack(side='right')
        ttk.Label(gen,text='参考堆栈只生成一次。后面调拉伸、颜色、Background、Curves、USM、浮雕时都直接在这张参考图上预览，不会反复重新堆栈。',foreground='#666666',wraplength=430).pack(anchor='w',pady=(6,0))
        _build_ewb_panel(self,left,wraplength=430)
        _build_timelapse_memory_panel(self,left,wraplength=430)

        proc=ttk.LabelFrame(left,text='第 2 步 · 在参考图上搭建处理链',padding=8); proc.pack(fill='x',pady=(8,0))
        ttk.Label(proc,text='每一段都有蓝色滑块 + 可直接输入的数值框，并可“预览到此步骤”。后面的批量帧会使用完全相同的参数。',foreground='#555555',wraplength=430).pack(anchor='w',pady=(0,6))

        # Stretch
        sec=ttk.LabelFrame(proc,text='A. 拉伸',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用 Asinh 拉伸',variable=self.p_stretch).pack(anchor='w'); self._slider_row(sec,'Strength',self.p_stretch_strength,0.1,500,0.1,reset_value=float(self.p_stretch_strength.get())); self._slider_row(sec,'Black Point',self.p_stretch_black,0.0,0.25,0.0001,reset_value=0.0)
        ttk.Button(sec,text='预览：拉伸后',command=lambda:self.preview_stage('stretch')).pack(fill='x',pady=(4,0))

        # Basic color/tone
        sec=ttk.LabelFrame(proc,text='B. 基础调色',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用基础调色',variable=self.p_basic).pack(anchor='w')
        self._slider_row(sec,'Exposure EV',self.p_exposure,-3,3,0.05,reset_value=0.0)
        for label,var in [('Contrast',self.p_contrast),('Highlights',self.p_highlights),('Shadows',self.p_shadows),('Whites',self.p_whites),('Blacks',self.p_blacks),('Clarity',self.p_clarity),('Dehaze',self.p_dehaze),('Vibrance',self.p_vibrance),('Saturation',self.p_saturation)]:
            self._slider_row(sec,label,var,-100,100,1,reset_value=0.0)
        ttk.Button(sec,text='预览：拉伸 + 调色后',command=lambda:self.preview_stage('basic')).pack(fill='x',pady=(4,0))

        # Background + Curves: curves are edited directly on the timelapse reference frame.
        sec=ttk.LabelFrame(proc,text='C. Background + Curves',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='Background Suppression 背景抑制',variable=self.p_bg).pack(anchor='w'); self._slider_row(sec,'Radius px',self.p_bg_radius,1,500,1,reset_value=80.0); self._slider_row(sec,'Strength %',self.p_bg_strength,0,200,1,reset_value=100.0)
        cr=ttk.Frame(sec); cr.pack(fill='x',pady=(5,3)); ttk.Checkbutton(cr,text='使用 Curves',variable=self.p_curves).pack(side='left'); ttk.Button(cr,text='读取主界面曲线',command=self._capture_curves).pack(side='right')
        crow=ttk.Frame(sec); crow.pack(fill='x',pady=(2,3)); ttk.Label(crow,text='曲线通道').pack(side='left')
        ccb=ttk.Combobox(crow,textvariable=self.tl_curve_channel,state='readonly',width=10,values=['RGB','红色','绿色','蓝色','亮度']); ccb.pack(side='right'); ccb.bind('<<ComboboxSelected>>',lambda e:self._tl_curve_channel_changed())
        self.tl_curve_canvas=tk.Canvas(sec,height=285,bg='#202020',highlightthickness=1,highlightbackground='#404040')
        self.tl_curve_canvas.pack(fill='x',pady=(2,4))
        self.tl_curve_canvas.bind('<Button-1>',self._tl_curve_click); self.tl_curve_canvas.bind('<B1-Motion>',self._tl_curve_drag); self.tl_curve_canvas.bind('<ButtonRelease-1>',self._tl_curve_release); self.tl_curve_canvas.bind('<Button-3>',self._tl_curve_right_click); self.tl_curve_canvas.bind('<Configure>',lambda e:(self.tl_curve_canvas.delete('curve_static'),self._draw_tl_curve_editor()))
        cv=ttk.Frame(sec); cv.pack(fill='x',pady=(0,4))
        ttk.Label(cv,text='输入').grid(row=0,column=0,sticky='w'); ie=ttk.Entry(cv,textvariable=self.tl_curve_input,width=9,justify='right'); ie.grid(row=0,column=1,sticky='ew',padx=(4,10))
        ttk.Label(cv,text='输出').grid(row=0,column=2,sticky='w'); oe=ttk.Entry(cv,textvariable=self.tl_curve_output,width=9,justify='right'); oe.grid(row=0,column=3,sticky='ew',padx=(4,0)); cv.columnconfigure(1,weight=1); cv.columnconfigure(3,weight=1)
        for ee in (ie,oe):
            ee.bind('<Control-a>',lambda ev,e=ee:(e.selection_range(0,'end'),'break')[1]); ee.bind('<Control-A>',lambda ev,e=ee:(e.selection_range(0,'end'),'break')[1]); ee.bind('<Double-Button-1>',lambda ev,e=ee:(e.focus_set(),e.selection_range(0,'end'),'break')[2])
        self.tl_curve_input.trace_add('write',lambda *a:self._tl_curve_numeric_changed()); self.tl_curve_output.trace_add('write',lambda *a:self._tl_curve_numeric_changed())
        cbuttons=ttk.Frame(sec); cbuttons.pack(fill='x',pady=(2,2)); ttk.Button(cbuttons,text='重置当前通道',command=self._reset_tl_curve_current).pack(side='left',fill='x',expand=True,padx=(0,3)); ttk.Button(cbuttons,text='重置全部曲线',command=self._reset_tl_curves).pack(side='left',fill='x',expand=True,padx=(3,0))
        ttk.Label(sec,text='点击添加控制点；左右拖动改变 Input，上下拖动改变 Output；右键删除中间控制点。灰色波峰为参考帧在进入 Curves 前的直方图。',foreground='#666666',wraplength=420).pack(anchor='w',pady=(3,2))
        ttk.Button(sec,text='预览：Background + Curves 后',command=lambda:self.preview_stage('background_curves')).pack(fill='x',pady=(4,0))

        # USM with repeat count.
        sec=ttk.LabelFrame(proc,text='D. USM 锐化（可重复）',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用 USM',variable=self.p_usm).pack(anchor='w'); self._slider_row(sec,'Amount %',self.p_usm_amount,0,500,1,reset_value=0.0); self._slider_row(sec,'Radius px',self.p_usm_radius,0.1,250,0.1,reset_value=2.0); self._slider_row(sec,'Threshold',self.p_usm_threshold,0,255,1,reset_value=0.0); self._slider_row(sec,'重复次数（1–10）',self.p_usm_passes,1,10,1,reset_value=1)
        ttk.Label(sec,text='例如次数=3：同一组 USM 参数连续应用 3 次。',foreground='#666666').pack(anchor='w')
        ttk.Button(sec,text='预览：USM 后',command=lambda:self.preview_stage('usm')).pack(fill='x',pady=(4,0))

        sec=ttk.LabelFrame(proc,text='E. High Pass',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用 High Pass',variable=self.p_hp).pack(anchor='w'); self._slider_row(sec,'Radius px',self.p_hp_radius,0.1,250,0.1,reset_value=10.0); self._slider_row(sec,'Opacity %',self.p_hp_amount,0,100,1,reset_value=100.0)
        r=ttk.Frame(sec); r.pack(fill='x',pady=2); ttk.Label(r,text='Mode').pack(side='left'); ttk.Combobox(r,textvariable=self.p_hp_mode,state='readonly',width=15,values=['Overlay','Soft Light','Linear Light']).pack(side='right')
        ttk.Button(sec,text='预览：High Pass 后',command=lambda:self.preview_stage('highpass')).pack(fill='x',pady=(4,0))

        sec=ttk.LabelFrame(proc,text='F. 浮雕 Emboss',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用浮雕',variable=self.p_emboss).pack(anchor='w')
        r=ttk.Frame(sec);r.pack(fill='x',pady=2);ttk.Label(r,text='Style').pack(side='left');ttk.Combobox(r,textvariable=self.p_emboss_style,state='readonly',width=20,values=['Photoshop Emboss','Color Emboss','Gray Emboss']).pack(side='right')
        self._slider_row(sec,'Angle °',self.p_emboss_angle,-180,180,1,reset_value=-128.0)
        dialrow=ttk.Frame(sec);dialrow.pack(fill='x',pady=(1,3));ttk.Label(dialrow,text='Angle Dial / 方向圆盘',foreground='#666').pack(side='left');AngleDial(dialrow,self.p_emboss_angle,command=lambda v:self._schedule_live_preview(dragging=True),release_command=lambda v:self._schedule_live_preview(force=True),reset_value=-128.0,size=66).pack(side='right')
        self._slider_row(sec,'Height px',self.p_emboss_height,1,200,1,reset_value=1.0); self._slider_row(sec,'Amount %',self.p_emboss_amount,1,500,1,reset_value=100.0)
        r=ttk.Frame(sec);r.pack(fill='x',pady=2);ttk.Label(r,text='Blend Mode').pack(side='left');ttk.Combobox(r,textvariable=self.p_emboss_blend,state='readonly',width=16,values=['Normal','Overlay','Soft Light','Linear Light']).pack(side='right')
        self._slider_row(sec,'Opacity %',self.p_emboss_opacity,0,100,1,reset_value=100.0)
        ttk.Label(sec,text='Photoshop Emboss：PS 风格灰色浮雕基底 + 原色边缘描迹；Color Emboss：完整保留原图色彩；Gray Emboss：旧版中性灰浮雕。',foreground='#666',wraplength=390).pack(anchor='w',pady=(2,0))
        ttk.Button(sec,text='预览：浮雕后',command=lambda:self.preview_stage('emboss')).pack(fill='x',pady=(4,0))

        sec=ttk.LabelFrame(proc,text='G. Channel Mixer',padding=6); sec.pack(fill='x',pady=3)
        ttk.Checkbutton(sec,text='启用通道混合器',variable=self.p_channel).pack(anchor='w')
        r=ttk.Frame(sec); r.pack(fill='x',pady=2); ttk.Label(r,text='输出').pack(side='left'); ttk.Combobox(r,textvariable=self.p_channel_output,state='readonly',width=12,values=['灰色','红色','绿色','蓝色']).pack(side='right')
        ttk.Checkbutton(sec,text='单色',variable=self.p_channel_mono).pack(anchor='w'); self._slider_row(sec,'R %',self.p_channel_red,-200,200,1,reset_value=40.0); self._slider_row(sec,'G %',self.p_channel_green,-200,200,1,reset_value=40.0); self._slider_row(sec,'B %',self.p_channel_blue,-200,200,1,reset_value=20.0); self._slider_row(sec,'常数 %',self.p_channel_constant,-100,100,1,reset_value=0.0)
        ttk.Checkbutton(sec,text='色彩噪声保护',variable=self.p_channel_noise).pack(anchor='w'); self._slider_row(sec,'噪声保护强度 %',self.p_channel_noise_strength,0,100,1,reset_value=30.0); self._slider_row(sec,'噪声保护半径 px',self.p_channel_noise_radius,0.1,10,0.1,reset_value=0.8)
        ttk.Button(sec,text='预览：最终处理效果',command=lambda:self.preview_stage('channel')).pack(fill='x',pady=(4,0))

        lock=ttk.Frame(proc); lock.pack(fill='x',pady=(8,2)); self.lock_btn=ttk.Button(lock,text='锁定当前处理方案',style='Primary.TButton',command=self.lock_pipeline); self.lock_btn.pack(side='left',fill='x',expand=True); ttk.Label(lock,textvariable=self.lock_status,foreground='#666666').pack(side='right',padx=(8,0))

        out=ttk.LabelFrame(left,text='第 3 步 · 批量生成与视频输出',padding=8); out.pack(fill='x',pady=(8,0))
        r=ttk.Frame(out); r.pack(fill='x'); ttk.Entry(r,textvariable=self.output_folder).pack(side='left',fill='x',expand=True); ttk.Button(r,text='选择...',command=self._choose_output).pack(side='right',padx=(5,0))
        r=ttk.Frame(out); r.pack(fill='x',pady=(5,2)); ttk.Checkbutton(r,text='保存图像序列',variable=self.save_sequence).pack(side='left'); ttk.Combobox(r,textvariable=self.sequence_format,state='readonly',width=17,values=['PNG 8-bit','JPEG','TIFF 16-bit','TIFF 32-bit Float']).pack(side='right')
        r=ttk.Frame(out); r.pack(fill='x',pady=2); ttk.Label(r,text='视频格式').pack(side='left'); ttk.Combobox(r,textvariable=self.video_format,state='readonly',width=18,values=['不生成视频','MP4 H.264','MOV H.264','MOV ProRes','GIF']).pack(side='right')
        self._entry_row(out,'FPS',self.fps)
        r=ttk.Frame(out); r.pack(fill='x',pady=2); ttk.Label(r,text='视频分辨率').pack(side='left'); ttk.Combobox(r,textvariable=self.resolution,state='readonly',width=20,values=['原始分辨率','16:9 · 3840×2160','4:3 · 2880×2160','自定义']).pack(side='right')
        self._entry_row(out,'自定义 Width',self.custom_w); self._entry_row(out,'自定义 Height',self.custom_h)
        r=ttk.Frame(out); r.pack(fill='x',pady=2); ttk.Label(r,text='宽高比处理').pack(side='left'); ttk.Combobox(r,textvariable=self.fit_mode,state='readonly',width=16,values=['Fill 裁切','Fit 黑边','Stretch 拉伸']).pack(side='right')
        self._build_export_profiles_ui(out)

        prev=ttk.LabelFrame(right,text='参考图 / 处理效果预览',padding=6); prev.pack(fill='both',expand=True)
        self.preview_title=tk.StringVar(value='尚未生成参考堆栈')
        prev_head=ttk.Frame(prev);prev_head.pack(fill='x')
        ttk.Label(prev_head,textvariable=self.preview_title,font=_ui_font(10)).pack(side='left',anchor='w')
        self.preview_zoom_text=tk.StringVar(value='Fit')
        zoom_bar=ttk.Frame(prev_head);zoom_bar.pack(side='right')
        for label,value in [('25%',0.25),('50%',0.50),('100%',1.0),('200%',2.0)]:
            ttk.Button(zoom_bar,text=label,width=5,command=lambda v=value:self._preview_set_zoom(v)).pack(side='left',padx=1)
        ttk.Button(zoom_bar,text='Fit',width=5,command=self._preview_fit).pack(side='left',padx=(2,0))
        ttk.Label(zoom_bar,textvariable=self.preview_zoom_text,width=10,anchor='e').pack(side='left',padx=(5,0))
        ttk.Checkbutton(prev,text='实时预览参考帧处理效果',variable=self.live_preview,command=lambda:self._schedule_live_preview(force=True)).pack(anchor='w',pady=(2,0))
        self.preview_canvas=tk.Canvas(prev,bg='#151515',highlightthickness=0); self.preview_canvas.pack(fill='both',expand=True,pady=(6,0)); self.preview_canvas.create_text(15,15,anchor='nw',fill='#aaa',text='第 1 步：点击“生成参考堆栈”。')
        self.preview_zoom=1.0; self.preview_fit_mode=True; self.preview_pan=[0.0,0.0]; self.preview_pan_anchor=None; self.last_preview_image=None; self.preview_display_rect=None
        self.preview_canvas.bind('<MouseWheel>',self._preview_wheel)
        self.preview_canvas.bind('<Button-4>',lambda e:self._preview_wheel_linux(e,1))
        self.preview_canvas.bind('<Button-5>',lambda e:self._preview_wheel_linux(e,-1))
        self.preview_canvas.bind('<ButtonPress-1>',self._preview_pan_start)
        self.preview_canvas.bind('<B1-Motion>',self._preview_pan_drag)
        self.preview_canvas.bind('<ButtonRelease-1>',self._preview_pan_end)
        self.preview_canvas.bind('z',lambda e:self._preview_fit())
        self.preview_canvas.bind('Z',lambda e:self._preview_fit())
        self.preview_canvas.bind('<Configure>',lambda e:self._preview_redraw(),add='+')
        ttk.Label(right,text='工作流：先确认参考堆栈 → 在同一张参考图上逐段预览处理 → 锁定参数 → 批量应用到全部时间帧。开启“实时预览”后，拖动滑块或修改数值会自动刷新右侧参考帧画面。',foreground='#555555',wraplength=600).pack(anchor='w',pady=(6,4))
        br=ttk.Frame(right); br.pack(fill='x',pady=(3,0)); self.start_btn=ttk.Button(br,text='开始批量生成',style='Primary.TButton',command=self.start_batch,state='disabled'); self.start_btn.pack(side='left',fill='x',expand=True,padx=(0,4)); self.cancel_btn=ttk.Button(br,text='取消',command=self.cancel,state='disabled'); self.cancel_btn.pack(side='right',padx=(4,0))
        ttk.Label(right,text='Processing / 处理',foreground='#666').pack(anchor='w',pady=(7,0))
        ttk.Progressbar(right,variable=self.processing_progress,maximum=100).pack(fill='x',pady=(2,2))
        ttk.Label(right,text='Writing / 写入',foreground='#666').pack(anchor='w',pady=(2,0))
        ttk.Progressbar(right,variable=self.writing_progress,maximum=100).pack(fill='x',pady=(2,2))
        ttk.Label(right,textvariable=self.output_pipeline_text,foreground='#666',wraplength=600).pack(anchor='w',pady=(1,2))
        ttk.Progressbar(right,variable=self.progress,maximum=100).pack(fill='x',pady=(4,3)); ttk.Label(right,textvariable=self.status).pack(anchor='w')

        for v in (self.mode,self.stack_method,self.window_size,self.step):
            v.trace_add('write',lambda *a:self._update_summary())
        proc_vars=[self.p_stretch,self.p_stretch_strength,self.p_stretch_black,self.p_basic,self.p_exposure,self.p_contrast,self.p_highlights,self.p_shadows,self.p_whites,self.p_blacks,self.p_clarity,self.p_dehaze,self.p_vibrance,self.p_saturation,self.p_bg,self.p_bg_radius,self.p_bg_strength,self.p_curves,self.p_usm,self.p_usm_amount,self.p_usm_radius,self.p_usm_threshold,self.p_usm_passes,self.p_hp,self.p_hp_radius,self.p_hp_amount,self.p_hp_mode,self.p_emboss,self.p_emboss_angle,self.p_emboss_height,self.p_emboss_amount,self.p_emboss_style,self.p_emboss_blend,self.p_emboss_opacity,self.p_channel,self.p_channel_output,self.p_channel_mono,self.p_channel_red,self.p_channel_green,self.p_channel_blue,self.p_channel_constant,self.p_channel_noise,self.p_channel_noise_strength,self.p_channel_noise_radius]
        for v in proc_vars:v.trace_add('write',lambda *a:self._on_processing_param_changed())
        # Only parameters *before* Curves change the histogram entering Curves.
        # Cache that histogram so dragging a curve point never recomputes Background/Basic/Stretch.
        curve_hist_upstream=[self.p_stretch,self.p_stretch_strength,self.p_stretch_black,self.p_basic,self.p_exposure,self.p_contrast,self.p_highlights,self.p_shadows,self.p_whites,self.p_blacks,self.p_clarity,self.p_dehaze,self.p_vibrance,self.p_saturation,self.p_bg,self.p_bg_radius,self.p_bg_strength]
        for v in curve_hist_upstream:v.trace_add('write',lambda *a:self._invalidate_tl_curve_hist())

    def _capture_curves(self):
        self.curve_snapshot=copy.deepcopy(getattr(self.app,'curve_points',{})); self.status.set('已读取主界面当前 Curves 控制点'); self._mark_pipeline_dirty(); self._draw_tl_curve_editor(); self._schedule_live_preview(force=True)

    def _on_processing_param_changed(self):
        self._mark_pipeline_dirty()
        self._schedule_live_preview()

    def _schedule_live_preview(self, force=False, dragging=False):
        if self.reference_master is None or not bool(self.live_preview.get()):
            return
        if self.worker and self.worker.is_alive() and not force:
            return
        self._live_preview_requested_quality = 'drag' if dragging else ('hq' if force else 'fast')
        try:
            if self._live_preview_after_id is not None:
                self.after_cancel(self._live_preview_after_id)
        except Exception:
            pass
        delay = 1 if force else (18 if dragging else int(self.live_preview_delay_ms))
        self._live_preview_after_id = self.after(delay, self._launch_live_preview)

    def _launch_live_preview(self):
        self._live_preview_after_id=None
        if self.reference_master is None or not bool(self.live_preview.get()):
            return
        if self._live_preview_running:
            self._live_preview_pending=True
            return
        quality=self._live_preview_requested_quality
        if quality=='hq' and self.reference_proxy_hq is not None:
            base=self.reference_proxy_hq; scale=self.reference_proxy_hq_scale
        elif quality=='drag' and self.reference_proxy_drag is not None:
            base=self.reference_proxy_drag; scale=self.reference_proxy_drag_scale
        elif self.reference_proxy_fast is not None:
            base=self.reference_proxy_fast; scale=self.reference_proxy_fast_scale
        else:
            base=self.reference_master; scale=1.0
        base_cfg=self._snapshot_cfg();
        current_profile=self._current_profile()
        effective_cfg=self._profile_to_cfg(base_cfg,current_profile) if current_profile is not None else base_cfg
        cfg=scale_timelapse_cfg_for_proxy(effective_cfg,scale); curves=copy.deepcopy(self.curve_snapshot)
        self._live_preview_token += 1
        token=self._live_preview_token
        self._live_preview_running=True
        qname='拖动代理' if quality=='drag' else ('快速代理' if quality=='fast' else '高质量代理')
        self.preview_title.set('实时预览：最终处理效果 · '+qname)
        self.status.set('正在实时刷新参考帧预览…')
        def work():
            try:
                out=apply_timelapse_pipeline(base,cfg,curves,stop_after='channel')
                self.queue.put(('stage_preview_live',(token,out,'实时预览：最终处理效果')))
            except Exception as e:
                self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()

    def _tl_curve_points(self):
        ch=self.tl_curve_channel.get()
        return self.curve_snapshot.setdefault(ch,[(0.0,0.0),(1.0,1.0)])

    def _tl_curve_geom(self):
        c=self.tl_curve_canvas; W=max(c.winfo_width(),120); H=max(c.winfo_height(),160); m=18; strip=20
        return W,H,m,max(20,W-2*m),max(20,H-2*m-strip)

    def _tl_curve_to_canvas(self,x,y):
        W,H,m,w,h=self._tl_curve_geom(); return m+x*w,m+(1-y)*h

    def _tl_canvas_to_curve(self,cx,cy):
        W,H,m,w,h=self._tl_curve_geom(); return max(0,min(1,(cx-m)/w)),max(0,min(1,1-(cy-m)/h))

    def _tl_curve_nearest(self,cx,cy,threshold=10):
        best=None; bd=1e9
        for i,(x,y) in enumerate(self._tl_curve_points()):
            px,py=self._tl_curve_to_canvas(x,y); d=((cx-px)**2+(cy-py)**2)**0.5
            if d<bd: best=i; bd=d
        return best if best is not None and bd<=threshold else None

    def _tl_curve_set_numeric(self):
        if self.tl_curve_selected_idx is None:return
        pts=self._tl_curve_points(); i=self.tl_curve_selected_idx
        if not (0<=i<len(pts)):return
        self._tl_curve_sync=True
        try:
            self.tl_curve_input.set(round(pts[i][0]*255,2)); self.tl_curve_output.set(round(pts[i][1]*255,2))
        finally:self._tl_curve_sync=False

    def _invalidate_tl_curve_hist(self):
        self._tl_curve_hist_dirty=True
        self._tl_curve_hist_source=None
        self._tl_curve_hist_cache.clear()
        # Do not force a redraw for every slider tick. The next curve redraw/channel change
        # will lazily rebuild the histogram once from the newest upstream parameters.

    def _timelapse_curve_hist_image(self):
        if self.reference_master is None:return None
        if not self._tl_curve_hist_dirty and self._tl_curve_hist_source is not None:
            return self._tl_curve_hist_source
        base=self.reference_proxy_drag if self.reference_proxy_drag is not None else (self.reference_proxy_fast if self.reference_proxy_fast is not None else self.reference_master)
        scale=self.reference_proxy_drag_scale if self.reference_proxy_drag is not None else (self.reference_proxy_fast_scale if self.reference_proxy_fast is not None else 1.0)
        base_cfg=self._snapshot_cfg()
        current_profile=self._current_profile()
        effective_cfg=self._profile_to_cfg(base_cfg,current_profile) if current_profile is not None else base_cfg
        cfg=scale_timelapse_cfg_for_proxy(effective_cfg,scale)
        # Curves histogram is the signal entering Curves: stretch/basic/background only.
        cfg['curves']=False
        try:self._tl_curve_hist_source=apply_timelapse_pipeline(base,cfg,{},stop_after='background_curves')
        except Exception:self._tl_curve_hist_source=base
        self._tl_curve_hist_cache.clear();self._tl_curve_hist_dirty=False
        return self._tl_curve_hist_source

    def _tl_curve_hist(self,ch):
        cached=self._tl_curve_hist_cache.get(ch)
        if cached is not None:return cached
        try:
            np,*_=_deps();img=self._timelapse_curve_hist_image()
            if img is None:return None
            smp=np.clip(img[::4,::4],0,1)
            if ch=='红色':vals=smp[...,0].ravel()
            elif ch=='绿色':vals=smp[...,1].ravel()
            elif ch=='蓝色':vals=smp[...,2].ravel()
            else:vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
            hist,_=np.histogram(vals,bins=160,range=(0,1));hist=np.log1p(hist.astype(np.float64));hist/=max(hist.max(),1.0)
            self._tl_curve_hist_cache[ch]=hist
            return hist
        except Exception:return None

    def _draw_tl_curve_editor(self):
        if not hasattr(self,'tl_curve_canvas'):return
        c=self.tl_curve_canvas;c.delete('curve_dynamic');W,H,m,w,h=self._tl_curve_geom()
        # Static background/grid/histogram is rebuilt only when missing or histogram becomes dirty.
        if not c.find_withtag('curve_static') or self._tl_curve_hist_dirty:
            c.delete('curve_static')
            c.create_rectangle(m,m,m+w,m+h,outline='#666666',fill='#222222',tags='curve_static')
            for j in range(1,4):
                gx=m+w*j/4;gy=m+h*j/4;c.create_line(gx,m,gx,m+h,fill='#343434',tags='curve_static');c.create_line(m,gy,m+w,gy,fill='#343434',tags='curve_static')
            c.create_line(m,m+h,m+w,m,fill='#555555',dash=(4,3),tags='curve_static')
            hist=self._tl_curve_hist(self.tl_curve_channel.get())
            if hist is not None:
                poly=[m,m+h];ridge=[]
                for j,v in enumerate(hist):
                    x=m+(j/(len(hist)-1))*w;y=m+h-v*h*0.78;poly.extend([x,y]);ridge.extend([x,y])
                poly.extend([m+w,m+h]);c.create_polygon(*poly,fill='#4a4a4a',outline='',tags='curve_static');c.create_line(*ridge,fill='#777777',width=1,tags='curve_static')
            # Recreate dynamic curve after static background so it remains on top.
        pts=self._tl_curve_points();lut=build_curve_lut(pts,256);line=[]
        for j,v in enumerate(lut):
            x,y=self._tl_curve_to_canvas(j/255,float(v));line.extend([x,y])
        c.create_line(*line,fill='#58a6ff',width=2,smooth=True,tags='curve_dynamic')
        axis_y=m+h+12
        if len(pts)>=2:
            bx,_=self._tl_curve_to_canvas(pts[0][0],pts[0][1]);wx,_=self._tl_curve_to_canvas(pts[-1][0],pts[-1][1])
            c.create_polygon(bx-6,axis_y+6,bx+6,axis_y+6,bx,axis_y-4,fill='#111111',outline='#999999',tags='curve_dynamic')
            c.create_polygon(wx-6,axis_y+6,wx+6,axis_y+6,wx,axis_y-4,fill='#eeeeee',outline='#999999',tags='curve_dynamic')
        for i,(x,y) in enumerate(pts):
            cx,cy=self._tl_curve_to_canvas(x,y);r=6 if i==self.tl_curve_selected_idx else 4;fill='#fff' if i==self.tl_curve_selected_idx else '#b9d6ff';c.create_oval(cx-r,cy-r,cx+r,cy+r,fill=fill,outline='#1f6feb',tags='curve_dynamic')
        try:c.tag_raise('curve_dynamic')
        except Exception:pass

    def _tl_curve_channel_changed(self):
        self.tl_curve_selected_idx=None
        try:self.tl_curve_canvas.delete('curve_static')
        except Exception:pass
        self._draw_tl_curve_editor()

    def _tl_curve_click(self,event):
        pts=self._tl_curve_points(); W,H,m,w,h=self._tl_curve_geom(); axis_y=m+h+12
        if len(pts)>=2:
            bx,_=self._tl_curve_to_canvas(pts[0][0],pts[0][1]); wx,_=self._tl_curve_to_canvas(pts[-1][0],pts[-1][1])
            if abs(event.y-axis_y)<=12 and abs(event.x-bx)<=12:self.tl_curve_axis_drag='black';self.tl_curve_selected_idx=0;self._tl_curve_set_numeric();return
            if abs(event.y-axis_y)<=12 and abs(event.x-wx)<=12:self.tl_curve_axis_drag='white';self.tl_curve_selected_idx=len(pts)-1;self._tl_curve_set_numeric();return
        self.tl_curve_axis_drag=None
        if event.y>m+h:return
        idx=self._tl_curve_nearest(event.x,event.y)
        if idx is None:
            x,y=self._tl_canvas_to_curve(event.x,event.y);pts.append((x,y));pts.sort(key=lambda p:p[0]);idx=min(range(len(pts)),key=lambda i:abs(pts[i][0]-x)+abs(pts[i][1]-y));
            if not self.p_curves.get():self.p_curves.set(True)
        self.tl_curve_selected_idx=idx;self._tl_curve_set_numeric();self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(dragging=True)

    def _tl_curve_drag(self,event):
        if self.tl_curve_selected_idx is None:return
        pts=self._tl_curve_points();i=self.tl_curve_selected_idx;x,y=self._tl_canvas_to_curve(event.x,event.y)
        if self.tl_curve_axis_drag=='black':x=max(0,min(pts[1][0]-0.002,x));pts[0]=(x,pts[0][1]);i=0
        elif self.tl_curve_axis_drag=='white':x=max(pts[-2][0]+0.002,min(1,x));pts[-1]=(x,pts[-1][1]);i=len(pts)-1
        else:
            if i==0:x=max(0,min(pts[1][0]-0.002,x))
            elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
            else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
            pts[i]=(x,y)
        self.tl_curve_selected_idx=i
        if not self.p_curves.get():self.p_curves.set(True)
        self._tl_curve_set_numeric();self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(dragging=True)

    def _tl_curve_release(self,event):
        self.tl_curve_axis_drag=None;self._schedule_live_preview(force=True)

    def _tl_curve_right_click(self,event):
        idx=self._tl_curve_nearest(event.x,event.y);pts=self._tl_curve_points()
        if idx is None or idx in (0,len(pts)-1):return
        pts.pop(idx);self.tl_curve_selected_idx=None;self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(force=True)

    def _tl_curve_numeric_changed(self):
        if self._tl_curve_sync or self.tl_curve_selected_idx is None:return
        pts=self._tl_curve_points();i=self.tl_curve_selected_idx
        try:x=max(0,min(1,float(self.tl_curve_input.get())/255));y=max(0,min(1,float(self.tl_curve_output.get())/255))
        except Exception:return
        if i==0:x=max(0,min(pts[1][0]-0.002,x))
        elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
        else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
        pts[i]=(x,y)
        if not self.p_curves.get():self.p_curves.set(True)
        self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview()

    def _reset_tl_curve_current(self):
        self.curve_snapshot[self.tl_curve_channel.get()]=[(0.0,0.0),(1.0,1.0)];self.tl_curve_selected_idx=None;self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(force=True)

    def _reset_tl_curves(self):
        self.curve_snapshot={k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']};self.tl_curve_selected_idx=None;self._draw_tl_curve_editor();self._mark_pipeline_dirty();self._schedule_live_preview(force=True)

    def _mark_pipeline_dirty(self):
        if getattr(self,'pipeline_locked',False):
            self.pipeline_locked=False
            self.lock_status.set('参数已改变，请重新锁定')
            try:self.start_btn.configure(state='disabled')
            except Exception:pass

    def lock_pipeline(self):
        if self.reference_master is None:
            messagebox.showwarning(APP_NAME,'请先生成参考堆栈并检查处理效果。',parent=self); return
        self.pipeline_locked=True
        self.lock_status.set('已锁定 · 批量帧使用同一参数')
        self.start_btn.configure(state='normal')
        self.status.set('处理方案已锁定，可以开始批量生成')

    def generate_reference(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME,'当前正在批量生成，请先等待或取消。',parent=self); return
        if not _ewb_require_analysis(self):return
        groups=self._groups()
        if not groups:return
        i=max(1,min(len(groups),int(self.preview_index.get())))-1
        method='maximum' if self.stack_method.get().startswith('最大值') else 'mean'
        self.status.set(f'正在生成参考堆栈 {i+1}/{len(groups)}…'); self.preview_title.set('正在生成参考堆栈…')
        self.reference_master=None; self.pipeline_locked=False; self.start_btn.configure(state='disabled'); self.lock_status.set('处理方案尚未锁定')
        def work():
            try:
                ref=self._ref_lum(); master=self._stack_group(groups[i],method,ref); self.queue.put(('reference',(master,i,groups[i])))
            except Exception as e:self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()

    def preview_stage(self,stage):
        if self.reference_master is None:
            messagebox.showwarning(APP_NAME,'请先在第 1 步生成参考堆栈。',parent=self); return
        base=self.reference_proxy_hq if self.reference_proxy_hq is not None else self.reference_master
        scale=self.reference_proxy_hq_scale if self.reference_proxy_hq is not None else 1.0
        base_cfg=self._snapshot_cfg()
        current_profile=self._current_profile()
        effective_cfg=self._profile_to_cfg(base_cfg,current_profile) if current_profile is not None else base_cfg
        cfg=scale_timelapse_cfg_for_proxy(effective_cfg,scale); curves=copy.deepcopy(self.curve_snapshot)
        names={'stretch':'拉伸后','basic':'拉伸 + 调色后','background_curves':'Background + Curves 后','usm':'USM 后','highpass':'High Pass 后','emboss':'浮雕后','channel':'最终处理效果'}
        self.status.set('正在计算参考图预览：'+names.get(stage,stage)+'…')
        def work():
            try:
                out=apply_timelapse_pipeline(base,cfg,curves,stop_after=stage); self.queue.put(('stage_preview',(out,names.get(stage,stage))))
            except Exception as e:self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()

    def _choose_output(self):
        p=filedialog.askdirectory(title='选择延时输出目录',parent=self)
        if p:self.output_folder.set(p)

    def _groups(self):
        n=len(self.app.files); step=max(1,int(self.step.get() or 1)); mode=self.mode.get()
        if n<1:return []
        if mode.startswith('累计'):
            ends=list(range(1,n+1,step))
            if ends[-1]!=n:ends.append(n)
            return [list(range(0,e)) for e in ends]
        if mode.startswith('逐帧剔除'):
            if n<2:return []
            return [[j for j in range(n) if j!=i] for i in range(0,n,step)]
        w=max(1,min(n,int(self.window_size.get() or 1)))
        if mode.startswith('中心'):
            # Valid centered windows only; fixed window size avoids edge frames using fewer samples.
            starts=list(range(0,n-w+1,step))
            return [list(range(s,s+w)) for s in starts]
        starts=list(range(0,n-w+1,step))
        return [list(range(s,s+w)) for s in starts]

    def _update_summary(self):
        try:
            groups=self._groups(); count=len(groups); mode=self.mode.get(); method=self.stack_method.get(); n=len(self.app.files); w=max(1,min(n,int(self.window_size.get() or 1))) if n else 0
            if mode.startswith('滑动'):
                desc=f'推荐用于真正的冰晕变化延时。例如 100 张、窗口 15：第1帧堆 1–15，第2帧堆 2–16，第3帧堆 3–17……每次向前移动“步长”张。'
            elif mode.startswith('中心'):
                desc=f'同样使用连续的固定窗口，但把每个堆栈结果理解为“窗口中央时刻”的状态。例如 1–15 代表约第8张附近的天空状态，适合按时间中心解释。'
            elif mode.startswith('累计'):
                desc='用于展示信号逐渐累积/生长：第1帧=第1张；第2帧=1–2；第3帧=1–3……最后一帧=全部照片。它展示“堆栈越多，冰晕如何逐渐显现”，不是普通时间变化。'
            else:
                desc='贡献分析模式：每个输出都使用几乎全部照片，但依次剔除一张。例如第1帧=除第1张外全部；第2帧=除第2张外全部。适合判断单张照片对总结果的影响，不推荐作为普通变化延时。'
            self.mode_description.set(desc)
            txt=f'预计输出 {count} 帧。'
            if groups:
                g=groups[0]; txt+=f' 当前参考首组会使用 {len(g)} 张输入。'
                if len(g)<=18: txt+=f' 范围示例：{g[0]+1}–{g[-1]+1}。'
            if method.startswith('最大值') and (mode.startswith('滑动') or mode.startswith('中心') or mode.startswith('逐帧剔除')):
                txt+=' Maximum 在此模式需要更多重算，通常慢于 Mean。'
            self.summary.set(txt); self.preview_spin.configure(to=max(1,count)); self.preview_index.set(min(max(1,self.preview_index.get()),max(1,count)))
            # Window/mode changes invalidate the old reference stack.
            if self.reference_master is not None:
                self.reference_master=None; self.pipeline_locked=False; self.lock_status.set('时间窗口已改变，请重新生成参考堆栈'); self.start_btn.configure(state='disabled'); self.preview_title.set('参考堆栈已失效')
        except Exception:
            self.summary.set('请检查窗口大小和步长。')

    def _snapshot_cfg(self):
        return dict(stretch=self.p_stretch.get(),stretch_strength=self.p_stretch_strength.get(),stretch_black=self.p_stretch_black.get(),
                    basic=self.p_basic.get(),exposure=self.p_exposure.get(),contrast=self.p_contrast.get(),highlights=self.p_highlights.get(),shadows=self.p_shadows.get(),whites=self.p_whites.get(),blacks=self.p_blacks.get(),clarity=self.p_clarity.get(),dehaze=self.p_dehaze.get(),vibrance=self.p_vibrance.get(),saturation=self.p_saturation.get(),
                    background=self.p_bg.get(),bg_radius=self.p_bg_radius.get(),bg_strength=self.p_bg_strength.get(),curves=self.p_curves.get(),
                    usm=self.p_usm.get(),usm_amount=self.p_usm_amount.get(),usm_radius=self.p_usm_radius.get(),usm_threshold=self.p_usm_threshold.get(),usm_passes=max(1,min(10,int(self.p_usm_passes.get() or 1))),
                    highpass=self.p_hp.get(),hp_radius=self.p_hp_radius.get(),hp_amount=self.p_hp_amount.get(),hp_mode=self.p_hp_mode.get(),
                    emboss=self.p_emboss.get(),emboss_angle=self.p_emboss_angle.get(),emboss_height=self.p_emboss_height.get(),emboss_amount=self.p_emboss_amount.get(),emboss_style=self.p_emboss_style.get(),emboss_blend=self.p_emboss_blend.get(),emboss_opacity=self.p_emboss_opacity.get(),
                    channel=self.p_channel.get(),channel_output=self.p_channel_output.get(),channel_mono=self.p_channel_mono.get(),channel_red=self.p_channel_red.get(),channel_green=self.p_channel_green.get(),channel_blue=self.p_channel_blue.get(),channel_constant=self.p_channel_constant.get(),
                    channel_noise=self.p_channel_noise.get(),channel_noise_strength=self.p_channel_noise_strength.get(),channel_noise_radius=self.p_channel_noise_radius.get())

    def _ref_lum(self):
        if not self.normalize.get() or not self.app.files:return None
        img=read_linear_rgb(self.app.files[0]); return robust_luminance(img)

    def _decode(self,idx,ref_lum=None):
        img=read_linear_rgb(self.app.files[idx])
        img=_ewb_apply_to_frame(self,img,idx)
        if ref_lum is not None:
            lum=robust_luminance(img)
            if lum>1e-8: img=img*(ref_lum/lum)
        return img

    def _stack_group(self,indices,method,ref_lum=None):
        np,*_= _deps(); master=None
        for k,idx in enumerate(indices,1):
            if self.cancel_event.is_set(): raise InterruptedError('cancelled')
            img=self._decode(idx,ref_lum).astype(np.float32,copy=False)
            if master is None: master=img.copy()
            elif method=='maximum': np.maximum(master,img,out=master)
            else: master += (img-master)/float(k)
        return master

    def preview_selected(self):
        self.generate_reference()

    def _preview_current_scale(self):
        img=getattr(self,'last_preview_image',None)
        if img is None:return max(0.01,float(getattr(self,'preview_zoom',1.0)))
        h,w=img.shape[:2]; c=self.preview_canvas; W=max(c.winfo_width(),1); H=max(c.winfo_height(),1)
        fit=min(W/max(w,1),H/max(h,1))
        return fit if getattr(self,'preview_fit_mode',True) else max(0.01,float(getattr(self,'preview_zoom',1.0)))

    def _preview_update_zoom_text(self,scale=None):
        if not hasattr(self,'preview_zoom_text'):return
        if getattr(self,'preview_fit_mode',True):
            self.preview_zoom_text.set('Fit')
        else:
            sc=self._preview_current_scale() if scale is None else float(scale)
            self.preview_zoom_text.set(f'{sc*100:.0f}%')

    def _preview_wheel(self,e):
        try:
            direction=1 if getattr(e,'delta',0)>0 else -1
            self._preview_zoom_step(direction,getattr(e,'x',None),getattr(e,'y',None))
        except Exception:pass
        return 'break'

    def _preview_wheel_linux(self,e,direction):
        self._preview_zoom_step(direction,getattr(e,'x',None),getattr(e,'y',None));return 'break'

    def _preview_set_zoom(self,scale):
        old=self._preview_current_scale();new=max(0.05,min(20.0,float(scale)))
        self._preview_adjust_pan_for_zoom(old,new,None,None);self.preview_zoom=new;self.preview_fit_mode=False
        self._preview_update_zoom_text(new);self._preview_redraw();self.preview_canvas.focus_set();return 'break'

    def _preview_zoom_step(self,direction,x=None,y=None):
        old=self._preview_current_scale();factor=1.12 if direction>0 else 1/1.12;new=max(0.05,min(20.0,old*factor))
        if abs(new-old)<1e-9:return
        self._preview_adjust_pan_for_zoom(old,new,x,y);self.preview_zoom=new;self.preview_fit_mode=False;self._preview_update_zoom_text(new);self._preview_redraw()
        try:self.status.set(f'预览缩放：{new*100:.0f}% · Z 回到 Fit')
        except Exception:pass

    def _preview_adjust_pan_for_zoom(self,old_scale,new_scale,x=None,y=None):
        try:
            c=self.preview_canvas;cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2]
            mx=cw/2 if x is None else float(x);my=ch/2 if y is None else float(y);rx=mx-(cw/2+px);ry=my-(ch/2+py);ratio=new_scale/max(old_scale,1e-9)
            self.preview_pan=[mx-cw/2-rx*ratio,my-ch/2-ry*ratio]
        except Exception:self.preview_pan=[0.0,0.0]

    def _preview_pan_start(self,e):
        self.preview_canvas.focus_set()
        if getattr(self,'preview_fit_mode',True):self.preview_pan_anchor=None;return 'break'
        self.preview_pan_anchor=(float(e.x),float(e.y),float(self.preview_pan[0]),float(self.preview_pan[1]));return 'break'
    def _preview_pan_drag(self,e):
        if not self.preview_pan_anchor:return 'break'
        x0,y0,px0,py0=self.preview_pan_anchor
        self.preview_pan=[px0+float(e.x)-x0,py0+float(e.y)-y0]
        self._preview_move_canvas_image_fast()
        return 'break'

    def _preview_move_canvas_image_fast(self):
        """Pan fast path: move the existing Tk canvas image only.

        No PIL resize, NumPy conversion, node processing or PhotoImage rebuild is
        performed while the mouse is moving. This makes panning independent of
        source image resolution and keeps preview/output fidelity untouched.
        """
        try:
            c=self.preview_canvas; item=getattr(self,'preview_image_item',None)
            if not item:return
            W=max(c.winfo_width(),1);H=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2]
            cx=W/2+px;cy=H/2+py;c.coords(item,int(cx),int(cy))
            rect=getattr(self,'preview_display_rect',None)
            if rect:
                _,_,nw,nh=rect;self.preview_display_rect=(int(cx-nw/2),int(cy-nh/2),nw,nh)
        except Exception:pass
    def _preview_pan_end(self,e):
        self.preview_pan_anchor=None;return 'break'

    def _preview_fit(self):
        self.preview_fit_mode=True;self.preview_pan=[0.0,0.0];self._preview_update_zoom_text();self._preview_redraw();self.preview_canvas.focus_set()
        try:self.status.set('预览已回到 Fit')
        except Exception:pass
        return 'break'

    def _preview_redraw(self):
        img=getattr(self,'last_preview_image',None)
        if img is not None:self._show_preview(img)

    def _show_preview(self,img):
        try:
            np,_,Image,ImageTk,*_=_deps();c=self.preview_canvas;W=max(c.winfo_width(),200);H=max(c.winfo_height(),200);h,w=img.shape[:2];fit=min(W/max(w,1),H/max(h,1));sc=fit if getattr(self,'preview_fit_mode',True) else max(0.05,float(getattr(self,'preview_zoom',1.0)));nw=max(1,int(w*sc));nh=max(1,int(h*sc))
            src_key=(id(img),h,w)
            if getattr(self,'_preview_pil_source_key',None)!=src_key:
                self._preview_pil_source=Image.fromarray(np.round(np.clip(img,0,1)*255).astype(np.uint8),'RGB');self._preview_pil_source_key=src_key
            src=self._preview_pil_source;pil=src if (nw,nh)==(w,h) else src.resize((nw,nh),Image.Resampling.LANCZOS)
            self.preview_photo=ImageTk.PhotoImage(pil);c.delete('all');px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];cx=W/2+px;cy=H/2+py;self.preview_image_item=c.create_image(int(cx),int(cy),image=self.preview_photo,anchor='center',tags=('preview_image',));self.last_preview_image=img;self.preview_display_rect=(int(cx-nw/2),int(cy-nh/2),nw,nh);self._preview_update_zoom_text(sc);c.create_text(10,10,anchor='nw',fill='#e0e0e0',font=_ui_font(9),text=('Fit' if getattr(self,'preview_fit_mode',True) else f'{sc*100:.0f}%')+' · 滚轮缩放 · 拖拽平移 · Z Fit',tags=('preview_overlay',))
        except Exception as e:self.status.set('预览显示失败：'+str(e))

    def _iter_masters(self,groups,method,ref_lum):
        # v0.9.4.18a: traditional and node timelapse now share one optimized
        # stack engine, preventing future performance/behavior drift.
        yield from _iter_optimized_timelapse_masters(self,groups,method,ref_lum)

    def start_batch(self):
        if self.worker and self.worker.is_alive():return
        if not _ewb_require_analysis(self):return
        if self.reference_master is None:
            messagebox.showwarning(APP_NAME,'请先完成第 1 步：生成参考堆栈。',parent=self); return
        if not self.pipeline_locked:
            messagebox.showwarning(APP_NAME,'请先在参考图上确认处理效果，然后点击“锁定当前处理方案”。',parent=self); return
        groups=self._groups()
        if not groups:messagebox.showwarning(APP_NAME,'当前设置无法产生输出帧。',parent=self);return
        base=Path(self.output_folder.get()).expanduser()
        try:base.mkdir(parents=True,exist_ok=True)
        except Exception as e:messagebox.showerror(APP_NAME,'无法创建输出目录：\n'+str(e),parent=self);return
        self.cancel_event.clear(); self._last_performance_snapshot=None; self.performance_monitor_text.set('Performance：准备启动…'); self.stability_text.set('Stability：Starting'); self.start_btn.configure(state='disabled'); self.cancel_btn.configure(state='normal'); self.progress.set(0); self.processing_progress.set(0); self.writing_progress.set(0); self.output_pipeline_text.set('写入：准备启动…'); self.status.set('准备批量生成…')
        cfg=self._snapshot_cfg(); curves=copy.deepcopy(self.curve_snapshot); method='maximum' if self.stack_method.get().startswith('最大值') else 'mean'
        profiles=self._iter_enabled_export_profiles(cfg)
        if not profiles:
            self.start_btn.configure(state='normal'); self.cancel_btn.configure(state='disabled'); messagebox.showwarning(APP_NAME,'没有有效输出组。请至少启用一个输出组并选择序列或视频。',parent=self); return
        self._active_memory_policy=_timelapse_memory_policy_snapshot(self)
        settings=dict(groups=groups,cfg=cfg,curves=curves,method=method,profiles=profiles,save_seq=self.save_sequence.get(),seqfmt=self.sequence_format.get(),video=self.video_format.get(),fps=max(0.1,float(self.fps.get())),res=self.resolution.get(),cw=max(2,int(self.custom_w.get())),ch=max(2,int(self.custom_h.get())),fit=self.fit_mode.get(),base=base,save_performance_report=bool(self.performance_save_report.get()),exposure_wb_smoothing=_ewb_config_snapshot(self))
        self.worker=threading.Thread(target=self._batch_worker,args=(settings,),daemon=True); self.worker.start()

    def cancel(self):
        self.cancel_event.set(); self.status.set('正在取消…'); self.cancel_btn.configure(state='disabled')

    def _batch_worker(self,s):
        run_dir=None;outpipe=None
        try:
            stamp=time.strftime('%Y%m%d_%H%M%S'); run_dir=s['base']/f'IceHaloStack_Timelapse_{stamp}'; run_dir.mkdir(parents=True,exist_ok=True)
            ref=self._ref_lum(); total=len(s['groups'])
            ext_map={'PNG 8-bit':'.png','JPEG':'.jpg','TIFF 16-bit':'.tif','TIFF 32-bit Float':'.tif'}; seq_ext=ext_map[s['seqfmt']]
            profile_dirs=[]
            for prof in s['profiles']:
                folder_name=self._format_output_name(prof, method=s['method'], mode='timelapse')
                pdir=run_dir/folder_name;pdir.mkdir(parents=True,exist_ok=True);seq_dir=pdir/'sequence'
                if prof['save_sequence'] or prof['save_video']:seq_dir.mkdir(exist_ok=True)
                recipe=[f"名称: {prof['name']}",f"命名模板: {prof['name_template']}",f"保存序列: {prof['save_sequence']}",f"保存视频: {prof['save_video']}",f"视频格式: {prof['video_format']}",f"缩放百分比: {prof['scale_percent']}",f"只保存视频时自动删除 sequence: {prof.get('delete_sequence_after_video_only', True)}",'Async Output: ON (RAM-aware bounded queue)','Disk Cache: OFF']
                ewb=s.get('exposure_wb_smoothing',{});recipe.append('曝光/白平衡平滑: '+('ON' if (ewb.get('exposure_enabled') or ewb.get('wb_enabled')) else 'OFF'));recipe.append('曝光/白平衡平滑设置: '+json.dumps(ewb,ensure_ascii=False))
                mods=[]
                for key,label in [('stretch','拉伸'),('basic','调色'),('usm','USM / 锐化'),('background','Background / 背景'),('curves','Curves / 曲线（BGR）'),('highpass','High Pass / 高反差保留'),('emboss','Emboss / 浮雕'),('channel','Channel Mixer / 通道混合器（BR）')]:
                    if prof['cfg'].get(key):mods.append(label)
                recipe.append('流程: '+(' -> '.join(mods) if mods else '仅保存线性结果'))
                (pdir/'recipe.txt').write_text('\n'.join(recipe),encoding='utf-8')
                profile_dirs.append({'prof':prof,'root':pdir,'seq':seq_dir,'video_path':None,'folder_name':folder_name})
            total_work=max(1,total*max(1,len(profile_dirs)));done_work=0;proc_start=time.monotonic()
            pol=getattr(self,'_active_memory_policy',{}) or {};engine=_timelapse_stack_engine_name(self,s['method'])
            perf=PerformanceMonitor(self,engine,pol,'Traditional Timelapse',s.get('save_performance_report',False))
            outpipe=AsyncOutputPipeline(self,pol,self.queue,'tl_output',total_work)
            self.queue.put(('tl_status',f'堆栈引擎：{engine} · 曝光/WB平滑 {"ON" if _ewb_enabled(self) else "OFF"} · Async Output ON · Queue {outpipe.capacity} · RAM Budget {_fmt_bytes(pol.get("limit_bytes",0))} · Disk Cache OFF'))
            for i,master in enumerate(perf.wrap_masters(self._iter_masters(s['groups'],s['method'],ref)),1):
                if self.cancel_event.is_set():raise InterruptedError('cancelled')
                for bundle in profile_dirs:
                    if self.cancel_event.is_set():raise InterruptedError('cancelled')
                    prof=bundle['prof'];self.queue.put(('tl_status',f"处理输出帧 {i}/{total} · 输出组 {prof['index']} {prof['name']}…"))
                    perf.touch('node_pipeline');tn=time.monotonic();out=apply_timelapse_pipeline(master,prof['cfg'],s['curves']);perf.add_stage('node_processing',time.monotonic()-tn);perf.inc('processed_tasks',1)
                    tp=time.monotonic()
                    if prof['save_sequence']:
                        scaled=resize_float_percent_array(out,prof['scale_percent']);perf.add_stage('output_prepare',time.monotonic()-tp)
                        outpipe.submit_array(bundle['seq']/f'frame_{i:06d}{seq_ext}',scaled,s['seqfmt'],'Balanced')
                    elif prof['save_video']:
                        pil=prepare_video_frame(out,s['res'],s['cw'],s['ch'],s['fit']);pil=resize_pil_percent(pil,prof['scale_percent']);perf.add_stage('output_prepare',time.monotonic()-tp)
                        outpipe.submit_pil_png(bundle['seq']/f'frame_{i:06d}.png',pil,compress_level=3)
                    done_work+=1;elapsed=max(1e-6,time.monotonic()-proc_start);fps=done_work/elapsed;remain=max(0,total_work-done_work);eta=(remain/fps if fps>1e-9 else None)
                    self.queue.put(('tl_processing',{'done':done_work,'total':total_work,'fps':fps,'eta':eta}))
            self.queue.put(('tl_status','处理完成，等待 Async Output Queue 写入剩余最终帧…'))
            outpipe.finish();outpipe=None
            self.queue.put(('tl_processing',{'done':total_work,'total':total_work,'fps':total_work/max(1e-6,time.monotonic()-proc_start),'eta':0.0}))
            video_paths=[];ff=None;vidflows=[b for b in profile_dirs if b['prof']['save_video']]
            for vidx,bundle in enumerate(vidflows,1):
                prof=bundle['prof']
                if self.cancel_event.is_set():raise InterruptedError('cancelled')
                if ff is None:
                    ff=get_ffmpeg_executable()
                    if not ff:raise RuntimeError('未找到 FFmpeg。请重新运行启动脚本安装 imageio-ffmpeg，或把 ffmpeg.exe 放在程序目录/系统 PATH。图像序列若已启用仍已保存。')
                self.queue.put(('tl_status',f"正在编码视频 {vidx}/{len(vidflows)} · {prof['name']}…"));fps=str(s['fps']);base_name=self._format_output_name(prof,method=s['method'],mode='timelapse');fmt=prof['video_format'];src_ext=seq_ext if prof['save_sequence'] else '.png';pattern=str(bundle['seq']/f'frame_%06d{src_ext}')
                if fmt=='MP4 H.264':video_path=bundle['root']/f'{base_name}.mp4';cmd=[ff,'-y','-framerate',fps,'-i',pattern]+_ffmpeg_even_pad_args()+['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',str(video_path)]
                elif fmt=='MOV H.264':video_path=bundle['root']/f'{base_name}.mov';cmd=[ff,'-y','-framerate',fps,'-i',pattern]+_ffmpeg_even_pad_args()+['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',str(video_path)]
                elif fmt=='MOV ProRes':video_path=bundle['root']/f'{base_name}_ProRes.mov';cmd=[ff,'-y','-framerate',fps,'-i',pattern]+_ffmpeg_even_pad_args()+['-c:v','prores_ks','-profile:v','3','-pix_fmt','yuv422p10le',str(video_path)]
                elif fmt=='GIF':
                    video_path=bundle['root']/f'{base_name}.gif';palette=bundle['seq']/'palette.png';cmd1=[ff,'-y','-framerate',fps,'-i',pattern,'-vf','palettegen=stats_mode=diff',str(palette)];perf.touch('ffmpeg');tf=time.monotonic();p1=subprocess.run(cmd1,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));perf.add_stage('ffmpeg',time.monotonic()-tf)
                    if p1.returncode!=0:raise RuntimeError('GIF palette 生成失败：\n'+(p1.stderr or '')[-2000:])
                    cmd=[ff,'-y','-framerate',fps,'-i',pattern,'-i',str(palette),'-lavfi','paletteuse=dither=sierra2_4a',str(video_path)]
                else:continue
                perf.touch('ffmpeg');tf=time.monotonic();p=subprocess.run(cmd,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));perf.add_stage('ffmpeg',time.monotonic()-tf)
                if p.returncode!=0:raise RuntimeError('FFmpeg 编码失败：\n'+(p.stderr or '')[-3000:]+'\n\nsequence 文件夹已保留，可使用 repair_failed_video_export.bat 直接重新编码，无需重新堆栈。')
                bundle['video_path']=video_path;video_paths.append(str(video_path))
                if (not prof['save_sequence']) and bool(prof.get('delete_sequence_after_video_only',True)):shutil.rmtree(bundle['seq'],ignore_errors=True)
                self.queue.put(('tl_progress',85.0+(vidx/max(1,len(vidflows)))*15.0))
            perf.finalize('Completed',run_dir,extra={'output_groups':len(profile_dirs),'frames_per_group':total})
            self.queue.put(('tl_done_multi',(str(run_dir),video_paths,total,[b['folder_name'] for b in profile_dirs])))
        except InterruptedError:
            if outpipe is not None:
                try:outpipe.cancel()
                except Exception:pass
            try:
                perf.finalize('Cancelled',run_dir) if 'perf' in locals() else setattr(self,'_active_memory_policy',None)
            except Exception:pass
            self.queue.put(('tl_cancelled',str(run_dir) if run_dir else ''))
        except Exception as e:
            if outpipe is not None:
                try:outpipe.cancel()
                except Exception:pass
            try:
                perf.finalize('Failed',run_dir,error=str(e)) if 'perf' in locals() else setattr(self,'_active_memory_policy',None)
            except Exception:pass
            self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=4)))

    def _poll(self):
        try:
            while True:
                kind,val=self.queue.get_nowait()
                if kind=='reference':
                    master,idx,group=val; self.reference_master=master; self.reference_index=idx; self.reference_group=list(group)
                    try:
                        strength,black=estimate_asinh_params(master); self.p_stretch_strength.set(round(float(strength),4)); self.p_stretch_black.set(round(float(black),6))
                    except Exception:pass
                    # Linear masters are too dark for a useful visual check; Auto Stretch here is display-only.
                    try:
                        disp=apply_asinh_stretch(master,self.p_stretch_strength.get(),self.p_stretch_black.get())
                    except Exception:disp=master
                    self.reference_proxy_drag,self.reference_proxy_drag_scale=make_float_preview_proxy(master,640)
                    self.reference_proxy_fast,self.reference_proxy_fast_scale=make_float_preview_proxy(master,1000)
                    self.reference_proxy_hq,self.reference_proxy_hq_scale=make_float_preview_proxy(master,1800)
                    self._invalidate_tl_curve_hist()
                    self._show_preview(disp); self.preview_title.set(f'参考堆栈 #{idx+1} · 输入 {group[0]+1}–{group[-1]+1} · Auto Stretch 仅用于显示')
                    self.status.set('参考堆栈完成。现在在第 2 步逐段调参数并预览。'); self.pipeline_locked=False; self.lock_status.set('处理方案尚未锁定'); self.start_btn.configure(state='disabled')
                    self._draw_tl_curve_editor(); self._schedule_live_preview(force=True)
                elif kind=='stage_preview':
                    img,name=val; self._show_preview(img); self.preview_title.set(name); self.status.set('参考图预览完成：'+name)
                elif kind=='stage_preview_live':
                    token,img,name=val
                    self._live_preview_running=False
                    if token == self._live_preview_token:
                        self._show_preview(img); self.preview_title.set(name); self.status.set('实时预览已更新')
                    if self._live_preview_pending:
                        self._live_preview_pending=False
                        self._schedule_live_preview(force=True)
                elif kind=='preview':self._show_preview(val); self.status.set('预览完成')
                elif kind=='tl_status':self.status.set(val)
                elif kind=='tl_processing':
                    d=val;tot=max(1,int(d.get('total',1)));done=int(d.get('done',0));self.processing_progress.set(min(100.0,done/tot*100.0));eta=d.get('eta');etxt=_format_seconds_short(eta) if eta is not None else '—';self.output_pipeline_text.set(f'Processing：{done}/{tot} · {float(d.get("fps",0.0)):.2f} fps · ETA {etxt}')
                elif kind=='tl_output':
                    d=val;tot=max(1,int(d.get('total',1)));done=int(d.get('completed',0));self.writing_progress.set(min(100.0,done/tot*100.0));self.progress.set(min(85.0,done/tot*85.0));eta=d.get('eta');etxt=_format_seconds_short(eta) if eta is not None else '—';wf=float(d.get('recent_writer_fps') or d.get('writer_fps') or 0.0);state='等待处理' if d.get('writer_idle') else f'Writer {wf:.2f} fps';self.output_pipeline_text.set(f'写入：{done}/{tot} · 队列 {d.get("queued",0)}/{d.get("capacity",0)} · {state} · 总 ETA {etxt}')
                elif kind=='tl_progress':self.progress.set(val)
                elif kind=='tl_done':
                    run,video,count=val; self.start_btn.configure(state='normal'); self.cancel_btn.configure(state='disabled'); self.progress.set(100); self.processing_progress.set(100); self.writing_progress.set(100); self.output_pipeline_text.set('写入：完成'); self.status.set(f'完成 · {count} 帧 · {run}')
                    msg=f'堆栈延时生成完成。\n\n输出帧：{count}\n目录：\n{run}'
                    if video:msg+=f'\n\n视频：\n{video}'
                    messagebox.showinfo(APP_NAME,msg,parent=self)
                elif kind=='tl_done_multi':
                    run,videos,count,names=val;self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.progress.set(100);self.processing_progress.set(100);self.writing_progress.set(100);self.output_pipeline_text.set('写入：完成');self.status.set(f'完成 · {len(names)} 个输出组 × {count} 帧 · {run}')
                    msg=f'堆栈延时生成完成。\n\n输出组：{len(names)}\n每组帧数：{count}\n目录：\n{run}'
                    if videos:msg+='\n\n视频：\n'+'\n'.join(videos)
                    messagebox.showinfo(APP_NAME,msg,parent=self)
                elif kind=='tl_cancelled':
                    self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.status.set('已取消');self.output_pipeline_text.set('写入：已取消')
                    messagebox.showinfo(APP_NAME,'批量生成已取消。\n已完成的最终文件不会删除；未写入的队列帧已释放。',parent=self)
                elif kind=='error':
                    self._live_preview_running=False;self._live_preview_pending=False;self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.status.set('处理失败');self.output_pipeline_text.set('写入：失败/已停止');messagebox.showerror(APP_NAME,val,parent=self)
        except Empty:pass
        if self.winfo_exists():self.after(80,self._poll)



class LocalNodeEditorHistory:
    """Local undo/redo history for one open node parameter dialog.

    Changes remain temporary until the parent node dialog is Applied. Fast
    slider motion is coalesced into a single undo step when possible.
    """
    def __init__(self, owner, window, flow, label='节点参数'):
        self.owner=owner; self.window=window; self.flow=flow; self.label=label
        self.undo=[]; self.redo=[]; self.limit=80
        self.last_state=copy.deepcopy(flow)
        self.last_change_time=0.0; self.burst_open=False; self.suspend=False
        self.poll_ms=70; self.coalesce_seconds=0.45
        for seq in ('<Control-z>','<Control-Z>'):
            window.bind(seq,self._undo_key,add='+')
        for seq in ('<Control-Shift-z>','<Control-Shift-Z>'):
            window.bind(seq,self._redo_key,add='+')
        self._poll_id=window.after(self.poll_ms,self._poll)

    def _equal(self,a,b):
        try:return a==b
        except Exception:return False

    def _push_undo(self,state):
        self.undo.append(copy.deepcopy(state))
        if len(self.undo)>self.limit:self.undo=self.undo[-self.limit:]

    def _push_redo(self,state):
        self.redo.append(copy.deepcopy(state))
        if len(self.redo)>self.limit:self.redo=self.redo[-self.limit:]

    def _capture_now(self):
        if self.suspend:return
        now=time.monotonic(); current=copy.deepcopy(self.flow)
        if not self._equal(current,self.last_state):
            # One continuous slider drag should normally be one undo step.
            if (not self.burst_open) or (now-self.last_change_time>self.coalesce_seconds):
                self._push_undo(self.last_state); self.redo.clear(); self.burst_open=True
            self.last_state=current; self.last_change_time=now
        elif self.burst_open and now-self.last_change_time>self.coalesce_seconds:
            self.burst_open=False

    def _poll(self):
        try:
            if not self.window.winfo_exists():return
            self._capture_now()
            self._poll_id=self.window.after(self.poll_ms,self._poll)
        except Exception:
            pass

    def _restore(self,state):
        self.suspend=True
        try:
            self.flow.clear(); self.flow.update(copy.deepcopy(state)); self.owner._normalize_flow(self.flow)
            self.last_state=copy.deepcopy(self.flow); self.burst_open=False; self.last_change_time=time.monotonic()
            self.owner._refresh_flow_list(); self.owner._draw_graph(); self.owner._schedule_preview(force=True)
        finally:self.suspend=False

    def undo_action(self):
        self._capture_now()
        if not self.undo:
            try:self.owner.status.set(f'{self.label}：没有可撤回的局部操作')
            except Exception:pass
            return
        current=copy.deepcopy(self.flow); state=self.undo.pop(); self._push_redo(current); self._restore(state)
        try:self.owner.status.set(f'{self.label}：已局部撤回 · Ctrl+Shift+Z 可重做')
        except Exception:pass

    def redo_action(self):
        self._capture_now()
        if not self.redo:
            try:self.owner.status.set(f'{self.label}：没有可重做的局部操作')
            except Exception:pass
            return
        current=copy.deepcopy(self.flow); state=self.redo.pop(); self._push_undo(current); self._restore(state)
        try:self.owner.status.set(f'{self.label}：已局部重做')
        except Exception:pass

    def _undo_key(self,event=None):
        self.undo_action(); return 'break'
    def _redo_key(self,event=None):
        self.redo_action(); return 'break'

class FlowCurveDialog(tk.Toplevel):
    def __init__(self, owner, flow):
        super().__init__(owner)
        self.owner=owner; self.flow=flow; self.before=copy.deepcopy(flow); self.history_before=owner._workflow_state(); self.committed=False
        self.title('Curves 节点参数')
        self.geometry('620x650'); self.minsize(460,380)
        self.channel=tk.StringVar(value='RGB')
        self.input_var=tk.DoubleVar(value=0.0); self.output_var=tk.DoubleVar(value=0.0)
        self.selected=None; self.axis_drag=None; self.syncing=False
        self.hist_cache={}
        self._build(); self._draw(); self.local_history=LocalNodeEditorHistory(self.owner,self,self.flow,'Curves / 曲线'); self.protocol('WM_DELETE_WINDOW',self._cancel_close)

    def _apply_close(self):
        self.committed=True; self.owner._draw_graph(); self.owner._schedule_preview(force=True); self.destroy()
    def _cancel_close(self):
        if not self.committed:
            self.flow.clear(); self.flow.update(copy.deepcopy(self.before)); self.owner._normalize_flow(self.flow)
            self.owner._refresh_flow_list(); self.owner._draw_graph(); self.owner._schedule_preview(force=True)
        self.destroy()

    def _points(self):
        curves=self.flow.setdefault('curves',{})
        return curves.setdefault(self.channel.get(),[(0.0,0.0),(1.0,1.0)])

    def _build(self):
        outer=ttk.Frame(self,padding=6); outer.pack(fill='both',expand=True); root,self._scroll_canvas,_scroll_shell=_make_vertical_scroll_area(outer,padding=6)
        top=ttk.Frame(root); top.pack(fill='x')
        self.enabled=tk.BooleanVar(value=bool(self.flow['cfg'].get('curves',False)))
        ttk.Checkbutton(top,text='启用 Curves 节点',variable=self.enabled,command=self._enabled_changed).pack(side='left')
        cb=ttk.Combobox(top,textvariable=self.channel,state='readonly',width=10,values=['RGB','红色','绿色','蓝色','亮度']); cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>',lambda e:self._channel_changed())
        self.canvas=tk.Canvas(root,bg='#202020',height=470,highlightthickness=1,highlightbackground='#555555')
        self.canvas.pack(fill='both',expand=True,pady=(8,6))
        self.canvas.bind('<Button-1>',self._click); self.canvas.bind('<B1-Motion>',self._drag); self.canvas.bind('<ButtonRelease-1>',self._release); self.canvas.bind('<Button-3>',self._right_click); self.canvas.bind('<Configure>',lambda e:self._draw())
        row=ttk.Frame(root); row.pack(fill='x')
        ttk.Label(row,text='输入').pack(side='left'); ie=ttk.Entry(row,textvariable=self.input_var,width=9,justify='right'); ie.pack(side='left',padx=(4,12))
        ttk.Label(row,text='输出').pack(side='left'); oe=ttk.Entry(row,textvariable=self.output_var,width=9,justify='right'); oe.pack(side='left',padx=(4,12))
        ttk.Button(row,text='重置当前通道',command=self._reset_current).pack(side='right')
        ttk.Button(root,text='重置全部曲线',command=self._reset_all).pack(fill='x',pady=(6,0))
        ttk.Label(root,text='点击增加控制点；左右拖动改变 Input，上下拖动改变 Output；右键删除中间控制点。拖动曲线时，主窗口右侧参考帧会同步实时预览。当前窗口支持 Ctrl+Z 局部撤回、Ctrl+Shift+Z 局部重做。',foreground='#666666',wraplength=570).pack(anchor='w',pady=(6,0))
        bar=ttk.Frame(root);bar.pack(fill='x',pady=(10,0))
        ttk.Button(bar,text='取消 / Cancel',command=self._cancel_close).pack(side='right',fill='x',expand=True,padx=(5,0))
        ttk.Button(bar,text='应用 / Apply',style='Primary.TButton',command=self._apply_close).pack(side='right',fill='x',expand=True)
        self.input_var.trace_add('write',lambda *a:self._numeric_changed()); self.output_var.trace_add('write',lambda *a:self._numeric_changed())
        for e in (ie,oe):
            def sel(ev,ent=e): ent.selection_range(0,'end'); ent.icursor('end'); return 'break'
            e.bind('<Control-a>',sel); e.bind('<Control-A>',sel); e.bind('<Double-Button-1>',sel)

    def _enabled_changed(self):
        self.flow['cfg']['curves']=bool(self.enabled.get());
        if self.enabled.get(): self.flow['cfg']['bgr']=True
        self.owner._flow_changed(force=True); self.owner._draw_graph()

    def _geom(self):
        W=max(self.canvas.winfo_width(),200); H=max(self.canvas.winfo_height(),240); m=24; strip=24
        return W,H,m,max(50,W-2*m),max(50,H-2*m-strip)
    def _to_canvas(self,x,y):
        W,H,m,w,h=self._geom(); return m+x*w,m+(1-y)*h
    def _to_curve(self,cx,cy):
        W,H,m,w,h=self._geom(); return max(0,min(1,(cx-m)/w)),max(0,min(1,1-(cy-m)/h))
    def _nearest(self,cx,cy,thr=12):
        best=None;bd=1e9
        for i,(x,y) in enumerate(self._points()):
            px,py=self._to_canvas(x,y);d=((cx-px)**2+(cy-py)**2)**0.5
            if d<bd:best=i;bd=d
        return best if best is not None and bd<=thr else None

    def _hist(self):
        ch=self.channel.get()
        if ch in self.hist_cache:return self.hist_cache[ch]
        img=self.owner._curve_hist_source(self.flow)
        if img is None:return None
        try:
            np,*_=_deps(); smp=np.clip(img[::4,::4],0,1)
            if ch=='红色':vals=smp[...,0].ravel()
            elif ch=='绿色':vals=smp[...,1].ravel()
            elif ch=='蓝色':vals=smp[...,2].ravel()
            else:vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
            hist,_=np.histogram(vals,bins=128,range=(0,1));hist=np.log1p(hist.astype(np.float64));mx=hist.max() or 1;hist/=mx
            self.hist_cache[ch]=hist;return hist
        except Exception:return None

    def _draw(self):
        if not hasattr(self,'canvas'):return
        c=self.canvas;c.delete('all');W,H,m,w,h=self._geom()
        c.create_rectangle(m,m,m+w,m+h,outline='#666',fill='#222')
        for j in range(1,4):
            gx=m+w*j/4;gy=m+h*j/4;c.create_line(gx,m,gx,m+h,fill='#343434');c.create_line(m,gy,m+w,gy,fill='#343434')
        c.create_line(m,m+h,m+w,m,fill='#555',dash=(4,3))
        hist=self._hist()
        if hist is not None:
            poly=[m,m+h];ridge=[]
            for j,v in enumerate(hist):
                x=m+(j/(len(hist)-1))*w;y=m+h-v*h*0.76;poly.extend([x,y]);ridge.extend([x,y])
            poly.extend([m+w,m+h]);c.create_polygon(*poly,fill='#4a4a4a',outline='');c.create_line(*ridge,fill='#777')
        pts=self._points();lut=build_curve_lut(pts,256);line=[]
        for j,v in enumerate(lut):line.extend(self._to_canvas(j/255,float(v)))
        c.create_line(*line,fill='#58a6ff',width=2,smooth=True)
        axis_y=m+h+14
        if len(pts)>=2:
            bx,_=self._to_canvas(pts[0][0],pts[0][1]);wx,_=self._to_canvas(pts[-1][0],pts[-1][1])
            c.create_polygon(bx-6,axis_y+6,bx+6,axis_y+6,bx,axis_y-5,fill='#111',outline='#aaa')
            c.create_polygon(wx-6,axis_y+6,wx+6,axis_y+6,wx,axis_y-5,fill='#eee',outline='#aaa')
        for i,(x,y) in enumerate(pts):
            cx,cy=self._to_canvas(x,y);r=6 if i==self.selected else 4;c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#fff' if i==self.selected else '#b9d6ff',outline='#1f6feb')

    def _set_numeric(self):
        if self.selected is None:return
        pts=self._points()
        if not(0<=self.selected<len(pts)):return
        self.syncing=True
        try:self.input_var.set(round(pts[self.selected][0]*255,2));self.output_var.set(round(pts[self.selected][1]*255,2))
        finally:self.syncing=False
    def _channel_changed(self):self.selected=None;self.axis_drag=None;self._draw()
    def _click(self,e):
        pts=self._points();W,H,m,w,h=self._geom();axis_y=m+h+14
        if len(pts)>=2:
            bx,_=self._to_canvas(pts[0][0],pts[0][1]);wx,_=self._to_canvas(pts[-1][0],pts[-1][1])
            if abs(e.y-axis_y)<=13 and abs(e.x-bx)<=13:self.axis_drag='black';self.selected=0;self._set_numeric();return
            if abs(e.y-axis_y)<=13 and abs(e.x-wx)<=13:self.axis_drag='white';self.selected=len(pts)-1;self._set_numeric();return
        if e.y>m+h:return
        self.axis_drag=None;idx=self._nearest(e.x,e.y)
        if idx is None:
            x,y=self._to_curve(e.x,e.y);pts.append((x,y));pts.sort(key=lambda p:p[0]);idx=min(range(len(pts)),key=lambda i:abs(pts[i][0]-x)+abs(pts[i][1]-y))
        self.selected=idx;self.flow['cfg']['curves']=True;self.flow['cfg']['bgr']=True;self.enabled.set(True);self._set_numeric();self._draw();self.owner._flow_changed(dragging=True);self.owner._draw_graph()
    def _drag(self,e):
        if self.selected is None:return
        pts=self._points();i=self.selected;x,y=self._to_curve(e.x,e.y)
        if self.axis_drag=='black':x=max(0,min(pts[1][0]-0.002,x));pts[0]=(x,pts[0][1]);i=0
        elif self.axis_drag=='white':x=max(pts[-2][0]+0.002,min(1,x));pts[-1]=(x,pts[-1][1]);i=len(pts)-1
        else:
            if i==0:x=max(0,min(pts[1][0]-0.002,x))
            elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
            else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
            pts[i]=(x,y)
        self.selected=i;self.flow['cfg']['curves']=True;self.flow['cfg']['bgr']=True;self._set_numeric();self._draw();self.owner._flow_changed(dragging=True)
    def _release(self,e):self.axis_drag=None;self.owner._flow_changed(force=True)
    def _right_click(self,e):
        idx=self._nearest(e.x,e.y);pts=self._points()
        if idx is None or idx in (0,len(pts)-1):return
        pts.pop(idx);self.selected=None;self._draw();self.owner._flow_changed(force=True)
    def _numeric_changed(self):
        if self.syncing or self.selected is None:return
        pts=self._points();i=self.selected
        try:x=max(0,min(1,float(self.input_var.get())/255));y=max(0,min(1,float(self.output_var.get())/255))
        except Exception:return
        if i==0:x=max(0,min(pts[1][0]-0.002,x))
        elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
        else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
        pts[i]=(x,y);self.flow['cfg']['curves']=True;self.flow['cfg']['bgr']=True;self.enabled.set(True);self._draw();self.owner._flow_changed()
    def _reset_current(self):self.flow['curves'][self.channel.get()]=[(0.0,0.0),(1.0,1.0)];self.selected=None;self._draw();self.owner._flow_changed(force=True)
    def _reset_all(self):
        self.flow['curves']={k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']};self.selected=None;self.hist_cache.clear();self._draw();self.owner._flow_changed(force=True)


class BaseCurveDialog(tk.Toplevel):
    def __init__(self, owner, flow):
        super().__init__(owner)
        self.owner=owner; self.flow=flow; self.before=copy.deepcopy(flow); self.history_before=owner._workflow_state(); self.committed=False
        self.title('Base Curve / 基础调色曲线')
        self.geometry('620x650'); self.minsize(460,380)
        self.channel=tk.StringVar(value='RGB')
        self.input_var=tk.DoubleVar(value=0.0); self.output_var=tk.DoubleVar(value=0.0)
        self.selected=None; self.axis_drag=None; self.syncing=False
        self.hist_cache={}
        self._build(); self._draw(); self.local_history=LocalNodeEditorHistory(self.owner,self,self.flow,'Base Curve / 基础曲线'); self.protocol('WM_DELETE_WINDOW',self._cancel_close)

    def _apply_close(self):
        self.committed=True; self.owner._draw_graph(); self.owner._schedule_preview(force=True); self.destroy()
    def _cancel_close(self):
        if not self.committed:
            self.flow.clear(); self.flow.update(copy.deepcopy(self.before)); self.owner._normalize_flow(self.flow)
            self.owner._refresh_flow_list(); self.owner._draw_graph(); self.owner._schedule_preview(force=True)
        self.destroy()

    def _points(self):
        curves=self.flow.setdefault('base_curves',{})
        return curves.setdefault(self.channel.get(),[(0.0,0.0),(1.0,1.0)])

    def _build(self):
        outer=ttk.Frame(self,padding=6); outer.pack(fill='both',expand=True); root,self._scroll_canvas,_scroll_shell=_make_vertical_scroll_area(outer,padding=6)
        top=ttk.Frame(root); top.pack(fill='x')
        self.enabled=tk.BooleanVar(value=bool(self.flow['cfg'].get('base_curve',False)))
        ttk.Checkbutton(top,text='启用 Base Curve / 基础曲线',variable=self.enabled,command=self._enabled_changed).pack(side='left')
        cb=ttk.Combobox(top,textvariable=self.channel,state='readonly',width=10,values=['RGB','红色','绿色','蓝色','亮度']); cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>',lambda e:self._channel_changed())
        self.canvas=tk.Canvas(root,bg='#202020',height=470,highlightthickness=1,highlightbackground='#555555')
        self.canvas.pack(fill='both',expand=True,pady=(8,6))
        self.canvas.bind('<Button-1>',self._click); self.canvas.bind('<B1-Motion>',self._drag); self.canvas.bind('<ButtonRelease-1>',self._release); self.canvas.bind('<Button-3>',self._right_click); self.canvas.bind('<Configure>',lambda e:self._draw())
        row=ttk.Frame(root); row.pack(fill='x')
        ttk.Label(row,text='输入').pack(side='left'); ie=ttk.Entry(row,textvariable=self.input_var,width=9,justify='right'); ie.pack(side='left',padx=(4,12))
        ttk.Label(row,text='输出').pack(side='left'); oe=ttk.Entry(row,textvariable=self.output_var,width=9,justify='right'); oe.pack(side='left',padx=(4,12))
        ttk.Button(row,text='重置当前通道',command=self._reset_current).pack(side='right')
        ttk.Button(root,text='重置全部曲线',command=self._reset_all).pack(fill='x',pady=(6,0))
        ttk.Label(root,text='点击增加控制点；左右拖动改变 Input，上下拖动改变 Output；右键删除中间控制点。拖动曲线时，主窗口右侧参考帧会同步实时预览。当前窗口支持 Ctrl+Z 局部撤回、Ctrl+Shift+Z 局部重做。',foreground='#666666',wraplength=570).pack(anchor='w',pady=(6,0))
        bar=ttk.Frame(root);bar.pack(fill='x',pady=(10,0))
        ttk.Button(bar,text='取消 / Cancel',command=self._cancel_close).pack(side='right',fill='x',expand=True,padx=(5,0))
        ttk.Button(bar,text='应用 / Apply',style='Primary.TButton',command=self._apply_close).pack(side='right',fill='x',expand=True)
        self.input_var.trace_add('write',lambda *a:self._numeric_changed()); self.output_var.trace_add('write',lambda *a:self._numeric_changed())
        for e in (ie,oe):
            def sel(ev,ent=e): ent.selection_range(0,'end'); ent.icursor('end'); return 'break'
            e.bind('<Control-a>',sel); e.bind('<Control-A>',sel); e.bind('<Double-Button-1>',sel)

    def _enabled_changed(self):
        self.flow['cfg']['base_curve']=bool(self.enabled.get())
        self.owner._flow_changed(force=True); self.owner._draw_graph()

    def _geom(self):
        W=max(self.canvas.winfo_width(),200); H=max(self.canvas.winfo_height(),240); m=24; strip=24
        return W,H,m,max(50,W-2*m),max(50,H-2*m-strip)
    def _to_canvas(self,x,y):
        W,H,m,w,h=self._geom(); return m+x*w,m+(1-y)*h
    def _to_curve(self,cx,cy):
        W,H,m,w,h=self._geom(); return max(0,min(1,(cx-m)/w)),max(0,min(1,1-(cy-m)/h))
    def _nearest(self,cx,cy,thr=12):
        best=None;bd=1e9
        for i,(x,y) in enumerate(self._points()):
            px,py=self._to_canvas(x,y);d=((cx-px)**2+(cy-py)**2)**0.5
            if d<bd:best=i;bd=d
        return best if best is not None and bd<=thr else None

    def _hist(self):
        ch=self.channel.get()
        if ch in self.hist_cache:return self.hist_cache[ch]
        img=self.owner._base_curve_hist_source(self.flow)
        if img is None:return None
        try:
            np,*_=_deps(); smp=np.clip(img[::4,::4],0,1)
            if ch=='红色':vals=smp[...,0].ravel()
            elif ch=='绿色':vals=smp[...,1].ravel()
            elif ch=='蓝色':vals=smp[...,2].ravel()
            else:vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
            hist,_=np.histogram(vals,bins=128,range=(0,1));hist=np.log1p(hist.astype(np.float64));mx=hist.max() or 1;hist/=mx
            self.hist_cache[ch]=hist;return hist
        except Exception:return None

    def _draw(self):
        if not hasattr(self,'canvas'):return
        c=self.canvas;c.delete('all');W,H,m,w,h=self._geom()
        c.create_rectangle(m,m,m+w,m+h,outline='#666',fill='#222')
        for j in range(1,4):
            gx=m+w*j/4;gy=m+h*j/4;c.create_line(gx,m,gx,m+h,fill='#343434');c.create_line(m,gy,m+w,gy,fill='#343434')
        c.create_line(m,m+h,m+w,m,fill='#555',dash=(4,3))
        hist=self._hist()
        if hist is not None:
            poly=[m,m+h];ridge=[]
            for j,v in enumerate(hist):
                x=m+(j/(len(hist)-1))*w;y=m+h-v*h*0.76;poly.extend([x,y]);ridge.extend([x,y])
            poly.extend([m+w,m+h]);c.create_polygon(*poly,fill='#4a4a4a',outline='');c.create_line(*ridge,fill='#777')
        pts=self._points();lut=build_curve_lut(pts,256);line=[]
        for j,v in enumerate(lut):line.extend(self._to_canvas(j/255,float(v)))
        c.create_line(*line,fill='#58a6ff',width=2,smooth=True)
        axis_y=m+h+14
        if len(pts)>=2:
            bx,_=self._to_canvas(pts[0][0],pts[0][1]);wx,_=self._to_canvas(pts[-1][0],pts[-1][1])
            c.create_polygon(bx-6,axis_y+6,bx+6,axis_y+6,bx,axis_y-5,fill='#111',outline='#aaa')
            c.create_polygon(wx-6,axis_y+6,wx+6,axis_y+6,wx,axis_y-5,fill='#eee',outline='#aaa')
        for i,(x,y) in enumerate(pts):
            cx,cy=self._to_canvas(x,y);r=6 if i==self.selected else 4;c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#fff' if i==self.selected else '#b9d6ff',outline='#1f6feb')

    def _set_numeric(self):
        if self.selected is None:return
        pts=self._points()
        if not(0<=self.selected<len(pts)):return
        self.syncing=True
        try:self.input_var.set(round(pts[self.selected][0]*255,2));self.output_var.set(round(pts[self.selected][1]*255,2))
        finally:self.syncing=False
    def _channel_changed(self):self.selected=None;self.axis_drag=None;self._draw()
    def _click(self,e):
        pts=self._points();W,H,m,w,h=self._geom();axis_y=m+h+14
        if len(pts)>=2:
            bx,_=self._to_canvas(pts[0][0],pts[0][1]);wx,_=self._to_canvas(pts[-1][0],pts[-1][1])
            if abs(e.y-axis_y)<=13 and abs(e.x-bx)<=13:self.axis_drag='black';self.selected=0;self._set_numeric();return
            if abs(e.y-axis_y)<=13 and abs(e.x-wx)<=13:self.axis_drag='white';self.selected=len(pts)-1;self._set_numeric();return
        if e.y>m+h:return
        self.axis_drag=None;idx=self._nearest(e.x,e.y)
        if idx is None:
            x,y=self._to_curve(e.x,e.y);pts.append((x,y));pts.sort(key=lambda p:p[0]);idx=min(range(len(pts)),key=lambda i:abs(pts[i][0]-x)+abs(pts[i][1]-y))
        self.selected=idx;self.flow['cfg']['base_curve']=True;self.enabled.set(True);self._set_numeric();self._draw();self.owner._flow_changed(dragging=True);self.owner._draw_graph()
    def _drag(self,e):
        if self.selected is None:return
        pts=self._points();i=self.selected;x,y=self._to_curve(e.x,e.y)
        if self.axis_drag=='black':x=max(0,min(pts[1][0]-0.002,x));pts[0]=(x,pts[0][1]);i=0
        elif self.axis_drag=='white':x=max(pts[-2][0]+0.002,min(1,x));pts[-1]=(x,pts[-1][1]);i=len(pts)-1
        else:
            if i==0:x=max(0,min(pts[1][0]-0.002,x))
            elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
            else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
            pts[i]=(x,y)
        self.selected=i;self.flow['cfg']['base_curve']=True;self._set_numeric();self._draw();self.owner._flow_changed(dragging=True)
    def _release(self,e):self.axis_drag=None;self.owner._flow_changed(force=True)
    def _right_click(self,e):
        idx=self._nearest(e.x,e.y);pts=self._points()
        if idx is None or idx in (0,len(pts)-1):return
        pts.pop(idx);self.selected=None;self._draw();self.owner._flow_changed(force=True)
    def _numeric_changed(self):
        if self.syncing or self.selected is None:return
        pts=self._points();i=self.selected
        try:x=max(0,min(1,float(self.input_var.get())/255));y=max(0,min(1,float(self.output_var.get())/255))
        except Exception:return
        if i==0:x=max(0,min(pts[1][0]-0.002,x))
        elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
        else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
        pts[i]=(x,y);self.flow['cfg']['base_curve']=True;self.enabled.set(True);self._draw();self.owner._flow_changed()
    def _reset_current(self):self.flow['base_curves'][self.channel.get()]=[(0.0,0.0),(1.0,1.0)];self.selected=None;self._draw();self.owner._flow_changed(force=True)
    def _reset_all(self):
        self.flow['base_curves']={k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']};self.selected=None;self.hist_cache.clear();self._draw();self.owner._flow_changed(force=True)


class StandaloneHPCurveDialog(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner; self.before=copy.deepcopy(owner.hp_curve_points); self.before_enabled=bool(owner.hp_curve_enabled.get()); self.committed=False
        self.title('High Pass Curve / 高反差保留曲线')
        self.geometry('620x650'); self.minsize(460,380)
        self.channel=tk.StringVar(value='RGB')
        self.input_var=tk.DoubleVar(value=0.0); self.output_var=tk.DoubleVar(value=0.0)
        self.selected=None; self.axis_drag=None; self.syncing=False; self.hist_cache={}
        self._build(); self._draw(); self.protocol('WM_DELETE_WINDOW',self._cancel_close)

    def _points(self):
        return self.owner.hp_curve_points.setdefault(self.channel.get(),[(0.0,0.0),(1.0,1.0)])

    def _build(self):
        outer=ttk.Frame(self,padding=6); outer.pack(fill='both',expand=True); root,self._scroll_canvas,_scroll_shell=_make_vertical_scroll_area(outer,padding=6)
        top=ttk.Frame(root); top.pack(fill='x')
        self.enabled=self.owner.hp_curve_enabled
        ttk.Checkbutton(top,text='启用 High Pass 曲线',variable=self.enabled,command=lambda:self.owner._schedule_preview(immediate=True)).pack(side='left')
        cb=ttk.Combobox(top,textvariable=self.channel,state='readonly',width=10,values=['RGB','红色','绿色','蓝色','亮度']); cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>',lambda e:self._channel_changed())
        self.canvas=tk.Canvas(root,bg='#202020',height=470,highlightthickness=1,highlightbackground='#555555')
        self.canvas.pack(fill='both',expand=True,pady=(8,6))
        self.canvas.bind('<Button-1>',self._click); self.canvas.bind('<B1-Motion>',self._drag); self.canvas.bind('<ButtonRelease-1>',self._release); self.canvas.bind('<Button-3>',self._right_click); self.canvas.bind('<Configure>',lambda e:self._draw())
        row=ttk.Frame(root); row.pack(fill='x')
        ttk.Label(row,text='输入').pack(side='left'); ie=ttk.Entry(row,textvariable=self.input_var,width=9,justify='right'); ie.pack(side='left',padx=(4,12))
        ttk.Label(row,text='输出').pack(side='left'); oe=ttk.Entry(row,textvariable=self.output_var,width=9,justify='right'); oe.pack(side='left',padx=(4,12))
        ttk.Button(row,text='重置当前通道',command=self._reset_current).pack(side='right')
        ttk.Button(root,text='重置全部曲线',command=self._reset_all).pack(fill='x',pady=(6,0))
        ttk.Label(root,text='高反差保留专用曲线：点击增加控制点；右键删除中间控制点。拖动时主预览会同步更新。',foreground='#666666',wraplength=570).pack(anchor='w',pady=(6,0))
        bar=ttk.Frame(root);bar.pack(fill='x',pady=(10,0))
        ttk.Button(bar,text='取消 / Cancel',command=self._cancel_close).pack(side='right',fill='x',expand=True,padx=(5,0))
        ttk.Button(bar,text='应用 / Apply',style='Primary.TButton',command=self._apply_close).pack(side='right',fill='x',expand=True)
        self.input_var.trace_add('write',lambda *a:self._numeric_changed()); self.output_var.trace_add('write',lambda *a:self._numeric_changed())
        for e in (ie,oe):
            def sel(ev,ent=e): ent.selection_range(0,'end'); ent.icursor('end'); return 'break'
            e.bind('<Control-a>',sel); e.bind('<Control-A>',sel); e.bind('<Double-Button-1>',sel)

    def _apply_close(self):
        self.committed=True; self.owner._schedule_preview(immediate=True); self.destroy()

    def _cancel_close(self):
        if not self.committed:
            self.owner.hp_curve_points=copy.deepcopy(self.before)
            self.owner.hp_curve_enabled.set(self.before_enabled)
            self.owner._schedule_preview(immediate=True)
        self.destroy()

    def _geom(self):
        W=max(self.canvas.winfo_width(),200); H=max(self.canvas.winfo_height(),240); m=24; strip=24
        return W,H,m,max(50,W-2*m),max(50,H-2*m-strip)
    def _to_canvas(self,x,y):
        W,H,m,w,h=self._geom(); return m+x*w,m+(1-y)*h
    def _to_curve(self,cx,cy):
        W,H,m,w,h=self._geom(); return max(0,min(1,(cx-m)/w)),max(0,min(1,1-(cy-m)/h))
    def _nearest(self,cx,cy,thr=12):
        best=None;bd=1e9
        for i,(x,y) in enumerate(self._points()):
            px,py=self._to_canvas(x,y);d=((cx-px)**2+(cy-py)**2)**0.5
            if d<bd:best=i;bd=d
        return best if best is not None and bd<=thr else None

    def _hist(self):
        ch=self.channel.get()
        if ch in self.hist_cache:return self.hist_cache[ch]
        img=self.owner._hp_curve_hist_source()
        if img is None:return None
        try:
            np,*_= _deps()
            smp=np.clip(img[::4,::4],0,1)
            if ch=='红色':vals=smp[...,0].ravel()
            elif ch=='绿色':vals=smp[...,1].ravel()
            elif ch=='蓝色':vals=smp[...,2].ravel()
            else:vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
            hist,_=np.histogram(vals,bins=128,range=(0,1));hist=np.log1p(hist.astype(np.float64));mx=hist.max() or 1;hist/=mx
            self.hist_cache[ch]=hist;return hist
        except Exception:return None

    def _draw(self):
        if not hasattr(self,'canvas'):return
        c=self.canvas;c.delete('all');W,H,m,w,h=self._geom()
        c.create_rectangle(m,m,m+w,m+h,outline='#666',fill='#222')
        for j in range(1,4):
            gx=m+w*j/4;gy=m+h*j/4;c.create_line(gx,m,gx,m+h,fill='#343434');c.create_line(m,gy,m+w,gy,fill='#343434')
        c.create_line(m,m+h,m+w,m,fill='#555',dash=(4,3))
        hist=self._hist()
        if hist is not None:
            poly=[m,m+h];ridge=[]
            for j,v in enumerate(hist):
                x=m+(j/(len(hist)-1))*w;y=m+h-v*h*0.76;poly.extend([x,y]);ridge.extend([x,y])
            poly.extend([m+w,m+h]);c.create_polygon(*poly,fill='#4a4a4a',outline='');c.create_line(*ridge,fill='#777')
        pts=self._points();lut=build_curve_lut(pts,256);line=[]
        for j,v in enumerate(lut):line.extend(self._to_canvas(j/255,float(v)))
        c.create_line(*line,fill='#58a6ff',width=2,smooth=True)
        axis_y=m+h+14
        if len(pts)>=2:
            bx,_=self._to_canvas(pts[0][0],pts[0][1]);wx,_=self._to_canvas(pts[-1][0],pts[-1][1])
            c.create_polygon(bx-6,axis_y+6,bx+6,axis_y+6,bx,axis_y-5,fill='#111',outline='#aaa')
            c.create_polygon(wx-6,axis_y+6,wx+6,axis_y+6,wx,axis_y-5,fill='#eee',outline='#aaa')
        for i,(x,y) in enumerate(pts):
            cx,cy=self._to_canvas(x,y);r=6 if i==self.selected else 4;c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#fff' if i==self.selected else '#b9d6ff',outline='#1f6feb')

    def _set_numeric(self):
        if self.selected is None:return
        pts=self._points()
        if not(0<=self.selected<len(pts)):return
        self.syncing=True
        try:self.input_var.set(round(pts[self.selected][0]*255,2));self.output_var.set(round(pts[self.selected][1]*255,2))
        finally:self.syncing=False
    def _channel_changed(self):self.selected=None;self.axis_drag=None;self._draw()
    def _click(self,e):
        pts=self._points();W,H,m,w,h=self._geom();axis_y=m+h+14
        if len(pts)>=2:
            bx,_=self._to_canvas(pts[0][0],pts[0][1]);wx,_=self._to_canvas(pts[-1][0],pts[-1][1])
            if abs(e.y-axis_y)<=13 and abs(e.x-bx)<=13:self.axis_drag='black';self.selected=0;self._set_numeric();return
            if abs(e.y-axis_y)<=13 and abs(e.x-wx)<=13:self.axis_drag='white';self.selected=len(pts)-1;self._set_numeric();return
        if e.y>m+h:return
        self.axis_drag=None;idx=self._nearest(e.x,e.y)
        if idx is None:
            x,y=self._to_curve(e.x,e.y);pts.append((x,y));pts.sort(key=lambda p:p[0]);idx=min(range(len(pts)),key=lambda i:abs(pts[i][0]-x)+abs(pts[i][1]-y))
        self.selected=idx;self.owner.hp_curve_enabled.set(True);self.enabled.set(True);self._set_numeric();self._draw();self.owner._schedule_preview(immediate=False)
    def _drag(self,e):
        if self.selected is None:return
        pts=self._points();i=self.selected;x,y=self._to_curve(e.x,e.y)
        if self.axis_drag=='black':x=max(0,min(pts[1][0]-0.002,x));pts[0]=(x,pts[0][1]);i=0
        elif self.axis_drag=='white':x=max(pts[-2][0]+0.002,min(1,x));pts[-1]=(x,pts[-1][1]);i=len(pts)-1
        else:
            if i==0:x=max(0,min(pts[1][0]-0.002,x))
            elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
            else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
            pts[i]=(x,y)
        self.selected=i;self.owner.hp_curve_enabled.set(True);self._set_numeric();self._draw();self.owner._schedule_preview(immediate=False)
    def _release(self,e):self.axis_drag=None;self.owner._schedule_preview(immediate=True)
    def _right_click(self,e):
        idx=self._nearest(e.x,e.y);pts=self._points()
        if idx is None or idx in (0,len(pts)-1):return
        pts.pop(idx);self.selected=None;self._draw();self.owner._schedule_preview(immediate=True)
    def _numeric_changed(self):
        if self.syncing or self.selected is None:return
        pts=self._points();i=self.selected
        try:x=max(0,min(1,float(self.input_var.get())/255));y=max(0,min(1,float(self.output_var.get())/255))
        except Exception:return
        if i==0:x=max(0,min(pts[1][0]-0.002,x))
        elif i==len(pts)-1:x=max(pts[-2][0]+0.002,min(1,x))
        else:x=max(pts[i-1][0]+0.002,min(pts[i+1][0]-0.002,x))
        pts[i]=(x,y);self.owner.hp_curve_enabled.set(True);self.enabled.set(True);self._draw();self.owner._schedule_preview(immediate=False)
    def _reset_current(self):self.owner.hp_curve_points[self.channel.get()]=[(0.0,0.0),(1.0,1.0)];self.selected=None;self._draw();self.owner._schedule_preview(immediate=True)
    def _reset_all(self):
        self.owner.hp_curve_points={k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']};self.selected=None;self.hist_cache.clear();self._draw();self.owner._schedule_preview(immediate=True)


class TimelapseNodeWindow(tk.Toplevel):
    NODE_ORDER=[('stack','Stack\n堆栈'),('stretch','Stretch\n拉伸'),('basic','Base\n基础调色'),('usm','USM\n锐化'),('bgr','BGR\n背景+曲线'),('highpass','High Pass\n高反差保留'),('emboss','Emboss\n浮雕'),('br','BR\n通道混合器'),('output','Output\n输出')]
    def __init__(self,app):
        super().__init__(app);self.app=app
        self.title(f'{APP_NAME} · 节点堆栈延时 / Node Stack Timelapse v{VERSION}')
        self.geometry('1580x900');self.minsize(1180,720)
        self.queue=Queue();self.worker=None;self.cancel_event=threading.Event();self.preview_photo=None
        self.reference_master=None;self.reference_proxy_drag=None;self.reference_proxy_drag_scale=1.0;self.reference_proxy_fast=None;self.reference_proxy_fast_scale=1.0;self.reference_proxy_hq=None;self.reference_proxy_hq_scale=1.0
        self.preview_running=False;self.preview_pending=False;self.preview_after=None;self.preview_token=0;self.preview_quality='fast'
        self.preview_pending_quality='fast';self.preview_hq_after=None;self.preview_active_node=None
        # Separate interactive and HQ lanes: a settled high-resolution refinement
        # must never make a newly moved slider wait seconds before it responds.
        self.preview_interactive_running=False;self.preview_hq_running=False
        self.preview_stage_cache={};self.preview_stage_cache_order=[];self.preview_cache_limit=18;self._preview_reference_serial=0
        self.preview_hq_idle_ms=1200
        self.mode=tk.StringVar(value='滑动窗口（推荐：观察变化）');self.stack_method=tk.StringVar(value='平均值 Mean');self.window_size=tk.IntVar(value=min(15,max(2,len(app.files))));self.step=tk.IntVar(value=1);self.normalize=tk.BooleanVar(value=bool(app.normalize_var.get()));self.preview_index=tk.IntVar(value=1)
        self.mode_desc=tk.StringVar(value='');self.summary=tk.StringVar(value='');self.output_folder=tk.StringVar(value=str(Path.cwd()/'IceHaloStack_Timelapse_Output'));self.progress=tk.DoubleVar(value=0);self.status=tk.StringVar(value='第 1 步：生成参考堆栈')
        self.processing_progress=tk.DoubleVar(value=0.0);self.writing_progress=tk.DoubleVar(value=0.0);self.output_pipeline_text=tk.StringVar(value='写入：空闲')
        self.elapsed_text=tk.StringVar(value='运行时间 / Elapsed：00:00:00');self.batch_started_at=None;self.batch_elapsed_seconds=0.0;self._elapsed_after_id=None
        _init_timelapse_memory_vars(self)
        _init_ewb_vars(self)
        self.normalize.set(False)
        self.graph_zoom=1.0;self.node_drag=None;self.link_preview=None;self.graph_context_pos=(0,0);self.wb_pick_context=None;self.last_preview_image=None;self.preview_display_rect=None
        self.workflow_undo=[];self.workflow_redo=[];self.workflow_history_limit=80
        self.flows=[self._new_flow('流程 1')];self.selected_flow=tk.IntVar(value=0);self.node_hits=[]
        self._build_ui();_enforce_regular_typography(self);self.after_idle(lambda: _enforce_regular_typography(self));self._bind_workflow_history_keys(self);self._update_summary();self._refresh_flow_list();self.after(80,self._poll)

    def _bind_workflow_history_keys(self,widget):
        for seq in ('<Control-z>','<Control-Z>'):
            widget.bind(seq,self._workflow_undo_shortcut,add='+')
        for seq in ('<Control-Shift-z>','<Control-Shift-Z>'):
            widget.bind(seq,self._workflow_redo_shortcut,add='+')

    def _workflow_state(self):
        return {'flows':copy.deepcopy(self.flows),'selected_flow':int(self.selected_flow.get() or 0)}

    def _workflow_state_equal(self,a,b):
        try:return a==b
        except Exception:return False

    def _commit_workflow_history(self,before,label='节点操作'):
        after=self._workflow_state()
        if self._workflow_state_equal(before,after):return
        self.workflow_undo.append({'state':copy.deepcopy(before),'label':label})
        if len(self.workflow_undo)>self.workflow_history_limit:self.workflow_undo=self.workflow_undo[-self.workflow_history_limit:]
        self.workflow_redo.clear()
        self.status.set(f'已应用：{label} · Ctrl+Z 可撤回')

    def _restore_workflow_state(self,state):
        self.flows=copy.deepcopy(state.get('flows',[])) or [self._new_flow('流程 1')]
        for i,f in enumerate(self.flows):self.flows[i]=self._normalize_flow(f)
        idx=max(0,min(len(self.flows)-1,int(state.get('selected_flow',0) or 0)))
        self.selected_flow.set(idx)
        self._refresh_flow_list();self._draw_graph();self._schedule_preview(force=True)

    def workflow_undo_action(self):
        if not self.workflow_undo:
            self.status.set('没有可撤回的节点操作');return
        current=self._workflow_state();item=self.workflow_undo.pop()
        self.workflow_redo.append({'state':current,'label':item.get('label','节点操作')})
        if len(self.workflow_redo)>self.workflow_history_limit:self.workflow_redo=self.workflow_redo[-self.workflow_history_limit:]
        self._restore_workflow_state(item['state']);self.status.set(f"已撤回：{item.get('label','节点操作')} · Ctrl+Shift+Z 可重做")

    def workflow_redo_action(self):
        if not self.workflow_redo:
            self.status.set('没有可重做的节点操作');return
        current=self._workflow_state();item=self.workflow_redo.pop()
        self.workflow_undo.append({'state':current,'label':item.get('label','节点操作')})
        if len(self.workflow_undo)>self.workflow_history_limit:self.workflow_undo=self.workflow_undo[-self.workflow_history_limit:]
        self._restore_workflow_state(item['state']);self.status.set(f"已重做：{item.get('label','节点操作')}")

    def _workflow_undo_shortcut(self,event=None):
        self.workflow_undo_action();return 'break'

    def _workflow_redo_shortcut(self,event=None):
        self.workflow_redo_action();return 'break'

    def _appval(self,name,default=0.0):
        try:return float(getattr(self.app,name).get())
        except Exception:return float(default)
    def _default_cfg(self):
        bv=getattr(self.app,'basic_vars',{})
        def b(k,d=0):
            try:return float(bv[k].get())
            except Exception:return float(d)
        return dict(stretch=True,stretch_strength=self._appval('stretch_strength',8),stretch_black=self._appval('stretch_black',0),basic=True,exposure=b('exposure'),contrast=b('contrast'),highlights=b('highlights'),shadows=b('shadows'),whites=b('whites'),blacks=b('blacks'),clarity=b('clarity'),dehaze=b('dehaze'),vibrance=b('vibrance'),saturation=b('saturation'),bgr=False,background=False,bg_radius=80.0,bg_strength=100.0,curves=False,usm=False,usm_amount=self._appval('usm_amount',100),usm_radius=self._appval('usm_radius',2),usm_threshold=self._appval('usm_threshold',0),usm_passes=1,highpass=False,hp_radius=self._appval('hp_radius',10),hp_amount=self._appval('hp_amount',100),hp_mode=str(getattr(self.app,'hp_mode',tk.StringVar(value='Overlay')).get()),emboss=False,emboss_angle=self._appval('emboss_angle',-128),emboss_height=self._appval('emboss_height',1),emboss_amount=self._appval('emboss_strength',100),emboss_style=str(getattr(self.app,'emboss_style',tk.StringVar(value='Photoshop Emboss')).get()),emboss_blend=str(getattr(self.app,'emboss_blend',tk.StringVar(value='Normal')).get()),emboss_opacity=self._appval('emboss_opacity',100),br=False,channel=False,channel_output=str(getattr(self.app,'channel_output',tk.StringVar(value='灰色')).get()),channel_mono=bool(getattr(self.app,'channel_mono',tk.BooleanVar(value=True)).get()),channel_red=self._appval('channel_red',40),channel_green=self._appval('channel_green',40),channel_blue=self._appval('channel_blue',20),channel_constant=self._appval('channel_constant',0),channel_noise=bool(getattr(self.app,'channel_noise_protect',tk.BooleanVar(value=True)).get()),channel_noise_strength=self._appval('channel_noise_strength',30),channel_noise_radius=self._appval('channel_noise_radius',0.8),temperature=0.0,tint=0.0,texture=0.0,base_curve=False,hsl_hue=0.0,hsl_sat=0.0,hsl_lum=0.0,
            cg_shadow_h=220.0,cg_shadow_s=0.0,cg_mid_h=35.0,cg_mid_s=0.0,cg_high_h=45.0,cg_high_s=0.0,cg_balance=0.0,
            detail_sharpen=0.0,detail_radius=1.0,luma_nr=0.0,chroma_nr=0.0,opt_distortion=0.0,opt_vignette=0.0,opt_ca=0.0,
            cal_red_h=0.0,cal_red_s=0.0,cal_green_h=0.0,cal_green_s=0.0,cal_blue_h=0.0,cal_blue_s=0.0,
            **{f'mix_{c}_{a}':0.0 for c in ['red','orange','yellow','green','aqua','blue','purple','magenta'] for a in ['h','s','l']})
    def _default_node_layout(self):
        # Compact U-shaped flow: descend on the left, turn at the bottom,
        # then climb the right side toward Output. This keeps the complete
        # pipeline visible without requiring an extremely tall canvas.
        return {
            'stack': (260.0, 145.0),
            'stretch': (260.0, 315.0),
            'basic': (260.0, 485.0),
            'usm': (260.0, 655.0),
            'bgr': (260.0, 825.0),
            'highpass': (640.0, 825.0),
            'emboss': (640.0, 655.0),
            'br': (640.0, 485.0),
            'output': (640.0, 315.0),
        }

    def _arrange_u(self,flow):
        flow=self._normalize_flow(flow)
        base=self._default_node_layout()
        for key in flow.get('present_nodes',[]):
            if key in base: flow['layout'][key]=tuple(base[key])

    def _arrange_vertical(self,flow,x=420.0,start_y=120.0,gap=145.0):
        flow=self._normalize_flow(flow)
        for i,key in enumerate([k for k,_ in self.NODE_ORDER if k in flow.get('present_nodes',[])]):
            flow['layout'][key]=(float(x), float(start_y+i*gap))

    def _default_edges(self,present_nodes=None):
        present=set(present_nodes or [k for k,_ in self.NODE_ORDER])
        order=[k for k,_ in self.NODE_ORDER if k in present]
        return [(order[i],order[i+1]) for i in range(len(order)-1)]

    def _new_flow(self,name):
        present=[k for k,_ in self.NODE_ORDER]
        flow={'name':name,'cfg':self._default_cfg(),'curves':{k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']},'base_curves':{k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']},'present_nodes':present[:],'layout':self._default_node_layout(),'edges':self._default_edges(present),'output':{'export_enabled':True,'save_sequence':True,'sequence_format':'PNG 8-bit','save_video':True,'delete_sequence_after_video_only':True,'video_format':'MP4 H.264','fps':24.0,'scale_percent':100.0,'name_template':'{index:02d}_{name}'}}
        self._arrange_u(flow)
        return flow

    def _normalize_flow(self,f):
        cfg=f.setdefault('cfg',{})
        for dk,dv in self._default_cfg().items(): cfg.setdefault(dk,copy.deepcopy(dv))
        if 'base_curves' not in f or not isinstance(f.get('base_curves'),dict): f['base_curves']={k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']}
        if 'delete_sequence_after_video_only' not in f.get('output',{}): f.setdefault('output',{})['delete_sequence_after_video_only']=True
        if 'bgr' not in cfg: cfg['bgr']=bool(cfg.get('background',False) or cfg.get('curves',False))
        if 'br' not in cfg: cfg['br']=bool(cfg.get('channel',False))
        if 'channel' not in cfg: cfg['channel']=cfg.get('br',False)
        allowed=[k for k,_ in self.NODE_ORDER]
        allowed_set=set(allowed)
        present=f.get('present_nodes', allowed[:])
        if not isinstance(present,list): present=allowed[:]
        present=[k for k in present if k in allowed_set]
        if 'stack' not in present: present.insert(0,'stack')
        if 'output' not in present: present.append('output')
        dedup=[]
        for k in allowed:
            if k in present and k not in dedup: dedup.append(k)
        f['present_nodes']=dedup
        if 'layout' not in f or not isinstance(f.get('layout'),dict):
            f['layout']=self._default_node_layout()
        else:
            base=self._default_node_layout()
            for k,v in base.items(): f['layout'].setdefault(k,v)
            for old in ('background','curves','channel'):
                f['layout'].pop(old,None)
        edges=f.get('edges',[])
        if not isinstance(edges,list): edges=[]
        clean=[]
        for e in edges:
            try:a,b=e
            except Exception: continue
            if a in f['present_nodes'] and b in f['present_nodes'] and a!=b and (a,b) not in clean: clean.append((a,b))
        f['edges']=clean or self._default_edges(f['present_nodes'])
        return f

    def _flow(self):
        if not self.flows:return None
        i=max(0,min(len(self.flows)-1,int(self.selected_flow.get() or 0)));self.selected_flow.set(i);return self._normalize_flow(self.flows[i])

    def _build_ui(self):
        root=ttk.Frame(self,padding=8);root.pack(fill='both',expand=True)
        head=ttk.Frame(root);head.pack(fill='x');ttk.Label(head,text='堆栈延时 · 节点工作流 / Stack Timelapse · Node Workflow',font=_ui_font(15)).pack(side='left');ttk.Label(head,text=f'输入 {len(self.app.files)} 帧',foreground='#666').pack(side='right');ttk.Separator(root).pack(fill='x',pady=7)
        # Use classic tk.PanedWindow here instead of ttk.Panedwindow.
        # On some Windows/Tk DPI combinations ttk.Panedwindow can initialize
        # the first two panes at zero width, leaving only Live Preview visible.
        pane=tk.PanedWindow(root,orient='horizontal',sashrelief='raised',sashwidth=6,borderwidth=0,showhandle=False)
        pane.pack(fill='both',expand=True)
        self.main_pane=pane
        left_pane=ttk.Frame(pane,padding=(0,0,6,0),width=330)
        center=ttk.Frame(pane,padding=(6,0),width=690)
        right=ttk.Frame(pane,padding=(6,0,0,0),width=500)
        self.left_pane=left_pane; self.center_pane=center; self.right_pane=right
        pane.add(left_pane,minsize=285,width=330,stretch='never')
        pane.add(center,minsize=470,width=690,stretch='always')
        pane.add(right,minsize=360,width=500,stretch='always')
        # The complete left workflow column is vertically scrollable. This keeps
        # Batch Export / Apply controls reachable on smaller or high-DPI screens.
        left,self.left_scroll_canvas,_left_shell=_make_vertical_scroll_area(left_pane,padding=0)
        # reference controls
        ref=ttk.LabelFrame(left,text='参考堆栈',padding=7);ref.pack(fill='x')
        r=ttk.Frame(ref);r.pack(fill='x',pady=2);ttk.Label(r,text='模式').pack(side='left');cb=ttk.Combobox(r,textvariable=self.mode,state='readonly',width=24,values=['滑动窗口（推荐：观察变化）','中心窗口（按中央时刻理解）','累计堆栈（观察信号生长）','逐帧剔除（贡献分析）']);cb.pack(side='right')
        r=ttk.Frame(ref);r.pack(fill='x',pady=2);ttk.Label(r,text='堆栈方式').pack(side='left');ttk.Combobox(r,textvariable=self.stack_method,state='readonly',width=18,values=['平均值 Mean','最大值 Maximum']).pack(side='right')
        self._small_entry(ref,'窗口大小',self.window_size);self._small_entry(ref,'步长',self.step)
        ttk.Label(ref,textvariable=self.summary,foreground='#666',wraplength=280).pack(anchor='w',pady=(3,4));rr=ttk.Frame(ref);rr.pack(fill='x');ttk.Label(rr,text='参考输出帧').pack(side='left');self.preview_spin=ttk.Spinbox(rr,textvariable=self.preview_index,from_=1,to=1,width=6);self.preview_spin.pack(side='left',padx=5);ttk.Button(rr,text='生成参考堆栈',style='Primary.TButton',command=self.generate_reference).pack(side='right')
        _build_ewb_panel(self,left,wraplength=280)
        _build_timelapse_memory_panel(self,left,wraplength=280,show_dag=True)
        # flow list
        fm=ttk.LabelFrame(left,text='节点流程 / Flows',padding=7);fm.pack(fill='both',expand=True,pady=(8,0))
        self.flow_list=tk.Listbox(fm,exportselection=False,font=_ui_font(10),height=10);self.flow_list._ihs_translate_flow_items=True;self.flow_list.pack(fill='both',expand=True);self.flow_list.bind('<<ListboxSelect>>',self._flow_select)
        b=ttk.Frame(fm);b.pack(fill='x',pady=(5,0));ttk.Button(b,text='＋ 新建',command=self._add_flow).pack(side='left',fill='x',expand=True);ttk.Button(b,text='复制',command=self._dup_flow).pack(side='left',fill='x',expand=True,padx=3);ttk.Button(b,text='删除',command=self._del_flow).pack(side='left',fill='x',expand=True)
        p=ttk.Frame(fm);p.pack(fill='x',pady=(5,0));ttk.Button(p,text='保存当前预设',command=self._save_preset).pack(fill='x');ttk.Button(p,text='加载预设为新流程',command=self._load_preset).pack(fill='x',pady=3);ttk.Button(p,text='批量导入预设',command=self._batch_import_presets).pack(fill='x')
        hb=ttk.Frame(fm);hb.pack(fill='x',pady=(5,0));ttk.Button(hb,text='↶ Undo  Ctrl+Z',command=self.workflow_undo_action).pack(side='left',fill='x',expand=True);ttk.Button(hb,text='↷ Redo  Ctrl+Shift+Z',command=self.workflow_redo_action).pack(side='left',fill='x',expand=True,padx=(4,0))
        # output root
        out=ttk.LabelFrame(left,text='批量导出 / Batch Export',padding=7);out.pack(fill='x',pady=(8,0));er=ttk.Frame(out);er.pack(fill='x');ttk.Entry(er,textvariable=self.output_folder).pack(side='left',fill='x',expand=True);ttk.Button(er,text='选择',command=self._choose_output).pack(side='right',padx=(4,0));self.start_btn=ttk.Button(out,text='开始批量导出所有启用流程',style='Primary.TButton',command=self.start_batch);self.start_btn.pack(fill='x',pady=(5,2));self.cancel_btn=ttk.Button(out,text='取消',command=self.cancel,state='disabled');self.cancel_btn.pack(fill='x')
        ttk.Label(out,textvariable=self.elapsed_text).pack(anchor='w',pady=(6,0))
        # node canvas large
        nodebox=ttk.LabelFrame(center,text='当前流程节点画布 / Node Canvas · 单击节点编辑参数',padding=5);nodebox.pack(fill='both',expand=True)
        nodewrap=ttk.Frame(nodebox);nodewrap.pack(fill='both',expand=True)
        self.node_canvas=tk.Canvas(nodewrap,bg='#151515',highlightthickness=0); self.node_canvas._ihs_node_canvas=True
        hs=ttk.Scrollbar(nodewrap,orient='horizontal',command=self.node_canvas.xview)
        vs=ttk.Scrollbar(nodewrap,orient='vertical',command=self.node_canvas.yview)
        self.node_canvas.configure(xscrollcommand=hs.set,yscrollcommand=vs.set)
        vs.pack(side='right',fill='y')
        self.node_canvas.pack(side='left',fill='both',expand=True)
        hs.pack(fill='x')
        self.node_canvas.bind('<ButtonPress-1>',self._graph_press)
        self.node_canvas.bind('<B1-Motion>',self._graph_drag)
        self.node_canvas.bind('<ButtonRelease-1>',self._graph_release)
        self.node_canvas.bind('<MouseWheel>',self._graph_wheel)
        self.node_canvas.bind('<Button-4>',lambda e:self._graph_wheel_linux(e,1))
        self.node_canvas.bind('<Button-5>',lambda e:self._graph_wheel_linux(e,-1))
        self.node_canvas.bind('<Button-3>',self._graph_context_menu)
        self.node_canvas.bind('<Configure>',lambda e:self._draw_graph())
        ttk.Button(center,text='节点画布操作…',command=self._show_node_canvas_help).pack(anchor='e',pady=(4,0))
        # preview
        pv=ttk.LabelFrame(right,text='当前流程实时预览 / Live Preview',padding=5);pv.pack(fill='both',expand=True);self.preview_frame=pv
        self.preview_title=tk.StringVar(value='尚未生成参考堆栈')
        pvh=ttk.Frame(pv);pvh.pack(fill='x')
        ttk.Label(pvh,textvariable=self.preview_title,font=_ui_font(10)).pack(side='left',anchor='w')
        self.preview_zoom_text=tk.StringVar(value='Fit')
        zbar=ttk.Frame(pvh);zbar.pack(side='right')
        for label,value in [('25%',0.25),('50%',0.50),('100%',1.0),('200%',2.0)]:
            ttk.Button(zbar,text=label,width=5,command=lambda v=value:self._preview_set_zoom(v)).pack(side='left',padx=1)
        ttk.Button(zbar,text='Fit',width=5,command=self._preview_fit).pack(side='left',padx=(2,0))
        ttk.Label(zbar,textvariable=self.preview_zoom_text,width=10,anchor='e').pack(side='left',padx=(5,0))
        self.preview_canvas=tk.Canvas(pv,bg='#101010',highlightthickness=0,width=460,height=560)
        self.preview_canvas.pack(fill='both',expand=True,pady=(5,0))
        self.preview_canvas.create_text(18,18,anchor='nw',fill='#9a9a9a',text='生成参考堆栈后，这里会显示当前流程的实时预览。',tags='placeholder')
        self.preview_zoom=1.0; self.preview_fit_mode=True; self.preview_pan=[0.0,0.0]; self.preview_pan_anchor=None; self.last_preview_image=None; self.preview_display_rect=None
        self.preview_canvas.bind('<Configure>',lambda e:self._schedule_preview())
        self.preview_canvas.bind('<MouseWheel>',self._preview_zoom_wheel)
        self.preview_canvas.bind('<Button-4>',lambda e:self._preview_zoom_wheel_linux(e,1))
        self.preview_canvas.bind('<Button-5>',lambda e:self._preview_zoom_wheel_linux(e,-1))
        self.preview_canvas.bind('<ButtonPress-1>',self._preview_mouse_press)
        self.preview_canvas.bind('<B1-Motion>',self._preview_pan_drag)
        self.preview_canvas.bind('<ButtonRelease-1>',self._preview_pan_end)
        self.preview_canvas.bind('z',lambda e:self._preview_fit())
        self.preview_canvas.bind('Z',lambda e:self._preview_fit())
        self.preview_canvas.bind('<Configure>',lambda e:self._preview_redraw(),add='+')
        ttk.Label(right,text='Processing / 处理',foreground='#666').pack(anchor='w',pady=(7,0));ttk.Progressbar(right,variable=self.processing_progress,maximum=100).pack(fill='x',pady=(2,2))
        ttk.Label(right,text='Writing / 写入',foreground='#666').pack(anchor='w',pady=(2,0));ttk.Progressbar(right,variable=self.writing_progress,maximum=100).pack(fill='x',pady=(2,2))
        ttk.Label(right,textvariable=self.output_pipeline_text,foreground='#666',wraplength=470).pack(anchor='w',pady=(1,2))
        ttk.Progressbar(right,variable=self.progress,maximum=100).pack(fill='x',pady=(4,3));ttk.Label(right,textvariable=self.status,wraplength=470).pack(anchor='w')
        for v in (self.mode,self.stack_method,self.window_size,self.step):v.trace_add('write',lambda *a:self._update_summary())
        # Wait until the Toplevel is mapped before placing sashes. Doing this
        # at idle is too early on some Windows systems and can collapse panes.
        self._pane_layout_initialized=False
        self.after(120,self._set_initial_pane_positions)
        self.after(420,self._verify_pane_positions)

    def _show_node_canvas_help(self):
        messagebox.showinfo(
            '节点画布操作',
            '单击节点：编辑参数\n'
            'Shift + 拖拽节点：创建或取消连线\n'
            '右键节点：编辑或删除\n'
            '右键空白处：新增节点\n'
            '滚轮：纵向滚动\n'
            'Shift + 滚轮：横向滚动\n'
            'Ctrl + 滚轮：缩放节点画布\n'
            '拖拽空白：平移\n'
            '拖拽节点：移动节点\n\n'
            'BGR = Background + Curves\nBR = Channel Mixer',
            parent=self)

    def _set_initial_pane_positions(self):
        try:
            self.update_idletasks()
            w=max(1180,int(self.winfo_width()))
            # Keep all three sections visible. The center gets the largest share,
            # while the Live Preview always retains a useful minimum width.
            left_w=max(300,min(370,int(w*0.215)))
            right_w=max(390,min(560,int(w*0.31)))
            center_w=max(500,w-left_w-right_w-20)
            self.main_pane.sash_place(0,left_w,1)
            self.main_pane.sash_place(1,left_w+center_w+6,1)
            self._pane_layout_initialized=True
        except Exception:
            self._pane_layout_initialized=False
        try:
            self.right_pane.update_idletasks()
            self.preview_canvas.update_idletasks()
        except Exception:
            pass

    def _verify_pane_positions(self):
        """Recover from a DPI/Tk startup layout that collapsed a pane."""
        try:
            self.update_idletasks()
            lw=max(0,self.left_pane.winfo_width())
            cw=max(0,self.center_pane.winfo_width())
            rw=max(0,self.right_pane.winfo_width())
            if lw < 260 or cw < 430 or rw < 330:
                self._set_initial_pane_positions()
        except Exception:
            pass

    def _small_entry(self,parent,label,var):
        r=ttk.Frame(parent);r.pack(fill='x',pady=2);ttk.Label(r,text=label).pack(side='left');e=ttk.Entry(r,textvariable=var,width=8,justify='right');e.pack(side='right');return e
    def _refresh_flow_list(self):
        self.flow_list.delete(0,'end')
        sources=[]
        for i,f in enumerate(self.flows,1):
            f=self._normalize_flow(f); o=f['output'];flag='●' if o.get('export_enabled',True) else '○';raw=f'{flag} {i:02d}  {f["name"]}';sources.append(raw);self.flow_list.insert('end',_translate_flow_list_item(raw))
        self.flow_list._ihs_i18n_item_sources=sources
        if self.flows:
            idx=max(0,min(len(self.flows)-1,int(self.selected_flow.get() or 0)));self.flow_list.selection_clear(0,'end');self.flow_list.selection_set(idx);self.flow_list.activate(idx)
        self._draw_graph()
    def _flow_select(self,e=None):
        sel=self.flow_list.curselection()
        if not sel:return
        self.selected_flow.set(sel[0]);self._draw_graph();self._schedule_preview(force=True)
    def _add_flow(self):
        before=self._workflow_state();self.flows.append(self._new_flow(f'流程 {len(self.flows)+1}'));self.selected_flow.set(len(self.flows)-1);self._refresh_flow_list();self._schedule_preview(force=True);self._commit_workflow_history(before,'新建流程')
    def _dup_flow(self):
        f=self._flow()
        if not f:return
        before=self._workflow_state();nf=copy.deepcopy(f);nf['name']=f['name']+' 副本';self.flows.append(nf);self.selected_flow.set(len(self.flows)-1);self._refresh_flow_list();self._schedule_preview(force=True);self._commit_workflow_history(before,'复制流程')
    def _del_flow(self):
        if len(self.flows)<=1:messagebox.showinfo(APP_NAME,'至少保留一个流程。',parent=self);return
        before=self._workflow_state();i=int(self.selected_flow.get());name=self.flows[i].get('name',f'流程{i+1}');self.flows.pop(i);self.selected_flow.set(max(0,min(i,len(self.flows)-1)));self._refresh_flow_list();self._schedule_preview(force=True);self._commit_workflow_history(before,f'删除流程：{name}')

    def _node_enabled(self,flow,key):
        flow=self._normalize_flow(flow)
        if key not in flow.get('present_nodes',[]): return False
        cfg=flow['cfg']
        if key in ('stack','output'): return True
        if key=='bgr': return bool(cfg.get('bgr',False))
        if key=='br': return bool(cfg.get('br',False))
        return bool(cfg.get(key,False))

    def _get_active_edges(self,flow):
        flow=self._normalize_flow(flow)
        active={k for k in flow.get('present_nodes',[]) if self._node_enabled(flow,k)}
        return [(a,b) for a,b in flow.get('edges',[]) if a in active and b in active]

    def _flow_exec_order(self,flow):
        flow=self._normalize_flow(flow)
        nodes=[k for k,_ in self.NODE_ORDER]
        node_set=set(nodes)
        edges=[(a,b) for a,b in flow.get('edges',[]) if a in node_set and b in node_set and a!=b]
        adj={k:[] for k in nodes}; rev={k:[] for k in nodes}
        for a,b in edges:
            if b not in adj[a]:
                adj[a].append(b); rev[b].append(a)
        # Only execute nodes that lie on at least one Stack -> Output path.
        reach=set(); stack=['stack']
        while stack:
            n=stack.pop()
            if n in reach: continue
            reach.add(n); stack.extend(adj.get(n,[]))
        to_out=set(); stack=['output']
        while stack:
            n=stack.pop()
            if n in to_out: continue
            to_out.add(n); stack.extend(rev.get(n,[]))
        relevant=reach & to_out
        if 'output' not in relevant:
            return []
        indeg={k:0 for k in relevant}
        for a,b in edges:
            if a in relevant and b in relevant: indeg[b]+=1
        q=[n for n in nodes if n in relevant and indeg[n]==0]
        order=[]
        while q:
            n=q.pop(0); order.append(n)
            for m in adj.get(n,[]):
                if m not in relevant: continue
                indeg[m]-=1
                if indeg[m]==0:q.append(m)
        if len(order)!=len(relevant):
            raise ValueError('流程图中存在循环，无法执行。')
        return [n for n in order if n not in ('stack','output')]

    def _apply_single_flow_node(self,out,node,flow):
        """Apply one node with the exact same math used by final batch output.

        Preview acceleration is allowed to reuse/crop/cache inputs, but it must
        never use a different sharpening/emboss/background algorithm than the
        final renderer. Keeping the node math in one function prevents the old
        "preview looks strong, Apply looks weak" regression.
        """
        cfg=flow['cfg'];curves=flow['curves']
        if node=='stretch':
            if cfg.get('stretch',False):
                out=apply_asinh_stretch(out,float(cfg.get('stretch_strength',8)),float(cfg.get('stretch_black',0)))
        elif node=='basic':
            if cfg.get('basic',False):
                out=apply_base_editor(out,cfg,flow.get('base_curves'))
        elif node=='usm':
            if cfg.get('usm',False):
                passes=max(1,min(10,int(cfg.get('usm_passes',1))))
                for _ in range(passes):
                    out=apply_usm(out,float(cfg.get('usm_amount',100)),float(cfg.get('usm_radius',2)),float(cfg.get('usm_threshold',0)))
        elif node=='bgr':
            if cfg.get('bgr',False):
                if cfg.get('background',False):
                    out=background_suppression(out,float(cfg.get('bg_radius',80)),float(cfg.get('bg_strength',100)))
                if cfg.get('curves',False) and curves:
                    for ch in ['RGB','红色','绿色','蓝色','亮度']:
                        pts=curves.get(ch,[(0.0,0.0),(1.0,1.0)])
                        identity=len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6
                        if not identity:
                            out=apply_curve_lut(out,build_curve_lut(pts,256),ch)
        elif node=='highpass':
            if cfg.get('highpass',False):
                out=apply_highpass(out,float(cfg.get('hp_radius',10)),float(cfg.get('hp_amount',100)),str(cfg.get('hp_mode','Overlay')))
        elif node=='emboss':
            if cfg.get('emboss',False):
                out=apply_emboss(out,float(cfg.get('emboss_angle',-128)),float(cfg.get('emboss_height',1)),float(cfg.get('emboss_amount',100)),float(cfg.get('emboss_opacity',100)),str(cfg.get('emboss_blend','Normal')),str(cfg.get('emboss_style','Photoshop Emboss')))
        elif node=='br':
            if cfg.get('br',False):
                out=apply_channel_mixer(out,
                    cfg.get('channel_output','灰色'),bool(cfg.get('channel_mono',True)),
                    float(cfg.get('channel_red',40)),float(cfg.get('channel_green',40)),float(cfg.get('channel_blue',20)),float(cfg.get('channel_constant',0)),
                    bool(cfg.get('channel_noise',True)),float(cfg.get('channel_noise_strength',30)),float(cfg.get('channel_noise_radius',0.8)))
        return out

    def _apply_flow_pipeline(self,img,flow):
        np,*_=_deps();out=img.astype(np.float32,copy=True);flow=self._normalize_flow(flow)
        for node in self._flow_exec_order(flow):
            out=self._apply_single_flow_node(out,node,flow)
        return np.clip(out,0,1).astype(np.float32)

    def _prepare_shared_node_dag(self,flows):
        """Compile identical upstream chains into a RAM-only shared DAG.

        v0.9.4.18m also emits per-node reuse audit data.  Signatures contain only
        parameters that the production node actually reads; unrelated legacy or
        output settings can no longer split otherwise identical Base/USM prefixes.
        """
        plans=[];occ=Counter();naive_nodes=0;param_occ=Counter()
        for flow0 in flows:
            flow=self._normalize_flow(flow0);parent=('MASTER',);steps=[]
            for node in self._flow_exec_order(flow):
                if not self._node_enabled(flow,node):continue
                sig=self._preview_node_signature(flow,node);key=(parent,node,sig)
                steps.append((key,node));occ[key]+=1;param_occ[(node,sig)]+=1;naive_nodes+=1;parent=key
            plans.append(steps)
        shared_keys=sum(1 for n in occ.values() if n>1);reusable_uses=sum(max(0,n-1) for n in occ.values())
        reusable_by_node=Counter();shared_keys_by_node=Counter();parameter_reuse_by_node=Counter()
        for key,n in occ.items():
            if n>1:
                node=key[1];shared_keys_by_node[node]+=1;reusable_by_node[node]+=n-1
        for (node,_sig),n in param_occ.items():
            if n>1:parameter_reuse_by_node[node]+=n-1
        meta={'naive_nodes':naive_nodes,'shared_keys':shared_keys,'reusable_uses':reusable_uses,
              'reusable_by_node':dict(reusable_by_node),'shared_keys_by_node':dict(shared_keys_by_node),
              'parameter_reuse_by_node':dict(parameter_reuse_by_node)}
        return plans,occ,meta

    @staticmethod
    def _shared_dag_cache_cap(policy):
        strategy=str((policy or {}).get('strategy','Balanced'))
        share={'Memory Saver':0.08,'Balanced':0.16,'Maximum Performance':0.22}.get(strategy,0.16)
        return max(64*_MIB,int((policy or {}).get('limit_bytes',4*_GIB)*share))

    def _execute_shared_flow(self,master,flow,steps,remaining,cache,cache_state,stats,policy):
        """Execute one output flow while reusing identical results from earlier flows.

        The cache exists for one timelapse Master only. It is RAM-only, bounded by the
        user's RAM Budget, and discarded before the next Master. If pressure is high,
        a shareable node is simply recomputed later instead of spilling to disk.
        """
        np,*_=_deps();out=None
        cap=self._shared_dag_cache_cap(policy)
        limit=max(1,int((policy or {}).get('limit_bytes',4*_GIB)))
        reserve=max(512*_MIB,int((policy or {}).get('system_reserve_bytes',4*_GIB)))
        for key,node in steps:
            cached=cache.get(key)
            if cached is not None:
                out=cached;stats['hits']+=1;stats.setdefault('hits_by_node',Counter())[node]+=1
                continue
            if out is None:
                out=master.astype(np.float32,copy=True)
            perf=getattr(self,'_active_performance_monitor',None)
            if perf is not None:perf.touch('node:'+str(node))
            tn=time.monotonic();out=self._apply_single_flow_node(out,node,flow);dt=time.monotonic()-tn;stats['computes']+=1;stats.setdefault('computes_by_node',Counter())[node]+=1
            if perf is not None:perf.record_node(node,dt)
            # Retain only results that another flow will actually reuse.
            if remaining.get(key,0)>1:
                nb=int(getattr(out,'nbytes',0));_,avail=_system_memory_status();rss=_process_memory_rss()
                safe=(nb>0 and cache_state['bytes']+nb<=cap and rss<limit*0.93 and (avail<=0 or avail>max(512*_MIB,int(reserve*0.70))))
                if safe:
                    cache[key]=out;cache_state['bytes']+=nb;cache_state['peak']=max(cache_state['peak'],cache_state['bytes']);stats['stores']+=1
                else:
                    stats['budget_skips']+=1
        if out is None:out=master.astype(np.float32,copy=True)
        return np.clip(out,0,1).astype(np.float32)

    def _release_shared_flow_refs(self,steps,remaining,cache,cache_state):
        for key,_node in steps:
            if key not in remaining:continue
            remaining[key]-=1
            if remaining[key]<=0:
                remaining.pop(key,None)
                old=cache.pop(key,None)
                if old is not None:
                    cache_state['bytes']=max(0,cache_state['bytes']-int(getattr(old,'nbytes',0)))

    def _preview_node_signature(self,flow,node):
        """Return only parameters that can change this node's pixels.

        This exact signature is shared by preview caching and batch DAG reuse.
        Unused/legacy cfg keys are deliberately excluded so they cannot prevent
        mathematically identical flows from sharing a common prefix.
        """
        cfg=flow['cfg']
        base_keys=(
            'exposure','contrast','highlights','shadows','whites','blacks',
            'temperature','tint','texture','clarity','dehaze','base_curve',
            'hsl_hue','hsl_sat','hsl_lum','cg_shadow_h','cg_shadow_s','cg_mid_h','cg_mid_s','cg_high_h','cg_high_s','cg_balance',
            'detail_sharpen','detail_radius','luma_nr','chroma_nr','opt_distortion','opt_vignette','opt_ca',
            'cal_red_h','cal_red_s','cal_green_h','cal_green_s','cal_blue_h','cal_blue_s','_proxy_scale')
        base_keys=base_keys+tuple(f'mix_{c}_{a}' for c in ('red','orange','yellow','green','aqua','blue','purple','magenta') for a in ('h','s','l'))
        keysets={
            'stretch':('stretch_strength','stretch_black'),
            'basic':base_keys,
            'usm':('usm_amount','usm_radius','usm_threshold','usm_passes'),
            'bgr':('background','bg_radius','bg_strength','curves'),
            'highpass':('hp_radius','hp_amount','hp_mode'),
            'emboss':('emboss_angle','emboss_height','emboss_amount','emboss_opacity','emboss_blend','emboss_style'),
            'br':('channel_output','channel_mono','channel_red','channel_green','channel_blue','channel_constant','channel_noise','channel_noise_strength','channel_noise_radius'),
        }
        vals={k:cfg.get(k) for k in keysets.get(node,())}
        if node=='basic':
            vals['_proxy_scale']=cfg.get('_proxy_scale',1.0)
            vals['base_curves']=flow.get('base_curves',{})
        elif node=='bgr':vals['curves_points']=flow.get('curves',{})
        def canonical(v):
            if isinstance(v,bool) or v is None or isinstance(v,str):return v
            if isinstance(v,(int,float)):return float(v)
            if isinstance(v,(list,tuple)):return [canonical(x) for x in v]
            if isinstance(v,dict):return {str(k):canonical(vv) for k,vv in sorted(v.items(),key=lambda kv:str(kv[0]))}
            try:return float(v)
            except Exception:return repr(v)
        vals=canonical(vals)
        try:return json.dumps(vals,sort_keys=True,ensure_ascii=True,separators=(',',':'))
        except Exception:return repr(vals)

    def _preview_cache_get(self,key):
        v=self.preview_stage_cache.get(key)
        if v is None:return None
        try:
            self.preview_stage_cache_order.remove(key)
        except ValueError:
            pass
        self.preview_stage_cache_order.append(key)
        return v

    def _preview_cache_put(self,key,value):
        self.preview_stage_cache[key]=value
        try:self.preview_stage_cache_order.remove(key)
        except ValueError:pass
        self.preview_stage_cache_order.append(key)
        while len(self.preview_stage_cache_order)>max(4,int(self.preview_cache_limit)):
            old=self.preview_stage_cache_order.pop(0)
            self.preview_stage_cache.pop(old,None)

    def _clear_preview_stage_cache(self):
        self.preview_stage_cache.clear();self.preview_stage_cache_order.clear()

    def _apply_flow_pipeline_preview_cached(self,img,flow,quality,token=None,stop_node=None):
        """Execute a responsive but mathematically faithful node preview.

        Drag/fast passes use the exact production node functions on reduced proxies.
        While the user is actively dragging a node control, the preview may stop after
        that currently edited node to provide immediate visual feedback. Mouse release
        and HQ refinement always render the complete flow. Stale work can abandon at
        node boundaries when a newer preview token supersedes it.
        """
        np,*_=_deps();flow=self._normalize_flow(flow);out=img.astype(np.float32,copy=True)
        order=self._flow_exec_order(flow)
        chain=('base',quality,int(getattr(self,'_preview_reference_serial',0)),tuple(order),out.shape)
        for node in order:
            if token is not None and token != self.preview_token:
                return None
            ns=self._preview_node_signature(flow,node)
            if quality=='hq':
                out=self._apply_single_flow_node(out,node,flow)
            else:
                key=(chain,node,ns)
                cached=self._preview_cache_get(key)
                if cached is not None:
                    out=cached
                else:
                    out=self._apply_single_flow_node(out,node,flow)
                    if token is not None and token != self.preview_token:
                        return None
                    self._preview_cache_put(key,out.astype(np.float32,copy=True))
                chain=(chain,node,ns)
            if stop_node and node==stop_node:
                break
        if token is not None and token != self.preview_token:
            return None
        return np.clip(out,0,1).astype(np.float32)

    def _draw_graph(self):
        if not hasattr(self,'node_canvas'):return
        c=self.node_canvas;c.delete('all');f=self._flow()
        if not f:return
        f=self._normalize_flow(f);cfg=f['cfg'];layout=f['layout'];zoom=max(0.45,min(2.5,float(self.graph_zoom)))
        # Node geometry is expressed in canvas pixels.  Canvas font sizes below
        # use *negative* Tk sizes (pixel units), so Windows DPI scaling cannot
        # enlarge bilingual labels independently of the node rectangle and make
        # the ON/OFF state overlap the second label line.
        node_w=155*zoom;node_h=90*zoom;outline_pad=10*zoom
        title_fs=max(13,int(round(18*zoom)));label_fs=max(10,int(round(13*zoom)));state_fs=max(8,int(round(10*zoom)));small_fs=max(9,int(round(11*zoom)))
        title_font=_ui_font(title_fs,pixel=True);label_font=_ui_font(label_fs,pixel=True);state_font=_ui_font(state_fs,pixel=True);small_font=_ui_font(small_fs,pixel=True)
        minx=25;miny=25;maxx=320;maxy=180;positions=[];self.node_hits=[]
        for key,label in self.NODE_ORDER:
            if key not in f.get('present_nodes',[]):
                continue
            if key not in layout: layout[key]=self._default_node_layout().get(key,(200.0,300.0))
            lx,ly=layout[key];x=lx*zoom;y=ly*zoom;on=self._node_enabled(f,key);positions.append((key,label,x,y,on))
            minx=min(minx,x-node_w/2-outline_pad);maxx=max(maxx,x+node_w/2+outline_pad);miny=min(miny,y-node_h/2-outline_pad);maxy=max(maxy,y+node_h/2+outline_pad)
        bottom_text_y=maxy+55*zoom;maxy=max(maxy,bottom_text_y+50*zoom)
        c.configure(scrollregion=(minx,miny,maxx,maxy))
        centers={key:(x,y) for key,_,x,y,_ in positions}
        # Global pre-stack system node. It is shared by every Flow and is never part
        # of the ordinary editable DAG; clicking it opens the global smoothing settings.
        if 'stack' in centers:
            sx,sy=centers['stack']; sysx=sx-205*zoom; sysy=sy; enabled=_ewb_enabled(self)
            minx=min(minx,sysx-node_w/2-outline_pad);maxx=max(maxx,sysx+node_w/2+outline_pad)
            c.configure(scrollregion=(minx,miny,maxx,maxy))
            c.create_line(sysx+node_w/2,sysy,sx-node_w/2,sy,fill='#58a6ff' if enabled else '#555',width=max(2,int(round(3*zoom))),arrow='last',arrowshape=(10*zoom,12*zoom,4*zoom))
            c.create_rectangle(sysx-node_w/2,sysy-node_h/2,sysx+node_w/2,sysy+node_h/2,fill='#2389f5' if enabled else '#333',outline='#bfe2ff' if enabled else '#777',width=max(1,int(round(2*zoom))))
            c.create_text(sysx,sysy-13*zoom,text='Exposure / WB\n曝光 / 白平衡平滑',fill='#fff' if enabled else '#ccc',font=label_font,justify='center',width=max(20,node_w-12*zoom))
            c.create_text(sysx,sysy+29*zoom,text='ON' if enabled else 'OFF',fill='#d9f0ff' if enabled else '#999',font=state_font)
            self.node_hits.append({'bbox':(sysx-node_w/2-outline_pad,sysy-node_h/2-outline_pad,sysx+node_w/2+outline_pad,sysy+node_h/2+outline_pad),'key':'__ewb_smoothing__','center':(sysx,sysy),'size':(node_w,node_h),'system':True})
        c.create_text(25,25,anchor='nw',fill='#eee',font=title_font,text=f['name'])
        c.create_text(25,56,anchor='nw',fill='#999',font=small_font,text=f'单击编辑 · Shift 拖拽连线 · 右键菜单 · Ctrl+滚轮缩放 · {zoom*100:.0f}%')
        active_edges=set(tuple(e) for e in f.get('edges',[]))
        for a,b in f.get('edges',[]):
            if a not in centers or b not in centers: continue
            sx,sy=centers[a]; ex,ey=centers[b]
            sx=sx+node_w/2; ex=ex-node_w/2
            mx=(sx+ex)/2
            active=(a,b) in active_edges
            color='#58a6ff' if active else '#555555'
            width=max(2,int(round((3 if active else 2)*zoom)))
            c.create_line(sx,sy,mx,sy,mx,ey,ex,ey,fill=color,width=width,arrow='last',arrowshape=(10*zoom,12*zoom,4*zoom),joinstyle='round')
        if getattr(self,'link_preview',None):
            src,(tx,ty)=self.link_preview
            if src in centers:
                sx,sy=centers[src]; sx=sx+node_w/2; mx=(sx+tx)/2
                c.create_line(sx,sy,mx,sy,mx,ty,tx,ty,fill='#f4d03f',width=max(2,int(round(3*zoom))),dash=(6,4),arrow='last',arrowshape=(10*zoom,12*zoom,4*zoom),joinstyle='round')
        for key,label,x,y,on in positions:
            fill='#2389f5' if on else '#333';outline='#bfe2ff' if on else '#777'
            c.create_rectangle(x-node_w/2,y-node_h/2,x+node_w/2,y+node_h/2,fill=fill,outline=outline,width=max(1,int(round(2*zoom))))
            # Reserve two independent vertical zones: bilingual node name above,
            # state below. Stack/Output have no state and remain centered.
            has_state=key not in ('stack','output')
            label_y=y-13*zoom if has_state else y
            c.create_text(x,label_y,text=label,fill='#fff' if on else '#ccc',font=label_font,justify='center',width=max(20,node_w-14*zoom))
            if has_state:
                c.create_text(x,y+29*zoom,text='ON' if on else 'OFF',fill='#d9f0ff' if on else '#999',font=state_font)
            self.node_hits.append({'bbox':(x-node_w/2-outline_pad,y-node_h/2-outline_pad,x+node_w/2+outline_pad,y+node_h/2+outline_pad),'key':key,'center':(x,y),'size':(node_w,node_h)})
        o=f['output']
        if not o.get('export_enabled',True):
            mode_text='不导出 / Disabled'
        elif o.get('save_sequence') and o.get('save_video'):
            mode_text=f'序列 + 视频 / Sequence + Video · {o['sequence_format']} + {o['video_format']}'
        elif o.get('save_sequence'):
            mode_text=f'仅序列 / Sequence Only · {o['sequence_format']}'
        elif o.get('save_video'):
            mode_text=f'仅视频 / Video Only · {o['video_format']}'
        else:
            mode_text='不导出 / Disabled'
        out_desc=f"输出：{mode_text} · {float(o.get('scale_percent',100)):.0f}% · {float(o.get('fps',24)):.2f} fps"
        c.create_text(25,bottom_text_y,anchor='nw',fill='#bbb',font=small_font,text=out_desc)

    def _hit_node(self,x,y):
        for item in self.node_hits:
            x1,y1,x2,y2=item['bbox']
            if x1<=x<=x2 and y1<=y<=y2:
                return item
        return None

    def _edge_creates_cycle(self,flow,src,dst):
        graph={k:[] for k,_ in self.NODE_ORDER}
        for a,b in flow.get('edges',[]):
            graph.setdefault(a,[]).append(b)
        graph.setdefault(src,[]).append(dst)
        stack=[dst]; seen=set()
        while stack:
            n=stack.pop()
            if n==src: return True
            if n in seen: continue
            seen.add(n); stack.extend(graph.get(n,[]))
        return False

    def _toggle_edge(self,src,dst):
        f=self._flow();
        if not f or src==dst or src=='output' or dst=='stack': return
        f=self._normalize_flow(f);before=self._workflow_state();edge=(src,dst)
        if edge in f['edges']:
            f['edges'].remove(edge); label=f'取消连线：{src} → {dst}'
        else:
            if self._edge_creates_cycle(f,src,dst):
                messagebox.showwarning(APP_NAME,'这条连线会形成循环，已阻止。',parent=self); return
            f['edges'].append(edge); label=f'创建连线：{src} → {dst}'
        self._draw_graph(); self._schedule_preview(force=True);self._commit_workflow_history(before,label)

    def _graph_context_menu(self,e):
        self.node_canvas.focus_set()
        x=self.node_canvas.canvasx(e.x); y=self.node_canvas.canvasy(e.y)
        hit=self._hit_node(x,y)
        menu=tk.Menu(self,tearoff=0)
        if hit and hit.get('system'):
            menu.add_command(label='打开曝光 / 白平衡平滑工作区…',command=lambda:_ewb_open_workspace(self))
            menu.tk_popup(e.x_root,e.y_root);return 'break'
        if hit:
            key=hit['key']
            menu.add_command(label=f'编辑节点 / Edit {key}', command=lambda k=key:self._open_node_dialog(k))
            if key not in ('stack','output'):
                menu.add_command(label=f'删除节点 / Delete {key}', command=lambda k=key:self._delete_graph_node(k))
            menu.add_separator()
            menu.add_command(label='自动 U 字形排列 / Arrange U-Shape', command=self._arrange_current_flow_u)
            menu.add_command(label='自动纵向排列 / Arrange Top-to-Bottom', command=self._arrange_current_flow_vertical)
        else:
            flow=self._flow(); present=set(flow.get('present_nodes',[])) if flow else set()
            missing=[(k,label) for k,label in self.NODE_ORDER if k not in present]
            if missing:
                sub=tk.Menu(menu,tearoff=0)
                for k,label in missing:
                    lab=label.replace('\n',' / ')
                    sub.add_command(label=f'新建 {lab}',command=lambda kk=k,xx=x,yy=y:self._add_graph_node(kk,xx,yy))
                menu.add_cascade(label='新建节点 / New Node',menu=sub)
            else:
                menu.add_command(label='没有可新建的节点 / No Hidden Nodes',state='disabled')
            menu.add_separator()
            menu.add_command(label='自动 U 字形排列 / Arrange U-Shape', command=self._arrange_current_flow_u)
            menu.add_command(label='自动纵向排列 / Arrange Top-to-Bottom', command=self._arrange_current_flow_vertical)
        try:
            menu.tk_popup(e.x_root,e.y_root)
        finally:
            try:menu.grab_release()
            except Exception:pass

    def _delete_graph_node(self,key):
        if key in ('stack','output'):return
        flow=self._flow()
        if not flow:return
        before=self._workflow_state();flow=self._normalize_flow(flow)
        if key in flow.get('present_nodes',[]):flow['present_nodes'].remove(key)
        flow['edges']=[(a,b) for a,b in flow.get('edges',[]) if a!=key and b!=key]
        self._draw_graph();self._schedule_preview(force=True);self._commit_workflow_history(before,f'删除节点：{key}')

    def _add_graph_node(self,key,x=None,y=None):
        flow=self._flow()
        if not flow:return
        before=self._workflow_state();flow=self._normalize_flow(flow)
        if key not in flow.get('present_nodes',[]):
            flow['present_nodes'].append(key)
            canonical=[k for k,_ in self.NODE_ORDER]
            flow['present_nodes']=[k for k in canonical if k in flow['present_nodes']]
        if x is not None and y is not None:
            flow['layout'][key]=(float(x)/max(self.graph_zoom,1e-6),float(y)/max(self.graph_zoom,1e-6))
        else:
            self._arrange_u(flow)
        self._draw_graph();self._schedule_preview(force=True);self._commit_workflow_history(before,f'新建节点：{key}')

    def _arrange_current_flow_u(self):
        flow=self._flow()
        if not flow:return
        before=self._workflow_state();self._arrange_u(flow);self._draw_graph();self._schedule_preview(force=True);self._commit_workflow_history(before,'节点 U 字形排列')

    def _arrange_current_flow_vertical(self):
        flow=self._flow()
        if not flow:return
        before=self._workflow_state();self._arrange_vertical(flow);self._draw_graph();self._schedule_preview(force=True);self._commit_workflow_history(before,'节点纵向排列')

    def _graph_press(self,e):
        self.node_canvas.focus_set(); x=self.node_canvas.canvasx(e.x);y=self.node_canvas.canvasy(e.y); hit=self._hit_node(x,y)
        if hit and hit.get('system'):
            self.node_drag={'mode':'system','key':hit['key']};return
        if hit and (e.state & 0x0001):
            self.node_drag={'mode':'link','src':hit['key']}; self.link_preview=(hit['key'],(x,y)); self._draw_graph(); return
        if hit:
            f=self._flow();layout=f.setdefault('layout',self._default_node_layout());lx,ly=layout.get(hit['key'],(x/self.graph_zoom,y/self.graph_zoom))
            self.node_drag={'mode':'node','key':hit['key'],'start_canvas':(x,y),'orig':(float(lx),float(ly)),'moved':False,'history_before':self._workflow_state()}
        else:
            self.node_drag={'mode':'pan','moved':False}; self.node_canvas.scan_mark(e.x,e.y)

    def _graph_drag(self,e):
        if not self.node_drag:return
        mode=self.node_drag.get('mode')
        if mode=='link':
            x=self.node_canvas.canvasx(e.x);y=self.node_canvas.canvasy(e.y); self.link_preview=(self.node_drag['src'],(x,y)); self._draw_graph()
        elif mode=='node':
            x=self.node_canvas.canvasx(e.x);y=self.node_canvas.canvasy(e.y); sx,sy=self.node_drag['start_canvas'];dx=(x-sx)/max(self.graph_zoom,1e-6);dy=(y-sy)/max(self.graph_zoom,1e-6)
            if abs(dx)>1e-3 or abs(dy)>1e-3:self.node_drag['moved']=True
            f=self._flow();layout=f.setdefault('layout',self._default_node_layout());ox,oy=self.node_drag['orig'];layout[self.node_drag['key']]=(ox+dx,oy+dy);self._draw_graph()
        elif mode=='pan':
            self.node_drag['moved']=True; self.node_canvas.scan_dragto(e.x,e.y,gain=1)

    def _graph_release(self,e):
        if not self.node_drag:return
        info=self.node_drag; self.node_drag=None
        if info.get('mode')=='link':
            x=self.node_canvas.canvasx(e.x);y=self.node_canvas.canvasy(e.y); hit=self._hit_node(x,y); self.link_preview=None; self._draw_graph()
            if hit and hit['key']!=info['src']: self._toggle_edge(info['src'],hit['key'])
            return
        if info.get('mode')=='system':
            _ewb_settings_dialog(self);return
        if info.get('mode')=='node':
            if not info.get('moved'): self._open_node_dialog(info['key'])
            else:
                self._draw_graph();self._commit_workflow_history(info.get('history_before',self._workflow_state()),f"移动节点：{info.get('key','node')}")

    def _graph_wheel_linux(self, e, direction):
        # Normal wheel = vertical navigation; Shift = horizontal; Ctrl = zoom.
        state=int(getattr(e,'state',0) or 0)
        if state & 0x0004:
            factor=1.1 if direction>0 else 1/1.1
            self._apply_graph_zoom(factor)
        elif state & 0x0001:
            self.node_canvas.xview_scroll(-3 if direction>0 else 3,'units')
        else:
            self.node_canvas.yview_scroll(-3 if direction>0 else 3,'units')
        return 'break'

    def _graph_wheel(self,e):
        delta=getattr(e,'delta',0)
        if delta==0:return 'break'
        state=int(getattr(e,'state',0) or 0)
        if state & 0x0004:
            factor=1.1 if delta>0 else 1/1.1
            self._apply_graph_zoom(factor)
        elif state & 0x0001:
            self.node_canvas.xview_scroll(_mousewheel_steps(e),'units')
        else:
            self.node_canvas.yview_scroll(_mousewheel_steps(e),'units')
        return 'break'

    def _apply_graph_zoom(self,factor):
        old=self.graph_zoom; new=max(0.45,min(2.5,old*factor))
        if abs(new-old)<1e-6:return
        xv=self.node_canvas.xview();yv=self.node_canvas.yview(); self.graph_zoom=new; self._draw_graph()
        try:self.node_canvas.xview_moveto(xv[0]);self.node_canvas.yview_moveto(yv[0])
        except Exception: pass

    def _open_node_dialog(self,key):
        f=self._flow()
        if not f:return
        self.preview_active_node=key
        before=copy.deepcopy(f);history_before=self._workflow_state()
        d=tk.Toplevel(self);d.title(f'{key} 节点参数 / Node Settings · {f["name"]}');d.geometry('540x760' if key=='basic' else '470x620');d.transient(self);local_history=LocalNodeEditorHistory(self,d,f,f'{key} 节点')
        outer=ttk.Frame(d,padding=10);outer.pack(fill='both',expand=True);body,cv,_scroll_shell=_make_vertical_scroll_area(outer,padding=0)
        cfg=f['cfg']
        committed={'value':False}
        def apply_close():
            committed['value']=True
            self.preview_active_node=None
            self._draw_graph(); self._schedule_preview(force=True); self._commit_workflow_history(history_before,f'应用节点：{key}'); d.destroy()
        def cancel_close():
            self.preview_active_node=None
            if not committed['value']:
                f.clear(); f.update(copy.deepcopy(before)); self._normalize_flow(f)
                self._refresh_flow_list(); self._draw_graph(); self._schedule_preview(force=True)
            d.destroy()
        def add_apply_cancel():
            ttk.Label(body,text='当前节点窗口：Ctrl+Z = 局部撤回，Ctrl+Shift+Z = 局部重做。只有点击“应用”后，这次编辑才会进入主流程的全局 Undo 历史。',foreground='#666',wraplength=430).pack(anchor='w',pady=(12,0))
            bar=ttk.Frame(body); bar.pack(fill='x',pady=(8,2))
            ttk.Button(bar,text='取消 / Cancel',command=cancel_close).pack(side='right',fill='x',expand=True,padx=(5,0))
            ttk.Button(bar,text='应用 / Apply',style='Primary.TButton',command=apply_close).pack(side='right',fill='x',expand=True)
        d.protocol('WM_DELETE_WINDOW',cancel_close)
        if key=='stack':
            ttk.Label(body,text='Stack 节点 / Stack Node：所有输出流程共享的输入节点。',font=_ui_font(11)).pack(anchor='w');ttk.Label(body,text=f'当前模式：{self.mode.get()}\n堆栈方式：{self.stack_method.get()}\n窗口大小：{self.window_size.get()}\n步长：{self.step.get()}\n\n这些参数在主窗口左侧“参考堆栈”区域统一调整。',wraplength=410).pack(anchor='w',pady=8);add_apply_cancel();return
        if key=='output':self._build_output_dialog(body,f,d);add_apply_cancel();return
        if key=='bgr':
            enabled=tk.BooleanVar(value=bool(cfg.get('bgr',False)));ttk.Checkbutton(body,text='启用 BGR 节点 / Enable BGR node',variable=enabled,command=lambda:self._cfgset(f,'bgr',bool(enabled.get()),True)).pack(anchor='w',pady=(0,8))
            bgv=tk.BooleanVar(value=bool(cfg.get('background',False)));ttk.Checkbutton(body,text='启用 Background / 背景抑制',variable=bgv,command=lambda:(self._cfgset(f,'background',bool(bgv.get()),True), self._cfgset(f,'bgr',True if bgv.get() else bool(f['cfg'].get('curves',False)),True))).pack(anchor='w')
            self._dlg_slider(body,f,'bg_radius','Background Radius px',1,500,1);self._dlg_slider(body,f,'bg_strength','Background Strength %',0,200,1)
            cv=tk.BooleanVar(value=bool(cfg.get('curves',False)));ttk.Checkbutton(body,text='启用 Curves / 曲线',variable=cv,command=lambda:(self._cfgset(f,'curves',bool(cv.get()),True), self._cfgset(f,'bgr',True if cv.get() else bool(f['cfg'].get('background',False)),True))).pack(anchor='w',pady=(8,0))
            ttk.Button(body,text='打开 Curves 曲线编辑器',command=lambda:FlowCurveDialog(self,f)).pack(fill='x',pady=(4,0))
            ttk.Label(body,text='BGR = Background + Curves。这个组节点用于背景抑制与曲线处理，但点击后仍可分别调整。',foreground='#666',wraplength=400).pack(anchor='w',pady=(10,0))
            add_apply_cancel();return
        if key=='br':
            enabled=tk.BooleanVar(value=bool(cfg.get('br',False)));ttk.Checkbutton(body,text='启用 BR 节点 / Enable BR node',variable=enabled,command=lambda:(self._cfgset(f,'br',bool(enabled.get()),True), self._cfgset(f,'channel',bool(enabled.get()),True))).pack(anchor='w',pady=(0,8))
            outv=tk.StringVar(value=str(cfg.get('channel_output','灰色')));r=ttk.Frame(body);r.pack(fill='x',pady=4);ttk.Label(r,text='输出通道').pack(side='left');cb=ttk.Combobox(r,textvariable=outv,state='readonly',values=['红色','绿色','蓝色','灰色']);cb.pack(side='right');cb.bind('<<ComboboxSelected>>',lambda e:self._cfgset(f,'channel_output',outv.get(),True))
            mono=tk.BooleanVar(value=bool(cfg.get('channel_mono',True)));ttk.Checkbutton(body,text='单色模式',variable=mono,command=lambda:self._cfgset(f,'channel_mono',bool(mono.get()),True)).pack(anchor='w',pady=2)
            for k,l in [('channel_red','R %'),('channel_green','G %'),('channel_blue','B %'),('channel_constant','常数 %')]:self._dlg_slider(body,f,k,l,-200 if k!='channel_constant' else -100,200 if k!='channel_constant' else 100,1)
            nr=tk.BooleanVar(value=bool(cfg.get('channel_noise',True)));ttk.Checkbutton(body,text='色彩噪声保护',variable=nr,command=lambda:self._cfgset(f,'channel_noise',bool(nr.get()),True)).pack(anchor='w',pady=(5,0));self._dlg_slider(body,f,'channel_noise_strength','噪声保护强度 %',0,100,1);self._dlg_slider(body,f,'channel_noise_radius','噪声保护半径 px',0.1,10,0.1)
            ttk.Label(body,text='BR = Channel Mixer。这里仍然是原本的通道混合器调整界面。',foreground='#666',wraplength=400).pack(anchor='w',pady=(10,0))
            add_apply_cancel();return
        enabled=tk.BooleanVar(value=bool(cfg.get(key,False)));ttk.Checkbutton(body,text=f'启用 {key} 节点 / Enable {key} node',variable=enabled,command=lambda:self._cfgset(f,key,bool(enabled.get()),True)).pack(anchor='w',pady=(0,8))
        if key=='stretch':
            self._dlg_slider(body,f,'stretch_strength','Strength',0.1,500,0.1);self._dlg_slider(body,f,'stretch_black','Black Point',0,0.25,0.0001)
        elif key=='basic':
            ttk.Label(body,text='Base / 基础调色 · Camera Raw-inspired',font=_ui_font(12)).pack(anchor='w',pady=(0,4))
            ttk.Label(body,text='面向堆栈并拉伸后的 TIFF / Float 图像，不调用 Adobe Camera Raw。鼠标滚轮可上下滚动整个面板。',foreground='#666',wraplength=465).pack(anchor='w',pady=(0,8))
            sec=ttk.LabelFrame(body,text='Basic / 基本明暗',padding=7);sec.pack(fill='x',pady=4)
            self._dlg_slider(sec,f,'exposure','Exposure / 曝光 EV',-5,5,0.05)
            for k,l in [('contrast','Contrast / 对比度'),('highlights','Highlights / 高光'),('shadows','Shadows / 阴影'),('whites','Whites / 白色色阶'),('blacks','Blacks / 黑色色阶')]:self._dlg_slider(sec,f,k,l,-100,100,1)
            sec=ttk.LabelFrame(body,text='WB / 白平衡',padding=7);sec.pack(fill='x',pady=4)
            temp_var=self._dlg_slider(sec,f,'temperature','Temperature / 色温',-100,100,1);tint_var=self._dlg_slider(sec,f,'tint','Tint / 色调',-100,100,1)
            ttk.Button(sec,text='Eyedropper / 白平衡吸管：点击后到右侧预览取样',command=lambda:self._activate_wb_eyedropper(f,temp_var,tint_var)).pack(fill='x',pady=(4,0))
            # Base used to synchronously create well over one hundred Tk widgets
            # before Windows could paint the dialog.  Keep Basic and WB immediate,
            # then yield between advanced sections so the panel opens at once.
            loading=ttk.Label(body,text='正在加载高级调色控件…',foreground='#777');loading.pack(anchor='w',pady=8)
            ctx={};jobs=[]
            def add_presence():
                sec=ttk.LabelFrame(body,text='Presence / 质感',padding=7);sec.pack(fill='x',pady=4)
                for k,l in [('texture','Texture / 纹理'),('clarity','Clarity / 清晰度'),('dehaze','Dehaze / 去朦胧')]:self._dlg_slider(sec,f,k,l,-100,100,1)
            def add_curve():
                sec=ttk.LabelFrame(body,text='Curve / 曲线',padding=7);sec.pack(fill='x',pady=4);bcv=tk.BooleanVar(value=bool(cfg.get('base_curve',False)));ttk.Checkbutton(sec,text='启用 Base Curve / 基础曲线',variable=bcv,command=lambda:self._cfgset(f,'base_curve',bool(bcv.get()),True)).pack(anchor='w');ttk.Button(sec,text='打开 Curve 控制点编辑器',command=lambda:BaseCurveDialog(self,f)).pack(fill='x',pady=(4,0))
            def add_hsl():
                sec=ttk.LabelFrame(body,text='HSL / 全局色相·饱和度·明度',padding=7);sec.pack(fill='x',pady=4);self._dlg_slider(sec,f,'hsl_hue','Hue / 色相',-180,180,1);self._dlg_slider(sec,f,'hsl_sat','Saturation / 饱和度',-100,100,1);self._dlg_slider(sec,f,'hsl_lum','Luminance / 明度',-100,100,1)
            def add_mixer():ctx['mixer']=ttk.LabelFrame(body,text='Color Mixer / 颜色混合器',padding=7);ctx['mixer'].pack(fill='x',pady=4)
            def add_mixer_color(cname,clabel):
                sub=ttk.LabelFrame(ctx['mixer'],text=clabel,padding=5);sub.pack(fill='x',pady=2);self._dlg_slider(sub,f,f'mix_{cname}_h','Hue',-100,100,1);self._dlg_slider(sub,f,f'mix_{cname}_s','Saturation',-100,100,1);self._dlg_slider(sub,f,f'mix_{cname}_l','Luminance',-100,100,1)
            def add_grading():
                sec=ttk.LabelFrame(body,text='Color Grading / 色彩分级',padding=7);sec.pack(fill='x',pady=4)
                for name,label in [('shadow','Shadows / 阴影'),('mid','Midtones / 中间调'),('high','Highlights / 高光')]:
                    sub=ttk.LabelFrame(sec,text=label,padding=5);sub.pack(fill='x',pady=2);self._dlg_slider(sub,f,f'cg_{name}_h','Hue / 色相',0,360,1);self._dlg_slider(sub,f,f'cg_{name}_s','Saturation / 饱和度',-100,100,1)
                self._dlg_slider(sec,f,'cg_balance','Balance / 平衡',-100,100,1)
            def add_detail():
                sec=ttk.LabelFrame(body,text='Detail / 细节',padding=7);sec.pack(fill='x',pady=4);self._dlg_slider(sec,f,'detail_sharpen','Sharpen / 锐化',0,200,1);self._dlg_slider(sec,f,'detail_radius','Radius / 半径 px',0.2,10,0.1);self._dlg_slider(sec,f,'luma_nr','Luma NR / 明度降噪',0,100,1);self._dlg_slider(sec,f,'chroma_nr','Chroma NR / 色彩降噪',0,100,1)
            def add_optics():
                sec=ttk.LabelFrame(body,text='Optics / 光学',padding=7);sec.pack(fill='x',pady=4);self._dlg_slider(sec,f,'opt_distortion','Distortion / 畸变',-100,100,1);self._dlg_slider(sec,f,'opt_vignette','Vignette / 暗角',-100,100,1);self._dlg_slider(sec,f,'opt_ca','CA / 色差校正',-100,100,1)
            def add_calibration():
                sec=ttk.LabelFrame(body,text='Calibration / 校准',padding=7);sec.pack(fill='x',pady=4)
                for name,label in [('red','Red Primary / 红原色'),('green','Green Primary / 绿原色'),('blue','Blue Primary / 蓝原色')]:
                    sub=ttk.LabelFrame(sec,text=label,padding=5);sub.pack(fill='x',pady=2);self._dlg_slider(sub,f,f'cal_{name}_h','Hue / 色相',-100,100,1);self._dlg_slider(sub,f,f'cal_{name}_s','Saturation / 饱和度',-100,100,1)
            def finish_base_panel():
                try:loading.destroy()
                except Exception:pass
                ttk.Label(body,text='拖动参数时，主窗口右侧当前流程预览会同步变化；点击“应用”确认，点击“取消”恢复打开节点前的参数。',foreground='#666',wraplength=400).pack(anchor='w',pady=(10,0));add_apply_cancel();_enforce_regular_typography(d)
            jobs.extend([add_presence,add_curve,add_hsl,add_mixer])
            for cname,clabel in [('red','Red / 红'),('orange','Orange / 橙'),('yellow','Yellow / 黄'),('green','Green / 绿'),('aqua','Aqua / 青'),('blue','Blue / 蓝'),('purple','Purple / 紫'),('magenta','Magenta / 洋红')]:jobs.append(lambda c=cname,l=clabel:add_mixer_color(c,l))
            jobs.extend([add_grading,add_detail,add_optics,add_calibration,finish_base_panel])
            def pump_base_widgets():
                if not d.winfo_exists() or not jobs:return
                jobs.pop(0)()
                if jobs:d.after(1,pump_base_widgets)
            d.update_idletasks();d.after_idle(pump_base_widgets);return
        elif key=='usm':self._dlg_slider(body,f,'usm_amount','Amount %',0,500,1);self._dlg_slider(body,f,'usm_radius','Radius px',0.1,250,0.1);self._dlg_slider(body,f,'usm_threshold','Threshold',0,255,1);self._dlg_slider(body,f,'usm_passes','重复次数',1,10,1)
        elif key=='highpass':
            self._dlg_slider(body,f,'hp_radius','Radius px',0.1,250,0.1);self._dlg_slider(body,f,'hp_amount','Opacity %',0,100,1);v=tk.StringVar(value=str(cfg.get('hp_mode','Overlay')));r=ttk.Frame(body);r.pack(fill='x',pady=4);ttk.Label(r,text='Mode').pack(side='left');cb=ttk.Combobox(r,textvariable=v,state='readonly',values=['Overlay','Soft Light','Linear Light']);cb.pack(side='right');cb.bind('<<ComboboxSelected>>',lambda e:self._cfgset(f,'hp_mode',v.get(),True))
        elif key=='emboss':
            sv=tk.StringVar(value=str(cfg.get('emboss_style','Photoshop Emboss')));r=ttk.Frame(body);r.pack(fill='x',pady=4);ttk.Label(r,text='Style / 浮雕类型').pack(side='left');cb=ttk.Combobox(r,textvariable=sv,state='readonly',values=['Photoshop Emboss','Color Emboss','Gray Emboss'],width=18);cb.pack(side='right');cb.bind('<<ComboboxSelected>>',lambda e:self._cfgset(f,'emboss_style',sv.get(),True))
            av=self._dlg_slider(body,f,'emboss_angle','Angle °',-180,180,1)
            dialbox=ttk.Frame(body);dialbox.pack(fill='x',pady=(2,6));ttk.Label(dialbox,text='Angle Dial / 角度圆盘\n拖动方向杆；双击恢复 -128°',foreground='#666').pack(side='left',anchor='w')
            AngleDial(dialbox,av,command=lambda val:(f['cfg'].__setitem__('emboss_angle',float(val)),self._flow_changed(dragging=True)),release_command=lambda val:(f['cfg'].__setitem__('emboss_angle',float(val)),self._flow_changed(force=True)),reset_value=-128.0,size=76).pack(side='right',padx=(8,12))
            self._dlg_slider(body,f,'emboss_height','Height px',1,200,1);self._dlg_slider(body,f,'emboss_amount','Amount %',1,500,1)
            bv=tk.StringVar(value=str(cfg.get('emboss_blend','Normal')));r=ttk.Frame(body);r.pack(fill='x',pady=4);ttk.Label(r,text='Blend Mode / 混合模式').pack(side='left');cb=ttk.Combobox(r,textvariable=bv,state='readonly',values=['Normal','Overlay','Soft Light','Linear Light'],width=18);cb.pack(side='right');cb.bind('<<ComboboxSelected>>',lambda e:self._cfgset(f,'emboss_blend',bv.get(),True))
            self._dlg_slider(body,f,'emboss_opacity','Opacity %',0,100,1)
            ttk.Label(body,text='Photoshop Emboss：更接近 PS 的灰色浮雕基底，并在边缘保留明显原色描迹。\nColor Emboss：保留原图色彩，只把方向性浮雕作用到亮度结构。\nGray Emboss：保留旧版经典中性灰浮雕。',foreground='#666',wraplength=430).pack(anchor='w',pady=(6,0))
        elif key=='channel':
            outv=tk.StringVar(value=str(cfg.get('channel_output','灰色')));r=ttk.Frame(body);r.pack(fill='x',pady=3);ttk.Label(r,text='输出通道').pack(side='left');cb=ttk.Combobox(r,textvariable=outv,state='readonly',values=['灰色','红色','绿色','蓝色']);cb.pack(side='right');cb.bind('<<ComboboxSelected>>',lambda e:self._cfgset(f,'channel_output',outv.get(),True))
            mono=tk.BooleanVar(value=bool(cfg.get('channel_mono',True)));ttk.Checkbutton(body,text='单色',variable=mono,command=lambda:self._cfgset(f,'channel_mono',bool(mono.get()),True)).pack(anchor='w')
            for k,l in [('channel_red','R %'),('channel_green','G %'),('channel_blue','B %'),('channel_constant','常数 %')]:self._dlg_slider(body,f,k,l,-200 if k!='channel_constant' else -100,200 if k!='channel_constant' else 100,1)
            nr=tk.BooleanVar(value=bool(cfg.get('channel_noise',True)));ttk.Checkbutton(body,text='色彩噪声保护',variable=nr,command=lambda:self._cfgset(f,'channel_noise',bool(nr.get()),True)).pack(anchor='w',pady=(5,0));self._dlg_slider(body,f,'channel_noise_strength','噪声保护强度 %',0,100,1);self._dlg_slider(body,f,'channel_noise_radius','噪声保护半径 px',0.1,10,0.1)
        ttk.Label(body,text='拖动参数时，主窗口右侧当前流程预览会同步变化；点击“应用”确认，点击“取消”恢复打开节点前的参数。',foreground='#666',wraplength=400).pack(anchor='w',pady=(10,0))
        add_apply_cancel()

    def _slider_reset_value(self,key,frm,to,current=0.0):
        # Most color/tone controls are neutral at 0. Opacity is an exception:
        # double-click should restore full strength rather than hide the effect.
        if key=='emboss_opacity':
            return 100.0
        if float(frm) <= 0.0 <= float(to):
            return 0.0
        defaults={
            'stretch_strength':8.0,
            'bg_radius':80.0,
            'detail_radius':1.0,
            'usm_radius':2.0,
            'usm_passes':1.0,
            'hp_radius':10.0,
            'emboss_height':1.0,
            'emboss_amount':100.0,
            'channel_noise_radius':0.8,
        }
        val=float(defaults.get(key,current))
        return max(float(frm),min(float(to),val))

    def _dlg_slider(self,parent,flow,key,label,frm,to,res):
        cfg=flow['cfg'];box=ttk.Frame(parent);box.pack(fill='x',pady=3);top=ttk.Frame(box);top.pack(fill='x');ttk.Label(top,text=label).pack(side='left');v=tk.DoubleVar(value=float(cfg.get(key,0)));e=ttk.Entry(top,textvariable=v,width=10,justify='right');e.pack(side='right')
        reset_value=self._slider_reset_value(key,frm,to,float(cfg.get(key,0)))
        def changed(val=None,force=False):
            try:cfg[key]=max(float(frm),min(float(to),float(v.get())))
            except Exception:return
            self._flow_changed(dragging=not force,force=force)
        def reset_slider(ev=None):
            v.set(reset_value)
            cfg[key]=float(reset_value)
            self._flow_changed(force=True)
            self.status.set(f'{label} 已恢复中性值：{reset_value:g}')
            return 'break'
        sc=ttk.Scale(box,from_=frm,to=to,variable=v,command=lambda x:changed());sc.pack(fill='x')
        node_click={'time':0}
        def node_press(ev=None):
            now=int(getattr(ev,'time',0) or 0)
            if now and node_click['time'] and 0 < now-node_click['time'] <= 420:
                node_click['time']=0
                return reset_slider(ev)
            node_click['time']=now
        sc.bind('<ButtonPress-1>',node_press,add='+')
        sc.bind('<ButtonRelease-1>',lambda ev:changed(force=True))
        sc.bind('<Double-Button-1>',reset_slider,add='+')
        e.bind('<Return>',lambda ev:(changed(force=True),'break')[1]);e.bind('<FocusOut>',lambda ev:changed(force=True))
        return v
    def _cfgset(self,flow,key,value,force=False):
        flow['cfg'][key]=value
        if key in ('background','curves') and bool(value): flow['cfg']['bgr']=True
        if key in ('background','curves') and not flow['cfg'].get('background',False) and not flow['cfg'].get('curves',False): flow['cfg']['bgr']=False
        if key=='bgr' and not bool(value):
            pass
        if key in ('channel','br'): flow['cfg']['br']=bool(flow['cfg'].get('br',False) or (key=='channel' and bool(value))) if key=='channel' and bool(value) else bool(flow['cfg'].get('br',False) if key=='channel' else value)
        if key=='br': flow['cfg']['channel']=bool(value)
        if key=='channel' and bool(value): flow['cfg']['br']=True
        self._flow_changed(force=force);self._draw_graph()

    def _get_output_mode(self,flow):
        o=flow['output']
        if not o.get('export_enabled',True): return '禁用导出'
        seq=bool(o.get('save_sequence',False)); vid=bool(o.get('save_video',False))
        if seq and vid: return '同时保存序列+视频'
        if seq: return '只保存序列'
        if vid: return '只保存视频'
        return '禁用导出'

    def _set_output_mode(self,flow,mode):
        o=flow['output']
        if mode=='只保存序列':
            o['export_enabled']=True; o['save_sequence']=True; o['save_video']=False
        elif mode=='只保存视频':
            o['export_enabled']=True; o['save_sequence']=False; o['save_video']=True
        elif mode=='同时保存序列+视频':
            o['export_enabled']=True; o['save_sequence']=True; o['save_video']=True
        else:
            o['export_enabled']=False; o['save_sequence']=False; o['save_video']=False
        self._flow_changed(force=True); self._refresh_flow_list()

    def _build_output_dialog(self,body,flow,dialog):
        o=flow['output'];ttk.Label(body,text='Output 节点 / Output Node',font=_ui_font(11)).pack(anchor='w',pady=(0,7))
        if not o.get('export_enabled',True): mode='禁用导出'
        elif o.get('save_sequence') and o.get('save_video'): mode='同时保存序列+视频'
        elif o.get('save_sequence'): mode='只保存序列'
        elif o.get('save_video'): mode='只保存视频'
        else: mode='禁用导出'
        mv=tk.StringVar(value=mode);r=ttk.Frame(body);r.pack(fill='x',pady=4);ttk.Label(r,text='输出模式 / Export Mode').pack(side='left');cb=ttk.Combobox(r,textvariable=mv,state='readonly',values=['禁用导出','只保存序列','只保存视频','同时保存序列+视频']);cb.pack(side='right')
        def set_mode(e=None):
            m=mv.get();o['export_enabled']=m!='禁用导出';o['save_sequence']=m in ('只保存序列','同时保存序列+视频');o['save_video']=m in ('只保存视频','同时保存序列+视频');self._flow_changed(force=True);self._refresh_flow_list()
        cb.bind('<<ComboboxSelected>>',set_mode)
        self._output_combo(body,flow,'sequence_format','序列格式 / Sequence Format',['PNG 8-bit','JPEG','TIFF 16-bit','TIFF 32-bit Float']);self._output_combo(body,flow,'video_format','视频格式 / Video Format',['MP4 H.264','MOV H.264','MOV ProRes','GIF'])
        delv=tk.BooleanVar(value=bool(o.get('delete_sequence_after_video_only',True)));ttk.Checkbutton(body,text='视频编码成功后：自动删除临时 sequence（仅“只保存视频”时）',variable=delv,command=lambda:self._oset(flow,'delete_sequence_after_video_only',bool(delv.get()))).pack(anchor='w',pady=(6,2))
        ttk.Label(body,text='取消勾选后，“只保存视频”模式也会保留 sequence，便于手工重编码或后续复用。',foreground='#666',wraplength=410).pack(anchor='w',pady=(0,4))
        self._output_entry(body,flow,'fps','FPS',float);self._output_entry(body,flow,'scale_percent','保持比例缩放 %',float);self._output_entry(body,flow,'name_template','文件夹/视频命名模板',str)
        name=tk.StringVar(value=flow['name']);r=ttk.Frame(body);r.pack(fill='x',pady=4);ttk.Label(r,text='流程名称').pack(side='left');en=ttk.Entry(r,textvariable=name,width=24);en.pack(side='right');en.bind('<FocusOut>',lambda e:self._rename_flow(flow,name.get()));en.bind('<Return>',lambda e:(self._rename_flow(flow,name.get()),'break')[1])
        ttk.Label(body,text='缩放 50% = 宽和高都缩为原来的 50%，画面比例保持不变。使用高质量 Lanczos/INTER_AREA 缩放，适合原始分辨率过大时减小序列和视频体积。\n\n命名模板可使用：{index:02d}、{name}、{method}。',foreground='#666',wraplength=410).pack(anchor='w',pady=(10,0))
    def _output_combo(self,parent,flow,key,label,values):
        o=flow['output'];v=tk.StringVar(value=str(o.get(key,values[0])));r=ttk.Frame(parent);r.pack(fill='x',pady=3);ttk.Label(r,text=label).pack(side='left');cb=ttk.Combobox(r,textvariable=v,state='readonly',values=values);cb.pack(side='right');cb.bind('<<ComboboxSelected>>',lambda e:self._oset(flow,key,v.get()))
    def _output_entry(self,parent,flow,key,label,typ):
        o=flow['output'];v=tk.StringVar(value=str(o.get(key,'')));r=ttk.Frame(parent);r.pack(fill='x',pady=3);ttk.Label(r,text=label).pack(side='left');e=ttk.Entry(r,textvariable=v,width=22,justify='right');e.pack(side='right')
        def commit(ev=None):
            try:val=typ(v.get());self._oset(flow,key,val)
            except Exception:v.set(str(o.get(key,'')))
            return 'break' if ev and getattr(ev,'keysym','')=='Return' else None
        e.bind('<Return>',commit);e.bind('<FocusOut>',commit)
    def _oset(self,flow,key,val):flow['output'][key]=val;self._flow_changed(force=True);self._refresh_flow_list()
    def _rename_flow(self,flow,name):flow['name']=str(name).strip() or '未命名流程';self._refresh_flow_list();self._draw_graph();self._schedule_preview(force=True)

    def _flow_changed(self,dragging=False,force=False):
        # Redrawing the complete HiDPI node canvas on every Scale callback creates
        # avoidable UI latency. Parameter drags only need the preview; redraw on release.
        if not dragging:self._draw_graph()
        self._schedule_preview(dragging=dragging,force=force)

    def _groups(self):
        n=len(self.app.files);step=max(1,int(self.step.get() or 1));mode=self.mode.get()
        if n<1:return []
        if mode.startswith('累计'):
            ends=list(range(1,n+1,step));
            if not ends or ends[-1]!=n:ends.append(n)
            return [list(range(e)) for e in ends]
        if mode.startswith('逐帧剔除'):return [[j for j in range(n) if j!=i] for i in range(0,n,step)] if n>=2 else []
        w=max(1,min(n,int(self.window_size.get() or 1)));return [list(range(st,st+w)) for st in range(0,n-w+1,step)]
    def _update_summary(self):
        groups=self._groups();mode=self.mode.get()
        if mode.startswith('滑动'):desc='最适合观察冰晕随时间变化：例如窗口 15，则依次堆栈 1–15、2–16、3–17……'
        elif mode.startswith('中心'):desc='固定窗口，但把每个结果理解为窗口中央时刻的状态。'
        elif mode.startswith('累计'):desc='观察信号逐渐显现：1；1–2；1–3；……直到全部照片。不是普通时间变化。'
        else:desc='贡献分析：每次从全部照片中剔除一张。用于判断单帧对总结果的影响。'
        method='maximum' if self.stack_method.get().startswith('最大值') else 'mean'
        engine=_timelapse_stack_engine_name(self,method)
        self.mode_desc.set(desc);self.summary.set(f'预计输出：{len(groups)} 帧 · {engine}');self.preview_spin.configure(to=max(1,len(groups)));self.preview_index.set(min(max(1,int(self.preview_index.get() or 1)),max(1,len(groups))));self.reference_master=None;self.preview_title.set('时间窗口已改变，请重新生成参考堆栈') if hasattr(self,'preview_title') else None
    def _ref_lum(self):
        if not self.normalize.get() or not self.app.files:return None
        return robust_luminance(read_linear_rgb(self.app.files[0]))
    def _decode(self,i,ref=None):
        img=read_linear_rgb(self.app.files[i])
        img=_ewb_apply_to_frame(self,img,i)
        if ref is not None:
            lum=robust_luminance(img)
            if lum>1e-8:img=img*(ref/lum)
        return img
    def _stack_group(self,indices,method,ref=None):
        np,*_=_deps();master=None
        for k,i in enumerate(indices,1):
            if self.cancel_event.is_set():raise InterruptedError('cancelled')
            img=self._decode(i,ref).astype(np.float32,copy=False)
            if master is None:master=img.copy()
            elif method=='maximum':np.maximum(master,img,out=master)
            else:master+=(img-master)/float(k)
        return master
    def generate_reference(self):
        if self.worker and self.worker.is_alive():return
        if not _ewb_require_analysis(self):return
        groups=self._groups()
        if not groups:return
        idx=max(1,min(len(groups),int(self.preview_index.get() or 1)))-1;method='maximum' if self.stack_method.get().startswith('最大值') else 'mean';self.status.set(f'正在生成参考堆栈 {idx+1}/{len(groups)}…');self.preview_title.set('正在生成参考堆栈…')
        def work():
            try:self.queue.put(('n_reference',(self._stack_group(groups[idx],method,self._ref_lum()),idx,groups[idx])))
            except Exception as e:self.queue.put(('n_error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()

    def _base_curve_hist_source(self,flow):
        if self.reference_proxy_drag is None:return None
        try:
            tf=copy.deepcopy(flow);tf=self._normalize_flow(tf);cfg=scale_timelapse_cfg_for_proxy(tf['cfg'],self.reference_proxy_drag_scale);out=self.reference_proxy_drag.copy()
            out=apply_basic(out,cfg.get('exposure',0),cfg.get('contrast',0),cfg.get('highlights',0),cfg.get('shadows',0),cfg.get('whites',0),cfg.get('blacks',0),0,0,0,0)
            out=apply_white_balance_post(out,cfg.get('temperature',0),cfg.get('tint',0))
            out=apply_presence_advanced(out,cfg.get('texture',0),cfg.get('clarity',0),cfg.get('dehaze',0),cfg.get('_proxy_scale',1))
            return out
        except Exception:return self.reference_proxy_drag

    def _activate_wb_eyedropper(self,flow,temp_var,tint_var):
        self.wb_pick_context={'flow':flow,'temp_var':temp_var,'tint_var':tint_var}
        self.status.set('WB Eyedropper：请在右侧实时预览中点击应为中性灰/白的区域。')
        try:self.preview_canvas.configure(cursor='crosshair')
        except Exception:pass

    def _preview_click(self,e):
        ctx=self.wb_pick_context
        if not ctx or self.last_preview_image is None or not self.preview_display_rect:return
        x0,y0,nw,nh=self.preview_display_rect
        if not(x0<=e.x<x0+nw and y0<=e.y<y0+nh):return
        np,*_=_deps();img=self.last_preview_image;h,w=img.shape[:2];ix=int((e.x-x0)/max(nw,1)*w);iy=int((e.y-y0)/max(nh,1)*h);rr=max(1,int(min(h,w)*0.006));patch=img[max(0,iy-rr):min(h,iy+rr+1),max(0,ix-rr):min(w,ix+rr+1)]
        rgb=np.median(np.clip(patch,1e-4,1),axis=(0,1));r,g,b=[float(v) for v in rgb]
        import math
        temp=max(-100,min(100,-math.log(max(r,1e-5)/max(b,1e-5))/0.70*100.0));tint=max(-100,min(100,(math.log(max(g,1e-5))-0.5*(math.log(max(r,1e-5))+math.log(max(b,1e-5))))/0.30*100.0))
        flow=ctx['flow'];flow['cfg']['temperature']=temp;flow['cfg']['tint']=tint
        try:ctx['temp_var'].set(temp);ctx['tint_var'].set(tint)
        except Exception:pass
        self.wb_pick_context=None
        try:self.preview_canvas.configure(cursor='')
        except Exception:pass
        self.status.set(f'白平衡吸管完成：Temperature {temp:.1f} / Tint {tint:.1f}');self._flow_changed(force=True)

    def _curve_hist_source(self,flow):
        if self.reference_proxy_drag is None:return None
        try:
            tf=copy.deepcopy(flow); tf=self._normalize_flow(tf); tf['cfg']=scale_timelapse_cfg_for_proxy(tf['cfg'],self.reference_proxy_drag_scale)
            out=self.reference_proxy_drag.copy()
            for node in self._flow_exec_order(tf):
                if node=='bgr':
                    if tf['cfg'].get('background',False): out=background_suppression(out,float(tf['cfg'].get('bg_radius',80)),float(tf['cfg'].get('bg_strength',100)))
                    return out
                if node=='stretch': out=apply_asinh_stretch(out,float(tf['cfg'].get('stretch_strength',8)),float(tf['cfg'].get('stretch_black',0)))
                elif node=='basic': out=apply_basic_adjust(out,float(tf['cfg'].get('exposure',0)),float(tf['cfg'].get('contrast',0)),float(tf['cfg'].get('highlights',0)),float(tf['cfg'].get('shadows',0)),float(tf['cfg'].get('whites',0)),float(tf['cfg'].get('blacks',0)),float(tf['cfg'].get('clarity',0)),float(tf['cfg'].get('dehaze',0)),float(tf['cfg'].get('vibrance',0)),float(tf['cfg'].get('saturation',0)))
                elif node=='usm':
                    for _ in range(max(1,min(10,int(tf['cfg'].get('usm_passes',1))))): out=apply_usm(out,float(tf['cfg'].get('usm_amount',100)),float(tf['cfg'].get('usm_radius',2)),float(tf['cfg'].get('usm_threshold',0)))
            return out
        except Exception:return self.reference_proxy_drag

    def _queue_preview_quality(self,quality,delay=1):
        self.preview_quality=str(quality)
        try:
            if self.preview_after:self.after_cancel(self.preview_after)
        except Exception:pass
        self.preview_after=self.after(max(1,int(delay)),self._launch_preview)

    def _schedule_preview(self,force=False,dragging=False):
        if self.reference_master is None:return
        try:
            if self.preview_hq_after:self.after_cancel(self.preview_hq_after)
        except Exception:pass
        self.preview_hq_after=None
        if dragging:
            # Collapse the flood of native Scale callbacks into the newest state.
            self._queue_preview_quality('drag',6)
            return
        if force:
            self._queue_preview_quality('fast',1)
            self.preview_hq_after=self.after(int(self.preview_hq_idle_ms),self._request_hq_refinement)
            return
        self._queue_preview_quality('fast',18)

    def _request_hq_refinement(self):
        self.preview_hq_after=None
        if self.reference_master is None:return
        # HQ is idle-only. Interactive work has strict priority.
        if self.preview_interactive_running or self.preview_pending:
            self.preview_hq_after=self.after(250,self._request_hq_refinement)
            return
        if self.preview_hq_running:return
        self._queue_preview_quality('hq',1)

    def _launch_preview(self):
        self.preview_after=None
        if self.reference_master is None:return
        q=self.preview_quality;interactive=q in ('drag','fast')
        if interactive:
            if self.preview_interactive_running:
                self.preview_pending=True;self.preview_pending_quality=q
                return
        else:
            if self.preview_hq_running or self.preview_interactive_running:
                self.preview_hq_after=self.after(250,self._request_hq_refinement)
                return
        if q=='drag' and self.reference_proxy_drag is not None:base=self.reference_proxy_drag;scale=self.reference_proxy_drag_scale
        elif q=='hq' and self.reference_proxy_hq is not None:base=self.reference_proxy_hq;scale=self.reference_proxy_hq_scale
        elif self.reference_proxy_fast is not None:base=self.reference_proxy_fast;scale=self.reference_proxy_fast_scale
        else:base=self.reference_master;scale=1
        f=self._flow()
        if not f:return
        cfg=scale_timelapse_cfg_for_proxy(copy.deepcopy(f['cfg']),scale);curves=copy.deepcopy(f['curves'])
        # A new interactive request supersedes any older HQ token. The older HQ
        # worker will drop out at the next node boundary and its result is ignored.
        self.preview_token+=1;token=self.preview_token;name=f['name']
        if interactive:self.preview_interactive_running=True
        else:self.preview_hq_running=True
        self.preview_running=self.preview_interactive_running or self.preview_hq_running
        qname={'drag':'即时预览','fast':'快速预览','hq':'高精度预览'}.get(q,q)
        self.status.set(f'正在{qname}：'+name)
        active_stop=self.preview_active_node if q=='drag' else None
        def work():
            try:
                tf=copy.deepcopy(f);tf['cfg']=cfg;tf['curves']=curves
                if not self._flow_exec_order(tf):
                    self.queue.put(('n_preview_status',(token,name,q,'当前没有从 Stack / 堆栈 连到 Output / 输出 的有效路径。')))
                    return
                out=self._apply_flow_pipeline_preview_cached(base,tf,q,token=token,stop_node=active_stop)
                if out is None:self.queue.put(('n_preview_cancelled',(token,name,q)))
                else:self.queue.put(('n_preview',(token,out,name,q)))
            except Exception as e:self.queue.put(('n_error',str(e)+'\n\n'+traceback.format_exc(limit=3)))
        threading.Thread(target=work,daemon=True).start()
    def _preview_current_scale(self):
        img=getattr(self,'last_preview_image',None)
        if img is None:return max(0.01,float(getattr(self,'preview_zoom',1.0)))
        h,w=img.shape[:2];c=self.preview_canvas;W=max(c.winfo_width(),1);H=max(c.winfo_height(),1);fit=min(W/max(w,1),H/max(h,1))
        return fit if getattr(self,'preview_fit_mode',True) else max(0.01,float(getattr(self,'preview_zoom',1.0)))
    def _preview_update_zoom_text(self,scale=None):
        if not hasattr(self,'preview_zoom_text'):return
        if getattr(self,'preview_fit_mode',True):self.preview_zoom_text.set('Fit')
        else:
            sc=self._preview_current_scale() if scale is None else float(scale);self.preview_zoom_text.set(f'{sc*100:.0f}%')
    def _preview_zoom_wheel(self,e):
        try:self._preview_zoom_step(1 if getattr(e,'delta',0)>0 else -1,getattr(e,'x',None),getattr(e,'y',None))
        except Exception:pass
        return 'break'
    def _preview_zoom_wheel_linux(self,e,direction):self._preview_zoom_step(direction,getattr(e,'x',None),getattr(e,'y',None));return 'break'
    def _preview_set_zoom(self,scale):
        old=self._preview_current_scale();new=max(0.05,min(20.0,float(scale)));self._preview_adjust_pan_for_zoom(old,new,None,None);self.preview_zoom=new;self.preview_fit_mode=False;self._preview_update_zoom_text(new);self._preview_redraw();self.preview_canvas.focus_set();return 'break'
    def _preview_zoom_step(self,direction,x=None,y=None):
        old=self._preview_current_scale();factor=1.12 if direction>0 else 1/1.12;new=max(0.05,min(20.0,old*factor))
        if abs(new-old)<1e-9:return
        self._preview_adjust_pan_for_zoom(old,new,x,y);self.preview_zoom=new;self.preview_fit_mode=False;self._preview_update_zoom_text(new);self._preview_redraw()
        try:self.status.set(f'实时预览缩放：{new*100:.0f}% · Z 回到 Fit')
        except Exception:pass
    def _preview_adjust_pan_for_zoom(self,old_scale,new_scale,x=None,y=None):
        try:
            c=self.preview_canvas;cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];mx=cw/2 if x is None else float(x);my=ch/2 if y is None else float(y);rx=mx-(cw/2+px);ry=my-(ch/2+py);ratio=new_scale/max(old_scale,1e-9);self.preview_pan=[mx-cw/2-rx*ratio,my-ch/2-ry*ratio]
        except Exception:self.preview_pan=[0.0,0.0]
    def _preview_mouse_press(self,e):
        self.preview_canvas.focus_set()
        if self.wb_pick_context is not None:
            self._preview_click(e);self.preview_pan_anchor=None;return 'break'
        if getattr(self,'preview_fit_mode',True):self.preview_pan_anchor=None;return 'break'
        self.preview_pan_anchor=(float(e.x),float(e.y),float(self.preview_pan[0]),float(self.preview_pan[1]));return 'break'
    def _preview_pan_drag(self,e):
        if self.wb_pick_context is not None or not self.preview_pan_anchor:return 'break'
        x0,y0,px0,py0=self.preview_pan_anchor
        self.preview_pan=[px0+float(e.x)-x0,py0+float(e.y)-y0]
        self._preview_move_canvas_image_fast()
        return 'break'

    def _preview_move_canvas_image_fast(self):
        try:
            c=self.preview_canvas;item=getattr(self,'preview_image_item',None)
            if not item:return
            W=max(c.winfo_width(),1);H=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];cx=W/2+px;cy=H/2+py
            c.coords(item,int(cx),int(cy))
            rect=getattr(self,'preview_display_rect',None)
            if rect:
                _,_,nw,nh=rect;self.preview_display_rect=(int(cx-nw/2),int(cy-nh/2),nw,nh)
        except Exception:pass
    def _preview_pan_end(self,e):self.preview_pan_anchor=None;return 'break'
    def _preview_fit(self):
        self.preview_fit_mode=True;self.preview_pan=[0.0,0.0];self._preview_update_zoom_text();self._preview_redraw();self.preview_canvas.focus_set()
        try:self.status.set('实时预览已回到 Fit')
        except Exception:pass
        return 'break'
    def _preview_redraw(self):
        img=getattr(self,'last_preview_image',None)
        if img is not None:self._show_preview(img)
    def _show_preview(self,img):
        try:
            np,_,Image,ImageTk,*_=_deps();c=self.preview_canvas;W=max(c.winfo_width(),200);H=max(c.winfo_height(),200);h,w=img.shape[:2];fit=min(W/max(w,1),H/max(h,1));sc=fit if getattr(self,'preview_fit_mode',True) else max(0.05,float(getattr(self,'preview_zoom',1.0)));nw=max(1,int(w*sc));nh=max(1,int(h*sc))
            src_key=(id(img),h,w)
            if getattr(self,'_preview_pil_source_key',None)!=src_key:
                self._preview_pil_source=Image.fromarray(np.round(np.clip(img,0,1)*255).astype(np.uint8),'RGB');self._preview_pil_source_key=src_key
            src=self._preview_pil_source;pil=src if (nw,nh)==(w,h) else src.resize((nw,nh),Image.Resampling.LANCZOS)
            self.preview_photo=ImageTk.PhotoImage(pil);c.delete('all');px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];cx=W/2+px;cy=H/2+py;self.preview_image_item=c.create_image(int(cx),int(cy),image=self.preview_photo,anchor='center',tags=('preview_image',));self.last_preview_image=img;self.preview_display_rect=(int(cx-nw//2),int(cy-nh//2),nw,nh);self._preview_update_zoom_text(sc);c.create_text(10,10,anchor='nw',fill='#eeeeee',font=_ui_font(9),text=('Fit' if getattr(self,'preview_fit_mode',True) else f'{sc*100:.0f}%')+' · 滚轮缩放 · 拖拽平移 · Z Fit',tags=('preview_overlay',))
        except Exception as e:self.status.set('预览显示失败：'+str(e))

    def _preset_payload(self,f):
        f=self._normalize_flow(copy.deepcopy(f))
        return {'format':'IceHaloStackFlowPreset','version':5,'name':f['name'],'cfg':copy.deepcopy(f['cfg']),'curves':copy.deepcopy(f['curves']),'base_curves':copy.deepcopy(f.get('base_curves',{})),'present_nodes':copy.deepcopy(f.get('present_nodes',[k for k,_ in self.NODE_ORDER])),'layout':copy.deepcopy(f.get('layout',self._default_node_layout())),'edges':copy.deepcopy(f.get('edges',self._default_edges(f.get('present_nodes',[k for k,_ in self.NODE_ORDER])))),'output':copy.deepcopy(f['output'])}
    def _flow_from_payload(self,data):
        if not isinstance(data,dict) or data.get('format')!='IceHaloStackFlowPreset':raise ValueError('不是有效的 IceHaloStack 流程预设。')
        f=self._new_flow(str(data.get('name','导入流程')));f['cfg'].update(data.get('cfg',{}));f['curves']=data.get('curves',f['curves']);f['base_curves']=data.get('base_curves',f.get('base_curves',{}));f['present_nodes']=data.get('present_nodes',f.get('present_nodes',[k for k,_ in self.NODE_ORDER]));f['layout']=data.get('layout',f.get('layout',self._default_node_layout()));f['edges']=data.get('edges',f.get('edges',self._default_edges(f.get('present_nodes',[k for k,_ in self.NODE_ORDER]))));f['output'].update(data.get('output',{}));return self._normalize_flow(f)
    def _save_preset(self):
        f=self._flow();
        if not f:return
        path=filedialog.asksaveasfilename(parent=self,title='保存流程预设',defaultextension='.ihspreset',filetypes=[('IceHaloStack 流程预设','*.ihspreset'),('JSON','*.json')],initialfile=self._safe_name(f['name'])+'.ihspreset')
        if not path:return
        Path(path).write_text(json.dumps(self._preset_payload(f),ensure_ascii=False,indent=2),encoding='utf-8');self.status.set('已保存流程预设：'+path)
    def _load_preset(self):
        path=filedialog.askopenfilename(parent=self,title='加载流程预设为新流程',filetypes=[('IceHaloStack 流程预设','*.ihspreset *.json'),('所有文件','*.*')])
        if not path:return
        try:
            before=self._workflow_state();self.flows.append(self._flow_from_payload(json.loads(Path(path).read_text(encoding='utf-8'))));self.selected_flow.set(len(self.flows)-1);self._refresh_flow_list();self._schedule_preview(force=True);self._commit_workflow_history(before,'加载流程预设')
        except Exception as e:messagebox.showerror(APP_NAME,'加载预设失败：\n'+str(e),parent=self)
    def _batch_import_presets(self):
        paths=filedialog.askopenfilenames(parent=self,title='批量导入流程预设',filetypes=[('IceHaloStack 流程预设','*.ihspreset *.json'),('所有文件','*.*')])
        if not paths:return
        before=self._workflow_state();ok=0;errors=[]
        for path in paths:
            try:self.flows.append(self._flow_from_payload(json.loads(Path(path).read_text(encoding='utf-8'))));ok+=1
            except Exception as e:errors.append(f'{Path(path).name}: {e}')
        if ok:self.selected_flow.set(len(self.flows)-1);self._refresh_flow_list();self._schedule_preview(force=True);self._commit_workflow_history(before,f'批量导入 {ok} 个流程预设')
        msg=f'成功导入 {ok} 个流程预设。'
        if errors:msg+='\n\n失败：\n'+'\n'.join(errors[:10])
        messagebox.showinfo(APP_NAME,msg,parent=self)
    def _safe_name(self,name):
        bad='<>:"/\\|?*';t=''.join('_' if c in bad else c for c in str(name).strip());return t or 'workflow'
    def _format_name(self,f,index,method):
        tpl=str(f['output'].get('name_template','{index:02d}_{name}'));name=self._safe_name(f['name'])
        try:return self._safe_name(tpl.format(index=index,name=name,method=method))
        except Exception:return f'{index:02d}_{name}'
    def _choose_output(self):
        p=filedialog.askdirectory(parent=self,title='选择延时输出目录')
        if p:self.output_folder.set(p)

    @staticmethod
    def _format_elapsed(seconds):
        total=max(0,int(seconds))
        hours,rem=divmod(total,3600);minutes,secs=divmod(rem,60)
        return f'{hours:02d}:{minutes:02d}:{secs:02d}'

    def _refresh_elapsed_text(self):
        if self.batch_started_at is not None:
            self.batch_elapsed_seconds=max(0.0,time.monotonic()-self.batch_started_at)
        self.elapsed_text.set('运行时间 / Elapsed：'+self._format_elapsed(self.batch_elapsed_seconds))

    def _elapsed_tick(self):
        self._elapsed_after_id=None
        if self.batch_started_at is None:return
        self._refresh_elapsed_text()
        try:
            if self.winfo_exists():self._elapsed_after_id=self.after(250,self._elapsed_tick)
        except Exception:pass

    def _start_elapsed_timer(self):
        if self._elapsed_after_id is not None:
            try:self.after_cancel(self._elapsed_after_id)
            except Exception:pass
            self._elapsed_after_id=None
        self.batch_elapsed_seconds=0.0;self.batch_started_at=time.monotonic();self._refresh_elapsed_text();self._elapsed_after_id=self.after(250,self._elapsed_tick)

    def _stop_elapsed_timer(self):
        if self.batch_started_at is not None:self.batch_elapsed_seconds=max(0.0,time.monotonic()-self.batch_started_at)
        self.batch_started_at=None
        if self._elapsed_after_id is not None:
            try:self.after_cancel(self._elapsed_after_id)
            except Exception:pass
            self._elapsed_after_id=None
        self._refresh_elapsed_text()
        return self._format_elapsed(self.batch_elapsed_seconds)

    def _iter_masters(self,groups,method,ref):
        # v0.9.4.18a: use the same optimized engine as traditional timelapse.
        # Masters remain RAM-only and are consumed immediately by enabled flows.
        yield from _iter_optimized_timelapse_masters(self,groups,method,ref)
    def start_batch(self):
        if self.worker and self.worker.is_alive():return
        if not _ewb_require_analysis(self):return
        flows=[copy.deepcopy(f) for f in self.flows if f['output'].get('export_enabled',True) and (f['output'].get('save_sequence',False) or f['output'].get('save_video',False))]
        if not flows:messagebox.showwarning(APP_NAME,'没有可导出的流程。请至少在一个流程的 Output 节点中启用序列或视频输出。',parent=self);return
        groups=self._groups()
        if not groups:messagebox.showwarning(APP_NAME,'当前设置没有产生可导出的堆栈帧，请检查输入序列、窗口大小和步长。',parent=self);return
        try:
            base=Path(self.output_folder.get()).expanduser();base.mkdir(parents=True,exist_ok=True)
            probe=base/'.icehalostack_write_test';probe.write_bytes(b'');probe.unlink()
        except Exception as exc:
            messagebox.showerror(APP_NAME,f'输出文件夹不可写：\n{exc}',parent=self);return
        method='maximum' if self.stack_method.get().startswith('最大值') else 'mean';self.cancel_event.clear();self._last_performance_snapshot=None;self.performance_monitor_text.set('Performance：准备启动…');self.stability_text.set('Stability：Starting');self.start_btn.configure(state='disabled');self.cancel_btn.configure(state='normal');self.progress.set(0);self.processing_progress.set(0);self.writing_progress.set(0);self.output_pipeline_text.set('写入：准备启动…');self.status.set('准备批量导出…');self._start_elapsed_timer()
        self._active_memory_policy=_timelapse_memory_policy_snapshot(self)
        self.memory_dag_text.set('Shared Node DAG：准备分析流程公共节点…')
        st={'flows':flows,'groups':groups,'base':base,'method':method,'save_performance_report':bool(self.performance_save_report.get()),'exposure_wb_smoothing':_ewb_config_snapshot(self)};self.worker=threading.Thread(target=self._batch_worker,args=(st,),daemon=True);self.worker.start()
    def cancel(self):self.cancel_event.set();self.cancel_btn.configure(state='disabled');self.status.set('正在取消…')
    def _resize_float(self,img,pct):
        np,_,Image,*rest=_deps();pct=max(1,float(pct));
        if abs(pct-100)<1e-6:return img
        h,w=img.shape[:2];nw=max(2,int(round(w*pct/100)));nh=max(2,int(round(h*pct/100)));cv2=rest[-1]
        if cv2 is not None:return cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA).astype(np.float32)
        chans=[np.asarray(Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.LANCZOS),dtype=np.float32) for k in range(3)];return np.stack(chans,axis=2)
    def _batch_worker(self,st):
        run=None;outpipe=None
        try:
            stamp=time.strftime('%Y%m%d_%H%M%S');run=st['base']/f'IceHaloStack_Timelapse_{stamp}';run.mkdir(parents=True,exist_ok=True);bundles=[]
            for idx,f in enumerate(st['flows'],1):
                name=self._format_name(f,idx,st['method']);root=run/name;root.mkdir(parents=True,exist_ok=True);o=f['output'];seq=root/'sequence'
                if o.get('save_sequence') or o.get('save_video'):seq.mkdir(exist_ok=True)
                recipe=self._preset_payload(f);recipe['runtime']={'async_output':True,'disk_cache':False,'version':VERSION,'exposure_wb_smoothing':copy.deepcopy(st.get('exposure_wb_smoothing',{}))}
                (root/'recipe.json').write_text(json.dumps(recipe,ensure_ascii=False,indent=2),encoding='utf-8');bundles.append((idx,f,root,seq,name))
            total=len(st['groups']);work_total=max(1,total*len(bundles));done=0;ref=self._ref_lum();proc_start=time.monotonic()
            engine=_timelapse_stack_engine_name(self,st['method']);pol=getattr(self,'_active_memory_policy',{}) or {}
            perf=PerformanceMonitor(self,engine,pol,'Node Timelapse',st.get('save_performance_report',False))
            dag_plans,dag_counts,dag_meta=self._prepare_shared_node_dag([b[1] for b in bundles]);dag_stats={'hits':0,'computes':0,'stores':0,'budget_skips':0,'peak_bytes':0,'hits_by_node':Counter(),'computes_by_node':Counter(),'reusable_by_node':dict(dag_meta.get('reusable_by_node',{}))}
            outpipe=AsyncOutputPipeline(self,pol,self.queue,'n_output',work_total)
            self.queue.put(('n_status',f'堆栈引擎：{engine} · 曝光/WB平滑 {"ON" if _ewb_enabled(self) else "OFF"} · Shared Node DAG ON · Async Output ON · Queue {outpipe.capacity} · RAM Budget {_fmt_bytes(pol.get("limit_bytes",0))} · Disk Cache OFF'))
            self.queue.put(('n_dag',f'Shared Node DAG：{dag_meta["shared_keys"]} 个共享阶段 · 每 Master 可复用 {dag_meta["reusable_uses"]} 次 · Disk Cache OFF'))
            ext={'PNG 8-bit':'.png','JPEG':'.jpg','TIFF 16-bit':'.tif','TIFF 32-bit Float':'.tif'}
            for fi,master in enumerate(perf.wrap_masters(self._iter_masters(st['groups'],st['method'],ref)),1):
                remaining=Counter(dag_counts);dag_cache={};cache_state={'bytes':0,'peak':0}
                for bi,(idx,f,root,seq,name) in enumerate(bundles):
                    if self.cancel_event.is_set():raise InterruptedError('cancelled')
                    self.queue.put(('n_status',f'帧 {fi}/{total} · {f["name"]} · Shared DAG Hit {dag_stats["hits"]} / Compute {dag_stats["computes"]}'))
                    out=self._execute_shared_flow(master,f,dag_plans[bi],remaining,dag_cache,cache_state,dag_stats,pol);perf.inc('processed_tasks',1);tp=time.monotonic();pct=float(f['output'].get('scale_percent',100));scaled=self._resize_float(out,pct);perf.add_stage('output_prepare',time.monotonic()-tp)
                    if f['output'].get('save_sequence'):
                        fmt=f['output'].get('sequence_format','PNG 8-bit');outpipe.submit_array(seq/f'frame_{fi:06d}{ext[fmt]}',scaled,fmt,'Balanced')
                    elif f['output'].get('save_video'):
                        outpipe.submit_array(seq/f'frame_{fi:06d}.png',scaled,'PNG 8-bit','Fast')
                    self._release_shared_flow_refs(dag_plans[bi],remaining,dag_cache,cache_state);dag_stats['peak_bytes']=max(dag_stats['peak_bytes'],cache_state['peak']);perf.record_dag_stats(dag_stats)
                    done+=1;elapsed=max(1e-6,time.monotonic()-proc_start);fps=done/elapsed;remain=max(0,work_total-done);eta=(remain/fps if fps>1e-9 else None)
                    self.queue.put(('n_processing',{'done':done,'total':work_total,'fps':fps,'eta':eta}))
                dag_cache.clear()
                if fi==1 or fi==total or fi%10==0:self.queue.put(('n_dag',f'Shared Node DAG：Hit {dag_stats["hits"]} · Compute {dag_stats["computes"]} · RAM Peak {_fmt_bytes(dag_stats["peak_bytes"])} · Budget Skip {dag_stats["budget_skips"]} · Disk Cache OFF'))
            self.queue.put(('n_status','节点处理完成，等待 Async Output Queue 写入剩余最终帧…'))
            outpipe.finish();outpipe=None
            self.queue.put(('n_processing',{'done':work_total,'total':work_total,'fps':work_total/max(1e-6,time.monotonic()-proc_start),'eta':0.0}))
            ff=None;videos=[];vidflows=[b for b in bundles if b[1]['output'].get('save_video')]
            for vi,(idx,f,root,seq,name) in enumerate(vidflows,1):
                if self.cancel_event.is_set():raise InterruptedError('cancelled')
                if ff is None:
                    ff=get_ffmpeg_executable()
                    if not ff:raise RuntimeError('未找到 FFmpeg。')
                o=f['output'];fmt=o.get('video_format','MP4 H.264');fps=str(max(0.1,float(o.get('fps',24))));src_ext=ext.get(o.get('sequence_format','PNG 8-bit'),'.png') if o.get('save_sequence') else '.png';pattern=str(seq/f'frame_%06d{src_ext}');self.queue.put(('n_status',f'编码视频：{f["name"]}'))
                if fmt=='MP4 H.264':vp=root/(name+'.mp4');cmd=[ff,'-y','-framerate',fps,'-i',pattern]+_ffmpeg_even_pad_args()+['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',str(vp)]
                elif fmt=='MOV H.264':vp=root/(name+'.mov');cmd=[ff,'-y','-framerate',fps,'-i',pattern]+_ffmpeg_even_pad_args()+['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',str(vp)]
                elif fmt=='MOV ProRes':vp=root/(name+'_ProRes.mov');cmd=[ff,'-y','-framerate',fps,'-i',pattern]+_ffmpeg_even_pad_args()+['-c:v','prores_ks','-profile:v','3','-pix_fmt','yuv422p10le',str(vp)]
                else:
                    vp=root/(name+'.gif');pal=seq/'palette.png';perf.touch('ffmpeg');tf=time.monotonic();p1=subprocess.run([ff,'-y','-framerate',fps,'-i',pattern,'-vf','palettegen=stats_mode=diff',str(pal)],capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));perf.add_stage('ffmpeg',time.monotonic()-tf)
                    if p1.returncode!=0:raise RuntimeError('GIF palette 生成失败：'+(p1.stderr or '')[-1000:])
                    cmd=[ff,'-y','-framerate',fps,'-i',pattern,'-i',str(pal),'-lavfi','paletteuse=dither=sierra2_4a',str(vp)]
                perf.touch('ffmpeg');tf=time.monotonic();pr=subprocess.run(cmd,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));perf.add_stage('ffmpeg',time.monotonic()-tf)
                if pr.returncode!=0:raise RuntimeError('FFmpeg 编码失败：'+(pr.stderr or '')[-2000:]+'\n\nsequence 文件夹已保留，可使用 repair_failed_video_export.bat 直接重新编码，无需重新堆栈。')
                videos.append(str(vp))
                if (not o.get('save_sequence')) and bool(o.get('delete_sequence_after_video_only',True)):shutil.rmtree(seq,ignore_errors=True)
                self.queue.put(('n_progress',86+14*vi/max(1,len(vidflows))))
            perf.finalize('Completed',run,extra={'flows':len(bundles),'frames_per_flow':total,'dag_meta':dag_meta})
            self.queue.put(('n_done',(str(run),total,len(bundles),videos)))
        except InterruptedError:
            if outpipe is not None:
                try:outpipe.cancel()
                except Exception:pass
            try:
                perf.finalize('Cancelled',run) if 'perf' in locals() else setattr(self,'_active_memory_policy',None)
            except Exception:pass
            self.queue.put(('n_cancel',str(run) if run else ''))
        except Exception as e:
            if outpipe is not None:
                try:outpipe.cancel()
                except Exception:pass
            try:
                perf.finalize('Failed',run,error=str(e)) if 'perf' in locals() else setattr(self,'_active_memory_policy',None)
            except Exception:pass
            self.queue.put(('n_error',str(e)+'\n\n'+traceback.format_exc(limit=4)))

    def _poll(self):
        try:
            while True:
                kind,val=self.queue.get_nowait()
                if kind=='n_reference':
                    master,idx,g=val;self.reference_master=master
                    self._preview_reference_serial=int(getattr(self,'_preview_reference_serial',0))+1
                    self._clear_preview_stage_cache()
                    try:
                        st,bp=estimate_asinh_params(master)
                        for f in self.flows:
                            if abs(float(f['cfg'].get('stretch_strength',8))-8)<1e-6:f['cfg']['stretch_strength']=float(st);f['cfg']['stretch_black']=float(bp)
                    except Exception:pass
                    self.reference_proxy_drag,self.reference_proxy_drag_scale=make_float_preview_proxy(master,420);self.reference_proxy_fast,self.reference_proxy_fast_scale=make_float_preview_proxy(master,760);self.reference_proxy_hq,self.reference_proxy_hq_scale=make_float_preview_proxy(master,1600);self.status.set('参考堆栈完成。现在单击节点调整当前流程。');self._schedule_preview(force=True)
                elif kind=='n_preview':
                    token,img,name,q=val
                    if q=='hq':self.preview_hq_running=False
                    else:self.preview_interactive_running=False
                    self.preview_running=self.preview_interactive_running or self.preview_hq_running
                    if token==self.preview_token:
                        self._show_preview(img)
                        qlabel={'drag':'即时当前节点','fast':'快速完整流程','hq':'高精度完整流程'}.get(q,q)
                        self.preview_title.set(f'实时预览 · {name} · {qlabel}')
                        self.status.set(f'{qlabel}预览已更新')
                    if self.preview_pending and not self.preview_interactive_running:
                        qnext=self.preview_pending_quality;self.preview_pending=False
                        self._queue_preview_quality(qnext,1)
                elif kind=='n_preview_cancelled':
                    token,name,q=val
                    if q=='hq':self.preview_hq_running=False
                    else:self.preview_interactive_running=False
                    self.preview_running=self.preview_interactive_running or self.preview_hq_running
                    if self.preview_pending and not self.preview_interactive_running:
                        qnext=self.preview_pending_quality;self.preview_pending=False
                        self._queue_preview_quality(qnext,1)
                elif kind=='n_preview_status':
                    token,name,q,msg=val
                    if q=='hq':self.preview_hq_running=False
                    else:self.preview_interactive_running=False
                    self.preview_running=self.preview_interactive_running or self.preview_hq_running
                    if token==self.preview_token:self.status.set(msg)
                    if self.preview_pending and not self.preview_interactive_running:
                        qnext=self.preview_pending_quality;self.preview_pending=False
                        self._queue_preview_quality(qnext,1)
                elif kind=='n_status':self.status.set(val)
                elif kind=='n_dag':self.memory_dag_text.set(val)
                elif kind=='n_processing':
                    d=val;tot=max(1,int(d.get('total',1)));done=int(d.get('done',0));self.processing_progress.set(min(100.0,done/tot*100.0));eta=d.get('eta');etxt=_format_seconds_short(eta) if eta is not None else '—';self.output_pipeline_text.set(f'Processing：{done}/{tot} · {float(d.get("fps",0.0)):.2f} fps · ETA {etxt}')
                elif kind=='n_output':
                    d=val;tot=max(1,int(d.get('total',1)));done=int(d.get('completed',0));self.writing_progress.set(min(100.0,done/tot*100.0));self.progress.set(min(86.0,done/tot*86.0));eta=d.get('eta');etxt=_format_seconds_short(eta) if eta is not None else '—';wf=float(d.get('recent_writer_fps') or d.get('writer_fps') or 0.0);state='等待处理' if d.get('writer_idle') else f'Writer {wf:.2f} fps';self.output_pipeline_text.set(f'写入：{done}/{tot} · 队列 {d.get("queued",0)}/{d.get("capacity",0)} · {state} · 总 ETA {etxt}')
                elif kind=='n_progress':self.progress.set(val)
                elif kind=='n_done':
                    run,frames,flows,videos=val;elapsed=self._stop_elapsed_timer();self.progress.set(100);self.processing_progress.set(100);self.writing_progress.set(100);self.output_pipeline_text.set('写入：完成');self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.status.set(f'完成 · {flows} 个流程 × {frames} 帧 · 用时 {elapsed} · {run}');messagebox.showinfo(APP_NAME,f'批量导出完成。\n\n流程：{flows}\n每流程帧数：{frames}\n运行时间：{elapsed}\n目录：\n{run}',parent=self)
                elif kind=='n_cancel':
                    elapsed=self._stop_elapsed_timer();self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.output_pipeline_text.set('写入：已取消');self.status.set(f'已取消 · 已运行 {elapsed}')
                elif kind=='n_error':
                    elapsed=self._stop_elapsed_timer();self.preview_running=False;self.preview_interactive_running=False;self.preview_hq_running=False;self.preview_pending=False;self.start_btn.configure(state='normal');self.cancel_btn.configure(state='disabled');self.output_pipeline_text.set('写入：失败/已停止');self.status.set(f'处理失败 · 已运行 {elapsed}');messagebox.showerror(APP_NAME,val+'\n\n运行时间：'+elapsed,parent=self)
        except Empty:pass
        if self.winfo_exists():self.after(80,self._poll)



class StorageManagerDialog(tk.Toplevel):
    """Inspect and safely clean IceHaloStack-related disk usage."""
    TEMP_PREFIXES=('icehalostack','icehalo_','ihs_')

    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner
        self.title('存储与缓存管理 / Storage & Cache Manager')
        self.geometry('980x720')
        self.minsize(760,520)
        self.items=[]
        self._scan_token=0
        self._build()
        self.refresh()

    @staticmethod
    def _human_size(n):
        try:n=float(n)
        except Exception:return '—'
        units=['B','KB','MB','GB','TB'];i=0
        while n>=1024 and i<len(units)-1:n/=1024.0;i+=1
        return f'{n:.2f} {units[i]}' if i>=2 else f'{n:.0f} {units[i]}'

    @staticmethod
    def _dir_size(path):
        path=Path(path)
        if not path.exists():return 0
        if path.is_file():
            try:return path.stat().st_size
            except Exception:return 0
        total=0;stack=[path]
        while stack:
            cur=stack.pop()
            try:
                with os.scandir(cur) as it:
                    for e in it:
                        try:
                            if e.is_symlink():continue
                            if e.is_dir(follow_symlinks=False):stack.append(Path(e.path))
                            elif e.is_file(follow_symlinks=False):total+=e.stat(follow_symlinks=False).st_size
                        except (OSError,PermissionError):pass
            except (OSError,PermissionError):pass
        return total

    @classmethod
    def _temp_entries(cls,tempdir):
        root=Path(tempdir)
        if not root.exists():return []
        out=[]
        try:
            for p in root.iterdir():
                low=p.name.lower()
                if any(low.startswith(prefix) for prefix in cls.TEMP_PREFIXES):out.append(p)
        except Exception:pass
        return out

    @staticmethod
    def _pip_cache_dir():
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        try:
            pr=subprocess.run([sys.executable,'-m','pip','cache','dir'],capture_output=True,text=True,timeout=8,creationflags=flags)
            if pr.returncode==0 and pr.stdout.strip():return Path(pr.stdout.strip())
        except Exception:pass
        local=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))
        return local/'pip'/'Cache'

    def _current_runtime(self):
        if getattr(sys,'frozen',False):return Path(sys.executable).resolve().parent,'EXE 内置运行环境'
        return Path(sys.prefix).resolve(),'当前 Python Runtime'

    @staticmethod
    def _runtime_container(current):
        p=Path(current)
        return p.parent if p.name.lower() in ('venv','.venv') else p

    def _discover_items(self):
        local=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))
        temp=Path(tempfile.gettempdir())
        runtime,runtime_label=self._current_runtime();runtime_container=self._runtime_container(runtime)
        pip_cache=self._pip_cache_dir();project=Path(__file__).resolve().parent if '__file__' in globals() else Path.cwd()
        found=[]
        def add(kind,label,path,safe=False,mode='dir',note=''):
            found.append(dict(kind=kind,label=label,path=Path(path),safe=bool(safe),mode=mode,note=note))
        add('runtime',runtime_label,runtime,False,'dir','当前正在使用；程序运行中不会删除。')
        add('pip','pip Cache',pip_cache,True,'dir','仅为 Python 安装包下载缓存，删除后需要时会重新下载。')
        add('temp_total','Windows TEMP（总占用，仅显示）',temp,False,'dir','不会执行整目录清理。')
        add('temp_ihs','IceHaloStack TEMP',temp,True,'ihs_temp','只删除名称明确属于 IceHaloStack 的临时项。')
        add('project','当前程序目录',project,False,'dir','源码/程序文件，仅显示。')
        try:
            for d in sorted(local.iterdir(),key=lambda x:x.name.lower()):
                if not d.is_dir():continue
                low=d.name.lower()
                if low.startswith('icehalostackruntime'):
                    try:same=(d.resolve()==runtime_container.resolve()) or str(runtime.resolve()).lower().startswith(str(d.resolve()).lower()+os.sep.lower())
                    except Exception:same=str(runtime).lower().startswith(str(d).lower())
                    if not same:add('old_runtime','旧版 Runtime：'+d.name,d,True,'dir','旧版本 Python 私有环境。')
                elif low.startswith('icehalostackbuild'):
                    add('old_build','旧版 Build：'+d.name,d,True,'dir','EXE 构建环境；以后构建时可重建。')
        except Exception:pass
        return found

    def _build(self):
        outer=ttk.Frame(self,padding=10);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='存储与缓存管理',font=_ui_font(14)).pack(anchor='w')
        ttk.Label(outer,text='显示当前 Runtime、pip Cache、TEMP 与旧版 IceHaloStack 环境占用。安全清理不会修改 CUDA Toolkit、NVIDIA 驱动、PixInsight 或你的延时输出目录。',wraplength=900,foreground='#555').pack(anchor='w',pady=(3,8))
        top=ttk.Frame(outer);top.pack(fill='x',pady=(0,8))
        ttk.Button(top,text='刷新统计',command=self.refresh).pack(side='left')
        ttk.Button(top,text='全选安全项',command=self.select_safe).pack(side='left',padx=(6,0))
        ttk.Button(top,text='取消选择',command=self.clear_selection).pack(side='left',padx=(6,0))
        ttk.Button(top,text='一键安全清理',style='Primary.TButton',command=self.clean_safe).pack(side='right')
        ttk.Button(top,text='清理所选',command=self.clean_selected).pack(side='right',padx=(0,6))
        cols=ttk.Frame(outer);cols.pack(fill='x',padx=(4,18));cols.columnconfigure(3,weight=1)
        ttk.Label(cols,text='清理',width=6).grid(row=0,column=0,sticky='w');ttk.Label(cols,text='项目',width=31).grid(row=0,column=1,sticky='w');ttk.Label(cols,text='占用',width=13).grid(row=0,column=2,sticky='w');ttk.Label(cols,text='路径 / 状态').grid(row=0,column=3,sticky='w')
        shell=ttk.Frame(outer);shell.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(shell,highlightthickness=0,borderwidth=0);sb=ttk.Scrollbar(shell,orient='vertical',command=self.canvas.yview,style='IHS.Vertical.TScrollbar');self.canvas.configure(yscrollcommand=sb.set);sb.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.rows=ttk.Frame(self.canvas);self._win=self.canvas.create_window((0,0),window=self.rows,anchor='nw');self.rows.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')));self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self._win,width=e.width));self.rows._ihs_scroll_target=self.canvas;self.canvas._ihs_scroll_target=self.canvas
        self.summary=tk.StringVar(value='等待扫描…');ttk.Label(outer,textvariable=self.summary,foreground='#444').pack(anchor='w',pady=(8,2))
        ttk.Label(outer,text='安全策略：当前 Runtime 永不在程序运行中删除；Windows TEMP 只做总量显示，清理仅针对明确属于 IceHaloStack 的临时项。',foreground='#666',wraplength=900).pack(anchor='w')

    def _open_path(self,path):
        p=Path(path)
        try:
            p.mkdir(parents=True,exist_ok=True)
            if os.name=='nt':os.startfile(str(p))
            elif sys.platform=='darwin':subprocess.Popen(['open',str(p)])
            else:subprocess.Popen(['xdg-open',str(p)])
        except Exception as e:messagebox.showerror(APP_NAME,'无法打开目录：\n'+str(e),parent=self)

    def _copy_path(self,path):
        try:self.clipboard_clear();self.clipboard_append(str(path));self.summary.set('路径已复制：'+str(path))
        except Exception:pass

    def _rebuild_rows(self,descs):
        for w in self.rows.winfo_children():w.destroy()
        self.items=[]
        for i,d in enumerate(descs):
            row=ttk.Frame(self.rows,padding=(3,4));row.grid(row=i,column=0,sticky='ew');row.columnconfigure(3,weight=1)
            var=tk.BooleanVar(value=False);cb=ttk.Checkbutton(row,variable=var)
            if not d['safe']:cb.state(['disabled'])
            cb.grid(row=0,column=0,sticky='w',padx=(0,5));ttk.Label(row,text=d['label'],width=31).grid(row=0,column=1,sticky='w')
            size=tk.StringVar(value='扫描中…');ttk.Label(row,textvariable=size,width=13).grid(row=0,column=2,sticky='w');ttk.Label(row,text=str(d['path'])).grid(row=0,column=3,sticky='w')
            ttk.Button(row,text='打开',width=7,command=lambda p=d['path']:self._open_path(p)).grid(row=0,column=4,padx=(6,2));ttk.Button(row,text='复制',width=7,command=lambda p=d['path']:self._copy_path(p)).grid(row=0,column=5,padx=(2,0))
            if d.get('note'):ttk.Label(row,text=d['note'],foreground='#777',wraplength=680).grid(row=1,column=1,columnspan=5,sticky='w',pady=(1,0))
            self.items.append({**d,'var':var,'size_var':size,'bytes':None})
        self.rows.columnconfigure(0,weight=1)

    def refresh(self):
        self._scan_token+=1;token=self._scan_token;descs=self._discover_items();self._rebuild_rows(descs);self.summary.set('正在后台统计目录大小…')
        def worker():
            total_safe=0
            for idx,item in enumerate(descs):
                if token!=self._scan_token:return
                try:n=sum(self._dir_size(p) for p in self._temp_entries(item['path'])) if item['mode']=='ihs_temp' else self._dir_size(item['path'])
                except Exception:n=0
                if item['safe']:total_safe+=n
                try:self.after(0,lambda i=idx,n=n,t=token:self._set_size(i,n,t))
                except Exception:return
            try:self.after(0,lambda n=total_safe,t=token:self._finish_scan(n,t))
            except Exception:pass
        threading.Thread(target=worker,daemon=True).start()

    def _set_size(self,idx,n,token):
        if token!=self._scan_token or idx>=len(self.items):return
        self.items[idx]['bytes']=n;self.items[idx]['size_var'].set(self._human_size(n))

    def _finish_scan(self,total_safe,token):
        if token==self._scan_token:self.summary.set(f'可安全清理项目当前合计约 {self._human_size(total_safe)}。')

    def select_safe(self):
        for item in self.items:
            if item['safe']:item['var'].set(True)
    def clear_selection(self):
        for item in self.items:item['var'].set(False)
    def clean_safe(self):self._clean([i for i in self.items if i['safe']],'确认执行一键安全清理？')
    def clean_selected(self):
        targets=[i for i in self.items if i['safe'] and i['var'].get()]
        if not targets:messagebox.showinfo(APP_NAME,'没有选择可清理项目。',parent=self);return
        self._clean(targets,'确认清理当前选中的安全项目？')

    def _clean(self,targets,prompt):
        labels='\n'.join('• '+i['label'] for i in targets)
        if not messagebox.askyesno(APP_NAME,prompt+'\n\n'+labels+'\n\n不会清理当前 Runtime、CUDA、PixInsight 或延时输出。',parent=self):return
        self.summary.set('正在清理…')
        def rm_path(p):
            try:
                if p.is_dir() and not p.is_symlink():shutil.rmtree(p)
                elif p.exists():p.unlink()
                return True,None
            except Exception as e:return False,str(e)
        def worker():
            ok=[];fail=[]
            for item in targets:
                try:
                    paths=self._temp_entries(item['path']) if item['mode']=='ihs_temp' else [item['path']]
                    for q in paths:
                        good,err=rm_path(Path(q))
                        if not good:fail.append(f'{q}: {err}')
                    ok.append(item['label'])
                except Exception as e:fail.append(f"{item['label']}: {e}")
            def done():
                msg=f'已处理 {len(ok)} 个项目。'
                if fail:msg+='\n\n部分项目无法删除：\n'+'\n'.join(fail[:8])
                (messagebox.showwarning if fail else messagebox.showinfo)(APP_NAME,msg,parent=self);self.refresh()
            try:self.after(0,done)
            except Exception:pass
        threading.Thread(target=worker,daemon=True).start()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.display_dpi=_configure_tk_high_dpi(self)
        self.title(f'{APP_NAME} {VERSION}')
        self.geometry('1460x860')
        self.minsize(1100,700)
        self.files=[]; self.queue=Queue(); self.worker=None
        self.stack_pause_event=threading.Event(); self.stack_stop_event=threading.Event(); self.stack_lock=threading.Lock()
        self.stack_running_mean=None; self.stack_count=0; self.stack_total=0; self.stack_out=None; self.stack_depth=None
        self.stack_preview_image=None; self.stack_active=False; self.stack_paused=False
        self.linear_master=None; self.working_image=None
        self.is_linear=True; self.image_path=None
        self.undo_stack=[]; self.redo_stack=[]; self.max_undo=8
        self.preview_photo=None
        self.auto_preview_var=tk.BooleanVar(value=True)
        self.normalize_var=tk.BooleanVar(value=False)
        self.stack_method=tk.StringVar(value='平均值 Mean')
        self.stack_range_start=tk.IntVar(value=1)
        self.stack_range_end=tk.IntVar(value=1)
        self.stack_range_info=tk.StringVar(value='当前堆栈区间：1 - 1（0 帧）')
        self.suggested_stretch_strength=8.0
        self.suggested_stretch_black=0.0
        self._var_trace_suspend=False
        self._last_channel_mono_state=False
        self.curve_points = {}
        self.curve_selected_idx = None
        self.hp_curve_points = {k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']}
        self._slider_dragging=False
        self._preview_after_id=None
        self._last_preview_request=0.0
        self._preview_generation=0
        self._last_display_preview=None
        # Main Base preview is computed off the Tk thread. Only the newest request
        # is allowed to render; stale slider-drag frames are discarded.
        self._main_preview_request_serial=0
        self._main_async_preview_running=False
        self._main_async_preview_pending=False
        self._main_async_preview_quality='drag'
        self.output_depth=tk.StringVar(value='32-bit float TIFF')
        self.status=tk.StringVar(value='等待导入冰晕延时序列')
        self.detail=tk.StringVar(value='LINEAR · 尚未生成 Master')
        self.progress=tk.DoubleVar(value=0)
        self.zoom=tk.DoubleVar(value=1.0)
        self.live_preview_var=tk.BooleanVar(value=True)
        self.preview_every=tk.IntVar(value=1)
        self.stack_counter_text=tk.StringVar(value='0 / 0 帧')
        self.compute_backend=tk.StringVar(value='自动')
        self.raw_workers=tk.IntVar(value=2)
        self.accel_status=tk.StringVar(value='尚未检测加速后端')
        self.ui_font_choice=tk.StringVar(value=UI_FONT_PREFERENCE)
        self.ui_theme_choice=tk.StringVar(value=UI_THEME_PREFERENCE)
        self.ui_language_choice=tk.StringVar(value=UI_LANGUAGE)
        self._style(); self._menu(); self._ui(); _enforce_regular_typography(self); self.after_idle(lambda: _enforce_regular_typography(self)); self._install_global_mousewheel();_install_combobox_selection_behavior(self); self._setup_var_traces(); self.after(100,self._poll)
        self._ui_pref_map_after=None;self._ui_pref_map_targets=[];self.bind_all('<Map>',self._ui_preferences_mapped,add='+')
        self.after(250, self.detect_acceleration)

    def _install_global_mousewheel(self):
        """Route the wheel to the scrollable area under the pointer.

        Registered scroll pages use ``_ihs_scroll_target``. Native list/text
        widgets keep their own scrolling. Parameter controls use the surrounding
        page instead of consuming the wheel, so a small screen can always reach
        Apply / Export buttons without accidentally changing a value.
        """
        self.bind_all('<MouseWheel>', self._global_mousewheel, add='+')
        self.bind_all('<Button-4>', lambda e:self._global_mousewheel(e,1), add='+')
        self.bind_all('<Button-5>', lambda e:self._global_mousewheel(e,-1), add='+')
        # On Windows some themed controls may otherwise consume the wheel before
        # the application-wide handler sees it. Override only their wheel class
        # binding; keyboard/mouse-drag behavior remains unchanged.
        for cls in ('TScale','Scale','TEntry','Entry','TSpinbox','Spinbox','TCombobox'):
            try:
                self.bind_class(cls,'<MouseWheel>',self._global_mousewheel)
            except Exception:
                pass

    def _ui_preferences_mapped(self,event=None):
        # Combobox pop-downs and each child widget also emit <Map>.  Refreshing
        # the entire application for those events used to close/rebuild the
        # pop-down before its selection could commit and made every node dialog
        # appear to load slowly.  Only initialize a genuinely new top-level.
        if _I18N_APPLYING:return
        target=getattr(event,'widget',None)
        if target is not self and not isinstance(target,tk.Toplevel):return
        try:
            if not target.winfo_exists():return
            if target not in self._ui_pref_map_targets:self._ui_pref_map_targets.append(target)
        except Exception:return
        if getattr(self,'_ui_pref_map_after',None) is not None:return
        try:self._ui_pref_map_after=self.after_idle(self._refresh_open_ui_preferences)
        except Exception:pass

    def _refresh_open_ui_preferences(self):
        self._ui_pref_map_after=None;targets=list(getattr(self,'_ui_pref_map_targets',[]) or []);self._ui_pref_map_targets=[]
        for target in targets:
            try:
                if target.winfo_exists():_enforce_regular_typography(target)
            except Exception:pass

    def _global_mousewheel(self,event,linux_direction=None):
        w=getattr(event,'widget',None)
        if w is None:return None
        # List/Text/Tree widgets are already proper scroll containers. Let their
        # native class bindings handle the wheel instead of scrolling the page.
        if isinstance(w,(tk.Listbox,tk.Text,ttk.Treeview)):
            return None
        # Node canvas has a dedicated wheel handler (normal scroll, Ctrl zoom).
        tw=w
        while tw is not None:
            if isinstance(tw,tk.Canvas) and getattr(tw,'_ihs_node_canvas',False):
                return None
            target=getattr(tw,'_ihs_scroll_target',None)
            if target is not None:
                try:
                    steps=_mousewheel_steps(event,linux_direction)
                    if steps:
                        target.yview_scroll(steps,'units')
                    return 'break'
                except Exception:
                    return None
            try:
                tw=tw.master
            except Exception:
                break
        return None

    def _style(self):
        _apply_ui_theme(self,UI_THEME_PREFERENCE,persist=False);s=ttk.Style(self)
        # Global regular-weight policy. Every text-bearing ttk class receives an
        # explicit regular font so native theme defaults cannot introduce a heavier
        # heading/caption/button weight.
        regular9=_ui_font(9)
        for sty in ('TLabel','TButton','TCheckbutton','TRadiobutton','TMenubutton',
                    'TEntry','TSpinbox','TCombobox','TNotebook.Tab','TLabelframe.Label',
                    'Treeview','Treeview.Heading','Toolbutton'):
            try: s.configure(sty, font=regular9)
            except Exception: pass
        s.configure('Title.TLabel', font=_ui_font(16))
        s.configure('Sub.TLabel', font=_ui_font(9), foreground=THEME_PALETTES[UI_THEME_PREFERENCE]['muted'])
        s.configure('Primary.TButton', font=_ui_font(10), padding=(16,8))
        s.configure('Stage.TLabel',font=_ui_font(9))
        # Native vector fonts + Per-Monitor-V2 DPI awareness keep labels/canvas text
        # crisp instead of letting Windows bitmap-scale the whole Tk application.

    def _menu(self):
        bar=tk.Menu(self)
        f=tk.Menu(bar, tearoff=0)
        f.add_command(label='添加图片 / RAW...', command=self.add_files, accelerator='Ctrl+O')
        f.add_command(label='添加文件夹...', command=self.add_folder)
        f.add_command(label='打开单张 TIFF / 图片进入编辑...', command=self.open_image)
        f.add_separator(); f.add_command(label='保存当前图像...', command=self.export_current, accelerator='Ctrl+S')
        f.add_separator(); f.add_command(label='清空工程', command=self.clear_files)
        f.add_command(label='退出', command=self.destroy)
        bar.add_cascade(label='文件', menu=f)

        e=tk.Menu(bar, tearoff=0)
        e.add_command(label='撤销', command=self.undo, accelerator='Ctrl+Z')
        e.add_command(label='重做', command=self.redo, accelerator='Ctrl+Y')
        e.add_separator(); e.add_command(label='全选帧', command=self.select_all, accelerator='Ctrl+A')
        e.add_command(label='移除所选帧', command=self.remove_selected, accelerator='Delete')
        bar.add_cascade(label='编辑', menu=e)

        st=tk.Menu(bar, tearoff=0)
        st.add_command(label='开始线性堆栈', command=self.start_stack, accelerator='Ctrl+Enter')
        st.add_command(label='暂停 / 继续', command=self.toggle_stack_pause, accelerator='Space')
        st.add_command(label='使用当前结果并停止', command=self.use_current_stack)
        st.add_command(label='取消堆栈', command=self.cancel_stack)
        bar.add_cascade(label='堆栈', menu=st)

        tl=tk.Menu(bar, tearoff=0)
        tl.add_command(label='打开堆栈延时...', command=self.open_timelapse)
        bar.add_cascade(label='延时', menu=tl)

        lin=tk.Menu(bar, tearoff=0)
        lin.add_checkbutton(label='Auto Stretch 预览（不修改数据）', variable=self.auto_preview_var, command=self.refresh_preview)
        lin.add_command(label='Asinh 拉伸 → 非线性...', command=lambda:self.tabs.select(self.tab_stretch))
        bar.add_cascade(label='线性处理', menu=lin)

        adj=tk.Menu(bar, tearoff=0)
        adj.add_command(label='基础调整 / Camera Raw 风格', command=lambda:self.tabs.select(self.tab_basic))
        adj.add_command(label='通道混合器', command=lambda:self.tabs.select(self.tab_channel))
        bar.add_cascade(label='调整', menu=adj)

        fil=tk.Menu(bar, tearoff=0)
        fil.add_command(label='USM 锐化', command=lambda:self.tabs.select(self.tab_detail))
        fil.add_command(label='高反差保留', command=lambda:self.tabs.select(self.tab_detail))
        fil.add_command(label='浮雕', command=lambda:self.tabs.select(self.tab_detail))
        fil.add_command(label='曲线 / 对比度', command=lambda:self.tabs.select(self.tab_curves))
        bar.add_cascade(label='滤镜', menu=fil)

        view=tk.Menu(bar, tearoff=0)
        view.add_checkbutton(label='Auto Stretch 预览', variable=self.auto_preview_var, command=self.refresh_preview)
        view.add_command(label='适合窗口', command=self.refresh_preview)
        bar.add_cascade(label='视图', menu=view)

        settings=tk.Menu(bar,tearoff=0)
        font_menu=tk.Menu(settings,tearoff=0)
        for key,label in FONT_CHOICES.items():
            font_menu.add_radiobutton(label=label,variable=self.ui_font_choice,value=key,command=self._change_ui_font)
        settings.add_cascade(label='界面字体',menu=font_menu)
        theme_menu=tk.Menu(settings,tearoff=0)
        for key,label in THEME_CHOICES.items():theme_menu.add_radiobutton(label=label,variable=self.ui_theme_choice,value=key,command=self._change_ui_theme)
        settings.add_cascade(label='界面主题',menu=theme_menu)
        language_menu=tk.Menu(settings,tearoff=0)
        for key,label in LANGUAGE_CHOICES.items():language_menu.add_radiobutton(label=label,variable=self.ui_language_choice,value=key,command=self._change_ui_language)
        settings.add_cascade(label='界面语言',menu=language_menu)
        settings.add_separator();settings.add_command(label='界面设置...',command=self.open_interface_settings)
        bar.add_cascade(label='设置',menu=settings)

        h=tk.Menu(bar, tearoff=0)
        h.add_command(label='单独堆栈与性能说明...', command=self.show_single_stack_help)
        h.add_command(label='存储与缓存管理...', command=self.open_storage_manager)
        h.add_separator()
        h.add_command(label='关于 IceHaloStack', command=self.about)
        bar.add_cascade(label='帮助', menu=h)
        self.config(menu=bar)
        self.bind_all('<Control-o>', lambda e:self.add_files())
        self.bind_all('<Control-s>', lambda e:self.export_current())
        self.bind_all('<Control-a>', self._handle_ctrl_a)
        self.bind_all('<Delete>', lambda e:self.remove_selected())
        self.bind_all('<Control-Return>', lambda e:self.start_stack())
        self.bind_all('<Control-z>', lambda e:self.undo())
        self.bind_all('<Control-y>', lambda e:self.redo())
        self.bind_all('<space>', lambda e:self.toggle_stack_pause() if self.stack_active else None)

    def _change_ui_font(self):
        key=str(self.ui_font_choice.get() or 'system')
        previous=UI_FONT_PREFERENCE
        ok,family=_apply_ui_font_preference(self,key,persist=True)
        if not ok:
            self.ui_font_choice.set(previous)
            label=FONT_CHOICES.get(key,key)
            messagebox.showinfo(APP_NAME,f'当前系统未检测到“{label}”。\n\n已保持当前字体，不会下载安装任何字体文件。',parent=self)
            return
        # Apply once more after idle so newly redrawn Canvas labels and native ttk
        # theme elements inherit the same family and regular weight.
        self.after_idle(lambda:_apply_ui_font_preference(self,key,persist=False))
        try:self.status.set(f'界面字体：{FONT_CHOICES.get(key,key)}')
        except Exception:pass

    def _change_ui_theme(self):
        key=str(self.ui_theme_choice.get() or 'light');_apply_ui_theme(self,key,persist=True);_enforce_regular_typography(self)
        try:self.status.set(_tr('界面主题')+': '+_tr(THEME_CHOICES.get(key,key)))
        except Exception:pass

    def _change_ui_language(self):
        key=str(self.ui_language_choice.get() or 'zh_CN');_apply_ui_language(self,key,persist=True);_enforce_regular_typography(self)
        try:self.status.set('Language: '+LANGUAGE_CHOICES.get(key,key) if key=='en' else '界面语言：中文')
        except Exception:pass

    def open_interface_settings(self):
        existing=getattr(self,'_interface_settings_window',None)
        try:
            if existing is not None and existing.winfo_exists():existing.lift();existing.focus_force();return
        except Exception:pass
        d=tk.Toplevel(self);self._interface_settings_window=d;d.title('界面设置');d.geometry('430x410');d.minsize(390,360);d.transient(self)
        def close():
            self._interface_settings_window=None
            try:d.destroy()
            except Exception:pass
        d.protocol('WM_DELETE_WINDOW',close);body=ttk.Frame(d,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='更改会立即应用到所有已打开窗口。',style='Sub.TLabel').pack(anchor='w',pady=(0,12))
        appearance=ttk.LabelFrame(body,text='外观',padding=10);appearance.pack(fill='x')
        for key,label in THEME_CHOICES.items():ttk.Radiobutton(appearance,text=label,variable=self.ui_theme_choice,value=key,command=self._change_ui_theme).pack(side='left',padx=(0,18))
        language=ttk.LabelFrame(body,text='语言',padding=10);language.pack(fill='x',pady=(10,0))
        for key,label in LANGUAGE_CHOICES.items():ttk.Radiobutton(language,text=label,variable=self.ui_language_choice,value=key,command=self._change_ui_language).pack(side='left',padx=(0,18))
        font=ttk.LabelFrame(body,text='字体',padding=10);font.pack(fill='x',pady=(10,0))
        for key,label in FONT_CHOICES.items():ttk.Radiobutton(font,text=label,variable=self.ui_font_choice,value=key,command=self._change_ui_font).pack(anchor='w',pady=2)
        ttk.Button(body,text='关闭设置',command=close).pack(side='bottom',anchor='e',pady=(14,0));_enforce_regular_typography(d)

    def _ui(self):
        root=ttk.Frame(self,padding=(10,8)); root.pack(fill='both',expand=True)
        head=ttk.Frame(root); head.pack(fill='x')
        ttk.Label(head,text='IceHaloStack',style='Title.TLabel').pack(side='left')
        ttk.Label(head,text='冰晕 RAW · 堆栈 · 处理',style='Sub.TLabel').pack(side='left',padx=(10,0),pady=(6,0))
        ttk.Label(head,text=f'v{VERSION}',style='Sub.TLabel').pack(side='right',pady=(6,0))
        ttk.Separator(root).pack(fill='x',pady=(7,7))

        toolbar=ttk.Frame(root); toolbar.pack(fill='x',pady=(0,6))
        ttk.Button(toolbar,text='＋ RAW / 图片',command=self.add_files).pack(side='left')
        ttk.Button(toolbar,text='＋ 文件夹',command=self.add_folder).pack(side='left',padx=4)
        ttk.Button(toolbar,text='▶ 开始堆栈',command=self.start_stack).pack(side='left',padx=(8,4))
        ttk.Button(toolbar,text='🎞 堆栈延时',command=self.open_timelapse).pack(side='left',padx=(0,4))
        self.toolbar_pause_btn=ttk.Button(toolbar,text='⏸ 暂停',command=self.toggle_stack_pause,state='disabled'); self.toolbar_pause_btn.pack(side='left',padx=2)
        self.toolbar_use_btn=ttk.Button(toolbar,text='✓ 使用当前',command=self.use_current_stack,state='disabled'); self.toolbar_use_btn.pack(side='left',padx=2)
        ttk.Separator(toolbar,orient='vertical').pack(side='left',fill='y',padx=6)
        ttk.Checkbutton(toolbar,text='Auto Stretch 预览',variable=self.auto_preview_var,command=self.refresh_preview).pack(side='left')
        ttk.Button(toolbar,text='↶ 撤销',command=self.undo).pack(side='left',padx=(10,3))
        ttk.Button(toolbar,text='↷ 重做',command=self.redo).pack(side='left')
        ttk.Button(toolbar,text='导出',command=self.export_current).pack(side='right')

        body=ttk.Panedwindow(root,orient='horizontal'); body.pack(fill='both',expand=True)
        left=ttk.Frame(body,width=260); center=ttk.Frame(body); right=ttk.Frame(body,width=340)
        body.add(left,weight=1); body.add(center,weight=5); body.add(right,weight=2)

        # Frames panel
        lf=ttk.LabelFrame(left,text='Frames',padding=5); lf.pack(fill='both',expand=True,padx=(0,6))
        self.listbox=tk.Listbox(lf,selectmode=tk.EXTENDED,font=_ui_font(9),activestyle='none')
        sy=ttk.Scrollbar(lf,orient='vertical',command=self.listbox.yview); self.listbox.configure(yscrollcommand=sy.set)
        self.listbox.pack(side='left',fill='both',expand=True); sy.pack(side='right',fill='y')
        lbar=ttk.Frame(left); lbar.pack(fill='x',padx=(0,6),pady=(5,0))
        self.count=ttk.Label(lbar,text='0 帧'); self.count.pack(side='left')
        ttk.Button(lbar,text='移除',command=self.remove_selected).pack(side='right')

        # Center preview
        preview_box=ttk.LabelFrame(center,text='图像预览',padding=3); preview_box.pack(fill='both',expand=True,padx=(0,6))
        phead=ttk.Frame(preview_box);phead.pack(fill='x',pady=(0,3))
        ttk.Label(phead,text='预览导航').pack(side='left')
        self.preview_zoom_text=tk.StringVar(value='Fit')
        pzoom=ttk.Frame(phead);pzoom.pack(side='right')
        for label,value in [('25%',0.25),('50%',0.50),('100%',1.0),('200%',2.0)]:
            ttk.Button(pzoom,text=label,width=5,command=lambda v=value:self._main_preview_set_zoom(v)).pack(side='left',padx=1)
        ttk.Button(pzoom,text='Fit',width=5,command=self._main_preview_fit).pack(side='left',padx=(2,0))
        ttk.Label(pzoom,textvariable=self.preview_zoom_text,width=10,anchor='e').pack(side='left',padx=(5,0))
        self.preview_canvas=tk.Canvas(preview_box,bg='#171717',highlightthickness=0)
        self.preview_canvas.pack(fill='both',expand=True)
        self.preview_zoom=1.0; self.preview_fit_mode=True; self.preview_pan=[0.0,0.0]; self.preview_pan_anchor=None
        self.preview_canvas.bind('<Configure>',lambda e:self._main_preview_redraw())
        self.preview_canvas.bind('<MouseWheel>',self._main_preview_wheel)
        self.preview_canvas.bind('<Button-4>',lambda e:self._main_preview_wheel_linux(e,1))
        self.preview_canvas.bind('<Button-5>',lambda e:self._main_preview_wheel_linux(e,-1))
        self.preview_canvas.bind('<ButtonPress-1>',self._main_preview_pan_start)
        self.preview_canvas.bind('<B1-Motion>',self._main_preview_pan_drag)
        self.preview_canvas.bind('<ButtonRelease-1>',self._main_preview_pan_end)
        self.preview_canvas.bind('z',lambda e:self._main_preview_fit())
        self.preview_canvas.bind('Z',lambda e:self._main_preview_fit())
        self.preview_canvas.create_text(20,20,anchor='nw',fill='#aaaaaa',font=_ui_font(11),text='堆栈完成后将在这里显示图像。',tags='placeholder')

        hist_box=ttk.LabelFrame(center,text='Histogram',padding=2); hist_box.pack(fill='x',padx=(0,6),pady=(6,0))
        self.hist_canvas=tk.Canvas(hist_box,height=92,bg='#101010',highlightthickness=0)
        self.hist_canvas.pack(fill='x')
        self.hist_canvas.bind('<Configure>',lambda e:self.draw_histogram())

        # Right edit tabs
        self.tabs=ttk.Notebook(right); self.tabs.pack(fill='both',expand=True); self.tabs.bind('<<NotebookTabChanged>>', lambda e:self.refresh_preview())
        self.tab_stack=ttk.Frame(self.tabs)
        self.tab_stretch=ttk.Frame(self.tabs)
        self.tab_basic=ttk.Frame(self.tabs)
        self.tab_channel=ttk.Frame(self.tabs)
        self.tab_curves=ttk.Frame(self.tabs)
        self.tab_detail=ttk.Frame(self.tabs)
        self.tabs.add(self.tab_stack,text='堆栈')
        self.tabs.add(self.tab_stretch,text='拉伸')
        self.tabs.add(self.tab_basic,text='基础')
        self.tabs.add(self.tab_detail,text='细节')
        self.tabs.add(self.tab_channel,text='通道')
        self.tabs.add(self.tab_curves,text='曲线')
        self._build_stack_tab(); self._build_stretch_tab(); self._build_basic_tab(); self._build_detail_tab(); self._build_channel_tab(); self._build_curves_tab()

        bottom=ttk.Frame(root); bottom.pack(fill='x',pady=(7,0))
        self.pb=ttk.Progressbar(bottom,variable=self.progress,maximum=100); self.pb.pack(side='left',fill='x',expand=True,padx=(0,10))
        ttk.Label(bottom,textvariable=self.status).pack(side='left',padx=(0,12))
        ttk.Label(bottom,textvariable=self.detail,style='Stage.TLabel').pack(side='right')

    def _scrollable_tab_body(self, outer):
        body=getattr(outer,'_ihs_scroll_body',None)
        if body is not None:
            return body
        body,canvas,shell=_make_vertical_scroll_area(outer,padding=10)
        outer._ihs_scroll_body=body
        outer._ihs_scroll_canvas=canvas
        return body

    def _build_stack_tab(self):
        t=self._scrollable_tab_body(self.tab_stack)
        ttk.Label(t,text='固定三脚架',font=_ui_font(11)).pack(anchor='w')
        ttk.Label(t,text='不进行几何对齐；适用于固定机位冰晕延时。',wraplength=280).pack(anchor='w',pady=(2,10))
        ttk.Label(t,text='组合方式').pack(anchor='w')
        ttk.Combobox(t,textvariable=self.stack_method,state='readonly',values=['平均值 Mean','最大值 Maximum']).pack(fill='x',pady=(4,8))
        ttk.Label(t,text='Mean：逐帧平均，适合降低随机噪声；Maximum：逐像素逐通道保留所有帧中的最大值。',style='Sub.TLabel',wraplength=280).pack(anchor='w',pady=(0,8))
        ttk.Separator(t).pack(fill='x',pady=8)
        ttk.Label(t,text='快速堆栈区间',font=_ui_font(10)).pack(anchor='w')
        ttk.Label(t,text='你可以只堆栈序列中的某一段，例如 1–50、50–100，而不是一次性把全部帧都堆完。',style='Sub.TLabel',wraplength=280).pack(anchor='w',pady=(2,6))
        rg=ttk.Frame(t); rg.pack(fill='x',pady=(0,4))
        ttk.Label(rg,text='起始帧').grid(row=0,column=0,sticky='w')
        ttk.Entry(rg,textvariable=self.stack_range_start,width=8,justify='right').grid(row=0,column=1,sticky='e',padx=(4,10))
        ttk.Label(rg,text='结束帧').grid(row=0,column=2,sticky='w')
        ttk.Entry(rg,textvariable=self.stack_range_end,width=8,justify='right').grid(row=0,column=3,sticky='e',padx=(4,0))
        ttk.Button(t,text='使用当前选中范围',command=self.use_selected_as_stack_range).pack(fill='x',pady=(2,4))
        ttk.Label(t,textvariable=self.stack_range_info,style='Stage.TLabel',wraplength=280).pack(anchor='w',pady=(0,6))
        ttk.Checkbutton(t,text='自动曝光归一化（实验性）',variable=self.normalize_var).pack(anchor='w')
        ttk.Separator(t).pack(fill='x',pady=12)
        ttk.Label(t,text='Master 输出').pack(anchor='w')
        ttk.Combobox(t,textvariable=self.output_depth,state='readonly',values=['16-bit TIFF','32-bit float TIFF']).pack(fill='x',pady=(4,10))
        self.start_stack_btn=ttk.Button(t,text='开始堆栈',style='Primary.TButton',command=self.start_stack); self.start_stack_btn.pack(fill='x')
        ttk.Separator(t).pack(fill='x',pady=12)
        ttk.Label(t,text='性能加速',font=_ui_font(10)).pack(anchor='w')
        perf=ttk.Frame(t); perf.pack(fill='x',pady=(5,2))
        ttk.Label(perf,text='计算后端').pack(side='left')
        ttk.Combobox(perf,textvariable=self.compute_backend,state='readonly',width=16,values=['自动','CPU','NVIDIA CUDA']).pack(side='right')
        perf2=ttk.Frame(t); perf2.pack(fill='x',pady=2)
        ttk.Label(perf2,text='RAW 并行解码').pack(side='left')
        ttk.Combobox(perf2,textvariable=self.raw_workers,state='readonly',width=6,values=[1,2,3,4]).pack(side='right')
        ttk.Button(t,text='重新检测 CUDA',command=lambda:self.detect_acceleration(show_dialog=True)).pack(fill='x',pady=(4,0))
        ttk.Separator(t).pack(fill='x',pady=12)
        ttk.Label(t,text='实时堆栈预览',font=_ui_font(10)).pack(anchor='w')
        ttk.Checkbutton(t,text='启用即时预览',variable=self.live_preview_var).pack(anchor='w',pady=(4,2))
        row=ttk.Frame(t); row.pack(fill='x',pady=2)
        ttk.Label(row,text='每').pack(side='left')
        ttk.Combobox(row,textvariable=self.preview_every,state='readonly',width=5,values=[1,2,5,10,20]).pack(side='left',padx=4)
        ttk.Label(row,text='帧刷新一次').pack(side='left')
        ttk.Label(t,textvariable=self.stack_counter_text,style='Stage.TLabel').pack(anchor='w',pady=(6,6))
        btnrow=ttk.Frame(t); btnrow.pack(fill='x')
        self.pause_btn=ttk.Button(btnrow,text='⏸ 暂停',command=self.toggle_stack_pause,state='disabled'); self.pause_btn.pack(side='left',fill='x',expand=True,padx=(0,3))
        self.use_btn=ttk.Button(btnrow,text='✓ 使用当前结果',command=self.use_current_stack,state='disabled'); self.use_btn.pack(side='left',fill='x',expand=True,padx=(3,0))
        self.cancel_btn=ttk.Button(t,text='取消堆栈',command=self.cancel_stack,state='disabled'); self.cancel_btn.pack(fill='x',pady=(5,0))

    def _build_stretch_tab(self):
        t=self._scrollable_tab_body(self.tab_stretch)
        ttk.Label(t,text='Linear → Nonlinear',font=_ui_font(11)).pack(anchor='w')
        ttk.Label(t,text='Auto Stretch 只是显示预览，不修改线性数据。\n“应用 Asinh”才真正转换到非线性。',wraplength=285).pack(anchor='w',pady=(3,12))
        self.stretch_strength=tk.DoubleVar(value=8.0)
        self.stretch_black=tk.DoubleVar(value=0.0)
        self._scale(t,'Asinh Strength',self.stretch_strength,0.1,500,0.5)
        self._scale(t,'Black Point',self.stretch_black,0,0.05,0.0005)
        ttk.Button(t,text='应用 Asinh 拉伸',style='Primary.TButton',command=self.do_stretch).pack(fill='x',pady=(12,4))
        ttk.Button(t,text='恢复 Linear Master',command=self.restore_linear_master).pack(fill='x')

    def _basic_defaults_dict(self):
        defaults={
            'exposure':0.0,'contrast':0.0,'highlights':0.0,'shadows':0.0,'whites':0.0,'blacks':0.0,
            'temperature':0.0,'tint':0.0,'texture':0.0,'clarity':0.0,'dehaze':0.0,
            'hsl_hue':0.0,'hsl_sat':0.0,'hsl_lum':0.0,
            'cg_shadow_h':0.0,'cg_shadow_s':0.0,'cg_mid_h':0.0,'cg_mid_s':0.0,'cg_high_h':0.0,'cg_high_s':0.0,'cg_balance':0.0,
            'detail_sharpen':0.0,'detail_radius':1.0,'luma_nr':0.0,'chroma_nr':0.0,
            'opt_distortion':0.0,'opt_vignette':0.0,'opt_ca':0.0,
            'cal_red_h':0.0,'cal_red_s':0.0,'cal_green_h':0.0,'cal_green_s':0.0,'cal_blue_h':0.0,'cal_blue_s':0.0,
        }
        for cname in ['red','orange','yellow','green','aqua','blue','purple','magenta']:
            defaults[f'mix_{cname}_h']=0.0;defaults[f'mix_{cname}_s']=0.0;defaults[f'mix_{cname}_l']=0.0
        return defaults

    def _basic_cfg_from_ui(self, proxy_scale=1.0):
        cfg={k:v.get() for k,v in self.basic_vars.items()}
        cfg['_proxy_scale']=float(proxy_scale)
        cfg['base_curve']=False
        return cfg

    def _basic_is_identity(self):
        if not hasattr(self,'basic_defaults') or not hasattr(self,'basic_vars'):
            return True
        for key,default in self.basic_defaults.items():
            try:
                if abs(float(self.basic_vars[key].get())-float(default))>1e-8:
                    return False
            except Exception:
                return False
        return True

    def _build_basic_tab(self):
        t=self._scrollable_tab_body(self.tab_basic)
        ttk.Label(t,text='Camera Raw 风格基础调整',font=_ui_font(11)).pack(anchor='w',pady=(0,6))
        ttk.Label(t,text='这里统一对齐延时处理中的 Base / 基础调色逻辑：面向堆栈并拉伸后的 TIFF / Float 图像，不调用 Adobe Camera Raw。可用鼠标滚轮浏览完整面板。',wraplength=300).pack(anchor='w',pady=(0,8))
        self.basic_defaults=self._basic_defaults_dict()
        self.basic_vars={k:tk.DoubleVar(value=v) for k,v in self.basic_defaults.items()}

        sec=ttk.LabelFrame(t,text='Basic / 基本明暗',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Exposure (EV)',self.basic_vars['exposure'],-5,5,0.05)
        for name,key in [('Contrast','contrast'),('Highlights','highlights'),('Shadows','shadows'),('Whites','whites'),('Blacks','blacks')]:
            self._scale(sec,name,self.basic_vars[key],-100,100,1)

        sec=ttk.LabelFrame(t,text='WB / 白平衡',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Temperature / 色温',self.basic_vars['temperature'],-100,100,1)
        self._scale(sec,'Tint / 色调',self.basic_vars['tint'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Presence / 质感',padding=7);sec.pack(fill='x',pady=4)
        for name,key in [('Texture / 纹理','texture'),('Clarity / 清晰度','clarity'),('Dehaze / 去朦胧','dehaze')]:
            self._scale(sec,name,self.basic_vars[key],-100,100,1)

        sec=ttk.LabelFrame(t,text='HSL / 全局色相·饱和度·明度',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Hue / 色相',self.basic_vars['hsl_hue'],-180,180,1)
        self._scale(sec,'Saturation / 饱和度',self.basic_vars['hsl_sat'],-100,100,1)
        self._scale(sec,'Luminance / 明度',self.basic_vars['hsl_lum'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Color Mixer / 颜色混合器',padding=7);sec.pack(fill='x',pady=4)
        color_labels=[('red','Red / 红'),('orange','Orange / 橙'),('yellow','Yellow / 黄'),('green','Green / 绿'),('aqua','Aqua / 青'),('blue','Blue / 蓝'),('purple','Purple / 紫'),('magenta','Magenta / 洋红')]
        for cname,clabel in color_labels:
            sub=ttk.LabelFrame(sec,text=clabel,padding=5);sub.pack(fill='x',pady=2)
            self._scale(sub,'Hue',self.basic_vars[f'mix_{cname}_h'],-100,100,1)
            self._scale(sub,'Saturation',self.basic_vars[f'mix_{cname}_s'],-100,100,1)
            self._scale(sub,'Luminance',self.basic_vars[f'mix_{cname}_l'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Color Grading / 色彩分级',padding=7);sec.pack(fill='x',pady=4)
        for prefix,label in [('shadow','Shadows / 阴影'),('mid','Midtones / 中间调'),('high','Highlights / 高光')]:
            sub=ttk.LabelFrame(sec,text=label,padding=5);sub.pack(fill='x',pady=2)
            self._scale(sub,'Hue / 色相',self.basic_vars[f'cg_{prefix}_h'],0,360,1)
            self._scale(sub,'Saturation / 饱和度',self.basic_vars[f'cg_{prefix}_s'],-100,100,1)
        self._scale(sec,'Balance / 平衡',self.basic_vars['cg_balance'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Detail / 细节',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Sharpen / 锐化',self.basic_vars['detail_sharpen'],0,200,1)
        self._scale(sec,'Radius / 半径 px',self.basic_vars['detail_radius'],0.2,10,0.1,reset_value=1.0)
        self._scale(sec,'Luma NR / 明度降噪',self.basic_vars['luma_nr'],0,100,1)
        self._scale(sec,'Chroma NR / 色彩降噪',self.basic_vars['chroma_nr'],0,100,1)

        sec=ttk.LabelFrame(t,text='Optics / 光学',padding=7);sec.pack(fill='x',pady=4)
        self._scale(sec,'Distortion / 畸变',self.basic_vars['opt_distortion'],-100,100,1)
        self._scale(sec,'Vignette / 暗角',self.basic_vars['opt_vignette'],-100,100,1)
        self._scale(sec,'CA / 色差校正',self.basic_vars['opt_ca'],-100,100,1)

        sec=ttk.LabelFrame(t,text='Calibration / 校准',padding=7);sec.pack(fill='x',pady=4)
        for prefix,label in [('red','Red Primary / 红原色'),('green','Green Primary / 绿原色'),('blue','Blue Primary / 蓝原色')]:
            sub=ttk.LabelFrame(sec,text=label,padding=5);sub.pack(fill='x',pady=2)
            self._scale(sub,'Hue / 色相',self.basic_vars[f'cal_{prefix}_h'],-100,100,1)
            self._scale(sub,'Saturation / 饱和度',self.basic_vars[f'cal_{prefix}_s'],-100,100,1)

        ttk.Button(t,text='应用基础调整',style='Primary.TButton',command=self.do_basic).pack(fill='x',pady=(10,3))
        ttk.Button(t,text='参数归零',command=self.reset_basic).pack(fill='x')

    def _build_channel_tab(self):
        t=self._scrollable_tab_body(self.tab_channel)
        ttk.Label(t,text='通道混合器',font=_ui_font(11)).pack(anchor='w',pady=(0,8))
        ttk.Label(t,text='可选择输出通道，并可开启单色模式。极端正/负通道权重会放大色差噪声，因此默认开启“色彩噪声保护”；它只预处理通道色差，不直接模糊亮度。关闭后即为纯数学通道混合。',wraplength=285).pack(anchor='w',pady=(0,10))
        self.channel_output=tk.StringVar(value='红色')
        self.channel_mono=tk.BooleanVar(value=False)
        self.channel_red=tk.DoubleVar(value=100.0)
        self.channel_green=tk.DoubleVar(value=0.0)
        self.channel_blue=tk.DoubleVar(value=0.0)
        self.channel_constant=tk.DoubleVar(value=0.0)
        self.channel_noise_protect=tk.BooleanVar(value=True)
        self.channel_noise_strength=tk.DoubleVar(value=30.0)
        self.channel_noise_radius=tk.DoubleVar(value=0.8)
        row=ttk.Frame(t); row.pack(fill='x',pady=(2,6))
        ttk.Label(row,text='输出通道').pack(side='left')
        channel_combo=ttk.Combobox(row,textvariable=self.channel_output,state='readonly',width=10,values=['灰色','红色','绿色','蓝色'])
        channel_combo.pack(side='right')
        channel_combo.bind('<<ComboboxSelected>>', lambda e:self.on_channel_output_changed())
        # The themed PhotoImage indicator can lose its selected-state image on
        # Windows after a theme/font refresh.  Use Tk's native indicator for this
        # important mode switch so a checked monochrome state is always visible.
        palette=THEME_PALETTES.get(UI_THEME_PREFERENCE,THEME_PALETTES['light'])
        self.channel_mono_check=tk.Checkbutton(
            t,text='单色',variable=self.channel_mono,command=self.on_channel_mono_toggle,
            bg=palette['bg'],fg=palette['fg'],activebackground=palette['bg'],
            activeforeground=palette['fg'],selectcolor=palette['field'],
            highlightthickness=0,bd=0,font=_ui_font(9),anchor='w')
        self.channel_mono_check.pack(anchor='w',pady=(0,6))
        noise=ttk.LabelFrame(t,text='色彩噪声保护',padding=6); noise.pack(fill='x',pady=(0,7))
        ttk.Checkbutton(noise,text='启用（只平滑通道色差，尽量保留亮度细节）',variable=self.channel_noise_protect).pack(anchor='w',pady=(0,3))
        self._scale(noise,'强度 %',self.channel_noise_strength,0,100,1,reset_value=30.0)
        self._scale(noise,'半径 px',self.channel_noise_radius,0.1,5.0,0.1,reset_value=0.8)
        self._scale(t,'红色 %',self.channel_red,-200,200,1)
        self._scale(t,'绿色 %',self.channel_green,-200,200,1)
        self._scale(t,'蓝色 %',self.channel_blue,-200,200,1)
        self._scale(t,'常数 %',self.channel_constant,-100,100,1)
        btns=ttk.Frame(t); btns.pack(fill='x',pady=(10,4))
        ttk.Button(btns,text='应用通道混合器',style='Primary.TButton',command=self.do_channel_mixer).pack(side='left',fill='x',expand=True,padx=(0,3))
        ttk.Button(btns,text='参数归零 / 预设',command=self.reset_channel_mixer).pack(side='left',fill='x',expand=True,padx=(3,0))

    def _build_curves_tab(self):
        t=self._scrollable_tab_body(self.tab_curves)
        ttk.Label(t,text='Curves',font=_ui_font(11)).pack(anchor='w')
        ttk.Label(t,text='真正的控制点曲线编辑器：支持 RGB / 红 / 绿 / 蓝 / 亮度。点击添加点，控制点可横向/纵向拖动；下方黑/白三角可直接调整输入端点。右键删除中间控制点。',wraplength=285).pack(anchor='w',pady=(3,10))
        row=ttk.Frame(t); row.pack(fill='x',pady=(0,6))
        ttk.Label(row,text='通道').pack(side='left')
        self.curve_channel=tk.StringVar(value='RGB')
        cb=ttk.Combobox(row,textvariable=self.curve_channel,state='readonly',width=10,values=['RGB','红色','绿色','蓝色','亮度'])
        cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>', lambda e:self._on_curve_channel_changed())

        self.curve_canvas=tk.Canvas(t,width=290,height=310,bg='#202020',highlightthickness=1,highlightbackground='#404040')
        self.curve_canvas.pack(fill='x',pady=(2,6))
        self.curve_canvas.bind('<Button-1>', self._curve_click)
        self.curve_canvas.bind('<B1-Motion>', self._curve_drag)
        self.curve_canvas.bind('<ButtonRelease-1>', self._curve_release)
        self.curve_canvas.bind('<Button-3>', self._curve_right_click)
        self.curve_canvas.bind('<Configure>', lambda e:self._draw_curve_editor())

        vals=ttk.Frame(t); vals.pack(fill='x',pady=(0,6))
        self.curve_input_var=tk.DoubleVar(value=50.0)
        self.curve_output_var=tk.DoubleVar(value=50.0)
        self._labeled_entry(vals,'输入',self.curve_input_var).pack(side='left',fill='x',expand=True,padx=(0,4))
        self._labeled_entry(vals,'输出',self.curve_output_var).pack(side='left',fill='x',expand=True,padx=(4,0))
        self.curve_input_var.trace_add('write', lambda *a:self._curve_numeric_changed())
        self.curve_output_var.trace_add('write', lambda *a:self._curve_numeric_changed())

        btns=ttk.Frame(t); btns.pack(fill='x',pady=(2,2))
        ttk.Button(btns,text='重置当前通道',command=self.reset_current_curve).pack(side='left',fill='x',expand=True,padx=(0,4))
        ttk.Button(btns,text='重置全部通道',command=self.reset_all_curves).pack(side='left',fill='x',expand=True,padx=(4,0))
        ttk.Button(t,text='应用曲线',style='Primary.TButton',command=self.do_curve).pack(fill='x',pady=(10,0))
        self._init_curves()
        self.curve_axis_drag = None
        self.after(30, self._draw_curve_editor)

    def _build_detail_tab(self):
        t=self._scrollable_tab_body(self.tab_detail)

        ttk.Label(t,text='细节滤镜 · 实时预览',font=_ui_font(11)).pack(anchor='w',pady=(0,6))
        ttk.Label(t,text='高反差保留与浮雕默认关闭，只有在你主动开启后才会参与实时预览与应用。数值框支持双击后直接输入。向下滚动可看到完整浮雕参数。',wraplength=300).pack(anchor='w',pady=(0,8))

        # USM
        usm=ttk.LabelFrame(t,text='USM 锐化',padding=7); usm.pack(fill='x')
        self.usm_amount=tk.DoubleVar(value=0); self.usm_radius=tk.DoubleVar(value=2.0); self.usm_threshold=tk.DoubleVar(value=0.0)
        self._scale(usm,'Amount %',self.usm_amount,0,500,1)
        self._scale(usm,'Radius px',self.usm_radius,0.1,250,0.2)
        self._scale(usm,'Threshold',self.usm_threshold,0,255,1)
        ttk.Button(usm,text='应用 USM',command=self.do_usm).pack(fill='x',pady=(5,0))

        # High Pass
        hp=ttk.LabelFrame(t,text='高反差保留（PS 风格）',padding=7); hp.pack(fill='x',pady=(8,0))
        self.hp_enabled=tk.BooleanVar(value=False)
        ttk.Checkbutton(hp,text='启用高反差保留',variable=self.hp_enabled).pack(anchor='w',pady=(0,4))
        self.hp_radius=tk.DoubleVar(value=10.0)
        self.hp_amount=tk.DoubleVar(value=100.0)
        self.hp_mode=tk.StringVar(value='Overlay')
        self.hp_preview_type=tk.StringVar(value='滤镜本体')
        self.hp_curve_enabled=tk.BooleanVar(value=False)
        self._scale(hp,'Radius px',self.hp_radius,0.1,250,0.1)
        ttk.Label(hp,text='预览').pack(anchor='w',pady=(3,0))
        ttk.Combobox(hp,textvariable=self.hp_preview_type,state='readonly',values=['滤镜本体','混合到原图']).pack(fill='x',pady=(2,4))
        ttk.Label(hp,text='混合模式 / Opacity（仅“混合到原图”）').pack(anchor='w')
        ttk.Combobox(hp,textvariable=self.hp_mode,state='readonly',values=['Overlay','Soft Light','Linear Light']).pack(fill='x',pady=(2,3))
        self._scale(hp,'Opacity %',self.hp_amount,0,100,1)
        ttk.Checkbutton(hp,text='启用高反差保留曲线',variable=self.hp_curve_enabled).pack(anchor='w',pady=(6,2))
        ttk.Button(hp,text='打开 High Pass 曲线编辑器',command=self.open_hp_curve_dialog).pack(fill='x',pady=(0,4))
        ttk.Button(hp,text='应用 High Pass',command=self.do_highpass).pack(fill='x')

        # Emboss - Photoshop-style core parameters
        em=ttk.LabelFrame(t,text='浮雕（Photoshop 风格）',padding=7); em.pack(fill='x',pady=(8,0))
        self.emboss_enabled=tk.BooleanVar(value=False)
        self.emboss_preview=tk.BooleanVar(value=True)
        top=ttk.Frame(em); top.pack(fill='x',pady=(0,4))
        ttk.Checkbutton(top,text='启用浮雕',variable=self.emboss_enabled).pack(side='left')
        ttk.Checkbutton(top,text='预览',variable=self.emboss_preview).pack(side='right')
        self.emboss_angle=tk.DoubleVar(value=-128.0)
        self.emboss_height=tk.DoubleVar(value=1.0)
        self.emboss_strength=tk.DoubleVar(value=100.0)
        self.emboss_style=tk.StringVar(value='Photoshop Emboss')
        self.emboss_blend=tk.StringVar(value='Normal')
        self.emboss_opacity=tk.DoubleVar(value=100.0)
        r=ttk.Frame(em);r.pack(fill='x',pady=(2,4));ttk.Label(r,text='类型 / Style').pack(side='left');ttk.Combobox(r,textvariable=self.emboss_style,state='readonly',values=['Photoshop Emboss','Color Emboss','Gray Emboss'],width=18).pack(side='right')
        self._scale(em,'角度 (°)',self.emboss_angle,-180,180,1,reset_value=-128.0)
        dialrow=ttk.Frame(em);dialrow.pack(fill='x',pady=(2,5))
        ttk.Label(dialrow,text='方向 / Angle Dial\n拖动圆内方向杆改变角度\n双击圆盘恢复 -128°',foreground='#666').pack(side='left',anchor='w')
        AngleDial(dialrow,self.emboss_angle,command=lambda v:self._schedule_preview(immediate=False),release_command=lambda v:self._schedule_preview(immediate=True),reset_value=-128.0,size=72).pack(side='right',padx=(8,10))
        self._scale(em,'高度 (像素)',self.emboss_height,1,200,1)
        self._scale(em,'数量 (%)',self.emboss_strength,1,500,1)
        r=ttk.Frame(em);r.pack(fill='x',pady=(3,3));ttk.Label(r,text='混合模式 / Blend').pack(side='left');ttk.Combobox(r,textvariable=self.emboss_blend,state='readonly',values=['Normal','Overlay','Soft Light','Linear Light'],width=18).pack(side='right')
        self._scale(em,'不透明度 / Opacity %',self.emboss_opacity,0,100,1,reset_value=100.0)
        ttk.Label(em,text='Photoshop Emboss 为推荐 PS 风格；Color Emboss 保留现有彩色模式；Gray Emboss 保留旧版灰色模式。',foreground='#666').pack(anchor='w',pady=(2,3))
        ttk.Button(em,text='应用浮雕',command=self.do_emboss).pack(fill='x',pady=(5,8))

    def _labeled_entry(self,parent,label,var):
        frame=ttk.Frame(parent)
        ttk.Label(frame,text=label).pack(anchor='w')
        entry=ttk.Entry(frame,textvariable=var,width=8,justify='right')
        entry.pack(fill='x')

        def select_all(event=None):
            entry.focus_set()
            entry.selection_range(0,'end')
            entry.icursor('end')
            return 'break'

        # Keep the same keyboard behavior as the other parameter boxes.
        entry.bind('<Control-a>', select_all)
        entry.bind('<Control-A>', select_all)
        entry.bind('<Double-Button-1>', select_all)
        entry.bind('<Return>', lambda e:(self._curve_numeric_changed(), 'break')[1])
        return frame

    def _scale(self,parent,label,var,frm,to,res,reset_value=None):
        box=ttk.Frame(parent); box.pack(fill='x',pady=2)
        top=ttk.Frame(box); top.pack(fill='x')
        ttk.Label(top,text=label).pack(side='left')
        entry=ttk.Entry(top,width=10,justify='right')
        entry.pack(side='right')
        initial_value=float(var.get())
        if reset_value is None:
            reset_value = 0.0 if float(frm) <= 0.0 <= float(to) else initial_value

        def fmt_value(v):
            try:
                fv=float(v)
                if abs(res - round(res)) < 1e-9 and res >= 1:
                    return str(int(round(fv)))
                return f'{fv:.6f}'.rstrip('0').rstrip('.')
            except Exception:
                return str(v)

        def sync_from_var(*args):
            # While the user is typing, don't overwrite their edit.
            if entry.focus_get() == entry:
                return
            entry.delete(0,'end')
            entry.insert(0, fmt_value(var.get()))

        def commit_entry(event=None):
            txt=entry.get().strip()
            try:
                v=float(txt)
                if v < frm: v = frm
                if v > to: v = to
                var.set(v)
                entry.delete(0,'end')
                entry.insert(0, fmt_value(v))
            except Exception:
                entry.delete(0,'end')
                entry.insert(0, fmt_value(var.get()))
            return 'break' if event and getattr(event,'keysym','') == 'Return' else None

        # Expose the commit callback so a slider can safely commit the currently
        # focused numeric field before Tk's Scale class binding changes its value.
        entry._icehalo_commit = commit_entry

        click_state={'time':0}
        def begin_drag(event=None):
            # ttk::scale's class binding may move the thumb on the second click before
            # <Double-Button-1> becomes visible on some Windows themes. Detect the
            # second press ourselves at widget-binding priority and stop the class
            # binding after restoring the neutral/default value.
            now=int(getattr(event,'time',0) or 0)
            if now and click_state['time'] and 0 < now-click_state['time'] <= 420:
                click_state['time']=0
                return reset_slider(event)
            click_state['time']=now
            focused=self.focus_get()
            if isinstance(focused, (tk.Entry, ttk.Entry)):
                cb=getattr(focused, '_icehalo_commit', None)
                if cb is not None:
                    cb()
                try:
                    scale.focus_set()
                except Exception:
                    pass
            self._slider_dragging=True

        def end_drag(event=None):
            self._slider_dragging=False
            # Make sure the numeric box reflects the final slider value.
            try:
                entry.delete(0,'end')
                entry.insert(0, fmt_value(var.get()))
            except Exception:
                pass
            # Do not force a zero-delay HQ render for every slider mouse-up.  The
            # normal debounce combines a quick sequence of three or four edits.
            self._schedule_preview(immediate=False)

        def reset_slider(event=None):
            var.set(float(reset_value))
            try:
                scale.focus_set()
            except Exception:
                pass
            self._slider_dragging=False
            try:self.status.set(f'{label} 已恢复中性/默认值：{float(reset_value):g}')
            except Exception:pass
            self._schedule_preview(immediate=True)
            return 'break'

        def select_entry_all(event=None):
            entry.focus_set()
            entry.selection_range(0,'end')
            entry.icursor('end')
            return 'break'

        var.trace_add('write', lambda *a: sync_from_var())
        sync_from_var()
        entry.bind('<Return>', commit_entry)
        # FocusOut remains useful when moving between ordinary controls. The Scale
        # ButtonPress handler above commits first, so it can no longer overwrite dragging.
        entry.bind('<FocusOut>', commit_entry)
        entry.bind('<Control-a>', select_entry_all)
        entry.bind('<Control-A>', select_entry_all)
        entry.bind('<Double-Button-1>', select_entry_all)
        scale=ttk.Scale(box,from_=frm,to=to,variable=var)
        scale.pack(fill='x')
        scale.bind('<ButtonPress-1>', begin_drag, add='+')
        scale.bind('<ButtonRelease-1>', end_drag, add='+')
        scale.bind('<Double-Button-1>', reset_slider, add='+')
        return scale

    def _setup_var_traces(self):
        vars_to_watch = [self.auto_preview_var, self.live_preview_var, self.preview_every, self.stretch_strength, self.stretch_black,
            self.usm_amount, self.usm_radius, self.usm_threshold, self.hp_enabled, self.hp_radius, self.hp_amount, self.hp_mode, self.hp_preview_type, self.hp_curve_enabled,
            self.emboss_enabled, self.emboss_preview, self.emboss_angle, self.emboss_height, self.emboss_strength, self.emboss_style, self.emboss_blend, self.emboss_opacity,
            self.channel_output, self.channel_mono, self.channel_red, self.channel_green, self.channel_blue, self.channel_constant, self.channel_noise_protect, self.channel_noise_strength, self.channel_noise_radius]
        vars_to_watch += list(self.basic_vars.values())
        for var in vars_to_watch:
            var.trace_add('write', self._on_live_param_change)
        self.tabs.bind('<<NotebookTabChanged>>', lambda e:self.refresh_preview(), add='+')

    def _on_live_param_change(self, *args):
        if self._var_trace_suspend:
            return
        self._schedule_preview(immediate=False)

    def _schedule_preview(self, immediate=False):
        # Coalesce high-frequency Scale events. Base/Camera-Raw preview is expensive,
        # so it is rendered in a single-flight worker: while one frame is running we
        # remember only the newest requested state instead of queueing every mouse move.
        self._main_preview_request_serial += 1
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id=None
        # A short mouse-up debounce lets several quick adjustments collapse into
        # one Base render.  Immediate is reserved for explicit final refreshes.
        delay = 0 if immediate else (28 if self._slider_dragging else 140)
        self._preview_after_id=self.after(delay, self._run_scheduled_preview)

    def _run_scheduled_preview(self):
        self._preview_after_id=None
        try:
            current_tab=self.tabs.select()
        except Exception:
            current_tab=''
        # Base is the heaviest interactive panel. Never run its full preview pipeline
        # synchronously on the Tk/UI thread; doing so is what caused Not Responding.
        if (not self.is_linear) and current_tab == str(getattr(self,'tab_basic','')):
            self._request_async_basic_preview()
            return
        self.refresh_preview()

    def _request_async_basic_preview(self):
        serial=int(self._main_preview_request_serial)
        quality='drag' if self._slider_dragging else 'hq'
        if self._main_async_preview_running:
            self._main_async_preview_pending=True
            self._main_async_preview_quality=quality
            return
        base=self._preview_base_image()
        if base is None:
            return
        cfg=self._basic_cfg_from_ui(proxy_scale=float(getattr(self,'_preview_proxy_scale',1.0)))
        # The cached proxy is read-only for this worker: apply_base_editor creates its
        # own float working array before processing, so the master/proxy cache is safe.
        self._main_async_preview_running=True
        self._main_async_preview_pending=False
        self._main_async_preview_quality=quality
        def work():
            try:
                out=apply_base_editor(base,cfg,None)
                self.queue.put(('main_basic_preview',(serial,out,quality,None)))
            except Exception as e:
                self.queue.put(('main_basic_preview',(serial,None,quality,str(e))))
        threading.Thread(target=work,daemon=True).start()

    def _set_var_silently(self, var, value):
        self._var_trace_suspend = True
        try:
            var.set(value)
        finally:
            self._var_trace_suspend = False

    def estimate_current_stretch(self):
        if self.linear_master is None and self.working_image is None:
            return
        img = self.linear_master if self.linear_master is not None else self.working_image
        if img is None:
            return
        strength, black = estimate_asinh_params(img)
        self.suggested_stretch_strength = float(strength)
        self.suggested_stretch_black = float(black)
        self._set_var_silently(self.stretch_strength, round(float(strength), 4))
        self._set_var_silently(self.stretch_black, round(float(black), 6))
        self.refresh_preview()

    def reset_to_suggested_stretch(self):
        self._set_var_silently(self.stretch_strength, round(float(self.suggested_stretch_strength), 4))
        self._set_var_silently(self.stretch_black, round(float(self.suggested_stretch_black), 6))
        self.refresh_preview()

    def _init_curves(self):
        self.curve_points = {k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']}
        self.curve_selected_idx = None

    def _current_curve_points(self):
        ch = self.curve_channel.get() if hasattr(self, 'curve_channel') else 'RGB'
        return self.curve_points.setdefault(ch, [(0.0,0.0),(1.0,1.0)])

    def _curve_is_identity(self, channel=None):
        ch = channel or (self.curve_channel.get() if hasattr(self,'curve_channel') else 'RGB')
        pts = self.curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
        return len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6

    def _curves_any_active(self):
        return any(not self._curve_is_identity(ch) for ch in ['RGB','红色','绿色','蓝色','亮度'])

    def _curve_canvas_geometry(self):
        c = self.curve_canvas
        W = max(c.winfo_width(), 80); H = max(c.winfo_height(), 100)
        m = 18
        # Leave a strip below the graph for Photoshop-style input endpoint handles.
        bottom_strip = 20
        return W, H, m, W-2*m, H-2*m-bottom_strip

    def _curve_to_canvas(self, x, y):
        W,H,m,w,h = self._curve_canvas_geometry()
        return m + x*w, m + (1.0-y)*h

    def _canvas_to_curve(self, cx, cy):
        W,H,m,w,h = self._curve_canvas_geometry()
        x = (cx - m) / max(w,1)
        y = 1.0 - (cy - m) / max(h,1)
        return max(0.0,min(1.0,x)), max(0.0,min(1.0,y))

    def _nearest_curve_point(self, cx, cy, threshold=10):
        pts = self._current_curve_points()
        best=None; bestd=1e9
        for i,(x,y) in enumerate(pts):
            px,py = self._curve_to_canvas(x,y)
            d=((cx-px)**2+(cy-py)**2)**0.5
            if d < bestd:
                best=(i,px,py); bestd=d
        if best and bestd <= threshold:
            return best[0]
        return None

    def _set_curve_selected_point_vars(self):
        if self.curve_selected_idx is None:
            return
        pts = self._current_curve_points()
        if 0 <= self.curve_selected_idx < len(pts):
            x,y = pts[self.curve_selected_idx]
            self._set_var_silently(self.curve_input_var, round(x*255.0, 2))
            self._set_var_silently(self.curve_output_var, round(y*255.0, 2))

    def _draw_curve_editor(self):
        if not hasattr(self, 'curve_canvas'):
            return
        c=self.curve_canvas; c.delete('all')
        W,H,m,w,h = self._curve_canvas_geometry()
        # background grid
        c.create_rectangle(m,m,m+w,m+h, outline='#666666', fill='#222222')
        for i in range(1,4):
            x = m + w*i/4.0; y = m + h*i/4.0
            c.create_line(x,m,x,m+h, fill='#333333')
            c.create_line(m,y,m+w,y, fill='#333333')
        # diagonal identity
        c.create_line(m,m+h,m+w,m, fill='#555555', dash=(4,3))
        # histogram background for current channel
        try:
            np, *_ = _deps()
            img = self._preview_base_image()
            if img is not None:
                smp = np.clip(img[::8,::8],0,1)
                ch=self.curve_channel.get() if hasattr(self,'curve_channel') else 'RGB'
                if ch=='RGB': vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
                elif ch=='红色': vals=smp[...,0].ravel()
                elif ch=='绿色': vals=smp[...,1].ravel()
                elif ch=='蓝色': vals=smp[...,2].ravel()
                else: vals=(0.2126*smp[...,0]+0.7152*smp[...,1]+0.0722*smp[...,2]).ravel()
                hist,_=np.histogram(vals,bins=160,range=(0,1))
                hist=np.log1p(hist.astype(np.float64)); mx=hist.max() or 1.0; hist/=mx
                # Filled gray waveform, closer to Photoshop/ACR Curves.
                poly=[m, m+h]
                ridge=[]
                for i,v in enumerate(hist):
                    x = m + (i/(len(hist)-1))*w
                    y = m+h - v*(h*0.78)
                    poly.extend([x,y]); ridge.extend([x,y])
                poly.extend([m+w, m+h])
                c.create_polygon(*poly, fill='#4a4a4a', outline='')
                c.create_line(*ridge, fill='#707070', width=1)
        except Exception:
            pass
        # Photoshop-style horizontal input endpoint sliders (black / white triangles).
        pts = self._current_curve_points()
        if len(pts) >= 2:
            bx,_ = self._curve_to_canvas(pts[0][0], pts[0][1])
            wx,_ = self._curve_to_canvas(pts[-1][0], pts[-1][1])
            axis_y = m+h+12
            c.create_polygon(bx-6,axis_y+6, bx+6,axis_y+6, bx,axis_y-4, fill='#111111', outline='#9a9a9a', tags=('curve_axis_black',))
            c.create_polygon(wx-6,axis_y+6, wx+6,axis_y+6, wx,axis_y-4, fill='#eeeeee', outline='#9a9a9a', tags=('curve_axis_white',))

        # curve line
        pts = self._current_curve_points()
        lut = build_curve_lut(pts, 256)
        line=[]
        for i,v in enumerate(lut):
            x = i/255.0
            cx,cy = self._curve_to_canvas(x, float(v))
            line.extend([cx,cy])
        c.create_line(*line, fill='#58a6ff', width=2, smooth=True)
        for i,(x,y) in enumerate(pts):
            cx,cy = self._curve_to_canvas(x,y)
            r = 4 if i != self.curve_selected_idx else 6
            fill = '#ffffff' if i==self.curve_selected_idx else '#b9d6ff'
            c.create_oval(cx-r,cy-r,cx+r,cy+r, fill=fill, outline='#1f6feb', width=1)

    def _on_curve_channel_changed(self):
        self.curve_selected_idx = None
        self._draw_curve_editor()
        self.refresh_preview()

    def _curve_click(self, event):
        pts = self._current_curve_points()
        # First test the bottom-axis black/white input handles.
        if len(pts) >= 2:
            W,H,m,w,h = self._curve_canvas_geometry()
            axis_y = m+h+12
            bx,_ = self._curve_to_canvas(pts[0][0], pts[0][1])
            wx,_ = self._curve_to_canvas(pts[-1][0], pts[-1][1])
            if abs(event.y-axis_y) <= 12 and abs(event.x-bx) <= 12:
                self.curve_axis_drag='black'; self.curve_selected_idx=0
                self._set_curve_selected_point_vars(); self._draw_curve_editor(); return
            if abs(event.y-axis_y) <= 12 and abs(event.x-wx) <= 12:
                self.curve_axis_drag='white'; self.curve_selected_idx=len(pts)-1
                self._set_curve_selected_point_vars(); self._draw_curve_editor(); return
        self.curve_axis_drag=None
        W,H,m,w,h = self._curve_canvas_geometry()
        if event.y > m+h:
            return
        idx = self._nearest_curve_point(event.x, event.y)
        if idx is None:
            x,y = self._canvas_to_curve(event.x, event.y)
            pts.append((x,y))
            pts.sort(key=lambda p:p[0])
            idx = min(range(len(pts)), key=lambda i: abs(pts[i][0]-x)+abs(pts[i][1]-y))
        self.curve_selected_idx = idx
        self._set_curve_selected_point_vars()
        self._draw_curve_editor()
        self.refresh_preview()

    def _curve_drag(self, event):
        if self.curve_selected_idx is None:
            return
        pts = self._current_curve_points()
        i = self.curve_selected_idx
        x,y = self._canvas_to_curve(event.x, event.y)
        if self.curve_axis_drag in ('black','white') and len(pts) >= 2:
            if self.curve_axis_drag == 'black':
                x = max(0.0, min(pts[1][0]-0.002, x))
                pts[0] = (x, pts[0][1])
                self.curve_selected_idx = 0
            else:
                x = max(pts[-2][0]+0.002, min(1.0, x))
                pts[-1] = (x, pts[-1][1])
                self.curve_selected_idx = len(pts)-1
            self._set_curve_selected_point_vars()
            self._draw_curve_editor()
            self._slider_dragging = True
            self._schedule_preview(immediate=False)
            return
        if i == 0:
            right = pts[1][0] - 0.002 if len(pts) > 1 else 0.998
            x = max(0.0, min(right, x))
        elif i == len(pts)-1:
            left = pts[-2][0] + 0.002 if len(pts) > 1 else 0.002
            x = max(left, min(1.0, x))
        else:
            left = pts[i-1][0] + 0.002
            right = pts[i+1][0] - 0.002
            x = max(left, min(right, x))
        pts[i] = (x,y)
        self._set_curve_selected_point_vars()
        self._draw_curve_editor()
        self.refresh_preview_fast()

    def _curve_release(self, event):
        self.curve_axis_drag = None
        self._slider_dragging = False
        self._schedule_preview(immediate=True)

    def _curve_right_click(self, event):
        idx = self._nearest_curve_point(event.x, event.y)
        pts = self._current_curve_points()
        if idx is None or idx in (0, len(pts)-1):
            return
        pts.pop(idx)
        self.curve_selected_idx = None
        self._draw_curve_editor()
        self.refresh_preview()

    def _curve_numeric_changed(self):
        if self._var_trace_suspend or self.curve_selected_idx is None:
            return
        pts = self._current_curve_points()
        i = self.curve_selected_idx
        if not (0 <= i < len(pts)):
            return
        try:
            x = float(self.curve_input_var.get())/255.0
            y = float(self.curve_output_var.get())/255.0
        except Exception:
            return
        x = max(0.0, min(1.0, x)); y = max(0.0, min(1.0, y))
        if i == 0:
            right = pts[1][0] - 0.002 if len(pts) > 1 else 0.998
            x = max(0.0, min(right, x))
        elif i == len(pts)-1:
            left = pts[-2][0] + 0.002 if len(pts) > 1 else 0.002
            x = max(left, min(1.0, x))
        else:
            left = pts[i-1][0] + 0.002
            right = pts[i+1][0] - 0.002
            x = max(left, min(right, x))
        pts[i] = (x,y)
        self._draw_curve_editor()
        self.refresh_preview()

    def reset_current_curve(self):
        ch = self.curve_channel.get()
        self.curve_points[ch] = [(0.0,0.0),(1.0,1.0)]
        self.curve_selected_idx = None
        self.curve_axis_drag = None
        self._draw_curve_editor()
        self.refresh_preview()

    def reset_all_curves(self):
        self._init_curves()
        self.curve_axis_drag = None
        self._draw_curve_editor()
        self.refresh_preview()

    def on_channel_mono_toggle(self):
        state = bool(self.channel_mono.get())
        self._last_channel_mono_state = state
        if state:
            self._set_var_silently(self.channel_output, '灰色')
            self._set_var_silently(self.channel_red, 40.0)
            self._set_var_silently(self.channel_green, 40.0)
            self._set_var_silently(self.channel_blue, 20.0)
            self._set_var_silently(self.channel_constant, 0.0)
        self.refresh_preview()

    def on_channel_output_changed(self):
        # If the user manually switches to gray output, keep that choice, but do not
        # force monochrome; presets are only forced when monochrome is enabled.
        self.refresh_preview()

    def reset_channel_mixer(self):
        if getattr(self, 'channel_mono', None) is not None and self.channel_mono.get():
            self._set_var_silently(self.channel_output, '灰色')
            self._set_var_silently(self.channel_red, 40.0)
            self._set_var_silently(self.channel_green, 40.0)
            self._set_var_silently(self.channel_blue, 20.0)
            self._set_var_silently(self.channel_constant, 0.0)
        else:
            out = getattr(self, 'channel_output', tk.StringVar(value='红色')).get()
            if out == '绿色':
                vals = (0.0, 100.0, 0.0)
            elif out == '蓝色':
                vals = (0.0, 0.0, 100.0)
            elif out == '灰色':
                vals = (40.0, 40.0, 20.0)
            else:
                vals = (100.0, 0.0, 0.0)
            self._set_var_silently(self.channel_red, vals[0])
            self._set_var_silently(self.channel_green, vals[1])
            self._set_var_silently(self.channel_blue, vals[2])
            self._set_var_silently(self.channel_constant, 0.0)
        self.refresh_preview()

    def do_channel_mixer(self):
        if not self._require_nonlinear():return
        self._push_undo()
        self.status.set('正在应用通道混合器…'); self.update_idletasks()
        self.working_image = apply_channel_mixer(
            self.working_image,
            output_channel=self.channel_output.get(),
            monochrome=self.channel_mono.get(),
            red=self.channel_red.get(),
            green=self.channel_green.get(),
            blue=self.channel_blue.get(),
            constant=self.channel_constant.get(),
            noise_protect=self.channel_noise_protect.get(),
            noise_strength=self.channel_noise_strength.get(),
            noise_radius=self.channel_noise_radius.get(),
        )
        self.reset_channel_mixer()
        self.status.set('通道混合器完成')

    def _preview_base_image(self):
        if self.stack_active and self.stack_preview_image is not None:
            img=self.stack_preview_image
            source_is_stack_proxy=True
        else:
            if self.working_image is None:
                return None
            img=self.working_image
            source_is_stack_proxy=False
        h,w=img.shape[:2]
        current_tab=self.tabs.select() if hasattr(self,'tabs') else ''
        detail_tab=(current_tab == str(getattr(self,'tab_detail','')))
        basic_tab=(current_tab == str(getattr(self,'tab_basic','')))
        # Dragging uses a small proxy but the SAME processing algorithms. Mouse-up
        # switches to a denser verification proxy. Base is intentionally capped below
        # the Detail page because Camera-Raw style processing runs many sequential
        # operations; this keeps feedback fast while proxy_scale preserves spatial
        # radii and avoids the old preview/final-strength mismatch.
        if self._slider_dragging:
            target_h,target_w=220,390
        elif detail_tab:
            target_h,target_w=1500,2600
        elif basic_tab:
            # Base may traverse WB, HSL, grading, detail, optics and calibration.
            # A 0.47 MP verification proxy is ample for the fit-sized canvas and
            # avoids repeatedly processing a 0.86 MP proxy after every small edit.
            target_h,target_w=520,900
        else:
            target_h,target_w=950,1600
        scale=min(1.0, target_h/float(max(h,1)), target_w/float(max(w,1)))
        # A live stack preview is already a reduced worker proxy; we do not know its
        # exact full-resolution ratio here, so treat it as the current source.
        if source_is_stack_proxy:
            self._preview_proxy_scale=1.0
            return img
        self._preview_proxy_scale=float(scale)
        if scale >= 0.999:
            return img
        nw=max(2,int(round(w*scale)));nh=max(2,int(round(h*scale)))
        # Resizing a 30–60 MP master on every Scale event can itself become the
        # bottleneck. Cache drag/HQ proxies while the underlying master is unchanged.
        cache=getattr(self,'_preview_proxy_cache',None)
        if not isinstance(cache,dict):
            cache={};self._preview_proxy_cache=cache
        key=(id(img),int(h),int(w),int(nh),int(nw))
        cached=cache.get(key)
        if cached is not None:
            return cached
        try:
            np,*_rest=_deps();cv2=_rest[-1]
            if cv2 is not None:
                out=cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA)
            else:
                Image=_rest[1];chans=[]
                for k in range(3):
                    ch=Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.BILINEAR)
                    chans.append(np.asarray(ch,dtype=np.float32))
                out=np.stack(chans,axis=2)
        except Exception:
            step=max(1,int(round(1.0/max(scale,1e-6))))
            out=img[::step,::step]
        cache[key]=out
        # Keep at most a few quality levels/source generations to bound RAM use.
        while len(cache)>4:
            try:cache.pop(next(iter(cache)))
            except Exception:break
        return out

    def _active_preview_image(self):
        np, *_ = _deps()
        img = self._preview_base_image()
        if img is None:
            return None
        out = img.copy()
        current_tab = self.tabs.select()
        if self.is_linear:
            if self.auto_preview_var.get():
                out = auto_stretch_for_display(out, self.stretch_strength.get(), self.stretch_black.get())
            return np.clip(out, 0, 1).astype(np.float32)
        if current_tab == str(self.tab_basic):
            if not self._basic_is_identity():
                out = apply_base_editor(out, self._basic_cfg_from_ui(proxy_scale=self._preview_proxy_scale), None)
        elif current_tab == str(self.tab_channel):
            if self.channel_mono.get() or self.channel_output.get() == '灰色' or any(abs(v.get()) > 1e-8 for v in [self.channel_red, self.channel_green, self.channel_blue, self.channel_constant]):
                out = apply_channel_mixer(out, self.channel_output.get(), self.channel_mono.get(), self.channel_red.get(), self.channel_green.get(), self.channel_blue.get(), self.channel_constant.get(), self.channel_noise_protect.get(), self.channel_noise_strength.get(), self.channel_noise_radius.get())
        elif current_tab == str(self.tab_detail):
            # Spatial parameters are defined in FULL-RESOLUTION pixels. The preview
            # proxy must scale Radius/Height or the preview will look much stronger
            # than the effect that is actually applied to the master.
            ps=max(float(getattr(self,'_preview_proxy_scale',1.0)),1e-4)
            if abs(self.usm_amount.get()) > 1e-8:
                out = apply_usm(out, self.usm_amount.get(), max(0.1,self.usm_radius.get()*ps), self.usm_threshold.get())
            if self.hp_enabled.get():
                hp_r=max(0.1,self.hp_radius.get()*ps)
                if self.hp_preview_type.get() == '滤镜本体':
                    out = highpass_filter(out, hp_r)
                elif abs(self.hp_amount.get()) > 1e-8:
                    out = apply_highpass(out, hp_r, self.hp_amount.get(), self.hp_mode.get())
                out = self._apply_hp_curve(out)
            if self.emboss_enabled.get() and self.emboss_preview.get():
                out = apply_emboss(out, self.emboss_angle.get(), max(0.1,self.emboss_height.get()*ps), self.emboss_strength.get(), self.emboss_opacity.get(), self.emboss_blend.get(), self.emboss_style.get())
        elif current_tab == str(self.tab_curves):
            ch = self.curve_channel.get()
            pts = self.curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
            if not self._curve_is_identity(ch):
                out = apply_curve_lut(out, build_curve_lut(pts, 256), ch)
        return np.clip(out, 0, 1).astype(np.float32)

    def add_files(self):
        pats=' '.join('*'+e for e in sorted(ALL_EXTS))
        ch=filedialog.askopenfilenames(title='选择冰晕延时序列',filetypes=[('图像 / RAW',pats),('所有文件','*.*')])
        self._append(ch)

    def add_folder(self):
        d=filedialog.askdirectory(title='选择包含延时序列的文件夹')
        if not d:return
        self._append([str(p) for p in Path(d).iterdir() if p.is_file() and p.suffix.lower() in ALL_EXTS])

    def open_image(self):
        p=filedialog.askopenfilename(title='打开图像进入编辑',filetypes=[('图像','*.tif *.tiff *.png *.jpg *.jpeg *.bmp')])
        if not p:return
        try:
            self.status.set('正在读取图像…'); self.update_idletasks()
            img=read_linear_rgb(p)
            self.linear_master=img.copy(); self.working_image=img.copy(); self.is_linear=True; self.image_path=p
            self.undo_stack.clear(); self.redo_stack.clear(); self.status.set('图像已载入'); self._update_state(); self.estimate_current_stretch(); self.refresh_preview()
        except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def _append(self, paths):
        old=set(self.files)
        for p in paths:
            if p not in old and Path(p).suffix.lower() in ALL_EXTS:
                self.files.append(p); old.add(p)
        self.files.sort(key=lambda x:Path(x).name.lower()); self.refresh_list()

    def refresh_list(self):
        self.listbox.delete(0,'end')
        for i,p in enumerate(self.files,1): self.listbox.insert('end',f'{i:04d}   {Path(p).name}')
        self.count.config(text=f'{len(self.files)} 帧')
        n=len(self.files)
        if n <= 0:
            self._set_var_silently(self.stack_range_start, 1)
            self._set_var_silently(self.stack_range_end, 1)
        else:
            s=int(self.stack_range_start.get() or 1)
            e=int(self.stack_range_end.get() or n)
            s=max(1,min(n,s)); e=max(1,min(n,e))
            if s>e: s,e=e,s
            if n==len(self.files):
                if self.stack_range_end.get() <= 1 and self.stack_range_start.get() == 1:
                    e=n
            self._set_var_silently(self.stack_range_start, s)
            self._set_var_silently(self.stack_range_end, e)
        self._update_stack_range_info()

    def _current_stack_range(self):
        n=len(self.files)
        if n <= 0:
            return 1, 1, []
        try:
            s=int(self.stack_range_start.get() or 1)
        except Exception:
            s=1
        try:
            e=int(self.stack_range_end.get() or n)
        except Exception:
            e=n
        s=max(1,min(n,s)); e=max(1,min(n,e))
        if s > e:
            s,e=e,s
        subset=self.files[s-1:e]
        return s,e,subset

    def _update_stack_range_info(self, *args):
        n=len(self.files)
        if n <= 0:
            self.stack_range_info.set('当前堆栈区间：无可用帧')
            return
        s,e,subset=self._current_stack_range()
        self.stack_range_info.set(f'当前堆栈区间：{s} - {e}（{len(subset)} 帧）')

    def use_selected_as_stack_range(self):
        sel=self.listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME,'请先在左侧 Frames 列表中选择你要堆栈的范围。\n\n例如先框选第 1–50 张，再点击“使用当前选中范围”。')
            return
        s=min(sel)+1; e=max(sel)+1
        self._set_var_silently(self.stack_range_start, s)
        self._set_var_silently(self.stack_range_end, e)
        self._update_stack_range_info()


    def _handle_ctrl_a(self, event=None):
        w = self.focus_get()
        # Parameter entry: Ctrl+A selects only the number inside that field.
        if isinstance(w, (tk.Entry, ttk.Entry)):
            try:
                w.selection_range(0, 'end')
                w.icursor('end')
            except Exception:
                pass
            return 'break'
        # Text-like widgets should keep their normal Select All behavior.
        if isinstance(w, tk.Text):
            try:
                w.tag_add('sel', '1.0', 'end-1c')
            except Exception:
                pass
            return 'break'
        self.select_all()
        return 'break'

    def select_all(self): self.listbox.selection_set(0,'end')
    def remove_selected(self):
        for i in reversed(self.listbox.curselection()): del self.files[i]
        self.refresh_list()
    def clear_files(self): self.files.clear(); self.refresh_list()
    def open_timelapse(self):
        if len(self.files) < 2:
            messagebox.showwarning(APP_NAME,'请先导入至少 2 帧延时序列。')
            return
        w=getattr(self,'timelapse_window',None)
        try:
            if w is not None and w.winfo_exists():
                w.lift(); w.focus_force(); return
        except Exception:
            pass
        self.timelapse_window=TimelapseNodeWindow(self)

    def open_storage_manager(self):
        StorageManagerDialog(self)

    def show_single_stack_help(self):
        messagebox.showinfo(
            '单独堆栈与性能说明',
            '计算后端：\n'
            '• 自动：CUDA 可用时可选择相应加速路径，否则使用 CPU。\n'
            '• CPU：使用 NumPy / CPU 计算。\n'
            '• NVIDIA CUDA：需要当前 IceHaloStack Python 环境中安装匹配的 CuPy。\n\n'
            'CUDA 检测不会安装或升级系统 CUDA Toolkit；RAW 解码仍主要依赖 CPU。'
            '高分辨率 RAW 可根据机器性能调整并行解码数量。\n\n'
            '实时堆栈预览：\n'
            '堆栈过程中可暂停检查当前结果，满意时可直接使用当前结果结束本次堆栈。\n\n'
            'Master 输出：\n'
            '需要保留线性高动态范围数据时，优先使用 32-bit float TIFF。'
        )

    def about(self):
        messagebox.showinfo('关于',f'{APP_NAME} {VERSION}\n\n冰晕专用 RAW / Mean + Maximum 堆栈 / 图像处理原型。\n当前已包含实时 Mean 堆栈预览、暂停/继续/使用当前结果、基于建议值的 Asinh 预览/拉伸、基础/细节/曲线实时预览、PS 风格 High Pass/Emboss、通道混合器，以及 Linear Master 导出。高反差保留/浮雕默认关闭，数值支持双击输入；浮雕采用 Photoshop 风格角度/高度/数量参数与角度圆盘，并提供 Photoshop Emboss、原有 Color Emboss、Gray Emboss、Blend Mode 与 Opacity；所有主调节页、节点参数页与延时左侧控制栏均支持鼠标滚轮滚动；主预览、延时参考预览、节点实时预览支持滚轮缩放，并可用 Z 一键回到 Fit。Base 实时预览采用单任务后台计算与过期帧丢弃，拖动滑块时不会在 UI 线程堆积计算。v0.4.0 加入预览防抖/拖动代理优化、滑块双击复位，并将 Asinh Strength 上限提高到 500。v0.5.0 加入并行 RAW 预解码与可选 NVIDIA CUDA/CuPy Mean 后端。v0.5.1 加入通用 CUDA Toolkit 检测与自动匹配 CuPy 安装，不修改系统 CUDA。v0.7.1 重构延时工作流；v0.7.6 在延时窗口内加入可直接拖动的 Curves 编辑器，并使用快速/高质量代理图显著提高参数拖动实时预览速度。 v0.9.4.14 将预览平移改为 Canvas Fast Pan，拖拽期间不再重新缩放或重建 PhotoImage。v0.9.5.2 将曝光 / 白平衡平滑工作区改为关键帧驱动界面：支持原生窗口最大化、关键帧向导、全帧列表蓝点切换、关键帧调整同步、LRTimelapse 风格平滑力度与 1–10 遍多遍平滑，并同时显示原始/自动平滑/关键帧目标三类曲线；修正仍以 RAM-only Correction Table 在 Stack 前应用到每个 Linear RGB 输入帧。')

    def _set_stack_controls(self, active=False, paused=False):
        self.stack_active=active; self.stack_paused=paused
        st = 'normal' if active else 'disabled'
        pause_text = '▶ 继续' if paused else '⏸ 暂停'
        for name in ('pause_btn','use_btn','cancel_btn','toolbar_pause_btn','toolbar_use_btn'):
            if hasattr(self,name): getattr(self,name).configure(state=st)
        if hasattr(self,'pause_btn'): self.pause_btn.configure(text=pause_text)
        if hasattr(self,'toolbar_pause_btn'): self.toolbar_pause_btn.configure(text=pause_text)

    def detect_acceleration(self, show_dialog=False):
        requested=self.compute_backend.get() if hasattr(self,'compute_backend') else '自动'
        if requested == 'CPU':
            ver, path, source = detect_system_cuda_toolkit()
            suffix = f' · 系统 Toolkit {ver} 保持不变' if ver else ''
            msg='CPU · NumPy CPU' + suffix
            self.accel_status.set(msg)
            if show_dialog:
                messagebox.showinfo('计算后端检测', msg)
            return
        ok, cuda_desc, _ = detect_cuda_backend()
        if ok:
            msg='CUDA 可用 · ' + cuda_desc
        else:
            prefix = 'CUDA 不可用 · ' if requested == 'NVIDIA CUDA' else '自动将使用 CPU · '
            msg=prefix + cuda_desc
        self.accel_status.set(msg)
        if show_dialog:
            messagebox.showinfo('计算后端检测', msg)

    def start_stack(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME,'堆栈正在进行中。可以暂停、继续，或使用当前结果。')
            return
        if len(self.files)<1:
            messagebox.showwarning(APP_NAME,'请至少导入 1 帧。'); return
        s,e,subset=self._current_stack_range()
        if len(subset) < 1:
            messagebox.showwarning(APP_NAME,'当前堆栈区间无可用帧。请检查起始帧和结束帧。'); return
        method=self.stack_method.get()
        method_key='maximum' if method.startswith('最大值') else 'mean'
        range_tag=f'_{s:04d}-{e:04d}'
        default_name=('IceHaloStack_Maximum' if method_key=='maximum' else 'IceHaloStack_Mean') + f'{range_tag}_LinearMaster_32f.tif'
        out=filedialog.asksaveasfilename(title='保存 Linear Master',defaultextension='.tif',filetypes=[('TIFF','*.tif *.tiff')],initialfile=default_name)
        if not out:return
        self.progress.set(0); self.status.set(f'正在准备实时堆栈… 区间 {s}-{e}')
        self.stack_pause_event.clear(); self.stack_stop_event.clear()
        self.stack_out=out; self.stack_depth=self.output_depth.get(); self.stack_count=0; self.stack_total=len(subset); self.stack_cancel_requested=False; self.active_stack_method=method_key
        self.active_stack_range=(s,e)
        self.stack_running_mean=None; self.stack_preview_image=None
        self.stack_counter_text.set(f'0 / {self.stack_total} 帧 · 区间 {s}-{e}')
        self._set_stack_controls(True,False)
        requested_backend=self.compute_backend.get()
        workers=max(1,min(4,int(self.raw_workers.get())))
        self.worker=threading.Thread(target=self._stack,args=(list(subset),out,self.normalize_var.get(),self.output_depth.get(),self.live_preview_var.get(),max(1,int(self.preview_every.get())),requested_backend,workers,method_key),daemon=True)
        self.worker.start()

    def toggle_stack_pause(self):
        if not self.stack_active:return
        if self.stack_pause_event.is_set():
            self.stack_pause_event.clear(); self._set_stack_controls(True,False)
            self.status.set(f'继续堆栈 · 当前 {self.stack_count}/{self.stack_total} 帧')
        else:
            self.stack_pause_event.set(); self._set_stack_controls(True,True)
            self.status.set(f'已暂停 · 当前 {self.stack_count}/{self.stack_total} 帧 · 可继续或使用当前结果')

    def use_current_stack(self):
        if not self.stack_active or self.stack_count < 1:return
        self.stack_pause_event.set(); self.stack_stop_event.set()
        self.status.set(f'正在固定当前 {self.stack_count} 帧结果…')
        self._set_stack_controls(False,False)

    def cancel_stack(self):
        if not self.stack_active:return
        if not messagebox.askyesno(APP_NAME,'取消本次堆栈？\n\n当前临时结果不会保存。'):return
        self.stack_cancel_requested=True; self.stack_stop_event.set(); self.stack_pause_event.clear(); self._set_stack_controls(False,False)
        self.status.set('正在取消堆栈…')

    def _stack(self, files, out, normalize, depth, live_preview=True, preview_every=1, requested_backend='自动', raw_workers=2, method='mean'):
        executor=None
        try:
            np,*_= _deps()
            backend, backend_desc, cp = choose_stack_backend(requested_backend)
            self.queue.put(('accel', (backend, backend_desc)))
            n=len(files); shape=None; ref_lum=None; stopped_by_user=False
            master_cpu=None; master_gpu=None
            raw_workers=max(1,min(int(raw_workers),4,n))
            decode_times=[]; stack_times=[]

            # Bounded prefetch: at most raw_workers decoded frames can coexist.
            # This uses threads because LibRaw/rawpy executes the heavy decoder in native code,
            # while avoiding large inter-process copies of 24–33 MP RGB arrays.
            executor=ThreadPoolExecutor(max_workers=raw_workers, thread_name_prefix='IceHaloRAW')
            futures={}
            next_submit=0
            def submit_one(i):
                if i < n and i not in futures:
                    futures[i]=executor.submit(read_linear_rgb, files[i])
            while next_submit < min(raw_workers,n):
                submit_one(next_submit); next_submit+=1

            processed=0
            for zero_idx,p in enumerate(files):
                idx=zero_idx+1
                while self.stack_pause_event.is_set() and not self.stack_stop_event.is_set():
                    time.sleep(0.05)
                if self.stack_stop_event.is_set():
                    stopped_by_user=True; break

                mode_name='Maximum' if method=='maximum' else 'Mean'
                self.queue.put(('status',f'{mode_name} · 并行解码 {idx}/{n}：{Path(p).name} · {backend}'))
                t0=time.perf_counter()
                fut=futures.pop(zero_idx)
                img=fut.result()
                decode_times.append(time.perf_counter()-t0)
                if next_submit < n:
                    submit_one(next_submit); next_submit+=1

                if shape is None:
                    shape=img.shape
                if img.shape!=shape:
                    raise RuntimeError(f'图像尺寸不一致：{Path(p).name}\n{img.shape} != {shape}')

                if normalize:
                    lum=robust_luminance(img)
                    if ref_lum is None: ref_lum=lum
                    if lum>1e-8: img=img*(ref_lum/lum)

                ts=time.perf_counter()
                if backend == 'CUDA' and cp is not None:
                    frame_gpu=cp.asarray(img, dtype=cp.float32)
                    if master_gpu is None:
                        master_gpu=frame_gpu.copy()
                    elif method == 'maximum':
                        cp.maximum(master_gpu, frame_gpu, out=master_gpu)
                    else:
                        # Incremental arithmetic mean; full master remains resident in VRAM.
                        master_gpu += (frame_gpu-master_gpu)/float(idx)
                    del frame_gpu
                else:
                    frame_cpu=img.astype(np.float32,copy=False)
                    if master_cpu is None:
                        master_cpu=frame_cpu.copy()
                    elif method == 'maximum':
                        np.maximum(master_cpu, frame_cpu, out=master_cpu)
                    else:
                        master_cpu += (frame_cpu-master_cpu)/float(idx)
                stack_times.append(time.perf_counter()-ts)
                processed=idx
                self.stack_count=idx

                self.queue.put(('progress',idx/n*100))
                self.queue.put(('stack_counter',(idx,n)))
                if live_preview and (idx==1 or idx%preview_every==0 or idx==n):
                    if backend == 'CUDA' and master_gpu is not None:
                        h,w=shape[:2]; step=max(1,int(max(h/1000,w/1500)))
                        proxy=cp.asnumpy(master_gpu[::step,::step])
                    else:
                        h,w=master_cpu.shape[:2]; step=max(1,int(max(h/1000,w/1500)))
                        proxy=master_cpu[::step,::step].copy()
                    self.queue.put(('live_preview',(proxy,idx,n)))

            if processed < 1:
                self.queue.put(('stack_cancelled',None)); return
            if stopped_by_user and getattr(self,'stack_cancel_requested',False):
                self.queue.put(('stack_cancelled',None)); return

            self.queue.put(('status','正在从计算后端生成最终 Master…'))
            if backend == 'CUDA' and master_gpu is not None:
                result=cp.asnumpy(master_gpu).astype(np.float32,copy=False)
                del master_gpu
                try: cp.get_default_memory_pool().free_all_blocks()
                except Exception: pass
            else:
                result=master_cpu.astype(np.float32,copy=True)

            save_tiff(out,result,float32=(depth=='32-bit float TIFF'))
            avg_decode=(sum(decode_times)/len(decode_times)) if decode_times else 0.0
            avg_stack=(sum(stack_times)/len(stack_times)) if stack_times else 0.0
            op_name='Maximum' if method=='maximum' else 'Mean'
            stats=f'{backend} · RAW等待均值 {avg_decode:.2f}s/帧 · {op_name} {avg_stack*1000:.1f}ms/帧 · 解码线程 {raw_workers}'
            self.queue.put(('stack_done',(out,result,processed,n,processed<n,stats,method)))
        except Exception as e:
            self.queue.put(('error',str(e)+'\n\n'+traceback.format_exc(limit=4)))
        finally:
            if executor is not None:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
    def _push_undo(self):
        if self.working_image is None:return
        self.undo_stack.append((self.working_image.copy(), self.is_linear))
        if len(self.undo_stack)>self.max_undo: self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack or self.working_image is None:return
        self.redo_stack.append((self.working_image.copy(),self.is_linear))
        self.working_image,self.is_linear=self.undo_stack.pop(); self._update_state(); self.refresh_preview()

    def redo(self):
        if not self.redo_stack or self.working_image is None:return
        self.undo_stack.append((self.working_image.copy(),self.is_linear))
        self.working_image,self.is_linear=self.redo_stack.pop(); self._update_state(); self.refresh_preview()

    def restore_linear_master(self):
        if self.linear_master is None:return
        self._push_undo(); self.working_image=self.linear_master.copy(); self.is_linear=True; self._update_state(); self.estimate_current_stretch(); self.refresh_preview()

    def _require_image(self):
        if self.working_image is None:
            messagebox.showwarning(APP_NAME,'请先完成堆栈或打开一张图像。'); return False
        return True

    def _require_nonlinear(self):
        if not self._require_image(): return False
        if self.is_linear:
            messagebox.showwarning(APP_NAME,'当前仍是 LINEAR 图像。\n\n请先在“拉伸”标签中应用 Asinh 拉伸，再进行该非线性处理。')
            return False
        return True

    def do_stretch(self):
        if not self._require_image():return
        if not self.is_linear:
            if not messagebox.askyesno(APP_NAME,'当前已经是 NONLINEAR。仍要再次应用拉伸吗？'):return
        self._push_undo(); self.status.set('正在应用 Asinh 拉伸…'); self.update_idletasks()
        self.working_image=apply_asinh_stretch(self.working_image,self.stretch_strength.get(),self.stretch_black.get())
        self.is_linear=False; self._update_state(); self.refresh_preview(); self.status.set('Asinh 拉伸完成')

    def do_basic(self):
        if not self._require_nonlinear():return
        self._push_undo(); cfg=self._basic_cfg_from_ui(proxy_scale=1.0); self.status.set('正在应用基础调整…'); self.update_idletasks()
        self.working_image=apply_base_editor(self.working_image,cfg,None); self.reset_basic(); self.status.set('基础调整完成')

    def reset_basic(self):
        for key,default in self.basic_defaults.items():
            self._set_var_silently(self.basic_vars[key], default)
        self.refresh_preview()

    def do_curve(self):
        if not self._require_nonlinear():return
        if not self._curves_any_active():
            self.status.set('当前曲线未修改')
            return
        self._push_undo(); self.status.set('正在应用曲线…'); self.update_idletasks()
        for ch in ['RGB','红色','绿色','蓝色','亮度']:
            pts = self.curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
            if not self._curve_is_identity(ch):
                self.working_image = apply_curve_lut(self.working_image, build_curve_lut(pts, 256), ch)
        self.reset_all_curves(); self.status.set('曲线调整完成')

    def do_usm(self):
        if not self._require_nonlinear():return
        self._push_undo(); self.status.set('正在计算 USM…'); self.update_idletasks()
        self.working_image=apply_usm(self.working_image,self.usm_amount.get(),self.usm_radius.get(),self.usm_threshold.get()); self._set_var_silently(self.usm_amount, 0.0); self.refresh_preview(); self.status.set('USM 完成')

    def do_highpass(self):
        if not self._require_nonlinear():return
        if not self.hp_enabled.get():
            self.status.set('High Pass 未启用')
            return
        self._push_undo(); self.status.set('正在计算 High Pass…'); self.update_idletasks()
        if self.hp_preview_type.get() == '滤镜本体':
            self.working_image = highpass_filter(self.working_image, self.hp_radius.get())
        else:
            self.working_image = apply_highpass(self.working_image, self.hp_radius.get(), self.hp_amount.get(), self.hp_mode.get())
        self.working_image = self._apply_hp_curve(self.working_image)
        self._set_var_silently(self.hp_enabled, False)
        self.refresh_preview(); self.status.set('High Pass 完成')

    def do_emboss(self):
        if not self._require_nonlinear():return
        if not self.emboss_enabled.get():
            self.status.set('浮雕未启用')
            return
        self._push_undo(); self.status.set('正在计算浮雕…'); self.update_idletasks()
        self.working_image = apply_emboss(
            self.working_image,
            self.emboss_angle.get(),
            self.emboss_height.get(),
            self.emboss_strength.get(),
            self.emboss_opacity.get(),
            self.emboss_blend.get(),
            self.emboss_style.get()
        )
        self._set_var_silently(self.emboss_enabled, False)
        self.refresh_preview(); self.status.set('浮雕完成')

    def _hp_curve_is_identity(self, channel):
        pts=self.hp_curve_points.get(channel, [(0.0,0.0),(1.0,1.0)])
        return len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6

    def _hp_curve_active(self):
        return bool(getattr(self,'hp_curve_enabled',tk.BooleanVar(value=False)).get()) and any(not self._hp_curve_is_identity(ch) for ch in ['RGB','红色','绿色','蓝色','亮度'])

    def _apply_hp_curve(self, img):
        if not self._hp_curve_active():
            return img
        out=img
        for ch in ['RGB','红色','绿色','蓝色','亮度']:
            pts=self.hp_curve_points.get(ch, [(0.0,0.0),(1.0,1.0)])
            if not self._hp_curve_is_identity(ch):
                out=apply_curve_lut(out, build_curve_lut(pts, 256), ch)
        return out

    def _hp_curve_hist_source(self):
        np,*_= _deps()
        img=self._preview_base_image()
        if img is None:
            return None
        return np.clip(img.astype(np.float32),0,1)

    def open_hp_curve_dialog(self):
        if not self._require_nonlinear():
            return
        StandaloneHPCurveDialog(self)

    def _update_state(self):
        if self.working_image is None:
            self.detail.set('LINEAR · 尚未生成 Master'); return
        h,w=self.working_image.shape[:2]
        stage='LINEAR · 32-bit Float' if self.is_linear else 'NONLINEAR · 32-bit Float'
        self.detail.set(f'{stage} · {w}×{h}')

    def _main_preview_current_scale(self):
        img=getattr(self,'_last_display_preview',None)
        if img is None:return max(0.01,float(getattr(self,'preview_zoom',1.0)))
        h,w=img.shape[:2];c=self.preview_canvas;cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);fit=min(cw/max(w,1),ch/max(h,1))
        return fit if getattr(self,'preview_fit_mode',True) else max(0.01,float(getattr(self,'preview_zoom',1.0)))
    def _main_preview_update_zoom_text(self,scale=None):
        if not hasattr(self,'preview_zoom_text'):return
        if getattr(self,'preview_fit_mode',True):self.preview_zoom_text.set('Fit')
        else:
            sc=self._main_preview_current_scale() if scale is None else float(scale);self.preview_zoom_text.set(f'{sc*100:.0f}%')
    def _main_preview_wheel(self,e):
        try:self._main_preview_zoom_step(1 if getattr(e,'delta',0)>0 else -1,getattr(e,'x',None),getattr(e,'y',None))
        except Exception:pass
        return 'break'
    def _main_preview_wheel_linux(self,e,direction):self._main_preview_zoom_step(direction,getattr(e,'x',None),getattr(e,'y',None));return 'break'
    def _main_preview_set_zoom(self,scale):
        old=self._main_preview_current_scale();new=max(0.05,min(20.0,float(scale)));self._main_preview_adjust_pan(old,new,None,None);self.preview_zoom=new;self.preview_fit_mode=False;self._main_preview_update_zoom_text(new);self._main_preview_redraw();self.preview_canvas.focus_set();return 'break'
    def _main_preview_zoom_step(self,direction,x=None,y=None):
        old=self._main_preview_current_scale();factor=1.12 if direction>0 else 1/1.12;new=max(0.05,min(20.0,old*factor))
        if abs(new-old)<1e-9:return
        self._main_preview_adjust_pan(old,new,x,y);self.preview_zoom=new;self.preview_fit_mode=False;self._main_preview_update_zoom_text(new);self._main_preview_redraw();self.status.set(f'预览缩放：{new*100:.0f}% · Z 回到 Fit')
    def _main_preview_adjust_pan(self,old_scale,new_scale,x=None,y=None):
        try:
            c=self.preview_canvas;cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];mx=cw/2 if x is None else float(x);my=ch/2 if y is None else float(y);rx=mx-(cw/2+px);ry=my-(ch/2+py);ratio=new_scale/max(old_scale,1e-9);self.preview_pan=[mx-cw/2-rx*ratio,my-ch/2-ry*ratio]
        except Exception:self.preview_pan=[0.0,0.0]
    def _main_preview_pan_start(self,e):
        self.preview_canvas.focus_set()
        if getattr(self,'preview_fit_mode',True):self.preview_pan_anchor=None;return 'break'
        self.preview_pan_anchor=(float(e.x),float(e.y),float(self.preview_pan[0]),float(self.preview_pan[1]));return 'break'
    def _main_preview_pan_drag(self,e):
        if not self.preview_pan_anchor:return 'break'
        x0,y0,px0,py0=self.preview_pan_anchor
        self.preview_pan=[px0+float(e.x)-x0,py0+float(e.y)-y0]
        self._main_preview_move_canvas_image_fast()
        return 'break'

    def _main_preview_move_canvas_image_fast(self):
        try:
            c=self.preview_canvas;item=getattr(self,'preview_image_item',None)
            if not item:return
            cw=max(c.winfo_width(),1);ch=max(c.winfo_height(),1);px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2]
            c.coords(item,int(cw/2+px),int(ch/2+py))
        except Exception:pass
    def _main_preview_pan_end(self,e):self.preview_pan_anchor=None;return 'break'
    def _main_preview_fit(self):
        self.preview_fit_mode=True;self.preview_pan=[0.0,0.0];self._main_preview_update_zoom_text();self._main_preview_redraw();self.preview_canvas.focus_set();self.status.set('预览已回到 Fit');return 'break'
    def _main_preview_redraw(self):
        disp=getattr(self,'_last_display_preview',None)
        if disp is None:
            if self.working_image is None and self.stack_preview_image is None:return
            self.refresh_preview();return
        self._render_main_preview(disp,update_hist=False)

    def _render_main_preview(self,disp,update_hist=True):
        try:
            np,_,Image,ImageTk,*_=_deps();cw=max(self.preview_canvas.winfo_width(),100);ch=max(self.preview_canvas.winfo_height(),100);h,w=disp.shape[:2];fit=min(cw/max(w,1),ch/max(h,1));scale=fit if getattr(self,'preview_fit_mode',True) else max(0.05,float(getattr(self,'preview_zoom',1.0)));nw=max(1,int(w*scale));nh=max(1,int(h*scale))
            src_key=(id(disp),h,w)
            if getattr(self,'_main_preview_pil_source_key',None)!=src_key:
                self._main_preview_pil_source=Image.fromarray((np.clip(disp,0,1)*255).astype(np.uint8),'RGB');self._main_preview_pil_source_key=src_key
            pil=self._main_preview_pil_source
            if (nw,nh)!=(w,h):pil=pil.resize((nw,nh),Image.Resampling.BILINEAR if self._slider_dragging else Image.Resampling.LANCZOS)
            self.preview_photo=ImageTk.PhotoImage(pil);self.preview_canvas.delete('all');px,py=(getattr(self,'preview_pan',[0.0,0.0]) or [0.0,0.0])[:2];cx=int(cw/2+px);cy=int(ch/2+py);self.preview_image_item=self.preview_canvas.create_image(cx,cy,image=self.preview_photo,anchor='center',tags=('preview_image',))
            if self.is_linear:badge='LINEAR · AUTO STRETCH PREVIEW' if self.auto_preview_var.get() else 'LINEAR · UNSTRETCHED'
            else:badge=f'NONLINEAR · 实时预览：{self.tabs.tab(self.tabs.select(), "text")}'
            self._main_preview_update_zoom_text(scale);zlabel='Fit' if getattr(self,'preview_fit_mode',True) else f'{scale*100:.0f}%';self.preview_canvas.create_text(10,10,anchor='nw',fill='#eeeeee',font=_ui_font(9),text=badge,tags=('preview_overlay',));self.preview_canvas.create_text(10,28,anchor='nw',fill='#d0d0d0',font=_ui_font(8),text=f'{zlabel} · 滚轮缩放 · 拖拽平移 · Z Fit',tags=('preview_overlay',))
            if update_hist and not self._slider_dragging:self.draw_histogram()
        except Exception as e:self.status.set('预览失败：'+str(e))

    def refresh_preview_fast(self):
        # Reuse the global debounced preview scheduler while curve points are dragged.
        self._slider_dragging = True
        self._schedule_preview(immediate=False)

    def refresh_preview(self):
        if self.working_image is None and self.stack_preview_image is None:return
        try:
            np, _, Image, ImageTk, *_ = _deps()
            disp = self._active_preview_image()
            if disp is None:
                return
            self._last_display_preview = disp
            self._render_main_preview(disp,update_hist=True)
        except Exception as e:
            self.status.set('预览失败：'+str(e))

    def draw_histogram(self):
        if not hasattr(self,'hist_canvas'):return
        c=self.hist_canvas; c.delete('all')
        if self.working_image is None and self.stack_preview_image is None:return
        try:
            np,*_= _deps(); img=getattr(self,'_last_display_preview',None)
            if img is None:
                img=self._active_preview_image()
            if img is None:
                return
            smp=np.clip(img[::8,::8],0,1)
            W=max(c.winfo_width(),100); H=max(c.winfo_height(),60)
            colors=['#ff6b6b','#6bff77','#6ba8ff']
            for k,col in enumerate(colors):
                hist,_=np.histogram(smp[...,k],bins=256,range=(0,1))
                hist=hist.astype(np.float64); hist=np.log1p(hist); m=hist.max() or 1; hist/=m
                pts=[]
                for i,v in enumerate(hist): pts.extend([i/(255)*(W-1), H-2-v*(H-6)])
                c.create_line(*pts,fill=col,width=1)
        except Exception: pass

    def export_current(self):
        if not self._require_image():return
        dlg=tk.Toplevel(self);dlg.title('批量导出处理分支');dlg.transient(self);dlg.grab_set();dlg.resizable(False,False)
        body=ttk.Frame(dlg,padding=14);body.pack(fill='both',expand=True)
        ttk.Label(body,text='以当前图像为共同输入，勾选要一次生成的独立处理结果。',wraplength=470).pack(anchor='w',pady=(0,8))
        ttk.Label(body,text='“USM → 通道”和“USM → 浮雕”是两条分支，互不串联。',foreground='#666666').pack(anchor='w',pady=(0,10))
        choices=[
            ('current','当前图像（不增加处理）',False),
            ('usm','仅 USM',True),
            ('usm_channel','USM → 通道混合器',True),
            ('usm_emboss','USM → 浮雕',True),
            ('usm_channel_emboss','USM → 通道混合器 → 浮雕',False),
        ]
        selected={key:tk.BooleanVar(value=default) for key,_label,default in choices}
        for key,label,_default in choices:ttk.Checkbutton(body,text=label,variable=selected[key]).pack(anchor='w',pady=2)
        name=tk.StringVar(value='IceHaloStack');fmt=tk.StringVar(value='16-bit TIFF')
        row=ttk.Frame(body);row.pack(fill='x',pady=(12,3));ttk.Label(row,text='文件名前缀').pack(side='left');ttk.Entry(row,textvariable=name,width=28).pack(side='right')
        row=ttk.Frame(body);row.pack(fill='x',pady=3);ttk.Label(row,text='格式').pack(side='left');ttk.Combobox(row,textvariable=fmt,state='readonly',width=18,values=['16-bit TIFF','PNG','JPEG']).pack(side='right')
        ttk.Label(body,text=f'当前 USM：Amount {self.usm_amount.get():g}% · Radius {self.usm_radius.get():g}px；分支使用当前通道与浮雕参数。',foreground='#666666',wraplength=470).pack(anchor='w',pady=(8,3))

        def start_export():
            enabled=[key for key,_label,_default in choices if selected[key].get()]
            if not enabled:
                messagebox.showwarning(APP_NAME,'请至少勾选一个处理结果。',parent=dlg);return
            folder=filedialog.askdirectory(title='选择批量导出文件夹',parent=dlg)
            if not folder:return
            prefix=re.sub(r'[<>:"/\\|?*]+','_',name.get().strip()) or 'IceHaloStack'
            params={
                'usm':(float(self.usm_amount.get()),float(self.usm_radius.get()),float(self.usm_threshold.get())),
                'channel':(self.channel_output.get(),bool(self.channel_mono.get()),float(self.channel_red.get()),float(self.channel_green.get()),float(self.channel_blue.get()),float(self.channel_constant.get()),bool(self.channel_noise_protect.get()),float(self.channel_noise_strength.get()),float(self.channel_noise_radius.get())),
                'emboss':(float(self.emboss_angle.get()),float(self.emboss_height.get()),float(self.emboss_strength.get()),float(self.emboss_opacity.get()),self.emboss_blend.get(),self.emboss_style.get()),
            }
            source=self.working_image.copy();format_name=fmt.get();dlg.destroy()
            self.status.set(f'正在批量导出 {len(enabled)} 个处理分支…')
            def work():
                try:
                    np,_,Image,*_=_deps();base=np.clip(source,0,1).astype(np.float32,copy=False)
                    usm_img=None
                    if any(k!='current' for k in enabled):usm_img=apply_usm(base,*params['usm'])
                    suffix={'current':'Current','usm':'USM','usm_channel':'USM_Channel','usm_emboss':'USM_Emboss','usm_channel_emboss':'USM_Channel_Emboss'}
                    written=[]
                    for key in enabled:
                        out=base if key=='current' else usm_img
                        if key in ('usm_channel','usm_channel_emboss'):out=apply_channel_mixer(out,*params['channel'])
                        if key in ('usm_emboss','usm_channel_emboss'):out=apply_emboss(out,*params['emboss'])
                        ext='.tif' if format_name=='16-bit TIFF' else ('.png' if format_name=='PNG' else '.jpg')
                        path=Path(folder)/f'{prefix}_{suffix[key]}{ext}';out=np.clip(out,0,1)
                        if ext=='.tif':save_tiff(str(path),out,float32=False)
                        elif ext=='.png':Image.fromarray((out*255).astype(np.uint8),'RGB').save(path)
                        else:Image.fromarray((out*255).astype(np.uint8),'RGB').save(path,quality=96,subsampling=0)
                        written.append(str(path))
                    self.queue.put(('variant_export_done',(folder,written)))
                except Exception as e:self.queue.put(('variant_export_error',str(e)))
            threading.Thread(target=work,daemon=True).start()
        buttons=ttk.Frame(body);buttons.pack(fill='x',pady=(12,0));ttk.Button(buttons,text='取消',command=dlg.destroy).pack(side='right');ttk.Button(buttons,text='选择文件夹并导出',style='Primary.TButton',command=start_export).pack(side='right',padx=(0,7))
        dlg.update_idletasks();dlg.geometry(f'+{self.winfo_rootx()+180}+{self.winfo_rooty()+100}')

    def _poll(self):
        try:
            while True:
                kind,val=self.queue.get_nowait()
                if kind=='status':
                    self.status.set(val)
                elif kind=='progress':
                    self.progress.set(val)
                elif kind=='stack_counter':
                    idx,total=val
                    self.stack_count=idx
                    self.stack_total=total
                    self.stack_counter_text.set(f'{idx} / {total} 帧')
                elif kind=='live_preview':
                    proxy,idx,total=val
                    # The worker sends only a reduced-resolution float32 proxy.
                    # Keep the full-resolution running mean in the worker; redraw only this proxy in Tk.
                    self.stack_preview_image=proxy
                    self.stack_count=idx
                    self.stack_total=total
                    self.stack_counter_text.set(f'{idx} / {total} 帧')
                    self.refresh_preview()
                elif kind=='stack_cancelled':
                    self.stack_preview_image=None
                    self._set_stack_controls(False,False)
                    self.progress.set(0)
                    self.stack_counter_text.set(f'0 / {self.stack_total} 帧')
                    self.status.set('堆栈已取消')
                elif kind=='accel':
                    backend,desc=val
                    self.accel_status.set((backend+' · '+desc) if backend=='CUDA' else ('CPU · '+desc))
                elif kind=='main_basic_preview':
                    serial,out,quality,err=val
                    self._main_async_preview_running=False
                    newest=(int(serial)==int(self._main_preview_request_serial))
                    try:still_basic=((not self.is_linear) and self.tabs.select()==str(self.tab_basic))
                    except Exception:still_basic=False
                    if err is None and out is not None and newest and still_basic:
                        self._last_display_preview=out
                        self._render_main_preview(out,update_hist=(quality!='drag'))
                    # If the user moved again while the worker was busy, launch exactly
                    # one new frame using the latest parameter snapshot. Old frames are
                    # never replayed, so dragging cannot build an unbounded backlog.
                    if int(self._main_preview_request_serial) > int(serial) or self._main_async_preview_pending:
                        self._main_async_preview_pending=False
                        try:self.after(0,self._run_scheduled_preview)
                        except Exception:pass
                    elif err:
                        self.status.set('预览计算失败：'+str(err))
                elif kind=='variant_export_done':
                    folder,written=val
                    self.status.set(f'批量导出完成：{len(written)} 个结果')
                    messagebox.showinfo(APP_NAME,f'批量导出完成。\n\n共 {len(written)} 个处理结果：\n{folder}',parent=self)
                elif kind=='variant_export_error':
                    self.status.set('批量导出失败')
                    messagebox.showerror(APP_NAME,'批量导出失败：\n'+str(val),parent=self)
                elif kind=='stack_done':
                    out,result,count,total,stopped_early,perf_stats,stack_method=val
                    self.progress.set(count/total*100 if total else 100)
                    self.linear_master=result.copy()
                    self.working_image=result.copy()
                    self.stack_preview_image=None
                    self.is_linear=True
                    self.image_path=out
                    self.stack_count=count
                    self.stack_total=total
                    self.stack_counter_text.set(f'{count} / {total} 帧')
                    self._set_stack_controls(False,False)
                    self.undo_stack.clear(); self.redo_stack.clear()
                    self._update_state(); self.estimate_current_stretch(); self.refresh_preview()
                    if stopped_early:
                        self.status.set(f'已使用当前结果 · {count}/{total} 帧 · {perf_stats}')
                        mode_cn='最大值' if stack_method=='maximum' else '平均值'
                        messagebox.showinfo(APP_NAME,f'已使用当前 {count}/{total} 帧的{mode_cn}堆栈结果。\n\n已保存 Master：\n{out}\n\n现在可以继续进行线性处理和拉伸。')
                    else:
                        self.progress.set(100)
                        mode_cn='最大值' if stack_method=='maximum' else '平均值'
                        self.status.set(mode_cn+'堆栈完成 · '+perf_stats)
                        messagebox.showinfo(APP_NAME,f'Linear {mode_cn}堆栈完成。\n\n已保存 Master：\n{out}\n\n现在可以直接在线性预览中检查结果，然后进入“拉伸”。')
                elif kind=='error':
                    self.stack_preview_image=None
                    self._set_stack_controls(False,False)
                    self.status.set('处理失败')
                    messagebox.showerror(APP_NAME,val)
        except Empty:
            pass
        self.after(50,self._poll)


if __name__=='__main__':
    try:
        App().mainloop()
    except Exception as e:
        root=tk.Tk(); root.withdraw(); messagebox.showerror('IceHaloStack 启动失败',str(e)+'\n\n'+traceback.format_exc(limit=4))
