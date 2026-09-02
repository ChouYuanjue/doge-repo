from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

import astrbot.api.message_components as Comp

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


class ArenaRoutingTests(unittest.TestCase):
    def test_raw_at_fight_is_detected_even_without_wake_flag(self):
        class Event:
            message_str = "/arena fight"
            is_at_or_wake_command = False
            def get_self_id(self): return "bot"
            def get_messages(self): return [Comp.Plain("/arena fight "), Comp.At(qq="123")]
        self.assertTrue(DogeArena._is_raw_at_battle(Event()))

    def test_raw_fallback_is_narrow(self):
        class Event:
            def __init__(self, text, chain):
                self.message_str = text
                self.chain = chain
            def get_self_id(self): return "bot"
            def get_messages(self): return self.chain
        self.assertFalse(DogeArena._is_raw_at_battle(Event("/arena draw", [Comp.Plain("/arena draw")])))
        self.assertFalse(DogeArena._is_raw_at_battle(Event("/arena fight 123", [Comp.Plain("/arena fight 123")])))
        self.assertFalse(DogeArena._is_raw_at_battle(Event("/arena fight", [Comp.Plain("/arena fight "), Comp.At(qq="bot")])))


class ArenaDeepSeekTests(unittest.TestCase):
    def test_old_wp_semantics_use_one_fast_named_judge_call(self):
        a = draw_legacy(__import__("random").Random(1))
        b = draw_legacy(__import__("random").Random(2))
        system, prompt = classic_plan_prompts("甲", a, "乙", b)
        self.assertIn("字面缝隙", prompt)
        self.assertIn("普通人的行动", system)
        self.assertIn(a.powers[0].description, prompt)
        self.assertIn(b.powers[0].description, prompt)

        fake = _FakeProvider([
            "A先试图触发能力，B却利用副作用迫使其改线。双方绕着荒诞条件认真周旋，最终普通动作成为决定因素。\n结果：A胜",
        ])
        obj = object.__new__(DogeArena)
        obj.context = _FakeContext(direct=fake)
        result = asyncio.run(obj._deepseek_battle("甲", a, "乙", b))
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("严肃、专业、平静", fake.calls[0]["system_prompt"])
        self.assertIn("荒谬", fake.calls[0]["system_prompt"])
        self.assertIn("禁止用A/B", fake.calls[0]["prompt"])
        self.assertIn("甲先", result)
        self.assertIn("乙却", result)
        self.assertTrue(result.endswith("结果：甲胜"))

    def test_ab_cleanup_does_not_corrupt_normal_latin_words(self):
        got = DogeArena._normalize_battle_names(
            "A先行动，B的策略随后生效；BPE 与 ABC 不应被改。\n结果：B胜",
            "小甲",
            "小乙",
        )
        self.assertIn("小甲先行动", got)
        self.assertIn("小乙的策略", got)
        self.assertIn("BPE", got)
        self.assertIn("ABC", got)
        self.assertTrue(got.endswith("结果：小乙胜"))


class CthuvianDeepSeekTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = CthuvianAdapter(PLUGINS / "doge_linguistics" / "assets" / "Rlyehian-Cthuvian-Translator")

    def test_candidate_safety_rejects_surface_generation_and_polarity_drift(self):
        self.assertFalse(_safe_high_english_candidate("I know everything", "ph'nglui mglw'nafh"))
        self.assertFalse(_safe_high_english_candidate("I do not know everything", "I know everything"))
        self.assertTrue(_safe_high_english_candidate("I understand everything", "I know everything"))

    def test_high_register_skips_deepseek_when_already_lexicalized(self):
        obj = object.__new__(DogeLinguistics)
        obj.context = _FakeContext()
        result, meta = asyncio.run(obj._cthuvian_high("I understand everything", self.adapter))
        self.assertTrue(result["roundtrip_ok"])
        self.assertEqual(result["provenance"], "lexicon")
        self.assertEqual(meta["provider_id"], "not_needed")
        self.assertEqual(meta["planner_status"], "not_needed")
        self.assertEqual(meta["candidate_english"], "I understand everything")
        self.assertIn("kadishtu", result["cthuvian"])

    def test_high_register_new_term_is_persisted_reversible_and_reused(self):
        root = PLUGINS / "doge_linguistics" / "assets" / "Rlyehian-Cthuvian-Translator"
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(root, registry)
            proposal = json.dumps({
                "source_term": "quantumwidget",
                "concept_type": "object",
                "selected_roots": [],
                "literal_gloss": "quantumwidget",
                "needs_new_root": True,
                "coined_surface": "zha'thul",
            })
            fake = _FakeProvider([
                '{"candidate_english":"I know quantumwidget"}',
                proposal,
            ])
            obj = object.__new__(DogeLinguistics)
            obj.context = _FakeContext(direct=fake)

            result, meta = asyncio.run(obj._cthuvian_high("I know quantumwidget", adapter))
            self.assertEqual(len(fake.calls), 2)
            self.assertIn("MUST NOT output Cthuvian", fake.calls[0]["system_prompt"])
            self.assertIn("terminology proposal layer", fake.calls[1]["system_prompt"])
            self.assertEqual(result["provenance"], "lexicon")
            self.assertIn("zha'thul", result["cthuvian"])
            self.assertNotIn("'zhro", result["cthuvian"])
            self.assertEqual(adapter.learned_count(), 1)
            self.assertEqual(meta["learned_terms"][0]["source"], "quantumwidget")
            self.assertTrue(registry.exists())

            reloaded = CthuvianAdapter(root, registry)
            self.assertEqual(reloaded.learned_count(), 1)
            self.assertEqual(reloaded.lookup("quantumwidget").rc, "zha'thul")
            self.assertIn("quantumwidget", reloaded.gloss("zha'thul")["best_gloss"])

            second = object.__new__(DogeLinguistics)
            second.context = _FakeContext()
            second_result, second_meta = asyncio.run(second._cthuvian_high("I know quantumwidget", reloaded))
            self.assertEqual(second_result["cthuvian"], result["cthuvian"])
            self.assertEqual(second_meta["planner_status"], "not_needed")
            self.assertEqual(second_meta["provider_id"], "not_needed")
            self.assertEqual(reloaded.learned_count(), 1)

    def test_high_register_never_returns_sealed_when_term_generation_fails(self):
        root = PLUGINS / "doge_linguistics" / "assets" / "Rlyehian-Cthuvian-Translator"
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(root, registry)
            bad = json.dumps({
                "source_term": "quantumwidget",
                "concept_type": "object",
                "selected_roots": [],
                "literal_gloss": "quantumwidget",
                "needs_new_root": True,
                "coined_surface": "quantumwidget",
            })
            fake = _FakeProvider([
                '{"candidate_english":"I know quantumwidget"}',
                bad,
                bad,
                bad,
            ])
            obj = object.__new__(DogeLinguistics)
            obj.context = _FakeContext(direct=fake)
            with self.assertRaisesRegex(ValueError, "永久 RC-1 词条"):
                asyncio.run(obj._cthuvian_high("I know quantumwidget", adapter))
            self.assertEqual(len(fake.calls), 4)
            self.assertFalse(registry.exists())


if __name__ == "__main__":
    unittest.main()
