"""Storage and cache management window."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from ihs.constants import APP_NAME
from ihs.ui.appearance import _ui_font


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
        pip_cache=self._pip_cache_dir();project=Path(__file__).resolve().parents[2]
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
