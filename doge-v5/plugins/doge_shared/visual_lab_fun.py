from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class FunLabError(ValueError):
    pass


def _font(size: int):
    for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _title(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    w = min(img.width - 18, 30 + max(330, len(text) * 12))
    d.rounded_rectangle((16, 14, w, 57), radius=11, fill=(250, 250, 248))
    d.text((29, 25), text, fill=(22, 22, 26), font=_font(18))


def _out(output_dir: Path, stem: str, suffix: str = ".png") -> Path:
    d = Path(output_dir) / "lab"
    d.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(stem.encode()).hexdigest()[:12]
    return d / f"{stem}-{token}{suffix}"


def _life_rule(rule: str) -> tuple[frozenset[int], frozenset[int], str]:
    text = str(rule or "B3/S23").upper().replace(" ", "")
    # Accept both B3/S23 and 23/3 shorthand, but report one canonical form.
    m = re.fullmatch(r"B([0-8]*)/S([0-8]*)", text)
    if not m:
        short = re.fullmatch(r"([0-8]*)/([0-8]*)", text)
        if short:
            text = f"B{short.group(2)}/S{short.group(1)}"
            m = re.fullmatch(r"B([0-8]*)/S([0-8]*)", text)
    if not m:
        raise FunLabError("life rule 用 B3/S23 形式（也接受 23/3）；邻居数只能是 0..8")
    birth = frozenset(int(x) for x in m.group(1))
    survive = frozenset(int(x) for x in m.group(2))
    return birth, survive, f"B{''.join(str(x) for x in sorted(birth))}/S{''.join(str(x) for x in sorted(survive))}"


def _life_rle_points(source: str) -> list[tuple[int, int]]:
    raw = str(source or "").strip()
    if raw.lower().startswith("rle:"):
        raw = raw[4:]
    # A pasted one-line RLE header may be included. Keep only the body after it.
    if "!" not in raw:
        raise FunLabError("自定义 RLE 需要以 ! 结束，例如 rle:bo$2bo$3o!")
    if "=" in raw and "\n" in raw:
        raw = "".join(line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#") and "=" not in line)
    raw = re.sub(r"\s+", "", raw)
    points: list[tuple[int, int]] = []
    x = y = run = 0
    for ch in raw:
        if ch.isdigit():
            run = run * 10 + int(ch)
            if run > 10000:
                raise FunLabError("RLE run length 过大")
            continue
        n = run or 1
        run = 0
        if ch in "bB":
            x += n
        elif ch in "oO":
            for dx in range(n):
                points.append((y, x + dx))
                if len(points) > 12000:
                    raise FunLabError("RLE 活细胞过多")
            x += n
        elif ch == "$":
            y += n; x = 0
        elif ch == "!":
            break
        else:
            raise FunLabError(f"RLE 含未知字符 {ch!r}")
    if not points:
        raise FunLabError("RLE 没有活细胞")
    return points


def _life_coord_points(source: str) -> list[tuple[int, int]]:
    raw = str(source or "").strip()
    if raw.lower().startswith("cells:"):
        raw = raw[6:]
    pts: list[tuple[int, int]] = []
    for item in raw.split(";"):
        if not item:
            continue
        try:
            x_s, y_s = item.split(",", 1)
            x, y = int(x_s), int(y_s)
        except Exception as exc:
            raise FunLabError("cells 格式为 cells:x,y;x,y;...，坐标相对中心") from exc
        pts.append((y, x))
        if len(pts) > 12000:
            raise FunLabError("自定义活细胞过多")
    if not pts:
        raise FunLabError("cells 没有活细胞")
    return pts


def _life_place(a: np.ndarray, points: list[tuple[int, int]], *, centered: bool = True) -> None:
    n = a.shape[0]
    ys = [p[0] for p in points]; xs = [p[1] for p in points]
    if centered:
        oy = n // 2 - (min(ys) + max(ys)) // 2
        ox = n // 2 - (min(xs) + max(xs)) // 2
    else:
        oy = ox = 0
    for y, x in points:
        yy, xx = y + oy, x + ox
        if not (0 <= yy < n and 0 <= xx < n):
            raise FunLabError("初始图样超出棋盘；请增大 size")
        a[yy, xx] = True


def _life_seed(kind: str, n: int, rng) -> tuple[np.ndarray, str]:
    a = np.zeros((n, n), dtype=bool)
    k = str(kind or "glider").strip()
    kl = k.lower()
    presets: dict[str, list[tuple[int, int]]] = {
        "glider": [(0,1),(1,2),(2,0),(2,1),(2,2)],
        "blinker": [(0,0),(0,1),(0,2)],
        "rpentomino": [(0,1),(0,2),(1,0),(1,1),(2,1)],
        "acorn": [(0,1),(1,3),(2,0),(2,1),(2,4),(2,5),(2,6)],
    }
    aliases = {"g":"glider", "a":"acorn", "blink":"blinker", "r-pentomino":"rpentomino", "r_pentomino":"rpentomino"}
    kl = aliases.get(kl, kl)
    if kl in presets:
        _life_place(a, presets[kl]); return a, kl
    if kl in {"gun", "gosper"}:
        points = [
            (5,1),(5,2),(6,1),(6,2),
            (5,11),(6,11),(7,11),(4,12),(8,12),(3,13),(9,13),(3,14),(9,14),
            (6,15),(4,16),(8,16),(5,17),(6,17),(7,17),(6,18),
            (3,21),(4,21),(5,21),(3,22),(4,22),(5,22),(2,23),(6,23),(1,25),(2,25),(6,25),(7,25),
            (3,35),(4,35),(3,36),(4,36),
        ]
        _life_place(a, points); return a, "gun"
    if kl in {"random", "r"}:
        box = min(56, n - 12); y0=n//2-box//2; x0=n//2-box//2
        a[y0:y0+box,x0:x0+box] = rng.random((box,box)) < .28
        return a, "random"
    if kl.startswith("rle:"):
        _life_place(a, _life_rle_points(k)); return a, "custom-rle"
    if kl.startswith("cells:"):
        # cells coordinates are intentionally relative to the board centre.
        pts = _life_coord_points(k)
        cy = cx = n // 2
        for y, x in pts:
            yy, xx = cy + y, cx + x
            if not (0 <= yy < n and 0 <= xx < n):
                raise FunLabError("cells 坐标超出棋盘；请增大 size")
            a[yy, xx] = True
        return a, "custom-cells"
    raise FunLabError("life 初态支持 glider / blinker / rpentomino / gun / acorn / random / rle:<RLE> / cells:x,y;...")


def _life_step(a: np.ndarray, birth=frozenset({3}), survive=frozenset({2,3}), boundary: str = "dead") -> np.ndarray:
    boundary = str(boundary or "dead").lower()
    u = a.astype(np.uint8)
    if boundary in {"wrap", "torus", "periodic"}:
        nb = sum(np.roll(np.roll(u, dy, axis=0), dx, axis=1) for dy in (-1,0,1) for dx in (-1,0,1) if (dy,dx)!=(0,0))
    elif boundary in {"dead", "fixed", "zero"}:
        p = np.pad(u, 1)
        nb = (
            p[:-2,:-2]+p[:-2,1:-1]+p[:-2,2:]+p[1:-1,:-2]+
            p[1:-1,2:]+p[2:,:-2]+p[2:,1:-1]+p[2:,2:]
        )
    else:
        raise FunLabError("life boundary 支持 dead / wrap")
    born = np.isin(nb, tuple(birth))
    kept = np.isin(nb, tuple(survive))
    return born | (a & kept)


def life_stateful(
    output_dir: Path,
    kind: str = "glider",
    steps: int = 120,
    rule: str = "B3/S23",
    boundary: str = "dead",
    size: int = 121,
    *,
    initial: np.ndarray | None = None,
    seed_label: str | None = None,
    generation_offset: int = 0,
) -> tuple[Path, str, np.ndarray, str, str]:
    """Run and render a Life-like CA, returning the exact final board for continuation."""
    steps = max(1, min(int(steps), 5000))
    birth, survive, rule_name = _life_rule(rule)
    boundary_name = {"torus":"wrap", "periodic":"wrap", "fixed":"dead", "zero":"dead"}.get(str(boundary).lower(), str(boundary).lower())
    if boundary_name not in {"dead", "wrap"}:
        raise FunLabError("life boundary 支持 dead / wrap")
    if initial is None:
        size = max(41, min(int(size) | 1, 301))
        rng = np.random.default_rng(20260831)
        a, resolved_label = _life_seed(kind, size, rng)
        seed_label = seed_label or resolved_label
    else:
        a = np.asarray(initial, dtype=bool).copy()
        if a.ndim != 2 or a.shape[0] != a.shape[1]:
            raise FunLabError("保存的 Life 棋盘不是方阵")
        size = int(a.shape[0])
        if not 41 <= size <= 301 or size % 2 == 0:
            raise FunLabError("保存的 Life 棋盘尺寸无效")
        seed_label = seed_label or "continued"
    initial_alive = int(a.sum())
    frame_count = min(72, max(2, min(steps + 1, 48 if steps <= 120 else 72)))
    marks = sorted(set(int(x) for x in np.linspace(0, steps, frame_count)))
    shots = {0: a.copy()}; wanted = set(marks)
    for t in range(1, steps + 1):
        a = _life_step(a, birth, survive, boundary_name)
        if t in wanted:
            shots[t] = a.copy()

    coords = []
    for arr in shots.values():
        yy, xx = np.nonzero(arr)
        if len(xx): coords.append((int(yy.min()), int(yy.max()), int(xx.min()), int(xx.max())))
    if coords:
        y0=max(0,min(v[0] for v in coords)-7); y1=min(size,max(v[1] for v in coords)+8)
        x0=max(0,min(v[2] for v in coords)-7); x1=min(size,max(v[3] for v in coords)+8)
    else:
        y0=x0=0; y1=x1=size
    h=max(1,y1-y0); w=max(1,x1-x0); side=max(h,w,18)
    cy=(y0+y1)//2; cx=(x0+x1)//2
    y0=max(0,min(max(0,size-side),cy-side//2)); x0=max(0,min(max(0,size-side),cx-side//2))
    y1=min(size,y0+side); x1=min(size,x0+side)

    panel=480; frames=[]; total_generation = int(generation_offset) + steps
    for idx,t in enumerate(marks,1):
        arr=shots[t][y0:y1,x0:x1]
        small=np.where(arr,24,246).astype(np.uint8)
        rgb=np.stack([small,small,small],axis=-1)
        board=Image.fromarray(rgb,"RGB").resize((panel,panel),Image.Resampling.NEAREST)
        canvas=Image.new("RGB",(panel+32,panel+92),(245,245,242)); canvas.paste(board,(16,68))
        absolute_generation = int(generation_offset) + t
        _title(canvas,f"Life · {seed_label} · {rule_name} · {boundary_name} · gen {absolute_generation}/{total_generation}")
        d=ImageDraw.Draw(canvas)
        d.text((22,panel+72),f"alive = {int(shots[t].sum())} · frame {idx}/{len(marks)}",fill=(75,75,82),font=_font(15))
        frames.append(canvas.convert("P",palette=Image.Palette.ADAPTIVE,colors=16))
    safe_rule=rule_name.replace('/','_')
    path=_out(output_dir,f"life-{seed_label}-{total_generation}-{size}-{safe_rule}-{boundary_name}",suffix=".gif")
    frames[0].save(path,save_all=True,append_images=frames[1:],format="GIF",duration=120,loop=0,disposal=2,optimize=True)
    caption=(
        f"Life-like CA GIF：初态 {seed_label}（本段起始 {initial_alive} cells），规则 {rule_name}，边界 {boundary_name}，"
        f"棋盘 {size}×{size}，本段真实模拟 {steps} 代，当前累计 generation {total_generation}，展示 {len(frames)} 帧。"
        "长模拟只减少 GIF 采样帧，不跳过任何演化代。当前最终棋盘可由 /lab life continue 接续。"
    )
    return path, caption, a.copy(), rule_name, boundary_name


def life(output_dir: Path, kind: str="glider", steps: int=120, rule: str="B3/S23", boundary: str="dead", size: int=121) -> tuple[Path,str]:
    """Backward-compatible stateless entrypoint; the plugin persists returned state."""
    path, caption, _board, _rule, _boundary = life_stateful(output_dir, kind, steps, rule, boundary, size)
    return path, caption


def _parse_life_cli(tokens: list[str]) -> tuple[str,int,str,str,int]:
    seed="glider"; steps=120; rule="B3/S23"; boundary="dead"; size=121
    rest=list(tokens)
    if rest and not any(rest[0].lower().startswith(k) for k in ("steps=","rule=","boundary=","size=")):
        seed=rest.pop(0)
    positional=[]
    for token in rest:
        low=token.lower()
        if low.startswith("steps="): steps=int(token.split("=",1)[1])
        elif low.startswith("rule="): rule=token.split("=",1)[1]
        elif low.startswith("boundary="): boundary=token.split("=",1)[1]
        elif low.startswith("size="): size=int(token.split("=",1)[1])
        else: positional.append(token)
    if positional:
        steps=int(positional.pop(0))
    if positional:
        rule=positional.pop(0)
    if positional:
        boundary=positional.pop(0)
    if positional:
        size=int(positional.pop(0))
    if positional:
        raise FunLabError("life 参数过多")
    return seed,steps,rule,boundary,size

def dla(output_dir: Path, particles: int=850, size: int=321) -> tuple[Path,str]:
    particles=max(80,min(int(particles),2200)); size=max(181,min(int(size)|1,451)); c=size//2
    grid=np.zeros((size,size),dtype=bool); age=np.full((size,size),-1,dtype=np.int32); grid[c,c]=1; age[c,c]=0
    rng=np.random.default_rng(20260831); radius=2.0; attached=1
    dirs=np.array([[1,0],[-1,0],[0,1],[0,-1]],dtype=np.int16)
    max_radius=size/2-8
    for k in range(1,particles):
        launch=min(max(radius+8,12),max_radius-3); kill=min(launch+26,max_radius)
        th=rng.random()*2*math.pi; y=int(round(c+launch*math.sin(th))); x=int(round(c+launch*math.cos(th)))
        for _ in range(26000):
            dy,dx=dirs[rng.integers(0,4)]; y+=int(dy); x+=int(dx)
            rr=(y-c)*(y-c)+(x-c)*(x-c)
            if y<2 or y>=size-2 or x<2 or x>=size-2 or rr>kill*kill:
                th=rng.random()*2*math.pi; y=int(round(c+launch*math.sin(th))); x=int(round(c+launch*math.cos(th))); continue
            if grid[y-1:y+2,x-1:x+2].any():
                # Do not occupy an already-filled site.
                if not grid[y,x]:
                    grid[y,x]=1; age[y,x]=k; attached+=1
                    radius=max(radius,math.sqrt(rr))
                break
        if radius>=max_radius-4: break
    yy,xx=np.indices(grid.shape); rr=np.sqrt((yy-c)**2+(xx-c)**2); crop=int(min(max(radius+9,45),size//2-2)); sub=age[c-crop:c+crop+1,c-crop:c+crop+1]
    mask=sub>=0; norm=np.zeros_like(sub,dtype=float); norm[mask]=sub[mask]/max(attached-1,1)
    rgb=np.full((*sub.shape,3),246,dtype=np.uint8)
    # Growth time runs from dark blue center to warm outer tips.
    rgb[...,0][mask]=(35+205*norm[mask]).astype(np.uint8)
    rgb[...,1][mask]=(70+80*(1-norm[mask])).astype(np.uint8)
    rgb[...,2][mask]=(165-105*norm[mask]).astype(np.uint8)
    img=Image.fromarray(rgb,"RGB").resize((820,820),Image.Resampling.NEAREST); _title(img,f"Diffusion-limited aggregation · {attached} particles")
    path=_out(output_dir,f"dla-{particles}-{size}"); img.save(path)
    return path,f"DLA：随机游走粒子一碰到团簇就粘住。颜色从中心到尖端表示生长先后；本次粘附 {attached} 个粒子。"


def beats(output_dir: Path, f1: float=9.0, f2: float=10.0, seconds: float=3.0) -> tuple[Path,str]:
    f1=float(f1); f2=float(f2); seconds=float(seconds)
    if not .2<=f1<=100 or not .2<=f2<=100: raise FunLabError("f1/f2 需在 0.2..100")
    if not .5<=seconds<=10: raise FunLabError("显示时长需在 0.5..10 秒")
    n=2400; t=np.linspace(0,seconds,n); y1=np.sin(2*np.pi*f1*t); y2=np.sin(2*np.pi*f2*t); y=y1+y2
    env=2*np.abs(np.cos(np.pi*(f2-f1)*t))
    img=Image.new("RGB",(1100,760),(250,250,247)); d=ImageDraw.Draw(img); _title(img,f"Beats · f₁={f1:g} Hz · f₂={f2:g} Hz · |Δf|={abs(f2-f1):g} Hz")
    left,right=55,1060
    # top: the two nearly-equal component waves
    d.text((60,78),"two component waves",fill=(30,30,35),font=_font(18))
    for arr,col in ((y1,(45,100,180)),(y2,(205,75,50))):
        pts=[(left+i/(n-1)*(right-left),235-arr[i]*105) for i in range(0,n,2)]; d.line(pts,fill=col,width=2)
    d.line((left,235,right,235),fill=(170,170,175),width=1)
    # bottom: sum + envelope; leave room for both ±2 envelope and caption.
    d.text((60,365),"sum and slow envelope",fill=(30,30,35),font=_font(18))
    center=545; amp=82
    pts=[(left+i/(n-1)*(right-left),center-y[i]*amp) for i in range(0,n,2)]; d.line(pts,fill=(80,70,155),width=2)
    up=[(left+i/(n-1)*(right-left),center-env[i]*amp) for i in range(0,n,3)]; lo=[(left+i/(n-1)*(right-left),center+env[i]*amp) for i in range(0,n,3)]
    d.line(up,fill=(215,145,35),width=3); d.line(lo,fill=(215,145,35),width=3); d.line((left,center,right,center),fill=(170,170,175),width=1)
    d.text((left,726),f"beat frequency = |f₂-f₁| = {abs(f2-f1):g} Hz",fill=(30,30,35),font=_font(20))
    path=_out(output_dir,f"beats-{f1:g}-{f2:g}-{seconds:g}"); img.save(path)
    return path,f"两个接近频率叠加后，快振荡被一个慢包络调制；拍频正好是 |f₂-f₁|={abs(f2-f1):g} Hz。"


def help_text() -> str:
    return (
        "  /lab life [seed] [steps] [rule] [dead|wrap] [size]    # animated GIF; seed 可为 glider/blinker/rpentomino/gun/acorn/random/rle:/cells:\n"
        "  /lab life continue [steps] [rule] [dead|wrap]          # 接着当前群/会话上一次最终棋盘继续演化\n"
        "  /lab life status | clear                               # 查看/清除当前群的保存状态\n"
        "  /lab dla [particles]\n"
        "  /lab beats [f1] [f2] [seconds]\n"
        + __import__("doge_v5.visual_lab_fun2", fromlist=["help_text"]).help_text()
    )


def render_fun(output_dir: Path, payload: str):
    parts=payload.strip().split()
    if not parts: return None
    h=parts[0].lower(); r=parts[1:]
    if h in {"life","conway"}: return life(output_dir,*_parse_life_cli(r))
    if h in {"dla","aggregate"}: return dla(output_dir,int(r[0]) if r else 850)
    if h in {"beats","beat"}: return beats(output_dir,float(r[0]) if r else 9,float(r[1]) if len(r)>1 else 10,float(r[2]) if len(r)>2 else 3)
    from .visual_lab_fun2 import render_fun2
    fun2 = render_fun2(output_dir, payload)
    if fun2 is not None:
        return fun2
    return None
