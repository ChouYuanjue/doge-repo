from __future__ import annotations

from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.utils.session_waiter import SessionController, session_waiter

from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.help_service import format_cli_error

from .media_service import make_mirage, trace_image


@register("doge_media", "runnel", "Doge 图片识别与视觉小实验", "5.5.0")
class DogeMedia(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = Path(StarTools.get_data_dir("doge_media"))

    async def _images(self, event: AstrMessageEvent) -> list[str]:
        paths: list[str] = []
        for comp in event.get_messages():
            if not isinstance(comp, Comp.Image):
                continue
            try:
                p = await comp.convert_to_file_path()
                if p:
                    paths.append(str(p))
            except Exception:
                continue
        return paths

    async def _wait_images(self, event: AstrMessageEvent, initial: list[str], needed: int) -> list[str]:
        collected = list(initial)
        if len(collected) >= needed:
            return collected[:needed]
        await event.send(event.plain_result(f"还需要 {needed-len(collected)} 张图片；60 秒内继续发送，输入 cancel 取消。"))

        @session_waiter(timeout=60, record_history_chains=False)
        async def waiter(controller: SessionController, incoming: AstrMessageEvent):
            if (incoming.message_str or "").strip().lower() in {"cancel", "取消"}:
                controller.stop()
                return
            collected.extend(await self._images(incoming))
            if len(collected) >= needed:
                controller.stop()
            else:
                await incoming.send(incoming.plain_result(f"已收到 {len(collected)}/{needed} 张。"))
                controller.keep(timeout=60, reset_timeout=True)

        try:
            await waiter(event)
        except TimeoutError as exc:
            raise ValueError("等待图片超时") from exc
        if len(collected) < needed:
            raise ValueError("没有收到足够的图片")
        return collected[:needed]

    @filter.command("media")
    async def media(self, event: AstrMessageEvent):
        result_path: Path | None = None
        try:
            payload = command_payload(event.message_str, "media")
            parts = split_head(payload, 2)
            if not parts:
                yield text_result(
                    event,
                    "Doge Media\n"
                    "/media trace {anime|gal}   同一条消息附一张图\n"
                    "/media mirage {gray|color} 同一条消息附两张图（第一张表图，第二张里图）",
                    markdown=False,
                )
                return
            action = parts[0].lower()
            mode = parts[1].lower() if len(parts) > 1 and parts[1].strip() else ""
            current = await self._images(event)

            if action == "trace":
                mode = mode or "anime"
                images = await self._wait_images(event, current, 1)
                text = await trace_image(images[0], mode)
                yield text_result(event, text, markdown=False)
                return

            if action == "mirage":
                mode = mode or "gray"
                images = await self._wait_images(event, current, 2)
                result_path = await make_mirage(images[0], images[1], self.data_dir, mode)
                yield image_result(
                    event,
                    result_path,
                    "幻影坦克 · gray 在浅/深背景呈现不同图像；color 保留更多色彩信息。",
                )
                return

            raise ValueError("未知 media 类型；支持 trace / mirage")
        except Exception as exc:
            yield text_result(event, format_cli_error('media', exc), markdown=False)
        finally:
            if result_path is not None:
                result_path.unlink(missing_ok=True)
