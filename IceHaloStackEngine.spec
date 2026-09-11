# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hiddenimports = [], [], []
for package in ('imageio_ffmpeg', 'cupy'):
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# NVRTC loads its builtins library dynamically, so binary dependency scanning
# cannot discover it. It is required for CuPy elementwise/reduction kernels.
cuda_root = Path(os.environ.get('CUDA_PATH', r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8'))
for nvrtc_builtins in (cuda_root / 'bin').glob('nvrtc-builtins64_*.dll'):
    binaries.append((str(nvrtc_builtins), '.'))
if (cuda_root / 'include').is_dir():
    datas.append((str(cuda_root / 'include'), 'cuda/include'))

a = Analysis(
    ['icehalostack_engine.py'],
    pathex=[], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports + [
        'fastrlock', 'fastrlock.rlock',
        'cupy', 'cupy._core', 'cupy._core._kernel',
        'cupy._core._dtype', 'cupy._core._routines_math',
        'cupy._core._routines_manipulation',
        'cupy_backends.cuda._softlink', 'cupy_backends.cuda.stream',
        'cupy_backends.cuda.api._driver_enum', 'cupy_backends.cuda.api._runtime_enum',
        'ihs.services.ipc', 'ihs.services.stack_acceleration',
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'IPython', 'jupyter', 'pytest'],
    noarchive=False, optimize=1,
)

# CuPy's package-level imports expose optional FFT, solver, sparse, random and
# neural-network backends. The stack accumulator only uses elementwise add,
# maximum and mean, so shipping those CUDA libraries adds ~1.5 GiB without a
# reachable code path. Keep CuPy's core/CUB/NVRTC modules and remove only the
# optional backend binaries after dependency analysis.
_unused_cuda_names = (
    'cublaslt64_', 'cublas64_', 'cusolver64_', 'cusparse64_',
    'cufft64_', 'curand64_', 'cudnn64_',
)
_unused_backend_modules = (
    'cupy_backends\\cuda\\libs\\cublas.',
    'cupy_backends\\cuda\\libs\\cusolver.',
    'cupy_backends\\cuda\\libs\\cusparse.',
    'cupy_backends\\cuda\\libs\\cufft.',
    'cupy_backends\\cuda\\libs\\curand.',
    'cupy_backends\\cuda\\libs\\cudnn.',
    'cupy_backends\\cuda\\libs\\cutensor.',
    'cupy_backends\\cuda\\libs\\nccl.',
)
_unused_binary_fragments = (
    'cupyx\\',
    'cupy\\cuda\\thrust.',
    'opencv_videoio_ffmpeg',
    'pil\\_avif.',
)
def _keep_stack_binary(entry):
    destination = entry[0].lower().replace('/', '\\')
    filename = destination.rsplit('\\', 1)[-1]
    return not any(filename.startswith(name) for name in _unused_cuda_names) \
        and not any(name in destination for name in _unused_backend_modules) \
        and not any(name in destination for name in _unused_binary_fragments)

a.binaries = [entry for entry in a.binaries if _keep_stack_binary(entry)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='IceHaloStackEngine', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon='assets/icon/icehalostack.ico',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               upx_exclude=[], name='IceHaloStackEngine')
