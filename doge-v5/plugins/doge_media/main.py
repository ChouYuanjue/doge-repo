from __future__ import annotations

from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.materials import MATERIALS, wait_for_materials
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.help_service import format_cli_error

from .media_service import make_mirage, trace_image


@register("doge_media", "runnel", "Doge 图片识别与视觉小实验", "5.5.0")
class DogeMedia(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = Path(StarTools.get_data_dir("doge_media"))

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
                    "/media trace {anime|gal}   使用当前/引用/上一张同用户图片，缺图时等待补发\n"
                    "/media mirage {gray|color} 使用两张图片（当前→引用→上一条→补发；第一张表图，第二张里图）",
                    markdown=False,
                )
                return
            action = parts[0].lower()
            mode = parts[1].lower() if len(parts) > 1 and parts[1].strip() else ""
            if action == "trace":
                mode = mode or "anime"
                materials = await MATERIALS.resolve(event, "image", needed=1)
                materials = await wait_for_materials(event, "image", 1, materials)
                text = await trace_image(materials[0].path, mode)
                yield text_result(event, text, markdown=False)
                return

            if action == "mirage":
                mode = mode or "gray"
                materials = await MATERIALS.resolve(event, "image", needed=2)
                materials = await wait_for_materials(event, "image", 2, materials)
                result_path = await make_mirage(materials[0].path, materials[1].path, self.data_dir, mode)
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
