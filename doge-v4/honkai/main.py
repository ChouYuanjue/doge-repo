import json
import requests
import os
import aiohttp
import asyncio
import logging

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
from astrbot.api.message_components import *

@register("honkai", "runnel", "崩铁攻略查询插件", "1.0.0")
class StrategyQuery(Star):
    @filter.command("honkai")
    async def query_strategy(self, event: AstrMessageEvent, *, message: str):
        yield event.plain_result("正在查询攻略，请稍候...")

        try:
            url = 'https://api.yaohud.cn/api/v5/mihoyou/xing'
            params = {'key': 'your-key', 'msg': message}
            response = requests.post(url, params=params)
            
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                logging.error(f"JSON解析失败: {str(e)}")
                yield event.plain_result(f"数据解析失败，原始响应：\n{response.text}")
                return

            logging.info(f"API 返回数据: {result}")            

            image_url = result.get('favicon', '')
            if image_url:
                try:
                        # 添加防盗链绕过头
                        headers = {
                            "Referer": "https://api.yaohud.cn/",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                        }
                        
                        async with session.get(image_url, headers=headers) as img_resp:
                            if img_resp.status == 200:
                                # 保存临时图片文件
                                image_data = await img_resp.read()
                                temp_dir = Path("temp_images")
                                temp_dir.mkdir(exist_ok=True)
                                
                                image_path = temp_dir / f"{uuid.uuid4().hex}.jpg"
                                with open(image_path, "wb") as f:
                                    f.write(image_data)
                            else:
                                logging.warning(f"图片下载失败 HTTP {img_resp.status}")
                except Exception as e:
                                logging.error(f"图片处理异常: {str(e)}")
                            
            if 'peidui_tuijian1' in result:
                formatted_msg = f"""
⭐ 角色攻略：{result['name']} ⭐

🖼️ 角色简介：
{result['icon']}

🎯 获取途径：{result['take']}

💫 光锥推荐：
{' '.join([cone['name'] for cone in result['guangzhui_tuijian']])}

🔮 遗器推荐：
{result['yq_tuijian']['one']['early']} + {result['yq_tuijian']['two']['early']}

📊 遗器词条：
躯干：{result['zhuangbei_tuijian']['qu']}
脚步：{result['zhuangbei_tuijian']['jiao']}
位面球：{result['zhuangbei_tuijian']['wei']}
连接绳：{result['zhuangbei_tuijian']['lian']}

💠 主词条优先级：
{result['fuct']}

🤝 配队推荐：

1️⃣ {result['peidui_tuijian']['name']}
阵容：{result['peidui_tuijian']['idstext']}
说明：{result['peidui_tuijian']['collocation']}

2️⃣ {result['peidui_tuijian1']['name']}
阵容：{result['peidui_tuijian1']['idstext']}
说明：{result['peidui_tuijian1']['collocation']}

💡 遗器说明：
{result['bytion']}
"""
                yield event.chain_result([
                    Image.fromURL(image_url),
                    Plain(formatted_msg),
                ])

            if 'peidui_tuijian1' not in result:
                formatted_msg2 = f"""
⭐ 角色攻略：{result['name']} ⭐

🖼️ 角色简介：
{result['icon']}

🎯 获取途径：{result['take']}

💫 光锥推荐：
{' '.join([cone['name'] for cone in result['guangzhui_tuijian']])}

🔮 遗器推荐：
{result['yq_tuijian']['one']['early']} + {result['yq_tuijian']['two']['early']}

📊 遗器词条：
躯干：{result['zhuangbei_tuijian']['qu']}
脚步：{result['zhuangbei_tuijian']['jiao']}
位面球：{result['zhuangbei_tuijian']['wei']}
连接绳：{result['zhuangbei_tuijian']['lian']}

💠 主词条优先级：
{result['fuct']}

🤝 配队推荐：

1️⃣ {result['peidui_tuijian']['name']}
阵容：{result['peidui_tuijian']['idstext']}
说明：{result['peidui_tuijian']['collocation']}

💡 遗器说明：
{result['bytion']}
"""
                yield event.chain_result([
                    Image.fromURL(image_url),
                    Plain(formatted_msg2),
                ])

        except requests.RequestException as e:
            logging.error(f"请求失败: {str(e)}")
            yield event.plain_result(f"网络请求失败，请稍后重试。错误信息：{str(e)}")