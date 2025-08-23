from astrbot.api.message_components import Image
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import io
import urllib.parse
import requests
import cairosvg
import tempfile
import os
import json
import aiohttp
import asyncio
import logging

@register("utex", "runnel", "将 LaTeX 渲染为 PNG", "1.0.1")
class UtexPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("utex")
    async def utex(self, event: AstrMessageEvent):
        message = event.message_str or ""
        parts = message.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            yield event.plain_result("用法: /utex <LaTeX 代码>")
            return

        latex = parts[1]
        encoded = urllib.parse.quote(latex, safe="")
        svg_url = f"https://i.upmath.me/svg/{encoded}"
        # 用此接口渲染是使用原生TeX, 效果比mathtext更好，且允许tikz,tikz-cd,xy-pic等宏包
        
        try:
            resp = requests.get(svg_url)
            resp.raise_for_status()
            svg_data = resp.content
            png_bytes = cairosvg.svg2png(
                bytestring=svg_data,
                dpi=300,
                scale=3.0
            )
            # 写入临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(png_bytes)
                tmp.flush()
                tmp_path = tmp.name

            # 使用 Image.fromFileSystem 生成图片消息组件
            img_comp = Image.fromFileSystem(path=tmp_path)

            # 使用 chain_result 发送图片
            yield event.chain_result([img_comp])

            # 删除临时文件
            os.remove(tmp_path)

        except Exception as e:
            logging.error(f"/utex 渲染失败: {e}", exc_info=True)
            yield event.plain_result(f"渲染失败: {e}")
