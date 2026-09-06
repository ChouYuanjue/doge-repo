from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
EXTERNAL = ROOT / "external_plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

data_pkg = sys.modules.get("data") or types.ModuleType("data")
data_pkg.__path__ = []
plugins_pkg = sys.modules.get("data.plugins") or types.ModuleType("data.plugins")
plugins_pkg.__path__ = [str(PLUGINS)]
data_pkg.plugins = plugins_pkg
sys.modules["data"] = data_pkg
sys.modules["data.plugins"] = plugins_pkg

from doge_shared.agent_tools import DogeEmojiSearchTool, DogeEmojiSendTool, DogeEmojiStealTool, DogeMemeTool
from astrbot_plugin_meme_generator.core.param_collector import ParamCollector


class MediaNamespaceTests(unittest.TestCase):
    def test_vendored_emoji_backend_exposes_no_public_commands_or_llm_tools(self):
        source = (ROOT / "external_plugins" / "astrbot_plugin_stealer" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("@filter.command(", source)
        self.assertNotIn("@filter.command_group(", source)
        self.assertNotIn("@filter.llm_tool(", source)
        self.assertNotIn("async def search_meme(", source)
        self.assertNotIn("async def send_meme(", source)
        self.assertNotIn("async def steal_sticker(", source)

    def test_doge_owns_semantic_public_tool_names(self):
        self.assertEqual(DogeMemeTool().name, "doge_meme")
        self.assertEqual(DogeEmojiSearchTool().name, "search_emoji")
        self.assertEqual(DogeEmojiSendTool().name, "send_emoji")
        self.assertEqual(DogeEmojiStealTool().name, "steal_emoji")

    def test_meme_tool_knows_runtime_can_resolve_avatar_material(self):
        desc = DogeMemeTool().description
        self.assertIn("当前发送者 QQ 头像", desc)
        self.assertIn("不要要求用户重复提供", desc)
        self.assertIn("直接 action=generate", desc)



    def test_meme_generate_sends_asset_directly_and_terminates(self):
        seen = {}

        async def fake_execute(_context, command):
            self.assertEqual(command, "/meme 摸头")
            return json.dumps({"media": [{"id": "img-generated", "type": "image"}]}, ensure_ascii=False)

        async def fake_present(_self, _context, **kwargs):
            seen.update(kwargs)
            return None

        async def scenario():
            with patch("doge_shared.agent_tools.execute_formal_command", fake_execute), patch(
                "doge_shared.agent_tools.DogePresentTool.call", fake_present
            ):
                return await DogeMemeTool().call(None, action="generate", template="摸头")

        result = asyncio.run(scenario())
        self.assertIsNone(result)
        self.assertEqual(seen["asset_ids"], ["img-generated"])

    def test_meme_detail_pushes_generation_instead_of_requesting_retrievable_avatar(self):
        async def fake_execute(_context, command):
            self.assertEqual(command, "/meme detail 摸头")
            return json.dumps({"text": "所需图片：1张"}, ensure_ascii=False)

        async def scenario():
            with patch("doge_shared.agent_tools.execute_formal_command", fake_execute):
                return await DogeMemeTool().call(None, action="detail", template="摸头")

        data = json.loads(asyncio.run(scenario()))
        self.assertIn("action=generate", data["next_step"])
        self.assertIn("current sender's QQ avatar", data["next_step"])

    def test_template_collector_auto_fetches_current_sender_avatar(self):
        class Network:
            def __init__(self):
                self.calls = []
            async def get_avatar(self, user_id):
                self.calls.append(str(user_id))
                return ("avatar:" + str(user_id)).encode()

        async def scenario():
            net = Network()
            collector = ParamCollector(net)
            images = []
            await collector._auto_fill_images("12345", "99999", "Sender", images, 1)
            return net.calls, images

        calls, images = asyncio.run(scenario())
        self.assertEqual(calls, ["12345"])
        self.assertEqual(len(images), 1)

    def test_vendor_readme_freezes_namespace_boundary(self):
        readme = (ROOT / "external_plugins" / "astrbot_plugin_stealer" / "README.md").read_text(encoding="utf-8")
        self.assertIn("/social emoji", readme)
        self.assertIn("/meme", readme)
        self.assertIn("不注册任何用户命令", readme)
        self.assertIn("不要重新引入", readme)


if __name__ == "__main__":
    unittest.main()
