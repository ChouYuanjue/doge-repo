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
from doge_linguistics.main import DogeLinguistics
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


class _CthuvianBatchProvider:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(completion_text=self.replies.pop(0) if self.replies else "")


def _batch(*items: dict) -> str:
    return json.dumps({"x": list(items)})


def _coin(surface: str) -> dict:
    return {"r": [], "c": surface}


class CthuvianDeepSeekTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = PLUGINS / "doge_linguistics" / "assets" / "Rlyehian-Cthuvian-Translator"

    def _obj(self, fake):
        obj = object.__new__(DogeLinguistics)
        obj.context = _FakeContext(direct=fake)
        return obj

    def test_known_high_words_need_zero_extra_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = CthuvianAdapter(self.root, Path(tmp) / "learned-registry.json")
            fake = _CthuvianBatchProvider([])
            obj = self._obj(fake)
            result, meta = asyncio.run(obj._cthuvian_high("blue hidden city", adapter))
            self.assertEqual(fake.calls, [])
            self.assertEqual(obj.context.requested, [])
            self.assertIsNone(meta["provider_id"])
            self.assertTrue(meta["batched_generation"])
            self.assertEqual(result["provenance"], "lexicon")
            self.assertEqual(result["sealed_tokens"], 0)
            self.assertEqual(result["words"], ["blue", "hidden", "city"])

    def test_one_missing_word_is_one_batch_request_and_then_reused_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            fake = _CthuvianBatchProvider([_batch(_coin("zha'thul"))])
            obj = self._obj(fake)
            result, meta = asyncio.run(obj._cthuvian_high("I know quantumwidget", adapter))
            self.assertEqual(len(fake.calls), 1)
            call = fake.calls[0]
            self.assertIn('w=["quantumwidget"]', call["prompt"])
            self.assertIn('JSON only {"x":[{"r":[],"c":""}]}', call["system_prompt"])
            self.assertLessEqual(call["max_tokens"], 96)
            self.assertLess(len(call["system_prompt"]) + len(call["prompt"]), 1400)
            self.assertEqual(call["request_max_retries"], 1)
            self.assertEqual(call["thinking"], {"type": "disabled"})
            self.assertEqual(call["response_format"], {"type": "json_object"})
            self.assertEqual(result["sealed_tokens"], 0)
            self.assertIn("zha'thul", result["cthuvian"])
            self.assertEqual(meta["generated_words"][0]["source"], "quantumwidget")
            self.assertEqual(adapter.learned_count(), 1)

            reloaded = CthuvianAdapter(self.root, registry)
            fake2 = _CthuvianBatchProvider([])
            obj2 = self._obj(fake2)
            result2, meta2 = asyncio.run(obj2._cthuvian_high("I know quantumwidget", reloaded))
            self.assertEqual(fake2.calls, [])
            self.assertEqual(obj2.context.requested, [])
            self.assertEqual(result2["cthuvian"], result["cthuvian"])
            self.assertEqual(meta2["generated_words"], [])
            self.assertIn("quantumwidget", reloaded.gloss("zha'thul")["best_gloss"])

    def test_classic_sentence_batches_all_missing_words_once_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            source = "In his house at R'lyeh, dead Cthulhu waits dreaming."
            self.assertEqual(adapter.high_missing_words(source), ("his", "dreaming"))
            fake = _CthuvianBatchProvider([_batch(_coin("qth'vra"), _coin("zha'thul"))])
            result, meta = asyncio.run(self._obj(fake)._cthuvian_high(source, adapter))
            self.assertEqual(len(fake.calls), 1)
            call = fake.calls[0]
            self.assertIn('w=["his","dreaming"]', call["prompt"])
            self.assertEqual(call["prompt"].count("roots="), 1)
            self.assertLess(len(call["system_prompt"]) + len(call["prompt"]), 1500)
            self.assertEqual({x["source"] for x in meta["generated_words"]}, {"his", "dreaming"})
            self.assertEqual(adapter.learned_count(), 2)
            self.assertEqual(result["sealed_tokens"], 0)
            self.assertNotIn("'zhro", result["cthuvian"])
            self.assertIn("R'lyeh", result["cthuvian"])
            self.assertIn("Cthulhu", result["cthuvian"])
            self.assertIn("fhtagn", result["cthuvian"])

    def test_partial_batch_retries_only_rejected_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            fake = _CthuvianBatchProvider([
                _batch(_coin("qth'vra"), _coin("quantumwidget")),
                _batch(_coin("zha'thul")),
            ])
            result, meta = asyncio.run(self._obj(fake)._cthuvian_high("frobnicator quantumwidget", adapter))
            self.assertEqual(len(fake.calls), 2)
            self.assertIn('w=["frobnicator","quantumwidget"]', fake.calls[0]["prompt"])
            self.assertIn('w=["quantumwidget"]', fake.calls[1]["prompt"])
            self.assertNotIn('w=["frobnicator","quantumwidget"]', fake.calls[1]["prompt"])
            self.assertIn("reject=", fake.calls[1]["prompt"])
            self.assertEqual({x["source"] for x in meta["generated_words"]}, {"frobnicator", "quantumwidget"})
            self.assertEqual(adapter.learned_count(), 2)
            self.assertEqual(result["sealed_tokens"], 0)

    def test_batch_failure_is_hard_error_and_registry_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            bad = _coin("quantumwidget")
            fake = _CthuvianBatchProvider([
                _batch(_coin("qth'vra"), bad),
                _batch(bad),
            ])
            before = adapter.learned_bytes()
            with self.assertRaisesRegex(ValueError, "batch term generation failed"):
                asyncio.run(self._obj(fake)._cthuvian_high("frobnicator quantumwidget", adapter))
            self.assertEqual(len(fake.calls), 2)
            self.assertEqual(adapter.learned_count(), 0)
            self.assertEqual(adapter.learned_bytes(), before)
            self.assertFalse(registry.exists())

    def test_compact_root_reply_expands_into_deterministic_semantic_compound(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            fake = _CthuvianBatchProvider([_batch({"r": ["FMAGL"], "c": ""})])
            result, meta = asyncio.run(self._obj(fake)._cthuvian_high("frobnicator", adapter))
            self.assertEqual(result["cthuvian"], "fmagl")
            self.assertEqual(meta["generated_words"][0]["strategy"], "semantic_compound")
            self.assertEqual(adapter.lookup("frobnicator").rc, "fmagl")

    def test_non_english_formal_input_is_rejected_without_provider_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = CthuvianAdapter(self.root, Path(tmp) / "learned-registry.json")
            fake = _CthuvianBatchProvider([])
            obj = self._obj(fake)
            with self.assertRaisesRegex(ValueError, "只接收英文"):
                asyncio.run(obj._cthuvian_high("蓝色的隐藏城市", adapter))
            self.assertEqual(fake.calls, [])
            self.assertEqual(obj.context.requested, [])

    def test_registry_tells_agent_to_translate_itself_before_cthuvian_command(self):
        registry = json.loads((PLUGINS / "doge_shared" / "resources" / "capability_registry.json").read_text())
        high = next(x for x in registry["operations"] if x.get("id") == "lang.cthuvian.high")
        notes = str(high.get("agent_notes") or "")
        self.assertIn("Agent", notes)
        self.assertIn("自己", notes)
        self.assertIn("英文", notes)
        self.assertIn("不额外调用", notes)


if __name__ == "__main__":
    unittest.main()
