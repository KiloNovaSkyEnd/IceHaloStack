"""Pure flow normalization, cache signatures, and Shared DAG planning."""

from __future__ import annotations

import copy
import json
from collections import Counter

from .performance import _GIB, _MIB


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
