"""Parameterized remaining scientific patterns: gratings, beat signals, spiral primes and modular maps."""
from __future__ import annotations

import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

from .science_expression import compute, float_opt, int_opt, numbers
from .visual_lab import LabError, _out, _title, _heat_rgb


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def moire_general(output_dir:Path,opt:dict):
    angle1=float_opt(opt.get("angle1",0),"angle1",-360,360)
    angle2=float_opt(opt.get("angle2",5),"angle2",-360,360)
    d1=float_opt(opt.get("spacing1",18),"spacing1",1,1000)
    d2=float_opt(opt.get("spacing2",18),"spacing2",1,1000)
    phase1=float_opt(opt.get("phase1",0),"phase1",-360,360)
    phase2=float_opt(opt.get("phase2",0),"phase2",-360,360)
    n=int_opt(opt.get("size",640),"size",180,850)
    profile=opt.get("profile","sin")
    if profile not in {"sin","square"}:raise LabError("profile 可用 sin / square")
    yy,xx=np.indices((n,n))
    X=xx-n/2;Y=yy-n/2
    patterns=[]
    q=[]
    for angle,d,phase in ((angle1,d1,phase1),(angle2,d2,phase2)):
        a=math.radians(angle)
        projection=X*math.cos(a)+Y*math.sin(a)
        k=2*math.pi/d
        wave=np.cos(k*projection+math.radians(phase))
        if profile=="square":patterns.append((wave>=0).astype(float))
        else:patterns.append((wave+1)/2)
        q.append(np.array([k*math.cos(a),k*math.sin(a)]))
    result=patterns[0]*patterns[1]
    rgb=np.stack([result,result,result],axis=-1)
    img=Image.fromarray(np.uint8(np.clip(255*(1-rgb),0,255)),"RGB")
    _title(img,f"Two gratings | delta={angle2-angle1:g} deg")
    p=_out(output_dir,"moire-gratings");img.save(p)
    dk=np.linalg.norm(q[0]-q[1])
    period=2*math.pi/dk if dk>1e-10 else math.inf
    return p,(f"两组真实可调相位光栅的透过率叠加 T=T1×T2；"
        f"angle=({angle1:g},{angle2:g})°，spacing=({d1:g},{d2:g}) px，"
        f"phase=({phase1:g},{phase2:g})°，profile={profile}，"
        f"差频空间周期≈{period:.5g}px（当空间频率矢量不同）。")


def phyllotaxis_general(output_dir:Path,opt:dict):
    angle=float_opt(opt.get("angle",137.507764),"angle",-360,360)
    count=int_opt(opt.get("points",1800),"points",50,9000)
    growth=float_opt(opt.get("growth",.5),"growth",.1,2)
    jitter=float_opt(opt.get("jitter",0),"jitter",0,30)
    seed=int_opt(opt.get("seed",42),"seed",0,2**31-1)
    rng=np.random.default_rng(seed)
    theta=(np.arange(1,count+1)*angle+rng.normal(0,jitter,count))*np.pi/180
    radius=360*(np.arange(1,count+1)/count)**growth
    xx=410+radius*np.cos(theta)
    yy=410+radius*np.sin(theta)
    img=Image.new("RGB",(820,820),(248,248,246))
    d=ImageDraw.Draw(img)
    for i,(x,y) in enumerate(zip(xx,yy)):
        t=i/max(count-1,1);color=(int(36+160*t),int(92+80*(1-t)),int(180-110*t))
        d.ellipse((x-2,y-2,x+2,y+2),fill=color)
    _title(img,f"Phyllotaxis | angle={angle:g} deg, growth={growth:g}")
    p=_out(output_dir,"phyllotaxis-general");img.save(p)
    return p,(f"直接计算每个种子的极坐标 r(k)=R·(k/N)^{growth:g}，"
        f"θ(k)=k·{angle:g}°+N(0,{jitter:g}°)；N={count}，seed={seed}。"
        "这是参数化几何排布模型，不声称真实植物严格遵循该公式。")


def beats_general(output_dir:Path,opt:dict):
    from scipy.signal import hilbert
    plt=_plt()
    fs=int_opt(opt.get("rate",1400),"rate",128,8192)
    seconds=float_opt(opt.get("seconds",3),"seconds",.15,12)
    sample_count=int(fs*seconds)
    if sample_count>40000:raise LabError("信号采样过长")
    t=np.arange(sample_count)/fs
    items=[numbers(x,"tone f,amplitude,phase_deg",low=3,high=3)
           for x in opt.get("tones","9,1,0;10,1,0").split(";")]
    if not 1<=len(items)<=8:raise LabError("tones 应包含 1..8 路单频信号")
    y=np.zeros(sample_count)
    fig,axes=plt.subplots(2,1,figsize=(11,7),dpi=105)
    try:
        for f,amp,phase in items:
            if f<0 or f>=fs/2:raise LabError("每个 tone 频率需在 0 到 Nyquist 频率之间")
            if abs(amp)>1e4:raise LabError("tone 振幅过大")
            wave=amp*np.sin(2*np.pi*f*t+np.deg2rad(phase))
            y+=wave
            if len(items)<=6:axes[0].plot(t,wave,lw=.6,label=f"{f:g}Hz")
        if len(items)<=6:axes[0].legend(fontsize=8)
        axes[0].set_title("Constituent harmonic signals")
        envelope=np.abs(hilbert(y))
        axes[1].plot(t,y,lw=.8,label="superposition")
        axes[1].plot(t,envelope,c="#a94d35",lw=1,label="Hilbert envelope")
        axes[1].plot(t,-envelope,c="#a94d35",lw=1)
        axes[1].legend(fontsize=8)
        axes[1].set_xlabel("time (s)")
        for ax in axes:ax.grid(alpha=.2)
        fig.tight_layout();p=_out(output_dir,"beats-general");fig.savefig(p)
    finally:plt.close(fig)
    return p,(f"真实叠加 {len(items)} 路正弦波：{items}，"
              f"采样率 {fs}Hz，时长 {seconds:g}s。"
              f"图中包络通过 scipy.signal.hilbert 解析信号估计；"
              f"RMS={float(np.sqrt(np.mean(y*y))):.5g}。"
              "只有双频且频率接近等特定情形，才可将包络视为单一拍频。")


def ulam_general(output_dir:Path,opt:dict):
    from sympy import isprime
    n=int_opt(opt.get("size",251),"size",31,501)
    if n%2==0:raise LabError("ulam size 必须为奇数")
    start=int_opt(opt.get("start",1),"start",0,10**10)
    step=int_opt(opt.get("step",1),"step",1,100000)
    vals=np.zeros((n,n),np.uint8)
    x=y=n//2; dx=1;dy=0
    stride=1;idx=0
    while idx<n*n:
        for _ in range(2):
            for _ in range(stride):
                if idx>=n*n:break
                if 0<=x<n and 0<=y<n:
                    vals[y,x]=1 if isprime(start+idx*step) else 0
                idx+=1;x+=dx;y+=dy
            dx,dy=-dy,dx
        stride+=1
    rgb=np.where(vals[:,:,None]>0, np.array([23,40,55],np.uint8),
                 np.array([245,245,242],np.uint8))
    img=Image.fromarray(rgb,"RGB").resize((800,800),Image.Resampling.NEAREST)
    _title(img,f"Ulam | start={start}, step={step}, primes={vals.sum()}")
    p=_out(output_dir,"ulam-general");img.save(p)
    return p,f"真正按螺旋顺序逐项测试整数 start+i·step 的素性：start={start}，step={step}，N={n}，图内素数共 {int(vals.sum())} 个。"


def modular_general(output_dir:Path,opt:dict):
    n=int_opt(opt.get("points",360),"points",8,700)
    mult=float_opt(opt.get("multiplier",2),"multiplier",-10000,10000)
    if "expr" in opt and "multiplier" in opt:raise LabError("--expr 与 --multiplier 二选一")
    xx=np.arange(n,dtype=float)
    if "expr" in opt:
        values=compute(opt["expr"],("x","n"),xx,n,shape=xx.shape)
        if np.iscomplexobj(values) and np.any(abs(values.imag)>1e-8):
            raise LabError("模映射输出必须是实数")
        values=np.asarray(values.real,float)
        name=opt["expr"]
    else:
        values=mult*xx
        name=f"{mult:g}*x"
    if not np.isfinite(values).all() or np.max(abs(values))>1e10:
        raise LabError("模映射包含过大的或非有限输出值")
    target=np.mod(values,n)
    a=2*np.pi*xx/n
    b=2*np.pi*target/n
    x1,y1=450+365*np.cos(a),450+365*np.sin(a)
    x2,y2=450+365*np.cos(b),450+365*np.sin(b)
    img=Image.new("RGB",(900,900),(247,247,244));d=ImageDraw.Draw(img)
    d.ellipse((85,85,815,815),outline=(34,38,44),width=2)
    for i in range(n):
        col=(int(50+100*i/n),int(70+60*(1-i/n)),int(155+85*i/n))
        d.line((x1[i],y1[i],x2[i],y2[i]),fill=col,width=1)
    _title(img,"Modular circle: "+name[:50])
    p=_out(output_dir,"modular-general");img.save(p)
    return p,(f"圆周 n={n} 等分，按自定义映射 j=f(i) mod n 真正连接弦；"
              f"f(i)={name}；共绘制 {n} 条连线，不是固定蝴蝶图案。")
