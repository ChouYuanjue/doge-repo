import re
import time
from typing import Dict
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Image, Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .render import DrawCube
from cube_rs import CubeCore  # type: ignore


@register(
    "cube",
    "runnel, Zhalslar",
    "修改自Zhalslar的魔方插件",
    "1.0.1"
)
class PokeproPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 唤醒前缀
        self.wake_prefix: list[str] = context.get_config().get("wake_prefix", [])
        self.prefix: str =  self.wake_prefix[0] if self.wake_prefix else ""
        # 魔方对象字典
        self.obj_dist: Dict[str, CubeCore] = {}
        # 魔方6面颜色
        self.colors = config.get("colors" , [])
        # 背景颜色
        self.bg_color = config.get("bg_color", "black")
        # 魔方绘制器
        self.drawer = DrawCube(self.colors, self.bg_color)
        # 公式存储
        self.formulas: Dict[str, str] = config.get("formulas", {})

    def _parse_steps(self, input_str: str):
        match = re.match(r"^([FBRLUDfbrlud-]+)(\d*)$", input_str)
        if match:
            steps = match.group(1)
            n = int(match.group(2) or 1)

            # 如果第一个字符是'-'，翻转大小写，否则保持原样
            steps = steps[1:].swapcase() if steps[0] == "-" else steps

            # 返回步骤字符串复制n次
            return steps * n
        return ""

    def _create_cube(self, group_id: str) -> CubeCore:
        """为当前群聊创建一个新的魔方"""
        cube = CubeCore()
        self.obj_dist[group_id] = cube
        return cube

    @filter.command("魔方", alias={"cb"})
    async def start_cube(self, event: AstrMessageEvent):
        """进行魔方游戏"""
        group_id = event.get_group_id()
        input_steps = event.message_str.removeprefix("魔方").removeprefix("cb").strip()
        steps = (
            self.formulas[input_steps]
            if input_steps in self.formulas
            else self._parse_steps(input_steps)
        )
        print(f"魔方输入：{steps}")

        # 魔方初始化
        cube = self.obj_dist.get(group_id) or self._create_cube(group_id)

        # 输入步骤
        raw_status = cube.is_solved()
        cube.rotate(steps)

        # 耗时
        duration = self.get_duration(cube.get_start_time())

        chain = []
        if raw_status is False and cube.is_solved():
            chain.append(Plain(f"还原成功！耗时{duration}"))
            cube.reset()
        elif steps:
            chain.append(Plain(f"操作: {cube.get_last_step()}"))
        elif duration != "00.000" and not cube.is_solved():
            chain.append(Plain(f"当前耗时：{duration}"))

        chain.append(Image.fromBytes(self.drawer.draw(cube.get_cube())))
        yield event.chain_result(chain)

    @filter.command("撤销操作", alias={"cbb"})
    async def back_cube(self, event: AstrMessageEvent):
        """撤销上一步的操作"""
        group_id = event.get_group_id()
        cube = self.obj_dist.get(group_id) or self._create_cube(group_id)

        plain_texts = cube.get_last_step()
        if not plain_texts:
            yield event.plain_result("已撤销为最初状态")
            return

        for plain_text in plain_texts:
            if plain_text.islower():
                cube.rotate(plain_text.upper())
            else:
                cube.rotate(plain_text.lower())

        yield event.chain_result(
            [
                Plain(f"撤销操作: {''.join(plain_texts)}"),
                Image.fromBytes(self.drawer.draw(cube.get_cube())),
            ]
        )

    @filter.command("打乱魔方", alias={"cbk"})
    async def break_cube(self, event: AstrMessageEvent):
        """打乱当前群聊的魔方"""
        group_id = event.get_group_id()
        cube = self.obj_dist.get(group_id) or self._create_cube(group_id)
        cube.reset()
        cube.scramble(1000)
        yield event.chain_result(
            [
                Plain("已打乱本群的魔方"),
                Image.fromBytes(self.drawer.draw(cube.get_cube())),
            ]
        )

    @filter.command("重置魔方", alias={"cbr"})
    async def reset_cube(self, event: AstrMessageEvent):
        """重置当前群聊的魔方"""
        group_id = event.get_group_id()
        cube = self.obj_dist.get(group_id) or self._create_cube(group_id)
        cube.reset()
        yield event.chain_result(
            [
                Plain("已重置本群的魔方"),
                Image.fromBytes(self.drawer.draw(cube.get_cube())),
            ]
        )

    @filter.command("添加公式", alias={"cba"})
    async def add_formula(
        self,
        event: AstrMessageEvent,
        name: str | None = None,
        formula: str | None = None,
    ):
        """添加公式"""
        if not name or not formula:
            yield event.plain_result(f"使用格式：{self.prefix}cba 公式名 公式")
            return
        self.formulas[name] = formula
        yield event.plain_result(f"添加公式成功\n{name}: {formula}")
        self.config.save_config()

    @filter.command("删除公式", alias={"cbd"})
    async def del_formula(self, event: AstrMessageEvent, name: str | None = None):
        """删除公式"""
        if not name:
            yield event.plain_result(f"使用格式：{self.prefix}cbd 公式名")
            return
        yield event.plain_result(f"已删除公式\n{name}: {self.formulas[name]}")
        del self.formulas[name]
        self.config.save_config()

    @filter.command("公式列表", alias={"cbl"})
    async def list_formula(self, event: AstrMessageEvent):
        """列出存储的魔方公式"""
        formulas_str  = "\n".join(
            [f"{name}: {formula}" for name, formula in self.formulas.items()]
        )
        yield event.plain_result(formulas_str)

    @filter.command("魔方帮助", alias={"cbh"})
    async def cube_help(self, event: AstrMessageEvent):
        """魔方帮助"""
        help_text = (
            f"{self.prefix}cb <操作符> - 操作魔方\n"
            "操作符：FfBbLlRrUuDd\n"
            "对应面：前后左右上下\n"
            "大小写：大写顺时针，小写逆时针\n\n"
            f"{self.prefix}cbb - 撤销上一步操作\n"
            f"{self.prefix}cbk - 打乱当前群聊的魔方\n"
            f"{self.prefix}cbr - 重置当前群聊的魔方\n\n"
            f"{self.prefix}cba <公式名> <公式> - 添加魔方公式\n"
            f"{self.prefix}cbd <公式名> - 删除魔方公式\n"
            f"{self.prefix}cbl - 列出存储的魔方公式"
        )
        yield event.plain_result(help_text)

    @staticmethod
    def get_duration(start_time: int) -> str:
        """获取毫秒级耗时(格式化)"""
        duration = int((time.time() * 1000) - start_time)
        seconds, milliseconds = divmod(duration, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        time_parts = []
        if hours > 0:
            time_parts.append(f"{hours:02d}")
        if minutes > 0 or hours > 0:
            time_parts.append(f"{minutes:02d}")
        time_parts.append(f"{seconds:02d}.{milliseconds:03d}")
        return ":".join(time_parts)

