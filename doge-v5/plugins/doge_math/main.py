from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.agent_tools import DogeMathTool, register_domain_tools
from data.plugins.doge_shared.presentation import text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.services import MathService


@register("doge_math", "runnel", "Doge 数学计算、进制、π 与 OEIS", "5.3.0")
class DogeMath(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        register_domain_tools(context, 'doge_math', DogeMathTool())

    @filter.command("math")
    async def math_command(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "math")
            parts = split_head(payload, 1)
            if not parts:
                yield text_result(event, "`/math <表达式>` · `base <数> <原进制> <目标进制>` · `pi <起点> <位数>` · `oeis <查询>`")
                return
            action = parts[0].lower(); rest = parts[1] if len(parts) > 1 else ""
            if action == "calc": result = MathService.calc(rest)
            elif action in {"base", "system"}:
                args = rest.split()
                if len(args) != 3: raise ValueError("用法：/math base <数> <原进制> <目标进制>")
                result = MathService.base(args[0], int(args[1]), int(args[2]))
            elif action == "pi":
                args = rest.split()
                if len(args) != 2: raise ValueError("用法：/math pi <起点> <位数>")
                result = await MathService.pi(int(args[0]), int(args[1]))
            elif action == "oeis":
                if not rest.strip(): raise ValueError("用法：/math oeis <数列或关键词>")
                result = await MathService.oeis(rest)
            else:
                result = MathService.calc(payload)
            yield text_result(event, str(result), markdown=False)
        except Exception as exc:
            yield text_result(event, f"math 失败：{exc}", markdown=False)
