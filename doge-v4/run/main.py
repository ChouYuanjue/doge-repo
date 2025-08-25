from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain
import aiohttp
import asyncio
import re
import json
import time

@register("doge_run", "runnel", "调用菜鸟教程在线编译器执行代码", "1.0.0")
class RunoobCompilerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 初始化编译器配置
        self.main_url = "https://www.runoob.com/try/runcode.php?filename=helloworld&type=python"
        self.compile_url = "https://www.runoob.com/try/compile2.php"
        # 支持的编程语言及其对应的type值和文件扩展名
        self.language_map = {
            "python": {"type": 0, "ext": "py"},
            "py": {"type": 0, "ext": "py"},
            "javascript": {"type": 1, "ext": "js"},
            "js": {"type": 1, "ext": "js"},
            "cpp": {"type": 2, "ext": "cpp"},
            "c++": {"type": 2, "ext": "cpp"},
            "c": {"type": 3, "ext": "c"},
            "java": {"type": 4, "ext": "java"},
            "html": {"type": 5, "ext": "html"},
            "css": {"type": 6, "ext": "css"},
            "php": {"type": 7, "ext": "php"},
            "go": {"type": 8, "ext": "go"},
            "golang": {"type": 8, "ext": "go"},
            "ruby": {"type": 9, "ext": "rb"},
            "swift": {"type": 10, "ext": "swift"},
            "kotlin": {"type": 11, "ext": "kt"}
        }
        # 缓存token及其过期时间
        self.token = None
        self.token_expire_time = 0

    async def initialize(self):
        logger.info("菜鸟教程在线编译器插件已加载")
        # 预加载token
        await self.get_token()

    @filter.command("run")
    async def run_code(self, event: AstrMessageEvent):
        command_text = event.message_str.strip()
        logger.info(f"接收到run命令: {command_text}")
        match = re.match(r"^run\s+(\w+)\s+([\s\S]*)$", command_text)
        
        if not match:
            logger.warning(f"命令格式不匹配: {command_text}")
            yield event.plain_result("格式错误，请使用以下格式：\n/run <语言> <代码>\n例如：/run python print('Hello World')")
            return
        
        language = match.group(1).lower()
        code = match.group(2)
        
        if code:
            code = code.strip()
        
        if language not in self.language_map:
            supported_languages = ", ".join(self.language_map.keys())
            yield event.plain_result(f"不支持的语言：{language}\n支持的语言：{supported_languages}")
            return

        if not code:
            yield event.plain_result(f"代码不能为空，请使用：/run {language} <代码>\n例如：/run {language} print('Hello World')")
            return
        
        try:
            yield event.plain_result("正在执行代码，请稍候...")
            result = await self.execute_code(language, code)
            yield event.plain_result(result)
        except Exception as e:
            logger.error(f"代码执行失败: {str(e)}")
            yield event.plain_result(f"代码执行失败: {str(e)}\n请检查代码或稍后再试")

    async def execute_code(self, language: str, code: str) -> str:
        lang_config = self.language_map[language]

        # 获取token
        token = await self.get_token()
        if not token:
            return "无法获取编译器token，无法执行代码"

        data = {
            "code": code,
            "token": token,
            "language": lang_config["type"],
            "fileext": lang_config["ext"],
            "filename": f"test.{lang_config['ext']}"
        }

        logger.info(f"发送执行请求: 语言={language}, 代码长度={len(code)}字符")
        logger.info(f"请求参数: {data}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.compile_url, data=data) as response:
                    logger.info(f"收到响应: 状态码={response.status}")
                    result = await response.text()
                    logger.info(f"响应内容长度: {len(result)}字符")
                    return self.parse_result(result, language)
        except Exception as e:
            logger.error(f"执行代码异常: {str(e)}")
            return f"执行代码异常: {str(e)}"

    async def get_token(self) -> str:
        """
        获取编译器token，带缓存机制
        """
        current_time = time.time()
        if self.token and current_time < self.token_expire_time:
            logger.info(f"使用缓存的token: {self.token[:5]}...")
            return self.token

        # 从网页中提取token
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.main_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        logger.info(f"成功获取网页内容，长度: {len(html)} 字符")

                        # 从hidden input中提取token (主要方式)
                        token_match = re.search(r'<input type="hidden" id="token" name="token" value="([^"]+)"\s*>', html)
                        if token_match:
                            self.token = token_match.group(1)
                            # 设置token过期时间为1小时后
                            self.token_expire_time = current_time + 3600
                            logger.info(f"Token获取成功: {self.token[:5]}...")
                            return self.token
                        else:
                            # 尝试备用正则表达式模式
                            token_patterns = [
                                r"token\s*=\s*'([^']+)';",
                                r"token\s*=\s*\"([^\"]+);",
                                r"var\s+token\s*=\s*'([^']+)';",
                                r"var\s+token\s*=\s*\"([^\"]+);",
                                r"token\s*:\s*'([^']+)';",
                                r"token\s*:\s*\"([^\"]+);",
                                r"token\s*=\s*([^;]+);"
                            ]

                            for pattern in token_patterns:
                                token_match = re.search(pattern, html)
                                if token_match:
                                    self.token = token_match.group(1)
                                    logger.info(f"使用备用模式 '{pattern}' 提取到token")
                                    self.token_expire_time = current_time + 3600
                                    return self.token

                            logger.error("无法从网页中提取token")
                            # 保存网页内容用于调试
                            with open("runoob_debug.html", "w", encoding="utf-8") as f:
                                f.write(html)
                            logger.info("网页内容已保存到 runoob_debug.html 供调试")
                            return None
                    else:
                        logger.error(f"获取token失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"获取token异常: {str(e)}")
            return None

    def parse_result(self, result: str, language: str) -> str:
        """
        解析编译结果
        """
        try:
            data = json.loads(result)
            logger.info(f"JSON解析成功: {data}")
            output = data.get('output', '').replace('\n', '\n')
            error = data.get('error', '').replace('\n', '\n')
            errors = data.get('errors', '').replace('\n', '\n')

            # 检查错误是否为非空白字符
            has_error = (error and error.strip()) or (errors and errors.strip())
            has_output = output and output.strip()

            if has_error:
                return f"执行错误:\n{error or errors}"
            elif has_output:
                return f"执行结果:\n{output}"
            else:
                return "执行完成，但没有输出结果"
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {result}")
            # 尝试直接返回结果
            if result.strip():
                return f"执行结果:\n{result}"
            else:
                return "无法解析执行结果"
        except Exception as e:
            logger.error(f"解析结果异常: {str(e)}")
            return f"解析结果异常: {str(e)}"