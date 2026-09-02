"""Pure flow normalization, cache signatures, and Shared DAG planning."""

from __future__ import annotations

import copy
import json
import time
from collections import Counter

from .dependencies import _deps
from .image_ops import (
    apply_asinh_stretch, apply_base_editor, apply_usm,
    background_suppression, apply_curve_lut, build_curve_lut,
    apply_highpass, apply_emboss, apply_channel_mixer,
)
from .performance import (
    _GIB, _MIB, _system_memory_status, _process_memory_rss,
)


NODE_ORDER = [
    ('stack','Stack\n堆栈'),('stretch','Stretch\n拉伸'),
    ('basic','Base\n基础调色'),('usm','USM\n锐化'),
    ('bgr','BGR\n背景+曲线'),('highpass','High Pass\n高反差保留'),
    ('emboss','Emboss\n浮雕'),('br','BR\n通道混合器'),
    ('output','Output\n输出'),
]


def default_edges(present_nodes=None,node_order=NODE_ORDER):
    present=set(present_nodes or [k for k,_ in node_order])
    order=[k for k,_ in node_order if k in present]
    return [(order[i],order[i+1]) for i in range(len(order)-1)]


def normalize_flow(flow,default_cfg,default_layout,node_order=NODE_ORDER):
    """Repair one flow in place using the v0.9.6.7 compatibility rules."""
    cfg=flow.setdefault('cfg',{})
    for dk,dv in default_cfg.items():cfg.setdefault(dk,copy.deepcopy(dv))
    if 'base_curves' not in flow or not isinstance(flow.get('base_curves'),dict):flow['base_curves']={k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']}
    if 'delete_sequence_after_video_only' not in flow.get('output',{}):flow.setdefault('output',{})['delete_sequence_after_video_only']=True
    if 'bgr' not in cfg:cfg['bgr']=bool(cfg.get('background',False) or cfg.get('curves',False))
    if 'br' not in cfg:cfg['br']=bool(cfg.get('channel',False))
    if 'channel' not in cfg:cfg['channel']=cfg.get('br',False)
    allowed=[k for k,_ in node_order];allowed_set=set(allowed)
    present=flow.get('present_nodes',allowed[:])
    if not isinstance(present,list):present=allowed[:]
    present=[k for k in present if k in allowed_set]
    if 'stack' not in present:present.insert(0,'stack')
    if 'output' not in present:present.append('output')
    dedup=[]
    for key in allowed:
        if key in present and key not in dedup:dedup.append(key)
    flow['present_nodes']=dedup
    if 'layout' not in flow or not isinstance(flow.get('layout'),dict):
        flow['layout']=copy.deepcopy(default_layout)
    else:
        for key,value in default_layout.items():flow['layout'].setdefault(key,value)
        for old in ('background','curves','channel'):flow['layout'].pop(old,None)
    edges=flow.get('edges',[])
    if not isinstance(edges,list):edges=[]
    clean=[]
    for edge in edges:
        try:a,b=edge
        except Exception:continue
        if a in flow['present_nodes'] and b in flow['present_nodes'] and a!=b and (a,b) not in clean:clean.append((a,b))
    flow['edges']=clean or default_edges(flow['present_nodes'],node_order)
    return flow


def workflow_snapshot(flows,selected_flow):
    return {'flows':copy.deepcopy(flows),'selected_flow':int(selected_flow or 0)}


def workflow_states_equal(first,second):
    try:return first==second
    except Exception:return False


def commit_workflow_history(before,after,undo,redo,limit,label='节点操作'):
    if workflow_states_equal(before,after):return False
    undo.append({'state':copy.deepcopy(before),'label':label})
    if len(undo)>limit:undo[:]=undo[-limit:]
    redo.clear()
    return True


def workflow_history_undo(current,undo,redo,limit):
    if not undo:return None
    item=undo.pop();redo.append({'state':current,'label':item.get('label','节点操作')})
    if len(redo)>limit:redo[:]=redo[-limit:]
    return item


def workflow_history_redo(current,undo,redo,limit):
    if not redo:return None
    item=redo.pop();undo.append({'state':current,'label':item.get('label','节点操作')})
    if len(undo)>limit:undo[:]=undo[-limit:]
    return item


def restore_workflow_snapshot(state,default_flow_factory,default_cfg,default_layout,node_order=NODE_ORDER):
    flows=copy.deepcopy(state.get('flows',[]))
    if not flows:flows=[default_flow_factory()]
    for index,flow in enumerate(flows):flows[index]=normalize_flow(flow,default_cfg,default_layout,node_order)
    selected=max(0,min(len(flows)-1,int(state.get('selected_flow',0) or 0)))
    return flows,selected


def node_enabled(flow,key):
    if key not in flow.get('present_nodes',[]):return False
    cfg=flow['cfg']
    if key in ('stack','output'):return True
    if key=='bgr':return bool(cfg.get('bgr',False))
    if key=='br':return bool(cfg.get('br',False))
    return bool(cfg.get(key,False))


def flow_exec_order(flow,node_order=NODE_ORDER):
    nodes=[k for k,_ in node_order];node_set=set(nodes)
    edges=[(a,b) for a,b in flow.get('edges',[]) if a in node_set and b in node_set and a!=b]
    adj={k:[] for k in nodes};rev={k:[] for k in nodes}
    for a,b in edges:
        if b not in adj[a]:adj[a].append(b);rev[b].append(a)
    reach=set();stack=['stack']
    while stack:
        node=stack.pop()
        if node in reach:continue
        reach.add(node);stack.extend(adj.get(node,[]))
    to_out=set();stack=['output']
    while stack:
        node=stack.pop()
        if node in to_out:continue
        to_out.add(node);stack.extend(rev.get(node,[]))
    relevant=reach&to_out
    if 'output' not in relevant:return []
    indeg={k:0 for k in relevant}
    for a,b in edges:
        if a in relevant and b in relevant:indeg[b]+=1
    queue=[node for node in nodes if node in relevant and indeg[node]==0];order=[]
    while queue:
        node=queue.pop(0);order.append(node)
        for child in adj.get(node,[]):
            if child not in relevant:continue
            indeg[child]-=1
            if indeg[child]==0:queue.append(child)
    if len(order)!=len(relevant):raise ValueError('流程图中存在循环，无法执行。')
    return [node for node in order if node not in ('stack','output')]


def node_signature(flow,node):
    """Return only parameters that can change this node's pixels."""
    cfg=flow['cfg']
    base_keys=(
        'exposure','contrast','highlights','shadows','whites','blacks',
        'temperature','tint','texture','clarity','dehaze','base_curve',
        'hsl_hue','hsl_sat','hsl_lum','cg_shadow_h','cg_shadow_s','cg_mid_h','cg_mid_s','cg_high_h','cg_high_s','cg_balance',
        'detail_sharpen','detail_radius','luma_nr','chroma_nr','opt_distortion','opt_vignette','opt_ca',
        'cal_red_h','cal_red_s','cal_green_h','cal_green_s','cal_blue_h','cal_blue_s','_proxy_scale')
    base_keys=base_keys+tuple(f'mix_{color}_{axis}' for color in ('red','orange','yellow','green','aqua','blue','purple','magenta') for axis in ('h','s','l'))
    keysets={
        'stretch':('stretch_strength','stretch_black'),'basic':base_keys,
        'usm':('usm_amount','usm_radius','usm_threshold','usm_passes'),
        'bgr':('background','bg_radius','bg_strength','curves'),
        'highpass':('hp_radius','hp_amount','hp_mode'),
        'emboss':('emboss_angle','emboss_height','emboss_amount','emboss_opacity','emboss_blend','emboss_style'),
        'br':('channel_output','channel_mono','channel_red','channel_green','channel_blue','channel_constant','channel_noise','channel_noise_strength','channel_noise_radius'),
    }
    values={key:cfg.get(key) for key in keysets.get(node,())}
    if node=='basic':values['_proxy_scale']=cfg.get('_proxy_scale',1.0);values['base_curves']=flow.get('base_curves',{})
    elif node=='bgr':values['curves_points']=flow.get('curves',{})
    def canonical(value):
        if isinstance(value,bool) or value is None or isinstance(value,str):return value
        if isinstance(value,(int,float)):return float(value)
        if isinstance(value,(list,tuple)):return [canonical(item) for item in value]
        if isinstance(value,dict):return {str(key):canonical(item) for key,item in sorted(value.items(),key=lambda pair:str(pair[0]))}
        try:return float(value)
        except Exception:return repr(value)
    values=canonical(values)
    try:return json.dumps(values,sort_keys=True,ensure_ascii=True,separators=(',',':'))
    except Exception:return repr(values)


def prepare_shared_node_dag(flows,node_order=NODE_ORDER):
    plans=[];occurrences=Counter();naive_nodes=0;parameter_occurrences=Counter()
    for flow in flows:
        parent=('MASTER',);steps=[]
        for node in flow_exec_order(flow,node_order):
            if not node_enabled(flow,node):continue
            signature=node_signature(flow,node);key=(parent,node,signature)
            steps.append((key,node));occurrences[key]+=1;parameter_occurrences[(node,signature)]+=1;naive_nodes+=1;parent=key
        plans.append(steps)
    shared_keys=sum(1 for count in occurrences.values() if count>1)
    reusable_uses=sum(max(0,count-1) for count in occurrences.values())
    reusable_by_node=Counter();shared_keys_by_node=Counter();parameter_reuse_by_node=Counter()
    for key,count in occurrences.items():
        if count>1:
            node=key[1];shared_keys_by_node[node]+=1;reusable_by_node[node]+=count-1
    for (node,_signature),count in parameter_occurrences.items():
        if count>1:parameter_reuse_by_node[node]+=count-1
    metadata={'naive_nodes':naive_nodes,'shared_keys':shared_keys,'reusable_uses':reusable_uses,
              'reusable_by_node':dict(reusable_by_node),'shared_keys_by_node':dict(shared_keys_by_node),
              'parameter_reuse_by_node':dict(parameter_reuse_by_node)}
    return plans,occurrences,metadata


def shared_dag_cache_cap(policy):
    strategy=str((policy or {}).get('strategy','Balanced'))
    share={'Memory Saver':0.08,'Balanced':0.16,'Maximum Performance':0.22}.get(strategy,0.16)
    return max(64*_MIB,int((policy or {}).get('limit_bytes',4*_GIB)*share))


def release_shared_flow_refs(steps,remaining,cache,cache_state):
    for key,_node in steps:
        if key not in remaining:continue
        remaining[key]-=1
        if remaining[key]<=0:
            remaining.pop(key,None);old=cache.pop(key,None)
            if old is not None:cache_state['bytes']=max(0,cache_state['bytes']-int(getattr(old,'nbytes',0)))


def apply_single_flow_node(out,node,flow):
    """Apply one node using the v0.9.6.7 preview/final pixel implementation."""
    cfg=flow['cfg'];curves=flow['curves']
    if node=='stretch':
        if cfg.get('stretch',False):out=apply_asinh_stretch(out,float(cfg.get('stretch_strength',8)),float(cfg.get('stretch_black',0)))
    elif node=='basic':
        if cfg.get('basic',False):out=apply_base_editor(out,cfg,flow.get('base_curves'))
    elif node=='usm':
        if cfg.get('usm',False):
            passes=max(1,min(10,int(cfg.get('usm_passes',1))))
            for _ in range(passes):out=apply_usm(out,float(cfg.get('usm_amount',100)),float(cfg.get('usm_radius',2)),float(cfg.get('usm_threshold',0)))
    elif node=='bgr':
        if cfg.get('bgr',False):
            if cfg.get('background',False):out=background_suppression(out,float(cfg.get('bg_radius',80)),float(cfg.get('bg_strength',100)))
            if cfg.get('curves',False) and curves:
                for channel in ['RGB','红色','绿色','蓝色','亮度']:
                    points=curves.get(channel,[(0.0,0.0),(1.0,1.0)])
                    identity=len(points)==2 and abs(points[0][0])<1e-6 and abs(points[0][1])<1e-6 and abs(points[1][0]-1)<1e-6 and abs(points[1][1]-1)<1e-6
                    if not identity:out=apply_curve_lut(out,build_curve_lut(points,256),channel)
    elif node=='highpass':
        if cfg.get('highpass',False):out=apply_highpass(out,float(cfg.get('hp_radius',10)),float(cfg.get('hp_amount',100)),str(cfg.get('hp_mode','Overlay')))
    elif node=='emboss':
        if cfg.get('emboss',False):out=apply_emboss(out,float(cfg.get('emboss_angle',-128)),float(cfg.get('emboss_height',1)),float(cfg.get('emboss_amount',100)),float(cfg.get('emboss_opacity',100)),str(cfg.get('emboss_blend','Normal')),str(cfg.get('emboss_style','Photoshop Emboss')))
    elif node=='br':
        if cfg.get('br',False):
            out=apply_channel_mixer(out,cfg.get('channel_output','灰色'),bool(cfg.get('channel_mono',True)),float(cfg.get('channel_red',40)),float(cfg.get('channel_green',40)),float(cfg.get('channel_blue',20)),float(cfg.get('channel_constant',0)),bool(cfg.get('channel_noise',True)),float(cfg.get('channel_noise_strength',30)),float(cfg.get('channel_noise_radius',0.8)))
    return out


def apply_flow_pipeline(img,flow,node_order=NODE_ORDER):
    np,*_=_deps();out=img.astype(np.float32,copy=True)
    for node in flow_exec_order(flow,node_order):out=apply_single_flow_node(out,node,flow)
    return np.clip(out,0,1).astype(np.float32)


def preview_cache_get(cache,cache_order,key):
    value=cache.get(key)
    if value is None:return None
    try:cache_order.remove(key)
    except ValueError:pass
    cache_order.append(key)
    return value


def preview_cache_put(cache,cache_order,key,value,cache_limit):
    cache[key]=value
    try:cache_order.remove(key)
    except ValueError:pass
    cache_order.append(key)
    while len(cache_order)>max(4,int(cache_limit)):
        old=cache_order.pop(0);cache.pop(old,None)


def clear_preview_stage_cache(cache,cache_order):
    cache.clear();cache_order.clear()


def apply_flow_pipeline_preview_cached(img,flow,quality,cache,cache_order,cache_limit,reference_serial,is_cancelled=None,stop_node=None,node_order=NODE_ORDER):
    """Run a faithful node preview with bounded per-stage caching."""
    np,*_=_deps();out=img.astype(np.float32,copy=True);order=flow_exec_order(flow,node_order)
    chain=('base',quality,int(reference_serial),tuple(order),out.shape)
    for node in order:
        if is_cancelled is not None and is_cancelled():return None
        signature=node_signature(flow,node)
        if quality=='hq':out=apply_single_flow_node(out,node,flow)
        else:
            key=(chain,node,signature);cached=preview_cache_get(cache,cache_order,key)
            if cached is not None:out=cached
            else:
                out=apply_single_flow_node(out,node,flow)
                if is_cancelled is not None and is_cancelled():return None
                preview_cache_put(cache,cache_order,key,out.astype(np.float32,copy=True),cache_limit)
            chain=(chain,node,signature)
        if stop_node and node==stop_node:break
    if is_cancelled is not None and is_cancelled():return None
    return np.clip(out,0,1).astype(np.float32)


def execute_shared_flow(master,flow,steps,remaining,cache,cache_state,stats,policy,perf=None):
    """Execute one flow with RAM-only reuse of identical upstream node results."""
    np,*_=_deps();out=None;cap=shared_dag_cache_cap(policy)
    limit=max(1,int((policy or {}).get('limit_bytes',4*_GIB)))
    reserve=max(512*_MIB,int((policy or {}).get('system_reserve_bytes',4*_GIB)))
    for key,node in steps:
        cached=cache.get(key)
        if cached is not None:
            out=cached;stats['hits']+=1;stats.setdefault('hits_by_node',Counter())[node]+=1;continue
        if out is None:out=master.astype(np.float32,copy=True)
        if perf is not None:perf.touch('node:'+str(node))
        started=time.monotonic();out=apply_single_flow_node(out,node,flow);elapsed=time.monotonic()-started
        stats['computes']+=1;stats.setdefault('computes_by_node',Counter())[node]+=1
        if perf is not None:perf.record_node(node,elapsed)
        if remaining.get(key,0)>1:
            size=int(getattr(out,'nbytes',0));_,available=_system_memory_status();rss=_process_memory_rss()
            safe=(size>0 and cache_state['bytes']+size<=cap and rss<limit*0.93 and (available<=0 or available>max(512*_MIB,int(reserve*0.70))))
            if safe:
                cache[key]=out;cache_state['bytes']+=size;cache_state['peak']=max(cache_state['peak'],cache_state['bytes']);stats['stores']+=1
            else:stats['budget_skips']+=1
    if out is None:out=master.astype(np.float32,copy=True)
    return np.clip(out,0,1).astype(np.float32)


def preset_payload(flow,node_order=NODE_ORDER,default_layout=None):
    layout=default_layout or {}
    present=flow.get('present_nodes',[key for key,_ in node_order])
    return {'format':'IceHaloStackFlowPreset','version':5,'name':flow['name'],'cfg':copy.deepcopy(flow['cfg']),'curves':copy.deepcopy(flow['curves']),'base_curves':copy.deepcopy(flow.get('base_curves',{})),'present_nodes':copy.deepcopy(present),'layout':copy.deepcopy(flow.get('layout',layout)),'edges':copy.deepcopy(flow.get('edges',default_edges(present,node_order))),'output':copy.deepcopy(flow['output'])}


def flow_from_payload(data,base_flow,default_cfg,default_layout,node_order=NODE_ORDER):
    if not isinstance(data,dict) or data.get('format')!='IceHaloStackFlowPreset':raise ValueError('不是有效的 IceHaloStack 流程预设。')
    flow=base_flow;flow['cfg'].update(data.get('cfg',{}));flow['curves']=data.get('curves',flow['curves']);flow['base_curves']=data.get('base_curves',flow.get('base_curves',{}));flow['present_nodes']=data.get('present_nodes',flow.get('present_nodes',[key for key,_ in node_order]));flow['layout']=data.get('layout',flow.get('layout',default_layout));flow['edges']=data.get('edges',flow.get('edges',default_edges(flow.get('present_nodes',[key for key,_ in node_order]),node_order)));flow['output'].update(data.get('output',{}))
    return normalize_flow(flow,default_cfg,default_layout,node_order)
