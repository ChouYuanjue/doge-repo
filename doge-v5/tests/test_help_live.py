from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from doge_shared.help_live import (
    HelpPreferenceStore,
    help_to_markdown,
    normalize_help_style_topic,
    random_quick_start,
    render_help_live,
    scope_key,
)


class HelpLiveTests(unittest.TestCase):
    def test_live_root_has_no_redundant_usage_block_and_randomizes_examples(self):
        root_a, markdown_a = render_help_live("", random.Random(7))
        root_b, markdown_b = render_help_live("", random.Random(17))
        self.assertFalse(markdown_a)
        self.assertFalse(markdown_b)
        self.assertIn("Doge Help", root_a)
        self.assertNotIn("\nUSAGE\n", root_a)
        self.assertIn("QUICK START", root_a)
        self.assertIn("/help style {image|text}", root_a)
        self.assertNotEqual(root_a, root_b)

    def test_quick_start_uses_real_topics_at_mixed_depths(self):
        rows = random_quick_start(random.Random(23), count=8)
        self.assertEqual(len(rows), len({topic for topic, _ in rows}))
        depths = {len(topic.split()) for topic, _ in rows}
        self.assertGreaterEqual(len(depths), 2)
        self.assertTrue(all(topic for topic, _ in rows))

    def test_style_parser(self):
        self.assertEqual(normalize_help_style_topic("style"), ("query", None))
        self.assertEqual(normalize_help_style_topic("style image"), ("set", "image"))
        self.assertEqual(normalize_help_style_topic("样式 文字"), ("set", "text"))
        self.assertEqual(normalize_help_style_topic("mode wat"), ("invalid", "wat"))
        self.assertIsNone(normalize_help_style_topic("lang tangut"))

    def test_group_preferences_are_isolated_and_default_to_image(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "help_preferences.json"
            store = HelpPreferenceStore(path)
            a, label_a = scope_key("aiocqhttp", "10001", "umo-a")
            b, label_b = scope_key("aiocqhttp", "10002", "umo-b")
            self.assertEqual(label_a, "当前群")
            self.assertEqual(label_b, "当前群")
            self.assertEqual(store.get(a), "image")
            self.assertEqual(store.get(b), "image")
            store.set(a, "text")
            self.assertEqual(store.get(a), "text")
            self.assertEqual(store.get(b), "image")
            reloaded = HelpPreferenceStore(path)
            self.assertEqual(reloaded.get(a), "text")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], 1)

    def test_help_card_markdown_is_semantic_not_a_terminal_screenshot(self):
        text, _ = render_help_live("lang tangut", random.Random(1))
        md = help_to_markdown(text)
        self.assertTrue(md.startswith("# "))
        self.assertIn("## 子功能", md)
        self.assertIn("`/lang tangut", md)
        self.assertIn("中文→西夏文", md)


class PersonaStyleTests(unittest.TestCase):
    def test_persona_style_never_replaces_identity_or_capability_knowledge(self):
        p = json.loads((ROOT / "persona" / "doge.json").read_text(encoding="utf-8"))
        prompt = p["system_prompt"]
        self.assertIn("自然地把自己当成一个女孩子", prompt)
        self.assertIn("服务器、电脑和工具只是你聊天做事用的设备", prompt)
        self.assertIn("不是住处或身体", prompt)
        self.assertIn("豆子（也有人写作まめこ）", prompt)
        self.assertIn("芽衣子（めいこ / Meiko）", prompt)
        self.assertIn("私人的真实名字", prompt)
        self.assertIn("平时别人问“你叫什么”“你是谁”，就自然回答豆子", prompt)
        self.assertIn("唯一角色参考是灰原哀", prompt)
        self.assertIn("聪明、成熟、敏锐", prompt)
        self.assertIn("不冒充原作身份或经历", prompt)
        self.assertIn("工具调用完全放在幕后", prompt)
        self.assertIn("回复密度跟语境走", prompt)
        self.assertIn("回答完一件事通常就自然收住", prompt)
        self.assertIn("客服式追问", prompt)
        self.assertIn("简洁”不等于强行压成一句话", prompt)
        self.assertIn("小得意或轻微吃味", prompt)
        self.assertIn("不要把每句话都写成", prompt)
        self.assertIn("authoritative capability inventory", prompt)
        self.assertIn("任务能力不降级", prompt)
        self.assertNotIn("靠电/token 活着", prompt)
        for forbidden in ("实验室怪人型前辈", "牧濑红莉栖", "GLaDOS"):
            self.assertNotIn(forbidden, prompt)
