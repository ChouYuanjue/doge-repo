from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from data.plugins.doge_shared.presentation import long_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.help_service import format_cli_error

from .executor import LANGUAGES, RunoobExecutor


@register("doge_code", "runnel", "远端代码执行（当前使用 Runoob，不在宿主机执行）", "5.6.0")
class DogeCode(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.executor = RunoobExecutor()

    @filter.command("run")
    async def run(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "run")
            parts = split_head(payload, 1)
            if len(parts) < 2:
                yield text_result(
                    event,
                    "/run <python|js|cpp|c|java|go|ruby|swift|kotlin|php> <代码>\n代码发送到 Runoob 远端执行器，不会在 Doge 宿主机执行。",
                    markdown=False,
                )
                return
            language = parts[0].lower()
            code = parts[1]
            result = await self.executor.execute(language, code)
            # `long_result` will render rich Markdown only on QQ Official and
            # strip it for OneBot/NapCat via the shared presentation layer.
            yield long_result(event, f"Run · {language}", f"```\n{result}\n```", fold_threshold=1800)
        except Exception as exc:
            yield text_result(event, format_cli_error('run', exc), markdown=False)
