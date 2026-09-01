from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class MoreLabError(ValueError): pass


def _font(size:int):
    for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc","/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try: return ImageFont.truetype(p,size)
        except Exception: pass
    return ImageFont.load_default()


def _title(img,text):
    d=ImageDraw.Draw(img); w=min(img.width-16,30+max(350,len(text)*13)); d.rounded_rectangle((16,14,w,58),12,fill=(250,250,248)); d.text((30,26),text,fill=(20,20,24),font=_font(18))


def _out(output_dir,stem):
    d=Path(output_dir)/"lab"; d.mkdir(parents=True,exist_ok=True); h=hashlib.sha256(stem.encode()).hexdigest()[:12]; return d/f"{stem}-{h}.png"


def moire(output_dir:Path, angle:float=5.0, spacing:float=18.0)->tuple[Path,str]:
    angle=float(angle); spacing=max(5.,min(float(spacing),80.)); n=800
    yy,xx=np.indices((n,n)); c=(n-1)/2; x=xx-c; y=yy-c; a=math.radians(angle)
    u1=x; u2=x*math.cos(a)+y*math.sin(a)
    # thin dark lines with anti-aliased-ish sinusoidal intensity
    v=np.minimum(np.abs(np.sin(np.pi*u1/spacing)),np.abs(np.sin(np.pi*u2/spacing)))
    g=(55+200*np.clip(v/.22,0,1)).astype(np.uint8); rgb=np.stack([g,g,g],-1)
    img=Image.fromarray(rgb,"RGB"); _title(img,f"Moiré · angle={angle:g}° · spacing={spacing:g}px")
    p=_out(output_dir,f"moire-{angle:g}-{spacing:g}"); img.save(p)
    return p,"两组几乎相同的周期结构叠加，会出现尺度远大于原始条纹的莫尔包络；小角度变化会被视觉放大。"


def orbital(output_dir:Path, kind:str="2px", scale:float=8.0)->tuple[Path,str]:
    kind=kind.lower(); n=720; s=max(3.,min(float(scale),20.)); x=np.linspace(-s,s,n); y=np.linspace(s,-s,n); X,Y=np.meshgrid(x,y); R=np.sqrt(X*X+Y*Y)+1e-9
    if kind in {"1s","s"}: psi=np.exp(-R); label="1s"
    elif kind in {"2p","2px","px"}: psi=X*np.exp(-R/2); label="2p_x"
    elif kind in {"2py","py"}: psi=Y*np.exp(-R/2); label="2p_y"
    elif kind in {"3dxy","dxy"}: psi=X*Y*np.exp(-R/3); label="3d_xy"
    elif kind in {"3dz2","dz2"}: psi=-(X*X+Y*Y)*np.exp(-R/3); label="3d_z² (z=0 slice)"
    else: raise MoreLabError("orbital 支持 1s / 2px / 2py / 3dxy / 3dz2")
    m=max(float(np.max(np.abs(psi))),1e-12); z=np.clip(psi/m,-1,1); amp=np.sqrt(np.abs(z)); rgb=np.empty((n,n,3),np.uint8)
    # sign -> red/blue; probability amplitude -> saturation
    rgb[...,0]=(245-190*amp*(z<0)).astype(np.uint8); rgb[...,1]=(245-200*amp).astype(np.uint8); rgb[...,2]=(245-190*amp*(z>0)).astype(np.uint8)
    img=Image.fromarray(rgb,"RGB"); _title(img,f"Hydrogen-like orbital slice · {label}")
    p=_out(output_dir,f"orbital-{kind}"); img.save(p)
    return p,"氢样原子轨道的二维波函数切片：两种颜色表示波函数相位/符号，颜色强度体现振幅；节点会直接显示出来。"


def _proj(v):
    x,y,z=v; return np.array([x-y*.72, z+(x+y)*.36])


def lattice(output_dir:Path, kind:str="fcc", cells:int=2)->tuple[Path,str]:
    kind=kind.lower(); cells=max(1,min(int(cells),3))
    bases={
      "sc":[(0,0,0)],
      "bcc":[(0,0,0),(.5,.5,.5)],
      "fcc":[(0,0,0),(0,.5,.5),(.5,0,.5),(.5,.5,0)],
    }
    if kind=="diamond":
        f=bases["fcc"]; bases["diamond"]=f+[(x+.25,y+.25,z+.25) for x,y,z in f]
    if kind not in bases: raise MoreLabError("lattice 支持 sc / bcc / fcc / diamond")
    pts=[]
    for i,j,k in itertools.product(range(cells+1),repeat=3):
        for b in bases[kind]:
            q=np.array((i+b[0],j+b[1],k+b[2]),float)
            if np.all(q<=cells+1e-8): pts.append(q)
    P=np.array([_proj(v) for v in pts]); mn=P.min(0); mx=P.max(0); scale=620/max(float((mx-mn).max()),1); off=np.array([450,430])-(mn+mx)/2*scale
    img=Image.new("RGB",(900,800),(249,249,246)); d=ImageDraw.Draw(img)
    # unit-cell grid edges
    for i,j,k in itertools.product(range(cells+1),repeat=3):
        for axis in range(3):
            a=np.array((i,j,k),float); b=a.copy(); b[axis]+=1
            if b[axis]<=cells:
                pa=_proj(a)*scale+off; pb=_proj(b)*scale+off; d.line((*pa,*pb),fill=(175,175,180),width=2)
    # painter order by x+y+z
    for q in sorted(pts,key=lambda q:q.sum()):
        p2=_proj(q)*scale+off; r=8 if any(abs(q-round(q))>.1 for q in q) else 9
        d.ellipse((p2[0]-r,p2[1]-r,p2[0]+r,p2[1]+r),fill=(50,105,175),outline=(15,45,85),width=2)
    _title(img,f"Crystal lattice · {kind.upper()} · {cells}×{cells}×{cells}")
    p=_out(output_dir,f"lattice-{kind}-{cells}"); img.save(p)
    return p,f"{kind.upper()} 晶格的等轴投影。可和 /lab xrd {kind} 联动看实空间结构如何变成衍射峰。"


def xrd(output_dir:Path, kind:str="fcc", a:float=4.05, wavelength:float=1.5406)->tuple[Path,str]:
    kind=kind.lower(); a=float(a); wavelength=float(wavelength)
    if kind not in {"sc","bcc","fcc","diamond"}: raise MoreLabError("xrd 支持 sc / bcc / fcc / diamond")
    if a<=0 or wavelength<=0: raise MoreLabError("晶格常数和波长必须为正")
    groups={}
    for h,k,l in itertools.product(range(0,9),repeat=3):
        if h==k==l==0: continue
        allowed=True; parity=(h%2,k%2,l%2); sm=h+k+l
        if kind=="bcc": allowed=(sm%2==0)
        elif kind in {"fcc","diamond"}: allowed=(parity[0]==parity[1]==parity[2])
        if kind=="diamond" and allowed and all(v%2==0 for v in (h,k,l)): allowed=(sm%4==0)
        if not allowed: continue
        q=h*h+k*k+l*l; d=a/math.sqrt(q); s=wavelength/(2*d)
        if s>=1: continue
        tt=2*math.degrees(math.asin(s));
        if tt>120: continue
        g=groups.setdefault(q,{"tt":tt,"count":0,"hkl":(h,k,l)}); g["count"]+=1
    peaks=sorted(groups.values(),key=lambda z:z["tt"]); maxc=max([x["count"] for x in peaks] or [1])
    img=Image.new("RGB",(1000,700),(250,250,247)); d=ImageDraw.Draw(img); left,right,bottom,top=65,960,620,90
    d.line((left,bottom,right,bottom),fill=(35,35,40),width=2)
    for pk in peaks:
        x=left+pk["tt"]/120*(right-left); H=450*(pk["count"]/maxc)**.65; d.line((x,bottom,x,bottom-H),fill=(35,90,165),width=3)
        if H>120: d.text((x-16,bottom-H-24),"".join(map(str,pk["hkl"])),fill=(30,30,35),font=_font(14))
    d.text((440,650),"2θ (0–120°)",fill=(30,30,35),font=_font(20)); _title(img,f"Ideal powder XRD · {kind.upper()} · a={a:g} Å · λ={wavelength:g} Å")
    p=_out(output_dir,f"xrd-{kind}-{a:g}-{wavelength:g}"); img.save(p)
    return p,"理想立方晶体粉末衍射：峰位置来自 Bragg 定律，系统消光由晶格的结构因子决定；这里展示几何/选择定则，不替代真实强度计算。"


def knot(output_dir:Path, kind:str="trefoil", pnum:int=2, qnum:int=3)->tuple[Path,str]:
    kind=kind.lower(); t=np.linspace(0,2*np.pi,2600)
    if kind in {"trefoil","3_1"}: x=(2+np.cos(3*t))*np.cos(2*t); y=(2+np.cos(3*t))*np.sin(2*t); z=np.sin(3*t); name="trefoil 3₁"
    elif kind in {"figure8","4_1"}: x=(2+np.cos(2*t))*np.cos(3*t); y=(2+np.cos(2*t))*np.sin(3*t); z=np.sin(4*t); name="figure-eight 4₁"
    elif kind in {"torus","t"}:
        pnum=max(1,min(int(pnum),9)); qnum=max(1,min(int(qnum),9)); x=(2+.7*np.cos(qnum*t))*np.cos(pnum*t); y=(2+.7*np.cos(qnum*t))*np.sin(pnum*t); z=.7*np.sin(qnum*t); name=f"torus ({pnum},{qnum})"
    else: raise MoreLabError("knot 支持 trefoil / figure8 / torus [p q]")
    # rotate then project; depth controls shade
    a=.55; b=.75; X=x*np.cos(a)-y*np.sin(a); Y=x*np.sin(a)*np.cos(b)+y*np.cos(a)*np.cos(b)-z*np.sin(b); Z=x*np.sin(a)*np.sin(b)+y*np.cos(a)*np.sin(b)+z*np.cos(b)
    img=Image.new("RGB",(900,800),(249,249,246)); d=ImageDraw.Draw(img); span=max(np.ptp(X),np.ptp(Y)); sc=650/span; px=450+X*sc; py=430-Y*sc
    # draw in short depth-sorted segments to suggest over/under structure
    segs=sorted(range(len(t)-1),key=lambda i:(Z[i]+Z[i+1])/2)
    zmin,zmax=Z.min(),Z.max()
    for i in segs:
        f=((Z[i]+Z[i+1])/2-zmin)/(zmax-zmin+1e-9); col=(int(45+130*f),int(65+70*f),int(150+80*f)); d.line((px[i],py[i],px[i+1],py[i+1]),fill=col,width=5)
    _title(img,f"Knot projection · {name}")
    path=_out(output_dir,f"knot-{kind}-{pnum}-{qnum}"); img.save(path)
    return path,"结绳不是“看起来打结”就结束：三维闭曲线的投影、交叉信息和不变量构成了拓扑学的典型入口。"


def brownian(output_dir:Path, walkers:int=36, steps:int=700)->tuple[Path,str]:
    walkers=max(3,min(int(walkers),100)); steps=max(50,min(int(steps),4000)); rng=np.random.default_rng(20260831); delta=rng.normal(size=(walkers,steps,2)); pos=np.concatenate([np.zeros((walkers,1,2)),np.cumsum(delta,axis=1)],axis=1)
    span=max(float(np.max(np.abs(pos))),1); img=Image.new("RGB",(900,800),(249,249,246)); d=ImageDraw.Draw(img); sc=330/span
    for j in range(walkers):
        pts=[(450+x*sc,420-y*sc) for x,y in pos[j]]; col=(40+((j*73)%150),70+((j*37)%130),100+((j*53)%120)); d.line(pts,fill=col,width=1)
        x,y=pts[-1]; d.ellipse((x-3,y-3,x+3,y+3),fill=col)
    rms=float(np.sqrt(np.mean(np.sum(pos[:,-1,:]**2,axis=1)))); _title(img,f"2D Brownian random walks · walkers={walkers} · steps={steps}")
    p=_out(output_dir,f"brownian-{walkers}-{steps}"); img.save(p)
    return p,f"二维随机游走的均方根位移本次约 {rms:.2f} 格；典型尺度随步数按 √N 增长。"


def sir(output_dir:Path, r0:float=2.5, infectious_days:float=7.0)->tuple[Path,str]:
    r0=float(r0); days=float(infectious_days)
    if r0<=0 or r0>10 or days<=0: raise MoreLabError("R0 需在 0..10，感染期需为正")
    gamma=1/days; beta=r0*gamma; dt=.05; T=160; n=int(T/dt); S=np.empty(n);I=np.empty(n);R=np.empty(n); S[0]=.999;I[0]=.001;R[0]=0
    for k in range(n-1):
        ds=-beta*S[k]*I[k]; di=beta*S[k]*I[k]-gamma*I[k]; S[k+1]=S[k]+ds*dt; I[k+1]=I[k]+di*dt; R[k+1]=R[k]+gamma*I[k]*dt
    img=Image.new("RGB",(1000,700),(250,250,247)); d=ImageDraw.Draw(img); left,right,top,bottom=65,960,90,620
    for arr,col,name in ((S,(45,110,180),"S"),(I,(205,65,50),"I"),(R,(50,150,90),"R")):
        pts=[(left+k/(n-1)*(right-left),bottom-arr[k]*(bottom-top)) for k in range(0,n,4)]; d.line(pts,fill=col,width=4); d.text((right-40,pts[-1][1]-8),name,fill=col,font=_font(19))
    peak=float(I.max()); peakday=float(np.argmax(I)*dt); _title(img,f"SIR epidemic · R₀={r0:g} · infectious period={days:g} d")
    p=_out(output_dir,f"sir-{r0:g}-{days:g}"); img.save(p)
    return p,f"经典 SIR 模型：感染比例峰值约 {peak:.1%}，出现在第 {peakday:.1f} 天。它是教学模型，不用于现实疫情预测。"


def predator(output_dir:Path, alpha:float=1.1,beta:float=.4,delta:float=.1,gamma:float=.4)->tuple[Path,str]:
    vals=[float(alpha),float(beta),float(delta),float(gamma)]
    if any(v<=0 or v>5 for v in vals): raise MoreLabError("Lotka–Volterra 四个参数需在 0..5")
    dt=.01; n=5000; x=np.empty(n);y=np.empty(n);x[0]=10;y[0]=5
    for i in range(n-1):
        dx=alpha*x[i]-beta*x[i]*y[i]; dy=delta*x[i]*y[i]-gamma*y[i]; x[i+1]=max(0,x[i]+dx*dt); y[i+1]=max(0,y[i]+dy*dt)
        if x[i+1]>100 or y[i+1]>100: x[i+1]=min(x[i+1],100); y[i+1]=min(y[i+1],100)
    img=Image.new("RGB",(1000,720),(250,250,247)); d=ImageDraw.Draw(img); _title(img,"Lotka–Volterra predator–prey dynamics")
    mx=max(float(x.max()),1); my=max(float(y.max()),1); pts=[(70+x[i]/mx*390,650-y[i]/my*520) for i in range(0,n,3)]; d.line(pts,fill=(110,65,170),width=2); d.text((90,90),"phase portrait",fill=(30,30,35),font=_font(20))
    # time series right
    for arr,m,col in ((x,mx,(45,105,180)),(y,my,(205,75,50))):
        pts=[(540+i/(n-1)*410,650-arr[i]/m*520) for i in range(0,n,4)]; d.line(pts,fill=col,width=2)
    d.text((570,90),"population vs time",fill=(30,30,35),font=_font(20))
    p=_out(output_dir,"predator"); img.save(p)
    return p,"Lotka–Volterra 捕食者—猎物模型会形成闭合/近闭合相轨迹：两个种群的峰值彼此错位，而不是同步涨跌。"


def lens(output_dir:Path, focal:float=100., obj_distance:float=180.)->tuple[Path,str]:
    f=float(focal); do=float(obj_distance)
    if f==0 or abs(do)<5: raise MoreLabError("焦距不能为 0，物距绝对值需 ≥5")
    di=1/(1/f-1/do) if abs(1/f-1/do)>1e-9 else math.inf
    img=Image.new("RGB",(1000,650),(250,250,247)); d=ImageDraw.Draw(img); ox,oy=500,350; scale=2.0
    d.line((40,oy,960,oy),fill=(60,60,65),width=2); d.line((ox,80,ox,600),fill=(45,105,180),width=5); d.text((ox+8,85),"lens",fill=(45,105,180),font=_font(18))
    for sign in (-1,1): x=ox+sign*f*scale; d.ellipse((x-5,oy-5,x+5,oy+5),fill=(205,70,50)); d.text((x-8,oy+10),"F",fill=(205,70,50),font=_font(16))
    xo=ox-do*scale; h=120; d.line((xo,oy,xo,oy-h),fill=(25,25,30),width=5); d.polygon([(xo,oy-h),(xo-8,oy-h+18),(xo+8,oy-h+18)],fill=(25,25,30))
    if math.isfinite(di) and abs(di)*scale<600:
        xi=ox+di*scale; hi=-h*di/do; d.line((xi,oy,xi,oy-hi),fill=(80,140,70),width=4)
    # principal rays from object top
    d.line((xo,oy-h,ox,oy-h),fill=(215,155,40),width=2)
    targetx=960; targety=oy+(targetx-ox)*(h)/(f*scale); d.line((ox,oy-h,targetx,targety),fill=(215,155,40),width=2)
    slope=(oy-(oy-h))/(ox-xo); yright=(oy-h)+slope*(960-xo); d.line((xo,oy-h,960,yright),fill=(190,70,55),width=2)
    _title(img,f"Thin lens · f={f:g} · object distance={do:g} · image distance={di:.2f}")
    p=_out(output_dir,f"lens-{f:g}-{do:g}"); img.save(p)
    return p,f"薄透镜公式给出像距 dᵢ≈{di:.2f}；正负号和实/虚像由参数共同决定。"


def quantum_well(output_dir:Path, nlevel:int=1)->tuple[Path,str]:
    nlevel=max(1,min(int(nlevel),12)); x=np.linspace(0,1,900); psi=np.sqrt(2)*np.sin(nlevel*np.pi*x); prob=psi*psi
    img=Image.new("RGB",(1000,700),(250,250,247)); d=ImageDraw.Draw(img); _title(img,f"Infinite square well · n={nlevel} · E ∝ n²={nlevel*nlevel}")
    # walls and zero line
    d.line((70,350,930,350),fill=(80,80,85),width=2); d.line((70,100,70,620),fill=(20,20,25),width=5); d.line((930,100,930,620),fill=(20,20,25),width=5)
    pts=[(70+xx*860,350-yy*125) for xx,yy in zip(x,psi)]; d.line(pts,fill=(45,100,180),width=3)
    pts2=[(70+xx*860,600-yy/prob.max()*170) for xx,yy in zip(x,prob)]; d.line(pts2,fill=(205,70,50),width=3); d.text((80,565),"|ψ|²",fill=(205,70,50),font=_font(18))
    p=_out(output_dir,f"well-{nlevel}"); img.save(p)
    return p,f"无限深方势阱第 n={nlevel} 个本征态有 {nlevel-1} 个内部节点，能量按 n² 增长。"


def diffraction(output_dir:Path, separation:float=4., width:float=1., wavelength:float=.5)->tuple[Path,str]:
    dsep=float(separation); a=float(width); lam=float(wavelength)
    if min(dsep,a,lam)<=0: raise MoreLabError("缝距、缝宽、波长必须为正")
    th=np.linspace(-.7,.7,1600); beta=np.pi*a*np.sin(th)/lam; alpha=np.pi*dsep*np.sin(th)/lam; env=np.sinc(beta/np.pi)**2; I=env*np.cos(alpha)**2; I/=max(I.max(),1e-12)
    img=Image.new("RGB",(1000,700),(250,250,247)); dr=ImageDraw.Draw(img); _title(img,f"Double-slit Fraunhofer diffraction · d={dsep:g}, a={a:g}, λ={lam:g}")
    pts=[(60+i/(len(I)-1)*900,620-v*500) for i,v in enumerate(I)]; dr.line(pts,fill=(40,95,180),width=3); dr.line((60,620,960,620),fill=(60,60,65),width=2)
    p=_out(output_dir,f"diffraction-{dsep:g}-{a:g}-{lam:g}"); img.save(p)
    return p,"双缝远场图样 = 单缝衍射包络 × 双缝干涉条纹；改缝距与缝宽可以分别控制细条纹和大包络。"


def replicator(output_dir:Path, bias:float=0.0)->tuple[Path,str]:
    eps=float(bias); A=np.array([[0,-1,1],[1,0,-1],[-1,1,0]],float)+eps*np.eye(3); dt=.012; n=7000; x=np.array([.72,.18,.10],float); hist=[]
    for _ in range(n):
        hist.append(x.copy()); fit=A@x; avg=x@fit; x=x+dt*x*(fit-avg); x=np.maximum(x,1e-10); x/=x.sum()
    h=np.array(hist); V=np.array([[450,85],[100,690],[800,690]],float); P=h@V
    img=Image.new("RGB",(900,780),(249,249,246)); d=ImageDraw.Draw(img); d.polygon([tuple(v) for v in V],outline=(40,40,45)); d.text((435,58),"R",fill=(30,30,35),font=_font(20)); d.text((75,700),"P",fill=(30,30,35),font=_font(20)); d.text((810,700),"S",fill=(30,30,35),font=_font(20)); d.line([tuple(v) for v in P[::3]],fill=(170,55,145),width=3); _title(img,f"Replicator dynamics · Rock–Paper–Scissors · bias={eps:g}")
    p=_out(output_dir,f"replicator-{eps:g}"); img.save(p)
    return p,"石头剪刀布的复制子动力学在策略单纯形上运行；即使规则完全对称，也不意味着系统一定静止在 1/3,1/3,1/3。"


def help_text()->str:
    return (
      "  /lab moire [angle_deg] [spacing_px]\n"
      "  /lab orbital [{1s|2px|2py|3dxy|3dz2}]\n"
      "  /lab lattice [{sc|bcc|fcc|diamond}] [cells]\n"
      "  /lab xrd [{sc|bcc|fcc|diamond}] [a] [wavelength]\n"
      "  /lab knot [{trefoil|figure8|torus}] [p] [q]\n"
      "  /lab brownian [walkers] [steps]\n"
      "  /lab sir [R0] [infectious_days]\n"
      "  /lab predator [alpha] [beta] [delta] [gamma]\n"
      "  /lab lens [focal] [object_distance]\n"
      "  /lab well [n]\n"
      "  /lab diffraction [slit_sep] [slit_width] [wavelength]\n"
      "  /lab replicator [bias]\n"
      + __import__("doge_v5.visual_lab_fun", fromlist=["help_text"]).help_text()
    )


def render_more(output_dir:Path,payload:str):
    p=payload.strip().split();
    if not p:return None
    h=p[0].lower();r=p[1:]
    if h=="moire":return moire(output_dir,float(r[0]) if r else 5,float(r[1]) if len(r)>1 else 18)
    if h=="orbital":return orbital(output_dir,r[0] if r else "2px")
    if h=="lattice":return lattice(output_dir,r[0] if r else "fcc",int(r[1]) if len(r)>1 else 2)
    if h in {"xrd","diffraction-crystal"}:return xrd(output_dir,r[0] if r else "fcc",float(r[1]) if len(r)>1 else 4.05,float(r[2]) if len(r)>2 else 1.5406)
    if h=="knot":return knot(output_dir,r[0] if r else "trefoil",int(r[1]) if len(r)>1 else 2,int(r[2]) if len(r)>2 else 3)
    if h in {"brownian","walk"}:return brownian(output_dir,int(r[0]) if r else 36,int(r[1]) if len(r)>1 else 700)
    if h=="sir":return sir(output_dir,float(r[0]) if r else 2.5,float(r[1]) if len(r)>1 else 7)
    if h in {"predator","lotka"}:
        vals=[float(x) for x in r]
        defaults=[1.1,.4,.1,.4]
        vals += defaults[len(vals):]
        return predator(output_dir,*vals[:4])
    if h=="lens":return lens(output_dir,float(r[0]) if r else 100,float(r[1]) if len(r)>1 else 180)
    if h in {"well","quantumwell"}:return quantum_well(output_dir,int(r[0]) if r else 1)
    if h in {"diffraction","slit"}:return diffraction(output_dir,float(r[0]) if r else 4,float(r[1]) if len(r)>1 else 1,float(r[2]) if len(r)>2 else .5)
    if h in {"replicator","rps"}:return replicator(output_dir,float(r[0]) if r else 0)
    from .visual_lab_fun import render_fun
    fun = render_fun(output_dir, payload)
    if fun is not None:
        return fun
    return None
