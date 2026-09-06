from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp
from PIL import Image, UnidentifiedImageError
from astrbot.api import logger

from .vendor.get_px.downloader import (
    ImageDownloader,
    cleanup,
    iter_download_urls,
    pick_image_url_exact,
)
from .vendor.get_px.lolicon import IMAGE_SIZES, LoliconClient


PIXIV_WEB_BASE = "https://www.pixiv.net"
PIXIV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8",
}
WEB_SEARCH_PAGE_SIZE = 60
WEB_PAGE_WINDOW = 8
WEB_DETAIL_CONCURRENCY = 4
WEB_DETAIL_CANDIDATES = 14
WEB_RECOMMEND_SEEDS = 3
WEB_RECOMMEND_LIMIT = 60
MAX_ORIGINAL_BYTES = 20 * 1024 * 1024
MAX_REGULAR_BYTES = 12 * 1024 * 1024


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
    def __init__(self, path: str | Path, keep: int = 400):
        self.path = Path(path)
        self.keep = max(20, int(keep))
        self.data: dict[str, list[str]] = {}
        self.cursors: dict[str, int] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                scopes = raw.get("scopes", {}) if isinstance(raw, dict) else {}
                if isinstance(scopes, dict):
                    self.data = {
                        str(k): [str(x) for x in v if x][-self.keep:]
                        for k, v in scopes.items() if isinstance(v, list)
                    }
                cursors = raw.get("cursors", {}) if isinstance(raw, dict) else {}
                if isinstance(cursors, dict):
                    self.cursors = {
                        str(k): max(0, int(v)) for k, v in cursors.items()
                        if str(v).lstrip("-").isdigit()
                    }
            except Exception:
                self.data = {}
                self.cursors = {}

    def ordered(self, scope: str, candidates: list[dict]) -> list[dict]:
        scope = str(scope or "global")
        seen_set = set(self.data.get(scope, []))
        unique: list[dict] = []
        repeated: list[dict] = []
        used_now: set[str] = set()
        for item in candidates:
            ident = str(item.get("id") or "")
            if not ident or ident in used_now:
                continue
            used_now.add(ident)
            (repeated if ident in seen_set else unique).append(item)
        return unique + repeated

    def remember(self, scope: str, items: list[dict]) -> None:
        if not items:
            return
        scope = str(scope or "global")
        ordered = list(self.data.get(scope, []))
        changed = False
        for item in items:
            ident = str(item.get("id") or "")
            if not ident:
                continue
            if ident in ordered:
                ordered.remove(ident)
            ordered.append(ident)
            changed = True
        if changed:
            self.data[scope] = ordered[-self.keep:]
            self.save()

    def choose(self, scope: str, candidates: list[dict], count: int) -> list[dict]:
        selected = self.ordered(scope, candidates)[:max(1, int(count))]
        self.remember(scope, selected)
        return selected

    def next_page(self, key: str, window: int = WEB_PAGE_WINDOW) -> int:
        key = str(key or "global")
        window = max(1, int(window))
        previous = int(self.cursors.get(key, 0))
        page = previous % window + 1
        self.cursors[key] = page
        self.save()
        return page

    def reset_page(self, key: str, page: int = 1) -> None:
        self.cursors[str(key or "global")] = max(0, int(page))
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {"schema": 2, "scopes": self.data, "cursors": self.cursors},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
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


class PixivWebClient:
    def __init__(self, proxy: str = "", *, request_timeout: float = 12.0):
        self.proxy = str(proxy or "").strip()
        self.request_timeout = float(request_timeout)
        self._session: aiohttp.ClientSession | None = None

    @property
    def available(self) -> bool:
        return bool(self.proxy)

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        referer: str = PIXIV_WEB_BASE + "/",
        timeout: float | None = None,
    ) -> Any:
        if not self.available:
            raise PixivError("Pixiv Web 代理未配置")
        session = self._ensure_session()
        headers = dict(PIXIV_HEADERS)
        headers["Referer"] = referer
        client_timeout = aiohttp.ClientTimeout(total=timeout or self.request_timeout)
        try:
            async with session.get(
                PIXIV_WEB_BASE + path,
                params=params,
                headers=headers,
                proxy=self.proxy,
                timeout=client_timeout,
            ) as resp:
                if resp.status != 200:
                    raise PixivError(f"Pixiv Web HTTP {resp.status}")
                payload = await resp.json(content_type=None)
        except PixivError:
            raise
        except Exception as exc:
            raise PixivError(f"Pixiv Web 请求失败：{type(exc).__name__}") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise PixivError("Pixiv Web 返回格式无效")
        return payload.get("body")

    @staticmethod
    def _as_int(value: object, default: int = 0) -> int:
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _normalize_search(cls, item: dict[str, Any]) -> dict[str, Any]:
        pid = str(item.get("id") or item.get("illustId") or "")
        tags = item.get("tags") or []
        if isinstance(tags, list):
            normalized_tags = [
                {"name": str(x.get("tag") or x.get("name") or "")}
                if isinstance(x, dict) else {"name": str(x)}
                for x in tags
            ]
        else:
            normalized_tags = []
        return {
            "id": f"{pid}:0" if pid else "",
            "pid": pid,
            "page": 0,
            "title": str(item.get("title") or "无标题"),
            "user": {
                "id": str(item.get("userId") or ""),
                "name": str(item.get("userName") or ""),
            },
            "x_restrict": cls._as_int(item.get("xRestrict")),
            "ai_type": cls._as_int(item.get("aiType")),
            "width": cls._as_int(item.get("width")),
            "height": cls._as_int(item.get("height")),
            "tags": normalized_tags,
            "type": "illust",
            "meta_single_page": {"original_image_url": ""},
            "image_urls": {"large": str(item.get("url") or "")},
            "_source": "pixiv-web-search",
        }

    @classmethod
    def _normalize_detail(cls, item: dict[str, Any]) -> dict[str, Any]:
        pid = str(item.get("illustId") or item.get("id") or "")
        tags_obj = item.get("tags") or {}
        tags = tags_obj.get("tags", []) if isinstance(tags_obj, dict) else []
        urls = item.get("urls") or {}
        return {
            "id": f"{pid}:0" if pid else "",
            "pid": pid,
            "page": 0,
            "title": str(item.get("illustTitle") or item.get("title") or "无标题"),
            "user": {
                "id": str(item.get("userId") or ""),
                "name": str(item.get("userName") or ""),
            },
            "x_restrict": cls._as_int(item.get("xRestrict")),
            "ai_type": cls._as_int(item.get("aiType")),
            "width": cls._as_int(item.get("width")),
            "height": cls._as_int(item.get("height")),
            "tags": [
                {"name": str(x.get("tag") or "")}
                for x in tags if isinstance(x, dict)
            ],
            "type": "illust",
            "bookmark_count": cls._as_int(item.get("bookmarkCount")),
            "like_count": cls._as_int(item.get("likeCount")),
            "view_count": cls._as_int(item.get("viewCount")),
            "meta_single_page": {
                "original_image_url": str(urls.get("original") or ""),
            },
            "image_urls": {
                "large": str(urls.get("regular") or ""),
                "medium": str(urls.get("small") or ""),
                "square_medium": str(urls.get("thumb") or urls.get("mini") or ""),
            },
            "_source": "pixiv-web",
        }

    async def _search_body(self, text: str, *, page: int, s_mode: str) -> dict[str, Any]:
        encoded = quote(text, safe="")
        body = await self._json(
            f"/ajax/search/artworks/{encoded}",
            params={
                "word": text,
                "order": "date_d",
                "mode": "all",
                "p": str(max(1, int(page))),
                "s_mode": s_mode,
                "type": "all",
                "lang": "ja",
            },
            referer=f"{PIXIV_WEB_BASE}/tags/{encoded}/artworks",
        )
        if not isinstance(body, dict):
            raise PixivError("Pixiv 搜索返回格式无效")
        return body

    async def search_bundle(
        self, query: str, *, page: int = 1
    ) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
        """Return ordinary search rows plus Pixiv's anonymous popular teaser.

        Exact tag matching is attempted first. If Pixiv has no exact-tag rows,
        fall back to partial tag matching so free-form/niche queries still work.
        """
        text = str(query or "").strip()
        if not text:
            return [], 0, []
        body = await self._search_body(text, page=page, s_mode="s_tag_full")
        illust = body.get("illustManga") or {}
        rows = illust.get("data") or [] if isinstance(illust, dict) else []
        total = self._as_int(illust.get("total") if isinstance(illust, dict) else 0)
        if not rows and total <= 0:
            body = await self._search_body(text, page=page, s_mode="s_tag")
            illust = body.get("illustManga") or {}
            rows = illust.get("data") or [] if isinstance(illust, dict) else []
            total = self._as_int(illust.get("total") if isinstance(illust, dict) else 0)

        popular_obj = body.get("popular") or {}
        popular: list[dict[str, Any]] = []
        if isinstance(popular_obj, dict):
            for name in ("permanent", "recent"):
                values = popular_obj.get(name) or []
                if not isinstance(values, list):
                    continue
                for raw in values:
                    if not isinstance(raw, dict):
                        continue
                    item = self._normalize_search(raw)
                    item["_source"] = "pixiv-web-popular"
                    item["_popular_kind"] = name
                    popular.append(item)

        normal = [self._normalize_search(x) for x in rows if isinstance(x, dict)]
        return normal, total, popular

    async def search(self, query: str, *, page: int = 1) -> tuple[list[dict[str, Any]], int]:
        rows, total, _popular = await self.search_bundle(query, page=page)
        return rows, total

    async def recommend(self, pid: str, *, limit: int = WEB_RECOMMEND_LIMIT) -> list[dict[str, Any]]:
        value = str(pid or "").strip()
        if not value.isdigit():
            return []
        body = await self._json(
            f"/ajax/illust/{value}/recommend/init",
            params={"limit": str(max(1, min(int(limit), 100))), "lang": "ja"},
            referer=f"{PIXIV_WEB_BASE}/artworks/{value}",
            timeout=10.0,
        )
        if not isinstance(body, dict):
            return []
        rows = body.get("illusts") or []
        result = [self._normalize_search(x) for x in rows if isinstance(x, dict)]
        for item in result:
            item["_source"] = "pixiv-web-recommend"
        return result

    async def detail(self, pid: str) -> dict[str, Any]:
        value = str(pid or "").strip()
        if not value.isdigit():
            raise PixivError("Pixiv PID 无效")
        body = await self._json(
            f"/ajax/illust/{value}",
            params={"lang": "ja"},
            referer=f"{PIXIV_WEB_BASE}/artworks/{value}",
            timeout=10.0,
        )
        if not isinstance(body, dict):
            raise PixivError("Pixiv 详情返回格式无效")
        return self._normalize_detail(body)

    async def download_image(
        self,
        url: str,
        *,
        pid: str,
        max_bytes: int,
        timeout: float = 18.0,
    ) -> tuple[str, int]:
        parsed = urlsplit(str(url or ""))
        if parsed.scheme != "https" or (parsed.hostname or "").casefold() != "i.pximg.net":
            raise PixivError("Pixiv 图片 URL 无效")
        session = self._ensure_session()
        headers = dict(PIXIV_HEADERS)
        headers["Referer"] = f"{PIXIV_WEB_BASE}/artworks/{pid}"
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            suffix = ".jpg"
        fd = -1
        path = ""
        try:
            async with session.get(
                url,
                headers=headers,
                proxy=self.proxy,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    raise PixivError(f"Pixiv 图片 HTTP {resp.status}")
                if resp.content_length and resp.content_length > max_bytes:
                    raise PixivError("Pixiv 原图超过发送体积阈值")
                fd, path = tempfile.mkstemp(prefix="doge_pixiv_", suffix=suffix)
                size = 0
                f = os.fdopen(fd, "wb")
                fd = -1
                with f:
                    async for chunk in resp.content.iter_chunked(128 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > max_bytes:
                            raise PixivError("Pixiv 原图超过发送体积阈值")
                        f.write(chunk)
            try:
                with Image.open(path) as image:
                    image.verify()
            except (OSError, UnidentifiedImageError) as exc:
                raise PixivError("Pixiv 图片响应不是有效图片") from exc
            return path, size
        except BaseException:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            cleanup(path)
            raise

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None


class PixivService:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        api_url = os.getenv("DOGE_PIXIV_LOLICON_API", "https://api.lolicon.app/setu/v2").strip()
        self.client = DogeLoliconClient(api_url=api_url, exclude_ai=True, request_timeout=20.0)
        proxy_origins = os.getenv("DOGE_PIXIV_IMAGE_PROXY_ORIGINS", "https://i.pixiv.re")
        self.downloader = ImageDownloader(proxy_origins)
        self.web = PixivWebClient(os.getenv("DOGE_PIXIV_PROXY", ""), request_timeout=12.0)
        self.seen = SeenStore(self.data_dir / "seen.json")

    @staticmethod
    def _hard_allowed(item: dict) -> bool:
        return int(item.get("x_restrict") or 0) == 0 and int(item.get("ai_type") or 0) != 2

    @classmethod
    def _filter(cls, candidates: list[dict]) -> list[dict]:
        rows = []
        for item in candidates:
            if not cls._hard_allowed(item):
                continue
            if not str((item.get("meta_single_page") or {}).get("original_image_url") or ""):
                continue
            rows.append(item)
        return rows

    @staticmethod
    def _tag_key(value: object) -> str:
        text = str(value or "").casefold()
        return re.sub(r"[\s_\-]+", "", text)

    @classmethod
    def _matches_query_tag(cls, item: dict, query: str) -> bool:
        key = cls._tag_key(query)
        if not key:
            return False
        for tag in item.get("tags") or []:
            value = tag.get("name") if isinstance(tag, dict) else tag
            if cls._tag_key(value) == key:
                return True
        return False

    @staticmethod
    def _dedupe_candidates(candidates: list[dict]) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for item in candidates:
            ident = str(item.get("id") or "")
            if not ident or ident in seen:
                continue
            seen.add(ident)
            rows.append(item)
        return rows

    async def _download_lolicon(self, candidates: list[dict], *, count: int, scope: str) -> list[PixivImage]:
        candidates = self._filter(candidates)
        if not candidates:
            raise PixivError("没有找到可用的非 R18、非 AI 插画")
        selected = self.seen.choose(scope, candidates, count)
        results: list[PixivImage] = []
        for item in selected:
            quality_urls = [
                (q, pick_image_url_exact(item, q))
                for q in ("original", "large", "medium")
            ]
            quality_urls = [(q, u) for q, u in quality_urls if u]
            downloaded = None
            for quality, source_url in quality_urls[:3]:
                routes = list(dict.fromkeys(iter_download_urls(
                    source_url, source=item.get("_source"),
                    proxy_origins=self.downloader.lolicon_image_proxy_origins,
                )))
                for url in routes[:2]:
                    try:
                        path, size = await self.downloader.download(url, timeout=12.0)
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

    # Kept as the fallback/download surface used by random and artist routes.
    async def _download(self, candidates: list[dict], *, count: int, scope: str) -> list[PixivImage]:
        return await self._download_lolicon(candidates, count=count, scope=scope)

    async def _enrich_web_candidates(self, candidates: list[dict]) -> list[dict]:
        sem = asyncio.Semaphore(WEB_DETAIL_CONCURRENCY)

        async def one(item: dict) -> dict | None:
            if not self._hard_allowed(item):
                return None
            pid = str(item.get("pid") or "")
            if not pid:
                return None
            async with sem:
                try:
                    detail = await self.web.detail(pid)
                except Exception:
                    return None
            if not self._hard_allowed(detail):
                return None
            if not str((detail.get("meta_single_page") or {}).get("original_image_url") or ""):
                return None
            detail["_selection_source"] = str(item.get("_source") or "pixiv-web-search")
            return detail

        rows = await asyncio.gather(*(one(x) for x in candidates))
        return [x for x in rows if x is not None]

    async def _download_web_item(self, item: dict) -> PixivImage | None:
        pid = str(item.get("pid") or "")
        original = str((item.get("meta_single_page") or {}).get("original_image_url") or "")
        regular = str((item.get("image_urls") or {}).get("large") or "")
        for quality, url, limit in (
            ("original", original, MAX_ORIGINAL_BYTES),
            ("regular", regular, MAX_REGULAR_BYTES),
        ):
            if not url:
                continue
            try:
                path, size = await self.web.download_image(url, pid=pid, max_bytes=limit)
                return PixivImage(Path(path), item, quality, size)
            except Exception:
                continue
        return None

    async def _search_web(self, query: str, *, count: int, scope: str) -> list[PixivImage]:
        key = f"{scope}|search:{query.casefold()}"
        page = self.seen.next_page(key, WEB_PAGE_WINDOW)
        candidates, total, popular = await self.web.search_bundle(query, page=page)
        if not candidates and page != 1:
            self.seen.reset_page(key, 1)
            page = 1
            candidates, total, popular = await self.web.search_bundle(query, page=1)
        if not candidates and not popular:
            raise PixivError("Pixiv 官方搜索没有返回候选")

        max_pages = max(1, min(WEB_PAGE_WINDOW, (max(total, 1) + WEB_SEARCH_PAGE_SIZE - 1) // WEB_SEARCH_PAGE_SIZE))
        if candidates and page > max_pages:
            page = (page - 1) % max_pages + 1
            self.seen.reset_page(key, page)
            candidates, total, popular = await self.web.search_bundle(query, page=page)

        popular = self._dedupe_candidates([x for x in popular if self._hard_allowed(x)])
        permanent = [x for x in popular if str(x.get("_popular_kind") or "permanent") == "permanent"]
        recent = [x for x in popular if str(x.get("_popular_kind") or "") == "recent"]
        latest = self._dedupe_candidates([x for x in candidates if self._hard_allowed(x)])

        # Permanent popular works are Pixiv's strongest anonymous quality prior.
        # Once those are nearly consumed, expand them through Pixiv's own
        # recommender. Recent-popular works remain a freshness tier below those
        # relevant recommendations, but still above the raw newest-first stream.
        seen_ids = set(self.seen.data.get(key, []))
        unseen_permanent = [x for x in permanent if str(x.get("id") or "") not in seen_ids]
        recommended: list[dict] = []
        if popular and len(unseen_permanent) < count:
            seed_key = key + "|recommend-seeds"
            seed_source = permanent or popular
            seed_order = self.seen.ordered(seed_key, seed_source)
            seeds = seed_order[:WEB_RECOMMEND_SEEDS]
            self.seen.remember(seed_key, seeds)
            groups = await asyncio.gather(
                *(self.web.recommend(str(x.get("pid") or ""), limit=WEB_RECOMMEND_LIMIT) for x in seeds),
                return_exceptions=True,
            )
            for group in groups:
                if isinstance(group, Exception):
                    continue
                for item in group:
                    if self._hard_allowed(item) and self._matches_query_tag(item, query):
                        recommended.append(item)
            recommended = self._dedupe_candidates(recommended)

        # Tier order: long-term popular → relevant recommendations → recent
        # popular → raw latest. SeenStore still moves unseen PIDs ahead of repeats.
        pool = self._dedupe_candidates([*permanent, *recommended, *recent, *latest])
        ordered = self.seen.ordered(key, pool)
        enriched = await self._enrich_web_candidates(ordered[:WEB_DETAIL_CANDIDATES])
        if not enriched:
            raise PixivError("Pixiv 官方搜索候选在过滤后为空")

        results: list[PixivImage] = []
        index = 0
        while index < len(enriched) and len(results) < count:
            remaining = count - len(results)
            wave = enriched[index:index + remaining]
            index += len(wave)
            downloaded = await asyncio.gather(*(self._download_web_item(x) for x in wave))
            results.extend(x for x in downloaded if x is not None)
        if not results:
            raise PixivError("Pixiv 官方原图下载失败")
        self.seen.remember(key, [x.item for x in results])
        return results[:count]

    async def search(self, tag: str, *, count: int, scope: str) -> list[PixivImage]:
        query = str(tag or "").strip()
        if not query:
            return await self.random(count=count, scope=scope)
        if self.web.available:
            try:
                return await self._search_web(query, count=count, scope=scope)
            except Exception as exc:
                logger.warning(
                    "doge pixiv web primary degraded, falling back to Lolicon: %s",
                    type(exc).__name__,
                )
        request_count = min(20, max(count * 4, count, 8))
        try:
            candidates = await self.client.search(query, count=request_count)
        except Exception as exc:
            raise PixivError(f"Pixiv Web 与 Lolicon 搜索均失败：{type(exc).__name__}") from exc
        return await self._download_lolicon(
            candidates,
            count=count,
            scope=f"{scope}|lolicon:{query.casefold()}",
        )

    async def random(self, *, count: int, scope: str) -> list[PixivImage]:
        request_count = min(20, max(count * 4, count, 8))
        try:
            candidates = await self.client.random(count=request_count)
        except Exception as exc:
            raise PixivError(f"Lolicon 随机图失败：{type(exc).__name__}") from exc
        return await self._download_lolicon(candidates, count=count, scope=f"{scope}|random")

    async def artist(self, uid: str, *, count: int, scope: str) -> list[PixivImage]:
        request_count = min(20, max(count * 4, count, 8))
        candidates = await self.client.artist(uid, count=request_count)
        return await self._download_lolicon(candidates, count=count, scope=f"{scope}|artist:{uid}")

    async def status(self) -> str:
        if self.web.available:
            try:
                candidates, total, popular = await self.web.search_bundle("初音ミク", page=1)
                safe = sum(1 for x in candidates if self._hard_allowed(x))
                popular_safe = sum(1 for x in popular if self._hard_allowed(x))
                return (
                    "Pixiv primary OK · official Web AJAX via isolated proxy · "
                    f"popular_seeds={popular_safe} page_candidates={len(candidates)} safe={safe} total={total} · "
                    "permanent→recommend→recent→fresh · original CDN first · Lolicon fallback · R18=off · AI=filtered"
                )
            except Exception as exc:
                web_error = type(exc).__name__
        else:
            web_error = "proxy_not_configured"
        try:
            candidates = self._filter(await self.client.random(count=1))
            if not candidates:
                return f"Pixiv Web degraded ({web_error}) · Lolicon reachable but empty · R18=off · AI=filtered"
            return f"Pixiv Web degraded ({web_error}) · Lolicon fallback OK · original-first · R18=off · AI=filtered"
        except Exception as exc:
            return f"Pixiv source degraded · web={web_error} lolicon={type(exc).__name__} · R18=off · AI=filtered"

    async def close(self) -> None:
        await self.web.close()
        await self.client.close()
        await self.downloader.close()

    @staticmethod
    def caption(images: list[PixivImage]) -> str:
        rows = []
        for image in images:
            page = f" p{image.page}" if image.page else ""
            author = image.author + (f" (uid {image.uid})" if image.uid else "")
            rows.append(
                f"#{image.pid}{page} · {image.title}"
                + (f" · {author}" if author else "")
                + f"\nhttps://www.pixiv.net/artworks/{image.pid}"
            )
        return "\n\n".join(rows)
