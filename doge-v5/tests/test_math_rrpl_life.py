from __future__ import annotations

import sys
import tempfile
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from doge_shared.capabilities import agent_capability_prompt, operation_by_id, registry, search_capabilities
from doge_shared.help_service import render_help
from doge_shared.lookup import LookupService
from doge_shared.services import MathService
from doge_shared.visual_lab_fun import life, life_stateful
from doge_linguistics.rrpl_py import RRPL_SYNTAX_GUIDE, explain


class AnimatedLifeTests(unittest.TestCase):
    def test_life_is_real_animated_gif(self):
        with tempfile.TemporaryDirectory() as td:
            path, caption = life(Path(td), "glider", 30)
            self.assertEqual(path.suffix, ".gif")
            self.assertIn("GIF", caption)
            with Image.open(path) as im:
                self.assertEqual(im.format, "GIF")
                self.assertTrue(im.is_animated)
                self.assertGreater(im.n_frames, 10)


class RrplGuidanceTests(unittest.TestCase):
    def test_syntax_guide_teaches_actual_language(self):
        for marker in ("0..8", "A-B", "A|B", "GROUPING", "REFERENCES", "廿|468|由|(八)"):
            self.assertIn(marker, RRPL_SYNTAX_GUIDE)

    def test_explain_expands_and_parses(self):
        out = explain("(48|37)-(25678|27)-(37|15)", ROOT / "plugins" / "doge_linguistics" / "assets" / "rrpl.json")
        self.assertIn("packing leaves: 6", out)
        self.assertIn("stroke segments:", out)

    def test_registry_and_agent_receive_rrpl_grammar(self):
        self.assertIsNotNone(operation_by_id("lang.rrpl.syntax"))
        self.assertIsNotNone(operation_by_id("lang.rrpl.explain"))
        prompt = agent_capability_prompt()
        self.assertIn("RRPL", prompt)
        self.assertIn("doge_capability_search", prompt)
        results = search_capabilities("RRPL 语法", 5)
        self.assertEqual(results[0]["id"], "lang.rrpl.syntax")
        syntax = results[0]
        joined = str(syntax)
        self.assertIn("/lang rrpl syntax", joined)
        self.assertIn("优先读取此语法说明", joined)
        # The full grammar is fetched by executing the syntax capability rather
        # than being duplicated into every Agent request/search result.
        self.assertIn("A-B", RRPL_SYNTAX_GUIDE)
        self.assertIn("A|B", RRPL_SYNTAX_GUIDE)


class MathExpansionTests(unittest.TestCase):
    def test_symbolic_algebra_and_calculus(self):
        self.assertEqual(MathService.expand("(x+1)^3"), "x**3 + 3*x**2 + 3*x + 1")
        self.assertEqual(MathService.factor("x^4-1"), "(x - 1)*(x + 1)*(x**2 + 1)")
        self.assertEqual(MathService.solve("x^2-5*x+6=0", "x"), "x = 2, 3")
        self.assertEqual(MathService.diff("sin(x)", "x", 1), "cos(x)")
        self.assertEqual(MathService.integrate("sin(x)", "x", "0", "pi"), "2")
        self.assertEqual(MathService.limit("sin(x)/x", "x", "0"), "1")

    def test_number_theory_and_stats(self):
        self.assertEqual(MathService.factorint(360), "2^3 × 3^2 × 5")
        self.assertIn("2147483647 是素数", MathService.prime(2147483647))
        stats = MathService.stats([1, 2, 3, 4, 10])
        self.assertIn("mean=4", stats)
        self.assertIn("median=3", stats)

    def test_symbolic_parser_rejects_python_surface(self):
        with self.assertRaises(ValueError):
            MathService.simplify("__import__('os').system('id')")
        with self.assertRaises(ValueError):
            MathService.simplify("x.__class__")

    def test_life_rules_boundaries_and_custom_initial_states_execute(self):
        from doge_shared.visual_lab_fun import _life_rule, _life_step, _life_rle_points, life
        import numpy as np
        birth, survive, name = _life_rule("B36/S23")
        self.assertEqual(name, "B36/S23")
        # A blinker flips orientation under Conway; verify the rule engine itself.
        a = np.zeros((7, 7), dtype=bool); a[3,2:5] = True
        b = _life_step(a, frozenset({3}), frozenset({2,3}), "dead")
        self.assertTrue(b[2:5,3].all()); self.assertEqual(int(b.sum()), 3)
        # RLE is the standard glider body.
        self.assertEqual(len(_life_rle_points("rle:bo$2bo$3o!")), 5)
        with TemporaryDirectory() as td:
            for args in (
                ("blinker", 4, "B3/S23", "dead", 81),
                ("rle:bo$2bo$3o!", 6, "B36/S23", "wrap", 81),
                ("cells:0,0;1,0;2,0", 4, "B3/S23", "dead", 81),
            ):
                path, caption = life(Path(td), *args)
                self.assertTrue(path.exists()); self.assertGreater(path.stat().st_size, 1000)
                self.assertIn("真实模拟", caption)
                path.unlink()

    def test_life_continuation_matches_one_shot_exactly(self):
        import numpy as np
        with TemporaryDirectory() as td:
            p1, _c1, board5, rule, boundary = life_stateful(Path(td), "glider", 5, "B3/S23", "wrap", 81)
            p2, c2, board12, rule2, boundary2 = life_stateful(
                Path(td), "glider", 7, rule, boundary, 81,
                initial=board5, seed_label="glider", generation_offset=5,
            )
            p3, _c3, direct12, _r3, _b3 = life_stateful(Path(td), "glider", 12, "B3/S23", "wrap", 81)
            self.assertTrue(np.array_equal(board12, direct12))
            self.assertEqual((rule2, boundary2), ("B3/S23", "wrap"))
            self.assertIn("generation 12", c2)
            for pth in (p1, p2, p3): pth.unlink(missing_ok=True)

    def test_life_session_state_persists_across_store_instances(self):
        import numpy as np
        from doge_shared.life_state import LifeSessionStore
        key = "napcat:GroupMessage:life-test-group"
        with TemporaryDirectory() as td:
            board = np.zeros((81,81), dtype=bool); board[40,39:42] = True
            LifeSessionStore(Path(td)).save(key, board, rule="B3/S23", boundary="wrap", label="blinker", generation=42)
            state = LifeSessionStore(Path(td)).load(key)
            self.assertIsNotNone(state)
            self.assertTrue(np.array_equal(state["board"], board))
            self.assertEqual((state["rule"], state["boundary"], state["generation"]), ("B3/S23", "wrap", 42))
            self.assertTrue(LifeSessionStore(Path(td)).clear(key))
            self.assertIsNone(LifeSessionStore(Path(td)).load(key))

    def test_life_current_status_query_is_grounded_in_registry(self):
        results = search_capabilities("你的生命游戏完善了吗", 4)
        self.assertEqual(results[0]["id"], "lab.life")
        text = str(results[0])
        for marker in ("自定义初态", "5000", "B36/S23", "wrap", "continue"):
            self.assertIn(marker, text)
        resume = search_capabilities("生命游戏接着上次继续跑", 4)
        self.assertTrue(any(x["id"] == "lab.life.continue" for x in resume))

    def test_life_rejects_bad_rule_and_boundary(self):
        from doge_shared.visual_lab_fun import FunLabError, _life_rule, life
        with self.assertRaises(FunLabError): _life_rule("B9/S23")
        with TemporaryDirectory() as td:
            with self.assertRaises(FunLabError): life(Path(td), "glider", 3, "B3/S23", "mirror", 81)

    def test_math_and_lab_have_explicit_product_boundary(self):
        r = registry()
        self.assertIn("精确/符号", r["commands"]["math"]["summary"])
        self.assertIn("可视化、模拟", r["commands"]["lab"]["summary"])
        math_help, _ = render_help("math")
        self.assertIn("/math solve", math_help)
        self.assertIn("formal", math_help)
        formal_help, _ = render_help("math formal")
        self.assertIn("/math formal lean", formal_help)
        self.assertIn("/math formal coq", formal_help)
        self.assertIn("/math formal rzk", formal_help)
        self.assertIn("/math wa", math_help)
        lab_help, _ = render_help("lab life")
        self.assertIn("动态 GIF", lab_help)

    def test_formal_is_explicitly_lightweight_not_fake_verification(self):
        lean = MathService.formal("lean", "example : 1 + 1 = 2 := by norm_num")
        self.assertIn("https://live.lean-lang.org/#project=mathlib-stable&code=", lean)
        self.assertIn("不把网页结果冒充本地 kernel 验证", lean)
        self.assertIn("https://coq.vercel.app/", MathService.formal("coq"))
        rzk = MathService.formal("rzk")
        self.assertIn("https://rzk-lang.github.io/rzk/develop/playground", rzk)
        self.assertIn("#lang rzk-1", rzk)

    def test_wolfram_uses_explicit_appid_without_leaking_to_headers(self):
        fake = AsyncMock(return_value="Query:\n2+2\nResult:\n4")
        with patch("doge_shared.lookup._text", fake):
            out = __import__("asyncio").run(LookupService.wolfram("2+2", appid="SECRET-APPID"))
        self.assertIn("Result", out)
        args = fake.await_args.args
        self.assertEqual(args[1]["appid"], "SECRET-APPID")
        self.assertEqual(args[1]["input"], "2+2")
        self.assertIsNone(args[2])


if __name__ == "__main__":
    unittest.main()
