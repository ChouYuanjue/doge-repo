import asyncio
import io
import re
import tempfile
import urllib.parse
import asyncio
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
from PIL import Image

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

@register("pack", "runnel", "Circle Packing 计算与可视化", "1.0.0")
class CirclePackingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 存储API URL模板
        self.api_templates = {
            'csq': 'http://hydra.nat.uni-magdeburg.de/cgi-bin/csq1.pl?size={size}&diameter={diameter}&name=&addr=',
            'cci': 'http://hydra.nat.uni-magdeburg.de/cgi-bin/cci1.pl?size={size}&diameter={diameter}&name=&addr='
        }

    async def initialize(self):
        logger.info("Circle Packing 插件已加载")

    @filter.command_group("pack")
    def pack_group(self):
        """pack 指令组: csq / cci"""
        pass

    @pack_group.command("csq")
    async def pack_csq(self, event: AstrMessageEvent):
        """
        /pack csq <size> <diameter>
        计算在正方形内放置圆形的最优方案
        size: 正方形边长
        diameter: 小圆直径
        """
        async for ret in self._handle_pack_request(event, 'csq'):
            yield ret

    @pack_group.command("cci")
    async def pack_cci(self, event: AstrMessageEvent):
        """
        /pack cci <size> <diameter>
        计算在大圆内放置小圆的最优方案
        size: 大圆直径
        diameter: 小圆直径
        """
        async for ret in self._handle_pack_request(event, 'cci'):
            yield ret

    async def _handle_pack_request(self, event: AstrMessageEvent, pack_type: str):
        command_text = event.message_str.strip()
        logger.info(f"接收到pack {pack_type}命令: {command_text}")
        
        # 提取参数
        match = re.match(rf"^pack\s+{pack_type}\s+(\d+)\s+(\d+)$", command_text)
        if not match:
            yield event.plain_result(f"用法: /pack {pack_type} <size> <diameter>\n例如: /pack {pack_type} 100 12")
            return
        
        size = int(match.group(1))
        diameter = int(match.group(2))
        
        # 验证参数范围
        if size <= 0 or diameter <= 0:
            yield event.plain_result("参数必须为正整数！")
            return
        
        # 发送请求
        try:
            # 显示处理中
            yield event.plain_result(f"正在计算{pack_type.upper()}类型的Circle Packing结果，请稍候...")
            
            # 构建URL并发送请求
            url = self.api_templates[pack_type].format(size=size, diameter=diameter)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=60) as response:
                    response.raise_for_status()
                    html_content = await response.text()
            
            # 解析HTML结果
            result = await self._parse_packing_result(html_content, pack_type)
            
            if result['success']:
                # 下载图片
                image_data = await self._download_image(result['image'])
                
                # 构造结果消息
                if pack_type == 'csq':
                    shape_type = "正方形"
                    result_type = "CSQ (正方形内圆排列)"
                else:
                    shape_type = "圆形"
                    result_type = "CCI (圆形容器内圆排列)"
                
                text = (f"Circle Packing 计算结果 ({result_type})\n" \
                       f"{shape_type}尺寸: {size}\n" \
                       f"小圆直径: {diameter}\n" \
                       f"可放置圆数量: {result['output']['count']}\n" \
                       f"空间利用率: {100 - float(result['output']['waste']):.2f}%\n" \
                       f"空间浪费: {result['output']['waste']}%")
                
                # 发送图片和文本
                yield event.chain_result([
                    Comp.Plain(text),
                    Comp.Image.fromBytes(image_data)
                ])
            else:
                # 发送错误信息
                error_msg = result.get('error', '计算失败，请尝试调整参数')
                if pack_type == 'csq':
                    shape_type = "正方形边长"
                else:
                    shape_type = "大圆直径"
                
                error_reply = (f"计算失败\n" \
                              f"错误信息: {error_msg}\n" \
                              f"建议: 减小{shape_type}或增大小圆直径后重试")
                
                yield event.plain_result(error_reply)
        
        except aiohttp.ClientError as e:
            logger.error(f"网络请求错误: {e}")
            yield event.plain_result("网络请求失败，请检查网络连接或稍后再试")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield event.plain_result("请求超时，请尝试使用较小的参数值")
        except Exception as e:
            logger.error(f"处理失败: {e}")
            yield event.plain_result(f"处理失败: {str(e)}")

    async def _parse_packing_result(self, html_content: str, pack_type: str):
        """解析Circle Packing计算结果的HTML，适应CSQ和CCI类型的成功与失败情况"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 检查是否包含错误信息（针对CSQ和CCI的不同失败情况）
        error_texts = [
            'too many circles', 
            '似乎圆数量过多',
            'Please decrease the diameter of the large disk or increase the diameter of the small circles'
        ]
        
        for error_text in error_texts:
            if error_text.lower() in html_content.lower():
                # 查找错误信息文本
                error_element = soup.find(text=lambda t: t and error_text.lower() in t.lower())
                if error_element:
                    error_msg = str(error_element).strip()
                    # 清理错误信息，使其更友好
                    if 'more than' in error_msg:
                        # 提取具体限制数量
                        match = re.search(r'more than (\d+)', error_msg)
                        if match:
                            limit = match.group(1)
                            if pack_type == 'csq':
                                error_msg = f"圆数量过多（超过{limit}个），无法完成计算"
                            else:
                                error_msg = f"圆数量过多（超过{limit}个），无法完成计算"
                    return {
                        'success': False,
                        'error': error_msg
                    }
        
        # 检查是否成功（包含"Number of circles that will fit"）
        count_element = soup.find('b', string=lambda t: t and 'Number of circles that will fit' in t)
        if not count_element:
            return {
                'success': False,
                'error': '未能找到计算结果，请尝试调整参数'
            }
        
        # 提取输出参数
        count = count_element.find_next_sibling(text=True).strip()
        waste_element = soup.find('b', string=lambda t: t and 'Waste' in t)
        waste = waste_element.find_next_sibling(text=True).strip().replace('%', '') if waste_element else "未知"
        
        # 提取图片URL
        img_element = soup.find('img', {'src': True})
        img_url = img_element['src'] if img_element else None
        
        return {
            'success': True,
            'output': {
                'count': count,
                'waste': waste
            },
            'image': img_url
        }
    
    async def _download_image(self, img_url: str):
        """下载图片并返回字节数据"""
        if not img_url:
            raise ValueError("图片URL无效")
            
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url, timeout=30) as response:
                response.raise_for_status()
                return await response.read()

if __name__ == "__main__":
    print("Circle Packing 插件主模块")