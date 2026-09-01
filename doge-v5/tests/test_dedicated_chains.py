from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

# Production plugins import through data.plugins.*.
data_pkg = types.ModuleType("data")
data_pkg.__path__ = []  # type: ignore[attr-defined]
plugins_pkg = types.ModuleType("data.plugins")
plugins_pkg.__path__ = [str(PLUGINS)]  # type: ignore[attr-defined]
data_pkg.plugins = plugins_pkg  # type: ignore[attr-defined]
sys.modules.setdefault("data", data_pkg)
sys.modules.setdefault("data.plugins", plugins_pkg)

from doge_arena.arena_engine import classic_plan_prompts, draw_legacy
from doge_arena.main import DogeArena
from doge_linguistics.linguistics import CthuvianAdapter
from doge_linguistics.main import DogeLinguistics, _safe_high_english_candidate
from doge_shared.provider_routes import dedicated_deepseek


class _FakeProvider:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies.pop(0) if self.replies else ""
        return SimpleNamespace(completion_text=text)


class _FakeContext:
    def __init__(self, direct=None, openrouter=None, default=None):
        self.direct = direct
        self.openrouter = openrouter
        self.default = default
        self.requested: list[str] = []

    def get_provider_by_id(self, provider_id: str):
        self.requested.append(provider_id)
        if provider_id == "deepseek/deepseek-v4-flash":
            return self.direct
        if provider_id == "openrouter/~deepseek/deepseek-v4-flash-latest":
            return self.openrouter
        return None

    async def get_using_provider_async(self, **kwargs):
        raise AssertionError("dedicated chain must not ask for session default provider")


class DedicatedProviderTests(unittest.TestCase):
    def test_direct_deepseek_is_preferred_and_never_uses_default(self):
        direct = _FakeProvider([])
        ctx = _FakeContext(direct=direct, default=object())
        provider, provider_id = dedicated_deepseek(ctx)
        self.assertIs(provider, direct)
        self.assertEqual(provider_id, "deepseek/deepseek-v4-flash")
        self.assertEqual(ctx.requested, ["deepseek/deepseek-v4-flash"])

    def test_missing_deepseek_does_not_fall_back_to_default(self):
        ctx = _FakeContext(default=object())
        with self.assertRaises(ValueError):
            dedicated_deepseek(ctx)


class ArenaDeepSeekTests(unittest.TestCase):
    def test_old_wp_semantics_are_creatively_planned_then_narrated(self):
        a = draw_legacy(__import__("random").Random(1))
        b = draw_legacy(__import__("random").Random(2))
        system, prompt = classic_plan_prompts("甲", a, "乙", b)
        self.assertIn("字面缝隙", prompt)
        self.assertIn("普通人的行动", system)
        self.assertIn(a.powers[0].description, prompt)
        self.assertIn(b.powers[0].description, prompt)

        fake = _FakeProvider([
            "利用前置条件制造误判；副作用反而封锁路线；最后由普通动作完成反转。",
            "甲先试图触发能力，乙却利用副作用迫使其改线。双方绕着荒诞条件认真周旋，最终普通动作成为决定因素。\n结果：A胜",
        ])
        obj = object.__new__(DogeArena)
        obj.context = _FakeContext(direct=fake)
        result = asyncio.run(obj._deepseek_battle("甲", a, "乙", b))
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("内部战术草案", fake.calls[1]["prompt"])
        self.assertIn("严肃、专业、平静", fake.calls[1]["system_prompt"])
        self.assertIn("荒谬", fake.calls[1]["system_prompt"])
        self.assertTrue(result.endswith("结果：A胜"))


class CthuvianDeepSeekTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = CthuvianAdapter(PLUGINS / "doge_linguistics" / "assets" / "Rlyehian-Cthuvian-Translator")

    def test_candidate_safety_rejects_surface_generation_and_polarity_drift(self):
        self.assertFalse(_safe_high_english_candidate("I know everything", "ph'nglui mglw'nafh"))
        self.assertFalse(_safe_high_english_candidate("I do not know everything", "I know everything"))
        self.assertTrue(_safe_high_english_candidate("I understand everything", "I know everything"))

    def test_high_register_uses_deepseek_only_as_english_proposal_layer(self):
        fake = _FakeProvider(['{"candidate_english":"I know everything"}'])
        obj = object.__new__(DogeLinguistics)
        obj.context = _FakeContext(direct=fake)
        result, meta = asyncio.run(obj._cthuvian_high("I understand everything", self.adapter))
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("MUST NOT output Cthuvian", fake.calls[0]["system_prompt"])
        self.assertTrue(result["roundtrip_ok"])
        self.assertEqual(result["provenance"], "lexicon")
        self.assertEqual(meta["provider_id"], "deepseek/deepseek-v4-flash")
        self.assertEqual(meta["candidate_english"], "I know everything")
        self.assertIn("kadishtu", result["cthuvian"])


if __name__ == "__main__":
    unittest.main()
