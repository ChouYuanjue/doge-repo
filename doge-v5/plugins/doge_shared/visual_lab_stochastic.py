"""Reproducible stochastic laboratories: every run computes a seeded simulation."""
from __future__ import annotations

import math
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .science_expression import float_opt, int_opt, numbers
from .visual_lab import LabError, _out, _title


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def ising(output_dir:Path,opt:dict):
    T=float_opt(opt.get("temperature",2.269),"temperature",.01,10)
    j=float_opt(opt.get("coupling",1),"coupling",-10,10)
    h=float_opt(opt.get("field",0),"field",-10,10)
    sweeps=int_opt(opt.get("sweeps",180),"sweeps",1,900)
    size=int_opt(opt.get("size",160),"size",32,240)
    if size%2:raise LabError("周期边界的棋盘必须为偶数尺寸（checkerboard Monte Carlo）")
    seed=int_opt(opt.get("seed",2026),"seed",0,2**31-1)
    init=opt.get("init","random")
    rng=np.random.default_rng(seed)
    if init=="random":spins=rng.choice(np.array([-1,1],np.int8),(size,size))
    elif init in {"up","down"}:spins=np.full((size,size),1 if init=="up" else -1,dtype=np.int8)
    else:raise LabError("init=random|up|down")
    yy,xx=np.indices(spins.shape)
    history=[]
    for _ in range(sweeps):
        for parity in (0,1):
            near=np.roll(spins,1,0)+np.roll(spins,-1,0)+np.roll(spins,1,1)+np.roll(spins,-1,1)
            de=2*spins*(j*near+h)
            mask=(xx+yy)%2==parity
            with np.errstate(over="ignore"):
                acceptance=(de<=0)|(rng.random(spins.shape)<np.exp(np.clip(-de/T,-700,100)))
            spins[mask&acceptance]*=-1
        history.append(float(spins.mean()))
    rgb=np.repeat(np.where(spins[:,:,None]>0,242,35).astype(np.uint8),3,axis=2)
    img=Image.fromarray(rgb,"RGB").resize((800,800),Image.Resampling.NEAREST)
    _title(img,f"Ising 2D | T={T:g}, J={j:g}, h={h:g}, m={history[-1]:.3g}")
    path=_out(output_dir,"ising-general");img.save(path)
    return path,(f"二维 Ising Metropolis 棋盘更新：T={T:g}, J={j:g}, h={h:g}，"
       f"{sweeps} sweeps，{size}² 自旋，seed={seed}，init={init}，末态 m={history[-1]:.5f}。"
       "仅在 J=1、h=0、热力学极限下临界温度约 2.269。")


def percolation(output_dir:Path,opt:dict):
    p=float_opt(opt.get("p",.5927),"p",0,1)
    n=int_opt(opt.get("size",180),"size",32,420)
    seed=int_opt(opt.get("seed",2026),"seed",0,2**31-1)
    kind=opt.get("kind","site")
    if kind not in {"site","bond"}:raise LabError("kind=site|bond")
    rng=np.random.default_rng(seed)
    if kind=="site":
        open_=rng.random((n,n))<p
        right=down=None
    else:
        open_=np.ones((n,n),bool)
        right=rng.random((n,n-1))<p
        down=rng.random((n-1,n))<p
    seen=np.zeros_like(open_)
    queue=deque()
    for j in np.flatnonzero(open_[0]):
        seen[0,j]=True;queue.append((0,int(j)))
    while queue:
        y,x=queue.popleft()
        for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
            ny,nx=y+dy,x+dx
            if not (0<=ny<n and 0<=nx<n) or seen[ny,nx] or not open_[ny,nx]:continue
            if kind=="bond":
                if dy==1 and not down[y,x]:continue
                if dy==-1 and not down[ny,x]:continue
                if dx==1 and not right[y,x]:continue
                if dx==-1 and not right[y,nx]:continue
            seen[ny,nx]=True;queue.append((ny,nx))
    spans=bool(seen[-1].any())
    rgb=np.full((n,n,3),245,np.uint8)
    rgb[open_]=(100,117,131)
    rgb[seen]=(232,69,54)
    img=Image.fromarray(rgb,"RGB").resize((800,800),Image.Resampling.NEAREST)
    _title(img,f"{kind.title()} percolation | p={p:.4g} | {'spanning' if spans else 'non-spanning'}")
    path=_out(output_dir,"percolation-general");img.save(path)
    return path,(f"二维方格{kind}渗流：p={p:g}, N={n}, seed={seed}，"
       f"顶边连通簇 {int(seen.sum())} 点，{'贯穿' if spans else '未贯穿'}。"
       "这是一次 Monte Carlo 样本，不是概率估计。")


def random_matrix(output_dir:Path,opt:dict):
    n=int_opt(opt.get("n",90),"n",4,260)
    seed=int_opt(opt.get("seed",2026),"seed",0,2**31-1)
    kind=opt.get("ensemble","ginibre").lower()
    rng=np.random.default_rng(seed)
    if "ratio" in opt and kind!="wishart":raise LabError("--ratio 只用于 Wishart 系综")
    if kind in {"ginibre","complex","circle"}:
        A=(rng.normal(size=(n,n))+1j*rng.normal(size=(n,n)))/math.sqrt(2*n)
        eigen=np.linalg.eigvals(A)
    elif kind in {"real-ginibre","realginibre"}:
        A=rng.normal(size=(n,n))/math.sqrt(n)
        eigen=np.linalg.eigvals(A)
    elif kind in {"goe","wigner"}:
        A=rng.normal(size=(n,n));A=(A+A.T)/math.sqrt(2*n)
        eigen=np.linalg.eigvalsh(A)
    elif kind=="gue":
        A=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))
        A=(A+A.conj().T)/math.sqrt(4*n)
        eigen=np.linalg.eigvalsh(A)
    elif kind=="wishart":
        ratio=float_opt(opt.get("ratio",1.5),"ratio",.3,6)
        k=max(2,int(round(n*ratio)))
        A=rng.normal(size=(n,k)); eigen=np.linalg.eigvalsh(A@A.T/k)
    else:raise LabError("ensemble=ginibre|real-ginibre|goe|gue|wishart")
    plt=_plt()
    fig,ax=plt.subplots(figsize=(9,7),dpi=110)
    try:
        if np.iscomplexobj(eigen) and np.max(abs(eigen.imag))>1e-9:
            ax.scatter(eigen.real,eigen.imag,s=6,alpha=.8)
            ax.set_xlabel("Re λ");ax.set_ylabel("Im λ")
            ax.set_aspect("equal",adjustable="datalim")
        else:
            ax.hist(eigen.real,bins=min(60,max(8,n//2)),density=True)
            ax.set_xlabel("eigenvalue");ax.set_ylabel("empirical density")
        ax.set_title(f"{kind} | n={n}, seed={seed}");ax.grid(alpha=.2)
        fig.tight_layout();path=_out(output_dir,"randommatrix-general");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"NumPy 真实抽样 {kind} 随机矩阵（N={n}，seed={seed}），"
        f"特征值数量 {len(eigen)}，谱均值 {np.mean(eigen):.5g}；"
        "图中为单次随机矩阵样本，有限规模不保证呈现极限谱律。")


def galton(output_dir:Path,opt:dict):
    from scipy.stats import binom
    rows=int_opt(opt.get("rows",12),"rows",2,50)
    balls=int_opt(opt.get("balls",6000),"balls",10,100000)
    p=float_opt(opt.get("p",.5),"p",0,1)
    seed=int_opt(opt.get("seed",2026),"seed",0,2**31-1)
    rng=np.random.default_rng(seed)
    outcomes=rng.binomial(rows,p,size=balls)
    hist=np.bincount(outcomes,minlength=rows+1)
    expected=balls*binom.pmf(np.arange(rows+1),rows,p)
    plt=_plt()
    fig,ax=plt.subplots(figsize=(10,7),dpi=100)
    try:
        ax.bar(np.arange(rows+1),hist,width=.85,label="sample count")
        ax.plot(np.arange(rows+1),expected,color="#c44a36",lw=2,marker=".",label="exact expectation")
        ax.set_xlabel("right turns");ax.set_ylabel("balls per bin");ax.legend()
        ax.set_title(f"Galton process | rows={rows}, balls={balls}, P(right)={p:g}, seed={seed}")
        ax.grid(alpha=.2);fig.tight_layout()
        path=_out(output_dir,"galton-general");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"独立 Bernoulli(p={p:g}) 逐层左右选择的真实蒙特卡洛模拟："
       f"{balls} 次、{rows} 层，seed={seed}；红线为二项分布 Bin({rows},{p:g}) 的精确期望，"
       f"实测均值转右 {np.average(np.arange(rows+1),weights=hist):.4g} 次。")


def brownian(output_dir:Path,opt:dict):
    walkers=int_opt(opt.get("walkers",36),"walkers",1,200)
    steps=int_opt(opt.get("steps",650),"steps",10,6000)
    D=float_opt(opt.get("diffusion",.5),"diffusion",0,100)
    dx,dy=numbers(opt.get("drift","0,0"),"drift",low=2,high=2)
    seed=int_opt(opt.get("seed",2026),"seed",0,2**31-1)
    rng=np.random.default_rng(seed)
    increments=rng.normal(0,math.sqrt(2*D),size=(walkers,steps,2))+np.array([dx,dy])
    coords=np.concatenate([np.zeros((walkers,1,2)),np.cumsum(increments,axis=1)],axis=1)
    msd=np.mean(np.sum((coords[:,-1]-steps*np.array([dx,dy]))**2,axis=1))
    plt=_plt()
    fig,ax=plt.subplots(figsize=(9,7),dpi=100)
    try:
        for p in coords:
            s=p[::max(1,steps//1000)]
            ax.plot(s[:,0],s[:,1],lw=.8,alpha=.6)
        ax.set_aspect("equal",adjustable="datalim")
        ax.set_title(f"2D Brownian | walkers={walkers}, D={D:g}, drift=({dx:g},{dy:g})")
        ax.set_xlabel("x");ax.set_ylabel("y");ax.grid(alpha=.2)
        fig.tight_layout();path=_out(output_dir,"brownian-general");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"欧拉离散 Wiener 过程：每步增量 N(drift,2D I)，D={D:g}，drift={dx:g},{dy:g}，"
       f"seed={seed}；{walkers} 轨迹、{steps} 步，去漂移 MSD={msd:.5g}，理论值 4Dt={4*D*steps:g}。")


def ant(output_dir:Path,opt:dict):
    steps=int_opt(opt.get("steps",18000),"steps",1,300000)
    size=int_opt(opt.get("size",401),"size",31,701)
    turns=opt.get("turns","RL").upper()
    if not 1<=len(turns)<=12 or not set(turns)<={"L","R","U","N"}:
        raise LabError("turns 是由 R/L/U/N 组成的循环状态规则，例如 RL、RLLR")
    state=np.zeros((size,size),dtype=np.uint8)
    x=y=size//2;direction=0
    dirs=((-1,0),(0,1),(1,0),(0,-1))
    for _ in range(steps):
        k=int(state[y,x]);rule=turns[k]
        direction=(direction+{"R":1,"L":-1,"U":2,"N":0}[rule])%4
        state[y,x]=(k+1)%len(turns)
        dy,dx=dirs[direction]
        y=(y+dy)%size;x=(x+dx)%size
    rng=np.random.default_rng(11)
    colors=np.vstack([np.array([[249,249,245]],dtype=np.uint8),
                      rng.integers(40,210,size=(len(turns)-1,3),dtype=np.uint8)])
    img=Image.fromarray(colors[state],"RGB").resize((800,800),Image.Resampling.NEAREST)
    _title(img,f"Turmite | {turns} | {steps} steps")
    path=_out(output_dir,"turmite");img.save(path)
    return path,f"广义 Langton ant/turmite：状态数 {len(turns)}，规则 {turns}，周期边界 {size}²，{steps} 步，终态 ({x},{y})。"
