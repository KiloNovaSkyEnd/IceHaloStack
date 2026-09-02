"""Numerical exposure and white-balance analysis and correction helpers."""

from __future__ import annotations

import copy
import math

from .dependencies import _deps
from .image_ops import apply_basic


_EWB_TONE_KEYS = ('contrast', 'highlights', 'shadows', 'whites', 'blacks')


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


def _ewb_resize_float(img,max_side=512):
    np,_,Image,_,_,_,cv2=_deps();h,w=img.shape[:2];m=max(h,w)
    if m<=max_side:return img.astype(np.float32,copy=False)
    scale=float(max_side)/float(m);nw=max(2,int(round(w*scale)));nh=max(2,int(round(h*scale)))
    if cv2 is not None:return cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA).astype(np.float32,copy=False)
    chans=[np.asarray(Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.BILINEAR),dtype=np.float32) for k in range(3)]
    return np.stack(chans,axis=2)


def _ewb_analysis_crop(img,cfg):
    if cfg.get('analysis_region')!='自定义 ROI':return img
    h,w=img.shape[:2];x0=int(round(w*cfg['roi_x']/100.0));y0=int(round(h*cfg['roi_y']/100.0));x1=int(round(w*(cfg['roi_x']+cfg['roi_w'])/100.0));y1=int(round(h*(cfg['roi_y']+cfg['roi_h'])/100.0))
    x0=max(0,min(w-1,x0));y0=max(0,min(h-1,y0));x1=max(x0+1,min(w,x1));y1=max(y0+1,min(h,y1));return img[y0:y1,x0:x1]


def _ewb_measure_proxy(img,cfg):
    """Return robust exposure and spatially balanced chroma metrics."""
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
    uniq={int(x):float(y) for x,y in zip(xs,ys)};xs=np.array(sorted(uniq),dtype=np.float64);ys=np.array([uniq[int(x)] for x in xs],dtype=np.float64)
    return np.interp(np.arange(n,dtype=np.float64),xs,ys,left=ys[0],right=ys[-1])


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
    local_e=_ewb_gaussian_smooth_1d(e,int(cfg.get('deflicker_radius',3)))
    flicker=e-local_e
    ev=np.zeros(n,dtype=np.float64)
    if cfg.get('exposure_enabled'):ev+=(et-local_e)*(float(cfg['exposure_strength'])/100.0)
    if cfg.get('deflicker_enabled'):ev-=flicker*(float(cfg.get('deflicker_strength',100.0))/100.0)
    ev=np.clip(ev,-float(cfg['exposure_max_ev']),float(cfg['exposure_max_ev']))
    p=max(0.0,float(cfg['wb_max_percent']))/100.0;loglim=math.log1p(p) if p>0 else 0.0
    dr=(rt-r)*(float(cfg['wb_strength'])/100.0) if cfg.get('wb_enabled') else np.zeros(n);db=(bt-b)*(float(cfg['wb_strength'])/100.0) if cfg.get('wb_enabled') else np.zeros(n)
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
    """Smooth an already-generated transition one more cumulative round."""
    np,*_=_deps();amount=max(0.0,min(100.0,float(cfg.get('smoothing_amount',50.0))));scale=amount/50.0
    eradius=max(1,int(round(float(cfg.get('exposure_radius',20))*max(0.05,scale))));wradius=max(1,int(round(float(cfg.get('wb_radius',30))*max(0.05,scale))))
    passes=max(1,min(10,int(cfg.get('smoothing_passes',2)))) if cfg.get('multi_pass_enabled') else 1
    et0=np.asarray(table['exposure_target'],dtype=np.float64);rt0=np.asarray(table['rlog_target'],dtype=np.float64);bt0=np.asarray(table['blog_target'],dtype=np.float64)
    es=et0.copy();rs=rt0.copy();bs=bt0.copy()
    if amount>1e-9:
        for _pass in range(passes):es=_ewb_gaussian_smooth_1d(es,eradius)
        rs,bs=_ewb_smooth_chroma_joint(rs,bs,wradius,passes)
    et=es.copy();rt=rs.copy();bt=bs.copy();n=len(et)
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


def _ewb_build_table_from_snapshot(measurements,cfg,progress=None):
    table=_ewb_build_correction_table(measurements['exposure_metric'],measurements['rlog_metric'],measurements['blog_metric'],cfg,cfg.get('anchors',[]),progress=progress)
    rounds=max(0,int(cfg.get('additional_smoothing_rounds',0)))
    for pos in range(rounds):
        table=_ewb_apply_additional_smoothing_round(table,cfg)
        if progress is not None:progress(89+int((pos+1)*8/max(1,rounds)),f'正在累计第 {pos+1} 轮再次平滑…')
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
