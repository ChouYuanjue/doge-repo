from __future__ import annotations

import json
import sys
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from doge_shared.agent_tools import DogeChaoliTool
from doge_shared.chaoli import ChaoliError, ChaoliService


LIST_HTML = """
<ul>
<li id='c1' class='channel-4 label-sticky'><div class='col-conversation'><strong class='title'><a href='/index.php/1'>置顶旧帖</a></strong><div class='excerpt'>old</div></div><div class='col-channel'><a class='channel' data-channel='maths' href='/index.php/conversations/maths/'>数学</a></div><div class='col-lastPost'><span class='action'><span class='firstPostMember'><a href='/index.php/member/10'>A</a></span><span class='startTime'>昨天</span></span><span class='action'><span class='lastPostMember'><a href='/index.php/member/11'>Z</a></span><a class='lastPostTime' href='/index.php/1/last'>今天</a></span></div><div class='col-replies'><a href='/index.php/1/unread'>9</a></div></li>
<li id='c2' class='channel-4'><div class='col-conversation'><strong class='title'><a href='/index.php/2'>新帖</a></strong><div class='excerpt'>quoted-looking excerpt</div></div><div class='col-channel'><a class='channel' data-channel='maths' href='/index.php/conversations/maths/'>数学</a></div><div class='col-lastPost'><span class='action'><span class='firstPostMember'><a href='/index.php/member/20'>B</a></span><span class='startTime'>今天</span></span><span class='action'><span class='lastPostMember'><a href='/index.php/member/21'>C</a></span><a class='lastPostTime' href='/index.php/2/last'>1小时前</a></span></div><div class='col-replies'><a href='/index.php/2/unread'>3</a></div></li>
<li id='c3' class='channel-5'><div class='col-conversation'><strong class='title'><a href='/index.php/999'>ID不一致</a></strong></div><div class='col-channel'><a class='channel' data-channel='physics' href='/index.php/conversations/physics/'>物理</a></div></li>
</ul>
"""

MEMBERS_HTML = """
<div class='members'>
<a href='/index.php/member/1286'>碘化亚铜</a>
<a href='/index.php/member/1202'>FatFish</a>
</div>
"""

THREAD_HTML = """
<html><head><title>真正标题 - 超理论坛</title></head><body>
<div class='post' id='p10' data-id='10'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/7'>甲</a></h3><span>1楼 </span><a class='time' href='/index.php/conversation/post/10'>今天</a></div></div><div class='postBody'><blockquote><cite><a class='link-member' href='/index.php/member/9'>@丙</a></cite> 丙说过的话</blockquote>甲自己的话 <a href='/index.php/99'>引用旧帖</a></div></div>
<div class='post deleted' id='p11' data-id='11'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/8'>乙</a></h3><span>2楼 </span><a class='time' href='/index.php/conversation/post/11'>刚刚</a></div></div></div>
<div class='post logInToReply' id='reply'><div class='postHeader'>回复</div><div class='postBody'>登录 后才能发言</div></div>
</body></html>
"""

ACTIVITY_HTML = """
<html><head><title>甲 - 超理论坛</title></head><body>
<div class='activity'><div class='controls'><span class='time'>2026-09-03 10:00:00</span></div><div class='action'>甲 更新于 <a href='/index.php/conversation/post/77'>一个主题</a></div><div class='activityBody postBody'><blockquote><cite><a class='link-member' href='/index.php/member/name/B'>@B</a></cite>B 的原话</blockquote>甲的新回复</div></div>
</body></html>
"""


class ChaoliParserTests(unittest.TestCase):
    def test_latest_strongly_binds_ids_authors_and_update_actor(self):
        cards = ChaoliService._parse_cards(LIST_HTML, 5, expected_channel="math")
        self.assertEqual([x.thread_id for x in cards], [2])
        c = cards[0]
        self.assertEqual((c.channel_slug, c.author, c.author_id, c.last_author, c.last_author_id, c.replies), ("maths", "B", 20, "C", 21, "3"))
        line = c.line()
        self.assertIn("发帖：B（member/20）", line)
        self.assertIn("最后回复：C（member/21）", line)
        self.assertNotIn("quoted-looking excerpt", line)

    def test_channel_is_strict_and_id_mismatch_never_leaks(self):
        with self.assertRaises(ChaoliError):
            ChaoliService._channel_slug("mathematics-guess")
        with self.assertRaisesRegex(ChaoliError, "强绑定"):
            ChaoliService._parse_cards(LIST_HTML, 5, include_sticky=True, expected_channel="physics")

    def test_thread_parser_separates_quotes_and_preserves_deleted_floor(self):
        title, floors = ChaoliService._parse_thread(THREAD_HTML, 42)
        self.assertEqual(title, "真正标题")
        self.assertEqual([x.number for x in floors], [1, 2])
        first = floors[0]
        self.assertEqual((first.author, first.author_id), ("甲", 7))
        self.assertEqual(first.text, "甲自己的话 引用旧帖")
        self.assertEqual(first.quotes[0].author, "丙")
        self.assertIn("丙说过的话", first.quotes[0].text)
        self.assertNotIn("丙说过的话", first.text)
        self.assertTrue(floors[1].deleted)
        self.assertIn("已删除", floors[1].line())
        self.assertNotIn("登录 后才能发言", " ".join(x.text for x in floors))

    def test_thread_ref_accepts_id_and_forum_url_only(self):
        self.assertEqual(ChaoliService.parse_thread_ref("12231"), (12231, None))
        self.assertEqual(ChaoliService.parse_thread_ref("https://chaoli.club/index.php/12231/2"), (12231, "2"))
        with self.assertRaises(ChaoliError):
            ChaoliService.parse_thread_ref("https://example.com/index.php/12231")

    def test_member_directory_parser_supports_joined_page(self):
        self.assertEqual(ChaoliService._member_links(MEMBERS_HTML), [(1286, "碘化亚铜"), (1202, "FatFish")])

    def test_duplicate_exact_username_fails_closed(self):
        with self.assertRaisesRegex(ChaoliError, "同名"):
            ChaoliService._match_member_rows([(1, "same"), (2, "same")], "same")

    def test_agent_tool_exposes_native_search_without_reserved_context_parameter(self):
        tool = DogeChaoliTool()
        actions = tool.parameters["properties"]["action"]["enum"]
        self.assertIn("search", actions)
        self.assertIn("radius", tool.parameters["properties"])
        self.assertNotIn("context", tool.parameters["properties"])

    def test_registry_truthfully_exposes_native_search(self):
        d = json.loads((PLUGINS / "doge_shared" / "resources" / "capability_registry.json").read_text(encoding="utf-8"))
        ids = {x["id"] for x in d["operations"] if x["id"].startswith("chaoli.")}
        self.assertIn("chaoli.outline", ids)
        self.assertIn("chaoli.search", ids)
        self.assertIn("原生帖子搜索", d["commands"]["chaoli"]["summary"])


class ChaoliSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_native_view_and_formats_cards(self):
        with patch.object(ChaoliService, "_search", AsyncMock(return_value=LIST_HTML)):
            out = await ChaoliService.search("新帖", "数学", 5)
        self.assertIn("超理搜索 · 新帖 · 数学", out)
        self.assertIn("#2 新帖", out)
        self.assertIn("https://chaoli.club/index.php/2", out)

    async def test_search_empty_native_view_is_explicit(self):
        with patch.object(ChaoliService, "_search", AsyncMock(return_value="<ul></ul>")):
            with self.assertRaisesRegex(ChaoliError, "没有找到"):
                await ChaoliService.search("不存在的词", "all", 5)


class ChaoliMemberLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_username_prefers_joined_directory_exact_match(self):
        with patch.object(ChaoliService, "_get", AsyncMock(return_value=MEMBERS_HTML)):
            self.assertEqual(await ChaoliService._resolve_member_id("碘化亚铜"), (1286, "碘化亚铜"))

    async def test_username_index_fallback_is_verified_against_real_profile(self):
        index = "1. 碘化亚铜\nhttps://chaoli.club/index.php/member/1286"
        with patch.object(ChaoliService, "_get", AsyncMock(side_effect=ChaoliError("blocked"))), patch(
            "doge_shared.chaoli.LookupService.web_search", AsyncMock(return_value=index)
        ), patch.object(ChaoliService, "_verify_member_name", AsyncMock(return_value=(1286, "碘化亚铜"))):
            self.assertEqual(await ChaoliService._resolve_member_id("碘化亚铜"), (1286, "碘化亚铜"))

    async def test_user_activity_keeps_quote_separate_from_own_text(self):
        with patch.object(ChaoliService, "_resolve_member_id", AsyncMock(return_value=(7, "甲"))), patch.object(ChaoliService, "_get", AsyncMock(return_value=ACTIVITY_HTML)):
            out = await ChaoliService.user("甲", 3)
        self.assertIn("在《一个主题》中更新", out)
        self.assertIn("引用 @B：B 的原话", out)
        self.assertIn("本人新增正文：甲的新回复", out)
        self.assertNotIn("本人新增正文：B 的原话", out)


if __name__ == "__main__":
    unittest.main()
