from __future__ import annotations

import ast
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

from doge_shared.capabilities import agent_capability_prompt, capability_display, counts, match_invocation, registry, search_capabilities
from doge_shared.help_service import format_cli_error, render_help
from doge_shared.presentation import markdown_to_plain
from doge_shared.runtime_stats import UsageCounter


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CapabilityRegistryTests(unittest.TestCase):
    def test_registry_covers_expected_public_surface(self):
        r = registry()
        commands = set(r["commands"])
        expected = {
            "help", "ver", "status", "statics", "admin",
            "math", "util", "paper", "bio", "chem", "mat", "astro", "trial",
            "lab", "fourier", "tex", "typst", "md", "snippet", "game", "fuse", "arena", "social",
            "lang", "media", "run", "lookup", "diagram", "ai", "cs", "eng",
        }
        self.assertEqual(commands, expected)
        listed = {c for cat in r["categories"] for c in cat["commands"]}
        self.assertEqual(listed, expected)
        c = counts()
        self.assertEqual(c["top_level"], 31)
        self.assertEqual(c["functions"], len(r["operations"]))
        self.assertEqual(c["forms"], c["functions"] + c["aliases"])
        self.assertEqual(c["aliases"], sum(len(op.get("aliases", [])) for op in r["operations"]))
        self.assertEqual(c["triggers"], 1)
        self.assertEqual(c["legacy_top_level"], 45)
        self.assertEqual(c["legacy_functions"], 81)
        self.assertEqual(c["all_functions"], c["functions"] + c["legacy_functions"])

    def test_registry_aliases_and_legacy_source_are_well_formed(self):
        r = registry()
        for op in r["operations"]:
            self.assertIsInstance(op.get("aliases", []), list)
            self.assertFalse(op.get("aliases") in [list("none"), list("required"), list("optional")], op["id"])
        tree = ast.parse((PLUGINS / "doge_legacy" / "main.py").read_text(encoding="utf-8"))
        history = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "HISTORY" for t in node.targets):
                history = ast.literal_eval(node.value)
                break
        self.assertIsInstance(history, dict)
        self.assertEqual(set(history), set(r["legacy"]["commands"]))

    def test_slash_wake_is_not_automatically_a_command(self):
        self.assertIsNone(match_invocation("/你好"))
        self.assertIsNone(match_invocation("/你能做什么"))
        self.assertIsNone(match_invocation("/totally-unknown whatever"))
        self.assertEqual(match_invocation("/ver").capability_id, "core.ver")
        self.assertIsNone(match_invocation("/gpt hello"))  # Legacy is not loaded in the default profile
        self.assertEqual(match_invocation("/gpt hello", include_legacy=True).capability_id, "legacy.gpt")

    def test_nested_aliases_canonicalize_but_invocation_form_is_preserved(self):
        x = match_invocation("/game minesweeper open A1")
        self.assertEqual(x.capability_id, "game.mine.open")
        self.assertEqual(x.invoked, "game minesweeper open")
        self.assertTrue(x.is_alias)
        x = match_invocation("/lang 西夏文 zh2t 我爱中国")
        self.assertEqual(x.capability_id, "lang.tangut.zh2t")
        self.assertEqual(x.invoked, "lang 西夏文 zh2t")
        self.assertEqual(match_invocation("/game nc start").capability_id, "game.nc.start")
        self.assertEqual(match_invocation("给我一点电疗").capability_id, "util.electrotherapy")

    def test_agent_knows_full_tangut_bidirectional_capability(self):
        prompt = agent_capability_prompt()
        self.assertIn("/lang", prompt)
        self.assertIn("西夏文", prompt)
        self.assertIn("doge_capability_search", prompt)
        self.assertIn(f"{counts()['functions']} canonical leaf functions", prompt)
        results = search_capabilities("西夏文翻译", 8)
        by_id = {x["id"]: x for x in results}
        self.assertIn("lang.tangut.t2zh", by_id)
        self.assertIn("lang.tangut.zh2t", by_id)
        self.assertIn("西夏文→中文", by_id["lang.tangut.t2zh"]["summary"])
        self.assertIn("中文→西夏文", by_id["lang.tangut.zh2t"]["summary"])
        self.assertIn("Legacy is historical", prompt)


class HelpTests(unittest.TestCase):
    def test_cli_root_and_layered_help(self):
        root, markdown = render_help("")
        self.assertFalse(markdown)
        self.assertIn("Doge CLI", root)
        self.assertIn(f"正式叶子功能   {counts()['functions']}", root)
        self.assertIn(f"正式调用形式   {counts()['forms']}", root)
        self.assertIn("Legacy 叶子    81", root)
        self.assertIn("/help lang tangut", root)
        research, _ = render_help("research")
        self.assertIn("/paper", research)
        mine, _ = render_help("game mine")
        self.assertIn("首次开格保证安全", mine)
        self.assertIn("/game mine mark <cell> [cell ...]", mine)
        self.assertIn("/game mine sweep <cell> [cell ...]", mine)
        tangut, _ = render_help("lang tangut")
        self.assertIn("t2zh", tangut)
        self.assertIn("zh2t", tangut)
        self.assertIn("中文→西夏文", tangut)

    def test_alias_help_redirect_and_typo_suggestion(self):
        alias, _ = render_help("game minesweeper")
        self.assertIn("兼容写法已归一", alias)
        self.assertIn("/game mine", alias)
        typo, _ = render_help("lagn")
        self.assertIn("/help lang", typo)
        self.assertNotIn("/help ltran", typo)
        legacy_typo, _ = render_help("legacy gtp")
        self.assertIn("/help legacy gpt", legacy_typo)

    def test_cli_error_points_back_to_help(self):
        out = format_cli_error("lang", "未知 Tangut 子命令", "lang tangut")
        self.assertIn("ERROR  /lang", out)
        self.assertIn("未知 Tangut 子命令", out)
        self.assertIn("/help lang tangut", out)
        self.assertIn("/help lang", out)

    def test_legacy_help_and_generated_docs_are_current(self):
        legacy, _ = render_help("legacy")
        self.assertIn("历史顶层入口   45", legacy)
        self.assertIn("历史叶子功能   81", legacy)
        gan, _ = render_help("legacy gan")
        self.assertIn("StyleGAN", gan)
        self.assertIn("cat", gan)
        self.assertIn("chem", gan)
        mod = _load_module("doge_help_gen", ROOT / "tools" / "generate_help_docs.py")
        self.assertEqual((ROOT / "HELP.md").read_text(encoding="utf-8"), mod.generate())
        self.assertEqual((ROOT / "LEGACY.md").read_text(encoding="utf-8"), mod.generate_legacy())


class UsageStatisticsTests(unittest.TestCase):
    def test_aliases_roll_up_to_one_canonical_top_feature(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); logs = td / "logs"; logs.mkdir(); usage = td / "usage.json"
            counter = UsageCounter(usage, logs)
            counter.record("aiocqhttp", "/game mine open A1")
            counter.record("aiocqhttp", "/game minesweeper open B2")
            counter.record("aiocqhttp", "/你觉得这个怎么样")
            d = counter.snapshot()
            self.assertEqual(d["commands"], 2)
            self.assertEqual(d["by_capability"], {"game.mine.open": 2})
            self.assertEqual(sum(d["by_command"].values()), 2)

    def test_v1_migration_rebuilds_only_registered_commands(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); logs = td / "logs"; logs.mkdir(); usage = td / "usage.json"
            usage.write_text(json.dumps({
                "schema": 1, "started_at": 1, "messages": 3, "commands": 3,
                "by_platform": {}, "by_command": {"你好": 1, "ver": 1, "lang": 1}, "by_date": {},
            }))
            (logs / "astrbot.log").write_text(
                "[x] [core.event_bus:74]: [g] [aiocqhttp] x: /你好\n"
                "[x] [core.event_bus:74]: [g] [aiocqhttp] x: /ver\n"
                "[x] [core.event_bus:74]: [g] [aiocqhttp] x: /lang 西夏文 zh2t 我爱中国\n",
                encoding="utf-8",
            )
            d = UsageCounter(usage, logs).snapshot()
            self.assertEqual(d["schema"], 2)
            self.assertEqual(d["commands"], 2)
            self.assertNotIn("你好", d["by_command"])
            self.assertEqual(d["by_command"], {"ver": 1, "lang 西夏文 zh2t": 1})
            self.assertEqual(d["by_capability"]["lang.tangut.zh2t"], 1)
            self.assertEqual(capability_display("lang.tangut.zh2t"), "/lang tangut zh2t")


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
        prompt = p["system_prompt"]
        self.assertLess(len(prompt), 1800)
        self.assertEqual(p["begin_dialogs"], [])  # examples are retrieved as examples, not fake chat history
        self.assertIn("自然地把自己当成一个女孩子", prompt)
        self.assertIn("不是住处", prompt)
        self.assertIn("我这边装了/没装", prompt)
        self.assertIn("也不编年龄、城市、学校、职业或住址", prompt)
        self.assertIn("昵称只是可变称呼", prompt)
        self.assertIn("陌生昵称也不等于“新人”", prompt)
        self.assertIn("远端跑 Python", prompt)
        self.assertIn("唯一角色参考是灰原哀", prompt)
        self.assertIn("不声称自己就是灰原哀", prompt)
        self.assertIn("可爱来自反应速度、语气、反差和关系感", prompt)
        self.assertIn("任务能力永远优先", prompt)
        self.assertIn("authoritative capability inventory", prompt)
        self.assertIn("空括号", prompt)
        self.assertIn("没必要每次列菜单", prompt)
        self.assertIn("服务器、电脑、主机只是你聊天和做事用的设备", prompt)
        self.assertIn("不告诉你", prompt)
        self.assertNotIn("你住在服务器和网络这一侧", prompt)
        self.assertNotIn("草莓蛋糕", prompt)
        self.assertNotIn("发卡", prompt)
        self.assertNotIn("靠电/token 活着", prompt)
        self.assertNotIn("实验室怪人型前辈", prompt)
        self.assertNotIn("牧濑红莉栖", prompt)
        self.assertNotIn("GLaDOS", prompt)
        self.assertNotIn("汪~", prompt)
        self.assertNotIn("Doge 只是项目名", prompt)
        self.assertIsNone(p["tools"])

    def test_runtime_profile_installer_is_idempotent_and_preserves_unrelated_config(self):
        installer = _load_module("doge_runtime_installer", ROOT / "tools" / "install_runtime_profile.py")
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td); data = runtime / "data"; data.mkdir()
            cfg = {
                "provider_settings": {"default_personality": "default", "persona_pool": ["*"], "default_provider_id": "keep-me"},
                "platform": [{"id": "napcat", "secret": "DO_NOT_TOUCH"}],
                "admins_id": ["existing-admin"],
                "disable_builtin_commands": False,
            }
            (data / "cmd_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8-sig")
            conn = sqlite3.connect(data / "data_v4.db")
            conn.execute(
                "CREATE TABLE personas (created_at TEXT NOT NULL, updated_at TEXT NOT NULL, id INTEGER PRIMARY KEY AUTOINCREMENT, persona_id TEXT UNIQUE NOT NULL, system_prompt TEXT NOT NULL, begin_dialogs JSON, tools JSON, skills JSON, custom_error_message TEXT, folder_id TEXT, sort_order INTEGER DEFAULT 0)"
            )
            conn.commit(); conn.close()
            (data / "config").mkdir()
            (data / "config" / "doge_core_config.json").write_text(
                json.dumps({"absolute_admin_ids": ["2700074128", "existing-admin"]}), encoding="utf-8"
            )
            installer.install(runtime, backup=False); installer.install(runtime, backup=False)
            out = json.loads((data / "cmd_config.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(out["provider_settings"]["default_personality"], "doge")
            self.assertEqual(out["provider_settings"]["default_provider_id"], "keep-me")
            self.assertEqual(out["platform"][0]["secret"], "DO_NOT_TOUCH")
            self.assertEqual(out["admins_id"], ["existing-admin", "2700074128"])
            self.assertTrue(out["disable_builtin_commands"])
            ps = out["platform_settings"]
            self.assertEqual(ps["forward_threshold"], 800)
            seg = ps["segmented_reply"]
            self.assertTrue(seg["enable"])
            self.assertTrue(seg["only_llm_result"])
            self.assertEqual(seg["words_count_threshold"], 1100)
            self.assertEqual(seg["split_mode"], "regex")
            self.assertEqual(seg["regex"], r".*?(?:\n{2,}|\Z)")
            self.assertEqual(seg["interval"], "0.4,1.0")
            conn = sqlite3.connect(data / "data_v4.db")
            rows = conn.execute("SELECT persona_id,system_prompt,begin_dialogs FROM personas").fetchall(); conn.close()
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0][0], "doge")
            self.assertEqual(len(json.loads(rows[0][2])) % 2, 0)


if __name__ == "__main__":
    unittest.main()
