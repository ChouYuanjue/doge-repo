"""Bounded 2D finite-element PDE operations using the scikit-fem project.

Scalar Poisson / diffusion / Dirichlet Laplace eigenmodes on a configurable mesh.
The governing equation and boundary conditions are always identified in output.
"""
from __future__ import annotations

from pathlib import Path
import math

import numpy as np
from .science_expression import compute, float_opt, int_opt
from .visual_lab import LabError, _out


def mesh_from_options(opt):
    from skfem import MeshTri
    shape = opt.get("shape", "square").lower()
    if shape not in {"square","circle","lshape"}:
        raise LabError("shape 支持 square / circle / lshape")
    refs = int_opt(opt.get("refine", 3), "refine", 1, 5)
    if (shape=="circle" and refs>3) or (shape in {"square","lshape"} and refs>4):
        raise LabError("PDE 当前几何/细化程度会超过内存预算：circle refine<=3，square/lshape refine<=4")
    if shape == "square": mesh = MeshTri.init_sqsymmetric().refined(refs)
    elif shape == "circle": mesh = MeshTri.init_circle(nrefs=refs+1)
    else: mesh = MeshTri.init_lshaped().refined(refs)
    aspect = float_opt(opt.get("aspect",1), "aspect", .25, 4)
    p = mesh.p.copy()
    p[0] = (p[0] - p[0].min()) / np.ptp(p[0])
    p[1] = (p[1] - p[1].min()) / np.ptp(p[1]) * aspect
    return MeshTri(p, mesh.t.copy()), shape


def pde_general(output_dir:Path, kind:str, opt:dict):
    from skfem import Basis, ElementTriP1, BilinearForm, LinearForm, asm
    from skfem.helpers import dot, grad
    from scipy.sparse.linalg import spsolve, eigsh, factorized

    kind = kind.lower()
    if kind not in {"poisson","heat","eigen"}:
        raise LabError("PDE 支持 poisson / heat / eigen")
    shared={"shape","refine","aspect"}
    typed={
        "poisson":shared|{"diffusion","f"},
        "heat":shared|{"diffusion","init","time","steps"},
        "eigen":shared|{"mode"},
    }
    unused=set(opt)-typed[kind]
    if unused:
        raise LabError(f"PDE {kind} 不能使用这些不会参与计算的参数："+", ".join("--"+x for x in sorted(unused)))
    mesh, shape = mesh_from_options(opt)
    basis = Basis(mesh, ElementTriP1())
    diffusivity = float_opt(opt.get("diffusion", 1), "diffusion", 1e-5, 1e5)
    if mesh.p.shape[1] > 2500:
        raise LabError("PDE 网格过大")
    @BilinearForm
    def laplace(u,v,w): return dot(grad(u),grad(v))
    @BilinearForm
    def mass(u,v,w):return u*v
    K = asm(laplace,basis).tocsr()
    M = asm(mass,basis).tocsr()
    D = basis.get_dofs().all()
    I = np.setdiff1d(np.arange(basis.N),D)
    if len(I)<15:raise LabError("内点不足")
    scalar = ""
    extra = {}
    if kind=="poisson":
        source=opt.get("f","sin(pi*x)*sin(pi*y)")
        @LinearForm
        def forcing(v,w):
            coords = w.x
            values = compute(source, ("x","y"), coords[0],coords[1], shape=coords[0].shape)
            if np.iscomplexobj(values) and np.any(abs(values.imag)>1e-8):
                raise LabError("泊松方程的源函数必须为实数")
            if not np.isfinite(values).all():raise LabError("源函数存在非有限计算值")
            return np.asarray(values.real,float)*v
        b=asm(forcing,basis)
        values=np.zeros(basis.N)
        values[I]=spsolve((diffusivity*K)[I][:,I],b[I])
        scalar=f"-{diffusivity:g} Δu={source}, u|∂Ω=0"
        extra["source"]=source
    elif kind=="heat":
        initial=opt.get("init","exp(-40*((x-0.5)^2+(y-0.5)^2))")
        time=float_opt(opt.get("time",.1),"time",1e-4,10)
        steps=int_opt(opt.get("steps",40),"steps",1,240)
        coords=basis.doflocs
        data=compute(initial,("x","y"),coords[0],coords[1],shape=(basis.N,))
        if np.iscomplexobj(data) and np.any(abs(data.imag)>1e-8):raise LabError("初值必须为实数")
        if not np.isfinite(data).all(): raise LabError("初值存在非有限计算值")
        values=np.array(data.real,dtype=float,copy=True)
        values[D]=0
        timestep=time/steps
        A=(M[I][:,I]/timestep+diffusivity*K[I][:,I]).tocsc()
        factor=factorized(A)
        for _ in range(steps):
            rhs=M[I][:,I]@values[I]/timestep
            values[I]=factor(rhs)
        scalar=(f"∂t u={diffusivity:g} Δu, u|∂Ω=0; "
                f"u(0)={initial}; t={time:g}, {steps} backward-Euler steps")
        extra["time"]=time
    else:
        mode=int_opt(opt.get("mode",1),"mode",1,12)
        k=min(mode+3,len(I)-2)
        lam,vec=eigsh(K[I][:,I],M=M[I][:,I],k=k,sigma=-.001)
        order=np.argsort(lam)
        lam=lam[order];vec=vec[:,order]
        if lam[mode-1]<=0:raise LabError("Eigen PDE 中出现异常非正特征值")
        values=np.zeros(basis.N,float)
        values[I]=vec[:,mode-1]
        scalar=f"-Δφ=λφ, φ|∂Ω=0; mode={mode}; λ≈{lam[mode-1]:.6g}"
        extra["eigenvalue"]=lam[mode-1]

    if not np.isfinite(values).all():raise LabError("FEM 求解结果含 NaN/Inf")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.tri import Triangulation
    triangulation=Triangulation(mesh.p[0],mesh.p[1],mesh.t.T)
    fig,ax=plt.subplots(figsize=(8,7),dpi=105)
    try:
        col=ax.tripcolor(triangulation,values,cmap="viridis",shading="gouraud")
        fig.colorbar(col,ax=ax,label="FEM nodal solution")
        if kind=="eigen":
            ax.tricontour(triangulation,values,levels=[0],colors=["white"],linewidths=.8)
        ax.set_aspect("equal",adjustable="box");ax.set_xlabel("x");ax.set_ylabel("y")
        ax.set_title(f"scikit-fem | {kind} | {shape} | {basis.N} DOFs")
        fig.tight_layout()
        path=_out(output_dir,"fem-pde")
        fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"二维线性三角有限元实际求解：{scalar}；区域={shape}，节点={basis.N}，"
        f"refine={opt.get('refine',3)}，边界为齐次 Dirichlet；"
        f"网格解范围=[{values.min():.5g},{values.max():.5g}]。"
        "数值误差和网格收敛性需通过细化网格验证，结果不代表实测场。")
