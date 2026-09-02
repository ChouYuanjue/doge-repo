from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile
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


def _is_tex_document(source: str) -> bool:
    """Recognize a real LaTeX document rather than a formula/fragment."""
    text = source or ""
    return bool(re.search(r"\\documentclass(?:\[[^]]*\])?\s*\{|\\begin\s*\{document\}", text, re.I))


def _tectonic_binary() -> str:
    configured = str(os.getenv("DOGE_TECTONIC_BIN") or "").strip()
    if configured:
        p = Path(configured).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        raise TypesetDependencyError(f"DOGE_TECTONIC_BIN 不可执行：{p}")
    found = shutil.which("tectonic")
    if found:
        return found
    fallback = Path.home() / ".local/bin/tectonic"
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)
    raise TypesetDependencyError(
        "完整 LaTeX 文档需要轻量 Tectonic 引擎；当前未安装。公式片段仍可使用 /tex smart 或 /tex native"
    )


def _bubblewrap_binary() -> str:
    configured = str(os.getenv("DOGE_BWRAP_BIN") or "").strip()
    if configured:
        p = Path(configured).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        raise TypesetDependencyError(f"DOGE_BWRAP_BIN 不可执行：{p}")
    found = shutil.which("bwrap") or shutil.which("bubblewrap")
    if found:
        return found
    raise TypesetDependencyError(
        "完整 LaTeX 文档需要 bubblewrap 文件系统沙箱；当前未安装。"
        "为避免不受信任 TeX 读取服务器文件，不会回退到裸 Tectonic"
    )


def _tectonic_sandbox_command(tectonic: str, work: Path) -> list[str]:
    """Build the production Tectonic command with a minimal filesystem view.

    Tectonic's ``--untrusted`` disables known engine escape hatches but still
    permits ordinary absolute-path reads such as ``\\input{/etc/...}``.  The
    outer bubblewrap namespace therefore exposes only the temporary workdir,
    the Tectonic binary, its cache, and the small TLS/DNS surface needed for
    on-demand package downloads.
    """
    bwrap = _bubblewrap_binary()
    cache = Path(os.getenv("DOGE_TECTONIC_CACHE") or (Path.home() / ".cache/tectonic"))
    cache.mkdir(parents=True, exist_ok=True)
    cmd = [
        bwrap,
        "--die-with-parent",
        "--unshare-all",
        "--share-net",
        "--dir", "/bin",
        "--dir", "/etc",
        "--dir", "/etc/ssl",
        "--dir", "/cache",
        "--dir", "/work",
        "--tmpfs", "/tmp",
        "--ro-bind", tectonic, "/bin/tectonic",
        "--bind", str(cache), "/cache/tectonic",
        "--bind", str(work), "/work",
        "--setenv", "HOME", "/work",
        "--setenv", "XDG_CACHE_HOME", "/cache",
        "--chdir", "/work",
    ]
    # The musl Tectonic build is static. Keep the filesystem sandbox small but
    # expose enough trust/network state for Tectonic's MiKTeX-like lazy bundle
    # downloads. On RHEL-family hosts /etc/ssl/certs points into /etc/pki; merely
    # bind-mounting /etc/ssl/certs leaves the CA symlink target invisible and
    # causes rustls to fail every cold package fetch with UnknownIssuer.
    for host_path in (Path("/etc/ssl/certs"), Path("/etc/resolv.conf"), Path("/etc/hosts")):
        if host_path.exists():
            cmd += ["--ro-bind", str(host_path), str(host_path)]
    ca_candidates = (
        Path("/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"),
        Path("/etc/ssl/certs/ca-certificates.crt"),
        Path("/etc/ssl/cert.pem"),
    )
    ca_bundle = next((x for x in ca_candidates if x.is_file()), None)
    if ca_bundle is not None:
        cmd += [
            "--dir", "/etc/pki",
            "--dir", "/etc/pki/tls",
            "--dir", "/etc/pki/tls/certs",
            "--ro-bind", str(ca_bundle), "/etc/pki/tls/cert.pem",
            "--ro-bind", str(ca_bundle), "/etc/pki/tls/certs/ca-bundle.crt",
            "--setenv", "SSL_CERT_FILE", "/etc/pki/tls/cert.pem",
        ]
    cmd += [
        "/bin/tectonic",
        "--untrusted",
        "--color", "never",
        "--chatter", "minimal",
        "--outdir", "/work",
        "/work/main.tex",
    ]
    return cmd


def _render_tex_document(output_dir: Path, source: str) -> tuple[Path, str]:
    source = _clean(source, 50000, "TeX 文档")
    if not _is_tex_document(source):
        raise TypesetError("/tex doc 需要完整 LaTeX 文档（含 \\documentclass 或 \\begin{document}）")
    tectonic = _tectonic_binary()
    out_dir = _out_dir(output_dir)
    token = _token("tex-document", source)
    final_pdf = out_dir / f"tex-document-{token}.pdf"
    with tempfile.TemporaryDirectory(prefix="doge-tex-") as td:
        work = Path(td)
        tex = work / "main.tex"
        tex.write_text(source, encoding="utf-8")
        cmd = _tectonic_sandbox_command(tectonic, work)
        try:
            try:
                timeout_s = int(os.getenv("DOGE_TECTONIC_TIMEOUT", "180"))
            except ValueError:
                timeout_s = 180
            timeout_s = max(30, min(300, timeout_s))
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise TypesetError("完整 LaTeX 文档编译超时；首次使用冷门宏包时会自动下载依赖并缓存，请稍后重试") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "Tectonic 编译失败").strip()
            # Keep the useful end of Tectonic's diagnostics without flooding chat.
            lines = [x.strip() for x in detail.splitlines() if x.strip()]
            detail = " | ".join(lines[-8:])[:1200]
            raise TypesetError(f"完整 LaTeX 文档编译失败：{detail}")
        generated = work / "main.pdf"
        if not generated.is_file() or not generated.read_bytes().startswith(b"%PDF"):
            raise TypesetError("Tectonic 没有生成有效 PDF")
        shutil.copy2(generated, final_pdf)
    pages = None
    try:
        from pypdf import PdfReader
        pages = len(PdfReader(str(final_pdf)).pages)
    except Exception:
        pass
    suffix = f" · {pages} page(s)" if pages is not None else ""
    return final_pdf, f"TeX · Tectonic full document{suffix}"


async def render_tex(output_dir: Path, source: str, mode: str = "smart") -> tuple[Path, str]:
    source = _clean(source, 50000, "TeX")
    mode = mode.lower()
    if mode not in {"smart", "native", "local", "doc"}:
        raise TypesetError("TeX 模式支持 smart / doc / native / local")
    document = _is_tex_document(source)
    if mode == "doc" or (mode == "smart" and document):
        return await asyncio.to_thread(_render_tex_document, output_dir, source)
    if document:
        raise TypesetError("完整 LaTeX 文档请使用默认 /tex 或 /tex doc；native/local 只用于公式与片段")
    expr = _strip_outer_dollars(source)
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
        "  /tex <LaTeX>                smart：完整文档走本机 Tectonic；公式/片段走轻量渲染\n"
        "  /tex doc <完整文档>         Tectonic 真 LaTeX 文档 → PDF（\\documentclass...）；缺宏包会自动按需下载并缓存\n"
        "  /tex native <片段>          强制 UpMath TeX；适合 align/matrix/TikZ 等片段\n"
        "  /tex local <公式>            仅本机 MathText，不把公式发到外部服务\n"
        "完整文档不会再误送给公式 API。可直接写多行；兼容别名：/latex /utex。"
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
