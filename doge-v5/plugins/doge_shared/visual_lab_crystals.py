"""Crystallographic reciprocal-space calculations from arbitrary user lattice and basis.

A deliberately labelled ideal point-scatterer/kinematical model. Real material
powder diffraction is available separately at /mat crystal powder (CIF).
"""
from __future__ import annotations

import itertools
import math
from pathlib import Path

import numpy as np

from .science_expression import float_opt, int_opt, numbers
from .visual_lab import LabError, _out


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _cell(opt):
    if "vectors" in opt:
        if "a" in opt:raise LabError("--vectors 与立方晶格常数 --a 不能同时指定")
        a=np.asarray([numbers(row,"lattice vector",low=3,high=3) for row in opt["vectors"].split(";")],float)
        if a.shape!=(3,3):
            raise LabError("vectors 必须是三组 3D 晶格矢量")
    else:
        a0=float_opt(opt.get("a",4.05),"a",.0001,2000)
        a=np.eye(3)*a0
    determinant=float(np.linalg.det(a))
    if abs(determinant)<1e-10 or not np.isfinite(determinant):
        raise LabError("晶格矢量线性相关或体积接近 0")
    return a


def _basis(opt,weighted=False):
    kind=opt.get("preset","fcc").lower()
    presets={
        "sc":[(0.,0.,0.)],
        "bcc":[(0.,0.,0.),(.5,.5,.5)],
        "fcc":[(0.,0.,0.),(0.,.5,.5),(.5,0.,.5),(.5,.5,0.)],
    }
    presets["diamond"]=presets["fcc"]+[
        tuple((z+.25)%1 for z in p) for p in presets["fcc"]]
    if "basis" in opt:
        if "preset" in opt:raise LabError("自定义 --basis 时不要同时使用预设 --preset")
        raw=opt["basis"].split(";")
        if not 1<=len(raw)<=64:raise LabError("basis 只允许 1..64 个分数坐标")
        atoms=[]
        for item in raw:
            values=numbers(item,"basis site x,y,z[,weight]",low=3,high=4)
            x,y,z=values[:3]
            if not all(-10<=c<=10 for c in (x,y,z)):
                raise LabError("分数坐标过大")
            weight=values[3] if len(values)==4 else 1.
            if not .001<=weight<=100: raise LabError("散射权重必须在 0.001..100")
            atoms.append((x%1,y%1,z%1,weight))
        return np.asarray(atoms,float)
    if kind not in presets:raise LabError("preset=sc|bcc|fcc|diamond；自定义用 --basis")
    return np.array([(*p,1.) for p in presets[kind]],float)


def lattice(output_dir:Path,opt:dict):
    plt=_plt()
    A=_cell(opt);atoms=_basis(opt)
    cells=int_opt(opt.get("cells",2),"cells",1,4)
    points=[]
    for i,j,k in itertools.product(range(cells+1),repeat=3):
        for x,y,z,weight in atoms:
            site=np.array([i+x,j+y,k+z])
            if np.all(site<=cells+1e-8):
                points.append((site@A,weight))
    if not points:raise LabError("晶胞中没有可显示的原子")
    fig=plt.figure(figsize=(8,7),dpi=105)
    try:
        ax=fig.add_subplot(projection="3d")
        xy=np.array([p[0] for p in points])
        marker_sizes=np.clip([p[1]*28 for p in points],6,130)
        ax.scatter(xy[:,0],xy[:,1],xy[:,2],s=marker_sizes,depthshade=True)
        # Unit cell wireframes using real, user-specified Bravais vectors.
        for i,j,k in itertools.product(range(cells+1),repeat=3):
            pos=np.array([i,j,k],float)
            for axis in range(3):
                if pos[axis]>=cells:continue
                a=pos@A
                b=(pos+np.eye(3)[axis])@A
                ax.plot([a[0],b[0]],[a[1],b[1]],[a[2],b[2]],color="gray",lw=.6)
        ax.set_xlabel("x (A)");ax.set_ylabel("y (A)");ax.set_zlabel("z (A)")
        ax.set_title(f"Crystal real-space basis={len(atoms)}, cells={cells}")
        fig.tight_layout();path=_out(output_dir,"lattice-general");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"任意三维 Bravais 晶格矢量 {A.tolist()}，"
        f"分数基底 {atoms.tolist()}，展示 {cells}³ 晶胞（截断边界），"
        f"原子位点 {len(points)} 个；模型内按分数坐标构造，不声称为实际 CIF。")


def xrd(output_dir:Path,opt:dict):
    plt=_plt()
    A=_cell(opt);atoms=_basis(opt,weighted=True)
    wave=float_opt(opt.get("wavelength",1.5406),"wavelength",.001,100)
    maxh=int_opt(opt.get("maxh",7),"maxh",1,12)
    maxangle=float_opt(opt.get("maxangle",120),"maxangle",1,179.9)
    width=float_opt(opt.get("width",.11),"width",.01,3)
    recip=np.linalg.inv(A).T
    coordinates=atoms[:,:3]
    factors=atoms[:,3]
    peaks={}
    for h,k,l in itertools.product(range(-maxh,maxh+1),repeat=3):
        if h==k==l==0:continue
        H=np.array([h,k,l],float)
        g=np.linalg.norm(H@recip)
        s=wave*g/2
        if not 0<s<1:continue
        theta2=2*math.degrees(math.asin(s))
        if theta2>maxangle:continue
        F=np.sum(factors*np.exp(2j*np.pi*(coordinates@H)))
        intensity=abs(F)**2
        if intensity<1e-8:continue
        key=round(theta2,4)
        value=peaks.setdefault(key,[0,(h,k,l)])
        value[0]+=intensity
    if not peaks:raise LabError("无衍射峰：调整晶格常数、波长或角度范围")
    ang=np.array(sorted(peaks),float)
    amps=np.array([peaks[z][0] for z in ang],float)
    y=np.zeros(1600)
    theta=np.linspace(0,maxangle,len(y))
    for z,h in zip(ang,amps):
        # Gaussian instrument broadening, simplified; no polarization/absorption/form factors.
        y+=h*np.exp(-.5*((theta-z)/width)**2)
    y/=max(y.max(),1e-20)
    fig,ax=plt.subplots(figsize=(11,6.5),dpi=105)
    try:
        ax.plot(theta,y,lw=1.2)
        ax.set_xlim(0,maxangle);ax.set_ylim(0,1.1)
        ax.set_xlabel("2-theta (degrees)");ax.set_ylabel("normalized relative intensity")
        ax.set_title(f"Ideal kinematic XRD | lambda={wave:g} A, basis={len(atoms)} sites")
        ax.grid(alpha=.2);fig.tight_layout()
        path=_out(output_dir,"xrd-general");fig.savefig(path)
    finally:plt.close(fig)
    dominant=np.argsort(amps)[::-1][:5]
    top=", ".join(f"{ang[i]:.2f}deg ({amps[i]/max(amps):.2f})" for i in dominant)
    return path,(f"理想运动学晶体衍射：由三维晶格矢量计算倒格子、Bragg 角度及结构因子"
                 f" F(hkl)=Σfⱼ exp(2πi h·rⱼ)，共 {len(ang)} 组峰；top {top}。"
                 f"散射权重视作常数，无原子 form factor / Lorentz-polarization / 位移参数。"
                 f"真实 CIF 粉末衍射请用 /mat crystal powder。")
