import asyncio
import aiohttp
import json
from typing import Dict, Optional, List, Tuple

from astrbot.api import logger
from astrbot.api import AstrBotConfig
from urllib.parse import urlparse

class StatsService:
    def __init__(self, config: AstrBotConfig):
        self.api_key = config.get("stats_server_api_key")
        self.stats_server_url = self._get_stats_server_root(config)
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_stats_server_root(self, config: AstrBotConfig) -> Optional[str]:
        """根据配置获取统计服务器的根URL。"""
        url_base = config.get("remote_resource_url_base", "").strip('/')
        if not url_base:
            return None
        try:
            parsed_url = urlparse(url_base)
            return f"{parsed_url.scheme}://{parsed_url.hostname}:5000"
        except Exception as e:
            logger.error(f"无法从 '{url_base}' 解析统计服务器地址: {e}")
            return None

    async def _get_session(self) -> Optional[aiohttp.ClientSession]:
        """延迟初始化并获取 aiohttp session"""
        if self.api_key is None or self.stats_server_url is None:
            return None
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _get_api_headers(self) -> Dict[str, str]:
        """获取带有认证信息的API请求头。"""
        return {"X-API-KEY": self.api_key} if self.api_key else {}

    async def api_ping(self, event_type: str):
        """向服务器发送一个简单的事件埋点。"""
        session = await self._get_session()
        if not session: return
        
        ping_url = f"{self.stats_server_url}/api/ping/{event_type}"
        try:
            async with session.get(ping_url, headers=self._get_api_headers(), timeout=2):
                pass
        except Exception as e:
            logger.warning(f"Stats ping to {ping_url} failed: {e}")

    async def api_log_game(self, game_log_data: dict):
        """向服务器记录一条详细的游戏日志。"""
        session = await self._get_session()
        if not session: return

        post_url = f"{self.stats_server_url}/api/log_game"
        try:
            async with session.post(post_url, json=game_log_data, headers=self._get_api_headers(), timeout=3) as resp:
                if resp.status != 200:
                    logger.warning(f"记录游戏日志失败. Status: {resp.status}, Response: {await resp.text()}")
        except Exception as e:
            logger.warning(f"发送游戏日志至 {post_url} 失败: {e}")

    async def api_update_score(self, user_id: str, user_name: str, score_delta: int):
        """向服务器同步玩家的分数变化。"""
        if score_delta == 0: return

        session = await self._get_session()
        if not session: return

        payload = {
            "user_id": str(user_id),
            "user_name": user_name,
            "score_change": score_delta
        }
        post_url = f"{self.stats_server_url}/api/update_score"
        try:
            async with session.post(post_url, json=payload, headers=self._get_api_headers(), timeout=3) as resp:
                if resp.status != 200:
                    logger.warning(f"同步分数至服务器失败. Status: {resp.status}, Response: {await resp.text()}")
        except Exception as e:
            logger.warning(f"发送分数更新至 {post_url} 失败: {e}")

    async def get_global_leaderboard(self) -> Optional[List[Dict]]:
        """通过API获取服务器排行榜数据。"""
        session = await self._get_session()
        if not session: return None

        leaderboard_url = f"{self.stats_server_url}/api/leaderboard"
        try:
            async with session.get(leaderboard_url, headers=self._get_api_headers(), timeout=10) as response:
                if response.status == 401:
                    logger.warning("API密钥无效，无法获取服务器排行榜。")
                    return None
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.error(f"获取服务器排行榜失败: {e}", exc_info=True)
            return None

    async def api_get_user_global_stats(self, user_id: str) -> Optional[Dict]:
        """通过API获取用户的服务器统计数据。"""
        session = await self._get_session()
        if not session:
            logger.warning("aiohttp session 不可用，无法获取服务器用户数据。")
            return None

        stats_url = f"{self.stats_server_url}/api/user_stats/{user_id}"
        try:
            async with session.get(stats_url, headers=self._get_api_headers(), timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 404:
                    return None
                else:
                    logger.warning(f"获取用户 {user_id} 服务器数据失败. Status: {response.status}, Response: {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"请求 {stats_url} 失败: {e}", exc_info=True)
            return None

    async def get_mode_stats(self) -> Optional[List[Tuple]]:
        """获取在线题型统计。"""
        session = await self._get_session()
        if not session: return None

        stats_url = f"{self.stats_server_url}/api/mode_stats"
        try:
            async with session.get(stats_url, headers=self._get_api_headers(), timeout=5) as response:
                if response.status == 401:
                    logger.warning("API密钥无效，无法获取题型统计。"); return None
                response.raise_for_status()
                rows_json = await response.json()
                return [(r['mode'], r['total_attempts'], r['correct_attempts']) for r in rows_json]
        except Exception as e:
            logger.error(f"获取在线题型统计失败: {e}", exc_info=True)
            return None

    async def migrate_scores(self, payload: List[Dict]):
        """异步将本地分数同步到服务器。"""
        session = await self._get_session()
        if not session:
            logger.error("网络组件初始化失败。")
            return
        
        migrate_url = f"{self.stats_server_url}/api/migrate_leaderboard"
        try:
            async with session.post(migrate_url, json=payload, headers=self._get_api_headers(), timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"分数同步成功：处理了 {result.get('processed_count', 0)} 条记录。")
                elif response.status == 401:
                    logger.warning(f"分数同步失败：API密钥无效。")
                else:
                    logger.error(f"分数同步失败，服务器返回错误：{response.status} {await response.text()}")
        except Exception as e:
            logger.error(f"同步服务器分数失败: {e}", exc_info=True)
 
    async def api_get_user_mode_stats(self, user_id: str) -> Optional[List[Dict]]:
        """从服务器获取单个用户的模式游玩统计数据。"""
        if not self.api_key or not self.stats_server_url:
            return None
        
        url = f"{self.stats_server_url}/api/user_mode_stats/{user_id}"
        headers = {'X-API-KEY': self.api_key}
        
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"获取用户模式统计失败 (用户ID: {user_id}): 服务器返回状态 {response.status}")
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"访问服务器时出错 (获取用户模式统计): {e}")
            raise  # 重新抛出异常，让调用方处理
        except Exception as e:
            logger.error(f"处理用户模式统计响应时发生未知错误: {e}")
            return None            
    async def api_get_user_mode_ranks(self, user_id: str, min_attempts: int) -> Optional[Dict]:
        """从服务器获取单个用户在各核心模式中的全服排名。"""
        if not self.api_key or not self.stats_server_url:
            return None
        
        url = f"{self.stats_server_url}/api/user_mode_ranks/{user_id}"
        params = {"min_attempts": min_attempts}
        headers = {'X-API-KEY': self.api_key}
        
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, params=params, timeout=15) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"获取用户模式排名失败 (用户ID: {user_id}): 服务器返回状态 {response.status}")
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"访问服务器时出错 (获取用户模式排名): {e}")
            return None
        except Exception as e:
            logger.error(f"处理用户模式排名响应时发生未知错误: {e}")
            return None

    async def terminate(self):
        """关闭 aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
