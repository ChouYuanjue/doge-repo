from __future__ import annotations

import asyncio
import json
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.materials import MATERIALS, wait_for_materials
from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.visual_lab import LabError, help_text as lab_help_text, render as lab_render

from .fourier import FourierError, FourierRenderer


@register('doge_playground','runnel','数学、物理、复杂系统与轮廓傅里叶的直观科学实验室','5.7.0')
class DogePlayground(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = Path(StarTools.get_data_dir('doge_playground'))
        self.mode_path = self.data_dir / 'fourier-modes.json'
        self.modes = self._load_modes()

    def _load_modes(self):
        # Preserve existing /fourier mode preferences when migrating from the
        # short-lived standalone doge_fourier plugin.
        candidates = [self.mode_path, Path(StarTools.get_data_dir('doge_fourier')) / 'modes.json']
        for path in candidates:
            try:
                if path.exists():
                    data = json.loads(path.read_text())
                    if path != self.mode_path:
                        self.mode_path.parent.mkdir(parents=True, exist_ok=True)
                        self.mode_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
                    return data
            except Exception:
                continue
        return {}

    def _save_modes(self):
        self.mode_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.mode_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.modes, ensure_ascii=False, indent=2))
        tmp.replace(self.mode_path)

    @staticmethod
    def _uid(event):
        try:
            return str(event.get_sender_id() or 'default')
        except Exception:
            return 'default'

    def _fourier_mode(self, event):
        return self.modes.get(self._uid(event), 'merge')

    @staticmethod
    def _fourier_vf(rest: str) -> tuple[int, int]:
        vals = rest.split(); vectors = 80; frames = 220
        if vals:
            try: vectors = int(vals[0])
            except ValueError as exc: raise FourierError('vectors 必须是整数') from exc
        if len(vals) > 1:
            try: frames = int(vals[1])
            except ValueError as exc: raise FourierError('frames 必须是整数') from exc
        if len(vals) > 2:
            raise FourierError('image 最多接受 vectors frames 两个参数')
        return vectors, frames

    @filter.command('lab')
    async def lab(self, event: AstrMessageEvent):
        path: Path | None = None
        try:
            payload = command_payload(event.message_str, 'lab')
            if not payload.strip() or payload.strip().lower() in {'help', '?'}:
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

    @filter.command('fourier')
    async def fourier(self, event: AstrMessageEvent):
        path: Path | None = None
        try:
            payload = command_payload(event.message_str, 'fourier')
            parts = split_head(payload, 1)
            if not parts or parts[0].lower() in {'help', '?'}:
                yield text_result(
                    event,
                    'Doge Fourier · v4 轮廓傅里叶动画\n'
                    '/fourier mode [merge|separate]\n'
                    '/fourier svg <SVG源码>\n'
                    '/fourier text <文本>\n'
                    '/fourier image [vectors] [frames]  当前/引用/上一张同用户图片；缺图时等待补发\n'
                    '输出是真正的轮廓 DFT 旋转圆/向量 GIF，不是普通 FFT 频谱图。',
                    markdown=False,
                )
                return
            action = parts[0].lower(); rest = parts[1] if len(parts) > 1 else ''
            if action == 'mode':
                value = rest.strip().lower()
                if not value:
                    yield text_result(event, f'当前模式：{self._fourier_mode(event)}（merge / separate）', markdown=False)
                    return
                if value not in {'merge', 'separate'}:
                    raise FourierError('mode 只支持 merge / separate')
                self.modes[self._uid(event)] = value; self._save_modes()
                yield text_result(event, f'已设置 Fourier 模式：{value}', markdown=False)
                return
            mode = self._fourier_mode(event)
            if action in {'image', 'img', 'draw'}:
                vectors, frames = self._fourier_vf(rest)
                mats = await MATERIALS.resolve(event, 'image', needed=1)
                mats = await wait_for_materials(event, 'image', 1, mats)
                path, stats = await asyncio.to_thread(
                    FourierRenderer.from_image_path, mats[0].path, mode=mode, vectors=vectors, frames=frames
                )
                source = {'current':'当前图片','reply':'引用图片','recent':'上一张同用户图片','followup':'随后补发图片'}.get(mats[0].source, mats[0].source)
            elif action == 'svg':
                if not rest.strip(): raise FourierError('用法：/fourier svg <SVG源码>')
                path, stats = await asyncio.to_thread(FourierRenderer.from_svg, rest, mode=mode)
                source = 'SVG'
            elif action == 'text':
                if not rest.strip(): raise FourierError('用法：/fourier text <文本>')
                path, stats = await asyncio.to_thread(FourierRenderer.from_text, rest, mode=mode)
                source = '文本'
            else:
                raise FourierError('未知 Fourier 子命令；支持 mode / svg / text / image')
            caption = (
                f'Fourier epicycles · {source} · {stats.mode} · contours={stats.contours} · '
                f'samples={stats.samples} · vectors={stats.vectors} · frames={stats.frames}'
            )
            yield image_result(event, path, caption)
        except (FourierError, ValueError) as exc:
            yield text_result(event, format_cli_error('fourier', exc), markdown=False)
        except Exception as exc:
            logger.warning(f'doge fourier failed: {exc}', exc_info=True)
            yield text_result(event, format_cli_error('fourier', exc), markdown=False)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
