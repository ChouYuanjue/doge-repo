from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.agent_tools import DogeWeatherTool, register_domain_tools
from data.plugins.doge_shared.presentation import text_result


@register("doge_core", "runnel", "Doge v5 核心运行与平台信息", "5.3.0")
class DogeCore(Star):
    """Minimal always-on Doge foundation.

    Domain tools register themselves from their own plugins.  Keeping this
    plugin deliberately small means disabling an optional feature cannot break
    the rest of the bot or pollute the command list.
    """

    def __init__(self, context: Context):
        super().__init__(context)
        register_domain_tools(context, "doge_core", DogeWeatherTool())

    @filter.command("ver")
    async def version(self, event: AstrMessageEvent):
        yield text_result(
            event,
            "Doge v5.3 · AstrBot 4.27.x · QQ Official + NapCat/OneBot\n"
            f"platform={event.get_platform_name()} · instance={event.get_platform_id()}",
            markdown=False,
        )
