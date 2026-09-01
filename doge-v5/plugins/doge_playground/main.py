from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload
from data.plugins.doge_shared.visual_lab import LabError, help_text as lab_help_text, render as lab_render
from data.plugins.doge_shared.help_service import format_cli_error


@register('doge_playground','runnel','数学、物理与复杂系统的直观科学实验室','5.4.0')
class DogePlayground(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir('doge_playground')

    @filter.command('lab')
    async def lab(self, event: AstrMessageEvent):
        path: Path | None = None
        try:
            payload = command_payload(event.message_str, 'lab')
            if not payload.strip() or payload.strip().lower() in {'help','?'}:
                yield text_result(event, lab_help_text(), markdown=False)
                return
            path, caption = await asyncio.to_thread(lab_render, self.data_dir, payload)
            yield image_result(event, path, caption)
        except (LabError, ValueError) as exc:
            yield text_result(event, format_cli_error('lab', exc), markdown=False)
        except Exception as exc:
            logger.warning(f'doge lab failed: {exc}')
            yield text_result(event, format_cli_error('lab', exc), markdown=False)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
