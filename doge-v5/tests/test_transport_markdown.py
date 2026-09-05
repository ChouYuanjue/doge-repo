from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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

import doge_core.main as core_module
from doge_core.main import DogeCore, strip_unsolicited_followup


class _Result:
    def __init__(self, llm: bool, chain=None):
        self.llm = llm
        self.markdown = None
        self.chain = list(chain or [])

    def is_llm_result(self) -> bool:
        return self.llm

    def is_model_result(self) -> bool:
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

    def get_self_id(self):
        return "10000"


class TransportMarkdownTests(unittest.TestCase):
    def _run(self, platform: str, llm: bool, chain=None):
        result = _Result(llm, chain=chain)
        event = _Event(platform, result)
        core = object.__new__(DogeCore)
        asyncio.run(core.transport_markdown_result(event))
        return result

    def test_qq_official_llm_forces_markdown(self):
        self.assertIs(self._run("qq_official", True).markdown, True)

    def test_napcat_onebot_forces_plain_text(self):
        self.assertIs(self._run("aiocqhttp", True).markdown, False)

    def test_qq_official_non_llm_keeps_plugin_media_choice(self):
        self.assertIsNone(self._run("qq_official", False).markdown)


    def test_shared_history_reader_marks_sqlite_naive_timestamps_as_utc(self):
        class Row:
            created_at = datetime(2026, 9, 5, 2, 55, 0)

        class Manager:
            async def get(self, *args, **kwargs):
                return [Row()]

        manager = Manager()
        core = object.__new__(DogeCore)
        core.context = types.SimpleNamespace(message_history_manager=manager)
        core._normalize_platform_history_timestamps()
        rows = asyncio.run(manager.get(platform_id="napcat", user_id="napcat:GroupMessage:g"))
        self.assertEqual(rows[0].created_at.tzinfo, timezone.utc)
        self.assertTrue(manager._doge_utc_normalized)

    def test_final_reality_anchor_is_unconditional_and_uses_shanghai_time(self):
        class Runtime:
            def reality_anchor(self, local_time):
                return "REALITY " + local_time

        class Event:
            pass

        req = types.SimpleNamespace(system_prompt="base")
        core = object.__new__(DogeCore)
        core.persona_runtime = Runtime()
        asyncio.run(core.finalize_reality_and_time(Event(), req))
        self.assertTrue(req.system_prompt.startswith("base\n\nREALITY "))
        self.assertRegex(req.system_prompt, r"[+-]08:00$")

    def test_completed_answer_strips_service_followup_even_when_short(self):
        self.assertEqual(strip_unsolicited_followup("HTTP 200。要不要我继续测？", "测试一下"), "HTTP 200")

    def test_multiple_customer_service_tails_are_stripped(self):
        src = "功能有 A/B。要搜什么或者想看哪个板的热帖，直接说就行啦。 ……呀，你该不会是想去论坛考古什么黑历史吧（"
        self.assertEqual(strip_unsolicited_followup(src, "看看功能"), "功能有 A/B")

    def test_declarative_missing_info_is_preserved_but_chat_questions_are_removed(self):
        self.assertEqual(strip_unsolicited_followup("这个任务缺少目标文件。请把文件发来。", "帮我改一下"), "这个任务缺少目标文件。请把文件发来。")
        self.assertEqual(strip_unsolicited_followup("那你今天最想聊什么？", "陪我聊一会儿"), "")

    def test_closed_turn_removes_directed_social_probe_but_keeps_answer(self):
        self.assertEqual(strip_unsolicited_followup("呀，中午好。吃午饭了没呀？没吃的话先去吃饭。", "中午好"), "呀，中午好")
        self.assertEqual(strip_unsolicited_followup("这件事本身挺有意思。那他看完什么反应？没当场翘尾巴吧。", "我转给他看了"), "这件事本身挺有意思")

    def test_required_directed_clarification_question_is_not_allowed(self):
        src = "这个报错缺少环境信息，需要你提供一下：你用的是哪个版本？"
        self.assertNotIn("？", strip_unsolicited_followup(src, "帮我修"))
        self.assertEqual(strip_unsolicited_followup("缺少环境信息。哪个版本？", "帮我修"), "缺少环境信息")

    def test_multi_plain_model_result_becomes_one_nodes_component(self):
        from astrbot.api import message_components as Comp
        result = self._run("aiocqhttp", True, [Comp.Plain("第一段。\n\n第二段。")])
        self.assertEqual(len(result.chain), 1)
        self.assertIsInstance(result.chain[0], Comp.Nodes)
        self.assertEqual(len(result.chain[0].nodes), 2)
        self.assertEqual(result.chain[0].nodes[0].content[0].text, "第一段。")
        self.assertEqual(result.chain[0].nodes[1].content[0].text, "第二段。")

    def test_agent_buffered_multiple_plain_components_also_merge(self):
        from astrbot.api import message_components as Comp
        result = self._run("aiocqhttp", True, [Comp.Plain("中间结果"), Comp.Plain("最终结果")])
        self.assertEqual(len(result.chain), 1)
        self.assertIsInstance(result.chain[0], Comp.Nodes)
        self.assertEqual(len(result.chain[0].nodes), 2)

    def test_agent_off_group_is_strictly_command_only(self):
        class GateEvent:
            def __init__(self, text, group="123", original=None):
                self.message_str = text
                self.message_obj = types.SimpleNamespace(message_str=original if original is not None else text)
                self.group = group
                self.unified_msg_origin = "qq:GroupMessage:123"
                self.stopped = False
            def get_group_id(self):
                return self.group
            def stop_event(self):
                self.stopped = True

        async def disabled(_umo):
            return False

        old = core_module.is_agent_enabled
        core_module.is_agent_enabled = disabled
        core = object.__new__(DogeCore)
        try:
            natural = GateEvent("你好")
            asyncio.run(core.enforce_group_agent_switch(natural))
            self.assertTrue(natural.stopped)

            command = GateEvent("math calc 1+1", original="/math calc 1+1")
            asyncio.run(core.enforce_group_agent_switch(command))
            self.assertFalse(command.stopped)

            private = GateEvent("你好", group="")
            asyncio.run(core.enforce_group_agent_switch(private))
            self.assertFalse(private.stopped)
        finally:
            core_module.is_agent_enabled = old

    def test_boundary_gate_never_intercepts_original_slash_command_after_wake_stripping(self):
        class Event:
            message_str = "admin agent on"
            message_obj = types.SimpleNamespace(message_str="/admin agent on")

        async def run():
            event = Event()
            return [item async for item in DogeCore.reject_obvious_boundary_request(object(), event)]

        self.assertEqual(asyncio.run(run()), [])

    def test_agent_reenable_command_survives_wake_prefix_stripping(self):
        class Event:
            unified_msg_origin = "napcat:GroupMessage:g"
            message_str = "admin agent on"  # WakingCheck has already stripped '/'.
            message_obj = types.SimpleNamespace(message_str="/admin agent on")
            stopped = False
            def get_group_id(self): return "g"
            def stop_event(self): self.stopped = True

        async def run(enabled):
            event = Event()
            original = __import__('doge_core.main', fromlist=['is_agent_enabled']).is_agent_enabled
            import doge_core.main as core_mod
            async def fake(_umo): return enabled
            core_mod.is_agent_enabled = fake
            try:
                await DogeCore.enforce_group_agent_switch(object(), event)
            finally:
                core_mod.is_agent_enabled = original
            return event.stopped

        self.assertFalse(asyncio.run(run(False)))



if __name__ == "__main__":
    unittest.main()
