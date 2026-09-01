from __future__ import annotations

import json
import os
import re
from datetime import date as date_type
from urllib.parse import quote, urljoin

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
    def _clean_html(value: str) -> str:
        import html as _html
        value = re.sub(r"<[^>]+>", " ", value or "")
        return re.sub(r"\s+", " ", _html.unescape(value)).strip()

    @classmethod
    async def _apod_page(cls, requested: str | None = None) -> dict:
        if requested:
            try:
                parsed = date_type.fromisoformat(requested.strip())
            except ValueError as exc:
                raise ValueError("APOD 日期使用 YYYY-MM-DD") from exc
            page_url = f"https://apod.nasa.gov/apod/ap{parsed.strftime('%y%m%d')}.html"
        else:
            page_url = "https://apod.nasa.gov/apod/astropix.html"
        body = await _text_get(page_url, timeout=12)
        date_match = re.search(
            r"\b(20\d{2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\b",
            body,
            re.I,
        )
        if date_match:
            import datetime as _dt
            parsed_date = _dt.datetime.strptime(" ".join(date_match.groups()), "%Y %B %d").date().isoformat()
        else:
            parsed_date = requested or ""
        title_match = re.search(r"<center>\s*<b>\s*(.*?)\s*</b>\s*<br", body, re.I | re.S)
        title = cls._clean_html(title_match.group(1)) if title_match else "Astronomy Picture of the Day"
        explanation_match = re.search(
            r"<b>\s*Explanation:\s*</b>(.*?)(?:<p>\s*<center>|<b>\s*Tomorrow|<p>\s*<hr)",
            body,
            re.I | re.S,
        )
        explanation = cls._clean_html(explanation_match.group(1)) if explanation_match else ""
        image_match = re.search(r'<a\s+href=["\']([^"\']+)["\'][^>]*>\s*<img', body, re.I | re.S)
        if image_match:
            media_type = "image"
            media_url = urljoin(page_url, image_match.group(1))
        else:
            frame = re.search(r'<iframe[^>]+src=["\']([^"\']+)', body, re.I | re.S)
            media_type = "video" if frame else ""
            media_url = urljoin(page_url, frame.group(1)) if frame else page_url
        if not explanation and not media_url:
            raise ServiceError("NASA APOD 页面结构无法识别")
        return {
            "date": parsed_date,
            "title": title,
            "explanation": explanation,
            "media_type": media_type,
            "url": media_url,
            "source": "NASA APOD page",
        }

    @classmethod
    async def apod(cls, date: str | None = None) -> dict:
        params = {"api_key": os.getenv("NASA_API_KEY", "DEMO_KEY")}
        if date:
            # Validate before sending the request so the fallback uses the same semantics.
            try:
                date_type.fromisoformat(date.strip())
            except ValueError as exc:
                raise ValueError("APOD 日期使用 YYYY-MM-DD") from exc
            params["date"] = date.strip()
        try:
            data = await _json_get("https://api.nasa.gov/planetary/apod", params=params, timeout=10)
            return {
                "date": data.get("date", ""),
                "title": data.get("title", ""),
                "explanation": data.get("explanation", ""),
                "media_type": data.get("media_type", ""),
                "url": data.get("hdurl") or data.get("url") or "",
                "source": "NASA APOD API",
            }
        except (ServiceError, aiohttp.ClientError, TimeoutError):
            return await cls._apod_page(date)


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
