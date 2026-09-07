from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from curl_cffi import requests

from .lookup import LookupError, LookupService


BASE = "https://chaoli.club"
DEFAULT_PROXY = "socks5h://127.0.0.1:10808"
DAILY_JSON_URL = "https://chaoli.club/index.php/conversations/index.json/all?search=%23%E4%BB%8A%E6%97%A5%E6%B4%BB%E8%B7%83"
DAILY_QUERY = "#今日活跃"
SHANGHAI = ZoneInfo("Asia/Shanghai")
THREAD_RE = re.compile(r"(?:https?://(?:www\.)?chaoli\.club)?/index\.php/(\d+)(?:/(p\d+|\d+|last|unread))?", re.I)
POST_RE = re.compile(r"(?:https?://(?:www\.)?chaoli\.club)?/index\.php/conversation/post/(\d+)", re.I)
POST_ANCHOR_RE = re.compile(r"(?:^|#)p(\d+)(?:$|[^0-9])", re.I)
MEMBER_RE = re.compile(r"(?:https?://(?:www\.)?chaoli\.club)?/index\.php/member/(\d+)", re.I)

CHANNELS = {
    "all": "all", "全部": "all",
    "math": "maths", "maths": "maths", "数学": "maths",
    "physics": "physics", "物理": "physics",
    "chem": "chem", "chemistry": "chem", "化学": "chem",
    "bio": "biology", "biology": "biology", "生物": "biology",
    "tech": "tech", "技术": "tech", "计算机": "tech",
    "others": "others", "其他": "others",
    "admin": "admin", "站务": "admin",
    "lang": "lang", "language": "lang", "语言": "lang",
    "soc": "soc-sci", "social": "soc-sci", "社科": "soc-sci",
    "sci-fi": "sci-fi", "科幻": "sci-fi",
    "collections": "collections", "合集": "collections",
}


class ChaoliError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThreadCard:
    thread_id: int
    title: str
    excerpt: str
    channel: str
    channel_slug: str
    author: str
    author_id: int | None
    started: str
    last_author: str
    last_author_id: int | None
    updated: str
    replies: str
    url: str
    crc: str = ""

    def line(self) -> str:
        meta = []
        if self.channel:
            meta.append(f"板块：{self.channel}")
        if self.author:
            meta.append(f"发帖：{self.author}" + (f"（member/{self.author_id}）" if self.author_id else ""))
        if self.started:
            meta.append(f"发表于：{self.started}")
        if self.last_author:
            meta.append(f"最后回复：{self.last_author}" + (f"（member/{self.last_author_id}）" if self.last_author_id else ""))
        if self.updated:
            meta.append(f"更新于：{self.updated}")
        if self.replies:
            meta.append(f"回复：{self.replies}")
        # Do not expose the list-page excerpt here. It can contain flattened
        # quotations and is not safe enough for author-level attribution.
        return f"#{self.thread_id} {self.title}" + ("\n" + " · ".join(meta) if meta else "") + f"\n{self.url}"


@dataclass(frozen=True)
class Quote:
    author: str
    text: str


@dataclass(frozen=True)
class Floor:
    number: int
    author: str
    author_id: int | None
    time: str
    text: str
    quotes: tuple[Quote, ...]
    url: str
    deleted: bool = False

    def line(self, *, max_chars: int = 1600) -> str:
        head = f"{self.number}楼" + (f" · {self.author}" if self.author else "") + (f"（member/{self.author_id}）" if self.author_id else "") + (f" · {self.time}" if self.time else "")
        if self.deleted:
            return f"{head}\n〔该楼已删除；公开页无正文〕\n{self.url}"
        parts = [head]
        for q in self.quotes[:3]:
            qtext = q.text if len(q.text) <= 360 else q.text[:359].rstrip() + "…"
            parts.append(f"引用{(' @' + q.author) if q.author else ''}：{qtext}")
        body = self.text if len(self.text) <= max_chars else self.text[: max_chars - 1].rstrip() + "…"
        if self.quotes:
            parts.append("本层正文：" + (body or "〔无可抽取文本，可能只有附件/图片〕"))
        else:
            parts.append(body or "〔无可抽取文本，可能只有附件/图片〕")
        parts.append(self.url)
        return "\n".join(parts)


class ChaoliService:
    proxy = os.getenv("DOGE_CHAOLI_PROXY", DEFAULT_PROXY).strip()
    timeout = 18

    @classmethod
    def _get_sync(cls, path_or_url: str) -> str:
        url = path_or_url if path_or_url.startswith("http") else urljoin(BASE, path_or_url)
        parsed = urlparse(url)
        if parsed.hostname not in {"chaoli.club", "www.chaoli.club"}:
            raise ChaoliError("只允许读取 chaoli.club")
        kwargs = {"impersonate": "chrome", "timeout": cls.timeout, "allow_redirects": True}
        if cls.proxy:
            kwargs["proxy"] = cls.proxy
        try:
            resp = requests.get(url, **kwargs)
        except Exception as exc:
            raise ChaoliError(f"超理连接失败：{exc}") from exc
        if resp.status_code != 200:
            title = ""
            try:
                soup = BeautifulSoup(resp.text, "lxml")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
            except Exception:
                pass
            if resp.status_code == 403 and "Just a moment" in title:
                raise ChaoliError("该页面触发了 Cloudflare 验证；此入口暂不作为稳定能力")
            raise ChaoliError(f"超理返回 HTTP {resp.status_code}" + (f"（{title}）" if title else ""))
        return resp.text

    @classmethod
    async def _get(cls, path_or_url: str) -> str:
        return await asyncio.to_thread(cls._get_sync, path_or_url)

    @classmethod
    def _search_sync(cls, query: str, channel: str = "all") -> str:
        raw_channel = str(channel or "all").strip()
        slug = cls._channel_slug(raw_channel)
        proxy = cls.proxy
        session = requests.Session(impersonate="chrome")
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}
        board_url = f"{BASE}/" if slug == "all" else f"{BASE}/index.php/conversations/{slug}/"
        try:
            landing = session.get(
                board_url,
                timeout=cls.timeout,
                allow_redirects=True,
                headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
            )
        except Exception as exc:
            raise ChaoliError(f"超理搜索初始化失败：{exc}") from exc
        if landing.status_code != 200:
            raise ChaoliError(f"超理搜索初始化返回 HTTP {landing.status_code}")
        # ET is a large nested inline object; do not parse it as one regex JSON
        # blob. Search only the stable scalar fields used by $.ETAjax.
        head_pos = landing.text.find("var ET=")
        window = landing.text[head_pos : head_pos + 12000] if head_pos >= 0 else ""
        token_m = re.search(r'"token"\s*:\s*"([^"\\]+)"', window)
        path_m = re.search(r'"webPath"\s*:\s*"([^"\\]+)"', window)
        token = token_m.group(1) if token_m else ""
        web_path = (path_m.group(1).replace(r"\/", "/") if path_m else "/index.php")
        if not token or not web_path.startswith("/"):
            raise ChaoliError("超理页面缺少 AJAX 会话参数")
        url = f"{BASE}{web_path}/?p=conversations/index.ajax/{slug}"
        data = {"search": query, "token": token}
        try:
            resp = session.post(
                url,
                data=data,
                timeout=cls.timeout,
                allow_redirects=True,
                headers={
                    "Referer": landing.url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
        except Exception as exc:
            raise ChaoliError(f"超理搜索连接失败：{exc}") from exc
        if resp.status_code != 200:
            title = ""
            try:
                soup = BeautifulSoup(resp.text, "lxml")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
            except Exception:
                pass
            if resp.status_code == 403 and "Just a moment" in title:
                raise ChaoliError("超理搜索触发了 Cloudflare 验证")
            raise ChaoliError(f"超理搜索返回 HTTP {resp.status_code}" + (f"（{title}）" if title else ""))
        try:
            payload = resp.json()
        except Exception as exc:
            raise ChaoliError("超理搜索返回了无法解析的数据") from exc
        if not isinstance(payload, dict):
            raise ChaoliError("超理搜索返回格式异常")
        messages = payload.get("messages") or []
        if messages:
            text = "；".join(str(x) for x in messages if x)
            if text:
                raise ChaoliError(f"超理搜索失败：{text[:500]}")
        view = payload.get("view")
        if not isinstance(view, str):
            raise ChaoliError("超理搜索结果缺少帖子列表")
        return view

    @classmethod
    async def _search(cls, query: str, channel: str = "all") -> str:
        return await asyncio.to_thread(cls._search_sync, query, channel)

    @staticmethod
    def _channel_catalog(html: str) -> dict[str, tuple[str, str]]:
        """Map numeric channel ids to (slug, display name) from the live page."""
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, tuple[str, str]] = {}
        valid_slugs = set(CHANNELS.values())
        for li in soup.select("#channelList li[id^='channel-']"):
            ident = str(li.get("id") or "")
            match = re.fullmatch(r"channel-(\d+)", ident)
            a = li.select_one(".info > a[href*='/conversations/']")
            if not match or a is None:
                continue
            href = str(a.get("href") or "")
            slug_match = re.search(r"/conversations/([^/?#]+)", href)
            slug = slug_match.group(1) if slug_match else ""
            if slug in valid_slugs:
                out[match.group(1)] = (slug, ChaoliService._text(a))
        for a in soup.select("#channels a[data-channel]"):
            slug = str(a.get("data-channel") or "").strip()
            if slug not in valid_slugs or slug == "all":
                continue
            for clsname in a.get("class") or []:
                match = re.fullmatch(r"channel-(\d+)", str(clsname))
                if match:
                    out.setdefault(match.group(1), (slug, ChaoliService._text(a)))
                    break
        return out

    @staticmethod
    def _timestamp_text(value) -> str:
        try:
            ts = int(value)
        except Exception:
            return ""
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts, SHANGHAI).strftime("%Y-%m-%d %H:%M")

    @classmethod
    def _parse_json_cards(cls, payload: dict, catalog: dict[str, tuple[str, str]], limit: int = 30) -> list[ThreadCard]:
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise ChaoliError("超理 #今日活跃 JSON 缺少 results")
        rows: list[ThreadCard] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            tid_raw = str(item.get("conversationId") or "")
            channel_id = str(item.get("channelId") or "")
            if not tid_raw.isdigit() or channel_id not in catalog:
                continue
            # The daily feed is public-only. Do not surface a row if the endpoint
            # ever starts returning a private conversation marker.
            if str(item.get("private") or "0") not in {"", "0"}:
                continue
            tid = int(tid_raw)
            slug, channel = catalog[channel_id]
            title = str(item.get("title") or "").strip()
            author = str(item.get("startMember") or "").strip()
            last_author = str(item.get("lastPostMember") or "").strip()
            try:
                author_id = int(item.get("startMemberId")) if str(item.get("startMemberId") or "").isdigit() else None
                last_author_id = int(item.get("lastPostMemberId")) if str(item.get("lastPostMemberId") or "").isdigit() else None
            except Exception:
                author_id = last_author_id = None
            replies_value = item.get("replies")
            if replies_value is None:
                try:
                    replies_value = max(0, int(item.get("countPosts") or 1) - 1)
                except Exception:
                    replies_value = ""
            replies = str(replies_value if replies_value is not None else "")
            if not title or not author:
                continue
            started = cls._timestamp_text(item.get("startTime"))
            updated = cls._timestamp_text(item.get("lastPostTime"))
            crc = f"{item.get('lastPostTime') or ''}:{item.get('lastPostMemberId') or ''}:{replies}"
            rows.append(ThreadCard(
                tid, title, str(item.get("firstPost") or ""), channel, slug,
                author, author_id, started, last_author, last_author_id,
                updated, replies, f"{BASE}/index.php/{tid}", crc,
            ))
            if len(rows) >= max(1, min(int(limit), 30)):
                break
        if not rows:
            raise ChaoliError("超理 #今日活跃 JSON 没有可强绑定的公开主题")
        return rows

    @classmethod
    def _daily_json_sync(cls) -> tuple[dict, dict[str, tuple[str, str]]]:
        """POST the forum-owner recommended ``#今日活跃`` JSON endpoint.

        The query-string GET is challenged by Cloudflare on server egress, while
        the same official ``conversations/index.json/all`` endpoint works through
        its native session/token POST flow. Keep the exact owner-provided URL as
        the canonical endpoint reference, but submit ``search=#今日活跃`` as form
        data after obtaining the current ET token.
        """
        proxy = cls.proxy
        session = requests.Session(impersonate="chrome")
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}
        try:
            landing = session.get(
                f"{BASE}/index.php/channels",
                timeout=cls.timeout,
                allow_redirects=True,
                headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
            )
        except Exception as exc:
            raise ChaoliError(f"超理 #今日活跃 JSON 初始化失败：{exc}") from exc
        if landing.status_code != 200:
            raise ChaoliError(f"超理 #今日活跃 JSON 初始化返回 HTTP {landing.status_code}")
        head_pos = landing.text.find("var ET=")
        window = landing.text[head_pos : head_pos + 12000] if head_pos >= 0 else ""
        token_m = re.search(r'"token"\s*:\s*"([^"\\]+)"', window)
        token = token_m.group(1) if token_m else ""
        catalog = cls._channel_catalog(landing.text)
        if not token or not catalog:
            raise ChaoliError("超理 #今日活跃 JSON 缺少 AJAX token 或板块映射")
        parsed = urlparse(DAILY_JSON_URL)
        post_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        try:
            resp = session.post(
                post_url,
                data={"search": DAILY_QUERY, "token": token},
                timeout=cls.timeout,
                allow_redirects=True,
                headers={
                    "Referer": landing.url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
        except Exception as exc:
            raise ChaoliError(f"超理 #今日活跃 JSON 连接失败：{exc}") from exc
        if resp.status_code != 200:
            title = ""
            try:
                soup = BeautifulSoup(resp.text, "lxml")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
            except Exception:
                pass
            if resp.status_code == 403 and "Just a moment" in title:
                raise ChaoliError("超理 #今日活跃 JSON POST 触发 Cloudflare 验证")
            raise ChaoliError(f"超理 #今日活跃 JSON 返回 HTTP {resp.status_code}" + (f"（{title}）" if title else ""))
        try:
            payload = resp.json()
        except Exception as exc:
            raise ChaoliError("超理 #今日活跃 JSON 返回了无法解析的数据") from exc
        if not isinstance(payload, dict):
            raise ChaoliError("超理 #今日活跃 JSON 返回格式异常")
        messages = payload.get("messages") or []
        if messages:
            text = "；".join(str(x) for x in messages if x)
            if text:
                raise ChaoliError(f"超理 #今日活跃 JSON 失败：{text[:500]}")
        return payload, catalog

    @classmethod
    async def daily_json_cards(cls, limit: int = 30) -> list[ThreadCard]:
        payload, catalog = await asyncio.to_thread(cls._daily_json_sync)
        return cls._parse_json_cards(payload, catalog, limit)

    @classmethod
    async def daily_native_cards(cls, limit: int = 30) -> list[ThreadCard]:
        view = await cls._search(DAILY_QUERY, "all")
        return cls._parse_cards(view, limit, include_sticky=True, expected_channel="all")

    @classmethod
    async def daily(cls, limit: int = 20) -> str:
        """Direct forum-owner daily source only; plugin layer owns pool fallback."""
        cards = await cls.daily_json_cards(limit)
        rows = [f"#{c.thread_id} [{c.channel}] {c.title}" + (f" · 最后回复：{c.last_author}" if c.last_author else "") + f"\n{c.url}" for c in cards]
        return "超理 · 今日活跃 · 坛主推荐 #今日活跃 JSON\n\n" + "\n\n".join(rows)

    @staticmethod
    def _text(node) -> str:
        return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""

    @classmethod
    def _channel_slug(cls, value: str | None) -> str:
        raw = str(value or "all").strip()
        key = raw.casefold()
        slug = CHANNELS.get(key) or CHANNELS.get(raw)
        if slug is None or slug not in set(CHANNELS.values()):
            raise ChaoliError(f"未知板块：{raw or '空'}")
        return slug

    @classmethod
    def _member_anchor(cls, node) -> tuple[int | None, str]:
        if node is None:
            return None, ""
        href = str(node.get("href") or "")
        m = MEMBER_RE.search(urljoin(BASE, href))
        name = cls._text(node)
        return (int(m.group(1)), name) if m and name else (None, "")

    @classmethod
    def _own_text_and_quotes(cls, body) -> tuple[str, tuple[Quote, ...]]:
        if body is None:
            return "", ()
        # A post may embed a separately attributed "best answer" card inside
        # its .postBody. That nested answer is forum UI/content from another
        # post, not part of the current floor. Remove it before both quote and
        # own-body extraction so attribution stays exact.
        cleaned = BeautifulSoup(str(body), "lxml")
        root = cleaned.select_one(".postBody") or cleaned.body or cleaned
        for embedded in root.select(".embedded-answer"):
            embedded.decompose()

        quotes: list[Quote] = []
        for block in root.select("blockquote"):
            cite = block.select_one("cite a.link-member[href], cite a[href*='/member/']")
            qauthor = cls._text(cite).lstrip("@").strip() if cite else ""
            clone = BeautifulSoup(str(block), "lxml")
            for x in clone.select("cite, .controls.postRef"):
                x.decompose()
            qtext = cls._text(clone)
            if qtext:
                quotes.append(Quote(qauthor, qtext))
        for block in root.select("blockquote"):
            block.decompose()
        return cls._text(root), tuple(quotes)

    @classmethod
    def _parse_cards(cls, html: str, limit: int = 12, *, include_sticky: bool = False, expected_channel: str | None = None) -> list[ThreadCard]:
        soup = BeautifulSoup(html, "lxml")
        rows: list[ThreadCard] = []
        expected = None if expected_channel in {None, "all"} else cls._channel_slug(expected_channel)
        for li in soup.select("li[id^='c']"):
            if not include_sticky and "label-sticky" in (li.get("class") or []):
                continue
            ident = str(li.get("id") or "")
            if not ident[1:].isdigit():
                continue
            tid = int(ident[1:])
            link = li.select_one(".col-conversation > strong.title > a[href]")
            if not link:
                continue
            href = str(link.get("href") or "")
            tm = THREAD_RE.search(urljoin(BASE, href))
            if not tm or int(tm.group(1)) != tid:
                continue

            channel_link = li.select_one(".col-channel > a.channel[data-channel][href]")
            channel_slug = str(channel_link.get("data-channel") or "").strip() if channel_link else ""
            if channel_slug not in set(CHANNELS.values()):
                continue
            if expected and channel_slug != expected:
                continue
            channel = cls._text(channel_link)

            actions = li.select(".col-lastPost > span.action")
            author_id = last_author_id = None
            author = started = last_author = updated = ""
            if actions:
                author_id, author = cls._member_anchor(actions[0].select_one(".firstPostMember > a[href*='/member/']"))
                started = cls._text(actions[0].select_one(".startTime"))
            if len(actions) >= 2:
                last_author_id, last_author = cls._member_anchor(actions[1].select_one(".lastPostMember > a[href*='/member/']"))
                last_time = actions[1].select_one("a.lastPostTime[href]")
                if last_time:
                    lm = THREAD_RE.search(urljoin(BASE, str(last_time.get("href") or "")))
                    if lm and int(lm.group(1)) == tid:
                        updated = cls._text(last_time)

            replies = ""
            reply_link = li.select_one(".col-replies a[href]")
            if reply_link:
                rm = THREAD_RE.search(urljoin(BASE, str(reply_link.get("href") or "")))
                if rm and int(rm.group(1)) == tid:
                    replies = cls._text(reply_link)

            rows.append(ThreadCard(
                tid, cls._text(link), cls._text(li.select_one(".excerpt")),
                channel, channel_slug, author, author_id, started,
                last_author, last_author_id, updated, replies, urljoin(BASE, href),
                str(li.get("data-crc") or "").strip(),
            ))
            if len(rows) >= max(1, min(limit, 30)):
                break
        if not rows:
            raise ChaoliError("没有解析到可强绑定的帖子列表")
        return rows

    @classmethod
    async def status(cls) -> str:
        html = await cls._get("/")
        soup = BeautifulSoup(html, "lxml")
        title = cls._text(soup.title) if soup.title else ""
        if "超理论坛" not in title:
            raise ChaoliError("代理链可连接，但返回页面不是超理论坛")
        return f"Chaoli transport OK · {title} · selective proxy active"

    @classmethod
    async def search(cls, query: str, channel: str = "all", limit: int = 10) -> str:
        query = str(query or "").strip()
        if not query:
            raise ChaoliError("缺少搜索词")
        raw_channel = str(channel or "all").strip()
        slug = cls._channel_slug(raw_channel)
        view = await cls._search(query, slug)
        try:
            cards = cls._parse_cards(view, limit, include_sticky=True, expected_channel=slug)
        except ChaoliError as exc:
            if "没有解析到" in str(exc):
                raise ChaoliError(f"没有找到与‘{query}’匹配的帖子") from exc
            raise
        scope = "全部板块" if slug == "all" else cards[0].channel
        return f"超理搜索 · {query} · {scope}\n\n" + "\n\n".join(x.line() for x in cards)

    @classmethod
    async def latest_cards(cls, channel: str = "all", limit: int = 10) -> list[ThreadCard]:
        """Return strongly-bound cards for polling/subscription code without reparsing display text."""
        slug = cls._channel_slug(channel)
        path = "/" if slug == "all" else f"/index.php/conversations/{slug}/"
        return cls._parse_cards(await cls._get(path), limit, expected_channel=slug)

    @classmethod
    async def latest(cls, channel: str = "all", limit: int = 10) -> str:
        slug = cls._channel_slug(channel)
        cards = await cls.latest_cards(slug, limit)
        title = "超理 · 最新" if slug == "all" else f"超理 · {cards[0].channel}"
        return title + "\n\n" + "\n\n".join(x.line() for x in cards)

    @staticmethod
    def parse_thread_ref(value: str) -> tuple[int, str | None]:
        value = value.strip()
        if value.isdigit():
            return int(value), None
        if value.lower().startswith(("http://", "https://")):
            host = (urlparse(value).hostname or "").lower()
            if host not in {"chaoli.club", "www.chaoli.club"}:
                raise ChaoliError("只允许 chaoli.club 帖子链接")
        m = THREAD_RE.search(value)
        if not m:
            raise ChaoliError("需要帖子号或 chaoli.club 帖子链接")
        return int(m.group(1)), m.group(2)

    @staticmethod
    def _post_id_from_ref(value: str) -> int | None:
        raw = str(value or "").strip()
        parsed = urlparse(raw) if raw.lower().startswith(("http://", "https://")) else None
        fragment = parsed.fragment if parsed else ""
        match = POST_ANCHOR_RE.search("#" + fragment if fragment else raw)
        if match:
            return int(match.group(1))
        match = POST_RE.search(raw)
        return int(match.group(1)) if match else None

    @classmethod
    def _fetch_exact_ref_sync(cls, value: str) -> tuple[int, int | None, str, str]:
        """Fetch an exact thread-page/post permalink and keep its final URL.

        This is essential for links like /12179/p2#p102981: the requested post
        is physically absent from page 1, so resolving only the thread id loses
        the locator even though the public page is readable.
        """
        raw = str(value or "").strip()
        url = raw if raw.lower().startswith(("http://", "https://")) else urljoin(BASE, raw)
        parsed = urlparse(url)
        if parsed.hostname not in {"chaoli.club", "www.chaoli.club"}:
            raise ChaoliError("只允许 chaoli.club 帖子链接")
        kwargs = {"impersonate": "chrome", "timeout": cls.timeout, "allow_redirects": True}
        if cls.proxy:
            kwargs["proxy"] = cls.proxy
        try:
            resp = requests.get(url, **kwargs)
        except Exception as exc:
            raise ChaoliError(f"超理楼层链接解析失败：{exc}") from exc
        if resp.status_code != 200:
            raise ChaoliError(f"超理楼层链接返回 HTTP {resp.status_code}")
        final = str(resp.url or url)
        thread_match = THREAD_RE.search(final) or THREAD_RE.search(url)
        if not thread_match:
            raise ChaoliError("超理楼层链接没有解析到所属主题")
        post_id = cls._post_id_from_ref(final) or cls._post_id_from_ref(url)
        return int(thread_match.group(1)), post_id, resp.text, final

    @classmethod
    async def _fetch_exact_ref(cls, value: str) -> tuple[int, int | None, str, str]:
        return await asyncio.to_thread(cls._fetch_exact_ref_sync, value)

    @classmethod
    def _parse_thread(cls, html: str, thread_id: int) -> tuple[str, list[Floor]]:
        soup = BeautifulSoup(html, "lxml")
        title = re.sub(r"\s*-\s*超理论坛\s*$", "", cls._text(soup.title)) if soup.title else ""
        floors: list[Floor] = []
        for post in soup.select(".post[data-id]"):
            header = post.select_one(".postHeader > .info")
            if header is None:
                continue
            floor_span = next((x for x in header.find_all("span", recursive=False) if re.fullmatch(r"\s*\d+楼\s*", cls._text(x))), None)
            if floor_span is None:
                continue
            fm = re.search(r"(\d+)楼", cls._text(floor_span))
            if not fm:
                continue
            number = int(fm.group(1))
            author_id, author = cls._member_anchor(header.select_one("h3 > a[href*='/member/']"))
            time_node = header.select_one("a.time[href*='/conversation/post/']")
            time = (str(time_node.get("title") or "").strip() or cls._text(time_node)) if time_node else ""
            post_id = str(post.get("data-id") or "")
            anchor = str(post.get("id") or "")
            if anchor and anchor != f"p{post_id}":
                continue
            # The post permalink redirects to the correct pagination before
            # applying the anchor; thread#anchor is broken for posts on p2+.
            url = f"{BASE}/index.php/conversation/post/{post_id}"
            deleted = "deleted" in (post.get("class") or [])
            body = post.select_one(".postBody")
            own_text, quotes = cls._own_text_and_quotes(body) if body else ("", ())
            floors.append(Floor(number, author, author_id, time, own_text, quotes, url, deleted))
        floors.sort(key=lambda x: x.number)
        if not floors:
            raise ChaoliError("没有解析到可强绑定的楼层")
        return title or f"帖子 #{thread_id}", floors

    @classmethod
    def _floor_number_for_post_id(cls, html: str, post_id: int) -> int | None:
        post = BeautifulSoup(html, "lxml").select_one(f".post[data-id='{int(post_id)}']")
        if post is None:
            return None
        header = post.select_one(".postHeader > .info")
        if header is None:
            return None
        for span in header.find_all("span", recursive=False):
            match = re.fullmatch(r"\s*(\d+)楼\s*", cls._text(span))
            if match:
                return int(match.group(1))
        return None

    @classmethod
    async def read(cls, value: str, floor: int | None = None, context: int = 0) -> str:
        raw = str(value or "").strip()
        post_id = cls._post_id_from_ref(raw)
        exact_page = bool(
            raw.lower().startswith(("http://", "https://"))
            and (post_id is not None or re.search(r"/p\d+(?:#|$)", urlparse(raw).path + ("#" + urlparse(raw).fragment if urlparse(raw).fragment else ""), re.I))
        )
        if exact_page or POST_RE.search(raw):
            thread_id, resolved_post_id, html, resolved_url = await cls._fetch_exact_ref(raw)
            post_id = post_id or resolved_post_id
            suffix = None
        else:
            thread_id, suffix = cls.parse_thread_ref(raw)
            html = await cls._get(f"/index.php/{thread_id}")
            resolved_url = f"{BASE}/index.php/{thread_id}"
        if floor is None and suffix and suffix.isdigit():
            floor = int(suffix)
        title, floors = cls._parse_thread(html, thread_id)
        if floor is None and post_id is not None:
            target = f"/conversation/post/{post_id}"
            matched = next((x for x in floors if x.url.endswith(target)), None)
            if matched is None:
                raise ChaoliError(f"当前分页没有找到楼层锚点 p{post_id}")
            floor = matched.number
        if floor is None:
            if len(floors) > 12:
                head = "\n\n".join(x.line(max_chars=1100) for x in floors[:6])
                omitted = len(floors) - 9
                middle = f"……当前页中间 {omitted} 楼省略；可用具体楼层链接或 /chaoli context {thread_id} <楼层> 查看。"
                tail = "\n\n".join(x.line(max_chars=1100) for x in floors[-3:])
                body = head + "\n\n" + middle + "\n\n" + tail
            else:
                body = "\n\n".join(x.line(max_chars=1100) for x in floors)
            max_floor = max(x.number for x in floors)
            return f"{title} · #{thread_id} · 当前页最高 {max_floor}楼\n{resolved_url}\n\n" + body
        pos = next((i for i, x in enumerate(floors) if x.number == floor), None)
        if pos is None:
            raise ChaoliError(f"当前分页没有找到 {floor} 楼；有具体楼层链接时请直接传原始链接")
        radius = max(0, min(int(context), 3))
        lo, hi = max(0, pos - radius), min(len(floors), pos + radius + 1)
        return f"{title} · #{thread_id} · 定位 {floor}楼\n{resolved_url}\n\n" + "\n\n".join(x.line(max_chars=1800) for x in floors[lo:hi])



    @classmethod
    async def outline(cls, value: str, limit: int = 40) -> str:
        thread_id, _ = cls.parse_thread_ref(value)
        title, floors = cls._parse_thread(await cls._get(f"/index.php/{thread_id}"), thread_id)
        rows = []
        for x in floors[: max(1, min(limit, 80))]:
            preview = "〔已删除〕" if x.deleted else (x.text[:180].rstrip() + ("…" if len(x.text) > 180 else ""))
            author = x.author or "作者未能强绑定"
            rows.append(f"{x.number}楼 · {author} · {x.time}\n{preview}")
        tail = "" if len(floors) <= len(rows) else f"\n\n……共 {len(floors)} 楼，可用 /chaoli context {thread_id} <楼层> 深读。"
        return f"{title} · #{thread_id} · 楼层提纲\n{BASE}/index.php/{thread_id}\n\n" + "\n\n".join(rows) + tail

    @classmethod
    async def links(cls, value: str, limit: int = 12) -> str:
        thread_id, _ = cls.parse_thread_ref(value)
        html = await cls._get(f"/index.php/{thread_id}")
        soup = BeautifulSoup(html, "lxml")
        seen: set[int] = {thread_id}
        rows: list[str] = []
        for a in soup.select(".postBody a[href]"):
            href = str(a.get("href") or "")
            m = THREAD_RE.search(href if href.startswith("http") else urljoin(BASE, href))
            if not m:
                continue
            tid = int(m.group(1))
            if tid in seen:
                continue
            seen.add(tid)
            label = cls._text(a) or f"帖子 #{tid}"
            rows.append(f"#{tid} {label}\n{BASE}/index.php/{tid}")
            if len(rows) >= max(1, min(limit, 30)):
                break
        return (f"帖子 #{thread_id} 的超理引用\n\n" + "\n\n".join(rows)) if rows else f"帖子 #{thread_id} 没有发现其他超理帖子链接。"

    @staticmethod
    def _member_key(value: str) -> str:
        return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()

    @classmethod
    def _member_links(cls, html: str) -> list[tuple[int, str]]:
        soup = BeautifulSoup(html, "lxml")
        rows: list[tuple[int, str]] = []
        seen: set[int] = set()
        for a in soup.select("a[href*='/index.php/member/']"):
            href = str(a.get("href") or "")
            m = MEMBER_RE.search(urljoin(BASE, href))
            if not m:
                continue
            member_id = int(m.group(1))
            name = cls._text(a)
            if member_id in seen or not name:
                continue
            seen.add(member_id)
            rows.append((member_id, name))
        return rows

    @classmethod
    async def _verify_member_name(cls, member_id: int) -> tuple[int, str] | None:
        try:
            html = await cls._get(f"/index.php/member/{member_id}")
        except ChaoliError:
            return None
        soup = BeautifulSoup(html, "lxml")
        name = re.sub(r"\s*-\s*超理论坛\s*$", "", cls._text(soup.title)) if soup.title else ""
        return (member_id, name) if name else None

    @classmethod
    def _match_member_rows(cls, rows: list[tuple[int, str]], wanted: str) -> tuple[int, str] | None:
        exact = [(mid, name) for mid, name in rows if cls._member_key(name) == wanted]
        unique = {(mid, cls._member_key(name)): (mid, name) for mid, name in exact}
        if len(unique) == 1:
            return next(iter(unique.values()))
        if len(unique) > 1:
            raise ChaoliError("存在多个同名超理用户，不能仅凭用户名唯一定位")
        return None

    @classmethod
    async def _member_from_public_pages(cls, username: str, paths: list[str]) -> tuple[int, str] | None:
        wanted = cls._member_key(username)
        seen: set[str] = set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            try:
                html = await cls._get(path)
            except ChaoliError:
                continue
            hit = cls._match_member_rows(cls._member_links(html), wanted)
            if hit:
                return hit
        return None

    @classmethod
    async def _resolve_member_id(cls, value: str) -> tuple[int, str | None]:
        value = value.strip()
        if value.isdigit():
            return int(value), None
        if value.lower().startswith(("http://", "https://")):
            host = (urlparse(value).hostname or "").lower()
            if host not in {"chaoli.club", "www.chaoli.club"}:
                raise ChaoliError("只允许 chaoli.club 用户链接")
            m = MEMBER_RE.search(value)
            if not m:
                raise ChaoliError("不是有效的超理用户链接")
            return int(m.group(1)), None

        wanted = cls._member_key(value)
        if not wanted:
            raise ChaoliError("缺少用户名")

        try:
            joined = await cls._get("/index.php/members/joined/")
            hit = cls._match_member_rows(cls._member_links(joined), wanted)
            if hit:
                return hit
        except ChaoliError:
            pass

        # Active users are often visible on current public channel pages even
        # when the joined-member directory is login/Cloudflare gated.
        public_paths = [
            "/", "/index.php/conversations/maths/", "/index.php/conversations/physics/",
            "/index.php/conversations/chem/", "/index.php/conversations/biology/",
            "/index.php/conversations/tech/", "/index.php/conversations/others/",
            "/index.php/conversations/lang/", "/index.php/conversations/soc-sci/",
            "/index.php/conversations/sci-fi/", "/index.php/conversations/collections/",
        ]
        hit = await cls._member_from_public_pages(value, public_paths)
        if hit:
            return hit

        try:
            indexed = await LookupService.web_search(f'{value} 超理论坛', 8)
        except LookupError as exc:
            raise ChaoliError(f"用户名定位失败：{exc}") from exc

        # AnySearch may return a board/thread page instead of the profile. Treat
        # those pages only as discovery surfaces, then match the actual member
        # link on Chaoli itself. Direct member hits are also verified below.
        urls: list[str] = []
        for match in re.finditer(r"https?://(?:www\.)?chaoli\.club/[^\s)\]>]+", indexed, re.I):
            url = match.group(0).rstrip('.,;')
            if url not in urls:
                urls.append(url)
        ids: list[int] = []
        page_paths: list[str] = []
        for url in urls[:10]:
            m = MEMBER_RE.search(url)
            if m:
                mid = int(m.group(1))
                if mid not in ids:
                    ids.append(mid)
            else:
                parsed = urlparse(url)
                path = parsed.path + (("?" + parsed.query) if parsed.query else "")
                if path and path not in page_paths:
                    page_paths.append(path)
        hit = await cls._member_from_public_pages(value, page_paths[:6])
        if hit:
            return hit

        verified: list[tuple[int, str]] = []
        for mid in ids[:8]:
            row = await cls._verify_member_name(mid)
            if row:
                verified.append(row)
        hit = cls._match_member_rows(verified, wanted)
        if hit:
            return hit
        raise ChaoliError(f"没有找到用户名‘{value}’对应的超理用户")

    @classmethod
    async def user(cls, value: str, limit: int = 8) -> str:
        member_id, resolved_name = await cls._resolve_member_id(value)
        html = await cls._get(f"/index.php/member/{member_id}")
        soup = BeautifulSoup(html, "lxml")
        name = re.sub(r"\s*-\s*超理论坛\s*$", "", cls._text(soup.title)) if soup.title else ""
        if not name:
            raise ChaoliError("用户页缺少可验证用户名")
        if resolved_name and cls._member_key(name) != cls._member_key(resolved_name):
            raise ChaoliError("用户名与用户页标题不一致，拒绝合并")

        activities: list[str] = []
        for activity in soup.select(".activity"):
            action = activity.select_one(".action")
            action_text = cls._text(action)
            if not action or not cls._member_key(action_text).startswith(cls._member_key(name)):
                continue
            link = action.select_one("a[href*='/conversation/post/']")
            if not link:
                continue
            href = urljoin(BASE, str(link.get("href") or ""))
            if urlparse(href).hostname not in {"chaoli.club", "www.chaoli.club"}:
                continue
            topic = cls._text(link)
            when = cls._text(activity.select_one(".controls > .time"))
            own_text, quotes = cls._own_text_and_quotes(activity.select_one(".activityBody.postBody"))
            parts = [f"{when + ' · ' if when else ''}在《{topic}》中更新"]
            for q in quotes[:2]:
                qtext = q.text if len(q.text) <= 260 else q.text[:259].rstrip() + "…"
                parts.append(f"引用{(' @' + q.author) if q.author else ''}：{qtext}")
            if own_text:
                body = own_text if len(own_text) <= 500 else own_text[:499].rstrip() + "…"
                parts.append("本人新增正文：" + body)
            elif not quotes:
                parts.append("〔该活动无可抽取文本，可能为附件/图片〕")
            parts.append(href)
            activities.append("\n".join(parts))
            if len(activities) >= max(1, min(limit, 20)):
                break

        out = f"{name} · member/{member_id}（用户名已由真实用户页验证）\n{BASE}/index.php/member/{member_id}"
        if activities:
            out += "\n\n近期公开活动（引用与本人新增正文已分离）：\n\n" + "\n\n".join(activities)
        else:
            out += "\n\n没有解析到可与该用户强绑定的公开活动记录。"
        return out

    @classmethod
    async def preview(cls, value: str) -> str:
        raw = str(value or "").strip()
        if cls._post_id_from_ref(raw) is not None:
            return await cls.read(raw, context=0)
        try:
            thread_id, suffix = cls.parse_thread_ref(raw)
        except ChaoliError:
            if POST_RE.search(raw):
                return await cls.read(raw, context=0)
            raise
        if suffix and suffix.isdigit():
            return await cls.read(str(thread_id), int(suffix), 0)
        html = await cls._get(f"/index.php/{thread_id}")
        title, floors = cls._parse_thread(html, thread_id)
        first = next((x for x in floors if not x.deleted), None)
        if first is None:
            return f"{title}\n公开页只有删除占位，未读取到正文。\n{BASE}/index.php/{thread_id}"
        excerpt = first.text[:360] + ("…" if len(first.text) > 360 else "")
        max_floor = max(x.number for x in floors)
        return f"{title}\n首楼作者：{first.author or '未能强绑定'} · 最高 {max_floor}楼\n首楼正文：{excerpt}\n{BASE}/index.php/{thread_id}"
