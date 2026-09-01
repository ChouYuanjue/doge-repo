from __future__ import annotations

import asyncio
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.academic import MaterialService
from data.plugins.doge_shared.agent_tools import DogeMaterialTool, register_domain_tools
from data.plugins.doge_shared.presentation import image_result, long_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.science_wrappers import (
    ScienceExtraDependencyError,
    ScienceWrapperError,
    crystal_info,
    render_crystal_powder,
)

HELP = (
    "Doge Materials /mat\n"
    "  /mat find <formula/filter>       OPTIMADE 跨材料数据库查询\n"
    "  /mat providers                   OPTIMADE provider 列表\n"
    "  /mat crystal info + CIF/mCIF     晶胞信息\n"
    "  /mat crystal powder [E] [width] + CIF/mCIF  真实 powder XRD\n"
    "晶体文件计算使用 Dans_Diffraction；/lab xrd 是快速教学模型。"
)


@register('doge_materials','runnel','材料数据库、晶体结构与衍射','5.4.0')
class DogeMaterials(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir('doge_materials')
        register_domain_tools(context, 'doge_materials', DogeMaterialTool())

    async def _crystal(self, event: AstrMessageEvent, payload: str):
        file_seg = next((x for x in event.get_messages() if isinstance(x, Comp.File)), None)
        if file_seg is None:
            raise ScienceWrapperError('请在同一条消息附带 .cif / .mcif 文件')
        input_path = await file_seg.get_file()
        if not input_path:
            raise ScienceWrapperError('无法取得 CIF/mCIF 文件')
        cleanup = bool(getattr(file_seg, 'url', '') and not getattr(file_seg, 'file_', ''))
        out_path: Path | None = None
        try:
            parts = payload.split()
            action = parts[0].lower() if parts else 'info'
            if action in {'info','cell'}:
                return text_result(event, await asyncio.to_thread(crystal_info, input_path), markdown=False), None
            if action in {'powder','xrd'}:
                energy = float(parts[1]) if len(parts) > 1 else 8.0
                width = float(parts[2]) if len(parts) > 2 else .08
                out_path, caption = await asyncio.to_thread(render_crystal_powder, self.data_dir, input_path, energy, width)
                return image_result(event, out_path, caption), out_path
            raise ScienceWrapperError('crystal 支持 info / powder')
        finally:
            if cleanup:
                Path(input_path).unlink(missing_ok=True)

    @filter.command('mat')
    async def command(self, event: AstrMessageEvent):
        out_path: Path | None = None
        try:
            raw = command_payload(event.message_str, 'mat')
            p = split_head(raw, 1)
            if not p or p[0].lower() in {'help','?'}:
                yield text_result(event, HELP, markdown=False)
                return
            action = p[0].lower()
            rest = p[1].strip() if len(p) > 1 else ''
            if action == 'crystal':
                result, out_path = await self._crystal(event, rest)
                yield result
                return
            if action in {'providers','db','databases'}:
                result = await MaterialService.providers()
            else:
                query = rest if action in {'find','search'} else raw
                result = await MaterialService.find(query)
            yield long_result(event, 'Materials', result, fold_threshold=1400)
        except (ScienceWrapperError, ScienceExtraDependencyError, ValueError) as exc:
            yield text_result(event, format_cli_error('mat', exc), markdown=False)
        except Exception as exc:
            yield text_result(event, format_cli_error('mat', exc), markdown=False)
        finally:
            if out_path is not None:
                out_path.unlink(missing_ok=True)
