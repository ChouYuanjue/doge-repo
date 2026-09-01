from __future__ import annotations

import os
import shlex

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.agent_tools import DogeMathTool, register_domain_tools
from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.lookup import LookupService
from data.plugins.doge_shared.presentation import text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.services import MathService


def _opts(text: str, allowed: set[str]) -> tuple[str, dict[str, str]]:
    """Extract conventional `--name value` options while preserving expression tokens."""
    toks = shlex.split(text, posix=True)
    body: list[str] = []
    options: dict[str, str] = {}
    i = 0
    while i < len(toks):
        tok = toks[i]
        if tok.startswith("--"):
            name = tok[2:].lower()
            if name not in allowed:
                raise ValueError(f"未知选项 --{name}")
            if i + 1 >= len(toks):
                raise ValueError(f"选项 --{name} 缺少值")
            options[name] = toks[i + 1]
            i += 2
            continue
        body.append(tok); i += 1
    return " ".join(body).strip(), options


@register("doge_math", "runnel", "Doge 精确/符号数学、数论、统计、WA 与形式化入口", "5.4.0")
class DogeMath(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.wolfram_appid = str(self.config.get("wolfram_appid", "") or "").strip()
        if self.wolfram_appid:
            # Keep the historical /lookup wa surface usable too; LookupService
            # resolves the environment lazily and never logs the credential.
            os.environ.setdefault("WOLFRAM_ALPHA_APPID", self.wolfram_appid)
        register_domain_tools(context, "doge_math", DogeMathTool(wolfram_appid=self.wolfram_appid))

    @filter.command("math")
    async def math_command(self, event: AstrMessageEvent):
        help_topic = "math"
        try:
            payload = command_payload(event.message_str, "math")
            parts = split_head(payload, 1)
            if not parts:
                yield text_result(
                    event,
                    "Doge Math：精确/符号计算、数论、统计、OEIS、Wolfram|Alpha 与形式化数学入口。\n"
                    "可视化、模拟、动态图和直觉实验请用 /lab。\n"
                    "查看完整参数：/help math",
                    markdown=False,
                )
                return
            action = parts[0].lower(); rest = parts[1] if len(parts) > 1 else ""
            aliases = {"system": "base", "derive": "diff", "int": "integrate", "lim": "limit", "wolfram": "wa", "rocq": "formal"}
            action = aliases.get(action, action)
            if action in {"calc","base","pi","oeis","numeric","simplify","expand","factor","solve","diff","integrate","limit","factorint","prime","stats","wa","formal"}:
                help_topic = f"math {action}"

            if action == "calc":
                if not rest.strip(): raise ValueError("用法：/math calc <表达式>")
                result = MathService.calc(rest)
            elif action == "base":
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
            elif action == "numeric":
                expr, opts = _opts(rest, {"digits"})
                if not expr: raise ValueError("用法：/math numeric <表达式> [--digits <位数>]")
                result = MathService.numeric(expr, int(opts.get("digits", "15")))
            elif action in {"simplify", "expand", "factor"}:
                if not rest.strip(): raise ValueError(f"用法：/math {action} <表达式>")
                result = getattr(MathService, action)(rest)
            elif action == "solve":
                expr, opts = _opts(rest, {"var"})
                if not expr: raise ValueError("用法：/math solve <方程/表达式> [--var <变量>]")
                result = MathService.solve(expr, opts.get("var", "x"))
            elif action == "diff":
                expr, opts = _opts(rest, {"var", "order"})
                if not expr: raise ValueError("用法：/math diff <表达式> [--var <变量>] [--order <阶数>]")
                result = MathService.diff(expr, opts.get("var", "x"), int(opts.get("order", "1")))
            elif action == "integrate":
                expr, opts = _opts(rest, {"var", "from", "to"})
                if not expr: raise ValueError("用法：/math integrate <表达式> [--var <变量>] [--from <下限> --to <上限>]")
                result = MathService.integrate(expr, opts.get("var", "x"), opts.get("from"), opts.get("to"))
            elif action == "limit":
                expr, opts = _opts(rest, {"var", "to", "dir"})
                if not expr or "to" not in opts: raise ValueError("用法：/math limit <表达式> --to <趋近点> [--var <变量>] [--dir {+|-|+-}]")
                result = MathService.limit(expr, opts.get("var", "x"), opts["to"], opts.get("dir", "+-"))
            elif action == "factorint":
                if not rest.strip(): raise ValueError("用法：/math factorint <整数>")
                result = MathService.factorint(int(rest.strip()))
            elif action == "prime":
                if not rest.strip(): raise ValueError("用法：/math prime <整数>")
                result = MathService.prime(int(rest.strip()))
            elif action == "stats":
                raw = rest.replace(",", " ").split()
                if not raw: raise ValueError("用法：/math stats <数> [数 ...]")
                result = MathService.stats([float(x) for x in raw])
            elif action == "wa":
                if not rest.strip(): raise ValueError("用法：/math wa <Wolfram|Alpha 查询>")
                result = await LookupService.wolfram(rest, appid=self.wolfram_appid)
            elif action == "formal":
                fparts = split_head(rest, 1)
                if not fparts:
                    result = MathService.formal_overview()
                else:
                    lang = fparts[0].lower(); code = fparts[1] if len(fparts) > 1 else ""
                    result = MathService.formal(lang, code)
            else:
                # Keep the convenient historical `/math 2^10` surface.
                result = MathService.calc(payload)
            yield text_result(event, str(result), markdown=False)
        except Exception as exc:
            yield text_result(event, format_cli_error("math", exc, help_topic), markdown=False)
