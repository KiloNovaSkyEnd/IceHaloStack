"""Pure, stateless image-processing operations used by IceHaloStack."""

import math

from .dependencies import _deps


def estimate_asinh_params(img):
    """Estimate suggested Asinh stretch parameters from a linear image."""
    np, *_ = _deps()
    lum = 0.2126*img[...,0] + 0.7152*img[...,1] + 0.0722*img[...,2]
    smp = lum[::8,::8].astype(np.float32)
    lo = float(np.quantile(smp, 0.002))
    hi = float(np.quantile(smp, 0.999))
    black = max(0.0, lo * 0.98)
    norm = max(hi - black, 1e-6)
    mid = float(np.quantile(np.clip((smp - black) / norm, 0, None), 0.60))
    mid = min(max(mid, 1e-6), 0.99)
    target = 0.32
    def f(s):
        return float(np.arcsinh(s*mid) / np.arcsinh(s))
    lo_s, hi_s = 0.05, 500.0
    for _ in range(36):
        m = (lo_s + hi_s) / 2.0
        if f(m) > target:
            hi_s = m
        else:
            lo_s = m
    strength = max(0.1, min((lo_s + hi_s) / 2.0, 500.0))
    return float(strength), float(black)


def auto_stretch_for_display(img, strength=None, black=None):
    """Display-only stretch using the same Asinh model as the real stretch."""
    if strength is None or black is None:
        strength, black = estimate_asinh_params(img)
    return apply_asinh_stretch(img, strength, black)


def apply_asinh_stretch(img, strength=8.0, black=0.0):
    np, *_ = _deps()
    x = np.maximum(img - black, 0.0)
    # robust normalization; preserves highlight headroom reasonably
    p = float(np.quantile(x[::8,::8], 0.9995))
    if p <= 1e-8: p = 1.0
    x = x / p
    s = max(float(strength), 0.01)
    y = np.arcsinh(s*x) / np.arcsinh(s)
    return np.clip(y,0,1).astype(np.float32)


def _blur(img, radius):
    np, *_rest = _deps(); cv2 = _rest[-1]
    radius = max(float(radius), 0.1)
    if cv2 is not None:
        sigma = max(radius, 0.1)
        return cv2.GaussianBlur(img, (0,0), sigmaX=sigma, sigmaY=sigma, borderType=cv2.BORDER_REFLECT)
    # fallback Pillow, slower and 8-bit internally for preview-like use
    Image = _rest[1]
    ImageFilter = _rest[3]
    arr8 = (np.clip(img,0,1)*255).astype(np.uint8)
    out = np.empty_like(img)
    pil = Image.fromarray(arr8, 'RGB').filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(pil,dtype=np.float32)/255.0


def apply_usm(img, amount=100.0, radius=2.0, threshold=0.0):
    np, *_ = _deps()
    blur = _blur(img, radius)
    detail = img - blur
    if threshold > 0:
        t = float(threshold)/255.0
        detail = np.where(np.abs(detail) >= t, detail, 0.0)
    out = img + (float(amount)/100.0)*detail
    return np.clip(out,0,1).astype(np.float32)


def overlay_blend(base, blend):
    np, *_ = _deps()
    return np.where(base <= 0.5, 2*base*blend, 1-2*(1-base)*(1-blend))


def softlight_blend(base, blend):
    np, *_ = _deps()
    return (1-2*blend)*base*base + 2*blend*base


def highpass_filter(img, radius=10.0, gain=1.0):
    """Photoshop-style High Pass filter output centered on neutral 50% gray."""
    np, *_ = _deps()
    blur = _blur(img, radius)
    # PS-like neutral gray carrier: low frequencies become 0.5, edges deviate around 0.5.
    hp = 0.5 + (img - blur) * float(gain)
    return np.clip(hp, 0, 1).astype(np.float32)


def apply_highpass(img, radius=10.0, amount=100.0, mode='Overlay'):
    """Apply High Pass as an effect layer blended back to the source."""
    np, *_ = _deps()
    hp = highpass_filter(img, radius, gain=1.0)
    if mode == 'Soft Light':
        mixed = softlight_blend(img, hp)
    elif mode == 'Linear Light':
        mixed = np.clip(img + 2*(hp-0.5),0,1)
    else:
        mixed = overlay_blend(img, hp)
    a = np.clip(float(amount)/100.0,0,1)
    return np.clip(img*(1-a)+mixed*a,0,1).astype(np.float32)


def _emboss_components(img, angle=135.0, height=1.0, amount=100.0):
    """Return source RGB, luminance, directional relief and gray emboss carrier."""
    np, *_rest = _deps(); cv2 = _rest[-1]
    x = np.clip(img.astype(np.float32), 0, 1)
    lum = (0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2]).astype(np.float32)
    a = math.radians(float(angle))
    h = max(float(height), 0.1)
    dx = math.cos(a) * h
    dy = -math.sin(a) * h
    if cv2 is not None:
        M1 = np.float32([[1,0, dx/2.0],[0,1, dy/2.0]])
        M2 = np.float32([[1,0,-dx/2.0],[0,1,-dy/2.0]])
        hi = cv2.warpAffine(lum, M1, (lum.shape[1],lum.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        lo = cv2.warpAffine(lum, M2, (lum.shape[1],lum.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        gx = cv2.Sobel(lum, cv2.CV_32F, 1, 0, ksize=3, borderType=cv2.BORDER_REFLECT)
        gy = cv2.Sobel(lum, cv2.CV_32F, 0, 1, ksize=3, borderType=cv2.BORDER_REFLECT)
        edge_mag = cv2.magnitude(gx, gy) * 0.25
    else:
        ix=int(round(dx/2.0)); iy=int(round(dy/2.0))
        hi=np.roll(np.roll(lum, iy, axis=0), ix, axis=1)
        lo=np.roll(np.roll(lum,-iy, axis=0),-ix, axis=1)
        gx=(np.roll(lum,-1,axis=1)-np.roll(lum,1,axis=1))*0.5
        gy=(np.roll(lum,-1,axis=0)-np.roll(lum,1,axis=0))*0.5
        edge_mag=np.sqrt(gx*gx+gy*gy)
    amount_scale=max(float(amount),0.0)/100.0
    directional=(hi-lo).astype(np.float32)
    relief=np.clip(0.5 + directional*(1.35*amount_scale), 0.0, 1.0)
    return x, lum, directional, relief, edge_mag, amount_scale


def _photoshop_emboss_filter(img, angle=135.0, height=1.0, amount=100.0):
    """PS-style Emboss approximation.

    Photoshop's published description of Emboss is a neutral/gray stamped
    surface whose edges retain the original fill color.  This implementation
    follows that visual model instead of merely preserving the source RGB
    everywhere.  Flat regions settle near 50% gray, directional relief creates
    the raised/recessed shading, and a broadened edge mask restores strong
    source chroma around the traced edges.
    """
    np, *_rest = _deps(); cv2 = _rest[-1]
    x = np.clip(img.astype(np.float32), 0, 1)
    lum = (0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2]).astype(np.float32)
    a = math.radians(float(angle))
    h = max(float(height), 0.1)
    dx = math.cos(a) * h
    dy = -math.sin(a) * h

    if cv2 is not None:
        M1=np.float32([[1,0, dx/2.0],[0,1, dy/2.0]])
        M2=np.float32([[1,0,-dx/2.0],[0,1,-dy/2.0]])
        lum_hi=cv2.warpAffine(lum,M1,(lum.shape[1],lum.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        lum_lo=cv2.warpAffine(lum,M2,(lum.shape[1],lum.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        rgb_hi=cv2.warpAffine(x,M1,(x.shape[1],x.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        rgb_lo=cv2.warpAffine(x,M2,(x.shape[1],x.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        gx=cv2.Sobel(lum,cv2.CV_32F,1,0,ksize=3,borderType=cv2.BORDER_REFLECT)
        gy=cv2.Sobel(lum,cv2.CV_32F,0,1,ksize=3,borderType=cv2.BORDER_REFLECT)
        edge=np.sqrt(gx*gx+gy*gy).astype(np.float32)
    else:
        ix=int(round(dx/2.0));iy=int(round(dy/2.0))
        lum_hi=np.roll(np.roll(lum,iy,axis=0),ix,axis=1)
        lum_lo=np.roll(np.roll(lum,-iy,axis=0),-ix,axis=1)
        rgb_hi=np.roll(np.roll(x,iy,axis=0),ix,axis=1)
        rgb_lo=np.roll(np.roll(x,-iy,axis=0),-ix,axis=1)
        gx=(np.roll(lum,-1,axis=1)-np.roll(lum,1,axis=1))*0.5
        gy=(np.roll(lum,-1,axis=0)-np.roll(lum,1,axis=0))*0.5
        edge=np.sqrt(gx*gx+gy*gy).astype(np.float32)

    amount_scale=max(float(amount),0.0)/100.0
    lum_dir=(lum_hi-lum_lo).astype(np.float32)
    rgb_dir=(rgb_hi-rgb_lo).astype(np.float32)

    # Neutral stamped carrier. Amount controls relief depth, as the PS Amount
    # control visually does, but the gain is compressed above 100% to avoid
    # premature clipping at the 500% end of the UI range.
    relief_gain=1.55*(0.65*min(amount_scale,1.0)+0.35*np.sqrt(max(amount_scale,0.0)))
    shade=np.clip(0.5 + lum_dir*relief_gain,0.0,1.0).astype(np.float32)

    # Edge tracing: combine Sobel energy with the directional difference and
    # broaden it slightly. This is the key difference from the old Gray mode:
    # Photoshop-like edges keep visibly more of the source fill color instead
    # of becoming almost monochrome.
    energy=np.abs(lum_dir)*(4.2+1.2*min(amount_scale,2.0)) + edge*(1.6+0.5*min(amount_scale,2.0))
    edge_mask=np.clip(energy,0.0,1.0).astype(np.float32)
    if cv2 is not None:
        sigma=max(0.35,min(3.0,h*0.32))
        edge_mask=cv2.GaussianBlur(edge_mask,(0,0),sigmaX=sigma,sigmaY=sigma,borderType=cv2.BORDER_REFLECT)
        edge_mask=np.clip(edge_mask*1.22,0.0,1.0)
    else:
        edge_mask=np.clip(edge_mask,0.0,1.0)

    source_chroma=x-lum[...,None]
    dir_lum=(0.2126*rgb_dir[...,0]+0.7152*rgb_dir[...,1]+0.0722*rgb_dir[...,2]).astype(np.float32)
    dir_chroma=rgb_dir-dir_lum[...,None]

    # At Amount=100, colored edge traces are deliberately strong.  Flat areas
    # remain neutral gray, matching the characteristic PS Emboss look, while
    # colored halo/cloud edges no longer wash out.
    color_gain=np.clip(0.62+0.38*min(amount_scale,1.0)+0.10*max(amount_scale-1.0,0.0),0.45,1.25)
    trace=(source_chroma*color_gain + dir_chroma*(0.30+0.12*min(amount_scale,2.0)))
    out=shade[...,None] + trace*edge_mask[...,None]

    # Very faint chroma shoulder around traced edges avoids the unnaturally
    # abrupt gray-to-color transition that made the previous mode look dull.
    shoulder=np.clip(edge_mask*0.38,0.0,0.38)[...,None]
    out += source_chroma*shoulder*(0.34+0.10*min(amount_scale,2.0))
    return np.clip(out,0,1).astype(np.float32)


def emboss_filter(img, angle=135.0, height=1.0, amount=100.0, style='Photoshop Emboss'):
    """Emboss filter body with PS-style, color-preserving and gray modes."""
    np, *_ = _deps()
    st=str(style or 'Photoshop Emboss').lower()
    if 'photoshop' in st or st.startswith('ps ') or 'ps-like' in st:
        return _photoshop_emboss_filter(img,angle,height,amount)
    x, lum, directional, relief, edge_mag, amount_scale = _emboss_components(img, angle, height, amount)
    if 'gray' in st or '灰' in st:
        chroma=x-lum[...,None]
        edge_mask=np.clip(edge_mag*(3.5 + 2.0*min(amount_scale,2.0)), 0.0, 1.0)[...,None]
        color_strength=np.clip(0.18 + 0.42*min(amount_scale,1.5), 0.0, 0.70)
        out=relief[...,None] + chroma*edge_mask*color_strength
        return np.clip(out,0,1).astype(np.float32)
    # Existing Color Emboss is intentionally preserved unchanged.
    target_lum=np.clip(lum + directional*(1.35*amount_scale),0.0,1.0)
    out=x + (target_lum-lum)[...,None]
    return np.clip(out,0,1).astype(np.float32)


def apply_emboss(img, angle=135.0, height=1.0, amount=100.0, opacity=100.0,
                 mode='Normal', style='Photoshop Emboss'):
    """Apply Emboss with selectable blend modes and opacity."""
    np, *_ = _deps()
    emb = emboss_filter(img, angle, height, amount, style=style)
    if mode == 'Overlay':
        mixed = overlay_blend(img, emb)
    elif mode == 'Soft Light':
        mixed = softlight_blend(img, emb)
    elif mode == 'Linear Light':
        st=str(style).lower()
        if 'gray' in st or '灰' in st or 'photoshop' in st or st.startswith('ps '):
            mixed = np.clip(img + 2*(emb-0.5),0,1)
        else:
            mixed = np.clip(img + 2*(emb-img),0,1)
    else:
        mixed = emb
    a = np.clip(float(opacity)/100.0,0,1)
    return np.clip(img*(1-a)+mixed*a,0,1).astype(np.float32)


def _smoothstep(a, b, x):
    np, *_ = _deps()
    t = np.clip((x-a)/max(b-a,1e-6), 0.0, 1.0)
    return t*t*(3.0-2.0*t)


def apply_basic(img, exposure=0.0, contrast=0.0, highlights=0.0, shadows=0.0,
                whites=0.0, blacks=0.0, vibrance=0.0, saturation=0.0,
                clarity=0.0, dehaze=0.0):
    """Camera-Raw-inspired basic tone adjustment with neutral fast paths.

    v0.9.4.18m avoids allocating tonal masks whose controls are neutral.  The
    active-control math is unchanged; only mathematically unused work is skipped.
    """
    np, *_ = _deps()
    ev=float(exposure); cv=float(contrast); hv0=float(highlights); sv0=float(shadows)
    wv0=float(whites); bv0=float(blacks); vib0=float(vibrance); sat0=float(saturation)
    cl0=float(clarity); dh0=float(dehaze)
    x=np.clip(img.astype(np.float32,copy=False),0,1)
    if abs(ev)>1e-7:
        x=np.clip(x*(2.0**ev),0,1).astype(np.float32,copy=False)
    else:
        # Keep callers isolated from in-place modifications further below.
        x=x.astype(np.float32,copy=True)

    tone_active=any(abs(v)>1e-7 for v in (cv,hv0,sv0,wv0,bv0))
    if tone_active:
        lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        y=lum.copy()
        if abs(sv0)>1e-7:
            sh_mask=1.0-_smoothstep(0.18,0.68,lum); sv=sv0/100.0
            if sv>=0:y += sv*0.55*sh_mask*(1.0-y)
            else:y += sv*0.38*sh_mask*y
        if abs(hv0)>1e-7:
            hi_mask=_smoothstep(0.35,0.88,lum); hv=hv0/100.0
            if hv>=0:y += hv*0.38*hi_mask*(1.0-y)
            else:y += hv*0.72*hi_mask*y
        if abs(wv0)>1e-7:
            white_mask=_smoothstep(0.68,0.98,lum); wv=wv0/100.0
            y += wv*0.42*white_mask*((1.0-y) if wv>=0 else y)
        if abs(bv0)>1e-7:
            black_mask=1.0-_smoothstep(0.02,0.34,lum); bv=bv0/100.0
            y += bv*0.42*black_mask*((1.0-y) if bv>=0 else y)
        c=cv/100.0
        if abs(c)>1e-7:
            shaped=0.5+0.5*np.tanh((y-0.5)*(2.0+2.6*abs(c)))/np.tanh(1.0+1.3*abs(c))
            if c>0:y=y*(1-c)+shaped*c
            else:y=y*(1+c)+(0.5+(y-0.5)*0.72)*(-c)
        y=np.clip(y,0,1)
        scale=y/np.maximum(lum,1e-5)
        x=np.clip(x*scale[...,None],0,1)

    if abs(cl0)>1e-7:
        blur=_blur(x,12.0);d=cl0/100.0
        l=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        protect=(1.0-0.55*_smoothstep(0.72,1.0,l))[...,None]
        x=x+d*0.75*(x-blur)*protect
    if abs(dh0)>1e-7:
        d=dh0/100.0;base=np.clip(x,0,1);local=_blur(base,48.0)
        l=np.clip(0.2126*base[...,0]+0.7152*base[...,1]+0.0722*base[...,2],0,1)
        if d>=0:
            protect=(1.0-0.72*_smoothstep(0.72,1.0,l))[...,None]
            enhanced=base+1.05*d*(base-local)*protect;bp=0.075*d
            enhanced=(enhanced-bp)/max(1.0-bp,0.25)
            x=base*(1.0-min(d,1.0)*0.25)+enhanced*min(d,1.0)*0.75
        else:
            haze=-d;x=base*(1.0-0.55*haze)+local*(0.55*haze)+0.045*haze

    if abs(sat0)>1e-7 or abs(vib0)>1e-7:
        x=np.clip(x,0,1);lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1);gray=lum[...,None]
        sat=sat0/100.0
        if abs(sat)>1e-7:x=gray+(x-gray)*(1.0+sat)
        vib=vib0/100.0
        if abs(vib)>1e-7:
            mx=x.max(axis=2);mn=x.min(axis=2);chroma=mx-mn;protect=np.clip(chroma/0.38,0,1);factor=1.0+vib*(1.0-protect);x=gray+(x-gray)*factor[...,None]
    return np.clip(x,0,1).astype(np.float32,copy=False)

def _rgb_to_hsv_np(rgb):
    np, *_ = _deps()
    x=np.clip(rgb,0,1).astype(np.float32)
    r,g,b=x[...,0],x[...,1],x[...,2]
    mx=np.maximum(np.maximum(r,g),b); mn=np.minimum(np.minimum(r,g),b); d=mx-mn
    h=np.zeros_like(mx,dtype=np.float32)
    nz=d>1e-8
    mr=(mx==r)&nz; mg=(mx==g)&nz; mb=(mx==b)&nz
    h[mr]=((g[mr]-b[mr])/d[mr])%6.0
    h[mg]=(b[mg]-r[mg])/d[mg]+2.0
    h[mb]=(r[mb]-g[mb])/d[mb]+4.0
    h=(h/6.0)%1.0
    sat=np.where(mx>1e-8,d/np.maximum(mx,1e-8),0.0).astype(np.float32)
    return h.astype(np.float32),sat,mx.astype(np.float32)


def _hsv_to_rgb_np(h,s,v):
    np, *_ = _deps()
    h=np.mod(h,1.0);s=np.clip(s,0,1);v=np.clip(v,0,1)
    q=h*6.0;i=np.floor(q).astype(np.int32)%6;f=q-np.floor(q)
    p=v*(1-s);qv=v*(1-f*s);t=v*(1-(1-f)*s)
    out=np.empty(h.shape+(3,),dtype=np.float32)
    choices=[(v,t,p),(qv,v,p),(p,v,t),(p,qv,v),(t,p,v),(v,p,qv)]
    for idx,(rr,gg,bb) in enumerate(choices):
        m=i==idx;out[...,0][m]=rr[m];out[...,1][m]=gg[m];out[...,2][m]=bb[m]
    return np.clip(out,0,1).astype(np.float32)


def apply_white_balance_post(img, temperature=0.0, tint=0.0):
    np, *_ = _deps()
    x=np.clip(img.astype(np.float32),0,1)
    t=np.clip(float(temperature)/100.0,-1,1);q=np.clip(float(tint)/100.0,-1,1)
    gains=np.array([np.exp(0.35*t+0.10*q),np.exp(-0.20*q),np.exp(-0.35*t+0.10*q)],dtype=np.float32)
    gains=gains/max(float((gains[0]*gains[1]*gains[2])**(1/3)),1e-6)
    return np.clip(x*gains[None,None,:],0,1).astype(np.float32)


def apply_presence_advanced(img, texture=0.0, clarity=0.0, dehaze=0.0, proxy_scale=1.0):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1);ps=max(float(proxy_scale),0.05)
    tex=float(texture)/100.0
    if abs(tex)>1e-7:
        blur=_blur(x,max(0.6,2.2*ps));detail=x-blur
        l=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        protect=(0.72+0.28*(1.0-_smoothstep(0.82,1.0,l)))[...,None]
        x=x+0.65*tex*detail*protect
    cl=float(clarity)/100.0
    if abs(cl)>1e-7:
        blur=_blur(np.clip(x,0,1),max(1.0,12.0*ps));detail=x-blur
        l=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
        mid=(0.45+0.55*(1.0-np.abs(l-0.5)*1.35))[...,None]
        x=x+0.82*cl*detail*mid
    dh=float(dehaze)/100.0
    if abs(dh)>1e-7:
        base=np.clip(x,0,1);local=_blur(base,max(2.0,48.0*ps));l=np.clip(0.2126*base[...,0]+0.7152*base[...,1]+0.0722*base[...,2],0,1)
        if dh>=0:
            protect=(1.0-0.78*_smoothstep(0.72,1.0,l))[...,None]
            detail=base-local
            candidate=base+1.18*dh*detail*protect
            bp=0.085*dh*(1.0-0.45*_smoothstep(0.55,1.0,l))[...,None]
            candidate=(candidate-bp)/np.maximum(1.0-bp,0.25)
            x=base*(1.0-0.80*min(dh,1.0))+candidate*(0.80*min(dh,1.0))
        else:
            haze=-dh;x=base*(1.0-0.58*haze)+local*(0.58*haze)+0.05*haze
    return np.clip(x,0,1).astype(np.float32)


def apply_global_hsl(img, hue=0.0, saturation=0.0, luminance=0.0):
    np, *_ = _deps();h,s,v=_rgb_to_hsv_np(img)
    h=np.mod(h+float(hue)/360.0,1.0);s=np.clip(s*(1.0+float(saturation)/100.0),0,1)
    lv=float(luminance)/100.0
    if lv>=0:v=v+lv*0.45*(1-v)
    else:v=v+lv*0.45*v
    return _hsv_to_rgb_np(h,s,np.clip(v,0,1))


def _hue_weight(h,center_deg,width_deg=45.0):
    np, *_ = _deps();c=(float(center_deg)%360.0)/360.0;d=np.abs(h-c);d=np.minimum(d,1.0-d)
    return np.clip(1.0-d/(float(width_deg)/360.0),0,1).astype(np.float32)


def apply_color_mixer_hsl(img,cfg,prefix='mix_'):
    np, *_ = _deps()
    colors=[('red',0),('orange',30),('yellow',60),('green',120),('aqua',180),('blue',225),('purple',275),('magenta',320)]
    active=[]
    for name,center in colors:
        ha=float(cfg.get(prefix+name+'_h',0.0));sa=float(cfg.get(prefix+name+'_s',0.0));la=float(cfg.get(prefix+name+'_l',0.0))
        if abs(ha)>1e-7 or abs(sa)>1e-7 or abs(la)>1e-7:
            active.append((name,center,ha,sa/100.0,la/100.0))
    if not active:
        return img.astype(np.float32,copy=False)
    h,s,v=_rgb_to_hsv_np(img);base_h=h.copy();hue_delta=np.zeros_like(h);sat_factor=np.ones_like(s);vdelta=np.zeros_like(v)
    for name,center,ha,sa,la in active:
        w=_hue_weight(base_h,center,42.0)
        hue_delta+=w*(ha/360.0);sat_factor*=np.clip(1.0+w*sa,0.0,2.5);vdelta+=w*la
    h=np.mod(h+hue_delta,1.0);s=np.clip(s*sat_factor,0,1)
    v=np.where(vdelta>=0,v+0.38*vdelta*(1-v),v+0.38*vdelta*v)
    return _hsv_to_rgb_np(h,s,np.clip(v,0,1))

def _grade_tint(hue_deg,sat):
    np, *_ = _deps();h=np.array([[float(hue_deg)%360/360.0]],dtype=np.float32);ss=np.array([[np.clip(float(sat)/100.0,0,1)]],dtype=np.float32);vv=np.ones_like(h)
    return _hsv_to_rgb_np(h,ss,vv)[0,0]


def apply_color_grading(img,cfg):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1);lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
    bal=np.clip(float(cfg.get('cg_balance',0))/100.0,-1,1);pivot=0.5+0.18*bal
    sh=1.0-_smoothstep(max(0.05,pivot-0.30),pivot,lum);hi=_smoothstep(pivot,min(0.95,pivot+0.30),lum);mid=np.clip(1.0-sh-hi,0,1)
    out=x.copy()
    for name,mask in [('shadow',sh),('mid',mid),('high',hi)]:
        sat=float(cfg.get('cg_'+name+'_s',0));
        if abs(sat)<1e-7:continue
        col=_grade_tint(cfg.get('cg_'+name+'_h',0),abs(sat));delta=col-col.mean();strength=np.clip(abs(sat)/100.0,0,1)*0.24
        if sat<0:delta=-delta
        out=out+mask[...,None]*strength*delta[None,None,:]
    return np.clip(out,0,1).astype(np.float32)


def apply_detail_base(img,sharpen=0.0,radius=1.0,luma_nr=0.0,chroma_nr=0.0,proxy_scale=1.0):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1);ps=max(float(proxy_scale),0.05)
    lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1)
    ln=np.clip(float(luma_nr)/100.0,0,1)
    if ln>1e-7:
        bl=_blur(np.repeat(lum[...,None],3,axis=2),max(0.6,(0.8+2.0*ln)*ps))[...,0]
        lum2=lum*(1-0.78*ln)+bl*(0.78*ln);scale=lum2/np.maximum(lum,1e-5);x=np.clip(x*scale[...,None],0,1);lum=lum2
    cn=np.clip(float(chroma_nr)/100.0,0,1)
    if cn>1e-7:x=protect_channel_chroma_noise(x,cn*100,max(0.4,(0.6+1.6*cn)*ps))
    sh=float(sharpen)/100.0
    if abs(sh)>1e-7:
        lum=np.clip(0.2126*x[...,0]+0.7152*x[...,1]+0.0722*x[...,2],0,1);bl=_blur(np.repeat(lum[...,None],3,axis=2),max(0.25,float(radius)*ps))[...,0];nl=np.clip(lum+sh*(lum-bl),0,1);x=np.clip(x*(nl/np.maximum(lum,1e-5))[...,None],0,1)
    return x.astype(np.float32)


def apply_optics_base(img,distortion=0.0,vignette=0.0,ca=0.0):
    np,*rest=_deps();cv2=rest[-1];x=np.clip(img.astype(np.float32),0,1);h,w=x.shape[:2]
    if cv2 is not None and (abs(float(distortion))>1e-7 or abs(float(ca))>1e-7):
        yy,xx=np.mgrid[0:h,0:w].astype(np.float32);xn=(xx-(w-1)/2)/max((w-1)/2,1);yn=(yy-(h-1)/2)/max((h-1)/2,1);r2=xn*xn+yn*yn
        d=np.clip(float(distortion)/100.0,-1,1)*0.18;fac=1.0+d*r2;mx=(xn*fac+1)*0.5*(w-1);my=(yn*fac+1)*0.5*(h-1)
        base=cv2.remap(x,mx.astype(np.float32),my.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        caa=np.clip(float(ca)/100.0,-1,1)*0.006
        if abs(caa)>1e-8:
            out=base.copy()
            for ch,sgn in [(0,1.0),(2,-1.0)]:
                f=1.0+sgn*caa*r2;cmx=(xn*f+1)*0.5*(w-1);cmy=(yn*f+1)*0.5*(h-1);out[...,ch]=cv2.remap(base[...,ch],cmx.astype(np.float32),cmy.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
            x=out
        else:x=base
    vg=np.clip(float(vignette)/100.0,-1,1)
    if abs(vg)>1e-7:
        yy,xx=np.mgrid[0:h,0:w].astype(np.float32);xn=(xx-(w-1)/2)/max((w-1)/2,1);yn=(yy-(h-1)/2)/max((h-1)/2,1);r=np.clip(np.sqrt(xn*xn+yn*yn)/1.4142,0,1);gain=1.0+vg*0.55*(r**2);x=np.clip(x*gain[...,None],0,1)
    return x.astype(np.float32)


def apply_calibration_base(img,cfg):
    np, *_ = _deps();x=np.clip(img.astype(np.float32),0,1)
    tmp={}
    for name,prefix in [('red','cal_red'),('green','cal_green'),('blue','cal_blue')]:
        tmp['mix_'+name+'_h']=float(cfg.get(prefix+'_h',0));tmp['mix_'+name+'_s']=float(cfg.get(prefix+'_s',0));tmp['mix_'+name+'_l']=0.0
    # Non-primary sectors remain neutral.
    for name in ['orange','yellow','aqua','purple','magenta']:
        tmp['mix_'+name+'_h']=tmp['mix_'+name+'_s']=tmp['mix_'+name+'_l']=0.0
    return apply_color_mixer_hsl(x,tmp)


def _base_activity(cfg,curve_points=None):
    """Return active Base submodules without touching image pixels."""
    def nz(k,default=0.0):
        try:return abs(float(cfg.get(k,default)))>1e-7
        except Exception:return True
    tone=any(nz(k) for k in ('exposure','contrast','highlights','shadows','whites','blacks'))
    wb=nz('temperature') or nz('tint')
    presence=any(nz(k) for k in ('texture','clarity','dehaze'))
    curve=False
    if bool(cfg.get('base_curve',False)) and curve_points:
        for ch in ('RGB','红色','绿色','蓝色','亮度'):
            pts=curve_points.get(ch,[(0.0,0.0),(1.0,1.0)])
            if not (len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6):
                curve=True;break
    hsl=any(nz(k) for k in ('hsl_hue','hsl_sat','hsl_lum'))
    mixer=False
    for c in ('red','orange','yellow','green','aqua','blue','purple','magenta'):
        if any(nz(f'mix_{c}_{a}') for a in ('h','s','l')):
            mixer=True;break
    grading=any(nz(k) for k in ('cg_shadow_s','cg_mid_s','cg_high_s'))
    detail=any(nz(k) for k in ('detail_sharpen','luma_nr','chroma_nr'))
    optics=any(nz(k) for k in ('opt_distortion','opt_vignette','opt_ca'))
    calibration=any(nz(k) for k in ('cal_red_h','cal_red_s','cal_green_h','cal_green_s','cal_blue_h','cal_blue_s'))
    return {'tone':tone,'wb':wb,'presence':presence,'curve':curve,'hsl':hsl,'mixer':mixer,'grading':grading,'detail':detail,'optics':optics,'calibration':calibration}


def apply_base_editor(img,cfg,curve_points=None):
    """Apply Base only where controls are active (v0.9.4.18m fast path).

    Neutral HSL, mixer, grading, detail, optics and calibration modules used to
    perform full-frame color conversions/mask construction anyway.  They now
    short-circuit before allocating pixel buffers.  Active module math is kept
    on the same production functions used by preview and final export.
    """
    np, *_ = _deps();source=img.astype(np.float32,copy=False);ps=float(cfg.get('_proxy_scale',1.0));act=_base_activity(cfg,curve_points)
    if not any(act.values()):
        return source
    out=np.clip(source,0,1)
    # Make one private working buffer; subsequent neutral modules do no extra copies.
    out=out.astype(np.float32,copy=True)
    if act['tone']:
        out=apply_basic(out,cfg.get('exposure',0),cfg.get('contrast',0),cfg.get('highlights',0),cfg.get('shadows',0),cfg.get('whites',0),cfg.get('blacks',0),0,0,0,0)
    if act['wb']:
        out=apply_white_balance_post(out,cfg.get('temperature',0),cfg.get('tint',0))
    if act['presence']:
        out=apply_presence_advanced(out,cfg.get('texture',0),cfg.get('clarity',0),cfg.get('dehaze',0),ps)
    if act['curve']:
        for ch in ('RGB','红色','绿色','蓝色','亮度'):
            pts=curve_points.get(ch,[(0.0,0.0),(1.0,1.0)])
            identity=len(pts)==2 and abs(pts[0][0])<1e-6 and abs(pts[0][1])<1e-6 and abs(pts[1][0]-1)<1e-6 and abs(pts[1][1]-1)<1e-6
            if not identity:out=apply_curve_lut(out,build_curve_lut(pts,256),ch)
    if act['hsl']:
        out=apply_global_hsl(out,cfg.get('hsl_hue',0),cfg.get('hsl_sat',0),cfg.get('hsl_lum',0))
    if act['mixer']:
        out=apply_color_mixer_hsl(out,cfg)
    if act['grading']:
        out=apply_color_grading(out,cfg)
    if act['detail']:
        out=apply_detail_base(out,cfg.get('detail_sharpen',0),cfg.get('detail_radius',1),cfg.get('luma_nr',0),cfg.get('chroma_nr',0),ps)
    if act['optics']:
        out=apply_optics_base(out,cfg.get('opt_distortion',0),cfg.get('opt_vignette',0),cfg.get('opt_ca',0))
    if act['calibration']:
        out=apply_calibration_base(out,cfg)
    return out.astype(np.float32,copy=False)

def build_curve_lut(points, size=256):
    np, *_ = _deps()
    pts = sorted([(max(0.0,min(1.0,float(x))), max(0.0,min(1.0,float(y)))) for x,y in points], key=lambda p:p[0])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    grid = np.linspace(0.0, 1.0, size, dtype=np.float32)
    lut = np.interp(grid, xs, ys).astype(np.float32)
    return np.clip(lut, 0, 1)


def apply_curve_lut(img, lut, channel='RGB'):
    np, *_ = _deps()
    x = np.clip(img, 0, 1).astype(np.float32)
    idx = np.clip(np.round(x * (len(lut)-1)).astype(np.int32), 0, len(lut)-1)
    out = x.copy()
    if channel == 'RGB':
        out[...,0] = lut[idx[...,0]]
        out[...,1] = lut[idx[...,1]]
        out[...,2] = lut[idx[...,2]]
    elif channel in ('红色','绿色','蓝色'):
        mapping = {'红色':0, '绿色':1, '蓝色':2}
        c = mapping[channel]
        out[...,c] = lut[idx[...,c]]
    elif channel in ('亮度','Luminance'):
        lum = np.clip(0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2],0,1)
        lidx = np.clip(np.round(lum * (len(lut)-1)).astype(np.int32), 0, len(lut)-1)
        new_lum = lut[lidx]
        scale = new_lum / np.maximum(lum, 1e-6)
        out = np.clip(x * scale[...,None], 0, 1)
    return out.astype(np.float32)


def protect_channel_chroma_noise(img, strength=30.0, radius=0.8):
    """Reduce high-frequency inter-channel noise while preserving luminance detail.

    The luminance plane is kept from the original image. Only RGB chroma residuals
    (RGB - Y) are Gaussian-smoothed and blended back according to strength.
    This is especially useful for extreme Channel Mixer coefficients such as
    R=-200%, B=+200%, which otherwise strongly amplify color-difference noise.
    """
    np, *_ = _deps()
    x = np.clip(img.astype(np.float32), 0, 1)
    a = np.clip(float(strength)/100.0, 0.0, 1.0)
    if a <= 1e-8:
        return x
    lum = 0.2126*x[...,0] + 0.7152*x[...,1] + 0.0722*x[...,2]
    chroma = x - lum[...,None]
    # _blur accepts RGB-like arrays; chroma can contain negatives, and OpenCV
    # preserves them in float32. The Pillow fallback clips, so offset around 0.5.
    try:
        np2, *_rest = _deps(); cv2 = _rest[-1]
        if cv2 is not None:
            smooth = cv2.GaussianBlur(chroma, (0,0), sigmaX=max(float(radius),0.1), sigmaY=max(float(radius),0.1), borderType=cv2.BORDER_REFLECT)
        else:
            smooth = _blur(np.clip(chroma + 0.5,0,1), radius) - 0.5
    except Exception:
        smooth = chroma
    protected_chroma = chroma*(1.0-a) + smooth*a
    return np.clip(lum[...,None] + protected_chroma, 0, 1).astype(np.float32)


def apply_channel_mixer(img, output_channel='红色', monochrome=False, red=100.0, green=0.0, blue=0.0, constant=0.0,
                        noise_protect=False, noise_strength=30.0, noise_radius=0.8):
    np, *_ = _deps()
    x = np.clip(img.astype(np.float32), 0, 1)
    if noise_protect:
        x = protect_channel_chroma_noise(x, noise_strength, noise_radius)
    r = x[...,0]
    g = x[...,1]
    b = x[...,2]
    mix = (float(red)/100.0)*r + (float(green)/100.0)*g + (float(blue)/100.0)*b + (float(constant)/100.0)
    mix = np.clip(mix, 0, 1).astype(np.float32)
    out = x.copy()
    if monochrome or output_channel == '灰色':
        out[...,0] = mix
        out[...,1] = mix
        out[...,2] = mix
    else:
        mapping = {'红色':0, '绿色':1, '蓝色':2}
        out[..., mapping.get(output_channel, 0)] = mix
    return np.clip(out, 0, 1).astype(np.float32)


def background_suppression(img, radius=80.0, strength=100.0):
    """Remove large-scale background while keeping local halo/cloud structures around mid-gray."""
    np, *_ = _deps()
    x = np.clip(img.astype(np.float32), 0, 1)
    bg = _blur(x, max(float(radius), 0.5))
    detail = x - bg
    out = 0.5 + detail * (max(float(strength), 0.0) / 100.0)
    return np.clip(out, 0, 1).astype(np.float32)
