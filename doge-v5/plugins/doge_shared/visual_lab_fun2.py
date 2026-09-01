from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class Fun2LabError(ValueError):
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
    w = min(img.width - 18, 30 + max(350, len(text) * 12))
    d.rounded_rectangle((16, 14, w, 57), radius=11, fill=(250, 250, 248))
    d.text((29, 25), text, fill=(22, 22, 26), font=_font(18))


def _out(output_dir: Path, stem: str) -> Path:
    d = Path(output_dir) / "lab"
    d.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(stem.encode()).hexdigest()[:12]
    return d / f"{stem}-{token}.png"


def chladni(output_dir: Path, m: int = 5, n: int = 3) -> tuple[Path, str]:
    m = max(1, min(int(m), 14)); n = max(1, min(int(n), 14))
    if m == n:
        raise Fun2LabError("Chladni 的两个模态序号请设成不同整数，例如 /lab chladni 5 3")
    N = 780
    x = np.linspace(-1, 1, N); y = np.linspace(-1, 1, N)
    X, Y = np.meshgrid(x, y)
    # A classic square-plate mode approximation. Nodal lines z≈0 are where
    # sand accumulates in the real experiment.
    z = np.cos(m * np.pi * X / 2) * np.cos(n * np.pi * Y / 2) - np.cos(n * np.pi * X / 2) * np.cos(m * np.pi * Y / 2)
    line = np.exp(-((z / 0.075) ** 2))
    shade = 248 - (215 * line).astype(np.uint8)
    blue = np.minimum(255, shade.astype(np.uint16) + 8).astype(np.uint8)
    rgb = np.stack([shade, shade, blue], axis=-1).astype(np.uint8)
    img = Image.fromarray(rgb, "RGB")
    d = ImageDraw.Draw(img); d.rectangle((2, 2, N - 3, N - 3), outline=(35, 35, 40), width=3)
    _title(img, f"Chladni-like square plate mode · m={m}, n={n}")
    p = _out(output_dir, f"chladni-{m}-{n}"); img.save(p)
    return p, "Chladni 图样把振动板的节点线直接变成图案：真实实验中细沙会从强振动区跳走，并聚到这些近似不动的线附近。"


def phyllotaxis(output_dir: Path, angle: float = 137.507764, points: int = 1800) -> tuple[Path, str]:
    angle = float(angle); points = max(80, min(int(points), 6000))
    if not 0 < angle < 360:
        raise Fun2LabError("角度需在 0..360°")
    img = Image.new("RGB", (820, 820), (248, 248, 245)); d = ImageDraw.Draw(img)
    c = 410.0; max_r = 350.0
    for k in range(1, points + 1):
        r = max_r * math.sqrt(k / points)
        th = math.radians(k * angle)
        x = c + r * math.cos(th); y = c + r * math.sin(th)
        u = k / points
        col = (int(35 + 195 * u), int(115 + 85 * (1 - u)), int(170 - 80 * u))
        rad = 2 if points > 3200 else 3 if points > 1000 else 4
        d.ellipse((x-rad, y-rad, x+rad, y+rad), fill=col)
    _title(img, f"Phyllotaxis · divergence angle={angle:.6g}° · {points} points")
    p = _out(output_dir, f"phyllotaxis-{angle:.6g}-{points}"); img.save(p)
    golden = 360 * (1 - 1 / ((1 + math.sqrt(5)) / 2))
    return p, f"每个新点只比前一个旋转固定角度。黄金角约 {golden:.6f}° 时，很难长期对齐成少数辐射线，因此填充特别均匀。"


def galton(output_dir: Path, rows: int = 12, balls: int = 6000) -> tuple[Path, str]:
    rows = max(5, min(int(rows), 20)); balls = max(200, min(int(balls), 50000))
    rng = np.random.default_rng(20260831)
    rights = rng.integers(0, 2, size=(balls, rows), dtype=np.uint8).sum(axis=1)
    counts = np.bincount(rights, minlength=rows + 1)
    img = Image.new("RGB", (1000, 820), (249, 249, 246)); d = ImageDraw.Draw(img)
    _title(img, f"Galton board · {rows} rows · {balls} balls")
    cx = 500; y0 = 100; dy = 27; dx = 27
    # Peg triangle.
    for r in range(rows):
        for j in range(r + 1):
            x = cx + (j - r / 2) * 2 * dx; y = y0 + r * dy
            d.ellipse((x-3, y-3, x+3, y+3), fill=(60, 70, 85))
    base_y = y0 + rows * dy + 28; max_h = 300; maxc = max(int(counts.max()), 1)
    barw = min(55, int(720 / (rows + 1)))
    centers = []
    for j, c in enumerate(counts):
        x = cx + (j - rows / 2) * 2 * dx; centers.append(x)
        h = max_h * int(c) / maxc
        d.rectangle((x-barw/2, base_y + max_h - h, x+barw/2, base_y + max_h), fill=(55, 110, 180))
        d.text((x-18, base_y + max_h + 7), str(j), fill=(40, 40, 45), font=_font(14))
    # Expected binomial probabilities, scaled to the same peak, as a smooth-looking polyline.
    probs = np.array([math.comb(rows, j) for j in range(rows + 1)], dtype=float) / (2 ** rows)
    expected = probs * balls; scale = max_h / maxc
    pts = [(centers[j], base_y + max_h - expected[j] * scale) for j in range(rows + 1)]
    d.line(pts, fill=(210, 70, 45), width=4)
    d.text((70, 760), "blue: simulated balls    red: exact binomial expectation", fill=(35,35,40), font=_font(18))
    p = _out(output_dir, f"galton-{rows}-{balls}"); img.save(p)
    return p, "每颗球每层只做一次左/右二选一；大量独立小随机选择叠起来，就自然出现接近钟形的二项分布。"


def lissajous(output_dir: Path, a: int = 3, b: int = 2, phase_deg: float = 90.0) -> tuple[Path, str]:
    a = max(1, min(int(a), 16)); b = max(1, min(int(b), 16)); phase = float(phase_deg)
    t = np.linspace(0, 2 * np.pi, 5000)
    x = np.sin(a * t + math.radians(phase)); y = np.sin(b * t)
    img = Image.new("RGB", (820, 820), (248, 248, 245)); d = ImageDraw.Draw(img)
    d.line((410, 80, 410, 770), fill=(205,205,205), width=1); d.line((65, 425, 755, 425), fill=(205,205,205), width=1)
    pts = [(410 + 325 * xx, 425 - 325 * yy) for xx, yy in zip(x, y)]
    # Phosphor-style thick + thin trace without requiring transparency compositing.
    d.line(pts, fill=(175, 220, 190), width=7); d.line(pts, fill=(25, 125, 75), width=2)
    _title(img, f"Lissajous figure · x: {a}ω · y: {b}ω · phase={phase:g}°")
    p = _out(output_dir, f"lissajous-{a}-{b}-{phase:g}"); img.save(p)
    return p, "示波器 XY 模式里，两路正弦信号不再按时间展开，而是互相当作横纵坐标；频率比会直接变成闭合图形的瓣数关系。"


def help_text() -> str:
    return (
        "  /lab chladni [m] [n]\n"
        "  /lab phyllotaxis [angle_deg] [points]\n"
        "  /lab galton [rows] [balls]\n"
        "  /lab lissajous [fx] [fy] [phase_deg]"
    )


def render_fun2(output_dir: Path, payload: str):
    p = payload.strip().split()
    if not p: return None
    h = p[0].lower(); r = p[1:]
    if h in {"chladni", "plate"}: return chladni(output_dir, int(r[0]) if r else 5, int(r[1]) if len(r)>1 else 3)
    if h in {"phyllotaxis", "sunflower"}: return phyllotaxis(output_dir, float(r[0]) if r else 137.507764, int(r[1]) if len(r)>1 else 1800)
    if h in {"galton", "bean"}: return galton(output_dir, int(r[0]) if r else 12, int(r[1]) if len(r)>1 else 6000)
    if h in {"lissajous", "xy"}: return lissajous(output_dir, int(r[0]) if r else 3, int(r[1]) if len(r)>1 else 2, float(r[2]) if len(r)>2 else 90)
    return None
