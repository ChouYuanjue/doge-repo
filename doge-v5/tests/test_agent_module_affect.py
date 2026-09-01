from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from doge_shared.affect import TransientAffect
from doge_shared.agent_bridge import DogeCapabilitySearchTool, DogeCapabilityTool, DogePresentTool, _likely_help, _normalize_command
from doge_shared.capabilities import agent_capability_prompt, search_capabilities
from doge_shared.module_control import available_doge_plugins, is_group_admin, resolve_module
from doge_shared.persona_runtime import PersonaRuntime


class AffectTests(unittest.TestCase):
    def test_affect_moves_and_recovers_without_becoming_long_term(self):
        affect = TransientAffect(half_life_s=100.0, ttl_s=500.0)
        state = affect.observe("g", "豆子你真可爱", now=100.0)
        self.assertGreater(state.valence, 0)
        self.assertIn(affect.label(state), {"略微愉快", "心情不错"})

        state = affect.observe("g", "豆子你真蠢", now=101.0)
        self.assertLess(state.valence, 0)
        self.assertIn(affect.label(state), {"微恼", "有点生气"})

        recovered = affect.observe("g", "抱歉，刚才我语气有点冲", now=102.0)
        self.assertGreater(recovered.valence, state.valence)
        self.assertLessEqual(recovered.arousal, state.arousal)

        neutral = affect.observe("g", "继续看代码", now=1000.0)
        self.assertAlmostEqual(neutral.valence, 0.0, delta=0.05)
        self.assertAlmostEqual(neutral.arousal, 0.0, delta=0.05)

    def test_technical_negative_words_do_not_count_as_personal_insult(self):
        affect = TransientAffect()
        state = affect.observe("g", "这个垃圾数据和蠢算法得重做", now=100.0)
        self.assertGreater(state.valence, -0.05)


class PersonaRuntimeTests(unittest.TestCase):
    def test_configured_closest_sender_is_always_maximally_familiar(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect, closest_sender_ids={"close-user"})
        close_scope = "group|sender:close-user"
        other_scope = "group|sender:other-user"
        close_state = affect.observe(close_scope, "今天陪我聊一会儿", now=100.0)
        other_state = affect.observe(other_scope, "今天陪我聊一会儿", now=100.0)
        close = runtime.cue(close_scope, "今天陪我聊一会儿", close_state)
        other = runtime.cue(other_scope, "今天陪我聊一会儿", other_state)
        self.assertTrue(close.closest)
        self.assertEqual(close.familiarity, 1.0)
        self.assertGreaterEqual(close.warmth, .86)
        self.assertGreaterEqual(close.playfulness, .62)
        self.assertLess(close.restraint, other.restraint)

        serious = runtime.cue(close_scope, "生产服务器错误继续查", close_state)
        self.assertTrue(serious.closest)
        self.assertGreaterEqual(serious.warmth, .82)
        self.assertGreaterEqual(serious.persona_strength, .55)
        self.assertLess(serious.persona_strength, close.persona_strength)

    def test_style_is_continuous_and_task_dependent(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect)
        calm = affect.observe("u", "继续看一下", now=100.0)
        serious = runtime.cue("u", "这个 CI 错误继续查", calm)
        casual = runtime.cue("v", "今天陪我玩会儿", calm)
        self.assertLess(serious.persona_strength, casual.persona_strength)
        self.assertGreater(serious.restraint, casual.restraint)
        self.assertGreater(casual.playfulness, serious.playfulness)

    def test_familiarity_thaws_warmth_without_storing_message_content(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect)
        state = affect.observe("u", "正常聊天", now=100.0)
        first = runtime.cue("u", "随便聊聊", state)
        for _ in range(20):
            runtime.prompt("u", "正常聊天", state)
        later = runtime.cue("u", "随便聊聊", state)
        self.assertGreater(later.familiarity, first.familiarity)
        self.assertGreater(later.warmth, first.warmth)
        self.assertTrue(all(not hasattr(v, "text") for v in runtime._relationships.values()))

    def test_strategic_child_act_is_rare_permission_and_never_serious(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect)
        state = affect.observe("p", "正常聊天", now=100.0)
        opened = [f"scope-{i}" for i in range(1024) if runtime._rare_gate(f"scope-{i}", "把截图发给你，哄我一下")]
        self.assertGreater(len(opened), 0)
        self.assertLess(len(opened), 50)
        cue = runtime.cue(opened[0], "把截图发给你，哄我一下", state)
        self.assertTrue(cue.child_act_allowed)
        serious = runtime.cue(opened[0], "生产服务器错误，把截图发给你", state)
        self.assertFalse(serious.child_act_allowed)

    def test_closest_casual_texture_is_warm_but_not_fixed_catchphrase(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect, closest_sender_ids={"close-user"})
        scope = "group|sender:close-user"
        state = affect.observe(scope, "陪我聊一会儿", now=100.0)
        p1 = runtime.prompt(scope, "陪我聊一会儿", state)
        p2 = runtime.prompt(scope, "我回来啦", state)
        self.assertIn("最亲近的关系档", p1)
        self.assertIn("空括号", p1)
        self.assertIn("小口癖只有", p1)
        self.assertNotEqual(p1.split("小口癖只有：", 1)[1][:12], p2.split("小口癖只有：", 1)[1][:12])

    def test_self_reality_questions_use_human_device_interpretation(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect, closest_sender_ids={"close-user"})
        scope = "group|sender:close-user"
        state = affect.observe(scope, "你住服务器里吗", now=100.0)
        prompt = runtime.prompt(scope, "你住服务器里吗", state)
        self.assertIn("服务器当你使用的设备", prompt)
        self.assertIn("不会/没装/这次做不了", prompt)
        self.assertIn("保留隐私", prompt)


    def test_identity_mapping_is_private_and_stable_id_authoritative(self):
        # The public schema exposes only the mechanism; real IDs stay runtime-private.
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "plugins" / "doge_core" / "_conf_schema.json").read_text(encoding="utf-8"))
        self.assertIn("known_sender_identities", schema)
        self.assertEqual(schema["known_sender_identities"]["default"], {})
        source = (root / "plugins" / "doge_core" / "main.py").read_text(encoding="utf-8")
        self.assertIn("Stable sender ID", source)
        self.assertIn("nicknames are mutable", source)
        self.assertIn("Do not treat a nickname change as a new person", source)
        self.assertIn("explicitly asked to inspect their QQ/sender ID", source)
        self.assertIn("do not infer that someone is a newcomer", source)

    def test_runtime_prompt_is_short_example_driven_not_role_chain(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect)
        state = affect.observe("u", "豆子你真可爱", now=100.0)
        prompt = runtime.prompt("u", "夸你一句，你今天挺可爱的", state)
        self.assertLess(len(prompt), 800)
        self.assertIn("参考下面两段", prompt)
        self.assertIn("豆子：", prompt)
        for marker in ("Anchoring", "Selecting", "Bounding", "Enacting"):
            self.assertNotIn(marker, prompt)


class AgentBridgeMetadataTests(unittest.TestCase):
    def test_bridge_tools_are_explicit_and_media_is_deferred(self):
        search = DogeCapabilitySearchTool()
        capability = DogeCapabilityTool()
        present = DogePresentTool()
        self.assertEqual(search.name, "doge_capability_search")
        self.assertEqual(capability.name, "doge_capability")
        self.assertEqual(present.name, "doge_present")
        self.assertIn("自然语言检索", search.description)
        self.assertIn("正式指令", capability.description)
        self.assertIn("精选", present.description)
        self.assertEqual(_normalize_command("math oeis 1,1,2,3"), "/math oeis 1,1,2,3")
        self.assertEqual(_likely_help("/math oeis"), "/help math oeis")

    def test_agent_inventory_is_compact_and_leaf_details_are_searchable(self):
        prompt = agent_capability_prompt()
        self.assertLess(len(prompt), 3500)
        self.assertIn("doge_capability_search", prompt)
        self.assertIn("/math", prompt)
        self.assertIn("/lang", prompt)
        self.assertNotIn("/media trace anime", prompt)
        tangut = search_capabilities("西夏文翻译", 6)
        self.assertTrue(any(x["id"] == "lang.tangut.t2zh" for x in tangut))
        self.assertTrue(any(x["id"] == "lang.tangut.zh2t" for x in tangut))
        life = search_capabilities("生命游戏 gif", 3)
        self.assertEqual(life[0]["id"], "lab.life")
        cif = search_capabilities("CIF 晶体", 3)
        self.assertTrue(cif[0].get("inputs"))
        fourier = search_capabilities("用傅立叶画图", 3)
        self.assertEqual(fourier[0]["id"], "fourier.image")
        self.assertGreater(fourier[0]["score"], 20)


class ModuleControlTests(unittest.TestCase):
    @staticmethod
    def _context():
        stars = [
            SimpleNamespace(name="doge_core", reserved=False, desc="core"),
            SimpleNamespace(name="doge_admin", reserved=False, desc="admin"),
            SimpleNamespace(name="doge_games", reserved=False, desc="games"),
            SimpleNamespace(name="doge_playground", reserved=False, desc="lab"),
            SimpleNamespace(name="doge_legacy", reserved=False, desc="legacy"),
            SimpleNamespace(name="other_plugin", reserved=False, desc="other"),
        ]
        return SimpleNamespace(get_all_stars=lambda: stars)

    def test_module_resolution_uses_loaded_formal_plugins_only(self):
        ctx = self._context()
        available = available_doge_plugins(ctx)
        self.assertEqual(set(available), {"doge_core", "doge_admin", "doge_games", "doge_playground"})
        self.assertEqual(resolve_module(ctx, "games"), "doge_games")
        self.assertEqual(resolve_module(ctx, "lab"), "doge_playground")
        self.assertIsNone(resolve_module(ctx, "legacy"))
        self.assertIsNone(resolve_module(ctx, "other_plugin"))

    def test_group_admin_is_checked_from_actual_group_membership(self):
        group = SimpleNamespace(group_owner="100", group_admins=["200", 201])

        class Event:
            message_obj = SimpleNamespace(group=None)

            def __init__(self, uid):
                self.uid = uid

            def get_group_id(self):
                return "300"

            def get_sender_id(self):
                return self.uid

            async def get_group(self):
                return group

        self.assertTrue(asyncio.run(is_group_admin(Event("100"))))
        self.assertTrue(asyncio.run(is_group_admin(Event("200"))))
        self.assertTrue(asyncio.run(is_group_admin(Event("201"))))
        self.assertFalse(asyncio.run(is_group_admin(Event("999"))))


if __name__ == "__main__":
    unittest.main()
