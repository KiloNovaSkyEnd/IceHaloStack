# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for package in ('imageio_ffmpeg', 'cupy'):
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ['icehalostack_engine.py'],
    pathex=[], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports + [
        'fastrlock', 'fastrlock.rlock',
        'cupy_backends.cuda._softlink', 'cupy_backends.cuda.stream',
        'cupy_backends.cuda.api._driver_enum', 'cupy_backends.cuda.api._runtime_enum',
        'ihs.services.ipc', 'ihs.services.stack_acceleration',
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'IPython', 'jupyter', 'pytest'],
    noarchive=False, optimize=1,
)
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
