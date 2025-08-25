from astrbot.api.message_components import Image, Plain
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import aiohttp
import os
import json
import logging
import urllib.parse
from io import BytesIO
import xml.etree.ElementTree as ET

@register("wolframalpha", "runnel", "WolframAlpha查询", "1.0.0")
class WolframAlphaPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.appid = "your-api-key"
        self.base_url = "https://api.wolframalpha.com/v2/query"
        self.error_msg = "查询过程中发生错误，请稍后再试。"
        if not self.appid:
            logging.warning("未设置 WOLFRAM_ALPHA_APPID")

    @filter.command("wa", alias="wolframalpha")
    async def wa_command(self, event: AstrMessageEvent):
        """
        WolframAlpha 查询命令
        用法: /wa <查询内容>
        示例: /wa 2+2
        """
        message = event.message_str or ""
        parts = message.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            yield event.plain_result("请提供查询内容，用法: /wa <查询内容>")
            return

        query = parts[1].strip()

        # 检查 AppID 是否存在
        if not self.appid:
            yield event.plain_result("未配置 WolframAlpha AppID，请先设置环境变量 WOLFRAM_ALPHA_APPID")
            return

        try:
            # 调用查询方法
            results = await self.query_wolframalpha(query)
            if not results:
                yield event.plain_result("未找到相关结果。")
                return

            # 构建回复消息
            reply_parts = [Plain("WolframAlpha 查询结果:\n")]
            for i, result in enumerate(results, 1):
                title_text = f"{i}. {result['title']}: "
                reply_parts.append(Plain(title_text))
                
                content = result['content']
                if 'text' in content:
                    reply_parts.append(Plain(content['text'] + "\n"))
                
                if 'image_url' in content and content['image_url']:
                    try:
                        # 下载图片
                        async with aiohttp.ClientSession() as session:
                            async with session.get(content['image_url']) as img_response:
                                if img_response.status == 200:
                                    img_data = await img_response.read()
                                    # 添加图片到回复 - 使用fromBytes方法
                                    reply_parts.append(Image.fromBytes(img_data))
                                    reply_parts.append(Plain("\n"))
                                else:
                                    logging.warning(f"图片下载失败，状态码: {img_response.status}")
                    except Exception as e:
                        logging.error(f"图片处理错误: {str(e)}", exc_info=True)
            yield event.chain_result(reply_parts)
        except Exception as e:
            logging.error(f"WolframAlpha 查询错误: {str(e)}", exc_info=True)
            yield event.plain_result(f"查询错误: {str(e)}")

    async def query_wolframalpha(self, query: str) -> list:
        """
        调用 WolframAlpha API 进行查询
        :param query: 查询字符串
        :return: 查询结果列表
        """
        params = {
            "input": query,
            "appid": self.appid,
            "format": "plaintext,image",  # 同时获取文本和图片
            "output": "json"  # 确保输出为JSON格式
        }

        logging.info(f"正在调用 WolframAlpha API，查询内容: {query}")
        logging.debug(f"API 请求参数: {params}")

        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url, params=params) as response:
                logging.info(f"API 响应状态码: {response.status}")
                if response.status != 200:
                    raise Exception(f"API 请求失败，状态码: {response.status}")

                # 获取响应的Content-Type
                content_type = response.headers.get('Content-Type', '')
                logging.debug(f"API 响应 Content-Type: {content_type}")

                # 根据Content-Type选择解析方法
                if 'application/json' in content_type:
                    try:
                        data = await response.json()
                        logging.debug(f"JSON 响应: {data}")
                        return self._parse_json_response(data)
                    except json.JSONDecodeError as e:
                        logging.error(f"JSON 解析失败: {str(e)}")
                        # 即使Content-Type是JSON，解析失败时也尝试解析为XML
                        xml_content = await response.text()
                        logging.debug(f"尝试将JSON解析失败的响应作为XML解析: {xml_content}")
                        return self._parse_xml_response(xml_content)
                else:
                    # 默认为XML解析
                    xml_content = await response.text()
                    logging.debug(f"XML 响应: {xml_content}")
                    return self._parse_xml_response(xml_content)

    def _parse_json_response(self, data: dict) -> list:
        """
        解析 JSON 格式的响应
        :param data: JSON 数据
        :return: 解析后的结果列表
        """
        results = []

        # 检查是否有查询结果
        if "queryresult" not in data:
            logging.error("JSON 响应中缺少 queryresult 字段")
            results.append("错误: 响应格式不正确，缺少 queryresult 字段")
            return results

        query_result = data["queryresult"]
        logging.debug(f"queryresult: {query_result}")

        # 检查是否有错误
        if query_result.get("error", False):
            error_info = query_result.get("errormsg", "")
            if not error_info:
                # 如果没有错误信息，尝试从其他字段获取
                error_info = str(query_result.get("error", {}))
                logging.error(f"API 返回错误但无 errormsg: {error_info}")
                results.append(f"错误: 未知错误 - API 返回错误但无详细信息: {error_info}")
            else:
                logging.error(f"API 返回错误: {error_info}")
                results.append(f"错误: {error_info}")
            return results

        # 检查是否有结果
        if not query_result.get("success", False):
            logging.warning("查询未成功，success=false")
            results.append("错误: 查询未成功，可能是输入无法被识别")
            return results

        # 解析 pods
        if "pods" in query_result:
            for pod in query_result["pods"]:
                # 跳过输入 pod
                if pod.get("id") == "Input":
                    continue

                pod_title = pod.get("title", "未命名")
                
                # 解析 subpods
                if "subpods" in pod:
                    for subpod in pod["subpods"]:
                        pod_content = {}
                        if "plaintext" in subpod and subpod["plaintext"]:
                            pod_content["text"] = subpod["plaintext"]
                        
                        # 提取图片URL
                        if "img" in subpod:
                            pod_content["image_url"] = subpod["img"].get("src", "")
                        
                        if pod_content:
                            results.append({
                                "title": pod_title,
                                "content": pod_content
                            })
                
                else:
                    logging.debug(f"Pod {pod_title} 没有 subpods 内容")
        else:
            logging.warning("JSON 响应中缺少 pods 字段")
            results.append("错误: 响应中没有找到结果数据")

        return results

    def _parse_xml_response(self, xml_content: str) -> list:
        """
        解析 XML 格式的响应
        :param xml_content: XML 字符串
        :return: 解析后的结果列表
        """
        results = []
        try:
            root = ET.fromstring(xml_content)

            # 命名空间处理
            namespace = {"wa": "http://www.wolframalpha.com/2009/api"}

            # 检查是否有错误
            error = root.find(".//wa:error", namespace)
            if error is not None:
                error_msg_elem = error.find(".//wa:msg", namespace)
                error_msg = error_msg_elem.text if error_msg_elem is not None else "未知错误"
                logging.error(f"API 返回错误: {error_msg}")
                results.append(f"错误: {error_msg}")
                return results

            # 检查是否有结果
            query_result = root.find(".//wa:queryresult", namespace)
            if query_result is None:
                logging.error("XML 响应中缺少 queryresult 元素")
                results.append("错误: 响应格式不正确，缺少 queryresult 元素")
                return results

            success = query_result.get("success")
            if success != "true":
                logging.warning("查询未成功，success=false")
                results.append("错误: 查询未成功，可能是输入无法被识别")
                return results

            # 解析 pods
            pods = root.findall(".//wa:pod", namespace)
            for pod in pods:
                # 跳过输入 pod
                if pod.get("id") == "Input":
                    continue

                pod_title = pod.get("title", "未命名")
                pod_content = []

                # 解析 subpods
                subpods = pod.findall(".//wa:subpod", namespace)
                for subpod in subpods:
                    pod_content = {}
                    plaintext = subpod.find(".//wa:plaintext", namespace)
                    if plaintext is not None and plaintext.text:
                        pod_content["text"] = plaintext.text
                    
                    # 提取图片URL
                    img = subpod.find(".//wa:img", namespace)
                    if img is not None and img.get("src"):
                        pod_content["image_url"] = img.get("src")
                    
                    if pod_content:
                        results.append({
                            "title": pod_title,
                            "content": pod_content
                        })
                if pod_content:
                    results.append(f"{pod_title}: {'; '.join(pod_content)}")
                else:
                    logging.debug(f"Pod {pod_title} 没有 plaintext 内容")
        except Exception as e:
            logging.error(f"XML 解析错误: {str(e)}", exc_info=True)
            results.append(f"错误: XML 解析失败 - {str(e)}")

        return results