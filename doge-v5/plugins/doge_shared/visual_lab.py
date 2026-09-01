from __future__ import annotations

"""Lightweight scientific playground renderers for Doge v5.

The module intentionally uses only NumPy + Pillow, both already present in the
AstrBot runtime dependency graph.  It turns small numerical experiments into
PNG files that can be sent directly through NapCat/OneBot.

Algorithm/reference notes:
- logistic-map/bifurcation UX is inspired by gboeing/pynamical (MIT), but the
  renderer here is an independent NumPy implementation.
- elementary cellular automata follow the standard Wolfram rule convention;
  CellPyLib (Apache-2.0) was used as a behavioural reference.
- Penrose thin/thick triangle subdivision is adapted from samm00/penrose
  (MIT, Copyright (c) 2020 samm00) and re-rendered with Pillow instead of Cairo.
- modular multiplication circles are adapted conceptually from
  roberto-aldera/modular-multiplication-circles (MIT, Copyright (c) 2021
  Roberto Aldera), with a new Pillow renderer.
- Gray-Scott presets/equations follow the classic Pearson model and were
  cross-checked against wigging/gray-scott examples.
"""

import colorsys
import math
import uuid
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class LabError(ValueError):
    pass


W = 800
H = 800


def _out(output_dir: Path, prefix: str) -> Path:
    output_dir = Path(output_dir) / "lab"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{prefix}-{uuid.uuid4().hex[:12]}.png"


def _font(size: int = 24):
    for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _title(img: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((16, 14, min(img.width - 16, 28 + 16 * len(text)), 58), radius=10, fill=(255, 255, 255, 220))
    draw.text((30, 24), text, fill=(20, 20, 24), font=_font(22))


def _heat_rgb(v: np.ndarray) -> np.ndarray:
    """Small dependency-free perceptual-ish heat palette, v in [0,1]."""
    v = np.clip(v, 0.0, 1.0)
    r = np.clip(1.5 - np.abs(4.0 * v - 3.0), 0, 1)
    g = np.clip(1.5 - np.abs(4.0 * v - 2.0), 0, 1)
    b = np.clip(1.5 - np.abs(4.0 * v - 1.0), 0, 1)
    return (255 * np.stack([r, g, b], axis=-1)).astype(np.uint8)


def mandelbrot(output_dir: Path, cx: float = -0.75, cy: float = 0.0, zoom: float = 1.0) -> tuple[Path, str]:
    zoom = max(0.2, min(float(zoom), 1e5))
    width = height = 720
    span_x = 3.4 / zoom
    span_y = span_x
    xs = np.linspace(cx - span_x / 2, cx + span_x / 2, width, dtype=np.float64)
    ys = np.linspace(cy - span_y / 2, cy + span_y / 2, height, dtype=np.float64)
    c = xs[None, :] + 1j * ys[:, None]
    z = np.zeros_like(c)
    escaped = np.zeros(c.shape, dtype=np.uint16)
    active = np.ones(c.shape, dtype=bool)
    max_iter = 120
    for i in range(1, max_iter + 1):
        z[active] = z[active] * z[active] + c[active]
        newly = active & (np.abs(z) > 2.0)
        escaped[newly] = i
        active[newly] = False
        if not active.any():
            break
    v = np.log1p(escaped.astype(np.float32)) / math.log1p(max_iter)
    rgb = _heat_rgb(v)
    rgb[escaped == 0] = (4, 5, 10)
    img = Image.fromarray(rgb, "RGB")
    _title(img, f"Mandelbrot · center=({cx:g},{cy:g}) · zoom={zoom:g}×")
    path = _out(output_dir, "mandelbrot")
    img.save(path)
    return path, "Mandelbrot 集：黑色区域在给定迭代次数内未逃逸；边界对初值具有无限细节。"


def julia(output_dir: Path, cr: float = -0.8, ci: float = 0.156, zoom: float = 1.0) -> tuple[Path, str]:
    zoom = max(0.3, min(float(zoom), 1e4))
    width = height = 720
    span = 3.2 / zoom
    xs = np.linspace(-span / 2, span / 2, width)
    ys = np.linspace(-span / 2, span / 2, height)
    z = xs[None, :] + 1j * ys[:, None]
    c = complex(cr, ci)
    escaped = np.zeros(z.shape, dtype=np.uint16)
    active = np.ones(z.shape, dtype=bool)
    max_iter = 120
    for i in range(1, max_iter + 1):
        z[active] = z[active] * z[active] + c
        newly = active & (np.abs(z) > 2.0)
        escaped[newly] = i
        active[newly] = False
        if not active.any():
            break
    v = np.log1p(escaped.astype(np.float32)) / math.log1p(max_iter)
    rgb = _heat_rgb(v)
    rgb[escaped == 0] = (3, 4, 9)
    img = Image.fromarray(rgb, "RGB")
    _title(img, f"Julia · c={cr:g}{ci:+g}i")
    path = _out(output_dir, "julia")
    img.save(path)
    return path, f"Julia 集 zₙ₊₁=zₙ²+c，c={cr:g}{ci:+g}i。改变 c 会改变连通性与形态。"


def bifurcation(output_dir: Path, rmin: float = 2.5, rmax: float = 4.0) -> tuple[Path, str]:
    rmin, rmax = float(rmin), float(rmax)
    if not (0 <= rmin < rmax <= 4.2):
        raise LabError("建议范围满足 0 <= rmin < rmax <= 4.2")
    width, height = 1000, 650
    r = np.linspace(rmin, rmax, width)
    x = np.full(width, 0.500123)
    for _ in range(900):
        x = r * x * (1 - x)
    canvas = np.full((height, width, 3), 248, dtype=np.uint8)
    for _ in range(180):
        x = r * x * (1 - x)
        yy = np.clip(((1 - x) * (height - 1)).astype(int), 0, height - 1)
        canvas[yy, np.arange(width)] = (12, 18, 26)
    img = Image.fromarray(canvas, "RGB")
    _title(img, f"Logistic map bifurcation · r∈[{rmin:g},{rmax:g}]")
    path = _out(output_dir, "bifurcation")
    img.save(path)
    return path, "Logistic map xₙ₊₁=r xₙ(1−xₙ)：从稳定点、倍周期分岔到混沌窗口。"


def _normalise_points(points: np.ndarray, width: int, height: int, margin: int = 55) -> list[tuple[float, float]]:
    p = np.asarray(points, dtype=float)
    lo = np.nanpercentile(p, 0.5, axis=0)
    hi = np.nanpercentile(p, 99.5, axis=0)
    span = np.maximum(hi - lo, 1e-9)
    scale = min((width - 2 * margin) / span[0], (height - 2 * margin) / span[1])
    q = (p - (lo + hi) / 2) * scale
    q[:, 0] += width / 2
    q[:, 1] = height / 2 - q[:, 1]
    return [tuple(x) for x in q]


def attractor(output_dir: Path, name: str = "lorenz") -> tuple[Path, str]:
    name = name.lower()
    if name == "lorenz":
        n, dt = 32000, 0.005
        s, r, b = 10.0, 28.0, 8.0 / 3.0
        x = np.empty((n, 3), dtype=float)
        x[0] = (0.1, 0.0, 0.0)
        for i in range(n - 1):
            a, y, z = x[i]
            x[i + 1] = x[i] + dt * np.array([s * (y - a), a * (r - z) - y, a * y - b * z])
        pts = x[2500:, [0, 2]]
        caption = "Lorenz attractor：确定性微分方程也会产生对初值高度敏感的奇异吸引子。"
    elif name == "rossler":
        n, dt = 50000, 0.008
        a, b, c = 0.2, 0.2, 5.7
        x = np.empty((n, 3), dtype=float)
        x[0] = (0.1, 0.0, 0.0)
        for i in range(n - 1):
            xx, y, z = x[i]
            x[i + 1] = x[i] + dt * np.array([-y - z, xx + a * y, b + z * (xx - c)])
        pts = x[5000:, [0, 1]]
        caption = "Rössler attractor：由扭转、拉伸与折叠形成的经典连续时间混沌。"
    elif name == "clifford":
        n = 180000
        a, b, c, d = -1.4, 1.6, 1.0, 0.7
        pts = np.empty((n, 2), dtype=float)
        xx = yy = 0.1
        for i in range(n):
            xx, yy = math.sin(a * yy) + c * math.cos(a * xx), math.sin(b * xx) + d * math.cos(b * yy)
            pts[i] = (xx, yy)
        pts = pts[1000:]
        caption = "Clifford attractor：二维迭代映射把简单三角函数折叠成复杂密度结构。"
    else:
        raise LabError("attractor 支持 lorenz / rossler / clifford")
    img = Image.new("RGB", (900, 780), (248, 248, 245))
    draw = ImageDraw.Draw(img)
    q = _normalise_points(pts[:: max(1, len(pts) // 26000)], img.width, img.height, 45)
    if name == "clifford":
        for i, p in enumerate(q):
            if i % 2 == 0:
                draw.point(p, fill=(28, 45, 76))
    else:
        for i in range(1, len(q), 80):
            seg = q[max(0, i - 80): i + 1]
            t = i / max(1, len(q))
            col = tuple(int(255 * v) for v in colorsys.hsv_to_rgb(0.62 - 0.5 * t, 0.65, 0.55))
            draw.line(seg, fill=col, width=1)
    _title(img, f"{name.title()} attractor")
    path = _out(output_dir, f"attractor-{name}")
    img.save(path)
    return path, caption


def cellular(output_dir: Path, rule: int = 30, steps: int = 420) -> tuple[Path, str]:
    rule = int(rule)
    steps = max(80, min(int(steps), 700))
    if not 0 <= rule <= 255:
        raise LabError("Wolfram elementary CA rule 必须在 0..255")
    width = min(2 * steps + 1, 1001)
    hist = np.zeros((steps, width), dtype=np.uint8)
    hist[0, width // 2] = 1
    table = np.array([(rule >> i) & 1 for i in range(8)], dtype=np.uint8)
    for t in range(1, steps):
        prev = hist[t - 1]
        idx = (np.roll(prev, 1) << 2) | (prev << 1) | np.roll(prev, -1)
        hist[t] = table[idx]
    rgb = np.where(hist[:, :, None] == 1, np.array([15, 19, 25], dtype=np.uint8), np.array([248, 248, 244], dtype=np.uint8))
    img = Image.fromarray(rgb.astype(np.uint8), "RGB")
    scale = min(3, max(1, 1000 // max(img.width, img.height)))
    img = img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)
    _title(img, f"Elementary cellular automaton · Rule {rule}")
    path = _out(output_dir, f"ca-{rule}")
    img.save(path)
    return path, f"Wolfram Rule {rule}：每个格子的下一状态只由自己与左右邻居决定。"


def ulam(output_dir: Path, size: int = 301) -> tuple[Path, str]:
    size = int(size)
    size = max(51, min(size, 501))
    if size % 2 == 0:
        size += 1
    max_n = size * size
    sieve = np.ones(max_n + 1, dtype=bool)
    sieve[:2] = False
    for p in range(2, int(max_n ** 0.5) + 1):
        if sieve[p]:
            sieve[p * p:max_n + 1:p] = False
    arr = np.full((size, size, 3), 249, dtype=np.uint8)
    x = y = size // 2
    n = 1
    dirs = ((1, 0), (0, -1), (-1, 0), (0, 1))
    length = 1
    d = 0
    if sieve[n]:
        arr[y, x] = (10, 10, 16)
    while n < max_n:
        for _ in range(2):
            dx, dy = dirs[d % 4]
            for _ in range(length):
                if n >= max_n:
                    break
                x += dx; y += dy; n += 1
                if 0 <= x < size and 0 <= y < size and sieve[n]:
                    arr[y, x] = (8, 18, 32)
            d += 1
        length += 1
    img = Image.fromarray(arr, "RGB").resize((900, 900), Image.Resampling.NEAREST)
    _title(img, f"Ulam prime spiral · 1…{max_n:,}")
    path = _out(output_dir, "ulam")
    img.save(path)
    return path, "Ulam 素数螺旋：把整数沿方形螺旋排布后，素数会意外形成明显的对角线结构。"


def modular_circle(output_dir: Path, multiplier: float = 2.0, points: int = 360) -> tuple[Path, str]:
    multiplier = float(multiplier)
    points = max(20, min(int(points), 900))
    img = Image.new("RGB", (900, 900), (249, 249, 246))
    draw = ImageDraw.Draw(img)
    cx = cy = 450
    radius = 390
    coords = []
    for i in range(points):
        th = 2 * math.pi * i / points - math.pi / 2
        coords.append((cx + radius * math.cos(th), cy + radius * math.sin(th)))
    for i in range(points):
        j = int(round((i * multiplier) % points)) % points
        hue = i / points
        rgb = tuple(int(255 * v) for v in colorsys.hsv_to_rgb(hue, 0.65, 0.68))
        draw.line((coords[i], coords[j]), fill=rgb, width=1)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(24, 28, 34), width=2)
    _title(img, f"Modular multiplication circle · ×{multiplier:g} mod {points}")
    path = _out(output_dir, "modcircle")
    img.save(path)
    return path, "模乘圆：把 n 连到 multiplier·n (mod N)，简单模运算会显现心形、星形等包络线。"


_LSYS = {
    "dragon": ("FX", {"X": "X+YF+", "Y": "-FX-Y"}, 90.0, 13),
    "hilbert": ("A", {"A": "+BF-AFA-FB+", "B": "-AF+BFB+FA-"}, 90.0, 6),
    "koch": ("F--F--F", {"F": "F+F--F+F"}, 60.0, 5),
    "plant": ("X", {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"}, 25.0, 5),
}


def lsystem(output_dir: Path, preset: str = "dragon", iterations: int | None = None) -> tuple[Path, str]:
    preset = preset.lower()
    if preset not in _LSYS:
        raise LabError("lsys 支持 dragon / hilbert / koch / plant")
    axiom, rules, angle, default_iter = _LSYS[preset]
    it = default_iter if iterations is None else max(1, min(int(iterations), 15))
    s = axiom
    for _ in range(it):
        s = "".join(rules.get(ch, ch) for ch in s)
        if len(s) > 1_200_000:
            raise LabError("展开结果过大，请降低 iterations")
    heading = -math.pi / 2
    turn = math.radians(angle)
    x = y = 0.0
    stack: list[tuple[float, float, float]] = []
    lines: list[tuple[float, float, float, float]] = []
    for ch in s:
        if ch in "FG":
            nx, ny = x + math.cos(heading), y + math.sin(heading)
            lines.append((x, y, nx, ny)); x, y = nx, ny
        elif ch == "f":
            x, y = x + math.cos(heading), y + math.sin(heading)
        elif ch == "+": heading += turn
        elif ch == "-": heading -= turn
        elif ch == "[": stack.append((x, y, heading))
        elif ch == "]" and stack: x, y, heading = stack.pop()
    if not lines:
        raise LabError("该 L-system 没有可绘制线段")
    arr = np.array([[a, b] for line in lines for a, b in ((line[0], line[1]), (line[2], line[3]))])
    lo = arr.min(axis=0); hi = arr.max(axis=0); span = np.maximum(hi - lo, 1e-9)
    scale = min(720 / span[0], 720 / span[1])
    ox = 400 - (lo[0] + hi[0]) * scale / 2
    oy = 400 - (lo[1] + hi[1]) * scale / 2
    img = Image.new("RGB", (800, 800), (248, 248, 244))
    draw = ImageDraw.Draw(img)
    for a, b, c, d in lines:
        draw.line((a * scale + ox, b * scale + oy, c * scale + ox, d * scale + oy), fill=(25, 38, 35), width=1)
    _title(img, f"L-system · {preset} · iteration {it}")
    path = _out(output_dir, f"lsys-{preset}")
    img.save(path)
    return path, f"L-system {preset}：局部字符串替换规则反复迭代后形成自相似几何。"


def penrose(output_dir: Path, divisions: int = 7) -> tuple[Path, str]:
    divisions = max(1, min(int(divisions), 9))
    phi = (5 ** 0.5 + 1) / 2
    triangles: list[tuple[str, complex, complex, complex]] = []
    for i in range(10):
        v2 = complex(math.cos((2 * i - 1) * math.pi / 10), math.sin((2 * i - 1) * math.pi / 10))
        v3 = complex(math.cos((2 * i + 1) * math.pi / 10), math.sin((2 * i + 1) * math.pi / 10))
        if i % 2 == 0:
            v2, v3 = v3, v2
        triangles.append(("thin", 0j, v2, v3))
    for _ in range(divisions):
        nxt = []
        for shape, v1, v2, v3 in triangles:
            if shape == "thin":
                p1 = v1 + (v2 - v1) / phi
                nxt.extend([("thin", v3, p1, v2), ("thick", p1, v3, v1)])
            else:
                p2 = v2 + (v1 - v2) / phi
                p3 = v2 + (v3 - v2) / phi
                nxt.extend([("thick", p3, v3, v1), ("thick", p2, p3, v2), ("thin", p3, p2, v1)])
        triangles = nxt
    img = Image.new("RGB", (900, 900), (245, 244, 239))
    draw = ImageDraw.Draw(img)
    scale, cx, cy = 420, 450, 450
    for shape, a, b, c in triangles:
        pts = [(cx + p.real * scale, cy + p.imag * scale) for p in (a, b, c)]
        fill = (58, 103, 112) if shape == "thin" else (210, 166, 92)
        draw.polygon(pts, fill=fill)
        draw.line(pts + [pts[0]], fill=(28, 30, 32), width=1)
    _title(img, f"Penrose tiling · subdivision {divisions}")
    path = _out(output_dir, "penrose")
    img.save(path)
    return path, "Penrose 非周期铺砌：具有五重局部对称，却不存在平移周期。"


def interference(output_dir: Path, separation: float = 1.0, wavelength: float = 0.35) -> tuple[Path, str]:
    separation = max(0.05, min(float(separation), 3.0))
    wavelength = max(0.05, min(float(wavelength), 2.0))
    n = 720
    x = np.linspace(-4.0, 4.0, n)
    y = np.linspace(-3.0, 3.0, n)
    X, Y = np.meshgrid(x, y)
    r1 = np.sqrt((X - separation / 2) ** 2 + Y ** 2) + 1e-6
    r2 = np.sqrt((X + separation / 2) ** 2 + Y ** 2) + 1e-6
    k = 2 * math.pi / wavelength
    amp = np.cos(k * r1) / np.sqrt(r1) + np.cos(k * r2) / np.sqrt(r2)
    inten = amp * amp
    inten = np.log1p(inten)
    inten /= max(float(inten.max()), 1e-9)
    rgb = _heat_rgb(inten)
    img = Image.fromarray(rgb, "RGB")
    draw = ImageDraw.Draw(img)
    sx = lambda xx: int((xx + 4.0) / 8.0 * n)
    sy = lambda yy: int((3.0 - yy) / 6.0 * n)
    for xx in (-separation / 2, separation / 2):
        px, py = sx(xx), sy(0)
        draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill=(255, 255, 255), outline=(20, 20, 20))
    _title(img, f"Two-source interference · d={separation:g}, λ={wavelength:g}")
    path = _out(output_dir, "interference")
    img.save(path)
    return path, "双相干点源干涉：亮暗条纹来自两路波程差导致的相长与相消。"


def electric_field(output_dir: Path, preset: str = "dipole") -> tuple[Path, str]:
    preset = preset.lower()
    if preset == "dipole":
        charges = [(-0.8, 0.0, 1.0), (0.8, 0.0, -1.0)]
    elif preset == "quadrupole":
        charges = [(-0.8, -0.8, 1.0), (0.8, 0.8, 1.0), (-0.8, 0.8, -1.0), (0.8, -0.8, -1.0)]
    elif preset == "triple":
        charges = [(-0.9, -0.3, 1.0), (0.9, -0.3, 1.0), (0.0, 0.8, -1.0)]
    else:
        raise LabError("field 支持 dipole / quadrupole / triple")
    n = 600
    x = np.linspace(-2.5, 2.5, n)
    y = np.linspace(-2.5, 2.5, n)
    X, Y = np.meshgrid(x, y)
    V = np.zeros_like(X)
    for qx, qy, q in charges:
        R = np.sqrt((X - qx) ** 2 + (Y - qy) ** 2 + 0.015)
        V += q / R
    norm = 0.5 + 0.5 * np.tanh(V / 2.0)
    rgb = _heat_rgb(norm) // 2 + 110
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").resize((800, 800))
    draw = ImageDraw.Draw(img)
    for gy in np.linspace(-2.2, 2.2, 21):
        for gx in np.linspace(-2.2, 2.2, 21):
            ex = ey = 0.0
            for qx, qy, q in charges:
                dx, dy = gx - qx, gy - qy
                r2 = dx * dx + dy * dy + 0.02
                f = q / (r2 ** 1.5)
                ex += f * dx; ey += f * dy
            mag = math.hypot(ex, ey)
            if mag < 1e-9: continue
            ex /= mag; ey /= mag
            px = int((gx + 2.5) / 5 * 800); py = int((2.5 - gy) / 5 * 800)
            L = 11
            draw.line((px - ex * L, py + ey * L, px + ex * L, py - ey * L), fill=(20, 22, 25), width=1)
    for qx, qy, q in charges:
        px = int((qx + 2.5) / 5 * 800); py = int((2.5 - qy) / 5 * 800)
        fill = (245, 245, 245) if q > 0 else (20, 20, 25)
        draw.ellipse((px - 10, py - 10, px + 10, py + 10), fill=fill, outline=(20, 20, 25), width=2)
        draw.text((px - 5, py - 10), "+" if q > 0 else "−", fill=(20, 20, 25) if q > 0 else (250, 250, 250), font=_font(18))
    _title(img, f"Electrostatic field · {preset}")
    path = _out(output_dir, f"field-{preset}")
    img.save(path)
    return path, "背景表示电势，短线表示归一化电场方向；正负电荷共同塑造场的拓扑。"


def _double_pendulum_deriv(s: np.ndarray) -> np.ndarray:
    t1, w1, t2, w2 = s
    g = 9.81; m1 = m2 = 1.0; l1 = l2 = 1.0
    d = t2 - t1
    den1 = (m1 + m2) * l1 - m2 * l1 * math.cos(d) ** 2
    a1 = (m2 * l1 * w1 * w1 * math.sin(d) * math.cos(d) + m2 * g * math.sin(t2) * math.cos(d) + m2 * l2 * w2 * w2 * math.sin(d) - (m1 + m2) * g * math.sin(t1)) / den1
    den2 = (l2 / l1) * den1
    a2 = (-m2 * l2 * w2 * w2 * math.sin(d) * math.cos(d) + (m1 + m2) * (g * math.sin(t1) * math.cos(d) - l1 * w1 * w1 * math.sin(d) - g * math.sin(t2))) / den2
    return np.array([w1, a1, w2, a2])


def _rk4(s: np.ndarray, dt: float) -> np.ndarray:
    k1 = _double_pendulum_deriv(s)
    k2 = _double_pendulum_deriv(s + dt * k1 / 2)
    k3 = _double_pendulum_deriv(s + dt * k2 / 2)
    k4 = _double_pendulum_deriv(s + dt * k3)
    return s + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6


def double_pendulum(output_dir: Path, theta_deg: float = 120.0) -> tuple[Path, str]:
    theta = math.radians(float(theta_deg))
    a = np.array([theta, 0.0, math.radians(-10), 0.0])
    b = a.copy(); b[0] += 1e-6
    pa, pb = [], []
    dt = 0.01
    for i in range(6500):
        a = _rk4(a, dt); b = _rk4(b, dt)
        if i % 2 == 0:
            pa.append((math.sin(a[0]) + math.sin(a[2]), -(math.cos(a[0]) + math.cos(a[2]))))
            pb.append((math.sin(b[0]) + math.sin(b[2]), -(math.cos(b[0]) + math.cos(b[2]))))
    img = Image.new("RGB", (900, 800), (249, 249, 246))
    draw = ImageDraw.Draw(img)
    qa = _normalise_points(np.array(pa), 900, 800, 60)
    qb = _normalise_points(np.array(pb), 900, 800, 60)
    draw.line(qa, fill=(30, 75, 120), width=2)
    draw.line(qb, fill=(180, 70, 55), width=2)
    _title(img, "Double pendulum · Δθ₀ = 10⁻⁶ rad")
    path = _out(output_dir, "double-pendulum")
    img.save(path)
    return path, "两条轨迹初始角只差 10⁻⁶ rad；随后逐渐分离，直观看到经典力学中的敏感初值。"


def figure8(output_dir: Path) -> tuple[Path, str]:
    r = np.array([[-0.97000436, 0.24308753], [0.97000436, -0.24308753], [0.0, 0.0]], dtype=float)
    v = np.array([[0.466203685, 0.43236573], [0.466203685, 0.43236573], [-0.93240737, -0.86473146]], dtype=float)
    dt = 0.002
    trails = [[], [], []]
    def acc(pos):
        a = np.zeros_like(pos)
        for i in range(3):
            for j in range(3):
                if i == j: continue
                d = pos[j] - pos[i]
                rr = float(np.dot(d, d) + 1e-10)
                a[i] += d / (rr ** 1.5)
        return a
    a = acc(r)
    for step in range(8000):
        r = r + v * dt + 0.5 * a * dt * dt
        na = acc(r)
        v = v + 0.5 * (a + na) * dt
        a = na
        if step % 2 == 0:
            for i in range(3): trails[i].append(tuple(r[i]))
    img = Image.new("RGB", (900, 800), (249, 249, 246))
    draw = ImageDraw.Draw(img)
    allpts = np.vstack([np.array(t) for t in trails])
    lo, hi = allpts.min(axis=0), allpts.max(axis=0)
    span = np.maximum(hi - lo, 1e-9); scale = min(760 / span[0], 660 / span[1])
    center = (lo + hi) / 2
    cols = [(34, 82, 135), (180, 70, 55), (70, 125, 80)]
    for tr, col in zip(trails, cols):
        pts = [((x - center[0]) * scale + 450, 400 - (y - center[1]) * scale) for x, y in tr]
        draw.line(pts, fill=col, width=2)
    _title(img, "Equal-mass three-body figure-eight orbit")
    path = _out(output_dir, "threebody-figure8")
    img.save(path)
    return path, "三颗等质量天体存在著名的稳定八字形周期解：复杂三体问题并不意味着所有轨道都无结构。"


def grayscott(output_dir: Path, preset: str = "spots") -> tuple[Path, str]:
    preset = preset.lower()
    params = {
        "spots": (0.035, 0.065),
        "worms": (0.078, 0.061),
        "mitosis": (0.0367, 0.0649),
        "coral": (0.0545, 0.062),
    }
    if preset not in params:
        raise LabError("reaction 支持 spots / worms / mitosis / coral")
    F, k = params[preset]
    n = 160
    u = np.ones((n, n), dtype=np.float32)
    v = np.zeros((n, n), dtype=np.float32)
    rng = np.random.default_rng(42)
    s = 14
    u[n//2-s:n//2+s, n//2-s:n//2+s] = 0.50
    v[n//2-s:n//2+s, n//2-s:n//2+s] = 0.25
    v += rng.normal(0, 0.008, v.shape).astype(np.float32)
    Du, Dv = 0.16, 0.08
    for _ in range(2200):
        lap_u = -u + 0.2 * (np.roll(u,1,0)+np.roll(u,-1,0)+np.roll(u,1,1)+np.roll(u,-1,1)) + 0.05 * (np.roll(np.roll(u,1,0),1,1)+np.roll(np.roll(u,1,0),-1,1)+np.roll(np.roll(u,-1,0),1,1)+np.roll(np.roll(u,-1,0),-1,1))
        lap_v = -v + 0.2 * (np.roll(v,1,0)+np.roll(v,-1,0)+np.roll(v,1,1)+np.roll(v,-1,1)) + 0.05 * (np.roll(np.roll(v,1,0),1,1)+np.roll(np.roll(v,1,0),-1,1)+np.roll(np.roll(v,-1,0),1,1)+np.roll(np.roll(v,-1,0),-1,1))
        uvv = u * v * v
        u += Du * lap_u - uvv + F * (1 - u)
        v += Dv * lap_v + uvv - (F + k) * v
        np.clip(u, 0, 1.4, out=u); np.clip(v, 0, 1.4, out=v)
    vv = (v - v.min()) / max(float(v.max() - v.min()), 1e-9)
    rgb = _heat_rgb(vv)
    img = Image.fromarray(rgb, "RGB").resize((800, 800), Image.Resampling.LANCZOS)
    _title(img, f"Gray–Scott reaction–diffusion · {preset}")
    path = _out(output_dir, f"grayscott-{preset}")
    img.save(path)
    return path, "Gray–Scott 反应扩散：只有局部反应与扩散，却能自组织出斑点、虫纹、分裂等形态。"


def linear_map(output_dir: Path, a: float, b: float, c: float, d: float) -> tuple[Path, str]:
    M = np.array([[float(a), float(b)], [float(c), float(d)]], dtype=float)
    if float(np.max(np.abs(M))) > 20:
        raise LabError("矩阵元素绝对值请不要超过 20")
    img = Image.new("RGB", (900, 800), (249, 249, 246))
    draw = ImageDraw.Draw(img)
    # Generate the transformed Cartesian grid.
    curves = []
    t = np.linspace(-3, 3, 181)
    for k in np.linspace(-3, 3, 13):
        curves.append((np.stack([np.full_like(t, k), t], axis=1), (80, 130, 170)))
        curves.append((np.stack([t, np.full_like(t, k)], axis=1), (190, 105, 80)))
    transformed = [(p @ M.T, col) for p, col in curves]
    allp = np.vstack([p for p, _ in transformed] + [np.array([[-1,0],[1,0],[0,-1],[0,1]]) @ M.T])
    span = max(float(np.max(np.abs(allp))), 1.0)
    scale = 330 / span
    for p, col in transformed:
        pts = [(450 + x * scale, 420 - y * scale) for x, y in p]
        draw.line(pts, fill=col, width=1)
    eigvals, eigvecs = np.linalg.eig(M)
    for j in range(2):
        vec = np.real(eigvecs[:, j])
        nrm = np.linalg.norm(vec)
        if nrm > 1e-9:
            vec /= nrm
            L = 300
            draw.line((450 - vec[0]*L, 420 + vec[1]*L, 450 + vec[0]*L, 420 - vec[1]*L), fill=(25,25,28), width=3)
    _title(img, f"Linear map · [[{a:g},{b:g}],[{c:g},{d:g}]]")
    txt = "eigenvalues: " + ", ".join(f"{z:.3g}" for z in eigvals)
    draw.text((28, 748), txt, fill=(20,20,24), font=_font(22))
    path = _out(output_dir, "linear-map")
    img.save(path)
    return path, f"线性变换把整张坐标网格一起拉伸、剪切、旋转；特征值为 {', '.join(f'{z:.3g}' for z in eigvals)}。"


def help_text() -> str:
    return (
        "Doge Scientific Playground /lab\n"
        "  /lab fractal mandelbrot [cx cy zoom]\n"
        "  /lab fractal julia [c_re c_im zoom]\n"
        "  /lab chaos bifurcation [rmin rmax]\n"
        "  /lab attractor <lorenz|rossler|clifford>\n"
        "  /lab ca <0..255> [steps]\n"
        "  /lab number ulam [size]\n"
        "  /lab number mod <multiplier> [points]\n"
        "  /lab lsys <dragon|hilbert|koch|plant> [iterations]\n"
        "  /lab tiling penrose [depth]\n"
        "  /lab wave [separation wavelength]\n"
        "  /lab field <dipole|quadrupole|triple>\n"
        "  /lab pendulum [initial-angle-deg]\n"
        "  /lab orbit figure8\n"
        "  /lab reaction <spots|worms|mitosis|coral>\n"
        "  /lab linear <a b c d>\n"
        + __import__("doge_v5.visual_lab_extra", fromlist=["help_text"]).help_text()
    )


def render(output_dir: Path, payload: str) -> tuple[Path, str]:
    parts = payload.strip().split()
    if not parts:
        raise LabError(help_text())
    head = parts[0].lower()
    rest = parts[1:]
    if head == "fractal":
        if not rest: raise LabError("fractal 需要 mandelbrot 或 julia")
        kind, args = rest[0].lower(), rest[1:]
        if kind in {"mandelbrot", "mandel", "m"}:
            vals = [float(x) for x in args]
            defaults = [-0.75, 0.0, 1.0]
            vals += defaults[len(vals):]
            return mandelbrot(output_dir, *vals[:3])
        if kind in {"julia", "j"}:
            vals = [float(x) for x in args]
            defaults = [-0.8, 0.156, 1.0]
            vals += defaults[len(vals):]
            return julia(output_dir, *vals[:3])
        raise LabError("fractal 支持 mandelbrot / julia")
    if head == "chaos":
        if not rest or rest[0].lower() in {"bifurcation", "bif", "logistic"}:
            vals = [float(x) for x in rest[1:]] if rest else []
            return bifurcation(output_dir, *(vals + [2.5,4.0])[:2]) if vals else bifurcation(output_dir)
        raise LabError("chaos 当前支持 bifurcation")
    if head == "attractor": return attractor(output_dir, rest[0] if rest else "lorenz")
    if head == "ca": return cellular(output_dir, int(rest[0]) if rest else 30, int(rest[1]) if len(rest)>1 else 420)
    if head == "number":
        if not rest: raise LabError("number 支持 ulam / mod")
        kind = rest[0].lower(); args=rest[1:]
        if kind == "ulam": return ulam(output_dir, int(args[0]) if args else 301)
        if kind in {"mod", "circle", "modcircle"}: return modular_circle(output_dir, float(args[0]) if args else 2.0, int(args[1]) if len(args)>1 else 360)
        raise LabError("number 支持 ulam / mod")
    if head in {"lsys", "l-system"}: return lsystem(output_dir, rest[0] if rest else "dragon", int(rest[1]) if len(rest)>1 else None)
    if head == "tiling":
        if rest and rest[0].lower() != "penrose": raise LabError("tiling 当前支持 penrose")
        return penrose(output_dir, int(rest[1]) if len(rest)>1 else 7)
    if head == "wave": return interference(output_dir, float(rest[0]) if rest else 1.0, float(rest[1]) if len(rest)>1 else 0.35)
    if head == "field": return electric_field(output_dir, rest[0] if rest else "dipole")
    if head in {"pendulum", "doublependulum"}: return double_pendulum(output_dir, float(rest[0]) if rest else 120.0)
    if head == "orbit":
        if rest and rest[0].lower() not in {"figure8", "8", "threebody"}: raise LabError("orbit 当前支持 figure8")
        return figure8(output_dir)
    if head in {"reaction", "grayscott"}: return grayscott(output_dir, rest[0] if rest else "spots")
    if head == "linear":
        if len(rest) != 4: raise LabError("用法：/lab linear <a b c d>")
        return linear_map(output_dir, *[float(x) for x in rest])
    from .visual_lab_extra import render_extra
    extra = render_extra(output_dir, payload)
    if extra is not None:
        return extra
    raise LabError(help_text())
