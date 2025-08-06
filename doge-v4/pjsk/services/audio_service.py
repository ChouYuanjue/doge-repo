import asyncio
import io
import random
import os
import subprocess
import time
import itertools
import aiohttp
from typing import List, Dict, Optional, Tuple, Union
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    AudioSegment = None
    PYDUB_AVAILABLE = False

try:
    from PIL.Image import Resampling
    LANCZOS = Resampling.LANCZOS
except ImportError:
    LANCZOS = 1

from pilmoji import Pilmoji

from astrbot.api import logger
from astrbot.api import AstrBotConfig
from .cache_service import CacheService

class AudioService:
    def __init__(self, cache_service: CacheService, resources_dir: Path, output_dir: Path, config: AstrBotConfig, plugin_version: str):
        self.cache_service = cache_service
        self.resources_dir = resources_dir
        self.output_dir = output_dir
        self.config = config
        self.plugin_version = plugin_version
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._session: Optional[aiohttp.ClientSession] = None
        
        self.game_effects = {
            'speed_2x': {'name': '2倍速', 'score': 1, 'kwargs': {'speed_multiplier': 2.0}},
            'reverse': {'name': '倒放', 'score': 3, 'kwargs': {'reverse_audio': True}},
            'piano': {'name': '钢琴', 'score': 2, 'kwargs': {'melody_to_piano': True}},
            'acc': {'name': '伴奏', 'score': 1, 'kwargs': {'play_preprocessed': 'accompaniment'}},
            'bass': {'name': '纯贝斯', 'score': 3, 'kwargs': {'play_preprocessed': 'bass_only'}},
            'drums': {'name': '纯鼓组', 'score': 4, 'kwargs': {'play_preprocessed': 'drums_only'}},
            'vocals': {'name': '纯人声', 'score': 1, 'kwargs': {'play_preprocessed': 'vocals_only'}},
        }
        self.game_modes = {
            'normal': {'name': '普通', 'kwargs': {}, 'score': 1},
            '1': {'name': '2倍速', 'kwargs': {'speed_multiplier': 2.0}, 'score': 1},
            '2': {'name': '倒放', 'kwargs': {'reverse_audio': True}, 'score': 3},
            '3': {'name': 'AI-Assisted Twin Piano ver.', 'kwargs': {'melody_to_piano': True}, 'score': 2},
            '4': {'name': '纯伴奏', 'kwargs': {'play_preprocessed': 'accompaniment'}, 'score': 1},
            '5': {'name': '纯贝斯', 'kwargs': {'play_preprocessed': 'bass_only'}, 'score': 3},
            '6': {'name': '纯鼓组', 'kwargs': {'play_preprocessed': 'drums_only'}, 'score': 4},
            '7': {'name': '纯人声', 'kwargs': {'play_preprocessed': 'vocals_only'}, 'score': 1},
        }
        self.listen_modes = {
            "piano": {"name": "钢琴", "list_attr": "available_piano_songs", "file_key": "piano", "not_found_msg": "......抱歉，没有找到任何预生成的钢琴曲。", "no_match_msg": "......没有找到与 '{search_term}' 匹配的歌曲，或者该歌曲没有可用的钢琴版本。", "title_suffix": "(钢琴)", "is_piano": True},
            "accompaniment": {"name": "伴奏", "list_attr": "available_accompaniment_songs", "file_key": "accompaniment", "not_found_msg": "......抱歉，没有找到任何预生成的伴奏曲。", "no_match_msg": "......没有找到与 '{search_term}' 匹配的歌曲，或者该歌曲没有可用的伴奏版本。", "title_suffix": "(伴奏)", "is_piano": False},
            "vocals": {"name": "人声", "list_attr": "available_vocals_songs", "file_key": "vocals_only", "not_found_msg": "......抱歉，没有找到任何预生成的纯人声曲。", "no_match_msg": "......没有找到与 '{search_term}' 匹配的歌曲，或者该歌曲没有可用的人声版本。", "title_suffix": "(人声)", "is_piano": False},
            "bass": {"name": "贝斯", "list_attr": "available_bass_songs", "file_key": "bass_only", "not_found_msg": "......抱歉，没有找到任何预生成的纯贝斯曲。", "no_match_msg": "......没有找到与 '{search_term}' 匹配的歌曲，或者该歌曲没有可用的贝斯版本。", "title_suffix": "(贝斯)", "is_piano": False},
            "drums": {"name": "鼓组", "list_attr": "available_drums_songs", "file_key": "drums_only", "not_found_msg": "......抱歉，没有找到任何预生成的纯鼓点曲。", "no_match_msg": "......没有找到与 '{search_term}' 匹配的歌曲，或者该歌曲没有可用的鼓点版本。", "title_suffix": "(鼓组)", "is_piano": False},
        }
        self.mode_name_map = {}
        for key, value in self.game_modes.items():
            self.mode_name_map[key] = key
            self.mode_name_map[value['name'].lower()] = key
        for key, value in self.game_effects.items():
            self.mode_name_map[key] = key
            self.mode_name_map[value['name'].lower()] = key

        self.random_mode_decay_factor = self.config.get("random_mode_decay_factor", 0.75)
        self.base_effects = [
            {'name': '2倍速', 'kwargs': {'speed_multiplier': 2.0}, 'group': 'speed', 'score': 1},
            {'name': '倒放', 'kwargs': {'reverse_audio': True}, 'group': 'direction', 'score': 3},
        ]
        self.source_effects = [
            {'name': 'Twin Piano ver.', 'kwargs': {'melody_to_piano': True}, 'group': 'source', 'score': 2},
            {'name': '纯人声', 'kwargs': {'play_preprocessed': 'vocals_only'}, 'group': 'source', 'score': 1},
            {'name': '纯贝斯', 'kwargs': {'play_preprocessed': 'bass_only'}, 'group': 'source', 'score': 3},
            {'name': '纯鼓组', 'kwargs': {'play_preprocessed': 'drums_only'}, 'group': 'source', 'score': 4},
            {'name': '纯伴奏', 'kwargs': {'play_preprocessed': 'accompaniment'}, 'group': 'source', 'score': 1}
        ]

    async def _get_session(self) -> Optional[aiohttp.ClientSession]:
        """延迟初始化并获取 aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_game_clip(self, **kwargs) -> Optional[Dict]:
        """
        准备一轮新游戏。该函数现在会智能选择处理路径：
        - 快速路径：对简单裁剪任务直接使用ffmpeg，性能更高。
        - 慢速路径：对需要变速、倒放等复杂效果的任务，使用pydub。
        """
        if not self.cache_service.song_data or not PYDUB_AVAILABLE:
            logger.error("无法开始游戏: 歌曲数据未加载或pydub未安装。")
            return None

        song = kwargs.get("force_song_object")
        preprocessed_mode = kwargs.get("play_preprocessed")
        is_piano_mode = kwargs.get("melody_to_piano", False)
        
        if not song:
            if preprocessed_mode:
                available_bundles = self.cache_service.preprocessed_tracks.get(preprocessed_mode, set())
                if not available_bundles:
                    logger.error(f"无法开始 {preprocessed_mode} 模式: 没有找到任何预处理的音轨文件。")
                    return None
                chosen_bundle = random.choice(list(available_bundles))
                song = self.cache_service.bundle_to_song_map.get(chosen_bundle)
            elif is_piano_mode:
                if not self.cache_service.available_piano_songs:
                    logger.error("无法开始钢琴模式: 没有找到任何预生成的钢琴曲。")
                    return None
                song = random.choice(self.cache_service.available_piano_songs)
            else:
                song = random.choice(self.cache_service.song_data)
        
        if not song:
            logger.error("在游戏准备的步骤一中未能确定歌曲。")
            return None

        audio_source: Optional[Union[Path, str]] = None
        audio_format = "mp3"
        vocal_version = kwargs.get("force_vocal_version")

        if preprocessed_mode:
            possible_bundles = [v['vocalAssetbundleName'] for v in song.get('vocals', [])
                                if v['vocalAssetbundleName'] in self.cache_service.preprocessed_tracks.get(preprocessed_mode, set())]
            if not possible_bundles:
                logger.error(f"歌曲 '{song.get('title')}' 没有适用于 '{preprocessed_mode}' 模式的可用音轨。")
                return None
            chosen_bundle = random.choice(possible_bundles)
            relative_path = f"{preprocessed_mode}/{chosen_bundle}.mp3"
            audio_source = self.cache_service.get_resource_path_or_url(relative_path)
        elif is_piano_mode:
            all_song_bundles = {v['vocalAssetbundleName'] for v in song.get('vocals', [])}
            valid_piano_bundles = list(all_song_bundles.intersection(self.cache_service.available_piano_songs_bundles))
            if not valid_piano_bundles:
                logger.error(f"逻辑错误：歌曲 '{song.get('title')}' 在可用钢琴曲列表中，但找不到任何有效的音轨bundle。")
                return None
            chosen_bundle = random.choice(valid_piano_bundles)
            relative_path = f"songs_piano_trimmed_mp3/{chosen_bundle}/{chosen_bundle}.mp3"
            audio_source = self.cache_service.get_resource_path_or_url(relative_path)
        else:
            if not vocal_version:
                if not song.get("vocals"):
                    logger.error(f"歌曲 '{song.get('title')}' 没有任何演唱版本信息。")
                    return None
                sekai_ver = next((v for v in song.get('vocals', []) if v.get('musicVocalType') == 'sekai'), None)
                vocal_version = sekai_ver if sekai_ver else random.choice(song.get("vocals", []))
            
            if vocal_version:
                bundle_name = vocal_version["vocalAssetbundleName"]
                relative_path = f"songs/{bundle_name}/{bundle_name}.mp3"
                audio_source = self.cache_service.get_resource_path_or_url(relative_path)

        if not audio_source:
            mode_name = preprocessed_mode or ('piano' if is_piano_mode else 'normal')
            song_title = song.get('title')
            logger.error(f"未能为歌曲 '{song_title}' 的 '{mode_name}' 模式找到有效的音频文件。")
            return None

        is_bass_boost = preprocessed_mode == 'bass_only'
        has_speed_change = kwargs.get("speed_multiplier", 1.0) != 1.0
        has_reverse = kwargs.get("reverse_audio", False)
        has_band_pass = kwargs.get("band_pass")
        use_slow_path = is_bass_boost or has_speed_change or has_reverse or has_band_pass

        loop = asyncio.get_running_loop()
        
        if not use_slow_path:
            try:
                total_duration_ms = await loop.run_in_executor(self.executor, self._get_duration_ms_ffprobe_sync, audio_source)
                if total_duration_ms is None: raise ValueError("ffprobe failed or not found.")

                target_duration_ms = int(self.config.get("clip_duration_seconds", 10) * 1000)
                if preprocessed_mode in ["drums_only", "bass_only"]: target_duration_ms *= 2
                source_duration_ms = target_duration_ms
                
                start_range_min = 0
                if not preprocessed_mode and not is_piano_mode:
                    start_range_min = int(song.get("fillerSec", 0) * 1000)
                
                start_range_max = int(total_duration_ms - source_duration_ms)
                start_ms = random.randint(start_range_min, start_range_max) if start_range_min < start_range_max else start_range_min
                duration_to_clip_ms = source_duration_ms

                clip_path_obj = self.output_dir / f"clip_{int(time.time())}.mp3"
                command = [
                    'ffmpeg', '-ss', str(start_ms / 1000.0), '-i', str(audio_source),
                    '-t', str(duration_to_clip_ms / 1000.0), '-c', 'copy', '-y', str(clip_path_obj)
                ]
                
                run_subprocess = partial(subprocess.run, command, capture_output=True, text=True, check=True, encoding='utf-8')
                result = await loop.run_in_executor(self.executor, run_subprocess)

                if result.returncode != 0: raise RuntimeError(f"ffmpeg clipping failed: {result.stderr}")
                
                mode_key = kwargs.get("random_mode_name") or kwargs.get('play_preprocessed') or ("melody_to_piano" if is_piano_mode else "normal")
                
                return {"song": song, "clip_path": str(clip_path_obj), "score": kwargs.get("score", 1), "mode": mode_key, "game_type": kwargs.get('game_type')}

            except Exception as e:
                logger.warning(f"快速路径处理失败: {e}. 将回退到 pydub 慢速路径。")
        
        # 慢速路径 (使用pydub，兼容复杂效果)
        try:
            audio_data: Union[str, Path, io.BytesIO]
            if isinstance(audio_source, str) and audio_source.startswith(('http://', 'https://')):
                session = await self._get_session()
                if not session:
                    logger.error("无法获取 aiohttp session")
                    return None
                async with session.get(audio_source) as response:
                    response.raise_for_status()
                    audio_data = io.BytesIO(await response.read())
            else:
                audio_data = audio_source
            
            pydub_kwargs = {
                "preprocessed_mode": preprocessed_mode,
                "target_duration_seconds": self.config.get("clip_duration_seconds", 10),
                "speed_multiplier": kwargs.get("speed_multiplier", 1.0),
                "reverse_audio": kwargs.get("reverse_audio", False),
                "band_pass": kwargs.get("band_pass"),
                "is_piano_mode": is_piano_mode,
                "song_filler_sec": song.get("fillerSec", 0)
            }
            
            clip = await loop.run_in_executor(self.executor, self._process_audio_with_pydub, audio_data, audio_format, pydub_kwargs)

            if clip is None: raise RuntimeError("pydub audio processing failed.")

            mode = kwargs.get("random_mode_name") or kwargs.get('play_preprocessed') or ("melody_to_piano" if is_piano_mode else "normal")
            
            clip_path = self.output_dir / f"clip_{int(time.time())}.mp3"
            clip.export(clip_path, format="mp3", bitrate="128k")

            return {"song": song, "clip_path": str(clip_path), "score": kwargs.get("score", 1), "mode": mode, "game_type": kwargs.get('game_type')}

        except Exception as e:
            logger.error(f"慢速路径 (pydub) 处理音频文件 {audio_source} 时失败: {e}", exc_info=True)
            return None
    
    def _get_duration_ms_ffprobe_sync(self, file_path: Union[Path, str]) -> Optional[float]:
        """[同步] 使用 ffprobe 高效获取音频时长。"""
        command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
            return float(result.stdout.strip()) * 1000
        except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as e:
            logger.error(f"使用 ffprobe 获取时长失败 ({type(e).__name__}): {e}")
            return None

    def _process_audio_with_pydub(self, audio_data: Union[str, Path, io.BytesIO], audio_format: str, options: dict) -> Optional['AudioSegment']:
        """[同步] 在线程池中执行的同步pydub处理逻辑"""
        try:
            audio = AudioSegment.from_file(audio_data, format=audio_format)
            preprocessed_mode = options.get("preprocessed_mode")
            if preprocessed_mode == "bass_only": audio += 6
            target_duration_ms = int(options.get("target_duration_seconds", 10) * 1000)
            if preprocessed_mode in ["bass_only", "drums_only"]: target_duration_ms *= 2
            speed_multiplier = options.get("speed_multiplier", 1.0)
            source_duration_ms = int(target_duration_ms * speed_multiplier)
            total_duration_ms = len(audio)
            
            if source_duration_ms >= total_duration_ms:
                clip_segment = audio
            else:
                start_range_min = 0
                if not preprocessed_mode and not options.get("is_piano_mode"):
                    start_range_min = int(options.get("song_filler_sec", 0) * 1000)
                start_range_max = total_duration_ms - source_duration_ms
                start_ms = random.randint(start_range_min, start_range_max) if start_range_min < start_range_max else start_range_min
                end_ms = start_ms + source_duration_ms
                clip_segment = audio[start_ms:end_ms]

            clip = clip_segment
            if speed_multiplier != 1.0:
                clip = clip._spawn(clip.raw_data, overrides={'frame_rate': int(clip.frame_rate * speed_multiplier)})
            if options.get("reverse_audio", False):
                clip = clip.reverse()
            band_pass = options.get("band_pass")
            if band_pass and isinstance(band_pass, tuple) and len(band_pass) == 2:
                low_freq, high_freq = band_pass
                clip = clip.high_pass_filter(low_freq).low_pass_filter(high_freq) + 6
            return clip
        except Exception as e:
            logger.error(f"Pydub processing in executor failed: {e}", exc_info=True)
            return None
    
    async def create_options_image(self, options: List[Dict]) -> Optional[str]:
        """为12个歌曲选项创建一个3x4的图鉴"""
        if not options or len(options) != 12: return None
        tasks = [self.cache_service.open_image(f"music_jacket/{opt['jacketAssetbundleName']}.png") for opt in options]
        jacket_images = await asyncio.gather(*tasks)
        loop = asyncio.get_running_loop()
        try:
            img_path = await loop.run_in_executor(self.executor, self._draw_options_image_sync, options, jacket_images)
            return img_path
        except Exception as e:
            logger.error(f"在executor中创建选项图片失败: {e}", exc_info=True)
            return None
    
    def _draw_options_image_sync(self, options: List[Dict], jacket_images: List[Optional[Image.Image]]) -> Optional[str]:
        """[同步] 选项图片绘制函数"""
        jacket_w, jacket_h = 128, 128
        padding = 15
        text_h = 50
        cols, rows = 3, 4
        img_w = cols * jacket_w + (cols + 1) * padding
        img_h = rows * (jacket_h + text_h) + (rows + 1) * padding
        img = Image.new('RGBA', (img_w, img_h), (245, 245, 245, 255))
        try:
            font_path = str(self.resources_dir / "font.ttf")
            title_font = ImageFont.truetype(font_path, 16)
            num_font = ImageFont.truetype(font_path, 22)
        except IOError:
            title_font = ImageFont.load_default()
            num_font = title_font
        draw = ImageDraw.Draw(img)
        for i, option in enumerate(options):
            jacket_img = jacket_images[i]
            if not jacket_img: continue
            row_idx, col_idx = i // cols, i % cols
            x = padding + col_idx * (jacket_w + padding)
            y = padding + row_idx * (jacket_h + text_h + padding)
            try:
                jacket = jacket_img.convert("RGBA").resize((jacket_w, jacket_h), LANCZOS)
                img.paste(jacket, (x, y), jacket)
                num_text = f"{i + 1}"
                circle_radius = 16
                circle_center = (x + circle_radius, y + circle_radius)
                draw.ellipse((circle_center[0] - circle_radius, circle_center[1] - circle_radius,
                                circle_center[0] + circle_radius, circle_center[1] + circle_radius),
                                fill=(0, 0, 0, 180))
                with Pilmoji(img) as pilmoji_drawer:
                    pilmoji_drawer.text(circle_center, num_text, font=num_font, fill=(255, 255, 255), anchor="mm")
                title = option['title']
                if title_font.getbbox(title)[2] > jacket_w:
                    while title_font.getbbox(title + "...")[2] > jacket_w and len(title) > 1:
                        title = title[:-1]
                    title += "..."
                title_bbox = draw.textbbox((0, 0), title, font=title_font)
                title_w = title_bbox[2] - title_bbox[0]
                text_x = x + (jacket_w - title_w) / 2
                text_y = y + jacket_h + 8
                draw.text((text_x, text_y), title, font=title_font, fill=(30, 30, 50))
            except Exception as e:
                logger.error(f"处理歌曲封面失败: {option.get('title')}, 错误: {e}")
                continue
        img_path = self.output_dir / f"song_options_{int(time.time())}.png"
        img.save(img_path)
        return str(img_path)

    async def draw_ranking_image(self, rows, title_text="猜歌排行榜") -> Optional[str]:
        """异步绘制排行榜图片。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._draw_ranking_image_sync, rows, title_text)

    def _draw_ranking_image_sync(self, rows, title_text="猜歌排行榜") -> Optional[str]:
        """[同步] 排行榜图片绘制函数"""
        try:
            width, height = 650, 950
            bg_color_start, bg_color_end = (230, 240, 255), (200, 210, 240)
            img = Image.new("RGB", (width, height), bg_color_start)
            draw_bg = ImageDraw.Draw(img)
            for y in range(height):
                r = int(bg_color_start[0] + (bg_color_end[0] - bg_color_start[0]) * y / height)
                g = int(bg_color_start[1] + (bg_color_end[1] - bg_color_start[1]) * y / height)
                b = int(bg_color_start[2] + (bg_color_end[2] - bg_color_start[2]) * y / height)
                draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
            background_path = self.resources_dir / "ranking_bg.png"
            if background_path.exists():
                try:
                    custom_bg = Image.open(background_path).convert("RGBA").resize((width, height), LANCZOS)
                    custom_bg.putalpha(128)
                    img = img.convert("RGBA")
                    img = Image.alpha_composite(img, custom_bg)
                except Exception as e:
                    logger.warning(f"加载或混合自定义背景图片失败: {e}")
            if img.mode != 'RGBA': img = img.convert('RGBA')
            white_overlay = Image.new("RGBA", img.size, (255, 255, 255, 100))
            img = Image.alpha_composite(img, white_overlay)
            font_color, shadow_color = (30, 30, 50), (180, 180, 190, 128)
            header_color, score_color, accuracy_color = (80, 90, 120), (235, 120, 20), (0, 128, 128)
            try:
                font_path = self.resources_dir / "font.ttf"
                title_font = ImageFont.truetype(str(font_path), 48)
                header_font = ImageFont.truetype(str(font_path), 28)
                body_font = ImageFont.truetype(str(font_path), 26)
                id_font = ImageFont.truetype(str(font_path), 16)
                medal_font = ImageFont.truetype(str(font_path), 36)
            except IOError:
                title_font, header_font, body_font, id_font = [ImageFont.load_default()] * 4
                medal_font = body_font
            with Pilmoji(img) as pilmoji:
                center_x, title_y = int(width / 2), 80
                pilmoji.text((center_x + 2, title_y + 2), title_text, font=title_font, fill=shadow_color, anchor="mm")
                pilmoji.text((center_x, title_y), title_text, font=title_font, fill=font_color, anchor="mm")
                headers = ["排名", "玩家", "总分", "正确率", "总次数"]
                col_positions_header = [40, 120, 320, 450, 560]
                current_y = title_y + int(pilmoji.getsize(title_text, font=title_font)[1] / 2) + 45
                for i, header in enumerate(headers):
                    pilmoji.text((col_positions_header[i], current_y), header, font=header_font, fill=header_color)
                current_y += 55
                rank_icons = ["🥇", "🥈", "🥉"]
                for i, row in enumerate(rows):
                    user_id, user_name, score, attempts, correct_attempts = str(row[0]), row[1], str(row[2]), str(row[3]), row[4]
                    if attempts == -1:
                        accuracy = "N/A"
                        attempts_str = "N/A"
                    else:
                        attempts_str = str(attempts)
                        accuracy = f"{(correct_attempts * 100 / int(attempts) if int(attempts) > 0 else 0):.1f}%"
                    rank = i + 1
                    col_positions = [40, 120, 320, 450, 560]
                    pilmoji.text((100, current_y), str(rank), font=body_font, fill=font_color, anchor="ra")
                    if i < 3:
                        pilmoji.text((col_positions[0], current_y - 2), rank_icons[i], font=medal_font, fill=font_color)
                    max_name_width = col_positions[2] - col_positions[1] - 20
                    if body_font.getbbox(user_name)[2] > max_name_width:
                        while body_font.getbbox(user_name + "...")[2] > max_name_width and len(user_name) > 0:
                            user_name = user_name[:-1]
                        user_name += "..."
                    pilmoji.text((col_positions[1], current_y), user_name, font=body_font, fill=font_color)
                    pilmoji.text((col_positions[1], current_y + 32), f"ID: {user_id}", font=id_font, fill=header_color)
                    pilmoji.text((col_positions[2], current_y), score, font=body_font, fill=score_color)
                    pilmoji.text((col_positions[3], current_y), accuracy, font=body_font, fill=accuracy_color)
                    pilmoji.text((col_positions[4], current_y), attempts_str, font=body_font, fill=font_color)
                    if i < len(rows) - 1:
                        draw = ImageDraw.Draw(img)
                        draw.line([(30, current_y + 60), (width - 30, current_y + 60)], fill=(200, 200, 210, 128), width=1)
                    current_y += 70
                footer_text = f"GuessSong v{self.plugin_version} | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                pilmoji.text((center_x, height - 25), footer_text, font=id_font, fill=header_color, anchor="ms")
            img_path = self.output_dir / f"song_ranking_{int(time.time())}.png"
            img.save(img_path)
            return str(img_path)
        except Exception as e:
            logger.error(f"生成猜歌排行榜图片时出错: {e}", exc_info=True)
            return None

    async def draw_mode_stats_image(self, stats) -> Optional[str]:
        """异步绘制题型统计图片。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._draw_mode_stats_image_sync, stats)

    def _draw_mode_stats_image_sync(self, stats) -> Optional[str]:
        """[同步] 题型统计图片绘制函数。"""
        try:
            width, height = 650, 950
            bg_color_start, bg_color_end = (230, 240, 255), (200, 210, 240)
            img = Image.new("RGB", (width, height), bg_color_start)
            draw_bg = ImageDraw.Draw(img)
            for y in range(height):
                r = int(bg_color_start[0] + (bg_color_end[0] - bg_color_start[0]) * y / height)
                g = int(bg_color_start[1] + (bg_color_end[1] - bg_color_start[1]) * y / height)
                b = int(bg_color_start[2] + (bg_color_end[2] - bg_color_start[2]) * y / height)
                draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
            background_path = self.resources_dir / "ranking_bg.png"
            if background_path.exists():
                try:
                    custom_bg = Image.open(background_path).convert("RGBA").resize((width, height), LANCZOS)
                    custom_bg.putalpha(128)
                    img = img.convert("RGBA")
                    img = Image.alpha_composite(img, custom_bg)
                except Exception as e:
                    logger.warning(f"加载或混合自定义背景图片失败: {e}")
            if img.mode != 'RGBA': img = img.convert('RGBA')
            white_overlay = Image.new("RGBA", img.size, (255, 255, 255, 100))
            img = Image.alpha_composite(img, white_overlay)
            font_color, shadow_color = (30, 30, 50), (180, 180, 190, 128)
            header_color, score_color, accuracy_color = (80, 90, 120), (235, 120, 20), (0, 128, 128)
            try:
                font_path = self.resources_dir / "font.ttf"
                title_font = ImageFont.truetype(str(font_path), 44)
                header_font = ImageFont.truetype(str(font_path), 28)
                body_font = ImageFont.truetype(str(font_path), 26)
            except IOError:
                title_font = header_font = body_font = ImageFont.load_default()
            with Pilmoji(img) as pilmoji:
                title_text = "题型正确率排行"
                center_x, title_y = int(width / 2), 60
                pilmoji.text((center_x + 2, title_y + 2), title_text, font=title_font, fill=shadow_color, anchor="mm")
                pilmoji.text((center_x, title_y), title_text, font=title_font, fill=font_color, anchor="mm")
                headers = ["题型", "答对/总数", "正确率"]
                col_positions = [60, 320, 500]
                current_y = title_y + 50
                for i, header in enumerate(headers):
                    pilmoji.text((col_positions[i], current_y), header, font=header_font, fill=header_color)
                current_y += 45
                max_mode_width = col_positions[1] - col_positions[0] - 20
                for i, (mode, total, correct, acc) in enumerate(stats):
                    mode_disp = self._mode_display_name(mode)
                    lines = []
                    temp = ""
                    for ch in mode_disp:
                        if pilmoji.getsize(temp + ch, font=body_font)[0] > max_mode_width and temp:
                            lines.append(temp)
                            temp = ch
                        else:
                            temp += ch
                    if temp: lines.append(temp)
                    line_spacing = 32
                    block_height = line_spacing * (len(lines))
                    row_center_y = current_y + block_height / 2
                    for idx, line in enumerate(lines):
                        pilmoji.text((col_positions[0], current_y + idx * line_spacing + 5), line, font=body_font, fill=font_color)
                    pilmoji.text((col_positions[1], row_center_y), f"{correct}/{total}", font=body_font, fill=score_color, anchor="lm")
                    pilmoji.text((col_positions[2], row_center_y), f"{acc:.1f}%", font=body_font, fill=accuracy_color, anchor="lm")
                    row_height = max(70, block_height + 15)
                    if i < len(stats) - 1:
                        draw = ImageDraw.Draw(img)
                        draw.line([(40, current_y + row_height - 8), (width - 40, current_y + row_height - 8)], fill=(200, 200, 210, 128), width=1)
                    current_y += row_height
                footer_text = f"GuessSong v{self.plugin_version} | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                pilmoji.text((center_x, height - 40), footer_text, font=body_font, fill=header_color, anchor="ms")
            img_path = self.output_dir / f"mode_stats_{int(time.time())}.png"
            img.save(img_path)
            return str(img_path)
        except Exception as e:
            logger.error(f"生成题型统计图片时出错: {e}", exc_info=True)
            return None

    async def draw_help_image(self) -> Optional[str]:
        """异步绘制帮助图片。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._draw_help_image_sync)

    def _draw_help_image_sync(self) -> Optional[str]:
        """[同步] 帮助图片绘制函数。"""
        try:
            width, height = 800, 1350
            bg_color_start, bg_color_end = (230, 240, 255), (200, 210, 240)
            img = Image.new("RGB", (width, height), bg_color_start)
            draw_bg = ImageDraw.Draw(img)
            for y in range(height):
                r = int(bg_color_start[0] + (bg_color_end[0] - bg_color_start[0]) * y / height)
                g = int(bg_color_start[1] + (bg_color_end[1] - bg_color_start[1]) * y / height)
                b = int(bg_color_start[2] + (bg_color_end[2] - bg_color_start[2]) * y / height)
                draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
            background_path = self.resources_dir / "ranking_bg.png"
            if background_path.exists():
                try:
                    custom_bg = Image.open(background_path).convert("RGBA").resize((width, height), LANCZOS)
                    custom_bg.putalpha(128)
                    img = img.convert("RGBA")
                    img = Image.alpha_composite(img, custom_bg)
                except Exception as e:
                    logger.warning(f"加载或混合自定义背景图片失败: {e}")
            if img.mode != 'RGBA': img = img.convert('RGBA')
            white_overlay = Image.new("RGBA", img.size, (255, 255, 255, 100))
            img = Image.alpha_composite(img, white_overlay)
            font_color, shadow_color = (30, 30, 50), (180, 180, 190, 128)
            header_color = (80, 90, 120)
            try:
                font_path = str(self.resources_dir / "font.ttf")
                title_font = ImageFont.truetype(font_path, 48)
                section_font = ImageFont.truetype(font_path, 32)
                body_font = ImageFont.truetype(font_path, 24)
                id_font = ImageFont.truetype(font_path, 16)
                # 为特殊行创建一个更大的字体
                special_font = ImageFont.truetype(font_path, 30)
            except IOError:
                title_font = ImageFont.load_default(size=48)
                section_font = ImageFont.load_default(size=32)
                body_font = ImageFont.load_default(size=24)
                id_font = ImageFont.load_default(size=16)
                # 如果主字体加载失败，特殊字体也使用一个较大的默认值
                special_font = ImageFont.load_default(size=30)

            help_text = (
                "--- PJSK猜歌插件帮助 ---\n\n"
                "🎵 基础指令\n"
                f"  `猜歌` - {self.game_modes['normal']['name']} ({self.game_modes['normal']['score']}分)\n"
                f"  `猜歌 1` - {self.game_modes['1']['name']} ({self.game_modes['1']['score']}分)\n"
                f"  `猜歌 2` - {self.game_modes['2']['name']} ({self.game_modes['2']['score']}分)\n"
                f"  `猜歌 3` - {self.game_modes['3']['name']} ({self.game_modes['3']['score']}分)\n"
                f"  `猜歌 4` - {self.game_modes['4']['name']} ({self.game_modes['4']['score']}分)\n"
                f"  `猜歌 5` - {self.game_modes['5']['name']} ({self.game_modes['5']['score']}分)\n"
                f"  `猜歌 6` - {self.game_modes['6']['name']} ({self.game_modes['6']['score']}分)\n"
                f"  `猜歌 7` - {self.game_modes['7']['name']} ({self.game_modes['7']['score']}分)\n\n"
                "🎲 高级指令\n"
                "  `随机猜歌` - 随机组合效果 (最高9分)\n"
                "  `猜歌手` - 竞猜演唱者 (测试功能, 不计分)\n"
                "  `听<模式> [歌名/ID]` - 播放指定或随机歌曲的特殊音轨。\n"
                "    可用模式: 钢琴, 伴奏, 人声, 贝斯, 鼓组\n"
                "  `听anvo [歌名/ID] [角色名缩写]` - 播放指定或随机的 Another Vocal，你可以选择一个角色来随机播放。\n"
                "    (所有听歌指令共享每日次数限制)\n\n"
                "📊 数据统计\n"
                "  `猜歌分数` - 查看自己的猜歌积分和排名\n"
                "  `群猜歌排行榜` - 查看本群猜歌排行榜\n"
                "  `本地猜歌排行榜` - 查看插件本地存储的猜歌排行榜\n"
                "  `猜歌排行榜` - 查看服务器猜歌总排行榜 (联网)\n"
                "  `同步分数` - (管理员)将本地总分同步至服务器\n"
                "  `查看统计` - 查看各题型的正确率排行\n\n"
            )
            with Pilmoji(img) as pilmoji:
                center_x, current_y = width // 2, 80
                x_margin = 60
                line_height_body = 40
                line_height_section = 55
                lines = help_text.split('\n')
                title_text = lines[0].replace("---", "").strip()
                pilmoji.text((int(center_x) + 2, int(current_y) + 2), title_text, font=title_font, fill=shadow_color, anchor="mm")
                pilmoji.text((int(center_x), int(current_y)), title_text, font=title_font, fill=font_color, anchor="mm")
                current_y += 100
                for line in lines[2:]:
                    if not line.strip():
                        current_y += line_height_body // 2
                        continue
                    
                    # 检查是否是特殊行
                    is_special_line = "♿" in line

                    if is_special_line:
                        font = special_font
                        y_increment = line_height_section # 使用稍大的行高
                        text_to_draw = line.strip()
                    elif line.startswith("🎵") or line.startswith("🎲") or line.startswith("📊"):
                        font = section_font
                        y_increment = line_height_section
                        text_to_draw = line.strip()
                    else:
                        font = body_font
                        y_increment = line_height_body
                        text_to_draw = line

                    pilmoji.text((x_margin, int(current_y)), text_to_draw, font=font, fill=font_color)
                    current_y += y_increment
                footer_text = f"GuessSong v{self.plugin_version} | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                pilmoji.text((int(center_x), height - 40), footer_text, font=id_font, fill=header_color, anchor="ms")
            img_path = self.output_dir / f"guess_song_help_{int(time.time())}.png"
            img.save(img_path)
            return str(img_path)
        except Exception as e:
            logger.error(f"生成帮助图片时出错: {e}", exc_info=True)
            return None

    def get_random_mode_config(self) -> Tuple[Dict, int, str, str]:
        """生成随机模式的配置。"""
        combinations_by_score = self._precompute_random_combinations()
        if not combinations_by_score: return {}, 0, "", ""
        
        target_distribution = self._get_random_target_distribution(combinations_by_score)
        scores = list(target_distribution.keys())
        probabilities = list(target_distribution.values())
        target_score = random.choices(scores, weights=probabilities, k=1)[0]
        
        valid_combinations = combinations_by_score[target_score]
        chosen_processed_combo = random.choice(valid_combinations)

        combined_kwargs = chosen_processed_combo['final_kwargs']
        total_score = chosen_processed_combo['final_score']
        
        effect_names = [eff['name'] for eff in chosen_processed_combo['effects_list']]
        effect_names_display = sorted(list(set(effect_names)))
        speed_mult = combined_kwargs.get('speed_multiplier')
        has_reverse = 'reverse_audio' in combined_kwargs

        if speed_mult and has_reverse:
            effect_names_display = [n for n in effect_names_display if n not in ['倒放', '2倍速', '1.5倍速']]
            effect_names_display.append(f"倒放+{speed_mult}倍速组合(+1分)")
        
        mode_name_str = '+'.join(sorted([name.replace(' ver.', '') for name in effect_names if name != 'Off']))
        return combined_kwargs, total_score, "、".join(effect_names_display), mode_name_str

    def _precompute_random_combinations(self) -> Dict[int, List[Dict]]:
        """预计算所有可行的随机效果组合。"""
        combinations_by_score = defaultdict(list)
        playable_source_effects = []
        for effect in self.source_effects:
            kwargs = effect.get('kwargs', {})
            if 'play_preprocessed' in kwargs:
                mode = kwargs['play_preprocessed']
                if self.cache_service.preprocessed_tracks.get(mode):
                    playable_source_effects.append(effect)
            elif 'melody_to_piano' in kwargs:
                if self.cache_service.available_piano_songs:
                    playable_source_effects.append(effect)
            else:
                playable_source_effects.append(effect)

        independent_options = []
        active_base_effects = [] if self.config.get("lightweight_mode", False) else self.base_effects
        for effect in active_base_effects:
            independent_options.append([effect, {'name': 'Off', 'score': 0, 'kwargs': {}}])

        if not playable_source_effects:
            return {}

        for source_effect in playable_source_effects:
            for independent_choices in itertools.product(*independent_options):
                is_piano_mode = 'melody_to_piano' in source_effect.get('kwargs', {})
                has_reverse_effect = any('reverse_audio' in choice.get('kwargs', {}) for choice in independent_choices)
                if is_piano_mode and has_reverse_effect:
                    continue
                
                raw_combination = [source_effect] + [choice for choice in independent_choices if choice['score'] > 0]
                
                final_effects_list = []
                final_kwargs = {}
                base_score = 0
                
                is_multi_effect = len(raw_combination) > 1
                
                for effect_template in raw_combination:
                    effect = {k: (v.copy() if isinstance(v, dict) else v) for k, v in effect_template.items()}
                    
                    if is_multi_effect and 'speed_multiplier' in effect.get('kwargs', {}):
                        effect['kwargs']['speed_multiplier'] = 1.5
                        effect['name'] = '1.5倍速'
                    
                    final_effects_list.append(effect)
                    final_kwargs.update(effect.get('kwargs', {}))
                    base_score += effect.get('score', 0)

                final_score = base_score
                if 'speed_multiplier' in final_kwargs and 'reverse_audio' in final_kwargs:
                    final_score += 1

                processed_combo = {
                    'effects_list': final_effects_list,
                    'final_kwargs': final_kwargs,
                    'final_score': final_score,
                }
                combinations_by_score[final_score].append(processed_combo)
        return dict(combinations_by_score)

    def _get_random_target_distribution(self, combinations_by_score: Dict[int, list]) -> Dict[int, float]:
        """根据预计算的组合和衰减因子，生成目标分数概率分布。"""
        if not combinations_by_score: return {}
        scores = sorted(combinations_by_score.keys())
        decay_factor = self.random_mode_decay_factor
        weights = [decay_factor ** score for score in scores]
        total_weight = sum(weights)
        if total_weight == 0:
            return {score: 1.0 / len(scores) for score in scores}
        probabilities = [w / total_weight for w in weights]
        return dict(zip(scores, probabilities))

    def _mode_display_name(self, mode_key: str) -> str:
        """(重构) 题型名美化，支持稳定ID"""
        default_map = {"normal": "普通"}
        if mode_key in default_map: return default_map[mode_key]
        if mode_key.startswith("random_"):
            ids = mode_key.replace("random_", "").split('+')
            names = [self.game_effects.get(i, {}).get('name', i) for i in ids]
            return "随机-" + "+".join(names)
        return self.game_effects.get(mode_key, {}).get('name', mode_key)

    async def get_listen_song_and_path(self, mode: str, search_term: Optional[str]) -> Tuple[Optional[Dict], Optional[Union[Path, str]]]:
        """获取听歌模式的歌曲和文件路径。"""
        config = self.listen_modes[mode]
        available_songs = getattr(self.cache_service, config['list_attr'])
        
        song_to_play = None
        if search_term:
            if search_term.isdigit():
                music_id_to_find = int(search_term)
                song_to_play = next((s for s in available_songs if s['id'] == music_id_to_find), None)
            else:
                found_songs = [s for s in available_songs if search_term.lower() in s['title'].lower()]
                if found_songs:
                    exact_match = next((s for s in found_songs if s['title'].lower() == search_term.lower()), None)
                    song_to_play = exact_match or min(found_songs, key=lambda s: len(s['title']))
        else:
            song_to_play = random.choice(available_songs)
        
        if not song_to_play:
            return None, None
            
        mp3_source: Optional[Union[Path, str]] = None
        if config['is_piano']:
            all_song_bundles = {v['vocalAssetbundleName'] for v in song_to_play.get('vocals', [])}
            valid_piano_bundles = list(all_song_bundles.intersection(self.cache_service.available_piano_songs_bundles))
            if valid_piano_bundles:
                chosen_bundle = random.choice(valid_piano_bundles)
                relative_path = f"songs_piano_trimmed_mp3/{chosen_bundle}/{chosen_bundle}.mp3"
                mp3_source = self.cache_service.get_resource_path_or_url(relative_path)
        else:
            sekai_ver = next((v for v in song_to_play.get('vocals', []) if v.get('musicVocalType') == 'sekai'), None)
            bundle_name = None
            if sekai_ver:
                bundle_name = sekai_ver.get('vocalAssetbundleName')
            elif song_to_play.get('vocals'):
                bundle_name = song_to_play['vocals'][0].get('vocalAssetbundleName')
            
            if bundle_name and bundle_name in self.cache_service.preprocessed_tracks[config['file_key']]:
                relative_path = f"{config['file_key']}/{bundle_name}.mp3"
                mp3_source = self.cache_service.get_resource_path_or_url(relative_path)

        return song_to_play, mp3_source

    async def get_anvo_song_and_vocal(self, content: str, another_vocal_songs: List[Dict], char_id_to_anov_songs: Dict, abbr_to_char_id: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
        """根据用户输入解析并返回Another Vocal歌曲和版本。"""
        song_to_play, vocal_info = None, None

        if not content:
            song_to_play = random.choice(another_vocal_songs)
            anov_list = [v for v in song_to_play.get('vocals', []) if v.get('musicVocalType') == 'another_vocal']
            if anov_list: vocal_info = random.choice(anov_list)
        else:
            parts = content.rsplit(maxsplit=1)
            last_part = parts[-1].lower()
            
            is_char_combo = True
            target_ids = set()
            for abbr in last_part.split('+'):
                char_id = abbr_to_char_id.get(abbr)
                if char_id is None:
                    is_char_combo = False
                    break
                target_ids.add(char_id)
            
            if is_char_combo and len(parts) > 1:
                song_query = parts[0]
                song_to_play = self.cache_service.find_song_by_query(song_query)
                if song_to_play:
                    for v in song_to_play.get('vocals', []):
                        if v.get('musicVocalType') == 'another_vocal' and {c.get('characterId') for c in v.get('characters', [])} == target_ids:
                            vocal_info = v
                            break
            else:
                if len(parts) == 1 and is_char_combo and len(target_ids) == 1:
                    char_id = list(target_ids)[0]
                    songs_by_char = char_id_to_anov_songs.get(char_id)
                    if songs_by_char:
                        song_to_play = random.choice(songs_by_char)
                        solo = next((v for v in song_to_play.get('vocals', []) if v.get('musicVocalType') == 'another_vocal' and len(v.get('characters',[])) == 1 and v['characters'][0].get('characterId') == char_id), None)
                        vocal_info = solo or next((v for v in song_to_play.get('vocals', []) if v.get('musicVocalType') == 'another_vocal' and any(c.get('characterId') == char_id for c in v.get('characters', []))), None)
                else:
                    song_to_play = self.cache_service.find_song_by_query(content)
                    if song_to_play:
                        vocal_info = 'list_versions'
        
        return song_to_play, vocal_info

    async def process_anvo_audio(self, song: Dict, vocal_info: Dict) -> Optional[str]:
        """处理ANVO音频，优先使用缓存文件。"""
        char_ids = [c.get('characterId') for c in vocal_info.get('characters', [])]
        char_id_for_cache = '_'.join(map(str, sorted(char_ids)))
        output_filename = f"anvo_{song['id']}_{char_id_for_cache}.mp3"
        output_path = self.output_dir / output_filename

        if output_path.exists():
            logger.info(f"使用已缓存的ANVO文件: {output_filename}")
            return str(output_path)
        
        logger.info(f"缓存文件 {output_filename} 不存在，正在创建...")
        mp3_source = self.cache_service.get_resource_path_or_url(f"songs/{vocal_info['vocalAssetbundleName']}/{vocal_info['vocalAssetbundleName']}.mp3")
        if not mp3_source:
            logger.error("找不到有效的ANVO音频文件。")
            return None
            
        filler_sec = song.get('fillerSec', 0)
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', str(filler_sec), '-i', str(mp3_source), '-c:a', 'copy', '-f', 'mp3', str(output_path)]
        
        try:
            proc = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(f"FFmpeg failed. Stderr: {stderr.decode(errors='ignore')}")
                if output_path.exists(): os.remove(output_path)
                return None
            return str(output_path)
        except Exception as e:
            logger.error(f"FFmpeg执行失败: {e}", exc_info=True)
            return None
    # 在 services/audio_service.py 的 AudioService 类中添加此方法

    async def draw_personal_stats_image(
        self,
        user_name: str,
        server_stats: Optional[Dict],
        core_mode_stats: Dict,
        detailed_stats: List[Tuple[str, int, int, float]],
    ) -> Optional[str]:
        """[异步] 绘制个人统计报告图片。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.executor,
            self._draw_personal_stats_image_sync,
            user_name,
            server_stats,
            core_mode_stats,
            detailed_stats
        )

    def _draw_personal_stats_image_sync(
        self,
        user_name: str,
        server_stats: Optional[Dict],
        core_mode_stats: Dict,
        detailed_stats: List[Tuple[str, int, int, float]],
    ) -> Optional[str]:
        """[同步] 个人统计报告图片绘制函数 (修正绘图上下文)。"""
        try:
            width, height = 1000, 1200
            
            background_path = self.resources_dir / "ranking_bg.png"
            if background_path.exists():
                img = Image.open(background_path).convert("RGBA")
                if img.size != (width, height):
                    img = img.resize((width, height), LANCZOS)
            else:
                img = Image.new("RGBA", (width, height), (230, 240, 255)).convert("RGBA")
            
            white_overlay = Image.new("RGBA", img.size, (255, 255, 255, 185))
            img = Image.alpha_composite(img, white_overlay)

            font_path = self.resources_dir / "font.ttf"
            font_title = ImageFont.truetype(str(font_path), 38)
            font_subtitle = ImageFont.truetype(str(font_path), 24)
            font_header = ImageFont.truetype(str(font_path), 28)
            font_body_bold = ImageFont.truetype(str(font_path), 26)
            font_body = ImageFont.truetype(str(font_path), 24)
            font_footer = ImageFont.truetype(str(font_path), 16)

            c_title = (40, 45, 60)
            c_text = (50, 55, 70)
            c_highlight = (10, 130, 140)
            c_dim = (140, 145, 160)
            c_line = (200, 205, 215, 150)

            # 关键修正: 统一在 Pilmoji 上下文管理器中进行所有绘制
            with Pilmoji(img) as pilmoji:
                # 从 Pilmoji 获取唯一的 Draw 对象
                draw = pilmoji.draw

                center_x, margin, y = width // 2, 100, 100
                
                pilmoji.text((center_x, y), f"{user_name} 的模式统计报告", font=font_title, fill=c_title, anchor="ms")
                y += 50
                
                if server_stats and server_stats.get('rank') is not None:
                    server_text = f"全服总排名: {server_stats.get('rank', 'N/A')}   |   总分数: {server_stats.get('total_score', 0)}"
                else:
                    server_text = "全服总排名: 暂无数据"
                pilmoji.text((center_x, y), server_text, font=font_subtitle, fill=c_text, anchor="ms")
                y += 50
                draw.line([(margin, y), (width - margin, y)], fill=c_line, width=2)
                y += 35

                x_name, x_rank, x_percent, x_counts = margin, 500, 750, width - margin
                
                pilmoji.text((x_name, y), "核心模式表现", font=font_header, fill=c_title, anchor="ls")
                pilmoji.text((x_rank, y), "全服排名", font=font_header, fill=c_title, anchor="ms")
                y += 55

                for name, data in core_mode_stats.items():
                    total, correct, rank = data.get('total', 0), data.get('correct', 0), data.get('rank')
                    accuracy = (correct * 100 / total) if total > 0 else 0
                    
                    pilmoji.text((x_name, y), name, font=font_body_bold, fill=c_text, anchor="ls")
                    if rank:
                        pilmoji.text((x_rank, y), f"#{rank}", font=font_body_bold, fill=c_text, anchor="ms")
                    else:
                        pilmoji.text((x_rank, y), "未上榜", font=font_body, fill=c_dim, anchor="ms")
                    
                    pilmoji.text((x_counts, y), f"({correct}/{total})", font=font_body, fill=c_dim, anchor="rs")
                    pilmoji.text((x_percent, y), f"{accuracy:.1f}%", font=font_body_bold, fill=c_highlight, anchor="rs")
                    y += 48
                
                y += 20
                draw.line([(margin, y), (width - margin, y)], fill=c_line, width=2)
                y += 35

                pilmoji.text((x_name, y), "详细模式统计 (按正确率排序)", font=font_header, fill=c_title, anchor="ls")
                y += 50
                x_detail_name = x_name + 20
                
                for name, total, correct, accuracy in detailed_stats[:15]:
                    if y > height - 90: break
                    
                    max_width = x_percent - x_detail_name - 30
                    display_name = name
                    if pilmoji.getsize(display_name, font=font_body)[0] > max_width:
                        while pilmoji.getsize(display_name + "...", font=font_body)[0] > max_width and len(display_name) > 1:
                            display_name = display_name[:-1]
                        display_name += "..."

                    pilmoji.text((x_detail_name, y), f"· {display_name}", font=font_body, fill=c_text, anchor="ls")
                    pilmoji.text((x_counts, y), f"({correct}/{total})", font=font_body, fill=c_dim, anchor="rs")
                    pilmoji.text((x_percent, y), f"{accuracy:.1f}%", font=font_body_bold, fill=c_highlight, anchor="rs")
                    y += 42

                footer_text = f"GuessSong v{self.plugin_version} | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                pilmoji.text((center_x, height - 65), footer_text, font=font_footer, fill=c_dim, anchor="ms")

            output_path = self.output_dir / f"personal_stats_{user_name}_{int(time.time())}.png"
            img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"生成个人统计图片时出错: {e}", exc_info=True)
            return None

    async def terminate(self):
        """关闭 aiohttp session 和线程池"""
        self.executor.shutdown(wait=False)
        if self._session and not self._session.closed:
            await self._session.close()
