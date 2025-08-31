from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image as MsgImage, Plain, Video, Reply
import aiohttp
import base64
import asyncio
import json
from PIL import Image
from io import BytesIO
import os
import re
from volcenginesdkarkruntime import Ark
import requests


@register("doubao", "runnel", "豆包AI插件", "1.2.0")
class DoubaoAIPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_key = os.environ.get("ARK_API_KEY", "")
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3"
        
        self.client = Ark(
            base_url=self.base_url,
            api_key=self.api_key
        )
       
        self.models = {
            "t2v": "doubao-seedance-1-0-pro-250528",
            "i2v": "doubao-seedance-1-0-lite-i2v-250428",
            "i2i": "doubao-seededit-3-0-i2i-250628",
            "t2i": "doubao-seedream-3-0-t2i-250415"
        }
        
        # 视频生成配置
        self.video_config = {
            "resolution": "480p",
            "duration": 5
        }

    @filter.command_group("doubao")
    def db(self):
        pass

    @db.command("i2v")
    async def image_to_video(self, event: AstrMessageEvent):
        """图生视频: /doubao i2v <文本> <图片>"""
        try:
            message = event.message_str or ""
            text = message[len("/doubao i2v"):].strip()

            # 提取图片
            image_urls = await self.extract_images_from_event(event)
            if not text or not image_urls:
                yield event.plain_result("请提供文本描述和图片")
                return

            # 检查图片尺寸是否符合要求
            valid_images = []
            for img_url in image_urls:
                try:
                    # 获取图片并检查尺寸
                    response = requests.get(img_url, timeout=10)
                    img = Image.open(BytesIO(response.content))
                    width, height = img.size

                    if width < 300 or height < 300:
                        yield event.plain_result(f"图片尺寸不符合要求 (需要至少300px×300px)，当前图片尺寸: {width}×{height}px")
                        return
                    valid_images.append(img_url)
                except Exception as e:
                    yield event.plain_result(f"无法获取或处理图片: {str(e)}")
                    return

            video_url = await self._call_i2v_api(text, valid_images)

            await event.send(event.plain_result("开始生成视频，请稍候..."))
            video_url = await self._call_i2v_api(text, image_urls)

            # 尝试直接发送视频文件
            try:
                chain = [
                    Video.fromURL(url=video_url)
                ]
                yield event.chain_result(chain)
            except Exception as e:
                logger.warning(f"直接发送视频失败，转为发送链接: {str(e)}")
                # 发送失败则转为发送链接
                yield event.plain_result(f"视频生成成功：{video_url}")
        except Exception as e:
            logger.error(f"i2v命令执行失败: {str(e)}")
            yield event.plain_result(f"处理失败: {str(e)}")

    @db.command("i2i")
    async def image_to_image(self, event: AstrMessageEvent):
        """图生图: /doubao i2i <文本> <图片>"""
        try:
            message = event.message_str or ""
            text = message[len("/doubao i2i"):].strip()

            image_urls = await self.extract_images_from_event(event)
            if not text or not image_urls:
                yield event.plain_result("请提供文本描述和图片")
                return
            # 取第一张图片用于生成
            image_url = image_urls[0]

            await event.send(event.plain_result("开始生成图片，请稍候..."))
            image_url = await self._call_i2i_api(text, image_url)

            yield event.plain_result(f"图片生成成功")
            yield event.image_result(image_url)
        except Exception as e:
            logger.error(f"i2i命令执行失败: {str(e)}")
            yield event.plain_result(f"处理失败: {str(e)}")

    @db.command("t2v")
    async def text_to_video(self, event: AstrMessageEvent):
        """文生视频: /doubao t2v <文本>"""
        try:
            message = event.message_str or ""
            text = message[len("/doubao t2v"):].strip()

            if not text:
                yield event.plain_result("请提供文本描述")
                return

            await event.send(event.plain_result("开始生成视频，请稍候..."))
            video_url = await self._call_t2v_api(text)

            # 尝试直接发送视频文件
            try:
                chain = [
                    Video.fromURL(url=video_url)
                ]
                yield event.chain_result(chain)
            except Exception as e:
                logger.warning(f"直接发送视频失败，转为发送链接: {str(e)}")
                # 发送失败则转为发送链接
                yield event.plain_result(f"视频生成成功：{video_url}")
        except Exception as e:
            logger.error(f"t2v命令执行失败: {str(e)}")
            yield event.plain_result(f"处理失败: {str(e)}")

    @db.command("t2i")
    async def text_to_image(self, event: AstrMessageEvent):
        """文生图: /doubao t2i <文本>"""
        try:
            message = event.message_str or ""
            text = message[len("/doubao t2i"):].strip()

            if not text:
                yield event.plain_result("请提供文本描述")
                return

            await event.send(event.plain_result("开始生成图片，请稍候..."))
            image_url = await self._call_t2i_api(text)

            yield event.plain_result(f"图片生成成功")
            yield event.image_result(image_url)
        except Exception as e:
            logger.error(f"t2i命令执行失败: {str(e)}")
            yield event.plain_result(f"处理失败: {str(e)}")

    async def extract_images_from_event(self, event: AstrMessageEvent):
        """从事件中提取图片URL列表（支持直接发送和引用消息）"""
        image_urls = []

        # 尝试从消息链中提取图片
        message_chain_images = self.get_images_from_chain(event.get_messages())
        image_urls.extend(message_chain_images)

        # 如果消息链中没有足够的图片，尝试从引用消息中提取
        if len(image_urls) < 2:
            referenced_image = await self.get_image_from_referenced_msg(event)
            if referenced_image and referenced_image not in image_urls:
                image_urls.append(referenced_image)

        return image_urls

    def get_images_from_chain(self, message_chain):
        """从消息链中提取图片URL列表"""
        image_urls = []
        if not message_chain:
            return image_urls

        for msg in message_chain:
            if isinstance(msg, MsgImage):
                if hasattr(msg, "url") and msg.url:
                    image_urls.append(msg.url)
                elif hasattr(msg, "data") and isinstance(msg.data, dict):
                    url = msg.data.get("url", "")
                    if url:
                        image_urls.append(url)
        return image_urls

    def get_reply_component(self, message_chain):
        """从消息链中获取Reply组件"""
        for msg in message_chain:
            if isinstance(msg, Reply):
                return msg
        return None

    async def get_image_from_referenced_msg(self, event: AstrMessageEvent):
        """从引用消息中提取图片URL"""
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

        try:
            if not hasattr(event, "bot"):
                logger.warning("缺少bot属性，无法查询引用消息")
                return None

            # 调用get_msg API获取引用消息
            raw_msg = await event.bot.api.call_action('get_msg', message_id=reply_msg_id)
            if not raw_msg or 'message' not in raw_msg:
                logger.warning("获取引用消息失败")
                return None

            # 解析消息段列表
            message_chain = raw_msg['message']
            if not message_chain:
                return None

            # 从消息段列表中提取图片
            for msg in message_chain:
                if isinstance(msg, dict) and msg.get('type') == 'image':
                    return msg.get('data', {}).get('url', '')

            return None
        except Exception as e:
            logger.error(f"获取引用消息失败: {str(e)}")
            return None

    async def _call_i2v_api(self, text, images):
        """调用图生视频API（支持单图或首尾帧）"""
        model = self.models["i2v"]
        
        content = []
        
        # 组合文本提示词和视频配置参数
        video_config_str = f" --rs {self.video_config['resolution']} --dur {self.video_config['duration']} --cf false"
        full_text = text + video_config_str
        
        content.append({
            "type": "text",
            "text": full_text
        })
        
        # 添加首帧图片
        if len(images) >= 1:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": images[0]
                },
                "role": "first_frame"  
            })
        else:
            raise Exception("未提供首帧图片")
        
        # 添加尾帧图片（如果有）
        if len(images) >= 2:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": images[1]
                },
                "role": "last_frame"
            })
        
        try:
            create_result = self.client.content_generation.tasks.create(
                model=model,
                content=content
            )
            
            # 轮询查询结果
            task_id = create_result.id
            max_retries = 30  # 最多轮询30次（约5分钟）
            retry_count = 0
            
            while retry_count < max_retries:
                retry_count += 1
                get_result = self.client.content_generation.tasks.get(task_id=task_id)
                
                if get_result.status == "succeeded":
                    return get_result.content.video_url
                elif get_result.status == "failed":
                    error_msg = get_result.error.message if hasattr(get_result.error, 'message') else str(get_result.error)
                    raise Exception(f"视频生成失败: {error_msg}")
                else:
                    await asyncio.sleep(10)  # 每10秒轮询一次
            
            raise Exception("视频生成超时")
        except Exception as e:
            logger.error(f"i2v API调用失败: {str(e)}")
            raise

    async def _call_t2v_api(self, text):
        """调用文生视频API"""
        model = self.models["t2v"]

        content = [{
            "type": "text",
            "text": text
        }]
        
        create_result = self.client.content_generation.tasks.create(
            model=model,
            content=content
        )
        
        # 轮询查询结果
        task_id = create_result.id
        while True:
            get_result = self.client.content_generation.tasks.get(task_id=task_id)
            if get_result.status == "succeeded":
                return get_result.content.video_url
            elif get_result.status == "failed":
                raise Exception(f"视频生成失败: {get_result.error}")
            else:
                await asyncio.sleep(10)

    async def _call_i2i_api(self, text, image_url):
        """调用图生图API"""
        model = self.models["i2i"]
 
        response = self.client.images.generate(
            model=model,
            prompt=text,
            image=image_url,
            seed=123,
            guidance_scale=5.5,
            size="adaptive",
            watermark=True
        )
        
        return response.data[0].url

    async def _call_t2i_api(self, text):
        """调用文生图API"""
        model = self.models["t2i"]

        response = self.client.images.generate(
            model=model,
            prompt=text
        )
        
        return response.data[0].url

    async def _send_api_request(self, url, data):
        """发送API请求"""
        headers = {
            "Authorization": f"Bearer {get_auth_token()}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API错误: {error_text[:100]}")
                result = await response.json()
                
                if "data" in result and "video_url" in result["data"]:
                    return result["data"]["video_url"]
                elif "data" in result and "image_url" in result["data"]:
                    return result["data"]["image_url"]
                else:
                    raise Exception("API返回格式异常")

    async def _download_image_as_base64(self, image_url):
        """下载图片并转换为base64编码"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        return base64.b64encode(image_data).decode('utf-8')
                    else:
                        logger.error(f"图片下载失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"图片处理失败: {str(e)}")
            return None


    async def terminate(self):
        pass
