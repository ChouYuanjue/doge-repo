from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

from doge_shared.capabilities import match_invocation, registry
from doge_shared.help_service import format_cli_error, render_help


class ParameterSemanticsTests(unittest.TestCase):
    def test_registry_uses_explicit_required_optional_choice_notation(self):
        syntax = registry()["syntax"]
        self.assertIn("<arg>", syntax["required"])
        self.assertIn("[arg]", syntax["optional"])
        self.assertIn("{a|b}", syntax["choices"])
        self.assertIn("[arg ...]", syntax["repeatable"])

        issues = []
        for op in registry()["operations"]:
            usage = op["usage"]
            mode = op.get("args")
            if "[...]" in usage or "[…]" in usage:
                issues.append((op["id"], "generic optional placeholder", usage))
            if mode == "none" and re.search(r"<[^>]+>|\[[^\]]+\]", usage):
                issues.append((op["id"], "args=none but usage has positional placeholder", usage))
            if mode == "required":
                has_required_positional = bool(re.search(r"<[^>]+>|(?<!\[)\{[^}]+\}(?!\])", usage))
                has_required_input = any(bool(x.get("required", True)) for x in (op.get("inputs") or []))
                if not has_required_positional and not has_required_input:
                    issues.append((op["id"], "required operation has no required marker", usage))
            if mode == "optional" and not re.search(r"\[[^\]]+\]", usage):
                issues.append((op["id"], "optional operation hides optionality", usage))
        self.assertEqual(issues, [])

    def test_known_optional_commands_match_without_and_with_arguments(self):
        self.assertEqual(match_invocation("/game mine").capability_id, "game.mine.new")
        self.assertEqual(match_invocation("/game mine hard").capability_id, "game.mine.new")
        self.assertEqual(match_invocation("/game sudoku").capability_id, "game.sudoku.new")
        self.assertEqual(match_invocation("/arena chaos 3").capability_id, "arena.chaos")

    def test_oeis_missing_arg_error_recovers_leaf_and_explains_parameter(self):
        out = format_cli_error("math", ValueError("用法：/math oeis <数列或关键词>"))
        self.assertIn("USAGE", out)
        self.assertIn("/math oeis <数列或关键词>", out)
        self.assertIn("PARAMETERS", out)
        self.assertIn("整数项", out)
        self.assertIn("EXAMPLES", out)
        self.assertIn("/math oeis 1,1,2,3,5,8", out)
        self.assertIn("/help math oeis", out)

    def test_optional_lab_args_and_attachment_inputs_are_visible(self):
        lab, _ = render_help("lab attractor")
        self.assertIn("/lab attractor [{lorenz|rossler|clifford}]", lab)
        self.assertIn("默认 lorenz", lab)

        crystal, _ = render_help("mat crystal info")
        self.assertIn("INPUTS", crystal)
        self.assertIn("CIF/mCIF", crystal)
        self.assertIn("必需", crystal)

    def test_repeatable_cell_and_game_action_help_are_conventional(self):
        mine, _ = render_help("game mine open")
        self.assertIn("<cell> [cell ...]", mine)
        morris, _ = render_help("game nc")
        self.assertIn("<action>", morris)


if __name__ == "__main__":
    unittest.main()
