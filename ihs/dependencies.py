"""Lazy loading for IceHaloStack's optional and required runtime dependencies."""


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

