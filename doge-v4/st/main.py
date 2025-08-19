import os
import json
import difflib
import tempfile
import aiohttp
import openpyxl
import re
import lxml.html

from astrbot.api.all import *

@register("doge_st", "runnel", "从 safebooru 获取图片的插件", "1.0.0")
class SafebooruPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        if config is None:
            config = {}
        super().__init__(context)
        self.config = config
        # 从配置中获取 limit 和 display_tags 参数
        self.limit = self.config.get("limit", 100)
        self.display_tags = self.config.get("display_tags", False)
        self.tag_mapping = self.load_tag_mapping("tag_mapping.xlsx")
        base_dir = os.path.dirname(os.path.realpath(__file__))
        self.usage_file = os.path.join(base_dir, "usage_count.json")
        self.usage_counts = self.load_usage_counts()

    def load_tag_mapping(self, filename: str) -> dict:
        mapping = {}
        base_dir = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(base_dir, filename)
        if os.path.exists(filepath):
            wb = openpyxl.load_workbook(filepath)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                if row[0] and row[1]:
                    mapping[str(row[1])] = str(row[0])
            wb.close()
        else:
            print(f"文件 {filepath} 不存在。")
        return mapping

    def load_usage_counts(self) -> dict:
        if os.path.exists(self.usage_file):
            try:
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        else:
            return {}

    def save_usage_counts(self):
        try:
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(self.usage_counts, f)
        except Exception as e:
            print("保存使用次数出错：", e)

    @command("st tag")
    async def fetch_image(self, event: AstrMessageEvent, tag: str):
        """
        根据用户输入的标签（支持中文和英文）从 safebooru 获取图片。
        1. 尝试在映射中进行模糊匹配，如果匹配到则使用映射后的真实 tag，否则直接使用用户输入的 tag；
        2. 如果配置中 display_tags 为 True，则先发送返回JSON中的 "tags" 字段信息；
        3. 如果 API 返回的图片列表为空，则报错提示。
        """
        # 如果映射存在，则尝试匹配；如果没有匹配项，直接使用用户输入的 tag
        candidates = list(self.tag_mapping.keys())
        matches = difflib.get_close_matches(tag, candidates, n=1, cutoff=0.1)
        if matches:
            best_match = matches[0]
            query_tag = self.tag_mapping[best_match]
        else:
            query_tag = tag

        # 获取该 tag 的使用次数，确保返回图片依次不同
        count = self.usage_counts.get(query_tag, 0)
        api_url = (f"https://safebooru.org/index.php?page=dapi&s=post&q=index"
                   f"&tags={query_tag}&limit={self.limit}&json=1")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        yield event.plain_result("无法获取图片数据，请稍后重试。")
                        return
                    posts = await resp.json(content_type=None)
        except Exception as e:
            yield event.plain_result(f"获取图片数据时出错: {e}")
            return

        if not posts:
            yield event.plain_result("未找到相关图片。")
            return

        index = count % len(posts)
        post = posts[index]
        file_url = post.get("file_url")
        if not file_url:
            yield event.plain_result("未获取到图片链接。")
            return

        # 当 display_tags 为 True 时，先发送图片的 tags 字段内容
        if self.display_tags:
            tags_field = post.get("tags", "")
            yield event.plain_result("Tags: " + tags_field)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as img_resp:
                    if img_resp.status != 200:
                        yield event.plain_result("下载图片失败。")
                        return
                    img_data = await img_resp.read()
                    temp_dir = tempfile.gettempdir()
                    temp_file_path = os.path.join(temp_dir, os.path.basename(file_url))
                    with open(temp_file_path, "wb") as f:
                        f.write(img_data)
        except Exception as e:
            yield event.plain_result(f"下载图片时出错: {e}")
            return

        self.usage_counts[query_tag] = count + 1
        self.save_usage_counts()

        yield event.image_result(temp_file_path)

        try:
            os.remove(temp_file_path)
        except Exception as e:
            print("删除临时文件失败：", e)

    @command("st random")
    async def safebooru_random(self, event: AstrMessageEvent):
        """
        获取随机图片：
        1. 访问 https://safebooru.org/index.php?page=post&s=random，允许重定向获取最终页面内容；
        2. 使用 XPath (/html/body/div[5]/div/div[2]/div[1]/div[2]/div[1]/img) 解析页面，
           提取目标 img 元素的 src 和 alt 属性；
        3. 无论如何，都要输出图片；如果配置中 display_tags 为 True，则额外发送标签信息（alt 字段）。
        """
        random_url = "https://safebooru.org/index.php?page=post&s=random"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(random_url, allow_redirects=True) as resp:
                    if resp.status != 200:
                        yield event.plain_result("请求随机图片失败，请稍后重试。")
                        return
                    html = await resp.text()
        except Exception as e:
            yield event.plain_result(f"请求随机图片出错: {e}")
            return

        try:
            doc = lxml.html.fromstring(html)
            elements = doc.xpath('/html/body/div[5]/div/div[2]/div[1]/div[2]/div[1]/img')
            if elements:
                img_elem = elements[0]
                src = img_elem.get("src")
                alt = img_elem.get("alt", "未知标签")
                # 如果启用了 display_tags，额外发送标签信息
                if self.display_tags:
                    yield event.plain_result("Tags: " + alt)
                # 无论如何，都输出图片
                yield event.image_result(src)
            else:
                yield event.plain_result("未能通过XPath找到随机图片。")
        except Exception as e:
            yield event.plain_result(f"解析随机图片时出错: {e}")
