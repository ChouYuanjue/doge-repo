from __future__ import annotations

import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp

from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.presentation import is_onebot, text_result
from data.plugins.doge_shared.raw_command import command_payload

from .service import MusicError, NetEaseMusicService, Song


HELP = """Doge Music /music
  /music <关键词>              搜索网易云歌曲，返回前 5 条
  /music play <序号>          播放本会话最近一次搜索结果中的一首
  /music play <关键词>        明确要求直接播放搜索第一条
  /music id <网易云歌曲ID>    直接发送指定歌曲的网易云音乐卡片
  /music status              检查网易云搜索链路
点歌使用 QQ/OneBot 原生网易云音乐卡片，不下载整首歌、不转码，也不做 AI 猜歌。"""


@register("doge_music", "runnel", "网易云音乐搜索与原生 QQ 音乐卡片点歌", "1.0.0")
class DogeMusic(Star):
    RESULT_TTL = 180.0

    def __init__(self, context: Context):
        super().__init__(context)
        self.service = NetEaseMusicService()
        self._results: dict[str, tuple[float, list[Song]]] = {}

    async def terminate(self):
        await self.service.close()

    @staticmethod
    def _scope(event: AstrMessageEvent) -> str:
        return str(event.unified_msg_origin)

    def _remember(self, event: AstrMessageEvent, rows: list[Song]) -> None:
        self._results[self._scope(event)] = (time.monotonic(), list(rows))

    def _recent(self, event: AstrMessageEvent) -> list[Song]:
        item = self._results.get(self._scope(event))
        if not item:
            raise MusicError("本会话还没有最近搜索结果，先用 /music <关键词> 搜歌")
        when, rows = item
        if time.monotonic() - when > self.RESULT_TTL:
            self._results.pop(self._scope(event), None)
            raise MusicError("最近搜索结果已经过期，重新搜一次")
        return list(rows)

    @staticmethod
    def _search_text(query: str, rows: list[Song]) -> str:
        lines = [f"网易云搜索 · {query}"]
        for i, song in enumerate(rows, 1):
            meta = song.name
            if song.artists:
                meta += f" — {song.artists}"
            if song.album:
                meta += f" · {song.album}"
            meta += f" · {song.duration_text}"
            lines.append(f"{i}. {meta}")
        lines.append("用 /music play <序号> 播放")
        return "\n".join(lines)

    @staticmethod
    def _card_result(event: AstrMessageEvent, song_id: int):
        song_id = int(song_id)
        if is_onebot(event):
            card = Comp.Music(id=song_id)
            # AstrBot 4.27 drops leading-underscore pydantic fields at init,
            # while its own toDict() expects `_type` for OneBot music subtype.
            object.__setattr__(card, "_type", "163")
            result = event.chain_result([card])
            result.use_markdown(False)
            return result
        return text_result(event, f"网易云音乐：https://music.163.com/#/song?id={song_id}", markdown=False)

    @filter.command("music")
    async def music(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "music").strip()
            if not payload or payload.casefold() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return

            action, sep, rest = payload.partition(" ")
            low = action.casefold()
            rest = rest.strip() if sep else ""

            if low == "status":
                yield text_result(event, await self.service.status(), markdown=False)
                return

            if low == "id":
                if not rest.isdigit():
                    raise MusicError("用法：/music id <网易云歌曲ID>")
                yield self._card_result(event, int(rest))
                return

            if low in {"play", "pick"}:
                if not rest:
                    raise MusicError("用法：/music play <序号|关键词>")
                if rest.isdigit():
                    rows = self._recent(event)
                    index = int(rest)
                    if index < 1 or index > len(rows):
                        raise MusicError(f"序号范围是 1-{len(rows)}")
                    yield self._card_result(event, rows[index - 1].song_id)
                    return
                rows = await self.service.search(rest, 1)
                self._remember(event, rows)
                yield self._card_result(event, rows[0].song_id)
                return

            query = rest if low in {"search", "find"} and rest else payload
            rows = await self.service.search(query, 5)
            self._remember(event, rows)
            yield text_result(event, self._search_text(query, rows), markdown=False)
        except MusicError as exc:
            yield text_result(event, format_cli_error("music", exc), markdown=False)
        except Exception as exc:
            logger.warning(f"doge music failed: {type(exc).__name__}: {exc}")
            yield text_result(event, format_cli_error("music", exc), markdown=False)
