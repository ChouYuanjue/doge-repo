import asyncio
import os
import io
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Union
from collections import defaultdict
from PIL import Image
import aiohttp
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from .stats_service import StatsService


class CacheService:
    def __init__(self, resources_dir: Path, output_dir: Path, stats_service: StatsService, config: AstrBotConfig):
        self.resources_dir = resources_dir
        self.output_dir = output_dir
        self.stats_service = stats_service
        self.config = config

        os.makedirs(self.output_dir, exist_ok=True)
        
        self.use_local_resources = self.config.get("use_local_resources", True)
        self.remote_resource_url_base = self.config.get("remote_resource_url_base", "").strip('/')
        
        self.song_data: List[Dict] = []
        self.character_data: Dict[str, Dict] = {}
        self.another_vocal_songs: List[Dict] = []
        self.bundle_to_song_map: Dict[str, Dict] = {}
        self.char_id_to_anov_songs = defaultdict(list)
        self.abbr_to_char_id: Dict[str, int] = {}

        self.available_piano_songs_bundles = set()
        self.preprocessed_tracks = defaultdict(set)

        self.available_piano_songs = []
        self.available_accompaniment_songs = []
        self.available_vocals_songs = []
        self.available_bass_songs = []
        self.available_drums_songs = []

    async def load_resources_and_manifest(self):
        """异步加载所有游戏资源和清单。"""
        if not self._load_song_data() or not self._load_character_data():
            logger.error("核心数据文件加载失败，插件将无法正常工作。")
            return

        if self.use_local_resources:
            self._load_local_manifest()
        else:
            await self._load_remote_manifest()
        
        self._populate_song_lists()

    def _load_song_data(self) -> bool:
        """同步加载 guess_song.json 数据"""
        try:
            songs_file = self.resources_dir / "guess_song.json"
            with open(songs_file, "r", encoding="utf-8") as f:
                self.song_data = json.load(f)
            
            for song_item in self.song_data:
                if 'vocals' in song_item and song_item['vocals']:
                    if any(v.get('musicVocalType') == 'another_vocal' for v in song_item['vocals']):
                        self.another_vocal_songs.append(song_item)
                    for vocal in song_item['vocals']:
                        bundle_name = vocal.get('vocalAssetbundleName')
                        if bundle_name:
                            self.bundle_to_song_map[bundle_name] = song_item

            for song in self.another_vocal_songs:
                processed_chars = set()
                for vocal in song.get('vocals', []):
                    if vocal.get('musicVocalType') == 'another_vocal':
                        for char in vocal.get('characters', []):
                            char_id = char.get('characterId')
                            if char_id and char_id not in processed_chars:
                                self.char_id_to_anov_songs[char_id].append(song)
                                processed_chars.add(char_id)
            
            return True
        except FileNotFoundError as e:
            logger.error(f"加载歌曲数据失败: {e}. 请确保 'guess_song.json' 和 'musicVocals.json' 在 'resources' 目录中。")
            return False
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载或解析歌曲数据失败: {e}")
            return False

    def _load_character_data(self) -> bool:
        """加载角色数据，将角色ID映射到完整的角色信息字典。"""
        characters_path = self.resources_dir / "characters.json"
        if not characters_path.exists():
            logger.warning(f"角色数据文件未找到: {characters_path}")
            return False
        
        try:
            with open(characters_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.character_data = {
                str(item.get("characterId")): item
                for item in data if item.get("characterId")
            }
            
            # 将衍生数据的逻辑迁移到这里
            self.abbr_to_char_id = {
                char_info['name'].lower(): int(char_id)
                for char_id, char_info in self.character_data.items() if char_info.get('name')
            }
            return True
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载或解析角色数据失败: {e}")
            return False

    def _load_local_manifest(self):
        """同步加载本地资源清单。"""
        logger.info("使用本地资源模式，开始扫描文件系统...")
        for mode in ["accompaniment", "bass_only", "drums_only", "vocals_only"]:
            mode_dir = self.resources_dir / mode
            if mode_dir.exists():
                for mp3_file in mode_dir.glob("*.mp3"):
                    self.preprocessed_tracks[mode].add(mp3_file.stem)
                logger.info(f"成功加载 {len(self.preprocessed_tracks[mode])} 个 '{mode}' 模式的本地音轨。")
        
        trimmed_mp3_dir = self.resources_dir / "songs_piano_trimmed_mp3"
        if trimmed_mp3_dir.exists():
            for mp3_path in trimmed_mp3_dir.glob("**/*.mp3"):
                self.available_piano_songs_bundles.add(mp3_path.parent.name)
            logger.info(f"成功加载 {len(self.available_piano_songs_bundles)} 个钢琴模式的本地音轨。")

    async def _load_remote_manifest(self):
        """异步加载远程资源清单。"""
        logger.info("使用远程资源模式，开始获取 manifest.json...")
        manifest_url = self.get_resource_path_or_url("manifest.json")
        if not manifest_url or not isinstance(manifest_url, str):
            logger.error("无法构建 manifest.json 的 URL。插件将无法使用预处理音轨模式。")
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(manifest_url, timeout=10) as response:
                    response.raise_for_status()
                    manifest_data = await response.json()
                    
                    for mode in ["accompaniment", "bass_only", "drums_only", "vocals_only"]:
                        self.preprocessed_tracks[mode] = set(manifest_data.get(mode, []))
                        logger.info(f"成功从 manifest 加载 {len(self.preprocessed_tracks[mode])} 个 '{mode}' 模式的音轨。")
                    
                    self.available_piano_songs_bundles = set(manifest_data.get("songs_piano_trimmed_mp3", []))
                    logger.info(f"成功从 manifest 加载 {len(self.available_piano_songs_bundles)} 个钢琴模式的音轨。")

        except Exception as e:
            logger.error(f"获取或解析远程 manifest.json 失败: {e}。插件将无法使用预处理音轨模式。", exc_info=True)

    def _populate_song_lists(self):
        """根据已加载的音轨信息，填充可用的歌曲列表。"""
        if not self.song_data: return
            
        self.available_accompaniment_songs.clear()
        self.available_vocals_songs.clear()
        self.available_bass_songs.clear()
        self.available_drums_songs.clear()
        self.available_piano_songs.clear()

        song_list_map = {
            'accompaniment': (self.available_accompaniment_songs, set()),
            'vocals_only': (self.available_vocals_songs, set()),
            'bass_only': (self.available_bass_songs, set()),
            'drums_only': (self.available_drums_songs, set()),
        }

        for mode, bundles in self.preprocessed_tracks.items():
            if mode in song_list_map:
                song_list, processed_ids = song_list_map[mode]
                for bundle_name in bundles:
                    if bundle_name in self.bundle_to_song_map:
                        song = self.bundle_to_song_map[bundle_name]
                        if song['id'] not in processed_ids:
                            song_list.append(song)
                            processed_ids.add(song['id'])
        
        piano_processed_ids = set()
        for bundle_name in self.available_piano_songs_bundles:
            if bundle_name in self.bundle_to_song_map:
                song = self.bundle_to_song_map[bundle_name]
                if song['id'] not in piano_processed_ids:
                    self.available_piano_songs.append(song)
                    piano_processed_ids.add(song['id'])
        logger.info(f"找到了 {len(self.available_piano_songs)} 首拥有预生成MP3的歌曲。")

    async def periodic_cleanup_task(self):
        """每隔一小时自动清理一次 output 目录。"""
        cleanup_interval_seconds = 3600
        while True:
            await asyncio.sleep(cleanup_interval_seconds)
            logger.info("开始周期性清理 output 目录...")
            self.cleanup_output_dir()
    
    def cleanup_output_dir(self, max_age_seconds: int = 3600):
        """清理过时的输出文件。"""
        if not self.output_dir.exists(): return
        now = time.time()
        for filename in os.listdir(self.output_dir):
            file_path = self.output_dir / filename
            if file_path.is_file() and (file_path.suffix in ['.png', '.wav', '.mp3']):
                if (now - file_path.stat().st_mtime) > max_age_seconds:
                    os.remove(file_path)
                    logger.info(f"已清理旧的输出文件: {filename}")

    def get_resource_path_or_url(self, relative_path: str) -> Optional[Union[Path, str]]:
        """根据配置返回资源的本地Path对象或远程URL字符串。"""
        if self.use_local_resources:
            path = self.resources_dir / relative_path
            return path if path.exists() else None
        else:
            if not self.remote_resource_url_base:
                logger.error("配置为使用远程资源，但 remote_resource_url_base 未设置。")
                return None
            return f"{self.remote_resource_url_base}/{'/'.join(Path(relative_path).parts)}"

    async def open_image(self, relative_path: str) -> Optional[Image.Image]:
        """打开一个资源图片，无论是本地路径还是远程URL。"""
        source = self.get_resource_path_or_url(relative_path)
        if not source: return None
        
        try:
            if isinstance(source, str) and source.startswith(('http://', 'https://')):
                async with aiohttp.ClientSession() as session:
                    async with session.get(source) as response:
                        response.raise_for_status()
                        image_data = await response.read()
                        return Image.open(io.BytesIO(image_data))
            else:
                return Image.open(source)
        except Exception as e:
            logger.error(f"无法打开图片资源 {source}: {e}", exc_info=True)
            return None
    
    def find_song_by_query(self, query: str) -> Optional[Dict]:
        """通过ID或名称统一查找歌曲，优先精确匹配。"""
        if query.isdigit():
            return next((s for s in self.song_data if s['id'] == int(query)), None)
        else:
            query_lower = query.lower()
            found_songs = [s for s in self.song_data if query_lower in s['title'].lower()]
            if not found_songs: return None
            
            exact_match = next((s for s in found_songs if s['title'].lower() == query_lower), None)
            return exact_match or min(found_songs, key=lambda s: len(s['title']))

    async def terminate(self):
        """关闭缓存服务，目前无需特殊操作"""
        pass
