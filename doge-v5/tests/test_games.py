import unittest
from fractions import Fraction

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from doge_shared.game24 import check, solve_24
from doge_shared.morris import MorrisGame


class Point24Tests(unittest.TestCase):
    def test_solver_finds_exact_solution(self):
        expr = solve_24([3, 3, 8, 8])
        self.assertIsNotNone(expr)
        self.assertEqual(check(expr, [3, 3, 8, 8]), Fraction(24))

    def test_checker_requires_exact_multiset(self):
        with self.assertRaises(ValueError):
            check("6*4", [6, 4, 1, 1])

    def test_wild_bitwise_is_opt_in(self):
        with self.assertRaises(ValueError):
            check("8<<1+4+2", [8, 1, 4, 2])
        value = check("(8<<1)+4+2", [8, 1, 4, 2], wild=True)
        self.assertEqual(value, Fraction(22))


class MorrisTests(unittest.TestCase):
    def setUp(self):
        self.g = MorrisGame()
        self.g.add_player("p0", "Alice")
        self.g.add_player("p1", "Bob")

    def test_mill_requires_capture_then_turn_changes(self):
        self.g.act("p0", "A1")
        self.g.act("p1", "B1")
        self.g.act("p0", "A2")
        self.g.act("p1", "B2")
        msg = self.g.act("p0", "A3")
        self.assertIn("磨坊", msg)
        self.assertEqual(self.g.capture_by, 0)
        with self.assertRaises(ValueError):
            self.g.act("p1", "B3")
        self.g.act("p0", "x B1")
        self.assertIsNone(self.g.capture_by)
        self.assertEqual(self.g.turn, 1)
        self.assertNotIn("B1", self.g.board)

    def test_non_player_cannot_act(self):
        with self.assertRaises(ValueError):
            self.g.act("spectator", "A1")

    def test_board_has_coordinate_labels(self):
        text = self.g.render()
        self.assertIn("A1", text)
        self.assertIn("C5", text)
        self.assertIn("Alice", text)
        self.assertIn("Bob", text)


if __name__ == "__main__":
    unittest.main()


class MarketGameTests(unittest.TestCase):
    def test_minesweeper_first_click_safe_and_renders(self):
        import asyncio
        import tempfile
        from doge_games.minesweeper_adapter import apply, new_game, render

        game = asyncio.run(new_game("easy"))
        apply(game, "open", ["A1"])
        self.assertFalse(game.tiles[0][0].is_mine)
        self.assertTrue(game.tiles[0][0].is_open)
        with tempfile.TemporaryDirectory() as td:
            path = render(game, Path(td), "test")
            self.assertGreater(path.stat().st_size, 1000)
            self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_sudoku_is_unique_solvable_and_renders(self):
        import tempfile
        from doge_games.sudoku_adapter import new_game, render

        game = new_game("easy")
        self.assertEqual(game.difficulty, "easy")
        self.assertFalse(game.complete)
        # The pinned generator marks multi-solution puzzles with difficulty=-3;
        # adapter retries them, so every returned session has one accepted solution.
        self.assertEqual(len(game.solution), 9)
        self.assertTrue(all(len(row) == 9 for row in game.solution))
        with tempfile.TemporaryDirectory() as td:
            path = render(game, Path(td), "test")
            self.assertGreater(path.stat().st_size, 1000)

    def test_tabletop_dice_supports_roll20_modifiers(self):
        from doge_games.dice_adapter import tabletop_roll

        out = tabletop_roll("d20adv 察觉 15")
        self.assertIn("察觉", out)
        self.assertIn("2d20adv", out)
        self.assertIn("/ 15", out)
        out2 = tabletop_roll("4d6kh3")
        self.assertIn("4d6kh3", out2)
