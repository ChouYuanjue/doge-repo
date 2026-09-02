from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from doge_shared.agent_tools import DogeChaoliTool
from doge_shared.chaoli import ChaoliError, ChaoliService


LIST_HTML = """
<ul>
<li id='c1' class='channel-4 label-sticky'><div class='col-conversation'><strong class='title'><a href='/index.php/1'>置顶旧帖</a></strong><div class='excerpt'>old</div></div><a class='channel'>数学</a><span class='firstPostMember'>A</span><span class='lastPostTime'>很久前</span><div class='col-replies'>9</div></li>
<li id='c2' class='channel-4'><div class='col-conversation'><strong class='title'><a href='/index.php/2'>新帖</a></strong><div class='excerpt'>new excerpt</div></div><a class='channel' href='/index.php/conversations/maths/'>数学</a><span class='firstPostMember'>B</span><span class='startTime'>今天</span><span class='lastPostMember'>C</span><span class='lastPostTime'>1小时前</span><div class='col-replies'><span>3</span></div></li>
</ul>
"""

THREAD_HTML = """
<html><head><title>真正标题 - 超理论坛</title></head><body>
<div class='post' id='p10' data-id='10'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/7'>甲</a></h3><span>1楼</span><a class='time'>今天</a></div></div><div class='postBody'>第一层 <a href='/index.php/99'>引用旧帖</a></div></div>
<div class='post' id='p11' data-id='11'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/8'>乙</a></h3><span>2楼</span><a class='time'>刚刚</a></div></div><div class='postBody'>第二层</div></div>
<div class='post logInToReply' id='reply'><div class='postHeader'>回复</div><div class='postBody'>登录 后才能发言</div></div>
</body></html>
"""


class ChaoliParserTests(unittest.TestCase):
    def test_latest_skips_sticky_by_default(self):
        cards = ChaoliService._parse_cards(LIST_HTML, 5)
        self.assertEqual([x.thread_id for x in cards], [2])
        self.assertEqual(cards[0].title, "新帖")
        self.assertEqual(cards[0].channel, "数学")
        self.assertEqual(cards[0].replies, "3")

    def test_thread_parser_uses_document_title_and_real_posts_only(self):
        title, floors = ChaoliService._parse_thread(THREAD_HTML, 42)
        self.assertEqual(title, "真正标题")
        self.assertEqual(len(floors), 2)
        self.assertEqual((floors[0].number, floors[0].author, floors[0].time), (1, "甲", "今天"))
        self.assertEqual((floors[1].number, floors[1].author), (2, "乙"))
        self.assertNotIn("登录 后才能发言", " ".join(x.text for x in floors))

    def test_thread_ref_accepts_id_and_forum_url_only(self):
        self.assertEqual(ChaoliService.parse_thread_ref("12231"), (12231, None))
        self.assertEqual(ChaoliService.parse_thread_ref("https://chaoli.club/index.php/12231/2"), (12231, "2"))
        with self.assertRaises(ChaoliError):
            ChaoliService.parse_thread_ref("https://example.com/index.php/12231")

    def test_agent_tool_exposes_no_search_action(self):
        tool = DogeChaoliTool()
        actions = tool.parameters["properties"]["action"]["enum"]
        self.assertIn("latest", actions)
        self.assertIn("outline", actions)
        self.assertIn("links", actions)
        self.assertIn("status", actions)
        self.assertNotIn("search", actions)

    def test_registry_truthfully_excludes_search(self):
        d = json.loads((PLUGINS / "doge_shared" / "resources" / "capability_registry.json").read_text(encoding="utf-8"))
        ids = {x["id"] for x in d["operations"] if x["id"].startswith("chaoli.")}
        self.assertIn("chaoli.outline", ids)
        self.assertNotIn("chaoli.search", ids)
        self.assertIn("不依赖站内搜索", d["commands"]["chaoli"]["summary"])


if __name__ == "__main__":
    unittest.main()
