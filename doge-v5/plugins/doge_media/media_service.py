from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image

from .vendor.mirage_upstream.processor.inference import generate_mirage


ANIMETRACE_URL = "https://api.animetrace.com/v1/search"


def _normalize_image_sync(path: str | Path, out: Path, max_side: int = 1400) -> Path:
    src = Path(path)
    if src.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("图片超过 12 MiB")
    with Image.open(src) as im:
        im.load()
        if im.width * im.height > 24_000_000:
            raise ValueError("图片像素过大")
        image = im.convert("RGBA")
        if max(image.size) > max_side:
            ratio = max_side / max(image.size)
            image = image.resize(
                (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
                Image.Resampling.LANCZOS,
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out, format="PNG")
    return out


async def normalize_image(path: str | Path, out: Path) -> Path:
    return await asyncio.to_thread(_normalize_image_sync, path, out)


async def make_mirage(
    front: str | Path,
    back: str | Path,
    output_dir: Path,
    mode: str = "gray",
) -> Path:
    mode = mode.lower()
    if mode not in {"gray", "color"}:
        raise ValueError("mirage 模式只能是 gray / color")
    output_dir = Path(output_dir)
    work = output_dir / "mirage-work"
    work.mkdir(parents=True, exist_ok=True)
    f = await normalize_image(front, work / "front.png")
    b = await normalize_image(back, work / "back.png")
    path = await generate_mirage(
        str(f),
        str(b),
        save_dir=str(output_dir),
        mode=mode,
        a=0.5,
        b=20,
        w=0.7,
    )
    return Path(path)


def _jpeg_b64(path: str | Path, max_side: int = 1024) -> str:
    with Image.open(path) as im:
        image = im.convert("RGB")
        if max(image.size) > max_side:
            ratio = max_side / max(image.size)
            image = image.resize(
                (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
                Image.Resampling.LANCZOS,
            )
        bio = BytesIO()
        image.save(bio, format="JPEG", quality=84, optimize=True)
        return base64.b64encode(bio.getvalue()).decode("ascii")


async def trace_image(path: str | Path, mode: str = "anime") -> str:
    mode = mode.lower()
    models = {"anime": "pre_stable", "gal": "full_game_model_kira"}
    if mode not in models:
        raise ValueError("trace 模式只能是 anime / gal")
    image_b64 = await asyncio.to_thread(_jpeg_b64, path)
    payload = {
        "base64": image_b64,
        "is_multi": "1",
        "model": models[mode],
        "ai_detect": "0",
    }
    timeout = aiohttp.ClientTimeout(total=18, connect=6, sock_read=12)
    headers = {"User-Agent": "Doge-v5/5.5"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.post(ANIMETRACE_URL, data=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"AnimeTrace HTTP {resp.status}: {text[:300]}")
            data = await resp.json(content_type=None)
    boxes = data.get("data") or []
    characters = boxes[0].get("character", []) if boxes else []
    if not characters:
        return "没有得到可靠的角色/作品候选。"
    label = "动漫" if mode == "anime" else "Gal"
    lines = [f"{label}识别 · AnimeTrace"]
    for i, item in enumerate(characters[:6], 1):
        char = item.get("character") or "未知角色"
        work = item.get("work") or "未知作品"
        lines.append(f"{i}. {char} — {work}")
    if data.get("ai"):
        lines.append("服务端判定：输入可能是 AI 生成图。")
    return "\n".join(lines)
