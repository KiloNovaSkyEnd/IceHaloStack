"""Focused regression for joint WB/chroma smoothing in v0.9.6.5."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as ihs
import ihs.exposure_wb as exposure_wb
import ihs.image_ops as image_ops

# These focused numeric tests do not decode files.  Keep them runnable in the
# lightweight development runtime where optional TIFF/RAW packages are absent.
ihs._deps=lambda:(np,None,None,None,None,None,None)
exposure_wb._deps=ihs._deps
image_ops._deps=ihs._deps


def cfg():
    c=ihs._ewb_default_config();c.update(wb_enabled=True,wb_strength=100.0,
        wb_radius=12,wb_max_percent=50.0,smoothing_amount=80.0,
        multi_pass_enabled=True,smoothing_passes=2,anchors=[])
    return c


def main():
    # Composition changes must not be interpreted as an illuminant change.
    h=w=160;base=np.full((h,w,3),0.30,dtype=np.float32)
    yy,xx=np.indices((h,w));neutral=((xx%10)<4)
    red=base.copy();blue=base.copy()
    red[~neutral]=np.array([0.62,0.16,0.11],dtype=np.float32)
    blue[~neutral]=np.array([0.10,0.18,0.62],dtype=np.float32)
    _,rr1,bb1=ihs._ewb_measure_proxy(red,{'analysis_region':'全画面'})
    _,rr2,bb2=ihs._ewb_measure_proxy(blue,{'analysis_region':'全画面'})
    assert np.hypot(rr1-rr2,bb1-bb2)<0.01,(rr1,bb1,rr2,bb2)

    # A true alternating green/magenta cast must be removed, not amplified.
    n=121;x=np.arange(n,dtype=np.float64);slow=0.025*np.sin(x/31.0)
    tint_flicker=0.045*((-1.0)**x);r=slow+tint_flicker;b=-slow+tint_flicker
    table=ihs._ewb_build_correction_table(np.zeros(n),r,b,cfg(),[])
    out_r=r+np.log(table['r_gain']);out_b=b+np.log(table['b_gain'])
    input_tint=0.5*(r+b);output_tint=0.5*(out_r+out_b)
    assert np.std(np.diff(output_tint))<np.std(np.diff(input_tint))*0.03

    # Vector limiting must preserve correction direction instead of clipping one
    # channel first and rotating the result toward green or magenta.
    correction=np.column_stack((np.log(table['r_gain']),np.log(table['b_gain'])))
    assert np.max(np.linalg.norm(correction,axis=1))<=np.log1p(0.5)+1e-6
    print('SPATIALLY_BALANCED_WB=PASS')
    print('GREEN_MAGENTA_ALTERNATION=PASS')
    print('JOINT_CHROMA_LIMIT=PASS')


if __name__=='__main__':main()
