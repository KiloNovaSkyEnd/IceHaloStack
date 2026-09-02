"""Exposure/white-balance analysis workspace and controls."""

from __future__ import annotations

import copy
import math
import os
import threading
import traceback
from collections import OrderedDict
from pathlib import Path
from queue import Empty, Queue

import tkinter as tk
from tkinter import messagebox, ttk

from .appearance import _enforce_regular_typography, _make_vertical_scroll_area, _ui_font
from ..constants import APP_NAME, RAW_EXTS
from ..dependencies import _deps
from ..exposure_wb import (
    _EWB_TONE_KEYS, _ewb_apply_to_frame, _ewb_build_table_from_snapshot,
    _ewb_default_config, _ewb_measure_proxy, _ewb_resize_float,
    _ewb_temp_tint_to_log_delta,
)
from ..image_io import linear_to_srgb, read_linear_rgb, srgb_to_linear
from ..image_ops import apply_basic


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


def _ewb_make_thumbnail(proxy,max_side=144):
    np,*_=_deps();x=_ewb_resize_float(proxy,max_side);disp=np.clip(linear_to_srgb(np.clip(x,0,None)),0,1);return np.round(disp*255.0).astype(np.uint8)


def _ewb_analyze_files(files,cfg,progress=None,cancel_event=None):
    exp=[];rr=[];bb=[];thumbs=[];n=len(files)
    for i,path in enumerate(files):
        if cancel_event is not None and cancel_event.is_set():raise InterruptedError('cancelled')
        proxy=read_analysis_proxy(path,int(cfg.get('proxy_max_side',512)));e,r,b=_ewb_measure_proxy(proxy,cfg);exp.append(e);rr.append(r);bb.append(b);thumbs.append(_ewb_make_thumbnail(proxy,int(cfg.get('thumbnail_max_side',144))))
        if progress is not None:progress(i+1,n,Path(path).name)
    return {'exposure_metric':_deps()[0].asarray(exp,dtype=_deps()[0].float32),'rlog_metric':_deps()[0].asarray(rr,dtype=_deps()[0].float32),'blog_metric':_deps()[0].asarray(bb,dtype=_deps()[0].float32),'thumbs':thumbs,'count':n,'config':copy.deepcopy(cfg)}


def _ewb_rebuild_table(owner):
    m=getattr(owner,'_ewb_measurements',None);cfg=_ewb_config_snapshot(owner)
    if not m:return None
    if getattr(owner,'_ewb_measurement_signature',None)!=_ewb_measurement_signature_for(owner,cfg):return None
    table=_ewb_build_table_from_snapshot(m,cfg)
    owner._ewb_table=table;owner._ewb_display_table=table;owner._ewb_correction_signature=_ewb_correction_signature_for(owner,cfg)
    try:owner.ewb_status.set(_ewb_table_summary(table))
    except Exception:pass
    return table


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
