from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import (
    Image as MsgImage,
    Reply,
    Plain,
)
import aiohttp
import base64
import asyncio
from io import BytesIO
from PIL import Image as PILImage
from astrbot.core.utils.session_waiter import session_waiter, SessionController

@register("doge_trace", "runnel", "动漫/Gal图片识别", "1.0.0")
class AnimeTracePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_url = "https://api.animetrace.com/v1/search"
        self.debug_mode = True  # 调试模式

    async def initialize(self):
        logger.info("动漫/Gal识别插件已加载")

    @filter.command("trace anime", "动漫图片识别")
    async def anime_search(self, event: AstrMessageEvent):
        await self.start_image_listener(event, "pre_stable")

    @filter.command("trace gal", "gal图片识别")
    async def gal_search(self, event: AstrMessageEvent):
        await self.start_image_listener(event, "full_game_model_kira")

    async def start_image_listener(self, event: AstrMessageEvent, model: str):
        initial_image_url = await self.extract_image_from_event(event)
        if initial_image_url:
            await event.send(event.plain_result("🔍 检测到图片，开始识别..."))
            await self.process_and_send_result(event, initial_image_url, model)
            return

        await event.send(event.plain_result("⚠️ 请发送图片或引用包含图片的消息"))

        @session_waiter(timeout=60, record_history_chains=False)
        async def image_waiter(controller: SessionController, new_event: AstrMessageEvent):
            image_url = await self.extract_image_from_event(new_event)
            if not image_url:
                await new_event.send(event.plain_result("⚠️ 未检测到图片，请重新发送"))
                return

            await new_event.send(event.plain_result("🔍 开始识别，请稍候..."))
            await self.process_and_send_result(new_event, image_url, model)
            controller.stop()

        try:
            await image_waiter(event)
        except TimeoutError:
            await event.send(event.plain_result("⏱️ 等待超时，请重新发送指令"))
        except Exception as e:
            logger.error(f"会话错误: {str(e)}")
            await event.send(event.plain_result(f"❌ 处理失败: {str(e)}"))

    async def process_and_send_result(self, event: AstrMessageEvent, image_url: str, model: str):
        try:
            img_data = await self.process_image(image_url)
            results = await self.search_anime(img_data, model)
            response = self.format_response(results, model)
            await event.send(event.plain_result(response))
        except Exception as e:
            logger.error(f"识别失败: {str(e)}")
            await event.send(event.plain_result(f"❌ 识别失败: {str(e)}"))

    async def extract_image_from_event(self, event: AstrMessageEvent) -> str:
        # 检查直接发送的图片
        direct_image = self.get_image_from_chain(event.get_messages())
        if direct_image:
            return direct_image

        # 非QQ平台不处理引用
        if event.get_platform_name() != "aiocqhttp":
            return None

        # 获取Reply组件
        reply_component = self.get_reply_component(event.get_messages())
        if not reply_component:
            return None

        # 获取引用消息ID（Reply组件的id属性）
        reply_msg_id = getattr(reply_component, 'id', None)
        if not reply_msg_id:
            logger.warning("引用消息中未找到有效的id")
            return None

        # 从引用消息中提取图片URL（仅处理消息段列表）
        referenced_image_url = await self.get_image_from_referenced_msg(event, reply_msg_id)
        return referenced_image_url

    def get_image_from_chain(self, message_chain) -> str:
        for msg in message_chain:
            if isinstance(msg, MsgImage):
                if hasattr(msg, "url") and msg.url:
                    return msg.url
                if hasattr(msg, "data") and isinstance(msg.data, dict):
                    return msg.data.get("url", "")
        return None

    def get_reply_component(self, message_chain) -> Reply:
        for msg in message_chain:
            if isinstance(msg, Reply):
                return msg
        return None

    async def get_image_from_referenced_msg(self, event: AstrMessageEvent, msg_id: str) -> str:
        """从引用消息中提取图片URL（仅处理消息段列表格式）"""
        try:
            if not hasattr(event, "bot"):
                logger.warning("缺少bot属性，无法查询引用消息")
                return None

            # 调用get_msg API获取引用消息
            raw_msg = await event.bot.api.call_action('get_msg', message_id=msg_id)
            if not raw_msg or "message" not in raw_msg:
                logger.warning(f"引用消息查询失败: {raw_msg}")
                return None

            # 消息内容（仅处理列表类型的消息段）
            msg_segments = raw_msg["message"]
            if not isinstance(msg_segments, list):
                logger.warning(f"引用消息格式不是列表，无法处理: {type(msg_segments)}")
                return None

            # 遍历消息段列表，寻找图片类型
            for segment in msg_segments:
                if isinstance(segment, dict) and segment.get("type") == "image":
                    # 图片消息段格式: {'type': 'image', 'data': {'url': 'xxx'}}
                    image_url = segment["data"].get("url")
                    if image_url:
                        return image_url

            # 未找到图片
            logger.warning("引用消息中未包含图片消息段")
            return None

        except Exception as e:
            logger.error(f"提取引用消息图片失败: {str(e)}")
            return None

    async def process_image(self, img_url: str, max_size: int = 1024) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as response:
                if response.status != 200:
                    raise Exception(f"图片下载失败: HTTP {response.status}")
                img_data = await response.read()
        
        img = PILImage.open(BytesIO(img_data))
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, PILImage.LANCZOS)
        
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    async def search_anime(self, img_base64: str, model: str) -> dict:
        payload = {
            "base64": img_base64,
            "is_multi": 1,
            "model": model,
            "ai_detect": 0
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.api_url, 
                data=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API错误: {error_text[:100]}")
                return await response.json()

    def format_response(self, data: dict, model: str) -> str:
        if not data.get("data") or not data["data"]:
            return "🔍 未找到匹配的信息"
        
        first_box = data["data"][0]
        characters = first_box.get("character", [])
        if not characters:
            return "🔍 未识别到具体角色信息"
        
        model_name = "动漫识别" if model == "pre_stable" else "Gal识别"
        emoji = "📺" if model == "pre_stable" else "🎮"
        ai_status = data.get("ai", False)
        ai_flag = "🤖 AI生成" if ai_status else "NO AI"
        
        lines = [
            f"{emoji} {model_name}结果 | {ai_flag}",
            "------------------------"
        ]
        
        for i, item in enumerate(characters[:5]):
            character = item.get("character", "未知角色")
            anime = item.get("work", "未知作品")
            lines.append(f"{i+1}. {character} - 《{anime}》")
        
        if len(characters) > 5:
            lines.append(f"\n> 共找到 {len(characters)} 个结果，显示前5项")
        lines.append("\n数据来源: AnimeTrace，该结果仅供参考")
        
        return "\n".join(lines)

    async def terminate(self):
        logger.info("动漫/Gal识别插件已卸载")