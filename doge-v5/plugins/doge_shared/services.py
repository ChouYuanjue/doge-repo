from __future__ import annotations

import json
import os
from urllib.parse import quote

import aiohttp

from .logic import codec, convert_base, safe_calc


class ServiceError(RuntimeError):
    pass


async def _json_get(url: str, params: dict | None = None, timeout: float = 15.0):
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    headers = {"User-Agent": "Doge-v5/1.0"}
    async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as session:
        async with session.get(url, params=params) as response:
            if response.status >= 400:
                text = (await response.text())[:300]
                raise ServiceError(f"HTTP {response.status}: {text}")
            try:
                return await response.json(content_type=None)
            except Exception as exc:
                raise ServiceError("远端返回的不是可解析 JSON") from exc


async def _text_get(url: str, timeout: float = 15.0) -> str:
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    headers = {"User-Agent": "Doge-v5/1.0"}
    async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as session:
        async with session.get(url) as response:
            if response.status >= 400:
                raise ServiceError(f"HTTP {response.status}")
            return (await response.text()).strip()


class MathService:
    @staticmethod
    def calc(expression: str) -> str:
        return str(safe_calc(expression))

    @staticmethod
    def base(value: str, source_base: int, target_base: int) -> str:
        return convert_base(value, source_base, target_base)

    @staticmethod
    async def pi(start: int, count: int) -> str:
        if start < 0 or count < 1 or count > 1000:
            raise ValueError("start >= 0，且 1 <= count <= 1000")
        data = await _json_get(
            "https://api.pi.delivery/v1/pi",
            params={"start": start, "numberOfDigits": count},
        )
        content = data.get("content") if isinstance(data, dict) else None
        if not content:
            raise ServiceError("π 服务未返回 content")
        return str(content)

    @staticmethod
    async def oeis(query: str, limit: int = 3) -> str:
        data = await _json_get("https://oeis.org/search", params={"q": query, "fmt": "json"})
        results = data.get("results", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        if not results:
            return "OEIS 未找到结果"
        out = []
        for item in results[: max(1, min(limit, 5))]:
            number = int(item.get("number", 0))
            name = item.get("name", "")
            seq = item.get("data", "")
            out.append(f"A{number:06d} {name}\n{seq}")
        return "\n\n".join(out)


class ChemService:
    TEXT_ACTIONS = {"formula": "formula", "smiles": "smiles", "names": "names", "inchikey": "stdinchikey"}

    @classmethod
    async def query(cls, compound: str, action: str = "formula") -> str:
        compound = compound.strip()
        action = action.lower()
        if not compound:
            raise ValueError("化学物质不能为空")
        encoded = quote(compound, safe="")
        if action == "image":
            return f"https://cactus.nci.nih.gov/chemical/structure/{encoded}/image"
        endpoint = cls.TEXT_ACTIONS.get(action)
        if not endpoint:
            raise ValueError("action 支持 formula / smiles / names / inchikey / image")
        return await _text_get(
            f"https://cactus.nci.nih.gov/chemical/structure/{encoded}/{endpoint}"
        )


class CodecService:
    @staticmethod
    def run(action: str, kind: str, text: str) -> str:
        return codec(action, kind, text)


class NasaService:
    @staticmethod
    async def apod(date: str | None = None) -> dict:
        params = {"api_key": os.getenv("NASA_API_KEY", "DEMO_KEY")}
        if date:
            params["date"] = date.strip()
        data = await _json_get("https://api.nasa.gov/planetary/apod", params=params)
        return {
            "date": data.get("date", ""),
            "title": data.get("title", ""),
            "explanation": data.get("explanation", ""),
            "media_type": data.get("media_type", ""),
            "url": data.get("hdurl") or data.get("url") or "",
        }


class BingService:
    @staticmethod
    async def today() -> dict:
        data = await _json_get(
            "https://www.bing.com/HPImageArchive.aspx",
            params={"format": "js", "idx": 0, "n": 1, "mkt": "zh-CN"},
        )
        images = data.get("images", []) if isinstance(data, dict) else []
        if not images:
            raise ServiceError("Bing 未返回壁纸")
        item = images[0]
        url = item.get("url", "")
        if url.startswith("/"):
            url = "https://www.bing.com" + url
        return {"title": item.get("title", ""), "copyright": item.get("copyright", ""), "url": url}


class ChartService:
    @staticmethod
    def url(chart_json: str) -> str:
        # Validate JSON locally so malformed requests fail before reaching QuickChart.
        parsed = json.loads(chart_json)
        compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        if len(compact) > 12000:
            raise ValueError("图表配置过长")
        return "https://quickchart.io/chart?c=" + quote(compact, safe="")
