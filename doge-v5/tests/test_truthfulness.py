from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from doge_alchemy import __path__ as _alchemy_path  # noqa: F401
from doge_arena.arena_engine import POWERS
from doge_code.executor import LANGUAGES
from doge_linguistics.linguistics import CthuvianAdapter
from doge_shared.alchemy import prompts as alchemy_prompts


class TruthfulnessPolicyTests(unittest.TestCase):
    def test_policy_exactly_covers_default_profile(self):
        manifest = json.loads((ROOT / "plugin_manifest.json").read_text(encoding="utf-8"))
        default = {x["name"] for x in manifest["plugins"] if x.get("default")}
        policy = json.loads((ROOT / "truthfulness_policy.json").read_text(encoding="utf-8"))["plugins"]
        self.assertEqual(set(policy), default)
        for name, item in policy.items():
            self.assertTrue(item.get("kind"), name)
            self.assertTrue(item.get("source"), name)
            self.assertTrue(item.get("fallback"), name)

    def test_no_high_risk_placeholder_markers_in_default_plugin_code(self):
        manifest = json.loads((ROOT / "plugin_manifest.json").read_text(encoding="utf-8"))
        default = {x["name"] for x in manifest["plugins"] if x.get("default")}
        forbidden = ("TODO_IMPLEMENT", "mock_response", "fake_response", "placeholder_result", "占位结果", "示例数据作为结果")
        hits = []
        for name in default:
            for path in (PLUGINS / name).rglob("*.py"):
                if "vendor" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for marker in forbidden:
                    if marker in text:
                        hits.append(f"{path}:{marker}")
        self.assertEqual(hits, [])

    def test_generative_alchemy_declares_fiction(self):
        system, _ = alchemy_prompts("a", "b", [])
        self.assertIn("虚构", system)

    def test_arena_source_is_real_preserved_corpus(self):
        self.assertEqual(len(POWERS), 238)
        self.assertNotIn("局部重力编辑", {x.name for x in POWERS})

    def test_code_executor_is_remote_only_surface(self):
        self.assertIn("python", LANGUAGES)
        main = (PLUGINS / "doge_code" / "main.py").read_text(encoding="utf-8")
        self.assertIn("不会在 Doge 宿主机执行", main)
        self.assertNotIn("subprocess", (PLUGINS / "doge_code" / "executor.py").read_text(encoding="utf-8"))

    def test_cthuvian_unknown_is_not_presented_as_lexicon_translation(self):
        root = PLUGINS / "doge_linguistics" / "assets" / "Rlyehian-Cthuvian-Translator"
        result = CthuvianAdapter(root).translate("quantumfoobarxyz", "low")
        self.assertIn(result["provenance"], {"sealed", "hybrid"})
        self.assertNotEqual(result["provenance"], "lexicon")


if __name__ == "__main__":
    unittest.main()
