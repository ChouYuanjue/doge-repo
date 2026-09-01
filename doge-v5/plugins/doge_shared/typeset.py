from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
import re
import shutil
import subprocess
import zlib
from pathlib import Path


class TypesetError(ValueError):
    pass


class TypesetDependencyError(RuntimeError):
    pass


_ZERO_SVG = re.compile(r'<svg[^>]*(?:width=["\']0["\']|height=["\']0["\'])', re.I)


def _out_dir(output_dir: Path) -> Path:
    d = Path(output_dir) / "typeset"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _token(kind: str, source: str) -> str:
    return hashlib.sha256((kind + "\0" + source).encode("utf-8")).hexdigest()[:16]


def _clean(source: str, limit: int, label: str) -> str:
    source = (source or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not source:
        raise TypesetError(f"{label} 内容不能为空")
    if "\x00" in source:
        raise TypesetError(f"{label} 内容包含 NUL 字符")
    if len(source) > limit:
        raise TypesetError(f"{label} 内容过长：最多 {limit} 个字符")
    return source


def _strip_outer_dollars(source: str) -> str:
    s = source.strip()
    if len(s) >= 4 and s.startswith("$$") and s.endswith("$$"):
        return s[2:-2].strip()
    if len(s) >= 2 and s.startswith("$") and s.endswith("$"):
        return s[1:-1].strip()
    return s


def _compressed_upmath_url(expr: str, fmt: str) -> str:
    # i.upmath.me added raw-deflate + URL-safe base64 paths in 2025. This keeps
    # TikZ/align URLs compact without adding a new client SDK.
    c = zlib.compressobj(level=9, wbits=-15)
    raw = c.compress(expr.encode("utf-8")) + c.flush()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"https://i.upmath.me/{fmt}b/{encoded}"


async def _fetch(url: str, *, timeout_s: float = 15.0) -> tuple[bytes, str]:
    try:
        import aiohttp
    except Exception as exc:
        raise TypesetDependencyError("TeX 原生后端需要 aiohttp") from exc
    timeout = aiohttp.ClientTimeout(total=timeout_s, connect=6, sock_read=10)
    last = None
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "doge-v5-typeset/5.0"}) as session:
                async with session.get(url) as resp:
                    data = await resp.read()
                    if resp.status != 200:
                        raise TypesetError(f"TeX 后端返回 HTTP {resp.status}")
                    return data, resp.headers.get("content-type", "")
        except TypesetError:
            raise
        except Exception as exc:
            last = exc
            if attempt == 0:
                await asyncio.sleep(0.35)
    raise TypesetError(f"TeX 原生后端暂时不可用：{last}")


def _rasterize_svg_if_possible(svg: str) -> bytes | None:
    # Prefer self-contained Rust renderer when installed; no libcairo system
    # dependency. Fall back to CairoSVG only when the host already supports it.
    try:
        import resvg_py
        return bytes(resvg_py.svg_to_bytes(svg_string=svg, zoom=4.0, background="#ffffff"))
    except Exception:
        pass
    try:
        import cairosvg
        return cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=4.0)
    except Exception:
        return None


def _polish_png(data: bytes, *, scale: int = 3, padding: int = 14) -> bytes:
    try:
        from PIL import Image
    except Exception:
        return data
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if im.width <= 0 or im.height <= 0:
            raise TypesetError("TeX 后端返回了空图片")
        # Public UpMath PNG is intentionally compact. Upscale only the fallback
        # raster path; when resvg/cairo is installed we keep true vector quality.
        if scale > 1:
            im = im.resize((im.width * scale, im.height * scale), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (im.width + 2 * padding, im.height + 2 * padding), "white")
        canvas.paste(im, (padding, padding))
        out = io.BytesIO(); canvas.save(out, "PNG", optimize=True)
        return out.getvalue()
    except TypesetError:
        raise
    except Exception:
        return data


async def _render_tex_native(output_dir: Path, expr: str) -> tuple[Path, str]:
    svg_data, ctype = await _fetch(_compressed_upmath_url(expr, "svg"))
    if "svg" not in ctype and not svg_data.lstrip().startswith(b"<"):
        raise TypesetError("TeX 后端没有返回 SVG")
    svg = svg_data.decode("utf-8", "replace")
    if _ZERO_SVG.search(svg) or re.search(r'<svg[^>]*width=["\']0(?:\.0+)?(?:pt|px)?["\']', svg, re.I):
        raise TypesetError("TeX 编译失败：公式为空或语法/宏不受支持")
    png = await asyncio.to_thread(_rasterize_svg_if_possible, svg)
    backend = "UpMath TeX + SVG"
    if not png:
        png_data, ptype = await _fetch(_compressed_upmath_url(expr, "png"))
        if "png" not in ptype or len(png_data) < 16:
            raise TypesetError("TeX 编译失败：后端未生成有效 PNG")
        png = await asyncio.to_thread(_polish_png, png_data)
        backend = "UpMath TeX + PNG fallback"
    path = _out_dir(output_dir) / f"tex-{_token('tex-native', expr)}.png"
    path.write_bytes(png)
    return path, backend


def _render_tex_local(output_dir: Path, expr: str) -> tuple[Path, str]:
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise TypesetDependencyError("/tex local 需要 matplotlib") from exc
    if re.search(r"\\begin\{|\\end\{|\\tikz|\\pgf|\\includegraphics|\\usepackage|\\documentclass", expr):
        raise TypesetError("local 只支持 MathText 公式；align/matrix/TikZ 请用默认 /tex 或 /tex native")
    lines = [x.strip() for x in expr.split("\n") if x.strip()]
    if not lines:
        raise TypesetError("TeX 内容不能为空")
    longest = max(len(x) for x in lines)
    width = max(2.0, min(15.0, 0.12 * longest + 0.8))
    height = max(0.8, min(12.0, 0.72 * len(lines) + 0.3))
    fig = plt.figure(figsize=(width, height), dpi=220, facecolor="white")
    try:
        for i, line in enumerate(lines):
            y = 1.0 - (i + 0.55) / len(lines)
            fig.text(0.025, y, f"${_strip_outer_dollars(line)}$", fontsize=20, color="black", va="center", ha="left")
        path = _out_dir(output_dir) / f"tex-{_token('tex-local', expr)}.png"
        fig.savefig(path, dpi=220, bbox_inches="tight", pad_inches=0.08, facecolor="white")
    except Exception as exc:
        raise TypesetError(f"本地 MathText 渲染失败：{str(exc).splitlines()[0][:240]}") from exc
    finally:
        plt.close(fig)
    return path, "local MathText"


async def render_tex(output_dir: Path, source: str, mode: str = "smart") -> tuple[Path, str]:
    source = _clean(source, 12000, "TeX")
    expr = _strip_outer_dollars(source)
    mode = mode.lower()
    if mode not in {"smart", "native", "local"}:
        raise TypesetError("TeX 模式支持 smart / native / local")
    if mode == "local":
        return await asyncio.to_thread(_render_tex_local, output_dir, expr)
    try:
        path, backend = await _render_tex_native(output_dir, expr)
        return path, f"TeX · {backend}"
    except Exception as native_exc:
        if mode == "native":
            if isinstance(native_exc, (TypesetError, TypesetDependencyError)):
                raise
            raise TypesetError(f"TeX 原生渲染失败：{native_exc}") from native_exc
        try:
            path, backend = await asyncio.to_thread(_render_tex_local, output_dir, expr)
            return path, f"TeX · {backend}（原生后端失败后回退）"
        except Exception:
            if isinstance(native_exc, (TypesetError, TypesetDependencyError)):
                raise native_exc
            raise TypesetError(f"TeX 渲染失败：{native_exc}") from native_exc


def tex_help() -> str:
    return (
        "Doge TeX /tex\n"
        "  /tex <LaTeX>                smart：优先原生 TeX，失败时本地回退\n"
        "  /tex native <LaTeX>         强制原生 TeX；支持 align/matrix/TikZ 等\n"
        "  /tex local <LaTeX>          仅本机 MathText，不把公式发到外部服务\n"
        "可直接写多行，不再按逗号拆分。兼容别名：/latex /utex。"
    )


_TYPST_CHAT_TEMPLATE = r'''
#set page(width: 12cm, height: auto, margin: 12pt, fill: rgb("f2f2f2"))
#set text(size: 11pt)
#let yau(body) = block(width: 100%, inset: 10pt, radius: 8pt, fill: white)[
  #text(size: 8.5pt, fill: rgb("777777"))[Yau] \
  #body
]
'''.strip()


_CJK_RE = re.compile(r"[\u2e80-\u2eff\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CJK_FONT_HINTS = ("noto", "sourcehan", "source-han", "wenquanyi", "wqy", "sarasa", "simsun", "simhei", "pingfang", "heiti", "songti", "cjk")


def _typst_font_paths() -> list[str]:
    paths: list[str] = []
    env = os.getenv("DOGE_TYPST_FONT_PATHS") or os.getenv("TYPST_FONT_PATHS") or ""
    for raw in env.split(os.pathsep):
        if raw and Path(raw).expanduser().is_dir():
            paths.append(str(Path(raw).expanduser().resolve()))
    return list(dict.fromkeys(paths))


def _has_cjk_font(extra_paths: list[str]) -> bool:
    fc = shutil.which("fc-list")
    if fc:
        try:
            r = subprocess.run([fc, ":lang=zh", "family", "file"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                return True
        except Exception:
            pass
    roots = [Path(x) for x in extra_paths]
    roots += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home()/".local/share/fonts"]
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for f in root.rglob("*"):
                if f.suffix.lower() not in {".ttf", ".otf", ".ttc", ".otc"}:
                    continue
                name = f.name.lower().replace("-", "").replace(" ", "")
                if any(h.replace("-", "") in name for h in _CJK_FONT_HINTS):
                    return True
        except Exception:
            continue
    return False


def _typst_source(source: str, mode: str) -> str:
    if mode == "math":
        body = source.strip()
        if body.startswith("$") and body.endswith("$"):
            content = body
        else:
            content = f"$ {body} $"
        return (
            "#set page(width: auto, height: auto, margin: 10pt, fill: white)\n"
            "#set text(size: 20pt)\n"
            f"#align(center, {content})\n"
        )
    if mode == "card":
        return "#set page(width: 16cm, height: auto, margin: 12pt, fill: white)\n" + source
    if mode == "chat":
        return _TYPST_CHAT_TEMPLATE + "\n" + source
    if mode == "doc":
        return source
    raise TypesetError("Typst 模式支持 math / card / doc / chat")


def render_typst(output_dir: Path, source: str, mode: str = "card", ppi: float = 220.0, max_pages: int = 4) -> tuple[list[Path], str]:
    source = _clean(source, 30000, "Typst")
    mode = mode.lower()
    if not 96 <= float(ppi) <= 360:
        raise TypesetError("Typst PPI 需在 96..360")
    try:
        import typst
    except Exception as exc:
        raise TypesetDependencyError("Typst 需要 typst-py；建议安装 typst>=0.15,<0.16") from exc
    font_paths = _typst_font_paths()
    if _CJK_RE.search(source) and not _has_cjk_font(font_paths):
        raise TypesetDependencyError(
            "检测到中文/CJK 文本，但当前运行环境没有可用 CJK 字体。"
            "请安装 Noto/Source Han 等字体，或设置 DOGE_TYPST_FONT_PATHS 指向字体目录。"
        )
    compiled_source = _typst_source(source, mode)
    package_cache = _out_dir(output_dir) / "typst-packages"
    package_cache.mkdir(parents=True, exist_ok=True)
    compile_kwargs = {
        "format": "png",
        "ppi": float(ppi),
        "package_cache_path": str(package_cache),
    }
    if font_paths:
        compile_kwargs["font_paths"] = font_paths
    try:
        result = typst.compile(compiled_source.encode("utf-8"), **compile_kwargs)
    except Exception as exc:
        msg = str(exc).strip() or type(exc).__name__
        raise TypesetError(f"Typst 编译失败：{msg[:1200]}") from exc
    pages = result if isinstance(result, list) else [result]
    if not pages:
        raise TypesetError("Typst 没有生成页面")
    if len(pages) > max_pages:
        raise TypesetError(f"Typst 生成了 {len(pages)} 页；群聊入口最多发送 {max_pages} 页，请缩短内容")
    paths: list[Path] = []
    stem = _token(f"typst-{mode}", source)
    for i, data in enumerate(pages, 1):
        if not isinstance(data, (bytes, bytearray)) or not bytes(data).startswith(b"\x89PNG\r\n\x1a\n"):
            raise TypesetError(f"Typst 第 {i} 页没有生成有效 PNG")
        p = _out_dir(output_dir) / f"typst-{stem}-{i}.png"
        p.write_bytes(bytes(data)); paths.append(p)
    version = getattr(typst, "__version__", "unknown")
    return paths, f"Typst {version} · {mode} · {len(paths)} page(s)"


def typst_help() -> str:
    return (
        "Doge Typst /typst\n"
        "  /typst math <formula>        自动裁边数学公式\n"
        "  /typst card <markup>         适合群聊的自适应长卡片（默认）\n"
        "  /typst doc <full source>     完整 Typst 文档，最多发送 4 页\n"
        "  /typst chat <markup>         内置聊天气泡模板，可写 #yau[...]\n"
        "兼容：/tym -> math，/typ -> doc，/yau -> chat。保留所有空格与换行。\n"
        "中文字体可通过 DOGE_TYPST_FONT_PATHS 显式提供；缺字时会报错，不输出方块图。"
    )
