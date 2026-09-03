from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

# Production imports use AstrBot's ``data.plugins`` package.  Recreate only
# that namespace for repository tests; the actual modules still come from the
# checked-out plugin tree.
data_pkg = types.ModuleType("data")
data_pkg.__path__ = []  # type: ignore[attr-defined]
plugins_pkg = types.ModuleType("data.plugins")
plugins_pkg.__path__ = [str(PLUGINS)]  # type: ignore[attr-defined]
data_pkg.plugins = plugins_pkg  # type: ignore[attr-defined]
sys.modules.setdefault("data", data_pkg)
sys.modules.setdefault("data.plugins", plugins_pkg)

from doge_core.main import DogeCore, strip_unsolicited_followup


class _Result:
    def __init__(self, llm: bool):
        self.llm = llm
        self.markdown = None

    def is_llm_result(self) -> bool:
        return self.llm

    def use_markdown(self, value):
        self.markdown = value
        return self


class _Event:
    def __init__(self, platform: str, result: _Result):
        self.platform = platform
        self.result = result

    def get_platform_name(self):
        return self.platform

    def get_result(self):
        return self.result


class TransportMarkdownTests(unittest.TestCase):
    def _run(self, platform: str, llm: bool):
        result = _Result(llm)
        event = _Event(platform, result)
        asyncio.run(DogeCore.transport_markdown_result(object(), event))
        return result.markdown

    def test_qq_official_llm_forces_markdown(self):
        self.assertIs(self._run("qq_official", True), True)

    def test_napcat_onebot_forces_plain_text(self):
        self.assertIs(self._run("aiocqhttp", True), False)

    def test_qq_official_non_llm_keeps_plugin_media_choice(self):
        self.assertIsNone(self._run("qq_official", False))

    def test_completed_answer_strips_service_followup_even_when_short(self):
        self.assertEqual(strip_unsolicited_followup("HTTP 200。要不要我继续测？", "测试一下"), "HTTP 200")

    def test_multiple_customer_service_tails_are_stripped(self):
        src = "功能有 A/B。要搜什么或者想看哪个板的热帖，直接说就行啦。 ……呀，你该不会是想去论坛考古什么黑历史吧（"
        self.assertEqual(strip_unsolicited_followup(src, "看看功能"), "功能有 A/B")

    def test_real_clarification_and_explicit_chat_question_are_preserved(self):
        self.assertEqual(strip_unsolicited_followup("这个任务缺少目标文件。请把文件发来。", "帮我改一下"), "这个任务缺少目标文件。请把文件发来。")
        self.assertEqual(strip_unsolicited_followup("那你今天最想聊什么？", "陪我聊一会儿"), "那你今天最想聊什么？")

    def test_closed_turn_removes_directed_social_probe_but_keeps_answer(self):
        self.assertEqual(strip_unsolicited_followup("呀，中午好。吃午饭了没呀？没吃的话先去吃饭。", "中午好"), "呀，中午好")
        self.assertEqual(strip_unsolicited_followup("这件事本身挺有意思。那他看完什么反应？没当场翘尾巴吧。", "我转给他看了"), "这件事本身挺有意思")

    def test_required_directed_clarification_is_kept(self):
        src = "这个报错缺少环境信息，需要你提供一下：你用的是哪个版本？"
        self.assertEqual(strip_unsolicited_followup(src, "帮我修"), src)


if __name__ == "__main__":
    unittest.main()
