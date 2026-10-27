"""General bounded 1D quantum mechanics and physical-optics models."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from .science_expression import compute, float_opt, int_opt, numbers
from .visual_lab import LabError, _out


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def schrodinger_1d(output_dir:Path,opt:dict):
    from scipy.sparse import diags
    from scipy.sparse.linalg import eigsh
    n = int_opt(opt.get("n", 1), "n", 1, 12)
    count = int_opt(opt.get("levels", max(n, 4)), "levels", n, 12)
    size = int_opt(opt.get("size", 700), "size", 120, 2200)
    xmin,xmax = numbers(opt.get("range", "0,1"), "range", low=2, high=2)
    if not xmin<xmax or xmax-xmin>1e4:raise LabError("range 必须是有效的递增物理空间范围")
    mass = float_opt(opt.get("mass", 1), "mass", 1e-5, 1e6)
    hbar = float_opt(opt.get("hbar", 1), "hbar", 1e-5, 1e4)
    potential = opt.get("potential", "0")
    dx=(xmax-xmin)/(size+1)
    x=xmin+(np.arange(size)+1)*dx
    V=compute(potential,("x",),x,shape=x.shape)
    if np.iscomplexobj(V) and np.max(abs(V.imag))>1e-8:raise LabError("V(x) 不能是非实数")
    V=np.asarray(V.real,float)
    if not np.isfinite(V).all() or np.max(np.abs(V))>1e9:
        raise LabError("V(x) 存在非有限或过大的值")
    alpha=hbar*hbar/(2*mass*dx*dx)
    H=diags([-alpha*np.ones(size-1),2*alpha+V,-alpha*np.ones(size-1)],
            offsets=[-1,0,1],format="csr")
    try:energies,vecs=eigsh(H,k=count,which="SA",tol=1e-8)
    except Exception as exc:raise LabError("Schrödinger 稀疏本征值计算失败") from exc
    perm=np.argsort(energies);energies=energies[perm];vecs=vecs[:,perm]
    for j in range(count):
        vecs[:,j]/=max(float(np.sqrt(np.sum(vecs[:,j]**2)*dx)),1e-15)
    energy = energies[n-1]
    psi=vecs[:,n-1]
    probability=psi**2
    plt=_plt();fig,axes=plt.subplots(2,1,figsize=(10,7),dpi=105)
    try:
        axes[0].plot(x,V,label="V(x)",c="#777777",lw=1.2)
        for j in range(min(count,8)):
            axes[0].axhline(energies[j],lw=.9,label=f"E{j+1}={energies[j]:.3g}")
        axes[0].set_ylabel("energy")
        axes[0].grid(alpha=.2);axes[0].legend(fontsize=8,ncol=2)
        axes[1].plot(x,psi,label=f"psi n={n}",lw=1.2)
        axes[1].plot(x,probability,label="probability density |psi|^2",lw=1.2)
        axes[1].set_xlabel("x");axes[1].grid(alpha=.2);axes[1].legend()
        fig.suptitle("1D stationary Schrodinger | numerical eigenstates")
        fig.tight_layout();path=_out(output_dir,"schrodinger");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"真实计算 -ℏ²/(2m) ψ''+V(x)ψ=Eψ；V(x)={potential}，"
                 f"x∈[{xmin:g},{xmax:g}]，m={mass:g}，ℏ={hbar:g}，{size} 个网格内点，"
                 f"边界 ψ=0，n={n}，E_n≈{energy:.7g}，归一化积分≈{np.sum(probability)*dx:.6g}。"
                 "这是有限盒子 Dirichlet 数值谱，连续谱同样会被盒子离散化。")


def diffraction_fft(output_dir:Path,opt:dict):
    plt=_plt()
    n=int_opt(opt.get("size",4096),"size",512,8192)
    span=float_opt(opt.get("span",8),"span",.1,1e4)
    wave=float_opt(opt.get("wavelength",.5),"wavelength",.0001,1000)
    distance=float_opt(opt["distance"],"distance",.01,1000) if "distance" in opt else None
    angle_limit=float_opt(opt.get("angle",30),"angle",.1,89)
    x=np.linspace(-span,span,n,endpoint=False)
    dx=x[1]-x[0]
    aperture=opt.get("aperture")
    if aperture and "slits" in opt:
        raise LabError("--aperture 和 --slits 二选一，不能叠加而假装独立")
    if aperture:
        transmission=compute(aperture,("x",),x,shape=x.shape).astype(np.complex128)
        spec=f"T(x)={aperture}"
    else:
        slits=opt.get("slits","-2,1,1,0;2,1,1,0")
        items=[numbers(z,"slit center,width,amplitude,phase_deg",low=4,high=4)
               for z in slits.split(";")]
        if not 1<=len(items)<=20:raise LabError("需提供 1..20 条狭缝")
        transmission=np.zeros(n,dtype=np.complex128)
        for center,width,amp,phase in items:
            if width<=0 or width>span*2 or abs(center)>span:
                raise LabError("缝宽必须为正，狭缝中心要在采样范围内")
            transmission[np.abs(x-center)<=width/2]+=amp*np.exp(1j*np.deg2rad(phase))
        spec=f"slits={items}"
    if not np.isfinite(transmission).all() or np.max(np.abs(transmission))>1e5:
        raise LabError("透过率包含无效值")
    if np.max(abs(transmission))<1e-12:raise LabError("透过光强为零")
    field=np.fft.fftshift(np.fft.fft(np.fft.ifftshift(transmission)))*dx
    spatial=np.fft.fftshift(np.fft.fftfreq(n,dx))
    # Fraunhofer far-field: spatial frequency q = sin(theta)/lambda.
    sine=spatial*wave
    visible=np.abs(sine)<np.sin(np.deg2rad(angle_limit))
    theta=np.rad2deg(np.arcsin(np.clip(sine[visible],-1,1)))
    intensity=np.abs(field[visible])**2
    intensity/=max(float(np.max(intensity)),1e-14)
    if len(theta)<12:raise LabError("可见远场点太少：减小波长、增加采样跨度或调整观察角")
    fig,axs=plt.subplots(2,1,figsize=(10,7),dpi=105)
    try:
        axs[0].plot(x,np.abs(transmission),label="|T(x)|")
        axs[0].plot(x,np.angle(transmission)/math.pi,label="phase / pi",alpha=.65)
        axs[0].set_xlim(-span,span);axs[0].set_xlabel("aperture position")
        axs[0].legend();axs[0].grid(alpha=.2)
        observed=np.tan(np.deg2rad(theta))*distance if distance is not None else theta
        axs[1].plot(observed,intensity,lw=1.2)
        axs[1].set_xlabel("screen coordinate (same units as distance)" if distance is not None else "theta (degrees)")
        axs[1].set_ylabel("normalized |FFT[T]|^2")
        axs[1].grid(alpha=.2)
        fig.suptitle("Fraunhofer far-field | user-defined aperture")
        fig.tight_layout();path=_out(output_dir,"fraunhofer");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"真实 1D Fraunhofer 衍射 FFT：{spec}，λ={wave:g}，"
                 f"屏距 {distance if distance is not None else '未给定'}（可选；提供时横轴为屏幕位置），采样点 {n}，"
                 f"孔径跨度±{span:g}。强度由 |∫T(x)e^(-i2πqx)dx|² 近似给出；"
                 "单维标量远场近似，不包含近场传播与偏振。")


def ray_transfer(output_dir:Path,opt:dict):
    plt=_plt()
    raw=opt.get("elements")
    if raw is None:
        f=float_opt(opt.get("focal",100),"focal",-1e6,1e6)
        do=float_opt(opt.get("object",180),"object",.001,1e6)
        if abs(f)<1e-8:raise LabError("焦距不能为零")
        di=(1/f-1/do)
        image_distance=1/di if abs(di)>1e-10 else math.inf
        raw=f"space:{do};lens:{f};space:{max(0.,image_distance) if math.isfinite(image_distance) else do}"
    elif {"focal","object"}&opt.keys():
        raise LabError("--elements 自定义链路不能同时输入 --focal/--object")
    parts=[]
    for token in raw.split(";"):
        if ":" not in token:raise LabError("光学链应为 space:长度;lens:焦距;space:长度")
        kind,value=token.split(":",1)
        kind=kind.strip().lower()
        if kind not in {"space","lens"}:raise LabError("仅支持 space/lens（近轴 ABCD 传输）")
        x=float_opt(value,kind,-1e6,1e6)
        if kind=="space" and x<0:raise LabError("传输距离应非负")
        if kind=="lens" and abs(x)<1e-8:raise LabError("透镜焦距不能为零")
        parts.append((kind,x))
    if not 1<=len(parts)<=20:raise LabError("光学元件数需在 1..20")
    vectors=[numbers(raw,"rays initial height,angle(rad)",low=2,high=2) for raw in
             opt.get("rays",".15,0;-.15,0;0,.03").split(";")]
    if not 1<=len(vectors)<=16:raise LabError("rays 需 1..16 条光线")
    tracks=[[(0.,r[0])] for r in vectors]
    total=np.eye(2)
    position=0.
    states=np.array(vectors,float).T
    lens_positions=[]
    for kind,value in parts:
        if kind=="space":
            A=np.array([[1.,value],[0.,1.]])
            position+=value
        else:
            A=np.array([[1.,0.],[-1./value,1.]])
            lens_positions.append(position)
        states=A@states
        total=A@total
        for j in range(len(vectors)):tracks[j].append((position,float(states[0,j])))
        if not np.isfinite(states).all() or np.max(np.abs(states))>1e8:
            raise LabError("光线发散或不满足近轴条件")
    fig,ax=plt.subplots(figsize=(10,6),dpi=105)
    try:
        for tr in tracks:
            a=np.asarray(tr);ax.plot(a[:,0],a[:,1],lw=1.3)
        for z in lens_positions:ax.axvline(z,color="#777777",lw=2,alpha=.5)
        ax.axhline(0,c="#333333",lw=.7)
        ax.set_xlabel("optical axis distance");ax.set_ylabel("ray height")
        ax.set_title("ABCD thin-lens paraxial ray transfer")
        ax.grid(alpha=.2);fig.tight_layout()
        path=_out(output_dir,"ray-transfer");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"由每段自由传播 P(d)=[[1,d],[0,1]] 和薄透镜 L(f)=[[1,0],[-1/f,1]]"
                 f"逐段真实相乘；chain={parts}，rays={vectors}，"
                 f"总 ABCD={np.round(total,6).tolist()}，det≈{np.linalg.det(total):.6g}。"
                 "近轴模型仅适用于小角度、薄透镜，无球差/衍射/色散。")
