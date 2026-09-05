from __future__ import annotations

import json
from dataclasses import dataclass

import aiohttp


class MusicError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Song:
    song_id: int
    name: str
    artists: str
    album: str
    duration_ms: int

    @property
    def duration_text(self) -> str:
        seconds = max(0, self.duration_ms // 1000)
        return f"{seconds // 60}:{seconds % 60:02d}"

    @property
    def url(self) -> str:
        return f"https://music.163.com/#/song?id={self.song_id}"


class NetEaseMusicService:
    """Tiny direct NetEase search client.

    Search follows the public route used by community AstrBot music plugins.
    Playback itself is not proxied or downloaded: the QQ transport receives a
    native `music,type=163,id=<song_id>` card and resolves it on its side.
    """

    SEARCH_URL = "https://music.163.com/api/search/get/web"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Referer": "https://music.163.com/",
        "Accept": "application/json,text/plain,*/*",
    }

    def __init__(self, timeout: float = 8.0):
        self.timeout = max(3.0, min(float(timeout), 20.0))
        self._session: aiohttp.ClientSession | None = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.HEADERS)
        return self._session

    @staticmethod
    def parse_search_payload(payload: object, limit: int = 5) -> list[Song]:
        if not isinstance(payload, dict):
            return []
        result = payload.get("result")
        songs = result.get("songs") if isinstance(result, dict) else None
        if not isinstance(songs, list):
            return []
        rows: list[Song] = []
        for raw in songs:
            if not isinstance(raw, dict):
                continue
            try:
                song_id = int(raw.get("id"))
            except (TypeError, ValueError):
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            artists_raw = raw.get("artists") or raw.get("ar") or []
            artist_names = []
            if isinstance(artists_raw, list):
                for artist in artists_raw:
                    if isinstance(artist, dict) and str(artist.get("name") or "").strip():
                        artist_names.append(str(artist["name"]).strip())
            album_raw = raw.get("album") or raw.get("al") or {}
            album = str(album_raw.get("name") or "").strip() if isinstance(album_raw, dict) else ""
            duration_raw = raw.get("duration", raw.get("dt", 0))
            try:
                duration_ms = max(0, int(duration_raw or 0))
            except (TypeError, ValueError):
                duration_ms = 0
            rows.append(Song(song_id, name, " / ".join(artist_names), album, duration_ms))
            if len(rows) >= max(1, min(int(limit), 10)):
                break
        return rows

    async def search(self, query: str, limit: int = 5) -> list[Song]:
        query = " ".join(str(query or "").split()).strip()
        if not query:
            raise MusicError("缺少歌曲名或歌手")
        if len(query) > 120:
            raise MusicError("搜索词太长")
        limit = max(1, min(int(limit), 10))
        session = self._ensure_session()
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        try:
            async with session.post(
                self.SEARCH_URL,
                data={"s": query, "limit": str(limit), "type": "1", "offset": "0"},
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    raise MusicError(f"网易云搜索 HTTP {resp.status}")
                raw = await resp.text()
        except MusicError:
            raise
        except Exception as exc:
            raise MusicError(f"网易云搜索连接失败：{type(exc).__name__}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MusicError("网易云搜索返回格式异常") from exc
        rows = self.parse_search_payload(payload, limit)
        if not rows:
            raise MusicError(f"没有搜到“{query}”")
        return rows

    async def status(self) -> str:
        rows = await self.search("网易云音乐", 1)
        return f"Music source OK · NetEase direct search · native QQ 163 card · probe #{rows[0].song_id}"

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
