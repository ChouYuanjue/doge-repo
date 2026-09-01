from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class FunLabError(ValueError):
    pass


def _font(size: int):
    for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _title(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    w = min(img.width - 18, 30 + max(330, len(text) * 12))
    d.rounded_rectangle((16, 14, w, 57), radius=11, fill=(250, 250, 248))
    d.text((29, 25), text, fill=(22, 22, 26), font=_font(18))


def _out(output_dir: Path, stem: str, suffix: str = ".png") -> Path:
    d = Path(output_dir) / "lab"
    d.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(stem.encode()).hexdigest()[:12]
    return d / f"{stem}-{token}{suffix}"


def _life_seed(kind: str, n: int, rng) -> np.ndarray:
    a = np.zeros((n, n), dtype=bool)
    cy = cx = n // 2
    kind = kind.lower()
    if kind in {"glider", "g"}:
        pts = [(0,1),(1,2),(2,0),(2,1),(2,2)]
        for y,x in pts: a[cy-6+y,cx-6+x] = 1
    elif kind in {"acorn", "a"}:
        # Seven cells; takes thousands of generations to fully settle.
        pts = [(0,1),(1,3),(2,0),(2,1),(2,4),(2,5),(2,6)]
        for y,x in pts: a[cy-3+y,cx-4+x] = 1
    elif kind in {"gun", "gosper"}:
        pts = [
            (5,1),(5,2),(6,1),(6,2),
            (5,11),(6,11),(7,11),(4,12),(8,12),(3,13),(9,13),(3,14),(9,14),
            (6,15),(4,16),(8,16),(5,17),(6,17),(7,17),(6,18),
            (3,21),(4,21),(5,21),(3,22),(4,22),(5,22),(2,23),(6,23),(1,25),(2,25),(6,25),(7,25),
            (3,35),(4,35),(3,36),(4,36),
        ]
        oy, ox = cy - 10, cx - 20
        for y,x in pts:
            yy,xx=oy+y,ox+x
            if 0<=yy<n and 0<=xx<n: a[yy,xx]=1
    elif kind in {"random", "r"}:
        box = min(56, n - 12); y0=cy-box//2; x0=cx-box//2
        a[y0:y0+box,x0:x0+box] = rng.random((box,box)) < .28
    else:
        raise FunLabError("life 支持 glider / gun / acorn / random")
    return a


def _life_step(a: np.ndarray) -> np.ndarray:
    # Dead boundary rather than a torus, so a glider can visibly leave the frame.
    p = np.pad(a.astype(np.uint8), 1)
    nb = (
        p[:-2,:-2]+p[:-2,1:-1]+p[:-2,2:]+p[1:-1,:-2]+
        p[1:-1,2:]+p[2:,:-2]+p[2:,1:-1]+p[2:,2:]
    )
    return (nb == 3) | (a & (nb == 2))


def life(output_dir: Path, kind: str="glider", steps: int=120, size: int=121) -> tuple[Path,str]:
    """Render Conway Life as a real animated GIF.

    `steps` is the simulated generation count.  For long runs we sample at most
    72 frames rather than allocating one full bitmap per generation; this keeps
    QQ-sized GIFs useful without changing the cellular automaton itself.
    """
    steps=max(3,min(int(steps),3500)); size=max(81,min(int(size)|1,241)); rng=np.random.default_rng(20260831)
    a=_life_seed(kind,size,rng)
    frame_count=min(72,max(12,min(steps+1,48 if steps<=120 else 72)))
    marks=sorted(set(int(x) for x in np.linspace(0,steps,frame_count)))
    shots={0:a.copy()}
    wanted=set(marks)
    for t in range(1,steps+1):
        a=_life_step(a)
        if t in wanted: shots[t]=a.copy()

    # One shared crop makes motion visible instead of re-centering each frame.
    coords=[]
    for arr in shots.values():
        yy,xx=np.nonzero(arr)
        if len(xx): coords.append((int(yy.min()),int(yy.max()),int(xx.min()),int(xx.max())))
    if coords:
        y0=max(0,min(v[0] for v in coords)-7); y1=min(size,max(v[1] for v in coords)+8)
        x0=max(0,min(v[2] for v in coords)-7); x1=min(size,max(v[3] for v in coords)+8)
    else:
        y0=x0=0; y1=x1=size
    h=max(1,y1-y0); w=max(1,x1-x0); side=max(h,w,18)
    cy=(y0+y1)//2; cx=(x0+x1)//2
    y0=max(0,min(max(0,size-side),cy-side//2)); x0=max(0,min(max(0,size-side),cx-side//2))
    y1=min(size,y0+side); x1=min(size,x0+side)

    panel=480
    frames=[]
    for t in marks:
        arr=shots[t][y0:y1,x0:x1]
        small=np.where(arr,24,246).astype(np.uint8)
        rgb=np.stack([small,small,small],axis=-1)
        board=Image.fromarray(rgb,"RGB").resize((panel,panel),Image.Resampling.NEAREST)
        canvas=Image.new("RGB",(panel+32,panel+92),(245,245,242))
        canvas.paste(board,(16,68))
        _title(canvas,f"Conway Life · {kind} · generation {t}/{steps}")
        d=ImageDraw.Draw(canvas)
        d.text((22,panel+72),f"alive = {int(shots[t].sum())} · sampled frame {marks.index(t)+1}/{len(marks)}",fill=(75,75,82),font=_font(15))
        # A tiny palette keeps the animated result reasonably small on QQ.
        frames.append(canvas.convert("P",palette=Image.Palette.ADAPTIVE,colors=16))
    path=_out(output_dir,f"life-{kind}-{steps}-{size}",suffix=".gif")
    frames[0].save(path,save_all=True,append_images=frames[1:],format="GIF",duration=120,loop=0,disposal=2,optimize=True)
    return path,f"Conway 生命游戏 GIF：模拟 {steps} 代，采样 {len(frames)} 帧。每一帧都来自同一局部规则的真实演化；长模拟只降低动画采样频率，不改变演化过程。"


def dla(output_dir: Path, particles: int=850, size: int=321) -> tuple[Path,str]:
    particles=max(80,min(int(particles),2200)); size=max(181,min(int(size)|1,451)); c=size//2
    grid=np.zeros((size,size),dtype=bool); age=np.full((size,size),-1,dtype=np.int32); grid[c,c]=1; age[c,c]=0
    rng=np.random.default_rng(20260831); radius=2.0; attached=1
    dirs=np.array([[1,0],[-1,0],[0,1],[0,-1]],dtype=np.int16)
    max_radius=size/2-8
    for k in range(1,particles):
        launch=min(max(radius+8,12),max_radius-3); kill=min(launch+26,max_radius)
        th=rng.random()*2*math.pi; y=int(round(c+launch*math.sin(th))); x=int(round(c+launch*math.cos(th)))
        for _ in range(26000):
            dy,dx=dirs[rng.integers(0,4)]; y+=int(dy); x+=int(dx)
            rr=(y-c)*(y-c)+(x-c)*(x-c)
            if y<2 or y>=size-2 or x<2 or x>=size-2 or rr>kill*kill:
                th=rng.random()*2*math.pi; y=int(round(c+launch*math.sin(th))); x=int(round(c+launch*math.cos(th))); continue
            if grid[y-1:y+2,x-1:x+2].any():
                # Do not occupy an already-filled site.
                if not grid[y,x]:
                    grid[y,x]=1; age[y,x]=k; attached+=1
                    radius=max(radius,math.sqrt(rr))
                break
        if radius>=max_radius-4: break
    yy,xx=np.indices(grid.shape); rr=np.sqrt((yy-c)**2+(xx-c)**2); crop=int(min(max(radius+9,45),size//2-2)); sub=age[c-crop:c+crop+1,c-crop:c+crop+1]
    mask=sub>=0; norm=np.zeros_like(sub,dtype=float); norm[mask]=sub[mask]/max(attached-1,1)
    rgb=np.full((*sub.shape,3),246,dtype=np.uint8)
    # Growth time runs from dark blue center to warm outer tips.
    rgb[...,0][mask]=(35+205*norm[mask]).astype(np.uint8)
    rgb[...,1][mask]=(70+80*(1-norm[mask])).astype(np.uint8)
    rgb[...,2][mask]=(165-105*norm[mask]).astype(np.uint8)
    img=Image.fromarray(rgb,"RGB").resize((820,820),Image.Resampling.NEAREST); _title(img,f"Diffusion-limited aggregation · {attached} particles")
    path=_out(output_dir,f"dla-{particles}-{size}"); img.save(path)
    return path,f"DLA：随机游走粒子一碰到团簇就粘住。颜色从中心到尖端表示生长先后；本次粘附 {attached} 个粒子。"


def beats(output_dir: Path, f1: float=9.0, f2: float=10.0, seconds: float=3.0) -> tuple[Path,str]:
    f1=float(f1); f2=float(f2); seconds=float(seconds)
    if not .2<=f1<=100 or not .2<=f2<=100: raise FunLabError("f1/f2 需在 0.2..100")
    if not .5<=seconds<=10: raise FunLabError("显示时长需在 0.5..10 秒")
    n=2400; t=np.linspace(0,seconds,n); y1=np.sin(2*np.pi*f1*t); y2=np.sin(2*np.pi*f2*t); y=y1+y2
    env=2*np.abs(np.cos(np.pi*(f2-f1)*t))
    img=Image.new("RGB",(1100,760),(250,250,247)); d=ImageDraw.Draw(img); _title(img,f"Beats · f₁={f1:g} Hz · f₂={f2:g} Hz · |Δf|={abs(f2-f1):g} Hz")
    left,right=55,1060
    # top: the two nearly-equal component waves
    d.text((60,78),"two component waves",fill=(30,30,35),font=_font(18))
    for arr,col in ((y1,(45,100,180)),(y2,(205,75,50))):
        pts=[(left+i/(n-1)*(right-left),235-arr[i]*105) for i in range(0,n,2)]; d.line(pts,fill=col,width=2)
    d.line((left,235,right,235),fill=(170,170,175),width=1)
    # bottom: sum + envelope; leave room for both ±2 envelope and caption.
    d.text((60,365),"sum and slow envelope",fill=(30,30,35),font=_font(18))
    center=545; amp=82
    pts=[(left+i/(n-1)*(right-left),center-y[i]*amp) for i in range(0,n,2)]; d.line(pts,fill=(80,70,155),width=2)
    up=[(left+i/(n-1)*(right-left),center-env[i]*amp) for i in range(0,n,3)]; lo=[(left+i/(n-1)*(right-left),center+env[i]*amp) for i in range(0,n,3)]
    d.line(up,fill=(215,145,35),width=3); d.line(lo,fill=(215,145,35),width=3); d.line((left,center,right,center),fill=(170,170,175),width=1)
    d.text((left,726),f"beat frequency = |f₂-f₁| = {abs(f2-f1):g} Hz",fill=(30,30,35),font=_font(20))
    path=_out(output_dir,f"beats-{f1:g}-{f2:g}-{seconds:g}"); img.save(path)
    return path,f"两个接近频率叠加后，快振荡被一个慢包络调制；拍频正好是 |f₂-f₁|={abs(f2-f1):g} Hz。"


def help_text() -> str:
    return (
        "  /lab life [{glider|gun|acorn|random}] [steps]    # animated GIF\n"
        "  /lab dla [particles]\n"
        "  /lab beats [f1] [f2] [seconds]\n"
        + __import__("doge_v5.visual_lab_fun2", fromlist=["help_text"]).help_text()
    )


def render_fun(output_dir: Path, payload: str):
    parts=payload.strip().split()
    if not parts: return None
    h=parts[0].lower(); r=parts[1:]
    if h in {"life","conway"}: return life(output_dir,r[0] if r else "glider",int(r[1]) if len(r)>1 else 120)
    if h in {"dla","aggregate"}: return dla(output_dir,int(r[0]) if r else 850)
    if h in {"beats","beat"}: return beats(output_dir,float(r[0]) if r else 9,float(r[1]) if len(r)>1 else 10,float(r[2]) if len(r)>2 else 3)
    from .visual_lab_fun2 import render_fun2
    fun2 = render_fun2(output_dir, payload)
    if fun2 is not None:
        return fun2
    return None
