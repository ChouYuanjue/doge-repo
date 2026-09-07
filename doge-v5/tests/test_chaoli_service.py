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
from doge_shared.raw_command import original_message_text


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


    def test_original_transport_text_survives_wake_prefix_stripping(self):
        class Obj:
            message_str = "/chaoli preview https://chaoli.club/index.php/12202"
        class Event:
            message_str = "chaoli preview https://chaoli.club/index.php/12202"
            message_obj = Obj()
        self.assertTrue(original_message_text(Event()).startswith("/chaoli"))

    def test_auto_preview_source_uses_original_transport_text_and_skips_all_slash_commands(self):
        source = (PLUGINS / "doge_chaoli" / "main.py").read_text(encoding="utf-8")
        self.assertIn("text = original_message_text(event).strip()", source)
        self.assertIn('text.lstrip().startswith("/")', source)
        self.assertNotIn('text.startswith("/chaoli")', source)

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
        self.assertIn("精确帖子/楼层", d["commands"]["chaoli"]["summary"])
        self.assertIn("chaoli.daily", ids)
        self.assertIn("authoritative locator", d["commands"]["chaoli"]["summary"])


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


PAGE2_HTML = """
<html><head><title>分页主题 - 超理论坛</title></head><body>
<div class='post' id='p102981' data-id='102981'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/1202'>FatFish</a></h3><span>33楼 </span><a class='time' href='/index.php/conversation/post/102981'>2026-09-05</a></div></div><div class='postBody'>Bourgain 的 4/7 与 3/5 讨论</div></div>
</body></html>
"""


class ChaoliExactPostTests(unittest.IsolatedAsyncioTestCase):
    def test_thread_ref_preserves_pagination_suffix_and_floor_permalink(self):
        self.assertEqual(ChaoliService.parse_thread_ref("https://chaoli.club/index.php/12179/p2#p102981"), (12179, "p2"))
        _, floors = ChaoliService._parse_thread(PAGE2_HTML, 12179)
        self.assertEqual(floors[0].number, 33)
        self.assertEqual(floors[0].url, "https://chaoli.club/index.php/conversation/post/102981")

    async def test_exact_page_anchor_is_authoritative_locator(self):
        url = "https://chaoli.club/index.php/12179/p2#p102981"
        with patch.object(ChaoliService, "_fetch_exact_ref", AsyncMock(return_value=(12179, 102981, PAGE2_HTML, url))) as fetch:
            out = await ChaoliService.read(url)
        fetch.assert_awaited_once_with(url)
        self.assertIn("定位 33楼", out)
        self.assertIn("FatFish", out)
        self.assertIn("Bourgain", out)
        self.assertIn("/conversation/post/102981", out)

    async def test_post_permalink_redirect_result_uses_same_exact_page(self):
        url = "https://chaoli.club/index.php/conversation/post/102981"
        final = "https://chaoli.club/index.php/12179/p2#p102981"
        with patch.object(ChaoliService, "_fetch_exact_ref", AsyncMock(return_value=(12179, 102981, PAGE2_HTML, final))):
            out = await ChaoliService.preview(url)
        self.assertIn("定位 33楼", out)
        self.assertIn("Bourgain", out)


class ChaoliDailySourceTests(unittest.IsolatedAsyncioTestCase):
    PAYLOAD = {
        "results": [
            {
                "conversationId": "12189", "title": "几何勘误", "channelId": "4", "private": "0",
                "startMemberId": "15870", "startMember": "Mimo", "startTime": "1786879561",
                "lastPostMemberId": "16720", "lastPostMember": "Sze Chia-Hao", "lastPostTime": "1788708317",
                "firstPost": "正文", "replies": 10,
            },
            {
                "conversationId": "12142", "title": "抛硬币中的期望", "channelId": "4", "private": "0",
                "startMemberId": "76", "startMember": "Ayachi Nene", "startTime": "1785058132",
                "lastPostMemberId": "16687", "lastPostMember": "AMST", "lastPostTime": "1788707621",
                "firstPost": "科普", "countPosts": "11",
            },
        ],
        "messages": [],
    }
    CATALOG = {"4": ("maths", "数学")}

    def test_channel_catalog_reads_nested_board_tree(self):
        html = """<div id='channelList'><ul>
        <li id='channel-4'><div class='info'><a href='/index.php/conversations/maths' class='channel channel-4'>数学</a></div></li>
        <li id='channel-40'><div class='info'><a href='/index.php/conversations/lang' class='channel channel-40'>语言</a></div></li>
        <li id='channel-43'><div class='info'><a href='/index.php/conversations/collections' class='channel channel-43'>辑录</a></div></li>
        </ul></div>"""
        catalog = ChaoliService._channel_catalog(html)
        self.assertEqual(catalog["4"], ("maths", "数学"))
        self.assertEqual(catalog["40"], ("lang", "语言"))
        self.assertEqual(catalog["43"], ("collections", "辑录"))

    def test_structured_owner_json_results_are_strongly_bound(self):
        cards = ChaoliService._parse_json_cards(self.PAYLOAD, self.CATALOG, 5)
        self.assertEqual([c.thread_id for c in cards], [12189, 12142])
        self.assertEqual((cards[0].channel_slug, cards[0].channel), ("maths", "数学"))
        self.assertEqual((cards[0].author, cards[0].author_id), ("Mimo", 15870))
        self.assertEqual((cards[0].last_author, cards[0].last_author_id), ("Sze Chia-Hao", 16720))
        self.assertEqual(cards[0].replies, "10")
        self.assertIn("2026-", cards[0].updated)

    async def test_daily_cards_use_official_json_post_payload(self):
        with patch.object(ChaoliService, "_daily_json_sync", return_value=(self.PAYLOAD, self.CATALOG)):
            cards = await ChaoliService.daily_json_cards(5)
        self.assertEqual([c.thread_id for c in cards], [12189, 12142])
        self.assertEqual(cards[1].author, "Ayachi Nene")

    def test_daily_json_code_uses_dedicated_proxy_and_post_not_query_get(self):
        source = (PLUGINS / "doge_shared" / "chaoli.py").read_text(encoding="utf-8")
        block = source[source.index("def _daily_json_sync"):source.index("async def daily_json_cards")]
        self.assertIn('session.proxies = {"http": proxy, "https": proxy}', block)
        self.assertIn("DAILY_JSON_URL", block)
        self.assertIn("session.post(", block)
        self.assertIn('data={"search": DAILY_QUERY, "token": token}', block)
        self.assertNotIn("requests.get(DAILY_JSON_URL", block)
        self.assertIn("urlunparse", block)




class ChaoliEmbeddedAnswerTests(unittest.TestCase):
    def test_embedded_best_answer_is_not_attributed_to_parent_floor(self):
        from bs4 import BeautifulSoup
        from doge_shared.chaoli import ChaoliService
        body = BeautifulSoup("""
        <div class='postBody'>
          <p>这是首楼自己的正文。</p>
          <div class='embedded-answer thing hasControls'>
            <div class='postHeader'><div class='info'><h3>最佳回答 <a href='/index.php/member/2'>乙</a></h3></div></div>
            <div class='postBody'><blockquote><cite><a class='link-member' href='/index.php/member/1'>@甲</a></cite>引用</blockquote><p>这是乙的最佳回答正文。</p></div>
          </div>
        </div>
        """, 'lxml').select_one('.postBody')
        own, quotes = ChaoliService._own_text_and_quotes(body)
        self.assertEqual(own, '这是首楼自己的正文。')
        self.assertEqual(quotes, ())
        self.assertNotIn('最佳回答', own)
        self.assertNotIn('这是乙的最佳回答正文', own)

if __name__ == "__main__":
    unittest.main()
