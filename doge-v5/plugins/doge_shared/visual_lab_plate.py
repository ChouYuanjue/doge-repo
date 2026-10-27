"""Physical Kirchhoff-Love plate vibration eigenmodes via scikit-fem Morley FEM.

Thin homogeneous isotropic plate, bounded finite element mesh, no pre-painted
'sand patterns'.  scikit-fem reference: examples/ex02.py (BSD-3-Clause).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .science_expression import float_opt, int_opt
from .visual_lab import LabError, _out


def plate_modes(output_dir: Path, opt: dict):
    try:
        from skfem import MeshTri, Basis, ElementTriMorley, BilinearForm, asm
        from skfem.helpers import dd, ddot, trace
        from scipy.sparse.linalg import eigsh
    except ImportError as exc:
        raise LabError("缺少 scikit-fem 有限元后端；请安装项目要求的 scikit-fem 12.0.2") from exc

    shape = opt.get("shape", "square").lower()
    bc = opt.get("bc", "free").lower()
    if shape not in {"square", "circle", "lshape"}:
        raise LabError("shape 支持 square / circle / lshape")
    if bc not in {"clamped", "simply", "free"}:
        raise LabError("bc 支持 clamped（固支）、simply（简支）、free（自由）")
    mode = int_opt(opt.get("mode", 5), "mode", 1, 14)
    # For legacy /lab chladni 5 3, mix two modes. Distinct frequencies imply a
    # snapshot superposition, NEVER a single eigenmode.
    mix = int_opt(opt["mix"], "mix", 1, 14) if "mix" in opt else None
    mix_amp = float_opt(opt.get("amplitude", .5), "amplitude", -10, 10)
    refinement = int_opt(opt.get("refine", 2), "refine", 1, 3)
    aspect = float_opt(opt.get("aspect", 1), "aspect", .3, 3)
    E = float_opt(opt.get("young", "2e11"), "young", 1e3, 1e13)
    density = float_opt(opt.get("density", 7850), "density", 10, 50000)
    thickness = float_opt(opt.get("thickness", ".001"), "thickness", 1e-5, .5)
    side = float_opt(opt.get("length", 1), "length", .01, 50)
    poisson = float_opt(opt.get("poisson", .3), "poisson", 0, .49)

    if shape == "square":
        mesh = MeshTri.init_sqsymmetric().refined(refinement)
    elif shape == "circle":
        mesh = MeshTri.init_circle(nrefs=refinement + 1)
    else:
        mesh = MeshTri.init_lshaped().refined(refinement)
    # Coordinate normalize the longest side to 1; aspect sets physical y/x.
    pos = mesh.p.copy()
    w = np.ptp(pos[0]); h = np.ptp(pos[1])
    pos[0] = (pos[0] - pos[0].min()) / w
    pos[1] = (pos[1] - pos[1].min()) / h * aspect
    mesh = MeshTri(pos, mesh.t.copy())
    basis = Basis(mesh, ElementTriMorley())

    @BilinearForm
    def bending(u, v, _):
        # Kirchhoff-Love energy with Poisson coupling:
        # D * [(1-nu) Hess(u):Hess(v) + nu Delta(u) Delta(v)]
        H = dd(u)
        V = dd(v)
        return (1 - poisson) * ddot(H, V) + poisson * trace(H) * trace(V)

    @BilinearForm
    def inertia(u, v, _):
        return u * v

    K = asm(bending, basis).tocsr()
    M = asm(inertia, basis).tocsr()

    if bc == "clamped":
        D = basis.get_dofs().all()
    elif bc == "simply":
        D = basis.get_dofs().all("u")
    else:
        D = np.empty(0, dtype=int)
    I = np.setdiff1d(np.arange(basis.N), D)
    if len(I) < max(mode, mix or 0) + 6:
        raise LabError("网格自由度不足，请增加 --refine")
    Kc = K[I][:, I]
    Mc = M[I][:, I]
    count = max(mode, mix or 0)
    # Free plate includes three rigid-body modes (translation + tilt); discard
    # them before selecting the vibrational mode. In a general L-domain this
    # assumption is preserved since the fourth-order plate energy vanishes
    # on every affine displacement.
    k = min(max(count + (5 if bc == "free" else 2), 7), len(I) - 2)
    try:
        vals, vecs = eigsh(Kc, M=Mc, k=k, sigma=-.001, tol=2e-6, maxiter=9000)
    except Exception as exc:
        raise LabError("稀疏有限元特征值求解失败，请降低振型编号或调整网格") from exc

    order = np.argsort(vals)
    vals = vals[order]
    vecs = vecs[:, order]
    # Eigensolvers can report very small negative eigenvalues for free rigid
    # modes; their numerical magnitude is orders below actual bending modes.
    retained = np.flatnonzero(vals > 1e-3)
    if len(retained) < count:
        raise LabError("提取到的有效振动模态不足；请增加网格细度")
    spectrum = vals[retained]
    modes = vecs[:, retained]

    def reconstruct(which):
        full = np.zeros(basis.N, float)
        full[I] = modes[:, which - 1].real
        vtx = full[basis.nodal_dofs[0]]
        scale = np.max(np.abs(vtx))
        if scale < 1e-14:
            raise LabError("FEM 结果退化为零振型")
        return vtx / scale

    displacement = reconstruct(mode)
    if mix is not None:
        displacement += mix_amp * reconstruct(mix)
    coordinates = mesh.p
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.tri import Triangulation

    tri = Triangulation(coordinates[0], coordinates[1], triangles=mesh.t.T)
    fig, ax = plt.subplots(figsize=(8.3, 7.2), dpi=110)
    try:
        scale = max(float(np.max(np.abs(displacement))), 1e-10)
        plot = ax.tripcolor(tri, displacement, shading="gouraud", cmap="coolwarm",
                            vmin=-scale, vmax=scale)
        ax.tricontour(tri, displacement, levels=[0.], colors=["#202427"], linewidths=1.8)
        fig.colorbar(plot, ax=ax, label="relative transverse displacement")
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x / L")
        ax.set_ylabel("y / L")
        ax.set_title(f"Kirchhoff-Love FEM | {shape} | {bc} | mode {mode}" +
                     (f" + {mix}" if mix else ""))
        fig.tight_layout()
        path = _out(output_dir, "kirchhoff-plate")
        fig.savefig(path)
    finally:
        plt.close(fig)

    Dplate = E * thickness**3 / (12 * (1 - poisson**2))
    frequency = math.sqrt(Dplate / (density * thickness)) / (2*math.pi*side*side)
    freq1 = frequency * math.sqrt(float(spectrum[mode - 1]))
    label = (f"mode={mode}，离散 λ={spectrum[mode - 1]:.5g}，理想共振频率≈{freq1:.4g} Hz"
             if mix is None else
             f"mode {mode}+{mix} 振型叠加（幅比 {mix_amp:g}，不同频率的瞬时线性叠加）")
    return path, (
        f"Kirchhoff–Love 各向同性薄板有限元（scikit-fem Morley 单元、稀疏广义特征值问题）"
        f"；形状={shape}，约束={bc}，节点={mesh.p.shape[1]}，DOF={basis.N}，"
        f"{label}；L={side:g} m，aspect={aspect:g}，E={E:g} Pa，ρ={density:g} kg/m³，"
        f"h={thickness:g} m，ν={poisson:g}。"
        "黑色为数值位移零线；简化均匀薄板模型，实际沙粒分布/阻尼/驱动频率尚未模拟。"
    )
