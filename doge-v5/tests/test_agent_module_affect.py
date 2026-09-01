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
from doge_shared.agent_bridge import DogeCapabilityTool, DogePresentTool, _likely_help, _normalize_command
from doge_shared.capabilities import agent_capability_prompt
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
    def test_scene_modes_are_contextual_not_one_fixed_voice(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect)
        calm = affect.observe("u", "继续看一下", now=100.0)
        self.assertEqual(runtime.cue("u", "这个 CI 错误继续查", calm).scene, "analytical")
        self.assertEqual(runtime.cue("u", "我这次真的搞砸了，好难受", calm).scene, "quiet-care")
        happy = affect.observe("p", "豆子你真可爱", now=100.0)
        self.assertEqual(runtime.cue("p", "哈哈你今天挺可爱", happy).scene, "playful")

    def test_strategic_child_act_is_rare_permission_and_never_serious(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect)
        state = affect.observe("p", "正常聊天", now=100.0)
        # The deterministic gate should open for some scopes, but remain rare.
        opened = [f"scope-{i}" for i in range(512) if runtime._rare_gate(f"scope-{i}", "把截图发给你，哄我一下")]
        self.assertGreater(len(opened), 0)
        self.assertLess(len(opened), 40)
        cue = runtime.cue(opened[0], "把截图发给你，哄我一下", state)
        self.assertTrue(cue.child_act_allowed)
        serious = runtime.cue(opened[0], "生产服务器错误，把截图发给你", state)
        self.assertFalse(serious.child_act_allowed)

    def test_runtime_prompt_uses_role_chain_and_anti_caricature_bounds(self):
        affect = TransientAffect()
        runtime = PersonaRuntime(affect)
        state = affect.observe("u", "继续", now=100.0)
        prompt = runtime.prompt("u", "继续", state)
        for marker in ("Anchoring", "Selecting", "Bounding", "Enacting"):
            self.assertIn(marker, prompt)
        self.assertIn("客服腔", prompt)
        self.assertIn("固定口癖轮播", prompt)


class AgentBridgeMetadataTests(unittest.TestCase):
    def test_bridge_tools_are_explicit_and_media_is_deferred(self):
        capability = DogeCapabilityTool()
        present = DogePresentTool()
        self.assertEqual(capability.name, "doge_capability")
        self.assertEqual(present.name, "doge_present")
        self.assertIn("完整", capability.description)
        self.assertIn("精选", present.description)
        self.assertEqual(_normalize_command("math oeis 1,1,2,3"), "/math oeis 1,1,2,3")
        self.assertEqual(_likely_help("/math oeis"), "/help math oeis")

    def test_agent_inventory_mentions_required_attachment_channels(self):
        prompt = agent_capability_prompt()
        self.assertIn("/media trace anime", prompt)
        self.assertIn("requires same-message input: <图片附件>", prompt)
        self.assertIn("/mat crystal info", prompt)
        self.assertIn("<CIF/mCIF 文件附件>", prompt)
        self.assertIn("doge_present", prompt)


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
