from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path


class ScienceWrapperError(ValueError):
    pass


class ScienceExtraDependencyError(RuntimeError):
    pass


def _out(output_dir: Path, group: str, stem: str, suffix: str=".png") -> Path:
    d=Path(output_dir)/group; d.mkdir(parents=True,exist_ok=True)
    tok=hashlib.sha256(stem.encode()).hexdigest()[:12]
    return d/f"{stem}-{tok}{suffix}"


def _value(token: str) -> tuple[str,str]:
    if ":" in token:
        a,b=token.split(":",1); return a.upper(),b
    m=re.match(r"([A-Za-z]+)(.*)",token)
    if not m: raise ScienceWrapperError(f"无法识别元件 {token}")
    return m.group(1).upper(),m.group(2)


def circuit_help() -> str:
    return (
        "Doge Circuit /circuit\n"
        "  /circuit rc [R C]\n"
        "  /circuit rlc [R L C]\n"
        "  /circuit divider [R1 R2]\n"
        "  /circuit series V:5V R:1k C:10u GND\n"
        "series 支持 V/R/C/L/D/LED/GND；标签写在冒号后。"
    )


def render_circuit(output_dir: Path, payload: str) -> tuple[Path,str]:
    try:
        import schemdraw
        import schemdraw.elements as elm
    except Exception as exc:
        raise ScienceExtraDependencyError("电路图需要可选依赖 schemdraw + matplotlib") from exc
    import matplotlib
    matplotlib.use("Agg", force=True)
    schemdraw.use("matplotlib")
    parts=payload.strip().split()
    if not parts: raise ScienceWrapperError(circuit_help())
    mode=parts[0].lower(); args=parts[1:]
    path=_out(output_dir,"circuit",re.sub(r"[^a-zA-Z0-9_-]+","-",payload)[:90] or "circuit")
    d=schemdraw.Drawing(show=False)
    if mode=="rc":
        R=args[0] if args else "1 kΩ"; C=args[1] if len(args)>1 else "10 μF"
        d += elm.SourceV().up().label("V")
        d += elm.Resistor().right().label(R)
        d += elm.Capacitor().down().label(C)
        d += elm.Line().left(); d += elm.Ground()
        cap=f"RC 回路：R={R}, C={C}。"
    elif mode=="rlc":
        R=args[0] if args else "100 Ω"; L=args[1] if len(args)>1 else "10 mH"; C=args[2] if len(args)>2 else "1 μF"
        d += elm.SourceSin().up().label("Vin")
        d += elm.Resistor().right().label(R)
        d += elm.Inductor().right().label(L)
        d += elm.Capacitor().down().label(C)
        d += elm.Line().left().length(6); d += elm.Ground()
        cap=f"串联 RLC：R={R}, L={L}, C={C}。"
    elif mode in {"divider","div"}:
        r1=args[0] if args else "10 kΩ"; r2=args[1] if len(args)>1 else "10 kΩ"
        d += elm.SourceV().up().label("Vin")
        d += elm.Resistor().right().label(r1)
        d += elm.Dot().label("Vout",loc="right")
        d.push(); d += elm.Resistor().down().label(r2); d += elm.Ground(); d.pop()
        d += elm.Line().right().length(1)
        cap=f"分压器：R1={r1}, R2={r2}。"
    elif mode=="series":
        if not args: raise ScienceWrapperError("用法：/circuit series V:5V R:1k C:10u GND")
        elements={
            "R": lambda label: elm.Resistor().label(label or "R"),
            "C": lambda label: elm.Capacitor().label(label or "C"),
            "L": lambda label: elm.Inductor().label(label or "L"),
            "D": lambda label: elm.Diode().label(label or "D"),
            "LED": lambda label: elm.LED().label(label or "LED"),
            "V": lambda label: elm.SourceV().label(label or "V"),
        }
        for i,tok in enumerate(args):
            kind,label=_value(tok)
            if kind in {"GND","GROUND"}: d += elm.Ground(); continue
            factory=elements.get(kind)
            if not factory: raise ScienceWrapperError(f"series 暂不支持元件 {kind}")
            e=factory(label)
            if i==0 and kind=="V": e=e.up()
            else: e=e.right()
            d += e
        cap="自定义串联电路："+" ".join(args)
    else:
        raise ScienceWrapperError(circuit_help())
    d.save(str(path), dpi=180, transparent=False)
    return path,cap


def control_help() -> str:
    return (
        "Doge Control /control\n"
        "  /control bode <num coeffs> | <den coeffs>\n"
        "  /control step <num> | <den>\n"
        "  /control impulse <num> | <den>\n"
        "  /control nyquist <num> | <den>\n"
        "  /control root <num> | <den>\n"
        "例：/control bode 1 | 1 0.4 1"
    )


def _coeffs(text: str) -> list[float]:
    xs=[x for x in re.split(r"[\s,]+",text.strip()) if x]
    if not xs: raise ScienceWrapperError("传递函数系数不能为空")
    if len(xs)>12: raise ScienceWrapperError("多项式次数过高；每侧最多 12 个系数")
    vals=[float(x) for x in xs]
    if max(abs(x) for x in vals)>1e9: raise ScienceWrapperError("系数过大")
    return vals


def _parse_tf(payload: str):
    parts=payload.strip().split(None,1)
    if len(parts)<2 or "|" not in parts[1]: raise ScienceWrapperError(control_help())
    mode=parts[0].lower(); left,right=parts[1].split("|",1)
    return mode,_coeffs(left),_coeffs(right)


def render_control(output_dir: Path, payload: str) -> tuple[Path,str]:
    try:
        import control as ct
        import numpy as np
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise ScienceExtraDependencyError("控制系统图需要可选依赖 control + scipy + matplotlib") from exc
    mode,num,den=_parse_tf(payload)
    if not den or abs(den[0])<1e-15: raise ScienceWrapperError("分母最高次系数不能为 0")
    sys=ct.TransferFunction(num,den)
    fig,ax=plt.subplots(figsize=(8.5,6.2),dpi=145)
    title=f"G(s)=({','.join(f'{x:g}' for x in num)}) / ({','.join(f'{x:g}' for x in den)})"
    if mode=="bode":
        w=np.logspace(-2,2,700); resp=ct.frequency_response(sys,w); mag=np.asarray(resp.magnitude).squeeze(); phase=np.asarray(resp.phase).squeeze()
        ax.remove(); ax1=fig.add_subplot(211); ax2=fig.add_subplot(212,sharex=ax1)
        ax1.semilogx(w,20*np.log10(np.maximum(mag,1e-15))); ax1.set_ylabel("magnitude (dB)"); ax1.grid(True,which="both",alpha=.25)
        ax2.semilogx(w,np.unwrap(phase)*180/np.pi); ax2.set_ylabel("phase (deg)"); ax2.set_xlabel("rad/s"); ax2.grid(True,which="both",alpha=.25)
    elif mode in {"step","impulse"}:
        T=np.linspace(0,20,900)
        resp=ct.step_response(sys,T=T) if mode=="step" else ct.impulse_response(sys,T=T)
        ax.plot(np.asarray(resp.time).squeeze(),np.asarray(resp.outputs).squeeze()); ax.axhline(0,lw=.8); ax.grid(True,alpha=.25); ax.set_xlabel("time"); ax.set_ylabel("response")
    elif mode=="nyquist":
        w=np.logspace(-3,3,1200); r=ct.frequency_response(sys,w); z=np.asarray(r.frdata).squeeze()
        ax.plot(z.real,z.imag); ax.plot(z.real,-z.imag,ls="--",alpha=.55); ax.scatter([-1],[0],marker="x",s=80); ax.axhline(0,lw=.8); ax.axvline(0,lw=.8); ax.set_aspect("equal",adjustable="datalim"); ax.grid(True,alpha=.25); ax.set_xlabel("Re"); ax.set_ylabel("Im")
    elif mode in {"root","rlocus","rootlocus"}:
        gains=np.concatenate(([0.],np.logspace(-3,4,650))); data=ct.root_locus_map(sys,gains=gains); loci=np.asarray(data.loci)
        for j in range(loci.shape[1]): ax.plot(loci[:,j].real,loci[:,j].imag,lw=1.3)
        poles=np.asarray(sys.poles()); zeros=np.asarray(sys.zeros()); ax.scatter(poles.real,poles.imag,marker="x",s=80,label="poles");
        if len(zeros): ax.scatter(zeros.real,zeros.imag,facecolors="none",edgecolors="k",s=70,label="zeros")
        ax.axhline(0,lw=.8); ax.axvline(0,lw=.8); ax.grid(True,alpha=.25); ax.set_xlabel("Re(s)"); ax.set_ylabel("Im(s)"); ax.legend()
    else:
        plt.close(fig); raise ScienceWrapperError("control 支持 bode / step / impulse / nyquist / root")
    fig.suptitle(title,fontsize=11); fig.tight_layout(rect=(0,0,1,.95))
    path=_out(output_dir,"control",re.sub(r"[^a-zA-Z0-9_-]+","-",payload)[:100] or "control"); fig.savefig(path,bbox_inches="tight"); plt.close(fig)
    poles=[complex(x) for x in sys.poles()]
    stable=all(p.real<0 for p in poles) if poles else True
    return path,f"{mode} · poles={', '.join(f'{p:.3g}' for p in poles) or 'none'} · {'stable' if stable else 'not asymptotically stable'}"


def crystal_help() -> str:
    return (
        "Doge Crystal /crystal（请在同一条消息附带 .cif/.mcif 文件）\n"
        "  /crystal info\n"
        "  /crystal powder [energy_keV] [peak_width_deg]\n"
        "真实 CIF 计算由 Dans_Diffraction 完成；/lab xrd 则是快速教学模型。"
    )


def _validate_cif_path(cif_path: str | Path) -> Path:
    p=Path(cif_path).resolve()
    if not p.is_file(): raise ScienceWrapperError("没有拿到可读取的 CIF 文件")
    if p.suffix.lower() not in {".cif", ".mcif"}: raise ScienceWrapperError("只接受 .cif / .mcif")
    if p.stat().st_size > 2_000_000: raise ScienceWrapperError("CIF 文件过大；群聊入口限制为 2 MB")
    return p


def crystal_info(cif_path: str | Path) -> str:
    p=_validate_cif_path(cif_path)
    try:
        import Dans_Diffraction as dif
    except Exception as exc:
        raise ScienceExtraDependencyError("真实 CIF 功能需要可选依赖 Dans_Diffraction") from exc
    xtl=dif.Crystal(str(p))
    lp=[float(x) for x in xtl.Cell.lp()]
    volume=float(xtl.Cell.volume())
    name=str(getattr(xtl,"name",p.stem))
    return (
        f"{name}\n"
        f"a,b,c = {lp[0]:.5g}, {lp[1]:.5g}, {lp[2]:.5g} Å\n"
        f"alpha,beta,gamma = {lp[3]:.5g}, {lp[4]:.5g}, {lp[5]:.5g} deg\n"
        f"volume = {volume:.5g} Å^3"
    )


def render_crystal_powder(output_dir: Path, cif_path: str | Path, energy_kev: float=8.0, peak_width: float=.08) -> tuple[Path,str]:
    p=_validate_cif_path(cif_path); energy=float(energy_kev); width=float(peak_width)
    if not 1 <= energy <= 40: raise ScienceWrapperError("X-ray energy 请设为 1..40 keV")
    if not .005 <= width <= 2: raise ScienceWrapperError("peak_width 请设为 0.005..2 deg")
    try:
        import Dans_Diffraction as dif
        import numpy as np
        import matplotlib
        matplotlib.use("Agg",force=True)
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise ScienceExtraDependencyError("真实 CIF 衍射需要可选依赖 Dans_Diffraction + matplotlib") from exc
    xtl=dif.Crystal(str(p))
    # Directly use the library's structure factors / reflection handling, but draw our own compact group-chat figure.
    tth,intensity,refs=xtl.Scatter.powder(
        scattering_type="xray", units="twotheta", energy_kev=energy,
        peak_width=width, background=0, powder_average=True,
    )
    tth=np.asarray(tth,dtype=float).squeeze(); intensity=np.asarray(intensity,dtype=float).squeeze()
    if tth.size==0 or intensity.size==0: raise ScienceWrapperError("CIF 未产生可绘制的粉末衍射结果")
    mask=np.isfinite(tth)&np.isfinite(intensity)&(tth>=0)&(tth<=140)
    tth=tth[mask]; intensity=intensity[mask]
    if not len(tth): raise ScienceWrapperError("0..140° 范围没有衍射结果")
    intensity=intensity/max(float(np.max(intensity)),1e-15)*100
    fig,ax=plt.subplots(figsize=(9.0,5.6),dpi=150)
    ax.plot(tth,intensity,lw=1.25)
    ax.set_xlim(0,min(140,max(90,float(np.max(tth)))))
    ax.set_ylim(0,105); ax.set_xlabel("2-theta (deg)"); ax.set_ylabel("relative intensity")
    ax.grid(True,alpha=.16); ax.set_title(f"{getattr(xtl,'name',p.stem)} · powder XRD · {energy:g} keV")
    fig.tight_layout()
    out=_out(output_dir,"crystal",f"powder-{p.stem}-{energy:g}-{width:g}")
    fig.savefig(out,bbox_inches="tight"); plt.close(fig)
    lp=[float(x) for x in xtl.Cell.lp()]
    cap=(f"Dans_Diffraction CIF powder XRD · {getattr(xtl,'name',p.stem)} · "
         f"cell=({lp[0]:.4g},{lp[1]:.4g},{lp[2]:.4g}) Å · E={energy:g} keV")
    return out,cap
