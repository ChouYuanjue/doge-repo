import io
import tempfile
import subprocess
import os
import urllib.parse

import cairosvg

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image

@register("rrpl", "runnel", "将 RRPL 渲染为 PNG 图像", "1.0.0")
class RrplPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("rrpl")
    async def rrpl(self, event: AstrMessageEvent):
        message = event.message_str or ""
        parts = message.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            yield event.plain_result("用法: /rrpl <RRPL 代码>")
            return

        rrpl_code = parts[1].strip()
        logger.info(f"收到 RRPL 代码: {rrpl_code!r}")

        # 生成临时文件路径
        with tempfile.NamedTemporaryFile(delete=False, suffix=".svg") as svg_tmp:
            svg_path = svg_tmp.name

        try:
            # 调用 Node.js 渲染 SVG
            rrpl_dir = "/root/AstrBot/data/plugins/rrpl/rrpl"
            cmd = ["node", "render.js", rrpl_code]
            result = subprocess.run(cmd,cwd=rrpl_dir,capture_output=True,text=True,timeout=10)

            if result.returncode != 0:
                logger.error(f"RRPL 渲染失败: {result.stderr}")
                yield event.plain_result(f"渲染失败: {result.stderr}")
                return

            svg_data = result.stdout.encode("utf-8")
            with open(svg_path, "wb") as f:
                f.write(svg_data)

            svg_text = svg_data.decode("utf-8")
            svg_bytes = svg_text.encode("utf-8")

            # 渲染为高分辨率 PNG
            png_bytes = cairosvg.svg2png(bytestring=svg_bytes, dpi=300, scale=2.0)

            # 临时 PNG 文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as png_tmp:
                png_path = png_tmp.name
                png_tmp.write(png_bytes)

            # 发送图片
            img_comp = Image.fromFileSystem(path=png_path)
            yield event.chain_result([img_comp])

        except Exception as e:
            logger.error(f"/rrpl 渲染异常: {e}", exc_info=True)
            yield event.plain_result(f"渲染异常: {e}")

        finally:
            for path in [svg_path, locals().get("png_path", None)]:
                if path and os.path.exists(path):
                    os.remove(path)
