"""General analytic scientific plots for /lab; actual formulas, not enumerated pictures."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from .science_expression import compute, compile_formula, float_opt, int_opt, numbers
from .visual_lab import LabError, _heat_rgb, _out, _title
from .visual_lab_extra import _hsv_rgb


def _view(opt: dict, *, default_span=3.2):
    n = int_opt(opt.get("size", 560), "size", 160, 760)
    cx, cy = numbers(opt.get("center", "0,0"), "center", low=2, high=2)
    zoom = float_opt(opt.get("zoom", "1"), "zoom", 1e-4, 1e6)
    span = float_opt(opt.get("span", default_span), "span", 1e-5, 1e5) / zoom
    if span < 1e-10:
        raise LabError("可视范围过小")
    xs = np.linspace(cx - span, cx + span, n)
    ys = np.linspace(cy + span, cy - span, n)
    return n, xs[None, :] + 1j * ys[:, None]


def _save_rgb(output_dir: Path, rgb, prefix: str, label: str, caption: str):
    img = Image.fromarray(np.asarray(rgb, dtype=np.uint8), "RGB")
    _title(img, label[:60])
    path = _out(output_dir, prefix)
    img.save(path)
    return path, caption


def complex_domain(output_dir: Path, expression: str, opt: dict):
    n, z = _view(opt)
    w = compute(expression, ("z",), z, shape=z.shape)
    w = np.asarray(w, dtype=np.complex128)
    with np.errstate(all="ignore"):
        mag = np.abs(w)
        hue = np.mod(np.angle(w)/(2*np.pi), 1.)
        logm = np.log2(np.maximum(mag, 1e-40))
        frac = logm - np.floor(logm)
        value = np.clip(.55 + .4*(1 - 2*np.abs(frac-.5)), .12, 1.)
    rgb = _hsv_rgb(np.nan_to_num(hue), np.full(z.shape, .85), np.nan_to_num(value))
    rgb[~np.isfinite(mag)] = (8, 8, 9)
    return _save_rgb(output_dir, rgb, "complex", "Domain coloring: f(z)=" + expression,
        f"f(z)={expression}；size={n}。色相=arg f(z)，同心亮度带=log₂|f(z)|；黑色表示非有限计算值。")


def escape_fractal(output_dir: Path, kind: str, expression: str, opt: dict, *,
                   legacy_c: complex | None = None):
    n, coords = _view(opt, default_span=1.7 if kind == "julia" else 1.9)
    iterations = int_opt(opt.get("iter", 110), "iter", 1, 320)
    bailout = float_opt(opt.get("escape", 8), "escape", 1.01, 1e6)
    if kind == "julia":
        if legacy_c is not None: c0 = legacy_c
        else: c0 = complex(opt.get("c", "-0.8+0.156j").replace("i", "j"))
        if not np.isfinite(c0.real) or not np.isfinite(c0.imag) or abs(c0) > 1e6:
            raise LabError("c 需为有限复数，例如 -0.8+0.156i")
        c = c0
        z = coords.copy()
    else:
        c = coords
        initial = complex(opt.get("z0", "0").replace("i", "j"))
        if not np.isfinite(initial.real) or not np.isfinite(initial.imag) or abs(initial) > 1e6:
            raise LabError("z0 必须为有限复数")
        z = np.full(coords.shape, initial, dtype=np.complex128)
    fn = compile_formula(expression, ("z", "c"))
    escaped = np.zeros(coords.shape, np.uint16)
    active = np.ones(coords.shape, dtype=bool)
    with np.errstate(all="ignore"):
        for it in range(1, iterations + 1):
            result = np.asarray(fn(z, c), dtype=np.complex128)
            if result.ndim == 0:
                result = np.broadcast_to(result, z.shape)
            else:
                result = np.broadcast_to(result, z.shape)
            z = np.where(active, result, 0j)
            failed = active & (~np.isfinite(z) | (np.abs(z) > bailout))
            escaped[failed] = it
            active[failed] = False
            z[~active] = 0
            if not active.any():
                break
    v = np.log1p(escaped.astype(np.float32)) / math.log1p(iterations)
    rgb = _heat_rgb(v)
    rgb[escaped == 0] = (6, 7, 14)
    label = ("Julia" if kind == "julia" else "parameter plane") + ": z -> " + expression
    return _save_rgb(output_dir, rgb, "escape", label,
        f"迭代 z[n+1]={expression}；{'c='+str(c) if kind=='julia' else 'c 为平面坐标'}；最多 {iterations} 次、逃逸阈值 {bailout:g}。黑色仅表示在给定计算预算内未逃逸，不能证明属于集合。")


def newton_general(output_dir: Path, expression: str, opt: dict):
    import sympy as sp
    n, z = _view(opt, default_span=2.)
    iterations = int_opt(opt.get("iter", 45), "iter", 1, 120)
    tol = float_opt(opt.get("tol", "1e-6"), "tol", 1e-12, 1e-2)
    symbolic = __import__(__package__ + ".science_expression", fromlist=["parse_formula"]).parse_formula(expression, ("z",))
    derivative = sp.diff(symbolic, sp.Symbol("z"))
    if derivative == 0:
        raise LabError("f'(z) 恒为零，没有 Newton 更新")
    f = sp.lambdify(sp.Symbol("z"), symbolic, "numpy", docstring_limit=0)
    df = sp.lambdify(sp.Symbol("z"), derivative, "numpy", docstring_limit=0)
    z = z.copy()
    iters = np.zeros(z.shape, np.uint16)
    good = np.zeros(z.shape, bool)
    active = np.ones(z.shape, bool)
    with np.errstate(all="ignore"):
        for k in range(1, iterations + 1):
            y = np.broadcast_to(np.asarray(f(z), dtype=np.complex128), z.shape)
            dy = np.broadcast_to(np.asarray(df(z), dtype=np.complex128), z.shape)
            done = active & np.isfinite(y) & (np.abs(y) < tol)
            good[done], iters[done], active[done] = True, k, False
            if not active.any(): break
            valid = active & np.isfinite(y) & np.isfinite(dy) & (np.abs(dy) > 1e-13)
            next_z = np.where(valid, z - np.where(valid, y / np.where(valid, dy, 1), 0), z)
            valid &= np.isfinite(next_z) & (np.abs(next_z) < 1e7)
            active &= valid
            z = np.where(active, next_z, z)
        remain = active & np.isfinite(z)
        if remain.any():
            yy = np.broadcast_to(np.asarray(f(z), dtype=np.complex128), z.shape)
            good[remain] = np.abs(yy[remain]) < tol
            iters[remain & good] = iterations
        h = np.mod(.18 + .23*np.arctan2(z.imag, z.real)/np.pi + .16*np.log1p(np.abs(z)), 1)
        # Index stable attraction basins by their roots, not by a fixed known polynomial.
        rreal = np.round(z.real, 2)
        rimag = np.round(z.imag, 2)
        h = np.mod(.6180339*rreal + .41421356*rimag, 1)
        bright = np.clip(.95 - .55*iters/max(iterations, 1), .28, .95)
    rgb = _hsv_rgb(np.nan_to_num(h), np.full(z.shape, .78), bright)
    rgb[~good] = (9, 11, 17)
    return _save_rgb(output_dir, rgb, "newton", "Newton basins: " + expression,
        f"数值求解 f(z)={expression}=0；由 SymPy 求导并执行 Newton 迭代；收敛 {int(good.sum())}/{n*n} 像素，阈值 {tol:g}。颜色依近似收敛根区分，黑色为未收敛。")


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def function_plot(output_dir: Path, expressions: str, opt: dict, kind="plot"):
    plt = _plt()
    xmin, xmax = numbers(opt.get("range", "-10,10"), "range", low=2, high=2)
    if not xmin < xmax or xmax-xmin > 1e6: raise LabError("range 必须从小到大")
    n = int_opt(opt.get("size", 1400), "size", 200, 3000)
    xs = np.linspace(xmin, xmax, n)
    exprs = expressions.split(";")
    if not 1 <= len(exprs) <= 6: raise LabError("一次最多绘制 6 个函数，用 ; 分隔")
    fig, ax = plt.subplots(figsize=(10, 7), dpi=110)
    try:
        for expr in exprs:
            vals = compute(expr, ("x",), xs, shape=xs.shape)
            if np.iscomplexobj(vals) and np.any(np.abs(vals.imag) > 1e-8):
                raise LabError("实函数图不能包含非实值；复函数请用 /lab complex")
            y = np.array(vals.real, dtype=float, copy=True)
            y[~np.isfinite(y)] = np.nan
            ax.plot(xs, y, lw=1.6, label=expr[:60])
        if "ylim" in opt:
            low, high = numbers(opt["ylim"], "ylim", low=2, high=2)
            if low >= high: raise LabError("ylim 上下限顺序错误")
            ax.set_ylim(low, high)
        ax.set_xlabel("x"); ax.set_ylabel("f(x)"); ax.axhline(0,color=".6",lw=.7); ax.axvline(0,color=".6",lw=.7)
        ax.grid(alpha=.23); ax.legend(loc="best"); ax.set_title("Functions: " + expressions[:85])
        fig.tight_layout()
        path = _out(output_dir, kind)
        fig.savefig(path)
    finally:
        plt.close(fig)
    return path, f"已按表达式计算 {len(exprs)} 条真实曲线；x ∈ [{xmin:g},{xmax:g}]，采样 {n} 点；非有限值不连线。"


def parametric_plot(output_dir: Path, opt: dict):
    plt = _plt()
    if not {"x", "y"} <= opt.keys(): raise LabError("用法：/lab param --x 'cos(3*t)' --y 'sin(2*t)' [--range '0,6.28']")
    start, stop = numbers(opt.get("range", "0,6.283185307179586"), "range", low=2, high=2)
    if not start < stop: raise LabError("range 必须递增")
    n = int_opt(opt.get("size", 1800), "size", 200, 5000)
    t = np.linspace(start, stop, n)
    values=[]
    for key in ("x", "y", "z"):
        if key in opt:
            val = compute(opt[key], ("t",), t, shape=t.shape)
            if np.iscomplexobj(val) and np.any(np.abs(val.imag)>1e-8): raise LabError("参数曲线坐标必须为实数")
            values.append(val.real.astype(float))
    if not all(np.isfinite(v).any() for v in values): raise LabError("轨迹没有有限数值")
    fig = plt.figure(figsize=(9, 7), dpi=110)
    try:
        if len(values) == 3:
            ax = fig.add_subplot(111, projection="3d")
            ax.plot(*values, lw=1.3)
            ax.set_zlabel("z")
        else:
            ax = fig.add_subplot(111)
            ax.plot(*values, lw=1.4)
            ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.grid(alpha=.3)
        ax.set_title("Parametric curve")
        fig.tight_layout(); path=_out(output_dir,"parametric"); fig.savefig(path)
    finally: plt.close(fig)
    return path, f"用户定义的 {len(values)}D 参数曲线；t ∈ [{start:g},{stop:g}]，{n} 个采样点。"


def linear_general(output_dir: Path, matrix: str, opt: dict):
    plt = _plt()
    rows = []
    for row in matrix.split(";"):
        rows.append(numbers(row, "matrix row", low=1, high=8))
    if not 2 <= len(rows) <= 8 or any(len(r) != len(rows[0]) for r in rows):
        raise LabError("matrix 必须是 2..8 行、等长的数值矩阵；例如 '1,2;3,4'")
    M = np.array(rows, dtype=float)
    if M.shape[1] > 8 or np.max(np.abs(M)) > 1e5: raise LabError("matrix 维度或元素过大")
    m, n = M.shape
    s = np.linalg.svd(M, compute_uv=False)
    rank = np.linalg.matrix_rank(M)
    eig = np.linalg.eigvals(M) if m == n else None
    det = np.linalg.det(M) if eig is not None else None
    vector = None
    if "vector" in opt:
        vector = np.array(numbers(opt["vector"], "vector", low=n, high=n))
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.5), dpi=100)
    try:
        ax, bx = axes
        if (m, n) == (2, 2):
            t = np.linspace(-2.5, 2.5, 130)
            originals = []
            for k in np.linspace(-2.5, 2.5, 11):
                originals.extend([(np.array([np.full_like(t,k),t]), "#4587ac"),
                                  (np.array([t,np.full_like(t,k)]), "#be8268")])
            pts = [M @ p for p, _ in originals]
            span = max(2.5, max(float(np.max(np.abs(q))) for q in pts))
            for q, color in zip(pts,(c for _,c in originals)):
                ax.plot(q[0],q[1],color=color,lw=.85)
            ax.set_xlim(-span*1.03,span*1.03); ax.set_ylim(-span*1.03,span*1.03)
            ax.set_aspect("equal")
            if vector is not None:
                z = M @ vector
                ax.quiver(0,0,z[0],z[1],angles="xy",scale_units="xy",scale=1,color="black",width=.01)
            ax.set_title("Transformed 2D grid")
        else:
            image=ax.imshow(M, cmap="coolwarm",aspect="auto")
            fig.colorbar(image,ax=ax,shrink=.7)
            ax.set_title(f"Matrix ({m}x{n})")
            for i in range(m):
                for j in range(n): ax.text(j,i,f"{M[i,j]:.3g}",ha="center",va="center",fontsize=9)
        if eig is not None:
            bx.scatter(eig.real,eig.imag,color="#15679b",s=75,label="eigenvalues")
            for z in eig: bx.annotate(f"{z:.3g}",(z.real,z.imag),xytext=(5,5),textcoords="offset points")
            bx.axhline(0,color=".5"); bx.axvline(0,color=".5"); bx.set_xlabel("Re");bx.set_ylabel("Im")
            bx.set_title("Eigenvalue spectrum"); bx.legend()
        else:
            bx.bar(np.arange(1,len(s)+1),s)
            bx.set_title("Singular values"); bx.set_xlabel("component")
        bx.grid(alpha=.25)
        fig.suptitle(f"Linear algebra | rank={rank} | singular values: "+", ".join(f"{v:.3g}" for v in s))
        fig.tight_layout()
        path=_out(output_dir,"linear-general");fig.savefig(path)
    finally: plt.close(fig)
    out=f"{m}x{n} 线性映射；rank={rank}，奇异值="+", ".join(f"{v:.6g}" for v in s)
    if eig is not None: out+=f"；det={det:.6g}；eigenvalues="+", ".join(f"{v:.5g}" for v in eig)
    if vector is not None: out+="；M·v="+",".join(f"{v:.6g}" for v in M@vector)
    return path,out


def spectrum_general(output_dir: Path, expression: str, opt: dict):
    plt = _plt()
    f = float_opt(opt.get("frequency", 5), "frequency", .001, 4000.)
    fs = int_opt(opt.get("rate", 1024), "rate", 128, 8192)
    seconds = float_opt(opt.get("seconds", 2), "seconds", .05, 12.)
    n = int(fs * seconds)
    if f >= fs / 2:
        raise LabError("frequency 必须低于采样率的一半（Nyquist），请增大 --rate 或降低 --frequency")
    if n < 64 or n > 32768: raise LabError("FFT 样本点数需在 64..32768")
    t = np.arange(n)/fs
    if expression in {"square", "sawtooth"}:
        from scipy.signal import square, sawtooth
        y = square(2*np.pi*f*t) if expression=="square" else sawtooth(2*np.pi*f*t)
    else:
        y=compute(expression, ("t","f"), t, f, shape=t.shape)
    if np.iscomplexobj(y) and np.any(np.abs(y.imag)>1e-8): raise LabError("信号必须为实数")
    y=np.asarray(y.real,float)
    if not np.isfinite(y).all() or np.max(np.abs(y))>1e7: raise LabError("信号包含无效值")
    win=np.hanning(n)
    amp=np.abs(np.fft.rfft((y-np.mean(y))*win))*2/max(win.sum(),1e-12)
    freq=np.fft.rfftfreq(n, 1/fs)
    fig, axes=plt.subplots(2,1,figsize=(10,7),dpi=110)
    try:
        count=min(n, max(100,int(.5*fs)))
        axes[0].plot(t[:count],y[:count],lw=1); axes[0].set_xlabel("time (s)");axes[0].set_ylabel("signal")
        axes[1].plot(freq,amp,lw=1); axes[1].set_xlim(0,float_opt(opt.get("maxfreq",min(fs/2,max(50,5*f))),"maxfreq",.001,fs/2))
        axes[1].set_xlabel("frequency (Hz)");axes[1].set_ylabel("windowed amplitude")
        for ax in axes: ax.grid(alpha=.25)
        fig.suptitle("Signal + Hann-window FFT: "+expression[:70]);fig.tight_layout()
        path=_out(output_dir,"spectrum-general");fig.savefig(path)
    finally:plt.close(fig)
    peak=int(np.argmax(amp[1:]))+1 if len(amp)>1 else 0
    return path,f"信号 y(t)={expression}；fs={fs}Hz，T={seconds:g}s，N={n}，最大非直流谱峰 {freq[peak]:.3g}Hz；采用 Hann 窗并去均值，频率分辨率 {fs/n:.3g}Hz。"


def orbital_general(output_dir:Path, n:int,l:int,m:int,opt:dict):
    from scipy.special import sph_harm_y, genlaguerre, gammaln
    n=int_opt(n,"n",1,8)
    l=int_opt(l,"l",0,n-1)
    m=int_opt(m,"m",-l,l)
    extent=float_opt(opt.get("extent",max(8,3*n*n)),"extent",.1,240)
    z0=float_opt(opt.get("offset",0),"offset",-240,240)
    plane=opt.get("plane","xy").lower()
    mode=opt.get("mode","real").lower()
    if opt.get("basis","complex") not in {"complex","real"}:raise LabError("basis 只能是 complex 或 real")
    if plane not in {"xy","xz","yz"} or mode not in {"real","imag","density","phase"}: raise LabError("plane=xy|xz|yz，mode=real|imag|density|phase")
    size=int_opt(opt.get("size",560),"size",160,720)
    a=np.linspace(-extent,extent,size); u,v=np.meshgrid(a,a[::-1])
    if plane=="xy":X,Y,Z=u,v,np.full_like(u,z0)
    elif plane=="xz":X,Y,Z=u,np.full_like(u,z0),v
    else:X,Y,Z=np.full_like(u,z0),u,v
    radius=np.sqrt(X*X+Y*Y+Z*Z)
    theta=np.arccos(np.clip(Z/np.maximum(radius,1e-20),-1,1))
    phi=np.arctan2(Y,X)
    rho=2*radius/n
    norm=math.exp(.5*(3*math.log(2/n)+gammaln(n-l)-math.log(2*n)-gammaln(n+l+1)))
    radial=norm*np.exp(-rho/2)*rho**l*genlaguerre(n-l-1,2*l+1)(rho)
    psi=radial*sph_harm_y(l,m,theta,phi)
    if opt.get("basis","complex")=="real" and m!=0:
        psi=np.sqrt(2)*((-1)**m)*(psi.real if m>0 else psi.imag)
    if mode=="density": val=np.abs(psi)**2
    elif mode=="real":val=np.real(psi)
    elif mode=="imag":val=np.imag(psi)
    else:val=np.angle(psi)
    finite=np.isfinite(val)
    vmax=np.percentile(np.abs(val[finite]),99.5) if finite.any() else 1
    vmax=max(float(vmax),1e-15)
    if mode=="density":
        rgb=_heat_rgb(np.clip(val/vmax,0,1))
    elif mode=="phase":
        rgb=_hsv_rgb(np.mod(val/(2*np.pi),1),np.full(val.shape,.8),np.clip(np.abs(psi)/max(float(np.max(np.abs(psi))),1e-15),.1,1))
    else:
        color=np.clip(val/vmax,-1,1)
        rgb=np.empty((*color.shape,3),dtype=np.uint8)
        rgb[...,0]=np.where(color>=0,245,245-200*np.abs(color))
        rgb[...,1]=245-205*np.abs(color)
        rgb[...,2]=np.where(color<0,245,245-200*np.abs(color))
    return _save_rgb(output_dir,rgb,"hydrogen-orbital",f"Hydrogen n={n}, l={l}, m={m} ({plane})",
        f"解析氢原子波函数（原子单位）：n={n}, l={l}, m={m}，{plane} 平面偏移 {z0:g} a0，mode={mode}；径向部分与球谐函数来自 SciPy。")
