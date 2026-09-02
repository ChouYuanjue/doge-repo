from __future__ import annotations

import re

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.agent_tools import DogeChaoliTool, register_domain_tools
from data.plugins.doge_shared.chaoli import ChaoliError, ChaoliService
from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.presentation import long_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head

HELP = """Doge Chaoli /chaoli
  /chaoli latest [板块] [数量]           最新主题（默认跳过置顶）；板块可用 数学/物理/化学/生物/技术/语言/社科/科幻/合集
  /chaoli channel <板块> [数量]         指定板块主题流
  /chaoli read <帖子号|链接>            读取主题；长楼自动压缩中段
  /chaoli floor <帖子号> <楼层>         精确读取一层
  /chaoli context <帖子号> <楼层> [1-3] 读取该层及前后文
  /chaoli outline <帖子号|链接>         长帖楼层提纲，按层快速定位
  /chaoli user <用户ID|链接>            用户公开活动
  /chaoli links <帖子号|链接>           沿帖内超理链接阅读相关旧帖
  /chaoli preview <帖子号|链接>         一屏预览
  /chaoli status                        检查 Chaoli 专用代理链
首版不依赖站内 search；Cloudflare 对查询页的验证不会影响以上入口。"""


@register("doge_chaoli", "runnel", "超理论坛只读浏览、楼层上下文、用户活动与引用链", "5.10.22")
class DogeChaoli(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        register_domain_tools(context, "doge_chaoli", DogeChaoliTool())

    @filter.command("chaoli")
    async def command(self, event: AstrMessageEvent):
        try:
            raw = command_payload(event.message_str, "chaoli").strip()
            if not raw or raw.lower() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return
            p = split_head(raw, 1)
            action = p[0].lower()
            rest = p[1].strip() if len(p) > 1 else ""
            if action in {"latest", "new"}:
                xs = rest.split()
                channel = xs[0] if xs and not xs[0].isdigit() else "all"
                limit = int(xs[-1]) if xs and xs[-1].isdigit() else 10
                out = await ChaoliService.latest(channel, limit)
            elif action in {"channel", "board"}:
                xs = rest.split()
                if not xs:
                    raise ValueError("缺少板块")
                out = await ChaoliService.latest(xs[0], int(xs[1]) if len(xs) > 1 and xs[1].isdigit() else 10)
            elif action in {"read", "thread"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.read(rest)
            elif action == "floor":
                xs = rest.split()
                if len(xs) < 2 or not xs[1].isdigit():
                    raise ValueError("用法：/chaoli floor <帖子号> <楼层>")
                out = await ChaoliService.read(xs[0], int(xs[1]), 0)
            elif action in {"context", "ctx"}:
                xs = rest.split()
                if len(xs) < 2 or not xs[1].isdigit():
                    raise ValueError("用法：/chaoli context <帖子号> <楼层> [1-3]")
                out = await ChaoliService.read(xs[0], int(xs[1]), int(xs[2]) if len(xs) > 2 and xs[2].isdigit() else 1)
            elif action in {"outline", "toc"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.outline(rest)
            elif action in {"user", "member"}:
                if not rest:
                    raise ValueError("缺少用户 ID 或链接")
                out = await ChaoliService.user(rest)
            elif action in {"links", "refs", "related"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.links(rest)
            elif action in {"preview", "peek"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.preview(rest)
            elif action == "status":
                out = await ChaoliService.status()
            else:
                raise ValueError("未知 chaoli 子命令")
            yield long_result(event, "Chaoli", out, fold_threshold=1800)
        except (ChaoliError, ValueError) as exc:
            yield text_result(event, format_cli_error("chaoli", exc), markdown=False)
        except Exception as exc:
            logger.warning(f"doge chaoli failed: {exc}")
            yield text_result(event, format_cli_error("chaoli", exc), markdown=False)

    @filter.regex(r"https?://(?:www\.)?chaoli\.club/index\.php/\d+(?:/\d+)?(?:#[^\s]+)?$")
    async def auto_preview(self, event: AstrMessageEvent):
        text = str(event.message_str or "").strip()
        if text.startswith("/chaoli"):
            return
        m = re.search(r"https?://(?:www\.)?chaoli\.club/index\.php/\d+(?:/\d+)?", text, re.I)
        if not m:
            return
        try:
            yield text_result(event, await ChaoliService.preview(m.group(0)), markdown=False)
        except Exception as exc:
            logger.debug(f"chaoli link preview skipped: {exc}")
