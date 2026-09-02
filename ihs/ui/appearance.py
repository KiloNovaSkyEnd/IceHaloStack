"""Theme, translation, typography, high-DPI and scrolling helpers."""

from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from pathlib import Path

import tkinter as tk
from tkinter import ttk


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
