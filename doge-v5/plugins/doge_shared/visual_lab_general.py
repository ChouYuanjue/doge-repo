"""Compatibility layer for general /lab scientific engines.

Historic presets are shortcuts to the same parametrized kernels; requests with
unrecognized options are rejected rather than silently ignoring inputs.
"""
from __future__ import annotations

import shlex
from pathlib import Path

from .science_expression import int_opt, options
from .visual_lab import LabError

ALL = {
    "size","center","zoom","span","iter","escape","c","z0","tol","expr","matrix","vector",
    "range","ylim","x","y","z","frequency","rate","seconds","maxfreq","extent","offset",
    "plane","mode","basis","eq","vars","init","params","time","steps","method","discard",
    "charges","fx","fy","soft","axiom","rules","angle","heading","bodies","g",
    "feed","kill","du","dv","preset","seed","sites","count","width","boundary","rng",
    "rule","temperature","coupling","sweeps","kind","ensemble","n","ratio","rows","balls","p",
    "walkers","diffusion","drift","turns","rmin","rmax","samples","field",
    "wavelength","extent","sources","decay","theta1","theta2","omega","masses","lengths",
    "infectious","r0","alpha","beta","gamma","delta","capacity","bias","fx","fy","phase",
    "p","q","vectors","a","cells","wavelength","maxh","maxangle","particles","neighbors",
}

# Reject option values that the selected backend cannot consume.
_OPT_GROUPS = {
    "complex": "expr center zoom span size",
    "newton": "expr center zoom span size iter tol",
    "fractal": "expr center zoom span size iter escape c z0",
    "linear": "matrix vector",
    "plot": "expr range size ylim",
    "param": "x y z range size",
    "spectrum": "expr frequency rate seconds maxfreq",
    "orbital": "expr basis plane mode extent offset size",
    "ode": "eq vars init params time steps method",
    "map": "eq vars init params steps discard",
    "attractor": "eq vars init params time steps method discard",
    "lsys": "axiom rules angle heading iter",
    "field": "charges fx fy range soft size",
    "nbody": "bodies time steps g soft",
    "reaction": "preset feed kill du dv size steps seed",
    "voronoi": "count sites size seed",
    "ca": "rule steps width boundary seed rng",
    "ising": "temperature coupling field sweeps size seed init",
    "percolation": "p size seed kind",
    "randommatrix": "n seed ensemble ratio",
    "galton": "rows balls p seed",
    "brownian": "walkers steps diffusion drift seed",
    "ant": "steps size turns",
    "chaos": "expr range size seed discard samples steps rmin rmax",
    "wave":"wavelength extent sources decay size",
    "pendulum":"theta1 theta2 omega masses lengths g time steps delta",
    "sir":"r0 infectious init time steps",
    "predator":"alpha beta delta gamma capacity init time steps",
    "replicator":"matrix init time steps bias",
    "lissajous":"fx fy phase range size",
    "knot":"preset p q x y z range size",
    "lattice":"preset vectors a basis cells",
    "xrd":"preset vectors a basis wavelength maxh maxangle width",
    "dla":"particles size seed neighbors",
}
_OPT_KEYS = {key: set(value.split()) for key,value in _OPT_GROUPS.items()}
_HEAD_TO_GROUP = {
    "domain":"complex","fft":"spectrum","parametric":"param","l-system":"lsys",
    "orbit":"nbody","grayscott":"reaction","geometry":"voronoi",
    "perc":"percolation","rmt":"randommatrix","bean":"galton",
    "walk":"brownian","langton":"ant","aggregate":"dla",
    "doublependulum":"pendulum","lotka":"predator","rps":"replicator",
    "diffraction-crystal":"xrd",
    "xy":"lissajous","slit":"diffraction",
}
def _opt_group(head):
    return _HEAD_TO_GROUP.get(head, head)


def render_general(output_dir:Path,payload:str):
    from . import visual_lab_analytic as a
    from . import visual_lab_dynamics as d
    from . import visual_lab_stochastic as st
    from . import visual_lab_models as mo
    from . import visual_lab_crystals as cr
    try:
        tokens=shlex.split(payload)
    except ValueError as exc:
        raise LabError("引号未闭合；含空格的表达式用英文引号包裹") from exc
    if not tokens:return None
    head=tokens[0].lower()
    if head not in {
        "complex","domain","newton","fractal","linear","plot","param","parametric",
        "spectrum","fft","orbital","ode","map","attractor","lsys","l-system",
        "field","orbit","nbody","reaction","grayscott","voronoi","geometry","ca",
        "ising","percolation","perc","randommatrix","rmt","galton","bean","brownian","walk",
        "ant","langton","chaos","wave","pendulum","doublependulum",
        "sir","predator","lotka","replicator","rps","lissajous","xy","knot","lattice","xrd","diffraction-crystal","dla","aggregate",
    }:
        return None
    args,opt=options(tokens[1:],ALL)
    allowed=_OPT_KEYS[_opt_group(head)]
    invalid=set(opt)-allowed
    if invalid:
        raise LabError(f"{head} 不支持选项 "+", ".join("--"+k for k in sorted(invalid)))
    def noextra(maximum):
        if len(args)>maximum:
            raise LabError(f"{head} 位置参数过多；请使用 /lab 查看 -- 选项")
    if head in {"complex","domain"}:
        aliases={"z":"z","id":"z","z2+1":"z^2+1","z3-1":"z^3-1","inv":"1/z",
                 "sin":"sin(z)","sinz":"sin(z)","exp":"exp(z)","expz":"exp(z)"}
        noextra(2)
        expr=opt.get("expr",args[0] if args else "z^3-1")
        expr=aliases.get(expr.lower(),expr)
        if len(args)>1: opt.setdefault("zoom",args[1])
        return a.complex_domain(output_dir,expr,opt)
    if head=="newton":
        noextra(2)
        first=opt.get("expr",args[0] if args else "3")
        expr=f"z^{first}-1" if first.isdigit() else first
        if len(args)>1:opt.setdefault("zoom",args[1])
        return a.newton_general(output_dir,expr,opt)
    if head=="fractal":
        if not args:raise LabError("fractal 用法：mandelbrot/julia [legacy coords] [--expr 'z^3+c'] ...")
        kind=args.pop(0).lower()
        if kind in {"mandelbrot","mandel","m","parameter","custom"}:
            if "c" in opt:raise LabError("--c 只用于 Julia 常数平面；Mandelbrot 参数 c 取自像素坐标")
            noextra(3)
            if len(args)==1:raise LabError("Mandelbrot 位置中心需要同时给定 cx cy；也可使用 --center cx,cy")
            if args:
                if len(args)>=2: opt.setdefault("center",args[0]+","+args[1])
                if len(args)>=3: opt.setdefault("zoom",args[2])
            opt.setdefault("center","-0.75,0")
            return a.escape_fractal(output_dir,"parameter",opt.get("expr","z^2+c"),opt)
        if kind in {"julia","j"}:
            if "z0" in opt:raise LabError("--z0 只用于参数平面；Julia 从各像素 z0 出发")
            noextra(3)
            if len(args)==1:raise LabError("Julia 常数需要同时给定实部与虚部")
            if len(args)>=2: opt.setdefault("c",args[0]+("+" if not args[1].startswith("-") else "")+args[1]+"i")
            if len(args)>=3: opt.setdefault("zoom",args[2])
            return a.escape_fractal(output_dir,"julia",opt.get("expr","z^2+c"),opt)
        raise LabError("fractal 当前支持 mandelbrot / julia，并可用 --expr 自定义迭代映射")
    if head=="linear":
        matrix=opt.get("matrix")
        if matrix is None and len(args)==4:
            matrix=",".join(args[:2])+";"+",".join(args[2:])
        elif matrix is None and len(args)==1:
            matrix=args[0]
        elif matrix is None or args:
            raise LabError("用法：/lab linear 1 2 3 4 或 /lab linear --matrix '1,2,3;4,5,6' [--vector 1,2,3]")
        return a.linear_general(output_dir,matrix,opt)
    if head=="plot":
        noextra(1)
        expr=opt.get("expr",args[0] if args else "")
        if not expr:raise LabError("用法：/lab plot 'sin(x)+x^2' [--range -3,3]")
        return a.function_plot(output_dir,expr,opt)
    if head in {"param","parametric"}:
        noextra(0)
        return a.parametric_plot(output_dir,opt)
    if head in {"spectrum","fft"}:
        aliases={
            "sine":"sin(2*pi*f*t)","sin":"sin(2*pi*f*t)",
            "square":"square",
            "saw":"sawtooth",
            "sawtooth":"sawtooth",
            "chirp":"sin(2*pi*(f*t+18*t^2))",
        }
        noextra(2)
        if len(args)>1:opt.setdefault("frequency",args[1])
        expr=opt.get("expr",args[0] if args else "square")
        expr=aliases.get(expr,expr)
        return a.spectrum_general(output_dir,expr,opt)
    if head=="orbital":
        noextra(1)
        name=args[0].lower() if args else "2px"
        alias={"1s":(1,0,0,"real"),"s":(1,0,0,"real"),
               "2p":(2,1,1,"real"),"2px":(2,1,1,"real"),"px":(2,1,1,"real"),
               "2py":(2,1,-1,"real"),"py":(2,1,-1,"real"),
               "3dxy":(3,2,-2,"real"),"dxy":(3,2,-2,"real"),
               "3dz2":(3,2,0,"real"),"dz2":(3,2,0,"real")}
        if name in alias:
            n,l,m,basis=alias[name]
            opt.setdefault("basis",basis)
        else:
            raw=opt.get("expr",name).split(",")
            if len(raw)!=3:raise LabError("orbital 用法：/lab orbital n,l,m [--plane xy|xz|yz] [--mode density|real|imag|phase]")
            try:n,l,m=map(int,raw)
            except ValueError as exc:raise LabError("轨道量子数必须是整数") from exc
        return a.orbital_general(output_dir,n,l,m,opt)
    if head=="ode":
        noextra(1)
        eq=opt.get("eq",args[0] if args else "")
        if not eq:raise LabError("ode 需要 --eq 'y;-x' --init '1,0' --time 20")
        return d.ode_general(output_dir,eq,opt)
    if head=="map":
        noextra(1)
        eq=opt.get("eq",args[0] if args else "")
        if not eq:raise LabError("map 需要 --eq '1-a*x^2+y;b*x' --init '0.1,0.1' --params 'a=1.4,b=0.3'")
        return d.map_general(output_dir,eq,opt)
    if head=="attractor":
        noextra(1)
        return d.attractor_general(output_dir,args[0] if args else "lorenz",opt)
    if head in {"lsys","l-system"}:
        noextra(2)
        if len(args)>1:opt.setdefault("iter",args[1])
        return d.lsystem_general(output_dir,args[0].lower() if args else "dragon",opt)
    if head=="field":
        noextra(1)
        kind=args[0].lower() if args else "dipole"
        presets={
            "dipole":"-0.8,0,1;0.8,0,-1",
            "quadrupole":"-0.8,-0.8,1;0.8,0.8,1;-0.8,0.8,-1;0.8,-0.8,-1",
            "triple":"-0.9,-0.3,1;0.9,-0.3,1;0,0.8,-1"
        }
        if kind not in presets and not ({"fx","fy","charges"}&opt.keys()):
            raise LabError("field 支持 --charges 'x,y,q;...' 或 --fx/--fy 自定义向量场")
        if kind in presets and not ({"fx","fy"}&opt.keys()):opt.setdefault("charges",presets[kind])
        return d.field_general(output_dir,opt)
    if head in {"orbit","nbody"}:
        noextra(1)
        name=args[0] if args else "figure8"
        if "bodies" in opt:name=opt["bodies"]
        if name in {"8","threebody"}:name="figure8"
        return d.nbody_general(output_dir,name,opt)
    if head in {"reaction","grayscott"}:
        noextra(1)
        if args:opt.setdefault("preset",args[0].lower())
        return d.grayscott_general(output_dir,opt)
    if head in {"voronoi","geometry"}:
        noextra(1)
        if args and args[0].isdigit():opt.setdefault("count",args[0])
        elif args and args[0] not in {"voronoi"}:raise LabError("geometry 目前支持 Voronoi；自定义点用 --sites")
        return d.voronoi_general(output_dir,opt)
    if head=="ca":
        noextra(2)
        if args:opt.setdefault("rule",args[0])
        if len(args)>1:opt.setdefault("steps",args[1])
        return d.ca_general(output_dir,opt.get("rule","30"),opt)
    if head in {"dla","aggregate"}:
        from .visual_lab_fun import dla
        noextra(2)
        if args:opt.setdefault("particles",args[0])
        if len(args)>1:opt.setdefault("size",args[1])
        try:
            return dla(output_dir,
                       int_opt(opt.get("particles","850"),"particles",80,2200),
                       int_opt(opt.get("size","321"),"size",181,451),
                       seed=int_opt(opt.get("seed","20260831"),"seed",0,2**31-1),
                       neighbors=int_opt(opt.get("neighbors","8"),"neighbors",4,8))
        except ValueError:
            raise
    if head=="lattice":
        noextra(2)
        if args:opt.setdefault("preset",args[0].lower())
        if len(args)>1:opt.setdefault("cells",args[1])
        return cr.lattice(output_dir,opt)
    if head in {"xrd","diffraction-crystal"}:
        noextra(3)
        if args:opt.setdefault("preset",args[0].lower())
        if len(args)>1:opt.setdefault("a",args[1])
        if len(args)>2:opt.setdefault("wavelength",args[2])
        return cr.xrd(output_dir,opt)
    if head=="wave":
        noextra(2)
        if args:
            if "sources" in opt:raise LabError("指定 --sources 时不可再传旧版波源间距位置参数")
            separation=float(args[0])
            if len(args)>1:opt.setdefault("wavelength",args[1])
            opt.setdefault("sources",f"{-separation/2:g},0,1,0;{separation/2:g},0,1,0")
        return mo.wave_general(output_dir,opt)
    if head in {"pendulum","doublependulum"}:
        noextra(1)
        if args:opt.setdefault("theta1",args[0])
        return mo.pendulum_general(output_dir,opt)
    if head=="sir":
        noextra(2)
        if args:opt.setdefault("r0",args[0])
        if len(args)>1:opt.setdefault("infectious",args[1])
        return mo.sir_general(output_dir,opt)
    if head in {"predator","lotka"}:
        noextra(4)
        for k,v in zip(("alpha","beta","delta","gamma"),args):opt.setdefault(k,v)
        return mo.predator_general(output_dir,opt)
    if head in {"replicator","rps"}:
        noextra(1)
        if args:opt.setdefault("bias",args[0])
        return mo.replicator_general(output_dir,opt)
    if head in {"lissajous","xy"}:
        noextra(3)
        for k,v in zip(("fx","fy","phase"),args):opt.setdefault(k,v)
        return mo.lissajous_general(output_dir,opt)
    if head=="knot":
        noextra(3)
        if args:opt.setdefault("preset",args[0].lower())
        if len(args)>1:opt.setdefault("p",args[1])
        if len(args)>2:opt.setdefault("q",args[2])
        return mo.knot_general(output_dir,opt)
    if head=="ising":
        noextra(2)
        if args: opt.setdefault("temperature",args[0])
        if len(args)>1: opt.setdefault("sweeps",args[1])
        return st.ising(output_dir,opt)
    if head in {"percolation","perc"}:
        noextra(2)
        if args: opt.setdefault("p",args[0])
        if len(args)>1: opt.setdefault("size",args[1])
        return st.percolation(output_dir,opt)
    if head in {"randommatrix","rmt"}:
        noextra(2)
        if args:opt.setdefault("ensemble",args[0])
        if len(args)>1:opt.setdefault("n",args[1])
        return st.random_matrix(output_dir,opt)
    if head in {"galton","bean"}:
        noextra(2)
        if args:opt.setdefault("rows",args[0])
        if len(args)>1:opt.setdefault("balls",args[1])
        return st.galton(output_dir,opt)
    if head in {"brownian","walk"}:
        noextra(2)
        if args:opt.setdefault("walkers",args[0])
        if len(args)>1:opt.setdefault("steps",args[1])
        return st.brownian(output_dir,opt)
    if head in {"ant","langton"}:
        noextra(1)
        if args:opt.setdefault("steps",args[0])
        return st.ant(output_dir,opt)
    if head=="chaos":
        noextra(3)
        if not args or args[0] not in {"bifurcation","bif","logistic"}:
            raise LabError("chaos 用法：/lab chaos bifurcation [rmin rmax] [--expr 'r*x*(1-x)']")
        if len(args)>=2:opt.setdefault("rmin",args[1])
        if len(args)>=3:opt.setdefault("rmax",args[2])
        return d.bifurcation_general(output_dir,opt)
    return None


def _saw_plot(output_dir,t,y,fs,f):
    import numpy as np
    plt=__import__(__package__+".visual_lab_analytic",fromlist=["_plt"])._plt()
    fig,axes=plt.subplots(2,1,figsize=(10,7),dpi=100)
    try:
        n=len(t);win=np.hanning(n)
        freqs=np.fft.rfftfreq(n,1/fs)
        amps=2*np.abs(np.fft.rfft((y-y.mean())*win))/win.sum()
        visible=min(n,max(100,fs//2))
        axes[0].plot(t[:visible],y[:visible]);axes[1].plot(freqs,amps)
        axes[1].set_xlim(0,min(fs/2,max(30,6*f)))
        for ax in axes:ax.grid(alpha=.2)
        axes[0].set_title(f"Actual sawtooth waveform (SciPy) | f={f:g} Hz")
        axes[0].set_xlabel("time (s)");axes[1].set_xlabel("frequency (Hz)")
        fig.tight_layout();path=__import__(__package__+".visual_lab",fromlist=["_out"])._out(output_dir,"saw-spectrum")
        fig.savefig(path)
    finally:plt.close(fig)
    return path,f"由 scipy.signal.sawtooth 生成真实采样：{len(t)} 点，fs={fs}Hz，f={f:g}Hz；下图为去均值 Hann 窗 FFT。"


HELP = """/lab 可泛化计算引擎（预设仍可用）
  /lab complex 'sin(z)/(z^2+1)' --center 0,0 --zoom 2 --size 560
  /lab newton 'z^5-z+1' --iter 60 --tol 1e-7 --zoom 1.5
  /lab fractal mandelbrot --expr 'z^3+c' --center -0.7,0 --zoom 1.5 --iter 160
  /lab fractal julia --expr 'z^2+c' --c -0.4+0.6i --zoom 2
  /lab linear --matrix '1,2,3;0,1,4;0,0,1' --vector 1,2,3
  /lab plot 'sin(x);cos(2*x)' --range -6.28,6.28
  /lab param --x 'cos(3*t)' --y 'sin(2*t)' --range 0,6.28
  /lab ode --eq 'y;-x' --init 1,0 --time 20
  /lab map --eq '1-a*x^2+y;b*x' --init 0.1,0.1 --params a=1.4,b=0.3
  /lab attractor lorenz --params sigma=14,rho=32,beta=2.7 --time 80
  /lab lsys custom --axiom F --rules 'F=F+F--F+F' --angle 60 --iter 4
  /lab field --charges '-1,0,1;1,0,-1'  或 --fx '-y' --fy x
  /lab nbody --bodies '1,-1,0,0,0.5;1,1,0,0,-0.5' --time 12
  /lab reaction --feed 0.035 --kill 0.065 --du 0.16 --dv 0.08 --steps 1800
  /lab spectrum --expr 'sin(2*pi*7*t)+0.4*sin(2*pi*21*t)' --rate 1024
  /lab orbital 4,2,1 --plane xz --mode density
  /lab voronoi --sites '0,0;1,1;-1,1;0.1,-0.9'
  /lab ca 110 400 --seed random --width 801 --boundary wrap
  /lab ising --temperature 2.1 --coupling 1 --field 0.2 --seed 2026
  /lab percolation --p 0.6 --kind bond --seed 2026
  /lab randommatrix --ensemble wishart --n 90 --ratio 1.8 --seed 2026
  /lab galton --rows 15 --balls 10000 --p 0.42 --seed 2026
  /lab brownian --diffusion 0.3 --drift 0.1,0 --walkers 50
  /lab ant --turns RLLR --steps 50000
  /lab chaos bifurcation --expr "r*x*(1-x)" --rmin 2.5 --rmax 4
  /lab wave --sources "-1,0,1,0;1,0,0.5,45" --wavelength 0.3
  /lab pendulum --theta1 100 --theta2 -20 --masses 1,2 --lengths 1,1.5
  /lab sir --r0 3.0 --infectious 5 --init .98,.02,0 --time 100
  /lab replicator --matrix "0,2,1;1,0,3;3,1,0" --init .2,.3,.5
  /lab knot --x "cos(2*t)" --y "sin(2*t)" --z "sin(3*t)"
  /lab lattice --vectors "2,0,0;0,3,0;0,0,4" --basis "0,0,0;0.5,0.5,0.5"
  /lab xrd --vectors "2,0,0;0,3,0;0,0,4" --basis "0,0,0,1;0.5,0.5,0.5,1"
  /lab dla --particles 600 --size 321 --neighbors 4 --seed 123
  /lab life random:123:0.35 120 B36/S23 wrap 121
数值计算使用 SymPy / NumPy / SciPy，绘图使用 Matplotlib / Pillow。
复函数表达式支持 + - * / ^、sin/cos/tan、exp/log/sqrt、abs/arg/re/im 等；
不支持任意 Python 代码。计算结果是模型模拟，不代表真实实验数据。"""
