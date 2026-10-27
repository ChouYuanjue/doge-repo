"""Parameter-driven models for physical and biological /lab commands.

All curves are computed from the supplied initial conditions and actual model
equations.  They are illustrations of the stated idealized models, not data.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from .science_expression import compute, float_opt, int_opt, numbers
from .visual_lab import LabError, _heat_rgb, _out, _title


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def wave_general(output_dir:Path,opt:dict):
    n=int_opt(opt.get("size",560),"size",160,760)
    wavelength=float_opt(opt.get("wavelength",.35),"wavelength",.001,10)
    extent=float_opt(opt.get("extent",4),"extent",.1,100)
    sources=[numbers(raw,"sources: x,y,amplitude,phase_deg",low=4,high=4) for raw in opt.get("sources","-0.5,0,1,0;0.5,0,1,0").split(";")]
    if not 1<=len(sources)<=12: raise LabError("需要 1..12 个波源")
    X,Y=np.meshgrid(np.linspace(-extent,extent,n),np.linspace(extent,-extent,n))
    w=np.zeros(X.shape,dtype=np.complex128)
    decay=opt.get("decay","sqrt").lower()
    if decay not in {"none","sqrt","distance"}:raise LabError("decay=none|sqrt|distance")
    for x,y,amp,phase in sources:
        r=np.sqrt((X-x)**2+(Y-y)**2+.0025**2)
        envelope={"none":1,"sqrt":1/np.sqrt(r),"distance":1/r}[decay]
        w+=amp*envelope*np.exp(1j*(2*math.pi/wavelength*r+math.radians(phase)))
    intensity=np.abs(w)**2
    scale=max(float(np.percentile(intensity,99.5)),1e-12)
    rgb=_heat_rgb(np.log1p(intensity)/math.log1p(scale))
    img=Image.fromarray(rgb,"RGB")
    _title(img,f"Coherent wave | N={len(sources)}, lambda={wavelength:g}")
    path=_out(output_dir,"waves");img.save(path)
    return path,(f"复振幅线性叠加的二维相干点波源：{len(sources)} 个源 (x,y,A,phase°)={sources}，"
                 f"波长={wavelength:g}、振幅衰减={decay}；颜色为归一化相对强度 |Σ A exp(ikr+iφ)|²。")


def pendulum_general(output_dir:Path,opt:dict):
    from scipy.integrate import solve_ivp
    plt=_plt()
    theta1=float_opt(opt.get("theta1",120),"theta1",-360,360)
    theta2=float_opt(opt.get("theta2",-10),"theta2",-360,360)
    w1,w2=numbers(opt.get("omega","0,0"),"omega",low=2,high=2)
    m1,m2=numbers(opt.get("masses","1,1"),"masses",low=2,high=2)
    l1,l2=numbers(opt.get("lengths","1,1"),"lengths",low=2,high=2)
    if min(m1,m2,l1,l2)<=0:raise LabError("质量和长度必须为正")
    g=float_opt(opt.get("g",9.81),"g",.0001,100)
    duration=float_opt(opt.get("time",32),"time",.05,120)
    samples=int_opt(opt.get("steps",2200),"steps",100,7000)
    delta=float_opt(opt.get("delta",1e-6),"delta",-0.2,.2)
    def f(_,v):
        t1,v1,t2,v2=v
        D=t2-t1
        s=math.sin(D); c=math.cos(D)
        den=m1+m2*s*s
        dt1=(m2*l1*v1*v1*s*c + m2*g*math.sin(t2)*c + m2*l2*v2*v2*s-(m1+m2)*g*math.sin(t1))/(l1*den)
        dt2=(-m2*l2*v2*v2*s*c + (m1+m2)*(g*math.sin(t1)*c-l1*v1*v1*s-g*math.sin(t2)))/(l2*den)
        return [v1,dt1,v2,dt2]
    state=np.array([math.radians(theta1),w1,math.radians(theta2),w2])
    times=np.linspace(0,duration,samples)
    configs=[state,state+np.array([delta,0,0,0])]
    paths=[]
    for initial in configs:
        sol=solve_ivp(f,(0,duration),initial,t_eval=times,method="DOP853",rtol=2e-7,atol=2e-9)
        if not sol.success:raise LabError("双摆数值积分失败："+sol.message)
        x=l1*np.sin(sol.y[0])+l2*np.sin(sol.y[2])
        y=-l1*np.cos(sol.y[0])-l2*np.cos(sol.y[2])
        paths.append((x,y))
    fig,ax=plt.subplots(figsize=(8,7),dpi=105)
    try:
        for path,label in zip(paths,("initial","perturbed")):
            ax.plot(*path,lw=.9,label=label)
        ax.set_aspect("equal",adjustable="box");ax.legend();ax.grid(alpha=.2)
        ax.set_title("Double pendulum | nonlinear Lagrange equations")
        ax.set_xlabel("x");ax.set_ylabel("y");fig.tight_layout()
        out=_out(output_dir,"pendulum");fig.savefig(out)
    finally:plt.close(fig)
    dist=math.hypot(paths[0][0][-1]-paths[1][0][-1],paths[0][1][-1]-paths[1][1][-1])
    return out,(f"双摆 Lagrange 方程、DOP853 积分：m={m1:g},{m2:g} kg；l={l1:g},{l2:g} m；"
                f"g={g:g} m/s²；θ₀={theta1:g}°, {theta2:g}°；ω₀={w1:g},{w2:g} rad/s；"
                f"初始扰动 {delta:g} rad；运行 {duration:g}s，末端双轨迹距离≈{dist:.5g}m。")


def sir_general(output_dir:Path,opt:dict):
    from scipy.integrate import solve_ivp
    plt=_plt()
    R0=float_opt(opt.get("r0",2.5),"r0",.01,20)
    infectious=float_opt(opt.get("infectious",7),"infectious",.05,365)
    init=np.array(numbers(opt.get("init",".999,.001,0"),"init S,I,R",low=3,high=3))
    if min(init)<0 or abs(sum(init)-1)>1e-6:raise LabError("S,I,R 初值必须非负且和为 1")
    duration=float_opt(opt.get("time",160),"time",1,1000)
    steps=int_opt(opt.get("steps",1400),"steps",100,6000)
    gamma=1/infectious
    beta=R0*gamma
    def f(_,s):
        S,I,R=s
        return [-beta*S*I, beta*S*I-gamma*I, gamma*I]
    times=np.linspace(0,duration,steps)
    sol=solve_ivp(f,(0,duration),init,t_eval=times,rtol=1e-8,atol=1e-10)
    if not sol.success:raise LabError("SIR 积分失败")
    fig,ax=plt.subplots(figsize=(9,6),dpi=110)
    try:
        for row,key in zip(sol.y,("susceptible S","infected I","recovered R")):
            ax.plot(times,row,label=key)
        ax.set_xlabel("days");ax.set_ylabel("fraction")
        ax.set_ylim(0,1.02);ax.grid(alpha=.2);ax.legend()
        ax.set_title(f"SIR | R0={R0:g}, infectious={infectious:g} days")
        fig.tight_layout();path=_out(output_dir,"sir");fig.savefig(path)
    finally:plt.close(fig)
    idx=int(np.argmax(sol.y[1]))
    return path,(f"经典 SIR 常微分方程求解；R0={R0:g}，感染期={infectious:g} 天，"
                 f"初值 {init.tolist()}，β={beta:.6g}，γ={gamma:.6g}，"
                 f"峰值 I={sol.y[1,idx]:.4%}，第 {times[idx]:.3g} 天。教学模型，不代表真实疫情预测。")


def predator_general(output_dir:Path,opt:dict):
    from scipy.integrate import solve_ivp
    plt=_plt()
    alpha=float_opt(opt.get("alpha",1.1),"alpha",0,20)
    beta=float_opt(opt.get("beta",.4),"beta",0,20)
    gamma=float_opt(opt.get("gamma",.4),"gamma",0,20)
    delta=float_opt(opt.get("delta",.1),"delta",0,20)
    K=float_opt(opt.get("capacity",1e6),"capacity",.001,1e10)
    init=numbers(opt.get("init","10,5"),"init prey,predator",low=2,high=2)
    if min(init)<0:raise LabError("初始种群数量非负")
    duration=float_opt(opt.get("time",50),"time",.01,400)
    steps=int_opt(opt.get("steps",1700),"steps",100,6000)
    def f(_,s):
        x,y=s
        return [alpha*x*(1-x/K)-beta*x*y,delta*x*y-gamma*y]
    times=np.linspace(0,duration,steps)
    sol=solve_ivp(f,(0,duration),init,t_eval=times,rtol=1e-7,atol=1e-9)
    if not sol.success or not np.isfinite(sol.y).all() or np.max(sol.y)>1e8:
        raise LabError("捕食模型积分失败或发散")
    fig,axes=plt.subplots(1,2,figsize=(11,5.5),dpi=100)
    try:
        axes[0].plot(*sol.y);axes[0].set_xlabel("prey");axes[0].set_ylabel("predator")
        axes[1].plot(times,sol.y[0],label="prey")
        axes[1].plot(times,sol.y[1],label="predator")
        axes[1].legend();axes[1].set_xlabel("time")
        axes[0].grid(alpha=.2);axes[1].grid(alpha=.2)
        fig.suptitle("Lotka-Volterra with optional logistic carrying capacity")
        fig.tight_layout();path=_out(output_dir,"predator");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"数值求解 dx/dt=αx(1−x/K)−βxy；dy/dt=δxy−γy；"
                 f"α={alpha:g},β={beta:g},δ={delta:g},γ={gamma:g}，"
                 f"K={K:g}，初值={init}，t={duration:g}。")


def replicator_general(output_dir:Path,opt:dict):
    from scipy.integrate import solve_ivp
    plt=_plt()
    if "matrix" in opt:
        rows=[numbers(line,"payoff row",low=2,high=6) for line in opt["matrix"].split(";")]
        if not 2<=len(rows)<=6 or any(len(r)!=len(rows) for r in rows):
            raise LabError("复制子动力学收益矩阵必须是 2..6 阶方阵")
        A=np.array(rows,dtype=float)
    else:
        bias=float_opt(opt.get("bias",0),"bias",-5,5)
        A=np.array([[bias,-1,1],[1,bias,-1],[-1,1,bias]],float)
    n=A.shape[0]
    init=np.array(numbers(opt.get("init",",".join(["1"]*n)),"init",low=n,high=n))
    if np.any(init<0) or init.sum()<=0:raise LabError("init 必须是非负的策略频率")
    init/=init.sum()
    duration=float_opt(opt.get("time",80),"time",.1,200)
    steps=int_opt(opt.get("steps",2200),"steps",100,7000)
    def f(_,state):
        fitness=A@state
        return state*(fitness-state@fitness)
    t=np.linspace(0,duration,steps)
    sol=solve_ivp(f,(0,duration),init,t_eval=t,rtol=1e-8,atol=1e-10)
    if not sol.success or not np.isfinite(sol.y).all():raise LabError("复制子动力学积分失败")
    fig,ax=plt.subplots(figsize=(9,6),dpi=110)
    try:
        for i,y in enumerate(sol.y):ax.plot(t,y,label=f"strategy {i+1}")
        ax.set_ylim(-.01,1.01);ax.set_xlabel("time");ax.set_ylabel("strategy frequency")
        ax.legend();ax.grid(alpha=.2);ax.set_title(f"Replicator dynamics | {n} strategies")
        fig.tight_layout();path=_out(output_dir,"replicator");fig.savefig(path)
    finally:plt.close(fig)
    return path,(f"真实求解 {n} 策略复制子方程 dxᵢ/dt=xᵢ[(Ax)ᵢ−xᵀAx]；"
                 f"收益矩阵={A.tolist()}，初始频率={init.round(5).tolist()}，"
                 f"末态={sol.y[:,-1].round(5).tolist()}，t={duration:g}。")


def lissajous_general(output_dir:Path,opt:dict):
    from .visual_lab_analytic import parametric_plot
    fa=float_opt(opt.get("fx",3),"fx",.001,1000)
    fb=float_opt(opt.get("fy",2),"fy",.001,1000)
    phase=float_opt(opt.get("phase",90),"phase",-360,360)
    # Delegates to the same real arbitrary parametric curve engine.
    raw={"x":f"sin({fa}*t+{phase}*pi/180)",
         "y":f"sin({fb}*t)",
         "range":"0,6.283185307179586","size":"3000"}
    for x in ("range","size"):
        if x in opt:raw[x]=opt[x]
    return parametric_plot(output_dir,raw)


def knot_general(output_dir:Path,opt:dict):
    from .visual_lab_analytic import parametric_plot
    name=opt.get("preset","torus")
    if {"x","y","z"}<=opt.keys():
        return parametric_plot(output_dir,{k:opt[k] for k in ("x","y","z","range","size") if k in opt})
    p=int_opt(opt.get("p",2),"p",1,20)
    q=int_opt(opt.get("q",3),"q",1,20)
    if name in {"torus","trefoil"}:
        if name=="trefoil":p,q=2,3
        expressions={"x":f"(2+0.7*cos({q}*t))*cos({p}*t)",
                     "y":f"(2+0.7*cos({q}*t))*sin({p}*t)",
                     "z":f"0.7*sin({q}*t)"}
    elif name=="figure8":
        expressions={"x":"(2+cos(2*t))*cos(3*t)",
                     "y":"(2+cos(2*t))*sin(3*t)",
                     "z":"sin(4*t)"}
    else:raise LabError("knot 可选 torus/trefoil/figure8，或提供 --x --y --z 参数方程")
    path,caption=parametric_plot(output_dir,{**expressions,"range":"0,6.283185307179586","size":"3000"})
    return path,caption+f" 此处绘制 {name} 参数曲线（p={p},q={q}），未计算结不变量，不作结类型认证。"
