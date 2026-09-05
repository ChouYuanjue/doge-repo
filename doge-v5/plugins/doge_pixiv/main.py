from __future__ import annotations

import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.agent_tools import DogePixivTool, register_domain_tools
from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.presentation import image_result, images_result, text_result
from data.plugins.doge_shared.raw_command import command_payload

from .service import PixivError, PixivService


HELP = """Doge Pixiv /pixiv
  /pixiv <标签> [数量]          按标签找插画；群聊最多 3 张，私聊最多 5 张
  /pixiv random [数量]         随机插画
  /pixiv artist <uid> [数量]   按 Pixiv 画师 UID 找作品
  /pixiv status                检查官方 Web / 原图 CDN / 回退链路
固定策略：R18 关闭，AI 生成作品过滤。标签搜索优先使用 Pixiv 官方 Web 候选池与原图 CDN；Lolicon 作为随机图、画师搜索和故障回退。"""


@register("doge_pixiv", "runnel", "Pixiv 插画搜索：官方 Web 候选池、原图 CDN 与 Lolicon 回退，固定过滤 R18/AI", "1.1.0")
class DogePixiv(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.data_dir = Path(StarTools.get_data_dir("doge_pixiv"))
        self.service = PixivService(self.data_dir)
        self._last_request: dict[str, float] = {}
        register_domain_tools(context, "doge_pixiv", DogePixivTool())

    async def terminate(self):
        await self.service.close()

    @staticmethod
    def _split_count(text: str, default: int, maximum: int) -> tuple[str, int]:
        raw = str(text or "").strip()
        if not raw:
            return "", default
        parts = raw.rsplit(None, 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0].strip(), max(1, min(int(parts[1]), maximum))
        if len(parts) == 1 and parts[0].isdigit():
            return "", max(1, min(int(parts[0]), maximum))
        return raw, default

    @staticmethod
    def _limit(event: AstrMessageEvent) -> int:
        return 3 if event.get_group_id() else 5

    def _rate_limit(self, event: AstrMessageEvent) -> None:
        key = str(event.get_sender_id() or "")
        now = time.monotonic()
        before = self._last_request.get(key, 0.0)
        if key and now - before < 4.0:
            raise PixivError("请求太快了，几秒后再搜")
        if key:
            self._last_request[key] = now

    @filter.command("pixiv")
    async def pixiv(self, event: AstrMessageEvent):
        paths: list[Path] = []
        try:
            payload = command_payload(event.message_str, "pixiv").strip()
            if not payload or payload.lower() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return
            action, _, rest = payload.partition(" ")
            low = action.casefold()
            if low == "status":
                yield text_result(event, await self.service.status(), markdown=False)
                return

            self._rate_limit(event)
            maximum = self._limit(event)
            scope = str(event.unified_msg_origin)
            if low in {"random", "rand"}:
                _, count = self._split_count(rest, 1, maximum)
                images = await self.service.random(count=count, scope=scope)
            elif low in {"artist", "user", "uid"}:
                uid, count = self._split_count(rest, 1, maximum)
                if not uid or not uid.isdigit():
                    raise PixivError("用法：/pixiv artist <uid> [数量]")
                images = await self.service.artist(uid, count=count, scope=scope)
            else:
                tag, count = self._split_count(payload, 1, maximum)
                images = await self.service.search(tag, count=count, scope=scope)

            paths = [image.path for image in images]
            caption = self.service.caption(images)
            if len(paths) == 1:
                yield image_result(event, paths[0], caption)
            else:
                yield images_result(event, paths, caption)
        except Exception as exc:
            if not isinstance(exc, PixivError):
                logger.warning(f"doge pixiv failed: {type(exc).__name__}: {exc}")
            yield text_result(event, format_cli_error("pixiv", exc), markdown=False)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)
