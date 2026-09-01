from __future__ import annotations

import html
import json
import re
import time

import aiohttp

LANGUAGES = {
    "python": (0, "py"), "py": (0, "py"), "javascript": (1, "js"), "js": (1, "js"),
    "cpp": (2, "cpp"), "c++": (2, "cpp"), "c": (3, "c"), "java": (4, "java"),
    "html": (5, "html"), "css": (6, "css"), "php": (7, "php"), "go": (8, "go"),
    "golang": (8, "go"), "ruby": (9, "rb"), "swift": (10, "swift"), "kotlin": (11, "kt"),
}


class RunoobExecutor:
    MAIN = "https://www.runoob.com/try/runcode.php?filename=helloworld&type=python"
    COMPILE = "https://www.runoob.com/try/compile2.php"

    def __init__(self):
        self.token: str | None = None
        self.expires = 0.0

    async def get_token(self) -> str:
        if self.token and time.monotonic() < self.expires:
            return self.token
        timeout = aiohttp.ClientTimeout(total=15, connect=6, sock_read=10)
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "Doge-v5/5.6"}) as session:
            async with session.get(self.MAIN) as response:
                response.raise_for_status()
                page = await response.text()
        patterns = [
            r'id=["\']token["\'][^>]*value=["\']([^"\']+)',
            r'name=["\']token["\'][^>]*value=["\']([^"\']+)',
            r'\btoken\s*=\s*["\']([^"\']+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, page, re.I)
            if match:
                self.token = match.group(1)
                self.expires = time.monotonic() + 1800
                return self.token
        raise RuntimeError("Runoob token format changed")

    async def execute(self, language: str, code: str) -> str:
        language = language.lower().strip()
        if language not in LANGUAGES:
            raise ValueError("不支持的语言：" + language)
        if len(code) > 12000:
            raise ValueError("代码最多 12000 字符")
        typ, ext = LANGUAGES[language]
        token = await self.get_token()
        data = {
            "code": code,
            "token": token,
            "language": typ,
            "fileext": ext,
            "filename": f"main.{ext}",
        }
        timeout = aiohttp.ClientTimeout(total=25, connect=6, sock_read=20)
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "Doge-v5/5.6"}) as session:
            async with session.post(self.COMPILE, data=data) as response:
                response.raise_for_status()
                raw = await response.text()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Runoob 执行协议发生变化：远端未返回 JSON；拒绝把未知响应当作执行结果") from exc
        if not isinstance(obj, dict):
            raise RuntimeError("Runoob 执行协议发生变化：JSON 根节点不是对象")
        error = str(obj.get("error") or obj.get("errors") or "").strip()
        output = str(obj.get("output") or "").strip()
        text = ("执行错误：\n" + error) if error else (output or "执行完成，无输出。")
        return html.unescape(text)[:12000]
