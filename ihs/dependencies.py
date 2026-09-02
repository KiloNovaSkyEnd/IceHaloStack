"""Lazy loading for IceHaloStack's optional and required runtime dependencies."""

import os
import re
import shutil
import subprocess
from pathlib import Path


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
    local = Path(__file__).resolve().parent.parent / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if local.exists():
        return str(local)
    return None


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
