import difflib
import random
import json
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple, Union

import aiohttp
from aiohttp import ClientError
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
import astrbot.api.message_components as Comp

AVAILABLE_SOURCES = {
    "gitlab": {
        "custom": "https://gitlab.com/infinitefusion/sprites/-/raw/master/CustomBattlers/{n}/",
        "autogen": "https://gitlab.com/infinitefusion/sprites/-/raw/master/Battlers/",
    },
    "fusioncalc": {
        "custom": "https://fusioncalc.com/wp-content/themes/twentytwentyone/pokemon/custom-fusion-sprites-main/CustomBattlers/",
        "autogen": "https://fusioncalc.com/wp-content/themes/twentytwentyone/pokemon/autogen-fusion-sprites-master/Battlers/",
    },
}


@register("doge_pokemon", "sugayoiya, runnel", "宝可梦融合插件", "1.0.0")
class PokemonFusionPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.pokemon_data = {}
        self.pokemon_id_map = {}  # ID -> Name 的映射
        self.config = {"source": "gitlab"}
        self.data_dir = StarTools.get_data_dir()
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """初始化插件，加载宝可梦数据"""
        try:
            # 创建 aiohttp session
            self.session = aiohttp.ClientSession()
            # 直接从插件目录读取固定文件
            plugin_file = Path(__file__).resolve().parent / "pokemons.json"
            if not plugin_file.exists():
                logger.error("找不到内置宝可梦数据文件")
                raise FileNotFoundError(str(plugin_file))
            # 加载数据
            with open(plugin_file, "r", encoding="utf8") as f:
                self.pokemon_data = json.load(f)
            # 创建 ID 到名字的反向映射
            self.pokemon_id_map = {str(v): k for k, v in self.pokemon_data.items()}
            logger.info("宝可梦数据和ID映射加载成功")
        except FileNotFoundError:
            logger.error("找不到宝可梦数据文件")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"宝可梦数据文件格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"加载宝可梦数据时发生未知错误: {e}")
            raise

    def _get_pokemon_name(self, pid: str) -> str:
        """根据ID获取宝可梦名字"""
        return self.pokemon_id_map.get(pid, f"#{pid}")

    def get_similar_names(self, name: str, limit: int = 3) -> List[str]:
        """获取相似的宝可梦名字"""
        if not self.pokemon_data:
            return []
        similarity_scores = [
            (n, difflib.SequenceMatcher(None, name, n).quick_ratio())
            for n in self.pokemon_data
        ]
        similarity_scores.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in similarity_scores[:limit]]

    async def _check_image_exists(self, url: str) -> bool:
        """检查图片URL是否可访问"""
        if not self.session:
            return False
        try:
            async with self.session.get(url) as response:
                return response.status == 200
        except ClientError as e:
            logger.error(f"检查图片URL失败（网络错误）: {e}")
            return False
        except Exception as e:
            logger.error(f"检查图片URL失败（未知错误）: {e}")
            return False

    async def get_fusion_image(self, fusion_id: str) -> Optional[str]:
        """获取融合图片URL"""
        head_id = fusion_id.split(".")[0]
        source = AVAILABLE_SOURCES[self.config["source"]]

        # 同时检查两个URL
        custom_url = f"{source['custom'].format(n=head_id)}{fusion_id}"
        autogen_url = f"{source['autogen']}{head_id}/{fusion_id}"
        urls = [custom_url, autogen_url]

        # 并行检查所有URL
        results = await asyncio.gather(
            *[self._check_image_exists(url) for url in urls], return_exceptions=True
        )

        # 返回第一个可用的URL
        for url, result in zip(urls, results):
            if isinstance(result, bool) and result:
                return url

        # 如果都失败了，返回 None
        return None

    def _get_random_pokemon_id(self) -> str:
        """随机获取一个宝可梦ID"""
        return str(random.choice(list(self.pokemon_data.values())))

    def _parse_fusion_input(
        self, message: str
    ) -> Tuple[Union[str, None], Union[str, None], Optional[str]]:
        """解析融合输入，返回 (id1, id2, error_message)"""
        # 处理随机融合的情况
        if not message or message == "随机":
            return self._get_random_pokemon_id(), self._get_random_pokemon_id(), None

        # 处理指定宝可梦融合的情况
        pokemon_list = message.split("+")

        # 如果只输入了一个宝可梦
        if len(pokemon_list) == 1:
            pokemon = pokemon_list[0].strip()
            if pokemon not in self.pokemon_data:
                similar_names = self.get_similar_names(pokemon)
                return (
                    None,
                    None,
                    f"未找到宝可梦 {pokemon}！\n你要找的是不是：{'、'.join(similar_names)}？",
                )

            return str(self.pokemon_data[pokemon]), self._get_random_pokemon_id(), None

        # 处理两个宝可梦的情况
        elif len(pokemon_list) == 2:
            pokemon_list = [p.strip() for p in pokemon_list]
            not_found_pokemons = []

            for pokemon in pokemon_list:
                if pokemon not in self.pokemon_data:
                    similar_names = self.get_similar_names(pokemon)
                    not_found_pokemons.append(
                        f"未找到 {pokemon}！尝试以下结果：{'、'.join(similar_names)}"
                    )

            if not_found_pokemons:
                return None, None, "\n".join(not_found_pokemons)

            return (
                str(self.pokemon_data[pokemon_list[0]]),
                str(self.pokemon_data[pokemon_list[1]]),
                None,
            )

        # 输入格式错误
        return (
            None,
            None,
            "请输入一个或两个宝可梦的名字\n例如：/融合 皮卡丘+妙蛙种子\n或者：/融合 皮卡丘（将随机选择另一个宝可梦）",
        )

    @filter.command("pokemon", alias=["融合"])
    async def fusion(self, event: AstrMessageEvent):
        """宝可梦融合！

        使用方法：
        - `/融合` - 随机融合两个宝可梦
        - `/融合 皮卡丘` - 将皮卡丘与随机宝可梦融合
        - `/融合 皮卡丘+妙蛙种子` - 融合指定的两个宝可梦
        """
        # 获取命令后的参数部分
        message = event.message_str.strip()
        parts = message.split()
        command = parts[0] if parts else ""
        message = message[len(command) :].strip() if command else ""

        # 解析输入
        id1, id2, error_message = self._parse_fusion_input(message)
        if error_message:
            chain = [Comp.At(qq=event.get_sender_id()), Comp.Plain(f" {error_message}")]
            yield event.chain_result(chain)
            return

        # 生成融合ID，保持确定的顺序
        fusion_ids_list = [f"{id1}.{id2}.png"]
        # 只有当两个ID不同时才添加反向融合
        if id1 != id2:
            fusion_ids_list.append(f"{id2}.{id1}.png")

        try:

            # 并行检查图片是否可访问
            tasks = [self.get_fusion_image(fid) for fid in fusion_ids_list]
            image_urls_raw = await asyncio.gather(*tasks)
            image_urls = [url for url in image_urls_raw if url is not None]

            if not image_urls:
                # 如果没有找到有效图片，显示默认的问号图片
                chain = [
                    Comp.At(qq=event.get_sender_id()),
                    Comp.Plain(
                        f" 正在为你融合 {self._get_pokemon_name(id1)} 和 {self._get_pokemon_name(id2)}：\n"
                    ),
                    Comp.Image.fromURL(
                        "https://infinitefusion.gitlab.io/pokemon/question.png"
                    ),
                    Comp.Plain(" 抱歉，获取融合图片失败，请稍后再试。"),
                ]
                yield event.chain_result(chain)
                return

            # 获取宝可梦名字并构建消息链
            name1 = self._get_pokemon_name(id1)
            name2 = self._get_pokemon_name(id2)
            chain = [
                Comp.At(qq=event.get_sender_id()),
                Comp.Plain(f" 正在为你融合 {name1} 和 {name2}：\n"),
            ]

            # 添加所有融合图片到消息链
            for image_url in image_urls:
                chain.append(Comp.Image.fromURL(image_url))
                chain.append(Comp.Plain("\n"))

            yield event.chain_result(chain)

        except Exception as e:
            logger.error(f"融合图片处理失败: {e}")
            chain = [
                Comp.At(qq=event.get_sender_id()),
                Comp.Plain(" 抱歉，处理融合图片时出错，请稍后再试。"),
            ]
            yield event.chain_result(chain)

    @filter.command("pokemon sc", alias=["融合切换源"])
    async def switch_source(self, event: AstrMessageEvent):
        """切换图片源

        使用方法：
        - `/宝可梦切换源` - 在 gitlab 和 fusioncalc 之间切换图片源
        """
        sources = list(AVAILABLE_SOURCES.keys())
        current_index = sources.index(self.config["source"])
        next_index = (current_index + 1) % len(sources)

        old_source = self.config["source"]
        self.config["source"] = sources[next_index]

        chain = [
            Comp.At(qq=event.get_sender_id()),
            Comp.Plain(f" 已将图片源从 {old_source} 切换为 {self.config['source']}"),
        ]
        yield event.chain_result(chain)

    async def terminate(self):
        """插件卸载时的清理工作"""
        if self.session:
            await self.session.close()
        self.pokemon_data = {}
        self.pokemon_id_map = {}
