import re
import io
import ssl
from typing import List
import asyncio
import httpx
import numpy as np
from PIL import Image as PILImage, ImageEnhance
from astrbot.api.star import register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Star, Context
from astrbot.api.message_components import Image as AstrImage, Plain as AstrPlain
import tempfile
import os
import time

ssl_context = ssl.create_default_context()
ssl_context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_TLSv1_3
ssl_context.set_ciphers("HIGH:!aNULL:!MD5")
ntqq_img_client = httpx.AsyncClient(verify=ssl_context)

np.seterr(divide="ignore", invalid="ignore")

@register("mirage", "runnel", "用于生成幻影坦克图片的插件", "1.2.0")
class MirageTankPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.default_client = httpx.AsyncClient()
        self.user_states = {}
        self.processed_messages = set()

    async def on_shutdown(self):
        await self.default_client.aclose()
        await ntqq_img_client.aclose()

    def _get_img_urls(self, message) -> List[str]:
        img_urls = []
        try:
            for component_str in getattr(message, 'message', []):
                if "type='Image'" in str(component_str):
                    url_match = re.search(r"url='([^']+)'", str(component_str))
                    if url_match:
                        img_urls.append(url_match.group(1))
            raw_message = getattr(message, 'raw_message', '')
            if isinstance(raw_message, dict) and "message" in raw_message:
                for msg_part in raw_message.get("message", []):
                    if msg_part.get("type") == "image":
                        data = msg_part.get("data", {})
                        url = data.get("url", "")
                        if url and url not in img_urls:
                            img_urls.append(url)
        except Exception as e:
            self.context.logger.error(f"提取图片URL失败: {str(e)}")
        return img_urls

    async def _download_img(self, url: str):
        if "multimedia.nt.qq.com.cn" in url:
            client = ntqq_img_client
        else:
            client = self.default_client
        try:
            r = await client.get(url, timeout=15)
            if r.status_code == 200:
                return PILImage.open(io.BytesIO(r.content))
        except Exception as e:
            self.context.logger.warning(f"下载图片 {url} 失败: {e}")
        return None

    async def get_imgs(self, img_urls: List[str]) -> List[PILImage.Image]:
        if not img_urls:
            return []
        imgs = await asyncio.gather(*[self._download_img(url) for url in img_urls])
        return [img for img in imgs if img is not None]

    def resize_image(self, im1: PILImage.Image, im2: PILImage.Image, mode: str) -> tuple:
        im1_w, im1_h = im1.size
        if im1_w * im1_h > 1500 * 2000:
            if im1_w > 1500:
                im1 = im1.resize((1500, int(im1_h * (1500 / im1_w))))
            else:
                im1 = im1.resize((int(im1_w * (1500 / im1_h)), 1500))

        _wimg = im1.convert(mode)
        _bimg = im2.convert(mode).resize(_wimg.size, PILImage.Resampling.NEAREST)

        wwidth, wheight = _wimg.size
        bwidth, bheight = _bimg.size

        width = max(wwidth, bwidth)
        height = max(wheight, bheight)

        wimg = PILImage.new(mode, (width, height), 255 if mode == "L" else (255, 255, 255))
        bimg = PILImage.new(mode, (width, height), 0 if mode == "L" else (0, 0, 0))

        wimg.paste(_wimg, ((width - wwidth) // 2, (height - wheight) // 2))
        bimg.paste(_bimg, ((width - bwidth) // 2, (height - bheight) // 2))

        return wimg, bimg

    def gray_car(self, wimg: PILImage.Image, bimg: PILImage.Image):
        wimg, bimg = self.resize_image(wimg, bimg, "L")

        wpix = np.array(wimg).astype("float64")
        bpix = np.array(bimg).astype("float64")

        wpix = wpix * 0.5 + 128
        bpix *= 0.5

        a = 1.0 - wpix / 255.0 + bpix / 255.0
        r = np.where(abs(a) > 1e-6, bpix / a, 255.0)

        pixels = np.dstack((r, r, r, a * 255.0))

        pixels[pixels > 255] = 255

        output = io.BytesIO()
        PILImage.fromarray(pixels.astype("uint8"), "RGBA").save(output, format="png")
        return output.getvalue()

    def color_car(self, wimg: PILImage.Image, bimg: PILImage.Image, wlight: float = 1.0, blight: float = 0.18, wcolor: float = 0.5, bcolor: float = 0.7):
        wimg = ImageEnhance.Brightness(wimg).enhance(wlight)
        bimg = ImageEnhance.Brightness(bimg).enhance(blight)

        wimg, bimg = self.resize_image(wimg, bimg, "RGB")

        wpix = np.array(wimg).astype("float64")
        bpix = np.array(bimg).astype("float64")

        wpix /= 255.0
        bpix /= 255.0

        wgray = wpix[:, :, 0] * 0.334 + wpix[:, :, 1] * 0.333 + wpix[:, :, 2] * 0.333
        wpix *= wcolor
        wpix[:, :, 0] += wgray * (1.0 - wcolor)
        wpix[:, :, 1] += wgray * (1.0 - wcolor)
        wpix[:, :, 2] += wgray * (1.0 - wcolor)

        bgray = bpix[:, :, 0] * 0.334 + bpix[:, :, 1] * 0.333 + bpix[:, :, 2] * 0.333
        bpix *= bcolor
        bpix[:, :, 0] += bgray * (1.0 - bcolor)
        bpix[:, :, 1] += bgray * (1.0 - bcolor)
        bpix[:, :, 2] += bgray * (1.0 - bcolor)

        d = 1.0 - wpix + bpix

        d[:, :, 0] = d[:, :, 1] = d[:, :, 2] = (
            d[:, :, 0] * 0.222 + d[:, :, 1] * 0.707 + d[:, :, 2] * 0.071
        )

        p = np.where(abs(d) > 1e-6, bpix / d * 255.0, 255.0)
        a = d[:, :, 0] * 255.0

        colors = np.zeros((p.shape[0], p.shape[1], 4))
        colors[:, :, :3] = p
        colors[:, :, -1] = a

        colors[colors > 255] = 255

        output = io.BytesIO()
        PILImage.fromarray(colors.astype("uint8")).convert("RGBA").save(output, format="png")
        return output.getvalue()

    @filter.command("mirage")
    async def generate_mirage_tank(self, event: AstrMessageEvent, mode: str = "gray"):
        user_id = event.get_sender_id()
        message = event.message_obj
        message_id = getattr(message, 'message_id', None)
        
        if mode and mode.lower() not in ("gray", "color"):
            yield event.plain_result("无效的模式，请使用 'gray'（黑白）或 'color'（彩色）。默认使用 'gray'。")
            mode = "gray"
        else:
            mode = mode.lower()
        
        img_urls = self._get_img_urls(message)
        if len(img_urls) >= 2:
            yield event.plain_result(f"收到两张图片，开始合成幻影坦克（模式：{mode}）...")
            imgs = await self.get_imgs(img_urls[:2])
            if len(imgs) < 2:
                yield event.plain_result("图片下载失败，请稍后重试。")
                return
            wimg, bimg = imgs
            if mode == "color":
                result = self.color_car(wimg, bimg)
            else:
                result = self.gray_car(wimg, bimg)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_file.write(result)
                temp_file_path = temp_file.name
            yield event.chain_result([AstrImage.fromFileSystem(temp_file_path)])
            os.unlink(temp_file_path)
        elif len(img_urls) == 1:
            self.user_states[user_id] = {
                "step": "dark",
                "light_url": img_urls[0],
                "mode": mode,
                "timestamp": time.time(),
                "last_message_id": message_id
            }
            yield event.plain_result("明图收到，请上传暗图（显示在黑色背景下的图片）。")
        else:
            self.user_states[user_id] = {
                "step": "light",
                "light_url": None,
                "dark_url": None,
                "mode": mode,
                "timestamp": time.time(),
                "last_message_id": message_id
            }
            yield event.plain_result("请上传明图（显示在白色背景下的图片）。")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        if user_id not in self.user_states:
            return

        message = event.message_obj
        message_id = getattr(message, 'message_id', None)
        state = self.user_states[user_id]
        
        if message_id and state.get("last_message_id") == message_id:
            return
        
        if time.time() - state["timestamp"] > self.timeout:
            yield event.plain_result("上传图片超时，操作取消。")
            del self.user_states[user_id]
            event.stop_event()
            return

        img_urls = self._get_img_urls(message)
        if not img_urls:
            return

        if state["step"] == "light":
            state["light_url"] = img_urls[0]
            state["step"] = "dark"
            state["timestamp"] = time.time()
            state["last_message_id"] = message_id
            yield event.plain_result("明图收到，请上传暗图（显示在黑色背景下的图片）。")
        elif state["step"] == "dark":
            state["dark_url"] = img_urls[0]
            mode = state.get("mode", "gray")
            yield event.plain_result(f"暗图收到，开始合成幻影坦克（模式：{mode}）...")
            imgs = await self.get_imgs([state["light_url"], state["dark_url"]])
            if len(imgs) < 2:
                yield event.plain_result("图片下载失败，请稍后重试。")
                del self.user_states[user_id]
                return
            wimg, bimg = imgs
            if mode == "color":
                result = self.color_car(wimg, bimg)
            else:
                result = self.gray_car(wimg, bimg)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_file.write(result)
                temp_file_path = temp_file.name
            yield event.chain_result([AstrImage.fromFileSystem(temp_file_path)])
            os.unlink(temp_file_path)
            del self.user_states[user_id]
            event.stop_event()

    timeout = 60
