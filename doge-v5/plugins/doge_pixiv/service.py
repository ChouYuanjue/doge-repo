from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from .vendor.get_px.downloader import ImageDownloader, cleanup, iter_download_urls, pick_image_url_exact
from .vendor.get_px.lolicon import IMAGE_SIZES, LoliconClient


class PixivError(RuntimeError):
    pass


class DogeLoliconClient(LoliconClient):
    async def artist(self, uid: str | int, *, count: int = 20) -> list[dict[str, Any]]:
        value = str(uid or "").strip()
        if not value.isdigit():
            raise PixivError("画师 UID 必须是数字")
        params: list[tuple[str, str]] = [
            ("r18", "0"), ("num", str(max(1, min(int(count), 20)))),
            ("excludeAI", "true"), ("uid", value),
        ]
        params.extend(("size", size) for size in IMAGE_SIZES)
        session = self._ensure_session()
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        try:
            async with session.get(self.api_url, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    raise PixivError(f"Lolicon API HTTP {resp.status}")
                payload = await resp.json(content_type=None)
        except PixivError:
            raise
        except Exception as exc:
            raise PixivError(f"Lolicon API 请求失败：{type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise PixivError("Lolicon API 返回格式无效")
        if payload.get("error"):
            raise PixivError(str(payload["error"]))
        return [self._normalize(item) for item in payload.get("data") or []]


class SeenStore:
    def __init__(self, path: str | Path, keep: int = 200):
        self.path = Path(path)
        self.keep = max(20, int(keep))
        self.data: dict[str, list[str]] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                scopes = raw.get("scopes", {}) if isinstance(raw, dict) else {}
                if isinstance(scopes, dict):
                    self.data = {str(k): [str(x) for x in v if x][-self.keep:] for k, v in scopes.items() if isinstance(v, list)}
            except Exception:
                self.data = {}

    def choose(self, scope: str, candidates: list[dict], count: int) -> list[dict]:
        scope = str(scope or "global")
        seen = self.data.get(scope, [])
        seen_set = set(seen)
        unique, repeated, used_now = [], [], set()
        for item in candidates:
            ident = str(item.get("id") or "")
            if not ident or ident in used_now:
                continue
            used_now.add(ident)
            (repeated if ident in seen_set else unique).append(item)
        selected = (unique + repeated)[:max(1, int(count))]
        if selected:
            ordered = list(seen)
            for item in selected:
                ident = str(item.get("id") or "")
                if not ident:
                    continue
                if ident in ordered:
                    ordered.remove(ident)
                ordered.append(ident)
            self.data[scope] = ordered[-self.keep:]
            self.save()
        return selected

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"schema": 1, "scopes": self.data}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)


@dataclass(slots=True)
class PixivImage:
    path: Path
    item: dict
    quality: str
    size_bytes: int

    @property
    def pid(self) -> str: return str(self.item.get("pid") or "")
    @property
    def page(self) -> int: return int(self.item.get("page") or 0)
    @property
    def author(self) -> str: return str((self.item.get("user") or {}).get("name") or "")
    @property
    def uid(self) -> str: return str((self.item.get("user") or {}).get("id") or "")
    @property
    def title(self) -> str: return str(self.item.get("title") or "无标题")


class PixivService:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        api_url = os.getenv("DOGE_PIXIV_LOLICON_API", "https://api.lolicon.app/setu/v2").strip()
        self.client = DogeLoliconClient(api_url=api_url, exclude_ai=True, request_timeout=20.0)
        proxy_origins = os.getenv("DOGE_PIXIV_IMAGE_PROXY_ORIGINS", "https://i.pixiv.re")
        self.downloader = ImageDownloader(proxy_origins)
        self.seen = SeenStore(self.data_dir / "seen.json")

    @staticmethod
    def _filter(candidates: list[dict]) -> list[dict]:
        rows = []
        for item in candidates:
            if int(item.get("x_restrict") or 0) != 0:
                continue
            if int(item.get("ai_type") or 0) == 2:
                continue
            if not str((item.get("meta_single_page") or {}).get("original_image_url") or ""):
                continue
            rows.append(item)
        return rows

    async def _download(self, candidates: list[dict], *, count: int, scope: str) -> list[PixivImage]:
        candidates = self._filter(candidates)
        if not candidates:
            raise PixivError("没有找到可用的非 R18、非 AI 插画")
        selected = self.seen.choose(scope, candidates, count)
        results: list[PixivImage] = []
        for item in selected:
            quality_urls = [(q, pick_image_url_exact(item, q)) for q in ("large", "medium")]
            quality_urls = [(q, u) for q, u in quality_urls if u]
            if not quality_urls:
                original = pick_image_url_exact(item, "original")
                quality_urls = [("original", original)] if original else []
            downloaded = None
            for quality, source_url in quality_urls[:2]:
                routes = list(dict.fromkeys(iter_download_urls(
                    source_url, source=item.get("_source"),
                    proxy_origins=self.downloader.lolicon_image_proxy_origins,
                )))
                for url in routes[:2]:
                    try:
                        path, size = await self.downloader.download(url, timeout=10.0)
                        downloaded = PixivImage(Path(path), item, quality, size)
                        break
                    except Exception:
                        continue
                if downloaded is not None:
                    break
            if downloaded is not None:
                results.append(downloaded)
        if not results:
            raise PixivError("图片元数据已找到，但当前镜像下载失败")
        return results

    async def search(self, tag: str, *, count: int, scope: str) -> list[PixivImage]:
        query = str(tag or "").strip()
        if not query:
            return await self.random(count=count, scope=scope)
        request_count = min(20, max(count * 4, count, 8))
        try:
            candidates = await self.client.search(query, count=request_count)
        except Exception as exc:
            raise PixivError(f"Lolicon 搜索失败：{type(exc).__name__}") from exc
        return await self._download(candidates, count=count, scope=scope)

    async def random(self, *, count: int, scope: str) -> list[PixivImage]:
        request_count = min(20, max(count * 4, count, 8))
        try:
            candidates = await self.client.random(count=request_count)
        except Exception as exc:
            raise PixivError(f"Lolicon 随机图失败：{type(exc).__name__}") from exc
        return await self._download(candidates, count=count, scope=scope)

    async def artist(self, uid: str, *, count: int, scope: str) -> list[PixivImage]:
        request_count = min(20, max(count * 4, count, 8))
        candidates = await self.client.artist(uid, count=request_count)
        return await self._download(candidates, count=count, scope=scope)

    async def status(self) -> str:
        try:
            candidates = self._filter(await self.client.random(count=1))
            if not candidates:
                return "Pixiv source: Lolicon API 可达，但当前没有返回可用图片。R18=off · AI=filtered"
            item = candidates[0]
            url = str((item.get("meta_single_page") or {}).get("original_image_url") or "")
            host = re.sub(r"^https?://([^/]+).*$", r"\1", url) if url else "unknown"
            sizes = [q for q in ("large", "medium", "original") if pick_image_url_exact(item, q)]
            return f"Pixiv source OK · Lolicon API · mirror route {host} · sizes={','.join(sizes)} · R18=off · AI=filtered"
        except Exception as exc:
            return f"Pixiv source degraded · {type(exc).__name__} · R18=off · AI=filtered"

    async def close(self) -> None:
        await self.client.close()
        await self.downloader.close()

    @staticmethod
    def caption(images: list[PixivImage]) -> str:
        rows = []
        for image in images:
            page = f" p{image.page}" if image.page else ""
            author = image.author + (f" (uid {image.uid})" if image.uid else "")
            rows.append(f"#{image.pid}{page} · {image.title}" + (f" · {author}" if author else "") + f"\nhttps://www.pixiv.net/artworks/{image.pid}")
        return "\n\n".join(rows)
