"""Parameterized scientific systems built on SciPy, NumPy and classic numerical methods."""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .science_expression import compile_formula, compute, float_opt, int_opt, numbers
from .visual_lab import LabError, _heat_rgb, _out, _title


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _parameters(source: str):
    result={}
    for part in source.split(","):
        if not part.strip(): continue
        if "=" not in part: raise LabError("params 使用 name=value,name=value")
        name,value=part.split("=",1)
        name=name.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*",name) or name in {"x","y","z","t","u","v","w","pi","e","E","i","I"}:
            raise LabError(f"非法参数名 {name}")
        if name in result or len(result)>=12: raise LabError("参数名重复或数量超过 12")
        result[name]=float_opt(value.strip(), name, -1e6, 1e6)
    return result


def ode_general(output_dir:Path, equations:str, opt:dict):
    from scipy.integrate import solve_ivp
    plt=_plt()
    parts=[x.strip() for x in equations.split(";")]
    if not 2 <= len(parts) <= 4 or any(not p for p in parts):
        raise LabError("ODE 需 2..4 个分量方程，用 ; 分隔")
    names=tuple(x.strip() for x in opt.get("vars","x,y,z,u"[:0]).split(",") if x.strip())
    if not names: names=tuple("xyzu"[:len(parts)])
    if len(names)!=len(parts) or len(set(names))!=len(names):
        raise LabError("vars 的数量必须与 ODE 方程相同且互不重复")
    values=np.array(numbers(opt.get("init",",".join("0.1" for _ in parts)),"init",low=len(parts),high=len(parts)))
    pars=_parameters(opt.get("params",""))
    if any(k in names for k in pars): raise LabError("params 与状态变量重复")
    t_end=float_opt(opt.get("time",40),"time",.02,250.)
    samples=int_opt(opt.get("steps",2400),"steps",100,8000)
    args=tuple(names)+tuple(pars)+("t",)
    fs=[compile_formula(p,args) for p in parts]
    counters=[0]
    def f(t,y):
        counters[0]+=1
        if counters[0]>50000: raise LabError("ODE 右端计算次数超过限制；请缩短 time 或调整参数")
        x=[*y,*pars.values(),t]
        with np.errstate(all="ignore"):
            dy=np.array([float(fn(*x)) for fn in fs],float)
        if not np.isfinite(dy).all() or np.linalg.norm(y)>1e8 or np.linalg.norm(dy)>1e10:
            raise LabError("ODE 轨道发散或含非有限值")
        return dy
    method=opt.get("method","RK45")
    if method not in {"RK45","RK23","DOP853","Radau","BDF"}:
        raise LabError("method 支持 RK45/RK23/DOP853/Radau/BDF")
    sol=solve_ivp(f,(0,t_end),values,t_eval=np.linspace(0,t_end,samples),
                  method=method,rtol=2e-6,atol=1e-8)
    if not sol.success or not np.isfinite(sol.y).all(): raise LabError("ODE 积分未成功："+str(sol.message)[:120])
    fig=plt.figure(figsize=(11,6.5),dpi=105)
    try:
        if len(parts)>=3:
            ax=fig.add_subplot(121,projection="3d")
            ax.plot(sol.y[0],sol.y[1],sol.y[2],lw=.75)
            ax.set_zlabel(names[2])
        else:
            ax=fig.add_subplot(121)
            ax.plot(sol.y[0],sol.y[1],lw=.85)
        ax.set_xlabel(names[0]);ax.set_ylabel(names[1]);ax.set_title("Phase trajectory")
        ax=fig.add_subplot(122)
        for name,series in zip(names,sol.y): ax.plot(sol.t,series,label=name,lw=1)
        ax.set_xlabel("time");ax.set_title("State vs time")
        ax.legend();ax.grid(alpha=.2)
        fig.tight_layout();path=_out(output_dir,"ode");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"真实数值解：d({','.join(names)})/dt=({equations})，"
                 f"初值 {values.tolist()}，参数 {pars}，t∈[0,{t_end:g}]，method={method}；"
                 f"成功积分 {len(sol.t)} 个时刻，RHS 调用 {counters[0]} 次。")


def map_general(output_dir:Path, equations:str, opt:dict):
    plt=_plt()
    parts=[x.strip() for x in equations.split(";")]
    if not 2<=len(parts)<=3: raise LabError("离散映射应提供 2 或 3 个方程")
    names=tuple(x.strip() for x in opt.get("vars",",".join("xyz"[:len(parts)])).split(","))
    if len(names)!=len(parts) or len(set(names))!=len(names): raise LabError("vars 维度不匹配")
    init=np.array(numbers(opt.get("init",",".join(["0.1"]*len(parts))),"init",low=len(parts),high=len(parts)))
    pars=_parameters(opt.get("params",""))
    args=names+tuple(pars)
    fns=[compile_formula(p,args) for p in parts]
    steps=int_opt(opt.get("steps",35000),"steps",100,100000)
    discard=int_opt(opt.get("discard",1000),"discard",0,steps-1)
    hist=np.empty((steps-discard,len(parts)),float)
    s=init.copy()
    parvals=tuple(pars.values())
    for i in range(steps):
        arg=tuple(s)+parvals
        with np.errstate(all="ignore"):
            v=np.array([float(fn(*arg)) for fn in fns],float)
        if not np.isfinite(v).all() or np.max(np.abs(v))>1e7:
            raise LabError(f"离散映射在第 {i} 次迭代发散")
        s=v
        if i>=discard:hist[i-discard]=s
    fig=plt.figure(figsize=(8.8,7),dpi=105)
    try:
        ax=fig.add_subplot(111,projection="3d" if len(parts)==3 else None)
        sub=hist[::max(1,len(hist)//25000)]
        if len(parts)==3:
            ax.plot(*sub.T,lw=.5)
        else:
            ax.scatter(sub[:,0],sub[:,1],s=.1,alpha=.45)
            ax.set_aspect("equal",adjustable="datalim")
        ax.set_xlabel(names[0]);ax.set_ylabel(names[1])
        if len(parts)==3: ax.set_zlabel(names[2])
        ax.set_title(f"Discrete map ({steps} iterations, {discard} discarded)")
        fig.tight_layout();path=_out(output_dir,"map");fig.savefig(path)
    finally:plt.close(fig)
    return path,f"离散动力系统 x[n+1]=F(x[n])，{len(parts)} 维，迭代 {steps} 次，舍弃前 {discard} 次；方程={equations}；参数={pars}。"


_LORENZ="sigma*(y-x);x*(rho-z)-y;x*y-beta*z"
_ROSSLER="-y-z;x+a*y;b+z*(x-c)"
_CLIFFORD="sin(a*y)+c*cos(a*x);sin(b*x)+d*cos(b*y)"


def attractor_general(output_dir:Path, name:str, opt:dict):
    name=name.lower()
    if "eq" in opt:
        equations=opt["eq"]
        return ode_general(output_dir,equations,opt)
    if name in {"lorenz","rossler"} and "discard" in opt:
        raise LabError("--discard 只用于离散 Clifford 映射；连续 ODE 使用 --time")
    if name=="clifford" and ({"time","method"} & opt.keys()):
        raise LabError("Clifford 是离散迭代映射，请使用 --steps/--discard，不支持 --time/--method")
    if name=="lorenz":
        vals={"eq":_LORENZ,"params":"sigma=10,rho=28,beta=2.6666666667","init":"0.1,0,0","time":"65"}
    elif name=="rossler":
        vals={"eq":_ROSSLER,"params":"a=0.2,b=0.2,c=5.7","init":"0.1,0,0","time":"135"}
    elif name=="clifford":
        vals={"eq":_CLIFFORD,"params":"a=-1.4,b=1.6,c=1,d=0.7","init":"0.1,0.1","steps":"70000","discard":"2000"}
        vals.update(opt)
        return map_general(output_dir,vals.pop("eq"),vals)
    else:
        raise LabError("attractor 可选 lorenz/rossler/clifford，或传 --eq 自定义 ODE")
    vals.update(opt)
    return ode_general(output_dir,vals.pop("eq"),vals)


def field_general(output_dir:Path, opt:dict):
    plt=_plt()
    n=int_opt(opt.get("size",64),"size",24,130)
    xmin,xmax,ymin,ymax=numbers(opt.get("range","-2.5,2.5,-2.5,2.5"),"range",low=4,high=4)
    if xmin>=xmax or ymin>=ymax: raise LabError("range 必须 xmin<xmax 且 ymin<ymax")
    xs=np.linspace(xmin,xmax,n);ys=np.linspace(ymin,ymax,n)
    X,Y=np.meshgrid(xs,ys)
    U=np.zeros_like(X);V=np.zeros_like(Y)
    charges=[]
    if "fx" in opt or "fy" in opt:
        if "charges" in opt:raise LabError("不能同时指定点电荷场 --charges 和显式向量场 --fx/--fy")
        if not {"fx","fy"}<=opt.keys(): raise LabError("通用向量场需同时提供 --fx 与 --fy")
        U=compute(opt["fx"],("x","y"),X,Y,shape=X.shape).astype(float)
        V=compute(opt["fy"],("x","y"),X,Y,shape=X.shape).astype(float)
    else:
        raw=opt.get("charges","-0.8,0,1;0.8,0,-1")
        for item in raw.split(";"):
            qx,qy,q=numbers(item,"charges: x,y,q",low=3,high=3)
            charges.append((qx,qy,q))
        if not 1 <=len(charges)<=20: raise LabError("charges 必须提供 1..20 个电荷")
        potential=np.zeros_like(X)
        soft=float_opt(opt.get("soft",.04),"soft",.001,1.)
        for x0,y0,q in charges:
            dx,dy=X-x0,Y-y0
            r2=dx*dx+dy*dy+soft*soft
            potential+=q/np.sqrt(r2)
            U+=q*dx/r2**1.5
            V+=q*dy/r2**1.5
    if not np.isfinite(U).all() or not np.isfinite(V).all() or max(np.max(np.abs(U)),np.max(np.abs(V)))>1e15:
        raise LabError("向量场含非有限值")
    fig,ax=plt.subplots(figsize=(8,7),dpi=100)
    try:
        speed=np.hypot(U,V)
        ax.streamplot(X,Y,U,V,color=np.log1p(speed),cmap="viridis",density=1.25,linewidth=.7,arrowsize=.8)
        if charges:
            for qx,qy,q in charges:
                ax.scatter(qx,qy,c="red" if q>0 else "blue",s=100,edgecolor="white",zorder=4)
        ax.set_xlabel("x");ax.set_ylabel("y");ax.set_aspect("equal")
        ax.set_title("Vector field " + (opt.get("fx","")[:60] if not charges else f"{len(charges)} point charges"))
        fig.tight_layout();path=_out(output_dir,"field");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"用 {n}x{n} 网格计算流线；"+
       (f"点电荷 {charges}（使用 {opt.get('soft',.04)} 的软化尺度避免奇点）" if charges
        else f"F=({opt['fx']}, {opt['fy']})")+
       "。图示为模型求解，不是实测场图。")


_LSYS={
    "dragon":("FX",{"X":"X+YF+","Y":"-FX-Y"},90,11),
    "hilbert":("A",{"A":"+BF-AFA-FB+","B":"-AF+BFB+FA-"},90,5),
    "koch":("F--F--F",{"F":"F+F--F+F"},60,4),
    "plant":("X",{"X":"F+[[X]-X]-F[-FX]+X","F":"FF"},25,5),
}


def lsystem_general(output_dir:Path,name:str,opt:dict):
    if name in _LSYS:
        axiom,rules,angle,iterations=_LSYS[name]
    else:
        axiom,rules,angle,iterations="F",{},90,4
        if name not in {"custom",""}: raise LabError("自定义 L-system 使用 /lab lsys custom --axiom ... --rules ... --angle ...")
    axiom=opt.get("axiom",axiom)
    angle=float_opt(opt.get("angle",angle),"angle",-360,360)
    iterations=int_opt(opt.get("iter",iterations),"iter",0,15)
    heading=math.radians(float_opt(opt.get("heading",-90),"heading",-360,360))
    if "rules" in opt:
        rules={}
        for r in opt["rules"].split(";"):
            if "=" not in r: raise LabError("rules 格式：F=F+F--F+F;X=...")
            key,value=r.split("=",1)
            if len(key)!=1 or not key.isalpha() or key in rules: raise LabError("规则左侧必须是一个字母")
            rules[key]=value
    if not axiom or len(axiom)>200 or len(rules)>25 or any(len(v)>300 for v in rules.values()):
        raise LabError("L-system 文法过大")
    if any(not (c.isalpha() or c in "+-[]|") for c in axiom+"".join(rules.values())):
        raise LabError("L-system 只允许英文字母和 +-[]|")
    s=axiom
    for _ in range(iterations):
        s="".join(rules.get(ch,ch) for ch in s)
        if len(s)>300000:raise LabError("L-system 展开超过 30 万字符，请降低迭代数")
    x=y=0.; stack=[]; pts=[]; turn=math.radians(angle)
    for ch in s:
        if ch in "FG":
            nx,ny=x+math.cos(heading),y+math.sin(heading)
            pts.append((x,y,nx,ny));x,y=nx,ny
        elif ch=="f":
            x,y=x+math.cos(heading),y+math.sin(heading)
        elif ch=="+":heading+=turn
        elif ch=="-":heading-=turn
        elif ch=="|":heading+=math.pi
        elif ch=="[": stack.append((x,y,heading))
        elif ch=="]":
            if not stack: raise LabError("L-system 括号不匹配")
            x,y,heading=stack.pop()
    if stack:raise LabError("L-system 括号不匹配")
    if not pts:raise LabError("L-system 展开后没有 F/G 可绘制线段")
    xy=np.array(pts).reshape(-1,2)
    low,high=np.min(xy,axis=0),np.max(xy,axis=0)
    scale=780/max(float(np.max(high-low)),1e-9)
    offset=450-(high+low)/2*scale
    img=Image.new("RGB",(900,900),(249,248,245));d=ImageDraw.Draw(img)
    for x1,y1,x2,y2 in pts:
        d.line((x1*scale+offset[0],y1*scale+offset[1],x2*scale+offset[0],y2*scale+offset[1]),fill=(30,45,56),width=1)
    _title(img,f"L-system {name} | iter={iterations} | angle={angle:g}")
    path=_out(output_dir,"lsys");img.save(path)
    return path,f"真实 L-system 字符替换与 turtle 绘制：axiom={axiom}，rules={rules}，角度={angle:g}°，迭代={iterations}，线段数={len(pts)}。"


def nbody_general(output_dir:Path, raw:str,opt:dict):
    plt=_plt()
    if raw=="figure8":
        masses=np.ones(3)
        R=np.array([[-.97000436,.24308753],[.97000436,-.24308753],[0,0.]])
        V=np.array([[.466203685,.43236573],[.466203685,.43236573],[-.93240737,-.86473146]])
    else:
        bodies=[numbers(b,"body: mass,x,y,vx,vy",low=5,high=5) for b in raw.split(";") if b.strip()]
        if not 2<=len(bodies)<=6 or any(b[0]<=0 for b in bodies):
            raise LabError("bodies 需 2..6 个质量为正的天体；每行 m,x,y,vx,vy 用 ; 分隔")
        a=np.asarray(bodies,float)
        masses,R,V=a[:,0],a[:,1:3],a[:,3:5]
    steps=int_opt(opt.get("steps",7000),"steps",100,12000)
    duration=float_opt(opt.get("time",15 if raw=="figure8" else 10),"time",.01,100)
    gravity=float_opt(opt.get("g",1),"g",.0001,100)
    soft=float_opt(opt.get("soft",.01),"soft",.00001,3.)
    dt=duration/steps
    tracks=np.empty((steps//2+1,len(masses),2))
    def acc(positions):
        dif=positions[None,:,:]-positions[:,None,:]
        r2=np.sum(dif*dif,axis=-1)+soft**2
        np.fill_diagonal(r2,np.inf)
        return gravity*np.sum(dif*masses[None,:,None]/r2[:,:,None]**1.5,axis=1)
    a=acc(R);idx=0
    for t in range(steps):
        R=R+V*dt+.5*a*dt*dt
        new_a=acc(R)
        V=V+.5*(a+new_a)*dt
        a=new_a
        if not np.isfinite(R).all() or np.max(np.abs(R))>1e8:
            raise LabError(f"N 体积分在 {t} 步发散")
        if t%2==0:tracks[idx]=R;idx+=1
    fig,ax=plt.subplots(figsize=(9,7),dpi=105)
    try:
        for j in range(len(masses)):
            ax.plot(tracks[:idx,j,0],tracks[:idx,j,1],lw=1.3,label=f"m={masses[j]:g}")
            ax.scatter([tracks[idx-1,j,0]],[tracks[idx-1,j,1]],s=35)
        ax.set_aspect("equal",adjustable="datalim");ax.set_xlabel("x");ax.set_ylabel("y")
        ax.grid(alpha=.2);ax.legend(fontsize=9);ax.set_title(f"{len(masses)}-body gravity | leapfrog | time={duration:g}")
        fig.tight_layout();path=_out(output_dir,"nbody");fig.savefig(path)
    finally:plt.close(fig)
    return path,f"{len(masses)} 体经典万有引力数值模拟，质量 {masses.tolist()}，G={gravity:g}，软化 {soft:g}，时间 {duration:g}，速度 Verlet {steps} 步。"


def grayscott_general(output_dir:Path,opt:dict):
    presets={"spots":(.035,.065),"worms":(.078,.061),"mitosis":(.0367,.0649),"coral":(.0545,.062)}
    preset=opt.get("preset","spots")
    if preset not in presets:raise LabError("reaction preset 可用 spots/worms/mitosis/coral")
    f0,k0=presets[preset]
    feed=float_opt(opt.get("feed",f0),"feed",0,.15)
    kill=float_opt(opt.get("kill",k0),"kill",0,.15)
    du=float_opt(opt.get("du",.16),"du",.0001,.3)
    dv=float_opt(opt.get("dv",.08),"dv",.0001,.3)
    n=int_opt(opt.get("size",140),"size",64,220)
    steps=int_opt(opt.get("steps",1900),"steps",10,7000)
    seed=int_opt(opt.get("seed",42),"seed",0,2**31-1)
    u=np.ones((n,n),np.float32);v=np.zeros((n,n),np.float32)
    rng=np.random.default_rng(seed);s=max(4,n//12)
    u[n//2-s:n//2+s,n//2-s:n//2+s]=.5
    v[n//2-s:n//2+s,n//2-s:n//2+s]=.25
    v+=rng.normal(0,.008,v.shape).astype(np.float32)
    for _ in range(steps):
        lapu=(-u+.2*(np.roll(u,1,0)+np.roll(u,-1,0)+np.roll(u,1,1)+np.roll(u,-1,1))
             +.05*(np.roll(np.roll(u,1,0),1,1)+np.roll(np.roll(u,1,0),-1,1)+np.roll(np.roll(u,-1,0),1,1)+np.roll(np.roll(u,-1,0),-1,1)))
        lapv=(-v+.2*(np.roll(v,1,0)+np.roll(v,-1,0)+np.roll(v,1,1)+np.roll(v,-1,1))
             +.05*(np.roll(np.roll(v,1,0),1,1)+np.roll(np.roll(v,1,0),-1,1)+np.roll(np.roll(v,-1,0),1,1)+np.roll(np.roll(v,-1,0),-1,1)))
        uvv=u*v*v
        u+=du*lapu-uvv+feed*(1-u)
        v+=dv*lapv+uvv-(feed+kill)*v
        np.clip(u,0,1.4,out=u);np.clip(v,0,1.4,out=v)
    z=(v-v.min())/max(float(v.max()-v.min()),1e-12)
    rgb=_heat_rgb(z);img=Image.fromarray(rgb,"RGB").resize((800,800),Image.Resampling.BILINEAR)
    _title(img,f"Gray-Scott | F={feed:g} k={kill:g}, steps={steps}")
    path=_out(output_dir,"reaction");img.save(path)
    return path,f"Gray–Scott 反应扩散实际迭代 {steps} 次；F={feed:g}, k={kill:g}, Du={du:g}, Dv={dv:g}, N={n}, seed={seed}；周期边界，固定初始扰动。"


def voronoi_general(output_dir:Path,opt:dict):
    count=int_opt(opt.get("count",32),"count",2,170)
    seed=int_opt(opt.get("seed",19),"seed",0,2**31-1)
    rng=np.random.default_rng(seed)
    if "sites" in opt:
        seeds=np.array([numbers(s,"site",low=2,high=2) for s in opt["sites"].split(";")],float)
        if not 2<=len(seeds)<=170:raise LabError("sites 必须包含 2..170 个二维点")
    else:seeds=rng.uniform(-1,1,size=(count,2))
    n=int_opt(opt.get("size",520),"size",180,720)
    if np.ptp(seeds,axis=0).max()<1e-8:raise LabError("所有点的位置相同")
    lo=seeds.min(0);hi=seeds.max(0);pad=max(float(np.max(hi-lo))*.12,.1)
    xx=np.linspace(lo[0]-pad,hi[0]+pad,n);yy=np.linspace(hi[1]+pad,lo[1]-pad,n)
    X,Y=np.meshgrid(xx,yy)
    dist=np.full((n,n),np.inf);inds=np.zeros((n,n),dtype=np.uint16)
    for j,(x,y) in enumerate(seeds):
        dd=(X-x)**2+(Y-y)**2
        mask=dd<dist
        dist[mask]=dd[mask];inds[mask]=j
    colors=rng.integers(70,230,(len(seeds),3),dtype=np.uint8)
    rgb=colors[inds]
    edge=(inds!=np.roll(inds,1,0))|(inds!=np.roll(inds,1,1))
    rgb[edge]=(22,22,23)
    img=Image.fromarray(rgb,"RGB");d=ImageDraw.Draw(img)
    for x,y in seeds:
        px=(x-xx[0])/(xx[-1]-xx[0])*(n-1)
        py=(yy[0]-y)/(yy[0]-yy[-1])*(n-1)
        d.ellipse((px-3,py-3,px+3,py+3),fill="white",outline="black")
    _title(img,f"Voronoi | N={len(seeds)} | seed={seed}")
    path=_out(output_dir,"voronoi");img.save(path)
    return path,f"真实最近邻 Voronoi 细分：{len(seeds)} 个二维种子点；"+("坐标来自 sites。" if "sites" in opt else f"使用随机种子 {seed}。")


def ca_general(output_dir:Path,rule:int,opt:dict):
    rule=int_opt(rule,"rule",0,255)
    steps=int_opt(opt.get("steps",300),"steps",10,800)
    width=int_opt(opt.get("width",2*steps+1),"width",31,1601)
    if steps*width>600000:raise LabError("CA 输出过大")
    boundary=opt.get("boundary","dead")
    if boundary not in {"dead","wrap"}:raise LabError("boundary=dead|wrap")
    seed=opt.get("seed","single")
    row=np.zeros(width,dtype=np.uint8)
    if "rng" in opt and seed!="random":raise LabError("--rng 只用于 --seed random")
    if seed=="single":row[width//2]=1
    elif seed=="random":
        rng=np.random.default_rng(int_opt(opt.get("rng",23),"rng",0,2**31-1))
        row=rng.integers(0,2,size=width,dtype=np.uint8)
    elif set(seed)<={"0","1"} and len(seed)<=width and seed:
        start=(width-len(seed))//2
        row[start:start+len(seed)]=np.fromiter((int(c) for c in seed),dtype=np.uint8)
    else:raise LabError("seed 可为 single/random/01 比特串")
    hist=np.zeros((steps,width),dtype=np.uint8);hist[0]=row
    table=np.array([(rule>>k)&1 for k in range(8)],np.uint8)
    for t in range(1,steps):
        p=hist[t-1]
        left=np.roll(p,1);right=np.roll(p,-1)
        if boundary=="dead":left[0]=0;right[-1]=0
        hist[t]=table[(left<<2)|(p<<1)|right]
    col=np.where(hist[:,:,None],np.array([15,19,25],np.uint8),np.array([249,249,246],np.uint8))
    im=Image.fromarray(col.astype(np.uint8),"RGB")
    if max(im.size)<800:
        factor=max(2,min(8,math.ceil(160/min(im.size))))
        im=im.resize((im.width*factor,im.height*factor),Image.Resampling.NEAREST)
    _title(im,f"Elementary CA | rule={rule}, seed={seed[:15]}")
    path=_out(output_dir,"cellular");im.save(path)
    return path,f"Wolfram elementary CA，rule={rule}，width={width}，steps={steps}，seed={seed[:100]}，边界={boundary}；按三邻域规则逐格演化。"


def bifurcation_general(output_dir:Path,opt:dict):
    """Bifurcation of an arbitrary x[n+1]=f(x[n],r) map over swept r."""
    plt=_plt()
    rmin=float_opt(opt.get("rmin",2.5),"rmin",-50,50)
    rmax=float_opt(opt.get("rmax",4),"rmax",-50,50)
    if rmax<=rmin:raise LabError("rmax 必须大于 rmin")
    samples=int_opt(opt.get("samples",900),"samples",100,1800)
    transient=int_opt(opt.get("discard",600),"discard",0,3000)
    steps=int_opt(opt.get("steps",150),"steps",10,900)
    initial=float_opt(opt.get("seed",.500123),"seed",-10,10)
    expr=opt.get("expr","r*x*(1-x)")
    fn=compile_formula(expr,("x","r"))
    r=np.linspace(rmin,rmax,samples)
    x=np.full_like(r,initial)
    traj=np.empty((steps,samples),float)
    with np.errstate(all="ignore"):
        for k in range(transient+steps):
            x=np.asarray(fn(x,r),dtype=float)
            x=np.broadcast_to(x,r.shape).copy()
            x[~np.isfinite(x)|(np.abs(x)>1e8)]=np.nan
            if k>=transient:traj[k-transient]=x
    finite=np.isfinite(traj)
    if not finite.any():raise LabError("所有参数的迭代轨道均发散；缩小 r 范围或改变初值")
    fig,ax=plt.subplots(figsize=(11,7),dpi=105)
    try:
        rr=np.broadcast_to(r,traj.shape)
        sampled=np.flatnonzero(finite.ravel())
        # Limit plotted points to protect the small VPS / Telegram image.
        if len(sampled)>250000:sampled=sampled[::int(np.ceil(len(sampled)/250000))]
        ax.scatter(rr.ravel()[sampled],traj.ravel()[sampled],c="#1e3945",s=.08,rasterized=True)
        ax.set_xlim(rmin,rmax);ax.set_xlabel("bifurcation parameter r");ax.set_ylabel("steady-state x")
        ax.set_title("Iteration bifurcation: x[n+1] = "+expr[:70])
        ax.grid(alpha=.15);fig.tight_layout();path=_out(output_dir,"bifurcation-general");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"用户自定义离散映射 x[n+1]={expr}；r∈[{rmin:g},{rmax:g}]，"
                 f"{samples} 个参数，每个参数先丢弃 {transient} 次、保留 {steps} 次；"
                 f"有限的末期轨道点数 {int(finite.sum())}/{steps*samples}。")
