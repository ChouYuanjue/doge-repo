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


class _CthuvianPromptProvider:
    def __init__(self, english: str, proposals: dict[str, str | list[str]] | None = None):
        self.english = english
        self.proposals = dict(proposals or {})
        self.calls: list[dict] = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        prompt = str(kwargs.get("prompt") or "")
        if '"english"' in prompt and "SOURCE:" in prompt:
            return SimpleNamespace(completion_text=json.dumps({"english": self.english}))
        for word, reply in self.proposals.items():
            if f"SOURCE_TERM: {word}\n" not in prompt:
                continue
            if isinstance(reply, list):
                text = reply.pop(0) if reply else ""
            else:
                text = reply
            return SimpleNamespace(completion_text=text)
        return SimpleNamespace(completion_text="")


def _cth_proposal(word: str, surface: str) -> str:
    return json.dumps({
        "source_term": word,
        "concept_type": "abstract",
        "selected_roots": [],
        "literal_gloss": word,
        "needs_new_root": True,
        "coined_surface": surface,
    })


class CthuvianDeepSeekTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = PLUGINS / "doge_linguistics" / "assets" / "Rlyehian-Cthuvian-Translator"

    def _obj(self, fake):
        obj = object.__new__(DogeLinguistics)
        obj.context = _FakeContext(direct=fake)
        return obj

    def test_high_register_uses_model_only_as_english_bridge_when_words_are_known(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            fake = _CthuvianPromptProvider("blue hidden city")
            result, meta = asyncio.run(self._obj(fake)._cthuvian_high("blue hidden city", adapter))
            self.assertEqual(len(fake.calls), 1)
            self.assertIn("literal translation gateway", fake.calls[0]["system_prompt"])
            self.assertIn("Do not simplify for downstream grammar", fake.calls[0]["system_prompt"])
            self.assertEqual(meta["english_source"], "blue hidden city")
            self.assertTrue(meta["word_level"])
            self.assertFalse(meta["fallback"])
            self.assertEqual(result["provenance"], "lexicon")
            self.assertEqual(result["sealed_tokens"], 0)
            self.assertEqual(result["words"], ["blue", "hidden", "city"])
            self.assertNotIn("'zhro", result["cthuvian"])
            self.assertFalse(registry.exists())

    def test_high_register_new_word_is_persisted_then_reused_without_term_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            fake = _CthuvianPromptProvider(
                "I know quantumwidget",
                {"quantumwidget": _cth_proposal("quantumwidget", "zha'thul")},
            )
            result, meta = asyncio.run(self._obj(fake)._cthuvian_high("I know quantumwidget", adapter))
            self.assertEqual(len(fake.calls), 2)
            term_calls = [x for x in fake.calls if "SOURCE_TERM:" in str(x.get("prompt") or "")]
            self.assertEqual(len(term_calls), 1)
            self.assertIn("SOURCE_TERM: quantumwidget\n", term_calls[0]["prompt"])
            self.assertIn("exactly one English lexical token", term_calls[0]["system_prompt"])
            self.assertEqual(result["sealed_tokens"], 0)
            self.assertIn("zha'thul", result["cthuvian"])
            self.assertEqual(adapter.learned_count(), 1)
            self.assertEqual(meta["generated_words"][0]["source"], "quantumwidget")

            reloaded = CthuvianAdapter(self.root, registry)
            fake2 = _CthuvianPromptProvider("I know quantumwidget")
            result2, meta2 = asyncio.run(self._obj(fake2)._cthuvian_high("I know quantumwidget", reloaded))
            self.assertEqual(len(fake2.calls), 1)  # English bridge only.
            self.assertEqual(result2["cthuvian"], result["cthuvian"])
            self.assertEqual(meta2["generated_words"], [])
            self.assertEqual(reloaded.learned_count(), 1)
            self.assertIn("quantumwidget", reloaded.gloss("zha'thul")["best_gloss"])

    def test_high_register_classic_sentence_generates_only_missing_words_individually(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            source = "In his house at R'lyeh, dead Cthulhu waits dreaming."
            self.assertEqual(adapter.high_missing_words(source), ("his", "dreaming"))
            fake = _CthuvianPromptProvider(source, {
                "his": _cth_proposal("his", "qth'vra"),
                "dreaming": _cth_proposal("dreaming", "zha'thul"),
            })
            result, meta = asyncio.run(self._obj(fake)._cthuvian_high(source, adapter))
            term_calls = [x for x in fake.calls if "SOURCE_TERM:" in str(x.get("prompt") or "")]
            self.assertEqual(len(fake.calls), 3)  # one English bridge + two per-word proposals
            self.assertEqual(len(term_calls), 2)
            prompts = [str(x["prompt"]) for x in term_calls]
            self.assertTrue(any("SOURCE_TERM: his\n" in x for x in prompts))
            self.assertTrue(any("SOURCE_TERM: dreaming\n" in x for x in prompts))
            self.assertFalse(any("SOURCE_TERM: his house" in x or "SOURCE_TERM: waits dreaming" in x for x in prompts))
            self.assertEqual({x["source"] for x in meta["generated_words"]}, {"his", "dreaming"})
            self.assertEqual(adapter.learned_count(), 2)
            self.assertEqual(result["sealed_tokens"], 0)
            self.assertNotIn("'zhro", result["cthuvian"])
            self.assertIn("R'lyeh", result["cthuvian"])
            self.assertIn("Cthulhu", result["cthuvian"])
            self.assertIn("fhtagn", result["cthuvian"])

    def test_high_register_generation_failure_is_hard_error_and_registry_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            bad = _cth_proposal("quantumwidget", "quantumwidget")
            fake = _CthuvianPromptProvider("frobnicator quantumwidget", {
                "frobnicator": _cth_proposal("frobnicator", "qth'vra"),
                "quantumwidget": [bad, bad, bad],
            })
            before = adapter.learned_bytes()
            with self.assertRaisesRegex(ValueError, "term generation failed for quantumwidget"):
                asyncio.run(self._obj(fake)._cthuvian_high("frobnicator quantumwidget", adapter))
            self.assertEqual(adapter.learned_count(), 0)
            self.assertEqual(adapter.learned_bytes(), before)
            self.assertFalse(registry.exists())

    def test_multilingual_input_is_translated_by_model_then_enters_same_word_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "learned-registry.json"
            adapter = CthuvianAdapter(self.root, registry)
            fake = _CthuvianPromptProvider("blue hidden city")
            result, meta = asyncio.run(self._obj(fake)._cthuvian_high("蓝色的隐藏城市", adapter))
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(meta["source_text"], "蓝色的隐藏城市")
            self.assertEqual(meta["english_source"], "blue hidden city")
            self.assertEqual(result["words"], ["blue", "hidden", "city"])
            self.assertEqual(result["sealed_tokens"], 0)
            self.assertFalse(registry.exists())


if __name__ == "__main__":
    unittest.main()
