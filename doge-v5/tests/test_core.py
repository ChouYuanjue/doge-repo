from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins"
sys.path.insert(0, str(PLUGIN))

from doge_shared.logic import codec, convert_base, parse_ban_duration, safe_calc
from doge_shared.raw_command import command_payload, split_head


class RawCommandTests(unittest.TestCase):
    def test_multiline_payload_is_preserved(self):
        raw = "/run python print('a b')\nprint('c')"
        self.assertEqual(
            command_payload(raw, "run"),
            "python print('a b')\nprint('c')",
        )

    def test_command_without_slash(self):
        self.assertEqual(command_payload("math calc 1 + 2", "math"), "calc 1 + 2")

    def test_bounded_split(self):
        self.assertEqual(split_head("calc 1 + 2", 1), ["calc", "1 + 2"])


class LogicTests(unittest.TestCase):
    def test_safe_calc_keeps_v3_power_semantics(self):
        self.assertEqual(safe_calc("2^10"), 1024)
        self.assertEqual(safe_calc("7 xor 3"), 4)
        self.assertEqual(safe_calc("(4+5)*3"), 27)

    def test_safe_calc_rejects_calls(self):
        with self.assertRaises(ValueError):
            safe_calc("__import__('os').system('id')")

    def test_base64_roundtrip(self):
        encoded = convert_base("114514", 10, 64)
        self.assertEqual(convert_base(encoded, 64, 10), "114514")

    def test_codecs(self):
        value = "豆子 doge"
        for kind in ("url", "unicode", "hex", "base64"):
            encoded = codec("encode", kind, value)
            self.assertEqual(codec("decode", kind, encoded), value)

    def test_ban_duration(self):
        self.assertEqual(parse_ban_duration("2小时30分"), 9000)
        self.assertEqual(parse_ban_duration("90s"), 90)
        self.assertEqual(parse_ban_duration("10"), 600)
        self.assertEqual(parse_ban_duration("1个月"), 30 * 24 * 60 * 60)


if __name__ == "__main__":
    unittest.main()
