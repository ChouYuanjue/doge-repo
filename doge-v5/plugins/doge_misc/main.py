from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.logic import parse_ban_duration
from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.services import BingService, CodecService, NasaService
from data.plugins.doge_shared.weather import WeatherService
from data.plugins.doge_shared.help_service import format_cli_error


@register("doge_misc", "runnel", "Doge 有用但不值得独立成域的小工具与轻彩蛋", "5.6.0")
class DogeMisc(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def _self_ban(self, event: AstrMessageEvent, duration_text: str) -> str:
        if not event.get_group_id():
            return "电疗只在群聊里有效。"
        if event.get_platform_name() != "aiocqhttp":
            return "电疗是 NapCat/OneBot 平台彩蛋；QQ 官方机器人不支持这一动作。"
        seconds = parse_ban_duration(duration_text)
        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", bot)
        call = getattr(api, "call_action", None)
        if call is None:
            return "当前 OneBot 适配器不支持群禁言动作。"
        await call(
            "set_group_ban",
            group_id=int(event.get_group_id()),
            user_id=int(event.get_sender_id()),
            duration=seconds,
        )
        return f"已自助电疗 {seconds} 秒。"

    @filter.command("util")
    async def util_command(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "util")
            parts = split_head(payload, 1)
            action = parts[0].lower() if parts else "help"
            rest = parts[1].strip() if len(parts) > 1 else ""

            if action in {"help", "?"}:
                yield text_result(
                    event,
                    "`/util encode <url|unicode|hex|base64> <文本>`\n"
                    "`/util decode <url|unicode|hex|base64> <文本>`\n"
                    "`/util weather <地点> [1-7天]`\n"
                    "`/util apod [YYYY-MM-DD]`\n"
                    "`/util bing`",
                )
                return

            if action in {"encode", "decode"}:
                second = split_head(rest, 1)
                if len(second) < 2:
                    raise ValueError("缺少编码类型或文本")
                yield text_result(
                    event,
                    CodecService.run(action, second[0], second[1]),
                    markdown=False,
                )
                return

            if action == "weather":
                if not rest:
                    raise ValueError("用法：/util weather <地点> [1-7天]")
                toks = rest.rsplit(None, 1)
                days = 3
                place = rest
                if len(toks) == 2 and toks[1].isdigit():
                    place, days = toks[0], int(toks[1])
                data = await WeatherService.forecast(place, days)
                yield text_result(event, WeatherService.format(data), markdown=False)
                return

            if action == "apod":
                data = await NasaService.apod(rest or None)
                caption = f"{data['date']} · {data['title']} · {data.get('source','NASA APOD')}\n\n{data['explanation'][:1600]}"
                if data["media_type"] == "image" and data["url"]:
                    yield image_result(event, data["url"], caption, remote=True)
                else:
                    yield text_result(
                        event,
                        caption + (f"\n\n{data['url']}" if data["url"] else ""),
                    )
                return

            if action == "bing":
                data = await BingService.today()
                caption = " · ".join(
                    x for x in [data["title"], data["copyright"]] if x
                )
                yield image_result(event, data["url"], caption, remote=True)
                return

            raise ValueError("未知 util 子命令")
        except Exception as exc:
            logger.warning(f"doge misc failed: {exc}")
            yield text_result(event, format_cli_error('util', exc), markdown=False)

    @filter.regex(r"^给我.*(?:光明|电疗).*$")
    async def shock(self, event: AstrMessageEvent):
        if event.get_platform_name() != "aiocqhttp":
            return
        event.stop_event()
        try:
            yield text_result(
                event,
                await self._self_ban(event, event.message_str or ""),
                markdown=False,
            )
        except Exception as exc:
            yield text_result(event, format_cli_error("util", exc), markdown=False)
