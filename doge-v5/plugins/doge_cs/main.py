from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.presentation import image_result, images_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from .cs_lab import CSLabError, render_pagerank, render_regex

HELP = (
    "Doge CS Lab /cs\n"
    "  /cs regex <python-style regex>     ε-NFA → DFA → 最小 DFA\n"
    "  /cs pagerank <edges>               PageRank 拓扑与分数\n"
    "边格式：A>B,B>C,C>A 或 A>B:2（带权）\n"
    "示例：/cs regex (a|b)*abb\n"
    "示例：/cs pagerank A>B,B>C,C>A,A>C"
)


@register("doge_cs", "runnel", "计算机科学实验室：形式语言与图算法", "5.4.0")
class DogeCS(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("doge_cs")

    @filter.command("cs")
    async def cs(self, event: AstrMessageEvent):
        paths: list[Path] = []
        try:
            payload = command_payload(event.message_str, "cs")
            if not payload.strip() or payload.strip().lower() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return
            parts = split_head(payload, 1)
            action = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""
            if action == "regex":
                if not rest.strip():
                    raise CSLabError("用法：/cs regex <python-style regex>")
                ps, caption = await asyncio.to_thread(render_regex, self.data_dir, rest)
                paths = [Path(x) for x in ps]
                yield images_result(event, paths, caption)
                return
            if action in {"pagerank", "pr"}:
                if not rest.strip():
                    raise CSLabError("用法：/cs pagerank A>B,B>C,C>A")
                p, caption = await asyncio.to_thread(render_pagerank, self.data_dir, rest)
                paths = [Path(p)]
                yield image_result(event, p, caption)
                return
            raise CSLabError("未知 CS 子命令。\n" + HELP)
        except CSLabError as exc:
            yield text_result(event, f"cs 失败：{exc}", markdown=False)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)
