from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from doge_shared.help_service import load_catalog, render_help
from doge_shared.presentation import markdown_to_plain


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HelpTests(unittest.TestCase):
    def test_catalog_covers_expected_public_surface(self):
        catalog = load_catalog()
        commands = set(catalog["commands"])
        expected = {
            "help", "ver", "status", "statics", "admin",
            "math", "util", "paper", "bio", "chem", "mat", "astro", "trial",
            "lab", "tex", "typst", "md", "snippet", "game", "fuse", "arena",
            "lang", "media", "run", "lookup", "diagram", "ai", "cs", "eng",
        }
        self.assertEqual(commands, expected)
        listed = {c for cat in catalog["categories"] for c in cat["commands"]}
        self.assertEqual(listed, expected)

    def test_layered_help(self):
        root, _ = render_help("")
        self.assertIn("/help game mine", root)
        research, _ = render_help("research")
        self.assertIn("/paper", research)
        mine, _ = render_help("game mine")
        self.assertIn("首击安全", mine)
        self.assertIn("/game mine mark A1", mine)

    def test_generated_help_is_current(self):
        mod = _load_module("doge_help_gen", ROOT / "tools" / "generate_help_docs.py")
        self.assertEqual((ROOT / "HELP.md").read_text(encoding="utf-8"), mod.generate())


class MarkdownPlainTests(unittest.TestCase):
    def test_strips_common_markdown_but_keeps_content(self):
        src = "## 标题\n\n- **粗体** 与 `code`\n- [链接](https://example.com)\n\n```python\nprint(42)\n```"
        out = markdown_to_plain(src)
        self.assertNotIn("##", out)
        self.assertNotIn("**", out)
        self.assertNotIn("```", out)
        self.assertIn("标题", out)
        self.assertIn("粗体", out)
        self.assertIn("code", out)
        self.assertIn("链接 (https://example.com)", out)
        self.assertIn("print(42)", out)

    def test_does_not_destroy_math_multiplication(self):
        self.assertEqual(markdown_to_plain("2*3=6; a_b is literal"), "2*3=6; a_b is literal")


class PersonaTests(unittest.TestCase):
    def test_persona_shape(self):
        p = json.loads((ROOT / "persona" / "doge.json").read_text(encoding="utf-8"))
        self.assertEqual(p["persona_id"], "doge")
        self.assertEqual(len(p["begin_dialogs"]) % 2, 0)
        self.assertGreaterEqual(len(p["begin_dialogs"]), 6)
        self.assertIn("不编造真实人生经历", p["system_prompt"])
        self.assertIn("计算机", p["system_prompt"])
        self.assertIsNone(p["tools"])

    def test_runtime_profile_installer_is_idempotent_and_preserves_unrelated_config(self):
        installer = _load_module("doge_runtime_installer", ROOT / "tools" / "install_runtime_profile.py")
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td)
            data = runtime / "data"
            data.mkdir()
            cfg = {
                "provider_settings": {"default_personality": "default", "persona_pool": ["*"], "default_provider_id": "keep-me"},
                "platform": [{"id": "napcat", "secret": "DO_NOT_TOUCH"}],
                "disable_builtin_commands": False,
            }
            (data / "cmd_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8-sig")
            conn = sqlite3.connect(data / "data_v4.db")
            conn.execute(
                "CREATE TABLE personas (created_at TEXT NOT NULL, updated_at TEXT NOT NULL, id INTEGER PRIMARY KEY AUTOINCREMENT, persona_id TEXT UNIQUE NOT NULL, system_prompt TEXT NOT NULL, begin_dialogs JSON, tools JSON, skills JSON, custom_error_message TEXT, folder_id TEXT, sort_order INTEGER DEFAULT 0)"
            )
            conn.commit(); conn.close()

            installer.install(runtime, backup=False)
            installer.install(runtime, backup=False)
            out = json.loads((data / "cmd_config.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(out["provider_settings"]["default_personality"], "doge")
            self.assertEqual(out["provider_settings"]["default_provider_id"], "keep-me")
            self.assertEqual(out["platform"][0]["secret"], "DO_NOT_TOUCH")
            self.assertTrue(out["disable_builtin_commands"])
            conn = sqlite3.connect(data / "data_v4.db")
            rows = conn.execute("SELECT persona_id,system_prompt,begin_dialogs FROM personas").fetchall()
            conn.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "doge")
            self.assertEqual(len(json.loads(rows[0][2])) % 2, 0)


if __name__ == "__main__":
    unittest.main()
