from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.science_wrappers import (
    ScienceExtraDependencyError,
    ScienceWrapperError,
    circuit_help,
    control_help,
    render_circuit,
    render_control,
)

HELP = (
    "Doge Engineering /eng\n"
    "  /eng circuit rc [R C]\n"
    "  /eng circuit rlc [R L C]\n"
    "  /eng circuit divider [R1 R2]\n"
    "  /eng circuit series V:5V R:1k C:10u GND\n"
    "  /eng control bode|step|impulse|nyquist|root <num coeffs> | <den coeffs>\n"
    "示例：/eng control bode 1 | 1 0.4 1"
)


@register("doge_engineering", "runnel", "工程实验室：电路图与经典控制系统", "5.4.0")
class DogeEngineering(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("doge_engineering")

    @filter.command("eng")
    async def eng(self, event: AstrMessageEvent):
        path: Path | None = None
        try:
            payload = command_payload(event.message_str, "eng")
            if not payload.strip() or payload.strip().lower() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return
            parts = split_head(payload, 1)
            family = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""
            if family == "circuit":
                if not rest.strip():
                    yield text_result(event, circuit_help().replace("/circuit", "/eng circuit"), markdown=False)
                    return
                path, caption = await asyncio.to_thread(render_circuit, self.data_dir, rest)
            elif family == "control":
                if not rest.strip():
                    yield text_result(event, control_help().replace("/control", "/eng control"), markdown=False)
                    return
                path, caption = await asyncio.to_thread(render_control, self.data_dir, rest)
            else:
                raise ScienceWrapperError("未知 engineering 子命令。\n" + HELP)
            yield image_result(event, path, caption)
        except (ScienceWrapperError, ScienceExtraDependencyError, ValueError) as exc:
            yield text_result(event, f"eng 失败：{exc}", markdown=False)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
