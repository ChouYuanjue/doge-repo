from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
MANIFEST = json.loads((ROOT / "plugin_manifest.json").read_text(encoding="utf-8"))
DEFAULT = {x["name"] for x in MANIFEST["plugins"] if x.get("default")}
LEGACY = {x["name"] for x in MANIFEST["plugins"] if x.get("status") == "legacy"}


def _is_filter_decorator(deco: ast.Call, attr: str) -> bool:
    return (
        isinstance(deco.func, ast.Attribute)
        and deco.func.attr == attr
        and isinstance(deco.func.value, ast.Name)
        and deco.func.value.id == "filter"
    )


def commands_for(names: set[str]) -> set[str]:
    """Return only *top-level* AstrBot commands/groups from plugin source.

    `@admin.command("reset")` is deliberately not a top-level `/reset`; it is
    `/admin reset` and therefore must not pollute the public surface audit.
    """
    out: set[str] = set()
    for name in names:
        p = PLUGINS / name / "main.py"
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                if _is_filter_decorator(deco, "command") or _is_filter_decorator(deco, "command_group"):
                    if any(k.arg == "alias" for k in deco.keywords):
                        raise AssertionError(f"AstrBot alias leaked: {p}:{node.lineno}")
                    if deco.args and isinstance(deco.args[0], ast.Constant):
                        out.add(str(deco.args[0].value))
    return out


class SplitLayoutTests(unittest.TestCase):
    def test_manifest_plugins_exist(self):
        for name in DEFAULT | LEGACY:
            self.assertTrue((PLUGINS / name / "main.py").exists(), name)
        self.assertTrue((PLUGINS / "doge_shared" / "__init__.py").exists())
        self.assertFalse((PLUGINS / "doge_shared" / "main.py").exists())
        self.assertTrue((PLUGINS / "doge_media" / "main.py").exists())
        self.assertTrue((PLUGINS / "doge_admin" / "main.py").exists())

    def test_default_command_surface_is_clean(self):
        expected = {
            "help", "ver", "status", "statics", "admin",
            "math", "util", "paper", "bio", "chem", "mat", "astro", "trial",
            "lab", "tex", "typst", "md", "snippet", "game", "fuse", "arena",
            "lang", "media", "run", "lookup", "diagram", "ai", "cs", "eng",
        }
        self.assertEqual(commands_for(DEFAULT), expected)

    def test_no_command_aliases_in_formal_plugins(self):
        commands_for(DEFAULT)  # helper asserts aliases are absent

    def test_historical_commands_do_not_leak_into_default(self):
        retired = {
            "gpt", "yg", "gan", "dream", "style", "toonify", "gen", "siku",
            "perc", "phil", "poem", "insult", "fru", "rua", "jeffjoke", "px",
            "yan", "se", "genshin", "honkai", "pack", "doubao", "lcha", "ltran",
            "lsd", "lflux", "lcon", "limg", "amuse", "netool", "chart", "api",
            "emojimix", "meme", "mirage", "music", "lyrics", "vv", "trace", "st",
            "mc", "law", "anime", "say", "arknights",
        }
        self.assertTrue(retired.isdisjoint(commands_for(DEFAULT)))
        self.assertTrue(retired.issubset(commands_for(LEGACY)))

    def test_bare_astrbot_builtins_do_not_exist_in_doge_surface(self):
        # Public /help is intentionally reclaimed by Doge. Everything else is
        # framework administration and belongs under /admin only.
        bare = {"sid", "name", "reset", "stop", "new", "stats", "provider", "dashboard_update", "set", "unset"}
        self.assertTrue(bare.isdisjoint(commands_for(DEFAULT)))
        self.assertIn("admin", commands_for(DEFAULT))

    def test_collapsed_old_aliases_are_not_registered(self):
        removed = {
            "doge", "encode", "decode", "cotool", "nasa", "bing", "circuit",
            "control", "crystal", "chart", "signal", "shock", "wp", "sci",
            "latex", "utex", "typ", "tym", "yau",
        }
        self.assertTrue(removed.isdisjoint(commands_for(DEFAULT)))

    def test_default_profile_is_granular(self):
        self.assertGreaterEqual(len(DEFAULT), 20)
        for too_broad in {"doge_research", "doge_lab"}:
            self.assertNotIn(too_broad, DEFAULT)


if __name__ == "__main__":
    unittest.main()
