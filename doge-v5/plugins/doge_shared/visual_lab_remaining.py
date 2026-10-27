"""Qubit mixed state/gate dynamics, Lorentz boosts, and truly stabilized sandpiles."""
from __future__ import annotations

import math
import time
from pathlib import Path
import numpy as np

from .science_expression import float_opt,int_opt,numbers
from .visual_lab import LabError,_out,_heat_rgb,_title
from PIL import Image


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def bloch_general(output_dir:Path,opt:dict):
    if "rho" in opt and "bloch" in opt:raise LabError("--rho 与 --bloch 不能同时指定")
    sigma=[
        np.array([[0,1],[1,0]],complex),
        np.array([[0,-1j],[1j,0]],complex),
        np.array([[1,0],[0,-1]],complex),
    ]
    if "rho" in opt:
        if any(x in opt for x in ("theta","phi")):
            raise LabError("指定 --rho 时不可同时输入纯态角度")
        arr=opt["rho"].replace("i","j").split(",")
        if len(arr)!=4:raise LabError("rho 必须是二维密度矩阵四个复数元素，例如 0.5,0,0,0.5")
        try:rho=np.asarray([complex(t.strip()) for t in arr]).reshape(2,2)
        except ValueError as exc:raise LabError("密度矩阵元素应是有限复数") from exc
        if not np.isfinite(rho).all() or np.max(np.abs(rho))>1e4:raise LabError("密度矩阵数值无效")
        if not np.allclose(rho,rho.conj().T,atol=1e-6):raise LabError("rho 必须是 Hermitian")
        if not np.isclose(rho.trace(),1,atol=1e-6):raise LabError("rho 的迹必须为 1")
        if np.min(np.linalg.eigvalsh(rho))<-1e-7:raise LabError("rho 必须半正定")
    elif "bloch" in opt:
        if any(x in opt for x in ("theta","phi")):
            raise LabError("--bloch 与纯态角度 --theta/--phi 不可同时指定")
        x,y,z=numbers(opt["bloch"],"Bloch x,y,z",low=3,high=3)
        if x*x+y*y+z*z>1+1e-8:raise LabError("Bloch 向量长度不能超过 1")
        rho=.5*(np.eye(2)+x*sigma[0]+y*sigma[1]+z*sigma[2])
    else:
        theta=float_opt(opt.get("theta",60),"theta",-360,360)
        phi=float_opt(opt.get("phi",45),"phi",-360,360)
        th=np.deg2rad(theta);ph=np.deg2rad(phi)
        state=np.array([math.cos(th/2),np.exp(1j*ph)*math.sin(th/2)])
        rho=np.outer(state,state.conj())
    gates=opt.get("gates","")
    applied=[]
    for token in gates.split(";"):
        token=token.strip()
        if not token:continue
        if len(applied)>=32:raise LabError("单次最多计算 32 个量子门")
        name,sep,theta=token.partition(":")
        name=name.upper()
        I=np.eye(2)
        if name=="H" and not sep:
            U=(sigma[0]+sigma[2])/np.sqrt(2)
        elif name in {"X","Y","Z"} and not sep:
            U=sigma["XYZ".index(name)]
        elif name in {"S","T"} and not sep:
            U=np.diag([1,np.exp(1j*(np.pi/2 if name=="S" else np.pi/4))])
        elif name in {"RX","RY","RZ"} and sep:
            angle=float_opt(theta,name,-3600,3600)*math.pi/180
            U=np.cos(angle/2)*I-1j*np.sin(angle/2)*sigma["XYZ".index(name[1])]
        else:raise LabError("gates 仅支持 H/X/Y/Z/S/T/Rx:角度/Ry:角度/Rz:角度；用 ; 分隔")
        rho=U@rho@U.conj().T
        applied.append(token)
    xyz=np.array([np.trace(rho@s).real for s in sigma],float)
    purity=float(np.trace(rho@rho).real)
    eig=np.linalg.eigvalsh(rho)
    if not np.isfinite(xyz).all() or np.min(eig)<-1e-6:
        raise LabError("量子状态不满足密度矩阵约束")
    plt=_plt()
    fig=plt.figure(figsize=(8,7),dpi=105)
    try:
        ax=fig.add_subplot(111,projection="3d")
        u=np.linspace(0,2*np.pi,41)
        v=np.linspace(0,np.pi,21)
        X=np.outer(np.cos(u),np.sin(v));Y=np.outer(np.sin(u),np.sin(v));Z=np.outer(np.ones_like(u),np.cos(v))
        ax.plot_wireframe(X,Y,Z,color="#b1b1b1",linewidth=.4,alpha=.5)
        ax.quiver(0,0,0,*xyz,color="#aa2728",linewidth=3,arrow_length_ratio=.12)
        for axis,label in enumerate(("x","y","z")):
            p=np.zeros(3);p[axis]=1.1
            ax.text(*p,label)
        ax.set_xlim(-1.1,1.1);ax.set_ylim(-1.1,1.1);ax.set_zlim(-1.1,1.1)
        ax.set_box_aspect((1,1,1));ax.set_title(f"Qubit rho | purity={purity:.4g} | {len(applied)} gates")
        fig.tight_layout();path=_out(output_dir,"qubit-density");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"真正由 2x2 密度矩阵计算的单量子比特状态："
        f"Bloch r={xyz.round(6).tolist()}，|r|={np.linalg.norm(xyz):.6g}，"
        f"Tr(ρ²)={purity:.6g}，特征值={eig.round(6).tolist()}，"
        f"已执行门={applied}。支持纯态/混态和酉门幺正演化，不包含噪声通道与多量子比特纠缠。")


def lorentz_general(output_dir:Path,opt:dict):
    beta=float_opt(opt.get("beta",.6),"beta",-.999,.999)
    gamma=1/math.sqrt(1-beta**2)
    points=[numbers(s,"event ct,x",low=2,high=2)
            for s in opt.get("events","1,0;2,1;3,-1").split(";")]
    if not 1<=len(points)<=20:raise LabError("需提供 1..20 个时空事件")
    E=np.asarray(points,float)
    T=np.array([[gamma,-beta*gamma],[-beta*gamma,gamma]])
    transformed=E@T.T
    before=E[:,0]**2-E[:,1]**2
    after=transformed[:,0]**2-transformed[:,1]**2
    err=float(np.max(np.abs(before-after)))
    plt=_plt();fig,axes=plt.subplots(1,2,figsize=(11,6),dpi=105)
    try:
        for ax,coords,title in zip(axes,(E,transformed),("frame S","boosted frame S'")):
            ax.scatter(coords[:,1],coords[:,0],s=55)
            for i,(t,x) in enumerate(coords):
                ax.annotate(str(i+1),(x,t),xytext=(4,4),textcoords="offset points")
            extreme=max(2,float(np.max(np.abs(coords)))*1.15)
            z=np.linspace(-extreme,extreme,100)
            ax.plot(z,z,color="#b2a065",ls="--",lw=1)
            ax.plot(z,-z,color="#b2a065",ls="--",lw=1)
            ax.set_xlim(-extreme,extreme);ax.set_ylim(-extreme,extreme)
            ax.set_aspect("equal");ax.set_xlabel("x");ax.set_ylabel("ct")
            ax.set_title(title);ax.grid(alpha=.2)
        fig.suptitle(f"1+1 Lorentz transform | beta={beta:g}, gamma={gamma:.5g}")
        fig.tight_layout();path=_out(output_dir,"lorentz-events");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"Lorentz boost β={beta:g}, γ={gamma:.6g}；"
        f"原始 (ct,x)={E.tolist()}，变换后 (ct',x')={np.round(transformed,6).tolist()}；"
        f"事件间隔 s²=(ct)²-x² 保持不变，最大数值误差 {err:.4g}。"
        "采用 c=1 的 1+1 维平直闵可夫斯基时空。")


def sandpile_general(output_dir:Path,opt:dict):
    n=int_opt(opt.get("size",151),"size",31,251)
    if n%2==0:raise LabError("size 必须为奇数，以便中心坐标明确")
    if "sites" in opt and "grains" in opt:
        raise LabError("指定 --sites 时不要同时使用 --grains；不会忽略任何初始沙粒")
    state=np.zeros((n,n),np.int64)
    c=n//2
    if "sites" in opt:
        sites=[numbers(s,"sites x,y,grains",low=3,high=3) for s in opt["sites"].split(";")]
        if not 1<=len(sites)<=50:raise LabError("sites 需给 1..50 个投沙位置")
        for x,y,g in sites:
            if x!=int(x) or y!=int(y) or g!=int(g) or g<0 or g>1e6:
                raise LabError("沙粒坐标/粒数应为非负整数")
            x,y=int(x)+c,int(y)+c
            if not(0<=x<n and 0<=y<n):raise LabError("投沙位置超出棋盘")
            state[y,x]+=int(g)
    else:state[c,c]=int_opt(opt.get("grains",120000),"grains",0,2000000)
    if int(state.sum())>2000000:raise LabError("总沙粒数最多 2,000,000")
    seed_total=int(state.sum())
    odometer=np.zeros_like(state)
    max_iters=int_opt(opt.get("maxiter",30000),"maxiter",100,100000)
    boundary=opt.get("boundary","open")
    if boundary not in {"open","wrap"}:raise LabError("boundary=open|wrap")
    sink=opt.get("sink")
    if boundary=="wrap":
        if not sink:raise LabError("周期边界必须通过 --sink x,y 指定吸收点，否则不能保证稳定")
        sx,sy=numbers(sink,"sink x,y",low=2,high=2)
        if int(sx)!=sx or int(sy)!=sy or not(0<=sx+c<n and 0<=sy+c<n):
            raise LabError("sink 必须为棋盘内整数坐标")
        sink_x,sink_y=int(sx)+c,int(sy)+c
        state[sink_y,sink_x]=0
    elif sink:
        raise LabError("只有 wrap 周期边界需要 --sink")
    iterations=0
    deadline=time.monotonic()+8.0
    for iterations in range(1,max_iters+1):
        if iterations % 64 == 0 and time.monotonic()>deadline:
            raise LabError("沙堆在 8 秒计算预算内尚未完全稳定；请降低 grains、调整 sites 或缩小 size")
        transfer=state//4
        if not transfer.any():break
        odometer+=transfer
        state%=4
        if boundary=="open":
            state[1:,:]+=transfer[:-1,:]
            state[:-1,:]+=transfer[1:,:]
            state[:,1:]+=transfer[:,:-1]
            state[:,:-1]+=transfer[:,1:]
        else:
            state+=np.roll(transfer,1,0)+np.roll(transfer,-1,0)+np.roll(transfer,1,1)+np.roll(transfer,-1,1)
            state[sink_y,sink_x]=0
    if (state>=4).any():
        raise LabError("沙堆尚未达到真正稳定态，达到 maxiter 限制；可减小 grains 或增大 maxiter")
    lost=seed_total-int(state.sum())
    plt=_plt();fig,ax=plt.subplots(1,2,figsize=(11,6),dpi=110)
    try:
        ax[0].imshow(state,cmap="inferno",vmin=0,vmax=3,interpolation="nearest")
        ax[0].set_title("Stable height (all <=3)")
        ax[1].imshow(np.log1p(odometer),cmap="viridis",interpolation="nearest")
        ax[1].set_title("Toppling odometer log(1+u)")
        for a in ax:a.axis("off")
        fig.tight_layout()
        path=_out(output_dir,"sandpile-stable");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"Abelian sandpile 真正稳定化：N={n}，初始沙粒 {seed_total}，"
        f"剩余 {int(state.sum())}，边界吸收损失 {lost}，迭代 {iterations} 轮，"
        f"总 topplings={int(odometer.sum())}，最终所有格点高度均 <=3；"
        f"boundary={boundary}，sink={sink or '外部边界'}。")
