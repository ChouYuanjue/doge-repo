from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path

import aiohttp


class DiagramError(RuntimeError):
    pass


FORMATS = ("graphviz", "mermaid", "vegalite")
ALIASES = {"dot": "graphviz", "vega-lite": "vegalite", "vl": "vegalite"}


def normalize_kind(kind: str) -> str:
    kind = ALIASES.get((kind or "").lower().strip(), (kind or "").lower().strip())
    if kind not in FORMATS:
        raise DiagramError("不支持的正式图类型；使用 /diagram formats 查看")
    return kind


def clean_source(source: str) -> str:
    source = (source or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not source:
        raise DiagramError("图源码不能为空")
    if "\x00" in source:
        raise DiagramError("图源码包含 NUL")
    if len(source) > 30000:
        raise DiagramError("群聊图源码最多 30000 字符")
    return source


def _out(output_dir: Path, kind: str, source: str) -> Path:
    d = Path(output_dir) / "diagram"
    d.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256((kind + "\0" + source).encode("utf-8")).hexdigest()[:16]
    return d / f"{kind}-{h}.png"


def _limits() -> None:
    # Graphviz is a normal local renderer, but user-controlled graph sizes still
    # get a hard CPU/address-space ceiling on this small server.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    except Exception:
        pass


def render_graphviz(output_dir: Path, source: str) -> tuple[Path, str]:
    source = clean_source(source)
    # Do not let DOT act as a local-file image loader. Hyperlinks themselves are
    # harmless in raster output, but image/shapefile paths are unnecessary here.
    low = source.lower()
    for forbidden in ("image=", "shapefile=", "stylesheet="):
        if forbidden in low:
            raise DiagramError(f"Graphviz 群聊模式禁用 `{forbidden[:-1]}` 外部资源属性")
    try:
        cp = subprocess.run(
            ["dot", "-Tpng", "-Gdpi=150", "-Gbgcolor=white"],
            input=source.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=9,
            check=False,
            preexec_fn=_limits if os.name == "posix" else None,
        )
    except FileNotFoundError as exc:
        raise DiagramError("缺少 Graphviz `dot` 运行时") from exc
    except subprocess.TimeoutExpired as exc:
        raise DiagramError("Graphviz 渲染超时；请简化图") from exc
    if cp.returncode != 0 or not cp.stdout.startswith(b"\x89PNG"):
        err = cp.stderr.decode("utf-8", "replace").strip()[:900]
        raise DiagramError("Graphviz 渲染失败：" + (err or f"exit {cp.returncode}"))
    if len(cp.stdout) > 12 * 1024 * 1024:
        raise DiagramError("Graphviz 输出超过 12 MiB")
    path = _out(Path(output_dir), "graphviz", source)
    path.write_bytes(cp.stdout)
    return path, "Graphviz · local renderer"


def _has_remote_url(obj) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() == "url":
                return True
            if _has_remote_url(v):
                return True
    elif isinstance(obj, list):
        return any(_has_remote_url(x) for x in obj)
    return False


def render_vegalite(output_dir: Path, source: str) -> tuple[Path, str]:
    source = clean_source(source)
    try:
        spec = json.loads(source)
    except Exception as exc:
        raise DiagramError(f"Vega-Lite JSON 解析失败：{exc}") from exc
    if not isinstance(spec, dict):
        raise DiagramError("Vega-Lite 顶层必须是 JSON object")
    if _has_remote_url(spec):
        raise DiagramError("Vega-Lite 群聊模式只接受 inline values，不抓取 data.url")
    try:
        import vl_convert as vlc  # type: ignore
    except Exception as exc:
        raise DiagramError("缺少 vl-convert-python；请安装 doge_diagrams requirements") from exc
    try:
        data = vlc.vegalite_to_png(spec, scale=1.5)
    except Exception as exc:
        raise DiagramError(f"Vega-Lite 渲染失败：{str(exc)[:900]}") from exc
    if not isinstance(data, (bytes, bytearray)) or not bytes(data).startswith(b"\x89PNG"):
        raise DiagramError("Vega-Lite 后端没有返回 PNG")
    if len(data) > 12 * 1024 * 1024:
        raise DiagramError("Vega-Lite 输出超过 12 MiB")
    path = _out(Path(output_dir), "vegalite", source)
    path.write_bytes(bytes(data))
    return path, "Vega-Lite · local vl-convert renderer"


def _mermaid_payload(source: str) -> str:
    raw = json.dumps({"code": source, "mermaid": {"theme": "default"}}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


async def render_mermaid(output_dir: Path, source: str) -> tuple[Path, str]:
    source = clean_source(source)
    # Mermaid currently uses the dedicated public renderer rather than a local
    # Chromium runtime. The source is therefore sent to mermaid.ink; keep this
    # explicit in the caption/help instead of pretending it is local.
    url = "https://mermaid.ink/img/" + _mermaid_payload(source) + "?type=png&bgColor=!white"
    timeout = aiohttp.ClientTimeout(total=18, connect=6, sock_read=12)
    headers = {"User-Agent": "Doge-v5/5.4 (+https://github.com/ChouYuanjue/doge-repo)"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                body = await resp.read()
                if resp.status >= 400:
                    raise DiagramError(f"Mermaid renderer HTTP {resp.status}: {body[:500].decode('utf-8','replace')}")
                ctype = (resp.headers.get("content-type") or "").lower()
    except asyncio.TimeoutError as exc:
        raise DiagramError("Mermaid 公共渲染器超时；Graphviz/Vega-Lite 本地后端不受影响") from exc
    except aiohttp.ClientError as exc:
        raise DiagramError(f"Mermaid 公共渲染器网络错误：{exc}") from exc
    if not body.startswith(b"\x89PNG"):
        raise DiagramError(f"Mermaid renderer 未返回 PNG（{ctype or 'unknown content-type'}）")
    if len(body) > 12 * 1024 * 1024:
        raise DiagramError("Mermaid 输出超过 12 MiB")
    path = _out(Path(output_dir), "mermaid", source)
    path.write_bytes(body)
    return path, "Mermaid · mermaid.ink renderer (source is sent to the public service)"


async def render_diagram(output_dir: Path, kind: str, source: str) -> tuple[Path, str]:
    kind = normalize_kind(kind)
    if kind == "mermaid":
        return await render_mermaid(output_dir, source)
    if kind == "graphviz":
        return await asyncio.to_thread(render_graphviz, output_dir, source)
    return await asyncio.to_thread(render_vegalite, output_dir, source)
