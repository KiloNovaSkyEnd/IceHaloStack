"""Node workflow window, mechanically extracted from the v0.9.6.7 entry module.

The temporary dependency binder preserves the original module-level UI helpers while
those helpers are migrated into dedicated UI modules in later stages.
"""

from __future__ import annotations

import tkinter as tk

from ..node_workflow import NODE_ORDER as _NODE_WORKFLOW_ORDER


def bind_legacy_dependencies(namespace):
    """Bind the entry module's existing UI helpers without creating an import cycle."""
    for name, value in namespace.items():
        if not name.startswith("__"):
            globals()[name] = value


class TimelapseNodeWindow(tk.Toplevel):
    NODE_ORDER=_NODE_WORKFLOW_ORDER
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
        return _node_workflow_snapshot(self.flows,self.selected_flow.get())

    def _workflow_state_equal(self,a,b):
        return _node_workflow_states_equal(a,b)

    def _commit_workflow_history(self,before,label='节点操作'):
        after=self._workflow_state()
        changed=_commit_node_workflow_history(before,after,self.workflow_undo,self.workflow_redo,self.workflow_history_limit,label)
        if changed:self.status.set(f'已应用：{label} · Ctrl+Z 可撤回')

    def _restore_workflow_state(self,state):
        self.flows,idx=_restore_node_workflow_snapshot(
            state,lambda:self._new_flow('流程 1'),self._default_cfg(),
            self._default_node_layout(),self.NODE_ORDER,
        )
        self.selected_flow.set(idx)
        self._refresh_flow_list();self._draw_graph();self._schedule_preview(force=True)

    def workflow_undo_action(self):
        item=_node_workflow_history_undo(self._workflow_state(),self.workflow_undo,self.workflow_redo,self.workflow_history_limit)
        if item is None:
            self.status.set('没有可撤回的节点操作');return
        self._restore_workflow_state(item['state']);self.status.set(f"已撤回：{item.get('label','节点操作')} · Ctrl+Shift+Z 可重做")

    def workflow_redo_action(self):
        item=_node_workflow_history_redo(self._workflow_state(),self.workflow_undo,self.workflow_redo,self.workflow_history_limit)
        if item is None:
            self.status.set('没有可重做的节点操作');return
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
        return _node_default_edges(present_nodes,self.NODE_ORDER)

    def _new_flow(self,name):
        present=[k for k,_ in self.NODE_ORDER]
        flow={'name':name,'cfg':self._default_cfg(),'curves':{k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']},'base_curves':{k:[(0.0,0.0),(1.0,1.0)] for k in ['RGB','红色','绿色','蓝色','亮度']},'present_nodes':present[:],'layout':self._default_node_layout(),'edges':self._default_edges(present),'output':{'export_enabled':True,'save_sequence':True,'sequence_format':'PNG 8-bit','save_video':True,'delete_sequence_after_video_only':True,'video_format':'MP4 H.264','fps':24.0,'scale_percent':100.0,'name_template':'{index:02d}_{name}'}}
        self._arrange_u(flow)
        return flow

    def _normalize_flow(self,f):
        return _normalize_node_flow(f,self._default_cfg(),self._default_node_layout(),self.NODE_ORDER)

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
        return _node_flow_enabled(flow,key)

    def _get_active_edges(self,flow):
        flow=self._normalize_flow(flow)
        active={k for k in flow.get('present_nodes',[]) if self._node_enabled(flow,k)}
        return [(a,b) for a,b in flow.get('edges',[]) if a in active and b in active]

    def _flow_exec_order(self,flow):
        flow=self._normalize_flow(flow)
        return _node_flow_exec_order(flow,self.NODE_ORDER)

    def _apply_single_flow_node(self,out,node,flow):
        return _apply_node_flow_node(out,node,flow)

    def _apply_flow_pipeline(self,img,flow):
        flow=self._normalize_flow(flow)
        return _apply_node_flow_pipeline(img,flow,self.NODE_ORDER)

    def _prepare_shared_node_dag(self,flows):
        normalized=[self._normalize_flow(flow) for flow in flows]
        return _prepare_node_shared_dag(normalized,self.NODE_ORDER)

    @staticmethod
    def _shared_dag_cache_cap(policy):
        return _node_shared_dag_cache_cap(policy)

    def _execute_shared_flow(self,master,flow,steps,remaining,cache,cache_state,stats,policy):
        perf=getattr(self,'_active_performance_monitor',None)
        return _execute_node_shared_flow(master,flow,steps,remaining,cache,cache_state,stats,policy,perf)

    def _release_shared_flow_refs(self,steps,remaining,cache,cache_state):
        return _release_node_shared_flow_refs(steps,remaining,cache,cache_state)

    def _preview_node_signature(self,flow,node):
        return _node_flow_signature(flow,node)

    def _preview_cache_get(self,key):
        return _node_preview_cache_get(self.preview_stage_cache,self.preview_stage_cache_order,key)

    def _preview_cache_put(self,key,value):
        return _node_preview_cache_put(self.preview_stage_cache,self.preview_stage_cache_order,key,value,self.preview_cache_limit)

    def _clear_preview_stage_cache(self):
        return _clear_node_preview_stage_cache(self.preview_stage_cache,self.preview_stage_cache_order)

    def _apply_flow_pipeline_preview_cached(self,img,flow,quality,token=None,stop_node=None):
        flow=self._normalize_flow(flow)
        cancelled=lambda: token is not None and token != self.preview_token
        return _apply_node_flow_pipeline_preview_cached(
            img,flow,quality,self.preview_stage_cache,self.preview_stage_cache_order,
            self.preview_cache_limit,getattr(self,'_preview_reference_serial',0),
            cancelled,stop_node,self.NODE_ORDER,
        )

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
        return _node_preset_payload(f,self.NODE_ORDER,self._default_node_layout())
    def _flow_from_payload(self,data):
        if not isinstance(data,dict) or data.get('format')!='IceHaloStackFlowPreset':raise ValueError('不是有效的 IceHaloStack 流程预设。')
        f=self._new_flow(str(data.get('name','导入流程')))
        return _node_flow_from_payload(data,f,self._default_cfg(),self._default_node_layout(),self.NODE_ORDER)
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
                plan=_build_ffmpeg_video_plan(ff,fmt,fps,pattern,root,name,seq)
                if plan is None:plan=_build_ffmpeg_video_plan(ff,'GIF',fps,pattern,root,name,seq)
                vp=plan['video_path']
                if plan['palette_command'] is not None:
                    p1=_run_ffmpeg_command(plan['palette_command'],perf)
                    if p1.returncode!=0:raise RuntimeError('GIF palette 生成失败：'+(p1.stderr or '')[-1000:])
                pr=_run_ffmpeg_command(plan['encode_command'],perf)
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
