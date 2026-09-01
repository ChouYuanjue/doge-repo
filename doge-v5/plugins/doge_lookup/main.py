from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.agent_tools import DogeLookupTool, register_domain_tools
from data.plugins.doge_shared.lookup import LookupError, LookupService
from data.plugins.doge_shared.presentation import long_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head


HELP = (
    "Doge Lookup /lookup\n"
    "  /lookup <query>                 可达百科 + Wikidata/QLever 双来源\n"
    "  /lookup wiki <query>            Wikipedia；不可达时明确切到真实百科后端\n"
    "  /lookup entity <query>          Wikidata 结构化事实（QLever 镜像）\n"
    "  /lookup wa <query>              Wolfram|Alpha LLM API（需 AppID）\n"
    "  /lookup en <query>              英文百科 + Wikidata/QLever\n"
    "输出保留来源链接；旧 DeepWiki 非正式接口不进入正式模块。"
)


@register('doge_lookup','runnel','Doge grounded 通用知识与计算查询','5.6.0')
class DogeLookup(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        register_domain_tools(context, 'doge_lookup', DogeLookupTool())

    @filter.command('lookup')
    async def lookup(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, 'lookup')
            if not payload.strip() or payload.strip().lower() in {'help','?'}:
                yield text_result(event, HELP, markdown=False); return
            parts = split_head(payload, 1)
            action = parts[0].lower() if parts else ''
            rest = parts[1].strip() if len(parts) > 1 else ''
            if action == 'wiki':
                if not rest: raise ValueError('缺少查询内容')
                out = (await LookupService.wikipedia(rest)).format()
            elif action in {'entity','wikidata'}:
                if not rest: raise ValueError('缺少查询内容')
                out = await LookupService.wikidata(rest)
            elif action in {'wa','wolfram'}:
                if not rest: raise ValueError('缺少查询内容')
                out = await LookupService.wolfram(rest)
            elif action in {'en','english'}:
                if not rest: raise ValueError('缺少查询内容')
                out = await LookupService.auto(rest, 'en')
            else:
                out = await LookupService.auto(payload)
            yield long_result(event, 'Lookup', out, fold_threshold=1800)
        except (LookupError, ValueError) as exc:
            yield text_result(event, f'lookup 失败：{exc}', markdown=False)
        except Exception as exc:
            logger.warning(f'doge lookup failed: {exc}')
            yield text_result(event, f'lookup 失败：{exc}', markdown=False)
