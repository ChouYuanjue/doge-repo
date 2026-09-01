from __future__ import annotations

import hashlib
import math
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class ExtraLabError(ValueError):
    pass


def _font(size: int):
    for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _title(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 14, min(img.width - 16, 28 + max(350, len(text) * 13)), 58), radius=12, fill=(250, 250, 248))
    d.text((30, 26), text, fill=(20, 20, 24), font=_font(18))


def _out(output_dir: Path, stem: str) -> Path:
    d = Path(output_dir) / "lab"
    d.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(stem.encode()).hexdigest()[:12]
    return d / f"{stem}-{token}.png"


def _hsv_rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    h = np.mod(h, 1.0); s = np.clip(s, 0, 1); v = np.clip(v, 0, 1)
    i = np.floor(h * 6).astype(np.int16)
    f = h * 6 - i
    p = v * (1-s); q = v * (1-f*s); t = v * (1-(1-f)*s)
    m = i % 6
    r = np.choose(m, [v,q,p,p,t,v]); g = np.choose(m, [t,v,v,q,p,p]); b = np.choose(m, [p,p,t,v,v,q])
    return (np.stack([r,g,b],axis=-1)*255).astype(np.uint8)


def domain_coloring(output_dir: Path, kind: str="z3-1", zoom: float=1.0) -> tuple[Path,str]:
    if not 0.2 <= zoom <= 20: raise ExtraLabError("zoom 需在 0.2..20")
    n=720; span=3.2/zoom
    x=np.linspace(-span,span,n); y=np.linspace(span,-span,n); X,Y=np.meshgrid(x,y); z=X+1j*Y
    k=kind.lower().replace(" ","")
    with np.errstate(all="ignore"):
        if k in {"z","id"}: w=z
        elif k in {"z2+1","z^2+1"}: w=z*z+1
        elif k in {"z3-1","z^3-1"}: w=z*z*z-1
        elif k in {"1/z","inv"}: w=1/z
        elif k in {"sin","sinz"}: w=np.sin(z)
        elif k in {"exp","expz"}: w=np.exp(z)
        else: raise ExtraLabError("complex 支持 z / z2+1 / z3-1 / 1/z / sin / exp")
    arg=np.angle(w); mag=np.abs(w)
    hue=(arg/(2*np.pi)+1)%1
    # Repeating lightness rings reveal magnitude while hue reveals argument.
    logm=np.log2(np.maximum(mag,1e-12)); frac=logm-np.floor(logm)
    value=0.55+0.4*(1-np.abs(frac-0.5)*2)
    sat=np.full_like(value,.88)
    rgb=_hsv_rgb(hue,sat,value)
    bad=~np.isfinite(mag); rgb[bad]=(0,0,0)
    img=Image.fromarray(rgb,"RGB"); _title(img,f"Complex domain coloring · f(z)={kind} · zoom={zoom:g}")
    path=_out(output_dir,f"domain-{k.replace('/','_')}"); img.save(path)
    return path,"复函数域着色：色相表示复数辐角，明暗条纹编码模长；零点、极点和绕数会直接显形。"


def newton_fractal(output_dir: Path, degree: int=3, zoom: float=1.0) -> tuple[Path,str]:
    degree=int(degree)
    if degree<2 or degree>8: raise ExtraLabError("Newton 分形次数支持 2..8")
    n=720; span=2.0/float(zoom)
    x=np.linspace(-span,span,n); y=np.linspace(span,-span,n); X,Y=np.meshgrid(x,y); z=X+1j*Y
    it=np.zeros(z.shape,np.uint8)
    for step in range(36):
        with np.errstate(all="ignore"):
            denom=degree*np.power(z,degree-1)
            z=np.where(np.abs(denom)>1e-14,z-(np.power(z,degree)-1)/denom,z)
        it[:]=step
    roots=np.exp(2j*np.pi*np.arange(degree)/degree)
    dist=np.stack([np.abs(z-r) for r in roots],axis=-1)
    idx=np.argmin(dist,axis=-1)
    mind=np.min(dist,axis=-1)
    h=idx/degree
    # distance to root gives subtle brightness; divergent pixels black
    v=np.clip(.98-.22*np.log1p(mind*30),.25,.98)
    rgb=_hsv_rgb(h,np.full_like(v,.82),v); rgb[mind>.2]=(0,0,0)
    img=Image.fromarray(rgb,"RGB"); _title(img,f"Newton fractal · z^{degree}-1=0")
    path=_out(output_dir,f"newton-{degree}"); img.save(path)
    return path,f"Newton 迭代求 z^{degree}=1：颜色代表最终落入哪个根，边界体现初值敏感性。"


def ising(output_dir: Path, temperature: float=2.269, sweeps: int=180, size: int=180) -> tuple[Path,str]:
    T=float(temperature); sweeps=max(10,min(int(sweeps),700)); size=max(64,min(int(size),240))
    if T<=0 or T>8: raise ExtraLabError("温度 T 需在 0..8")
    rng=np.random.default_rng(20260831); s=rng.choice(np.array([-1,1],np.int8),(size,size))
    yy,xx=np.indices(s.shape)
    for _ in range(sweeps):
        for parity in (0,1):
            nb=np.roll(s,1,0)+np.roll(s,-1,0)+np.roll(s,1,1)+np.roll(s,-1,1)
            dE=2*s*nb
            mask=((xx+yy)&1)==parity
            accept=(dE<=0)|(rng.random(s.shape)<np.exp(-dE/T))
            s[mask&accept]*=-1
    mag=float(abs(s.mean()))
    arr=np.where(s>0,242,35).astype(np.uint8)
    rgb=np.stack([arr,arr,arr],axis=-1)
    img=Image.fromarray(rgb,"RGB").resize((800,800),Image.Resampling.NEAREST); _title(img,f"2D Ising · T={T:g} · |m|={mag:.3f}")
    path=_out(output_dir,f"ising-{T:.3f}"); img.save(path)
    return path,f"二维 Ising 模型，T≈2.269 是经典临界温度；本次 |磁化强度|≈{mag:.3f}。"


def percolation(output_dir: Path, p: float=.5927, size: int=180) -> tuple[Path,str]:
    p=float(p); size=max(60,min(int(size),260))
    if not 0<=p<=1: raise ExtraLabError("p 需在 0..1")
    rng=np.random.default_rng(20260831); open_=rng.random((size,size))<p
    seen=np.zeros_like(open_,bool); q=deque()
    for x in np.flatnonzero(open_[0]): seen[0,x]=1; q.append((0,int(x)))
    while q:
        y,x=q.popleft()
        for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
            ny,nx=y+dy,x+dx
            if 0<=ny<size and 0<=nx<size and open_[ny,nx] and not seen[ny,nx]:
                seen[ny,nx]=1; q.append((ny,nx))
    spans=bool(seen[-1].any())
    rgb=np.full((size,size,3),245,np.uint8); rgb[open_]=(90,110,120); rgb[seen]=(230,75,55)
    img=Image.fromarray(rgb,"RGB").resize((800,800),Image.Resampling.NEAREST); _title(img,f"Site percolation · p={p:g} · {'SPANS' if spans else 'no span'}")
    path=_out(output_dir,f"percolation-{p:.4f}"); img.save(path)
    return path,f"方格点渗流：红色是与顶边连通的簇；p≈0.592746 是无限方格的临界概率。本次{'形成' if spans else '没有形成'}贯穿簇。"


def random_matrix(output_dir: Path, n: int=180, ensemble: str="ginibre") -> tuple[Path,str]:
    n=max(40,min(int(n),320)); rng=np.random.default_rng(20260831); kind=ensemble.lower()
    if kind in {"ginibre","complex","circle"}:
        A=(rng.normal(size=(n,n))+1j*rng.normal(size=(n,n)))/math.sqrt(2*n); vals=np.linalg.eigvals(A); caption="复 Ginibre ensemble：特征值在极限下趋近 circular law。"
    elif kind in {"goe","wigner","real"}:
        A=rng.normal(size=(n,n)); A=(A+A.T)/math.sqrt(2*n); vals=np.linalg.eigvalsh(A); caption="GOE/Wigner 随机矩阵：实特征值密度趋近半圆律。"
    else: raise ExtraLabError("randommatrix 支持 ginibre / goe")
    img=Image.new("RGB",(900,800),(250,250,247)); d=ImageDraw.Draw(img); _title(img,f"Random matrix · {kind} · N={n}")
    if np.iscomplexobj(vals):
        scale=320/max(1.1,float(np.max(np.abs(vals))));
        for z in vals: d.ellipse((450+z.real*scale-3,420-z.imag*scale-3,450+z.real*scale+3,420-z.imag*scale+3),fill=(30,90,160))
        d.ellipse((130,100,770,740),outline=(120,120,120),width=2)
    else:
        hist,edges=np.histogram(vals,bins=45,density=True); mx=max(hist.max(),1e-9)
        pts=[]
        for i,h in enumerate(hist):
            x=80+(edges[i]-edges[0])/(edges[-1]-edges[0])*740; y=700-h/mx*560; pts.append((x,y))
        d.line(pts,fill=(40,90,160),width=4)
    path=_out(output_dir,f"randommatrix-{kind}-{n}"); img.save(path)
    return path,caption


def voronoi(output_dir: Path, points: int=32) -> tuple[Path,str]:
    points=max(3,min(int(points),100)); n=700; rng=np.random.default_rng(20260831); seeds=rng.uniform(25,n-25,(points,2))
    yy,xx=np.indices((n,n)); best=np.full((n,n),np.inf); labels=np.zeros((n,n),np.int16)
    for i,(sx,sy) in enumerate(seeds):
        ds=(xx-sx)**2+(yy-sy)**2; m=ds<best; best[m]=ds[m]; labels[m]=i
    rngc=np.random.default_rng(7); palette=rngc.integers(85,235,(points,3),dtype=np.uint8); rgb=palette[labels]
    edge=(labels!=np.roll(labels,1,0))|(labels!=np.roll(labels,1,1)); rgb[edge]=(25,25,28)
    img=Image.fromarray(rgb,"RGB"); d=ImageDraw.Draw(img)
    for sx,sy in seeds: d.ellipse((sx-4,sy-4,sx+4,sy+4),fill=(255,255,255),outline=(0,0,0),width=1)
    _title(img,f"Voronoi diagram · {points} sites")
    path=_out(output_dir,f"voronoi-{points}"); img.save(path)
    return path,"Voronoi 图把平面分给最近的种子点；它同时连接计算几何、晶粒、生物形态和空间优化。"


def bloch(output_dir: Path, theta_deg: float=60, phi_deg: float=45) -> tuple[Path,str]:
    th=math.radians(float(theta_deg)); ph=math.radians(float(phi_deg)); x=math.sin(th)*math.cos(ph); y=math.sin(th)*math.sin(ph); z=math.cos(th)
    img=Image.new("RGB",(820,820),(249,249,246)); d=ImageDraw.Draw(img); cx=410; cy=430; R=300
    d.ellipse((cx-R,cy-R,cx+R,cy+R),outline=(35,35,40),width=3)
    # equator as flattened ellipse and three axes
    d.ellipse((cx-R,cy-80,cx+R,cy+80),outline=(160,160,165),width=2)
    d.line((cx-R-30,cy,cx+R+30,cy),fill=(95,95,100),width=2); d.line((cx,cy+R+30,cx,cy-R-30),fill=(95,95,100),width=2)
    # pseudo-3D y projected diagonally
    d.line((cx-210,cy+150,cx+210,cy-150),fill=(130,130,135),width=2)
    px=cx+R*(x+.55*y); py=cy-R*(z+.25*y)
    d.line((cx,cy,px,py),fill=(205,55,45),width=5); d.ellipse((px-8,py-8,px+8,py+8),fill=(205,55,45))
    d.text((cx+R+10,cy-10),"x",fill=(30,30,35),font=_font(22)); d.text((cx+5,cy-R-35),"z",fill=(30,30,35),font=_font(22)); d.text((cx+210,cy-175),"y",fill=(30,30,35),font=_font(22))
    _title(img,f"Bloch sphere · theta={theta_deg:g}°, phi={phi_deg:g}°")
    path=_out(output_dir,f"bloch-{theta_deg:g}-{phi_deg:g}"); img.save(path)
    return path,f"单量子比特纯态的 Bloch 向量约为 ({x:.3f}, {y:.3f}, {z:.3f})。"


def relativity(output_dir: Path, beta: float=.6) -> tuple[Path,str]:
    beta=float(beta)
    if abs(beta)>=.98: raise ExtraLabError("为了图形可读性，|beta| 请小于 0.98")
    g=1/math.sqrt(1-beta*beta); img=Image.new("RGB",(900,800),(250,250,247)); d=ImageDraw.Draw(img); ox,oy=450,700; S=105
    # lab axes x and ct
    d.line((80,oy,820,oy),fill=(30,30,35),width=3); d.line((ox,740,ox,80),fill=(30,30,35),width=3)
    # light cone
    for sign in (-1,1): d.line((ox,oy,ox+sign*5.5*S,oy-5.5*S),fill=(215,160,55),width=2)
    # moving t' axis x=beta ct; x' axis ct=beta x
    d.line((ox,oy,ox+beta*5.2*S,oy-5.2*S),fill=(190,55,55),width=4)
    d.line((ox-5.2*S,oy+beta*5.2*S,ox+5.2*S,oy-beta*5.2*S),fill=(45,105,190),width=4)
    d.text((790,oy+8),"x",fill=(30,30,35),font=_font(22)); d.text((ox+8,82),"ct",fill=(30,30,35),font=_font(22)); d.text((ox+beta*4.8*S+8,oy-4.8*S),"ct'",fill=(190,55,55),font=_font(22)); d.text((760,oy-beta*3*S-25),"x'",fill=(45,105,190),font=_font(22))
    _title(img,f"Minkowski diagram · beta=v/c={beta:g} · gamma={g:.3f}")
    path=_out(output_dir,f"relativity-{beta:.3f}"); img.save(path)
    return path,f"Lorentz boost 的时空图：β={beta:g} 时 γ={g:.3f}；光锥保持不变，而运动坐标轴发生双曲旋转。"


def spectrum(output_dir: Path, kind: str="square", frequency: float=5.0) -> tuple[Path,str]:
    kind=kind.lower(); f=float(frequency)
    if f<=0 or f>100: raise ExtraLabError("frequency 需在 0..100")
    fs=1024.; t=np.arange(2048)/fs
    if kind in {"sine","sin"}: y=np.sin(2*np.pi*f*t)
    elif kind=="square": y=np.sign(np.sin(2*np.pi*f*t))
    elif kind in {"saw","sawtooth"}: y=2*((f*t)%1)-1
    elif kind=="chirp": y=np.sin(2*np.pi*(f*t+18*t*t))
    else: raise ExtraLabError("spectrum 支持 sine / square / saw / chirp")
    win=np.hanning(len(y)); sp=np.abs(np.fft.rfft(y*win)); fr=np.fft.rfftfreq(len(y),1/fs); sp/=max(sp.max(),1e-12)
    img=Image.new("RGB",(1000,800),(250,250,247)); d=ImageDraw.Draw(img); _title(img,f"Waveform + FFT · {kind} · f={f:g} Hz")
    # top waveform, first 0.5 sec
    nshow=512; pts=[(50+i/(nshow-1)*900,250-y[i]*130) for i in range(nshow)]; d.line(pts,fill=(30,90,165),width=2)
    d.line((50,250,950,250),fill=(170,170,175),width=1)
    # bottom spectrum 0..min(100, fs/2)
    maxf=100.; inds=np.where(fr<=maxf)[0]; vals=sp[inds]
    pts=[(50+fr[i]/maxf*900,700-vals[j]*320) for j,i in enumerate(inds)]; d.line(pts,fill=(195,70,45),width=2)
    d.line((50,700,950,700),fill=(60,60,65),width=2); d.text((55,390),"frequency spectrum",fill=(30,30,35),font=_font(20))
    path=_out(output_dir,f"spectrum-{kind}-{f:g}"); img.save(path)
    return path,"同一个信号同时看时域和频域：方波/锯齿波会显露谐波，chirp 会铺开成频率带。"


def sandpile(output_dir: Path, grains: int=120000, size: int=181) -> tuple[Path,str]:
    grains=max(100,min(int(grains),2_000_000)); size=max(81,min(int(size)|1,301)); a=np.zeros((size,size),np.int64); c=size//2; a[c,c]=grains
    for _ in range(20000):
        topple=a//4
        if not topple.any(): break
        a%=4
        a[1:,:]+=topple[:-1,:]; a[:-1,:]+=topple[1:,:]; a[:,1:]+=topple[:,:-1]; a[:,:-1]+=topple[:,1:]
    pal=np.array([[20,20,25],[225,85,55],[245,190,65],[70,135,180]],np.uint8); rgb=pal[np.clip(a,0,3)]
    img=Image.fromarray(rgb,"RGB").resize((800,800),Image.Resampling.NEAREST); _title(img,f"Abelian sandpile · grains={grains}")
    path=_out(output_dir,f"sandpile-{grains}"); img.save(path)
    return path,"Abelian sandpile：中心不断加沙，局部规则只有“≥4 就向四邻居各送 1”，却长出具有自相似性的临界结构。"


def langton_ant(output_dir: Path, steps: int=18000, size: int=401) -> tuple[Path,str]:
    steps=max(100,min(int(steps),250000)); size=max(151,min(int(size)|1,701)); a=np.zeros((size,size),bool); y=x=size//2; direction=0
    dy=(-1,0,1,0); dx=(0,1,0,-1)
    for _ in range(steps):
        if a[y,x]: direction=(direction-1)%4
        else: direction=(direction+1)%4
        a[y,x]=~a[y,x]; y=(y+dy[direction])%size; x=(x+dx[direction])%size
    rgb=np.where(a[...,None],np.array([25,25,30],np.uint8),np.array([247,247,243],np.uint8)); rgb=np.repeat(rgb,3,axis=2) if rgb.shape[2]==1 else rgb
    img=Image.fromarray(rgb.astype(np.uint8),"RGB").resize((800,800),Image.Resampling.NEAREST); _title(img,f"Langton's ant · {steps} steps")
    path=_out(output_dir,f"langton-{steps}"); img.save(path)
    return path,"Langton's ant：仅凭左右转和翻格两条规则，会先混沌很久，随后突然形成稳定的“高速公路”。"


def help_text() -> str:
    return (
        "  /lab complex [{z|z2+1|z3-1|1/z|sin|exp}] [zoom]\n"
        "  /lab newton [degree] [zoom]\n"
        "  /lab ising [T] [sweeps]\n"
        "  /lab percolation [p] [size]\n"
        "  /lab randommatrix [{ginibre|goe}] [N]\n"
        "  /lab voronoi [points]\n"
        "  /lab bloch [theta_deg] [phi_deg]\n"
        "  /lab relativity [beta]\n"
        "  /lab spectrum [{sine|square|saw|chirp}] [frequency]\n"
        "  /lab sandpile [grains]\n"
        "  /lab ant [steps]\n"
        + __import__("doge_v5.visual_lab_more", fromlist=["help_text"]).help_text()
    )


def render_extra(output_dir: Path, payload: str) -> tuple[Path,str] | None:
    parts=payload.strip().split()
    if not parts: return None
    h=parts[0].lower(); r=parts[1:]
    if h in {"complex","domain"}: return domain_coloring(output_dir,r[0] if r else "z3-1",float(r[1]) if len(r)>1 else 1.)
    if h=="newton": return newton_fractal(output_dir,int(r[0]) if r else 3,float(r[1]) if len(r)>1 else 1.)
    if h=="ising": return ising(output_dir,float(r[0]) if r else 2.269,int(r[1]) if len(r)>1 else 180)
    if h in {"percolation","perc"}: return percolation(output_dir,float(r[0]) if r else .5927,int(r[1]) if len(r)>1 else 180)
    if h in {"randommatrix","rmt"}: return random_matrix(output_dir,int(r[1]) if len(r)>1 else 180,r[0] if r else "ginibre")
    if h in {"voronoi","geometry"}: return voronoi(output_dir,int(r[0]) if r and r[0].isdigit() else int(r[1]) if len(r)>1 and r[1].isdigit() else 32)
    if h in {"bloch","quantum"}: return bloch(output_dir,float(r[0]) if r else 60,float(r[1]) if len(r)>1 else 45)
    if h in {"relativity","minkowski"}: return relativity(output_dir,float(r[0]) if r else .6)
    if h in {"spectrum","fft"}: return spectrum(output_dir,r[0] if r else "square",float(r[1]) if len(r)>1 else 5.)
    if h in {"sandpile","sand"}: return sandpile(output_dir,int(r[0]) if r else 120000)
    if h in {"ant","langton"}: return langton_ant(output_dir,int(r[0]) if r else 18000)
    from .visual_lab_more import render_more
    more = render_more(output_dir, payload)
    if more is not None:
        return more
    return None
