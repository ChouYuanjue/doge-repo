from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests

from .lookup import LookupError, LookupService


BASE = "https://chaoli.club"
DEFAULT_PROXY = "socks5h://127.0.0.1:10808"
THREAD_RE = re.compile(r"(?:https?://(?:www\.)?chaoli\.club)?/index\.php/(\d+)(?:/(\d+|last|unread))?", re.I)
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
    author: str
    started: str
    last_author: str
    updated: str
    replies: str
    url: str

    def line(self) -> str:
        meta = " · ".join(x for x in (self.channel, self.author, self.updated, f"{self.replies} 回复" if self.replies else "") if x)
        return f"#{self.thread_id} {self.title}" + (f"\n{meta}" if meta else "") + (f"\n{self.excerpt}" if self.excerpt else "") + f"\n{self.url}"


@dataclass(frozen=True)
class Floor:
    number: int
    author: str
    time: str
    text: str
    url: str

    def line(self, *, max_chars: int = 1600) -> str:
        body = self.text if len(self.text) <= max_chars else self.text[: max_chars - 1].rstrip() + "…"
        head = f"{self.number}楼" + (f" · {self.author}" if self.author else "") + (f" · {self.time}" if self.time else "")
        return f"{head}\n{body}\n{self.url}"


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

    @staticmethod
    def _text(node) -> str:
        return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""

    @classmethod
    def _parse_cards(cls, html: str, limit: int = 12, *, include_sticky: bool = False) -> list[ThreadCard]:
        soup = BeautifulSoup(html, "lxml")
        rows: list[ThreadCard] = []
        for li in soup.select("li[id^='c']"):
            if not include_sticky and "label-sticky" in (li.get("class") or []):
                continue
            ident = str(li.get("id") or "")
            if not ident[1:].isdigit():
                continue
            link = li.select_one("strong.title a[href]")
            if not link:
                continue
            tid = int(ident[1:])
            href = str(link.get("href") or f"/index.php/{tid}")
            channel_link = li.select_one("a.channel[href*='/conversations/']")
            channel = cls._text(channel_link)
            if not channel:
                classes = [x for x in li.get("class", []) if str(x).startswith("channel-")]
                channel = classes[0] if classes else ""
            replies = cls._text(li.select_one(".col-replies"))
            rows.append(ThreadCard(
                tid,
                cls._text(link),
                cls._text(li.select_one(".excerpt")),
                channel,
                cls._text(li.select_one(".firstPostMember")),
                cls._text(li.select_one(".startTime")),
                cls._text(li.select_one(".lastPostMember")),
                cls._text(li.select_one(".lastPostTime")),
                replies,
                urljoin(BASE, href),
            ))
            if len(rows) >= max(1, min(limit, 30)):
                break
        if not rows:
            raise ChaoliError("没有解析到帖子列表")
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
    async def latest(cls, channel: str = "all", limit: int = 10) -> str:
        slug = CHANNELS.get(channel.strip().lower(), CHANNELS.get(channel.strip(), channel.strip().lower() or "all"))
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise ChaoliError("未知板块")
        path = "/" if slug == "all" else f"/index.php/conversations/{slug}/"
        cards = cls._parse_cards(await cls._get(path), limit)
        title = "超理 · 最新" if slug == "all" else f"超理 · {channel}"
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

    @classmethod
    def _parse_thread(cls, html: str, thread_id: int) -> tuple[str, list[Floor]]:
        soup = BeautifulSoup(html, "lxml")
        title = re.sub(r"\s*-\s*超理论坛\s*$", "", cls._text(soup.title)) if soup.title else ""
        floors: list[Floor] = []
        real_posts = [p for p in soup.select(".post") if p.get("data-id") and p.select_one(".postHeader") and p.select_one(".postBody")]
        for idx, post in enumerate(real_posts, start=1):
            header = post.select_one(".postHeader")
            author = cls._text(header.select_one(".info h3 a") if header else None)
            header_text = cls._text(header)
            m = re.search(r"(\d+)楼", header_text)
            number = int(m.group(1)) if m else idx
            time = cls._text(header.select_one("a.time") if header else None)
            body = post.select_one(".postBody")
            text = cls._text(body)
            if not text:
                continue
            anchor = str(post.get("id") or "")
            url = f"{BASE}/index.php/{thread_id}/{number}"
            if anchor:
                url = f"{BASE}/index.php/{thread_id}#{anchor}"
            floors.append(Floor(number, author, time, text, url))
        if not floors:
            raise ChaoliError("没有解析到楼层")
        return title or f"帖子 #{thread_id}", floors

    @classmethod
    async def read(cls, value: str, floor: int | None = None, context: int = 0) -> str:
        thread_id, suffix = cls.parse_thread_ref(value)
        if floor is None and suffix and suffix.isdigit():
            floor = int(suffix)
        title, floors = cls._parse_thread(await cls._get(f"/index.php/{thread_id}"), thread_id)
        if floor is None:
            if len(floors) > 12:
                head = "\n\n".join(x.line(max_chars=1100) for x in floors[:6])
                omitted = len(floors) - 9
                middle = f"……中间 {omitted} 楼省略；可用 /chaoli outline {thread_id} 或 /chaoli context {thread_id} <楼层> 查看。"
                tail = "\n\n".join(x.line(max_chars=1100) for x in floors[-3:])
                body = head + "\n\n" + middle + "\n\n" + tail
            else:
                body = "\n\n".join(x.line(max_chars=1100) for x in floors)
            return f"{title} · #{thread_id} · {len(floors)}楼\n{BASE}/index.php/{thread_id}\n\n" + body
        pos = next((i for i, x in enumerate(floors) if x.number == floor), None)
        if pos is None:
            raise ChaoliError(f"没有找到 {floor} 楼")
        radius = max(0, min(int(context), 3))
        lo, hi = max(0, pos - radius), min(len(floors), pos + radius + 1)
        return f"{title} · #{thread_id}\n\n" + "\n\n".join(x.line(max_chars=1800) for x in floors[lo:hi])


    @classmethod
    async def outline(cls, value: str, limit: int = 40) -> str:
        thread_id, _ = cls.parse_thread_ref(value)
        title, floors = cls._parse_thread(await cls._get(f"/index.php/{thread_id}"), thread_id)
        rows = []
        for x in floors[: max(1, min(limit, 80))]:
            preview = x.text[:180].rstrip() + ("…" if len(x.text) > 180 else "")
            rows.append(f"{x.number}楼 · {x.author or '匿名'} · {x.time}\n{preview}")
        tail = "" if len(floors) <= len(rows) else f"\n\n……共 {len(floors)} 楼，可用 /chaoli context {thread_id} <楼层> 深读。"
        return f"{title} · #{thread_id} · 楼层提纲\n{BASE}/index.php/{thread_id}\n\n" + "\n\n".join(rows) + tail

    @classmethod
    async def links(cls, value: str, limit: int = 12) -> str:
        thread_id, _ = cls.parse_thread_ref(value)
        html = await cls._get(f"/index.php/{thread_id}")
        soup = BeautifulSoup(html, "lxml")
        seen: set[int] = {thread_id}
        rows: list[str] = []
        for a in soup.select("a[href]"):
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
        if exact:
            return exact[0]
        partial = [(mid, name) for mid, name in rows if wanted in cls._member_key(name)]
        if len(partial) == 1:
            return partial[0]
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
        partial = [row for row in verified if wanted in cls._member_key(row[1]) or cls._member_key(row[1]) in wanted]
        if partial:
            names = "、".join(name for _mid, name in partial[:5])
            raise ChaoliError(f"用户名不唯一，候选：{names}")
        raise ChaoliError(f"没有找到用户名‘{value}’对应的超理用户")

    @classmethod
    async def user(cls, value: str, limit: int = 8) -> str:
        member_id, resolved_name = await cls._resolve_member_id(value)
        html = await cls._get(f"/index.php/member/{member_id}")
        soup = BeautifulSoup(html, "lxml")
        name = re.sub(r"\s*-\s*超理论坛\s*$", "", cls._text(soup.title)) if soup.title else (resolved_name or f"用户 {member_id}")
        activities: list[str] = []
        for post in soup.select(".post")[: max(1, min(limit, 20))]:
            body = cls._text(post.select_one(".postBody"))
            if not body:
                continue
            href = ""
            a = post.select_one("a[href*='/index.php/']")
            if a:
                href = urljoin(BASE, str(a.get("href") or ""))
            activities.append((body[:500] + ("…" if len(body) > 500 else "")) + (f"\n{href}" if href else ""))
        if not activities:
            for body in soup.select(".postBody")[: max(1, min(limit, 20))]:
                text = cls._text(body)
                if text:
                    activities.append(text[:500] + ("…" if len(text) > 500 else ""))
        out = f"{name} · member/{member_id}\n{BASE}/index.php/member/{member_id}"
        if activities:
            out += "\n\n近期公开活动：\n\n" + "\n\n".join(activities)
        return out

    @classmethod
    async def preview(cls, value: str) -> str:
        thread_id, suffix = cls.parse_thread_ref(value)
        if suffix and suffix.isdigit():
            return await cls.read(str(thread_id), int(suffix), 0)
        html = await cls._get(f"/index.php/{thread_id}")
        title, floors = cls._parse_thread(html, thread_id)
        first = floors[0]
        excerpt = first.text[:360] + ("…" if len(first.text) > 360 else "")
        return f"{title}\n{first.author} · {len(floors)}楼\n{excerpt}\n{BASE}/index.php/{thread_id}"
