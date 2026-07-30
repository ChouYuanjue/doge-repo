import asyncio
import aiohttp
from typing import Optional, List, Dict, Any
import emoji
import os
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp
from volcenginesdkarkruntime import Ark


@register("emojimix", "runnel ", "合成emoji插件", "2.0.0")
class EmojiMixPlugin(Star):
    def __init__(self, context: Context, config: Optional[AstrBotConfig] = None):
        super().__init__(context)
        self.config = config if config else AstrBotConfig({})
        self.date_codes = self.config.get("date_codes")
        self.base_url_template = self.config.get("base_url_template")
        self.request_timeout = self.config.get("request_timeout")
        self.auto_trigger = self.config.get("auto_trigger", True)
        
        # 初始化豆包API客户端
        self.api_key = os.environ.get("ARK_API_KEY", "")
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.client = Ark(
            base_url=self.base_url,
            api_key=self.api_key
        )
        self.t2i_model = "doubao-seedream-3-0-t2i-250415"

    async def initialize(self):
        logger.info("EmojiKitchenPlugin 初始化完成。")
        pass

    async def terminate(self):
        logger.info("EmojiKitchenPlugin 正在终止。")
        pass

    # ---核心 Emoji 处理逻辑---
    def _get_emoji_hex_code(self, emoji: str) -> Optional[str]:
        try:
            hex_code = [f"u{ord(c):x}" for c in emoji]
            full_hex = "-".join(hex_code)
            return full_hex
        except Exception as e:
            logger.error(f"转换 Emoji '{emoji}' 到十六进制时出错: {e}")
            return None

    async def _find_emoji_kitchen_url_async(
        self, emoji1: str, emoji2: str
    ) -> Optional[str]:
        hex1 = self._get_emoji_hex_code(emoji1)
        hex2 = self._get_emoji_hex_code(emoji2)

        if not hex1 or not hex2:
            logger.warning(f"无法为 '{emoji1}' 或 '{emoji2}' 获取有效的十六进制代码。")
            return None

        logger.info(f"正在尝试混合: {emoji1} ({hex1}) + {emoji2} ({hex2})")

        async with aiohttp.ClientSession() as session:
            urls_to_check = []
            for date_code in self.date_codes:
                try:
                    url1 = self.base_url_template.format(
                        date_code=date_code, hex1=hex1, hex2=hex2
                    )
                    urls_to_check.append(url1)
                    if hex1 != hex2:
                        url2 = self.base_url_template.format(
                            date_code=date_code, hex1=hex2, hex2=hex1
                        )
                        urls_to_check.append(url2)
                except KeyError as e:
                    logger.error(
                        f"URL 模板格式错误或缺少键: {e}. 模板: '{self.base_url_template}'"
                    )
                    return None

            for url in urls_to_check:
                try:
                    logger.info(f"正在检查 URL: {url}")
                    async with session.head(
                        url, timeout=self.request_timeout
                    ) as response:
                        if response.status == 200:
                            logger.info(f"找到有效的 Emoji Kitchen URL: {url}")
                            return url
                except asyncio.TimeoutError:
                    logger.warning(f"检查 URL 超时: {url}")
                except aiohttp.ClientError as e:
                    logger.warning(f"检查 URL 时发生网络错误 {url}: {e}")

        logger.info(f"未能找到 {emoji1} 和 {emoji2} 的有效混合 Emoji URL。")
        return None
        
    async def _call_doubao_t2i_api(self, emoji_input: str) -> Optional[str]:
        """调用豆包文生图API生成emoji混合图片"""
        try:
            prompt = f"输入的emoji为{emoji_input}，任务要求是根据输入的emoji生成一张融合各emoji特征的唯一一个新emoji，保证照顾到各emoji的特征，flat design。图片的比例为1:1，背景为白色。"
            
            logger.info(f"调用豆包API生成图片，提示词: {prompt}")
            
            response = self.client.images.generate(
                model=self.t2i_model,
                prompt=prompt
            )
            
            if response.data and len(response.data) > 0:
                image_url = response.data[0].url
                logger.info(f"豆包API图片生成成功，URL: {image_url}")
                return image_url
            else:
                logger.error("豆包API返回数据格式异常")
                return None
        except Exception as e:
            logger.error(f"调用豆包API失败: {str(e)}")
            return None

    # --- 辅助函数：提取文本中的 Emoji ---
    def _extract_emojis_from_text(self, text: str) -> List[str]:
        ems = []
        for em in emoji.emoji_list(text):
            ems.append(em["emoji"])
        return ems

    # --- 内部处理合成并发送结果的方法 ---
    async def _process_and_send_mix(
        self, event: AstrMessageEvent, emoji1: str, emoji2: str
    ):
        """内部方法，用于执行合成查找并发送结果"""
        logger.info(
            f"检测到混合请求: {emoji1} 和 {emoji2} (来自: {event.get_sender_name()})"
        )
        try:
            result_url = await self._find_emoji_kitchen_url_async(emoji1, emoji2)
        except Exception as e:
            logger.error(
                f"执行 Emoji Kitchen URL 查找时发生意外错误: {e}", exc_info=True
            )
            result_url = None

        if result_url:
            logger.info(f"成功合成 {emoji1} + {emoji2}，发送图片: {result_url}")
            # 修复错误：之前错误地引用了未定义的变量doubao_image_url
            # 恢复原始逻辑，使用chain_result发送原始emoji kitchen的图片
            yield event.image_result(result_url)
        else:
            # 尝试调用豆包API生成图片
            logger.info(f"尝试使用豆包API生成 {emoji1} + {emoji2} 的混合图片")
            await event.send(event.plain_result("原始emoji组合未找到，正在调用AI生成图片，请稍候..."))
            
            emoji_input = f"{emoji1} 和 {emoji2}"
            doubao_image_url = await self._call_doubao_t2i_api(emoji_input)
            
            if doubao_image_url:
                logger.info(f"豆包API成功生成 {emoji1} + {emoji2} 的混合图片")
                # 使用专门的image_result方法发送豆包API生成的图片
                yield event.plain_result(f"图片生成成功")
                yield event.image_result(doubao_image_url)
            else:
                response_text = f"😟 抱歉，无法找到 {emoji1} 和 {emoji2} 的混合 Emoji，且调用AI生成图片也失败了。"
                logger.info(f"未能找到 {emoji1} + {emoji2} 的混合 Emoji，且豆包API调用失败。")
                yield event.plain_result(response_text)

    # --- 命令处理 ---
    @filter.command("emojimix", alias={"合成emoji"}, priority=1)
    async def mix_emoji_command(self, event: AstrMessageEvent):
        """(命令) 合成两个 Emoji。用法: /emojimix <emoji1><emoji2>"""
        input_text = event.message_str.strip()

        if "emojimix" in input_text:
            input_text = input_text.replace("emojimix", "", 1).strip()

        # 添加日志，确认 input_text 的内容
        logger.debug(
            f"命令 /emojimix 接收到的原始参数文本 (event.message_str): '{input_text}'"
        )

        if not input_text:
            yield event.plain_result(
                "🤔 请在命令后提供两个 Emoji 来合成。\n例如: `/emojimix 💩😊`"
            )
            # 确保停止事件，即使没有参数也由命令处理器处理了
            event.stop_event()
            return

        # 尝试提取文本中的所有 Emoji
        emojis = self._extract_emojis_from_text(input_text)
        logger.debug(f"命令 /emojimix 从 '{input_text}' 提取到 emojis: {emojis}")

        # 验证逻辑
        if len(emojis) == 2:
            text_without_emojis = input_text
            temp_text = text_without_emojis.replace(emojis[0], "", 1)
            temp_text = temp_text.replace(emojis[1], "", 1)

            if not temp_text.strip():
                emoji1 = emojis[0]
                emoji2 = emojis[1]
                logger.info(
                    f"命令 /emojimix 解析成功: emoji1='{emoji1}', emoji2='{emoji2}'"
                )
                async for result in self._process_and_send_mix(event, emoji1, emoji2):
                    yield result
            else:
                logger.warning(
                    f"命令 /emojimix 输入 '{input_text}' 包含除两个 Emoji 和空格外的其他字符: '{temp_text.strip()}'"
                )
                yield event.plain_result(
                    f"🤔 请确保命令后只提供两个 Emoji (可以有空格分隔)。检测到额外字符: '{temp_text.strip()}'"
                )

        elif len(emojis) == 1:
            logger.warning(f"命令 /emojimix 输入 '{input_text}' 只包含一个 Emoji。")
            yield event.plain_result(
                "🤔 检测到只有一个 Emoji，请提供两个 Emoji 来合成。"
            )
        elif len(emojis) > 2:
            logger.warning(f"命令 /emojimix 输入 '{input_text}' 包含超过两个 Emoji。")
            yield event.plain_result(
                "🤔 检测到超过两个 Emoji，请只提供两个 Emoji 来合成。"
            )
        else:
            logger.warning(f"命令 /emojimix 输入 '{input_text}' 未检测到有效的 Emoji。")
            yield event.plain_result(
                "🤔 未能在输入中检测到有效的 Emoji，请提供两个 Emoji。"
            )

        event.stop_event()

    # --- 自动检测双 Emoji 消息 ---
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_double_emoji_message(self, event: AstrMessageEvent):
        if self.auto_trigger:
            message_text = event.get_message_str().strip()
            if not message_text:  # 忽略空消息
                return

            emojis = self._extract_emojis_from_text(message_text)

            if len(emojis) == 2:
                # 进一步检查，去除所有非 Emoji 字符后是否为空，或者只剩空格
                text_without_emojis = message_text
                for e in emojis:
                    text_without_emojis = text_without_emojis.replace(
                        e, "", 1
                    )  # 替换一次，防止emoji内部字符被误删

                if not text_without_emojis.strip():  # 如果移除 emojis 后只剩空格或为空
                    emoji1 = emojis[0]
                    emoji2 = emojis[1]

                    logger.debug(f"自动检测到双 Emoji 消息: '{emoji1}' 和 '{emoji2}'")
                    # 调用内部处理方法
                    async for result in self._process_and_send_mix(event, emoji1, emoji2):
                        yield result
                    event.stop_event()
                else:
                    logger.debug(
                        f"提取到两个 Emoji，但原消息包含其他字符: '{message_text}' -> '{text_without_emojis}'"
                    )