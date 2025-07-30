import json
import requests
import os
import aiohttp
import asyncio
import logging

from urllib.parse import quote
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
from astrbot.api.message_components import *

@register("genshin", "runnel", "原神攻略查询插件", "1.0.0")
class StrategyQuery(Star):
    @filter.command("genshin")
    async def query_strategy(self, event: AstrMessageEvent, *, message: str):
        yield event.plain_result("正在查询攻略，请稍候...")

        try:
            message_encoded = quote(message)
            url = 'https://api.yaohud.cn/api/v5/mihoyou/yuan'
            params = {'key': 'your-key', 'msg': message}
            response = requests.post(url, params=params)
            
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                logging.error(f"JSON解析失败: {str(e)}")
                yield event.plain_result(f"数据解析失败，原始响应：\n{response.text}")
                return

            logging.info(f"API 返回数据: {result}")            

            image_url = result['pictureurl']
            if result['code'] == '200':
                # 格式化输出信息

                if result['url'] == '未找到有关信息':
                    yield event.plain_result("抱歉，未找到相关信息喵。")
                    return

                basic = ''.join([f'• {info}\n' for info in result['text']])
            if result['msg'] == '角色':
                formatted_msg = f"""
⭐ 角色攻略：{result['name']} ⭐

🖼️ 角色简介：
{result['icon']}

📍 基本信息：
{basic}

🎯 获取途径：{result['bbs']}

🤝 推荐配队：
队伍类型：{result['ranks']}
推荐阵容：{result['teamname']}
配队说明：{result['yaohuby']}

🗡️ 武器推荐：

前期武器：{result['recommendation']['one']['name']}
{result['recommendation']['one']['introduce']}

毕业武器：{result['recommendation']['two']['name']}
{result['recommendation']['two']['introduce']}

📊 圣遗物搭配：

前期搭配：{result['recommendation']['one']['early']}
主词条优先级：{result['recommendation']['one']['order']}
圣遗物部位：{result['recommendation']['one']['sequence']}
说明：{result['recommendation']['one']['yaoby']}

毕业搭配：{result['recommendation']['two']['early']}
主词条优先级：{result['recommendation']['two']['order']}
圣遗物部位：{result['recommendation']['two']['sequence']}
说明：{result['recommendation']['two']['yaoby']}
"""
                yield event.chain_result([
                    Image.fromURL(image_url),
                    Plain(formatted_msg),
                ])
            if result['msg'] == '武器':
                formatted_msg2 = f"""
⭐ 武器标签：{result['name']} ⭐

📍 基本信息：
{basic}
"""             
                yield event.chain_result([
                    Image.fromURL(image_url),
                    Plain(formatted_msg2),
                ])


        except requests.RequestException as e:
            logging.error(f"请求失败: {str(e)}")
            yield event.plain_result(f"网络请求失败，请稍后重试。错误信息：{str(e)}")