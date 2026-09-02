"""Image decoding, encoding, scaling, and atomic output helpers."""

import os
import threading
import time
from pathlib import Path

from .constants import RAW_EXTS
from .dependencies import _deps


def srgb_to_linear(arr):
    np, *_ = _deps()
    a = 0.055
    return np.where(arr <= 0.04045, arr/12.92, ((arr+a)/(1+a))**2.4).astype(np.float32)


def linear_to_srgb(arr):
    np, *_ = _deps()
    x = np.clip(arr, 0, 1)
    a = 0.055
    return np.where(x <= 0.0031308, 12.92*x, (1+a)*np.power(x,1/2.4)-a).astype(np.float32)


def read_linear_rgb(path: str):
    np, tifffile, Image, *_rest = _deps()
    rawpy = _rest[2]
    p = Path(path); ext = p.suffix.lower()
    if ext in RAW_EXTS:
        if rawpy is None:
            raise RuntimeError('RAW 解码组件 rawpy 未正确安装。')
        with rawpy.imread(str(p)) as raw:
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                use_auto_wb=False,
                no_auto_bright=True,
                gamma=(1,1),
                output_bps=16,
            )
        return rgb16.astype(np.float32) / 65535.0

    if ext in {'.tif','.tiff'}:
        arr = np.asarray(tifffile.imread(str(p)))
        if arr.ndim == 2:
            arr = np.repeat(arr[...,None], 3, axis=2)
        elif arr.ndim == 3 and arr.shape[-1] >= 3:
            arr = arr[...,:3]
        else:
            raise RuntimeError(f'不支持的 TIFF 数据形状：{arr.shape}')
        if np.issubdtype(arr.dtype, np.integer):
            arr = arr.astype(np.float32) / float(np.iinfo(arr.dtype).max)
        else:
            arr = arr.astype(np.float32)
        return arr

    if ext in {'.png','.jpg','.jpeg','.bmp'}:
        with Image.open(str(p)) as im:
            arr = np.asarray(im.convert('RGB'), dtype=np.float32) / 255.0
        return srgb_to_linear(arr)
    raise RuntimeError(f'不支持的文件格式：{p.suffix}')


def save_tiff(path: str, img, float32=False):
    np, tifffile, *_ = _deps()
    if float32:
        tifffile.imwrite(path, img.astype(np.float32), photometric='rgb')
    else:
        out = np.round(np.clip(img,0,1)*65535.0).astype(np.uint16)
        tifffile.imwrite(path, out, photometric='rgb')


def save_timelapse_sequence_frame(path, img, fmt='PNG 8-bit'):
    np, tifffile, Image, *_ = _deps()
    x = np.clip(img, 0, 1)
    if fmt == 'TIFF 32-bit Float':
        tifffile.imwrite(str(path), x.astype(np.float32), photometric='rgb')
    elif fmt == 'TIFF 16-bit':
        tifffile.imwrite(str(path), np.round(x*65535.0).astype(np.uint16), photometric='rgb')
    elif fmt == 'JPEG':
        Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB').save(str(path), quality=96, subsampling=0)
    else:
        Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB').save(str(path), compress_level=4)


def resize_pil_percent(pil, percent=100.0):
    _, _, Image, *_ = _deps()
    pct=max(1.0,float(percent))
    if abs(pct-100.0) < 1e-6:
        return pil
    sw,sh=pil.size
    nw=max(2,int(round(sw*pct/100.0))); nh=max(2,int(round(sh*pct/100.0)))
    nw -= nw % 2; nh -= nh % 2
    nw=max(2,nw); nh=max(2,nh)
    if (nw,nh)==(sw,sh):
        return pil
    return pil.resize((nw,nh), Image.Resampling.LANCZOS)



def resize_float_percent_array(img, percent=100.0):
    """Resize float RGB without an 8-bit round-trip; used before async output."""
    np, _, Image, *_rest = _deps();cv2=_rest[-1]
    pct=max(1.0,float(percent))
    if abs(pct-100.0)<1e-6:return img
    h,w=img.shape[:2];nw=max(2,int(round(w*pct/100.0)));nh=max(2,int(round(h*pct/100.0)))
    if cv2 is not None:
        return cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA).astype(np.float32,copy=False)
    chans=[np.asarray(Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.LANCZOS),dtype=np.float32) for k in range(3)]
    return np.stack(chans,axis=2)


def _ffmpeg_even_pad_args():
    """Pad at most one pixel on right/bottom so subsampled video codecs receive even dimensions.

    Sequence frames stay untouched; only the encoded video receives the padding.
    """
    return ['-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:black']


def save_timelapse_sequence_frame_scaled(path, img, fmt='PNG 8-bit', scale_percent=100.0):
    np, tifffile, Image, *_ = _deps()
    pct=max(1.0,float(scale_percent))
    if abs(pct-100.0) < 1e-6:
        return save_timelapse_sequence_frame(path, img, fmt)
    x = np.clip(img, 0, 1)
    pil = Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB')
    pil = resize_pil_percent(pil, pct)
    if fmt == 'TIFF 32-bit Float':
        arr = np.asarray(pil, dtype=np.float32) / 255.0
        tifffile.imwrite(str(path), arr.astype(np.float32), photometric='rgb')
    elif fmt == 'TIFF 16-bit':
        arr = np.asarray(pil, dtype=np.uint8)
        tifffile.imwrite(str(path), np.round(arr.astype(np.float32)/255.0*65535.0).astype(np.uint16), photometric='rgb')
    elif fmt == 'JPEG':
        pil.save(str(path), quality=96, subsampling=0)
    else:
        pil.save(str(path), compress_level=4)



def _atomic_temp_path(path):
    path=Path(path)
    # Never reuse a deterministic temporary name. Two app instances, a retry,
    # or a delayed scanner can otherwise contend for ``frame_N.ihs_tmp.png``.
    token=f'{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}'
    return path.with_name(path.stem+'.ihs_tmp.'+token+path.suffix)


def _atomic_replace_with_retry(tmp,path,timeout=5.0):
    """Replace an output after transient Windows sharing locks clear."""
    deadline=time.monotonic()+max(0.0,float(timeout));delay=0.025
    while True:
        try:
            os.replace(str(tmp),str(path));return
        except OSError as exc:
            # Windows Defender, Explorer thumbnails and indexing services can
            # briefly open a freshly encoded file without delete sharing.
            transient=isinstance(exc,PermissionError) or getattr(exc,'winerror',None) in (5,32,33)
            if not transient or time.monotonic()>=deadline:raise
            time.sleep(delay);delay=min(0.40,delay*1.7)


def save_timelapse_sequence_frame_atomic(path, img, fmt='PNG 8-bit', png_compression='Balanced'):
    """Write one final output frame atomically.

    The temporary sibling exists only while the final file is being encoded and
    is immediately renamed on success. This is not a stack/decode/node cache.
    """
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=_atomic_temp_path(path)
    try:
        try: tmp.unlink(missing_ok=True)
        except TypeError:
            if tmp.exists(): tmp.unlink()
        np, tifffile, Image, *_ = _deps()
        x=np.clip(img,0,1)
        if fmt=='TIFF 32-bit Float':
            tifffile.imwrite(str(tmp),x.astype(np.float32,copy=False),photometric='rgb')
        elif fmt=='TIFF 16-bit':
            tifffile.imwrite(str(tmp),np.round(x*65535.0).astype(np.uint16),photometric='rgb')
        elif fmt=='JPEG':
            Image.fromarray(np.round(x*255.0).astype(np.uint8),'RGB').save(str(tmp),format='JPEG',quality=96,subsampling=0)
        else:
            # v0.9.4.18l: prefer OpenCV's native PNG encoder when available.
            # It is lossless just like Pillow PNG, but is materially faster on
            # large 4K/6K frames in our benchmarks. Fall back to Pillow.
            levels={'Fast':1,'Balanced':3,'Maximum':9}
            level=int(levels.get(str(png_compression),3))
            u8=np.round(x*255.0).astype(np.uint8)
            cv2=_deps()[-1]
            wrote=False
            if cv2 is not None:
                try:
                    wrote=bool(cv2.imwrite(str(tmp),u8[...,::-1],[int(cv2.IMWRITE_PNG_COMPRESSION),level]))
                except Exception:
                    wrote=False
            if not wrote:
                Image.fromarray(u8,'RGB').save(str(tmp),format='PNG',compress_level=level)
        _atomic_replace_with_retry(tmp,path)
    except Exception:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass
        raise


def save_pil_png_atomic(path, pil, compress_level=3):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=_atomic_temp_path(path)
    try:
        try: tmp.unlink(missing_ok=True)
        except TypeError:
            if tmp.exists():tmp.unlink()
        pil.save(str(tmp),format='PNG',compress_level=int(max(0,min(9,compress_level))))
        _atomic_replace_with_retry(tmp,path)
    except Exception:
        try:tmp.unlink(missing_ok=True)
        except Exception:pass
        raise


def prepare_video_frame(img, preset='原始分辨率', custom_w=1920, custom_h=1080, fit_mode='Fill 裁切'):
    np, _, Image, *_ = _deps()
    x = np.clip(img, 0, 1)
    pil = Image.fromarray(np.round(x*255.0).astype(np.uint8), 'RGB')
    sw, sh = pil.size
    if preset == '原始分辨率':
        tw, th = sw, sh
    elif preset.startswith('16:9'):
        tw, th = 3840, 2160
    elif preset.startswith('4:3'):
        tw, th = 2880, 2160
    else:
        tw, th = max(2,int(custom_w)), max(2,int(custom_h))
    # yuv420p encoders require even dimensions; keep video dimensions valid.
    tw -= tw % 2; th -= th % 2
    tw=max(2,tw); th=max(2,th)
    if (sw,sh)==(tw,th):
        return pil
    if fit_mode == 'Stretch 拉伸':
        return pil.resize((tw,th), Image.Resampling.LANCZOS)
    scale = max(tw/sw, th/sh) if fit_mode == 'Fill 裁切' else min(tw/sw, th/sh)
    nw=max(1,int(round(sw*scale))); nh=max(1,int(round(sh*scale)))
    resized=pil.resize((nw,nh), Image.Resampling.LANCZOS)
    if fit_mode == 'Fill 裁切':
        left=max(0,(nw-tw)//2); top=max(0,(nh-th)//2)
        return resized.crop((left,top,left+tw,top+th))
    canvas=Image.new('RGB',(tw,th),(0,0,0))
    canvas.paste(resized,((tw-nw)//2,(th-nh)//2))
    return canvas


def make_float_preview_proxy(img, max_side=1200):
    """Create a float32 RGB preview proxy without altering the full-resolution master."""
    np, tifffile, Image, ImageTk, ImageFilter, rawpy, cv2 = _deps()
    h,w=img.shape[:2]
    max_side=max(256,int(max_side))
    scale=min(1.0, max_side/float(max(h,w)))
    if scale >= 0.999:
        return img.astype(np.float32,copy=True), 1.0
    nw=max(2,int(round(w*scale))); nh=max(2,int(round(h*scale)))
    if cv2 is not None:
        out=cv2.resize(img.astype(np.float32,copy=False),(nw,nh),interpolation=cv2.INTER_AREA)
    else:
        chans=[]
        for k in range(3):
            ch=Image.fromarray(img[...,k].astype(np.float32),mode='F').resize((nw,nh),Image.Resampling.BILINEAR)
            chans.append(np.asarray(ch,dtype=np.float32))
        out=np.stack(chans,axis=2)
    return np.clip(out,0,None).astype(np.float32), float(scale)

