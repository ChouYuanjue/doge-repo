from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from astrbot.api.message_components import File, Image, Node, Nodes, Plain

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

# Production plugins import data.plugins.*. Recreate the namespace for unittest
# discovery, which loads this file independently of the handler tests.
data_pkg = sys.modules.get("data") or types.ModuleType("data")
if not hasattr(data_pkg, "__path__"):
    data_pkg.__path__ = []  # type: ignore[attr-defined]
plugins_pkg = sys.modules.get("data.plugins") or types.ModuleType("data.plugins")
plugins_pkg.__path__ = [str(PLUGINS)]  # type: ignore[attr-defined]
data_pkg.plugins = plugins_pkg  # type: ignore[attr-defined]
sys.modules["data"] = data_pkg
sys.modules["data.plugins"] = plugins_pkg

import doge_chaoli.main as chaoli_main
from doge_chaoli.main import DogeChaoli
from doge_chaoli.daily_report import DailyEditorialBlock, DailyEditorialIssue, DailyReportBundle, DailyTopicEvidence, DailyTopicSummary, _render_issue_tex, _report_markdown, _report_provider_json, _tex_escape, build_daily_report, editorialize_daily, summarize_daily_topics

from doge_chaoli.push import (
    ChaoliDailyPool,
    ChaoliPushStore,
    PushEvent,
    classify_cards,
    format_daily_message,
    format_push_message,
    primed_channel_state,
    shanghai_date,
)
from doge_shared.chaoli import ThreadCard


def card(
    thread_id: int,
    *,
    replies: int = 0,
    title: str | None = None,
    updated: str = "刚刚",
    last_author: str = "乙",
    channel: str = "数学",
    slug: str = "maths",
    crc: str = "crc",
) -> ThreadCard:
    return ThreadCard(
        thread_id=thread_id,
        title=title or f"帖子{thread_id}",
        excerpt="",
        channel=channel,
        channel_slug=slug,
        author="甲",
        author_id=1,
        started="今天",
        last_author=last_author,
        last_author_id=2,
        updated=updated,
        replies=str(replies),
        url=f"https://chaoli.club/index.php/{thread_id}",
        crc=crc,
    )


class ChaoliPushClassifierTests(unittest.TestCase):
    def test_new_thread_and_known_reply_are_distinct(self):
        state = primed_channel_state([card(100, replies=2)])
        events, next_state = classify_cards(
            state,
            [card(101, replies=1), card(100, replies=3)],
        )
        self.assertEqual([(x.kind, x.card.thread_id) for x in events], [
            ("new_thread", 101), ("new_reply", 100)
        ])
        self.assertEqual(events[1].previous_replies, 2)
        self.assertEqual(next_state["max_seen_thread_id"], 101)

    def test_unseen_older_thread_resurfacing_is_reply_not_new_thread(self):
        state = primed_channel_state([card(120, replies=1), card(119, replies=3)])
        events, _ = classify_cards(state, [card(80, replies=9)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "new_reply")
        self.assertTrue(events[0].resurfaced)

    def test_relative_time_title_or_crc_change_does_not_fake_reply(self):
        state = primed_channel_state([card(100, replies=2, updated="1小时前", title="旧标题", crc="a")])
        events, next_state = classify_cards(
            state,
            [card(100, replies=2, updated="2小时前", title="新标题", crc="b")],
        )
        self.assertEqual(events, [])
        self.assertEqual(next_state["threads"]["100"]["replies"], 2)
        self.assertEqual(next_state["threads"]["100"]["crc"], "b")

    def test_enabling_primes_state_without_backfill(self):
        with tempfile.TemporaryDirectory() as td:
            store = ChaoliPushStore(Path(td) / "push.json")
            initial = [card(100, replies=2), card(99, replies=5)]
            self.assertEqual(store.enable("umo", "maths", initial), "enabled")
            state = store.channel_state("umo", "maths")
            events, _ = classify_cards(state or {}, initial)
            self.assertEqual(events, [])
            self.assertEqual((state or {})["max_seen_thread_id"], 100)

    def test_full_site_subscription_covers_specific_boards(self):
        with tempfile.TemporaryDirectory() as td:
            store = ChaoliPushStore(Path(td) / "push.json")
            self.assertEqual(store.enable("umo", "all", [card(100)]), "enabled")
            self.assertEqual(store.enable("umo", "maths", [card(100)]), "covered")
            self.assertEqual(store.channel_slugs("umo"), ["all"])

    def test_message_visibly_separates_new_threads_and_old_thread_replies(self):
        text = format_push_message([
            PushEvent("new_thread", card(101, replies=0)),
            PushEvent("new_reply", card(80, replies=7), previous_replies=6),
        ])
        self.assertIn("新帖（1）", text)
        self.assertIn("【新帖】#101", text)
        self.assertIn("旧帖新回复（1）", text)
        self.assertIn("【旧帖新回复】#80", text)
        self.assertIn("回复 6→7", text)


class ChaoliPushDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_proactive_send_does_not_advance_reply_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            plugin = object.__new__(DogeChaoli)
            plugin.push_store = ChaoliPushStore(Path(td) / "push.json")
            plugin._push_lock = __import__("asyncio").Lock()
            plugin.context = type("Ctx", (), {})()
            plugin.context.send_message = AsyncMock(return_value=False)
            plugin.push_store.enable("napcat:GroupMessage:1", "maths", [card(100, replies=6)])

            latest = AsyncMock(return_value=[card(100, replies=7)])
            with patch.object(chaoli_main, "is_plugin_enabled", AsyncMock(return_value=True)), patch.object(
                chaoli_main.ChaoliService, "latest_cards", latest
            ):
                await plugin._poll_push_once()

            state = plugin.push_store.channel_state("napcat:GroupMessage:1", "maths") or {}
            self.assertEqual(state["threads"]["100"]["replies"], 6)
            plugin.context.send_message.assert_awaited_once()

            plugin.context.send_message.reset_mock()
            plugin.context.send_message.return_value = True
            with patch.object(chaoli_main, "is_plugin_enabled", AsyncMock(return_value=True)), patch.object(
                chaoli_main.ChaoliService, "latest_cards", AsyncMock(return_value=[card(100, replies=7)])
            ):
                await plugin._poll_push_once()

            state = plugin.push_store.channel_state("napcat:GroupMessage:1", "maths") or {}
            self.assertEqual(state["threads"]["100"]["replies"], 7)
            args = plugin.context.send_message.await_args.args
            self.assertEqual(args[0], "napcat:GroupMessage:1")
            rendered = str(args[1])
            self.assertIn("旧帖新回复", rendered)
            self.assertIn("6→7", rendered)


class ChaoliDailyTests(unittest.IsolatedAsyncioTestCase):
    def test_schema1_realtime_subscription_migrates_to_daily_without_backfill(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "push.json"
            path.write_text('{"schema":1,"subscriptions":{"umo":{"channels":{"all":{"max_seen_thread_id":100,"threads":{}}}}}}', encoding="utf-8")
            store = ChaoliPushStore(path)
            self.assertEqual(store.channel_slugs("umo"), ["all"])
            daily = store.daily_state("umo")
            self.assertTrue(daily["enabled"])
            self.assertEqual(daily["time"], "23:45")
            self.assertEqual(daily["last_sent"], shanghai_date())

    def test_realtime_and_daily_switches_are_independent(self):
        with tempfile.TemporaryDirectory() as td:
            store = ChaoliPushStore(Path(td) / "push.json")
            store.enable("umo", "all", [card(100)])
            self.assertTrue(store.daily_state("umo")["enabled"])
            store.disable("umo", None)
            self.assertEqual(store.channel_slugs("umo"), [])
            self.assertTrue(store.daily_state("umo")["enabled"])
            store.enable("umo", "all", [card(100)])
            store.set_daily("umo", False)
            self.assertEqual(store.channel_slugs("umo"), ["all"])
            self.assertFalse(store.daily_state("umo")["enabled"])

    def test_daily_pool_rolls_by_date_and_renders_deterministically(self):
        with tempfile.TemporaryDirectory() as td:
            pool = ChaoliDailyPool(Path(td) / "daily.json")
            pool.merge("2026-09-06", [card(100, replies=3), card(101, replies=1)])
            self.assertEqual([c.thread_id for c in pool.cards("2026-09-06")], [100, 101])
            pool.merge("2026-09-06", [card(101, replies=2)])
            self.assertEqual([c.thread_id for c in pool.cards("2026-09-06")], [101, 100])
            self.assertEqual(pool.cards("2026-09-07"), [])
            text = format_daily_message(pool.cards("2026-09-06"), "2026-09-06", "pool")
            self.assertIn("今日活跃 2 主题", text)
            self.assertIn("来源：pool", text)

    async def test_json_failure_uses_nonempty_daily_pool_without_native_repoll(self):
        with tempfile.TemporaryDirectory() as td:
            plugin = object.__new__(DogeChaoli)
            plugin.daily_pool = ChaoliDailyPool(Path(td) / "daily.json")
            plugin.daily_pool.merge("2026-09-06", [card(100)])
            with patch.object(chaoli_main.ChaoliService, "daily_json_cards", AsyncMock(side_effect=RuntimeError("cf"))), patch.object(
                chaoli_main.ChaoliService, "daily_native_cards", AsyncMock(return_value=[card(999)])
            ) as native:
                cards, source = await plugin._daily_cards_for_send("2026-09-06")
            self.assertEqual([c.thread_id for c in cards], [100])
            self.assertIn("按日活跃池", source)
            native.assert_not_awaited()

    async def test_manual_daily_push_really_sends_and_advances_enabled_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            plugin = object.__new__(DogeChaoli)
            plugin.push_store = ChaoliPushStore(Path(td) / "push.json")
            plugin.daily_pool = ChaoliDailyPool(Path(td) / "daily.json")
            plugin._push_lock = __import__("asyncio").Lock()
            plugin.context = type("Ctx", (), {})()
            plugin.context.send_message = AsyncMock(return_value=True)
            umo = "napcat:GroupMessage:1"
            plugin.push_store.set_daily(umo, True, "23:45")
            plugin.push_store.data["subscriptions"][umo]["daily"]["last_sent"] = "2026-09-06"
            plugin.push_store.save()
            page = Path(td) / "daily-1.png"
            page.write_bytes(b"png")
            manifest = Path(td) / "daily.json"
            manifest.write_text("{}", encoding="utf-8")
            pdf = Path(td) / "daily.pdf"
            pdf.write_bytes(b"%PDF-test")
            c = card(100)
            bundle = DailyReportBundle("2026-09-07", "owner-json", (c,), (DailyTopicEvidence(c, None, (), ()),), (DailyTopicSummary(c.thread_id, "摘要", (1,)),), DailyEditorialIssue("标题", "导语", (DailyEditorialBlock("lead", (c.thread_id,), "标题", "导语句"),)), "# report", "\\documentclass{article}", pdf, (page,), manifest)
            plugin._daily_report_for_send = AsyncMock(return_value=bundle)

            event = type("Event", (), {
                "unified_msg_origin": umo,
                "get_group_id": lambda self: "1",
            })()
            with patch.object(chaoli_main, "is_group_admin", AsyncMock(return_value=True)):
                result = await plugin._daily_command(event, "push")

            self.assertIsNone(result)
            plugin.context.send_message.assert_awaited_once()
            self.assertEqual(plugin.context.send_message.await_args.args[0], umo)
            chain = plugin.context.send_message.await_args.args[1]
            self.assertEqual(len(chain.chain), 1)
            self.assertIsInstance(chain.chain[0], Nodes)
            nodes = chain.chain[0].nodes
            self.assertEqual(len(nodes), 3)  # edition note + one page + PDF
            self.assertIsInstance(nodes[0], Node)
            self.assertIn("超理日报", nodes[0].content[0].text)
            self.assertTrue(any(isinstance(x, Image) for x in nodes[1].content))
            self.assertTrue(any(isinstance(x, File) for x in nodes[-1].content))
            self.assertEqual(plugin.push_store.daily_state(umo)["last_sent"], shanghai_date())

    async def test_daily_forward_serializes_page_and_pdf_inside_nodes(self):
        with tempfile.TemporaryDirectory() as td:
            plugin = object.__new__(DogeChaoli)
            plugin.context = type("Ctx", (), {})()
            plugin.context.get_platform_inst = lambda _pid: None
            page = Path(td) / "page.png"
            from PIL import Image as PILImage
            PILImage.new("RGB", (8, 8), "white").save(page, "PNG")
            pdf = Path(td) / "daily.pdf"
            pdf.write_bytes(b"%PDF-1.5\n%%EOF\n")
            manifest = Path(td) / "daily.json"
            manifest.write_text("{}", encoding="utf-8")
            c = card(100)
            bundle = DailyReportBundle(
                "2026-09-07", "owner-json", (c,),
                (DailyTopicEvidence(c, None, (), ()),),
                (DailyTopicSummary(c.thread_id, "摘要", (1,)),),
                DailyEditorialIssue("标题", "导语", (DailyEditorialBlock("lead", (c.thread_id,), "标题", "导语句"),)),
                "# report", "\\documentclass{article}", pdf, (page,), manifest,
            )
            chain = await plugin._daily_report_chain("napcat:GroupMessage:1", bundle)
            self.assertEqual(len(chain.chain), 1)
            payload = await chain.chain[0].to_dict()
            messages = payload["messages"]
            self.assertEqual(len(messages), 3)
            page_content = messages[1]["data"]["content"]
            image_segments = [x for x in page_content if x.get("type") == "image"]
            self.assertEqual(len(image_segments), 1)
            self.assertTrue(image_segments[0]["data"]["file"].startswith("base64://"))
            pdf_content = messages[2]["data"]["content"]
            file_segments = [x for x in pdf_content if x.get("type") == "file"]
            self.assertEqual(len(file_segments), 1)
            self.assertEqual(file_segments[0]["data"]["name"], "Chaoli-Daily-2026-09-07.pdf")



    async def test_failed_manual_daily_push_does_not_advance_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            plugin = object.__new__(DogeChaoli)
            plugin.push_store = ChaoliPushStore(Path(td) / "push.json")
            plugin.daily_pool = ChaoliDailyPool(Path(td) / "daily.json")
            plugin._push_lock = __import__("asyncio").Lock()
            plugin.context = type("Ctx", (), {})()
            plugin.context.send_message = AsyncMock(return_value=False)
            umo = "napcat:GroupMessage:1"
            plugin.push_store.set_daily(umo, True, "23:45")
            plugin.push_store.data["subscriptions"][umo]["daily"]["last_sent"] = "2026-09-06"
            plugin.push_store.save()
            page = Path(td) / "daily-1.png"
            page.write_bytes(b"png")
            manifest = Path(td) / "daily.json"
            manifest.write_text("{}", encoding="utf-8")
            pdf = Path(td) / "daily.pdf"
            pdf.write_bytes(b"%PDF-test")
            c = card(100)
            bundle = DailyReportBundle("2026-09-07", "owner-json", (c,), (DailyTopicEvidence(c, None, (), ()),), (DailyTopicSummary(c.thread_id, "摘要", (1,)),), DailyEditorialIssue("标题", "导语", (DailyEditorialBlock("lead", (c.thread_id,), "标题", "导语句"),)), "# report", "\\documentclass{article}", pdf, (page,), manifest)
            plugin._daily_report_for_send = AsyncMock(return_value=bundle)
            event = type("Event", (), {
                "unified_msg_origin": umo,
                "get_group_id": lambda self: "1",
            })()

            with patch.object(chaoli_main, "is_group_admin", AsyncMock(return_value=True)):
                with self.assertRaisesRegex(ValueError, "水位未推进"):
                    await plugin._daily_command(event, "push")
            self.assertEqual(plugin.push_store.daily_state(umo)["last_sent"], "2026-09-06")

    async def test_multiple_due_groups_share_one_daily_source_fetch(self):
        with tempfile.TemporaryDirectory() as td:
            plugin = object.__new__(DogeChaoli)
            plugin.push_store = ChaoliPushStore(Path(td) / "push.json")
            plugin._push_lock = __import__("asyncio").Lock()
            plugin.context = type("Ctx", (), {})()
            plugin.context.send_message = AsyncMock(return_value=True)
            for umo in ("napcat:GroupMessage:1", "napcat:GroupMessage:2"):
                plugin.push_store.set_daily(umo, True, "00:00")
                plugin.push_store.data["subscriptions"][umo]["daily"]["last_sent"] = ""
            plugin.push_store.save()
            page = Path(td) / "daily-1.png"
            page.write_bytes(b"png")
            manifest = Path(td) / "daily.json"
            manifest.write_text("{}", encoding="utf-8")
            pdf = Path(td) / "daily.pdf"
            pdf.write_bytes(b"%PDF-test")
            c = card(100)
            bundle = DailyReportBundle("2026-09-07", "owner-json", (c,), (DailyTopicEvidence(c, None, (), ()),), (DailyTopicSummary(c.thread_id, "摘要", (1,)),), DailyEditorialIssue("标题", "导语", (DailyEditorialBlock("lead", (c.thread_id,), "标题", "导语句"),)), "# report", "\\documentclass{article}", pdf, (page,), manifest)
            build = AsyncMock(return_value=bundle)
            plugin._daily_report_for_send = build
            with patch.object(chaoli_main, "is_plugin_enabled", AsyncMock(return_value=True)):
                await plugin._poll_daily_once()
            build.assert_awaited_once()
            self.assertEqual(plugin.context.send_message.await_count, 2)
            for call in plugin.context.send_message.await_args_list:
                chain = call.args[1]
                self.assertEqual(len(chain.chain), 1)
                self.assertIsInstance(chain.chain[0], Nodes)
                nodes = chain.chain[0].nodes
                self.assertTrue(any(isinstance(x, Image) for x in nodes[1].content))
                self.assertTrue(any(isinstance(x, File) for x in nodes[-1].content))
            for umo in ("napcat:GroupMessage:1", "napcat:GroupMessage:2"):
                self.assertEqual(plugin.push_store.daily_state(umo)["last_sent"], shanghai_date())




class ChaoliDailyReportTests(unittest.TestCase):
    def test_report_keeps_all_index_topics_and_marks_evidence_failure(self):
        c1 = card(100, replies=7, title="A")
        c2 = card(101, replies=3, title="B")
        f1 = chaoli_main.ChaoliService._parse_thread("""<html><title>A - 超理论坛</title><div class='post' data-id='1' id='p1'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/1'>甲</a></h3><span>1楼</span><a class='time' href='/index.php/conversation/post/1' title='2026-09-07 20:00:00'></a></div></div><div class='postBody'><p>正文</p></div></div></html>""", 100)[1][0]
        evidence = [
            DailyTopicEvidence(c1, f1, (f1,), (f1,)),
            DailyTopicEvidence(c2, None, (), (), "ChaoliError: failed"),
        ]
        md = _report_markdown([c1, c2], evidence, [DailyTopicSummary(100, "A 的编辑摘要。", (1,)), DailyTopicSummary(101, "", (), "missing")], "2026-09-07", "owner-json")
        self.assertIn("## 01 · A", md)
        self.assertIn("## 02 · B", md)
        self.assertIn("正文证据本次未能补全", md)
        self.assertIn("A 的编辑摘要", md)
        self.assertIn("不读取群聊上下文或豆子人格", md)
        self.assertNotIn("今日概览", md)
        self.assertNotIn("活跃主题索引", md)
        self.assertNotIn("逐主题证据", md)

    def test_report_uses_24h_floor_window_and_exact_permalinks(self):
        c = card(100, replies=2, title="主题")
        first = chaoli_main.ChaoliService._parse_thread("""<html><title>主题 - 超理论坛</title><div class='post' data-id='1' id='p1'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/1'>甲</a></h3><span>1楼</span><a class='time' href='/index.php/conversation/post/1' title='2026-09-01 10:00:00'></a></div></div><div class='postBody'><p>主题背景</p></div></div></html>""", 100)[1][0]
        floor = chaoli_main.ChaoliService._parse_thread("""<html><title>主题 - 超理论坛</title><div class='post' data-id='9' id='p9'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/2'>乙</a></h3><span>3楼</span><a class='time' href='/index.php/conversation/post/9' title='2026-09-07 21:00:00'></a></div></div><div class='postBody'><p>今天的更新</p></div></div></html>""", 100)[1][0]
        md = _report_markdown([c], [DailyTopicEvidence(c, first, (floor,), (floor,))], [DailyTopicSummary(100, "今天有明确推进。", (3,))], "2026-09-07", "owner-json")
        self.assertIn("过去24小时 1 个公开楼层更新", md)
        self.assertIn("https://chaoli.club/index.php/conversation/post/9", md)
        self.assertIn("今天的更新", md)


class ChaoliEditionFreezeTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_signature_reuses_frozen_pdf_without_recollecting(self):
        c = card(100, replies=8, title="冻结版主题")
        evidence = [DailyTopicEvidence(c, None, (), ())]
        summaries = [DailyTopicSummary(100, "冻结版正文。", (1,))]
        editorial = DailyEditorialIssue(
            "冻结版主标题",
            "相同主题签名再次请求时，应直接复用已经完成的版次。",
            (DailyEditorialBlock("lead", (100,), "冻结版头条", "冻结版导语"),),
        )

        def fake_compile(out: Path, tex_text: str, stem: str):
            pdf = out / f"{stem}.pdf"
            page = out / f"{stem}-page-01.png"
            pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
            page.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2048)
            return pdf, (page,)

        with tempfile.TemporaryDirectory() as td, patch(
            "doge_chaoli.daily_report.collect_daily_evidence", AsyncMock(return_value=evidence)
        ) as collect, patch(
            "doge_chaoli.daily_report.summarize_daily_topics", AsyncMock(return_value=summaries)
        ) as summarize, patch(
            "doge_chaoli.daily_report.editorialize_daily", AsyncMock(return_value=editorial)
        ) as edit, patch(
            "doge_chaoli.daily_report._compile_issue_tex", side_effect=fake_compile
        ) as compile_issue:
            first = await build_daily_report(Path(td), [c], "2026-09-09", "owner-json", provider=object())
            second = await build_daily_report(Path(td), [c], "2026-09-09", "owner-json", provider=object())

        self.assertEqual(first.manifest, second.manifest)
        self.assertEqual(first.pdf, second.pdf)
        self.assertEqual(first.pages, second.pages)
        self.assertEqual(second.editorial.headline, "冻结版主标题")
        collect.assert_awaited_once()
        summarize.assert_awaited_once()
        edit.assert_awaited_once()
        compile_issue.assert_called_once()



class ChaoliReportProviderPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_provider_private_query_gets_explicit_report_controls(self):
        class Provider:
            def get_model(self):
                return "deepseek-v4-flash"

            async def _query(self, payload, tools, *, request_max_retries=None):
                self.payload = payload
                self.tools = tools
                self.retries = request_max_retries
                return type("Resp", (), {"completion_text": '{"ok":true}'})()

        provider = Provider()
        resp = await _report_provider_json(provider, "SYSTEM", "PROMPT", max_tokens=3210)
        self.assertEqual(resp.completion_text, '{"ok":true}')
        self.assertEqual(provider.payload["temperature"], 0.0)
        self.assertEqual(provider.payload["max_tokens"], 3210)
        self.assertEqual(provider.payload["response_format"], {"type": "json_object"})
        self.assertEqual(provider.payload["thinking"], {"type": "disabled"})
        self.assertEqual(provider.payload["messages"][0], {"role": "system", "content": "SYSTEM"})
        self.assertIsNone(provider.tools)
        self.assertEqual(provider.retries, 1)

class ChaoliDailySummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_provider_is_direct_and_floor_refs_are_validated(self):
        c = card(100, replies=2, title="主题")
        floor = chaoli_main.ChaoliService._parse_thread("""<html><title>主题 - 超理论坛</title><div class='post' data-id='9' id='p9'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/2'>乙</a></h3><span>3楼</span><a class='time' href='/index.php/conversation/post/9' title='2026-09-07 21:00:00'></a></div></div><div class='postBody'><p>今天的更新</p></div></div></html>""", 100)[1][0]
        provider = type("Provider", (), {})()
        provider.text_chat = AsyncMock(return_value=type("Resp", (), {"completion_text": '{"topics":[{"thread_id":100,"summary":"围绕主题继续讨论，并在今天得到更新。","evidence_floors":[3]}]}'})())
        rows = await summarize_daily_topics(provider, [DailyTopicEvidence(c, floor, (floor,), (floor,))])
        self.assertEqual(rows[0].evidence_floors, (3,))
        self.assertIn("得到更新", rows[0].text)
        kwargs = provider.text_chat.await_args.kwargs
        self.assertEqual(kwargs["temperature"], 0.0)
        self.assertEqual(kwargs["thinking"], {"type": "disabled"})
        self.assertNotIn("contexts", kwargs)
        self.assertNotIn("session_id", kwargs)

    async def test_summary_with_fake_floor_is_rejected(self):
        c = card(100, replies=2, title="主题")
        floor = chaoli_main.ChaoliService._parse_thread("""<html><title>主题 - 超理论坛</title><div class='post' data-id='9' id='p9'><div class='postHeader'><div class='info'><h3><a href='/index.php/member/2'>乙</a></h3><span>3楼</span><a class='time' href='/index.php/conversation/post/9' title='2026-09-07 21:00:00'></a></div></div><div class='postBody'><p>今天的更新</p></div></div></html>""", 100)[1][0]
        provider = type("Provider", (), {})()
        provider.text_chat = AsyncMock(return_value=type("Resp", (), {"completion_text": '{"topics":[{"thread_id":100,"summary":"伪造支持。","evidence_floors":[99]}]}'})())
        rows = await summarize_daily_topics(provider, [DailyTopicEvidence(c, floor, (floor,), (floor,))])
        self.assertEqual(rows[0].text, "")
        self.assertEqual(rows[0].error, "invalid_evidence_refs")


class ChaoliEditorialIssueTests(unittest.IsolatedAsyncioTestCase):
    async def test_editorial_issue_enforces_one_lead_and_full_thread_coverage(self):
        c1 = card(100, replies=8, title="主讨论")
        c2 = card(101, replies=1, title="轻量更新")
        provider = type("Provider", (), {})()
        provider.text_chat = AsyncMock(return_value=type("Resp", (), {"completion_text": '{"headline":"证明细节继续收紧","standfirst":"主讨论今天出现实质推进，另一条只是轻量更新。","blocks":[{"level":"lead","thread_ids":[100],"headline":"构造从直觉走向细节","deck":"主讨论围绕具体证明继续推进。"},{"level":"brief","thread_ids":[101],"headline":"另一帖只有轻量更新","deck":"该主题今天没有新的实质论证。"}]}'})())
        e1 = DailyTopicEvidence(c1, None, (), ())
        e2 = DailyTopicEvidence(c2, None, (), ())
        issue = await editorialize_daily(provider, [e1, e2], [DailyTopicSummary(100, "主讨论摘要", (1,)), DailyTopicSummary(101, "轻量更新摘要", (1,))])
        self.assertEqual(issue.error, "")
        self.assertEqual(sum(1 for x in issue.blocks if x.level == "lead"), 1)
        self.assertEqual({tid for x in issue.blocks for tid in x.thread_ids}, {100, 101})
        self.assertEqual(issue.blocks[0].level, "lead")

    async def test_editorial_invalid_duplicate_thread_falls_back_safely(self):
        c1 = card(100, replies=8, title="主讨论")
        c2 = card(101, replies=1, title="轻量更新")
        provider = type("Provider", (), {})()
        provider.text_chat = AsyncMock(return_value=type("Resp", (), {"completion_text": '{"headline":"x","standfirst":"y","blocks":[{"level":"lead","thread_ids":[100],"headline":"a","deck":"b"},{"level":"feature","thread_ids":[100],"headline":"c","deck":"d"}]}'})())
        issue = await editorialize_daily(provider, [DailyTopicEvidence(c1, None, (), ()), DailyTopicEvidence(c2, None, (), ())], [DailyTopicSummary(100, "A", (1,)), DailyTopicSummary(101, "B", (1,))])
        self.assertTrue(issue.error)
        self.assertEqual({tid for x in issue.blocks for tid in x.thread_ids}, {100, 101})
        self.assertEqual(sum(1 for x in issue.blocks if x.level == "lead"), 1)

    def test_tex_is_formal_academic_bulletin_not_card_html(self):
        c1 = card(100, replies=8, title="主讨论")
        c2 = card(101, replies=2, title="次要讨论")
        c3 = card(102, replies=1, title="轻量讨论")
        evidence = [
            DailyTopicEvidence(c1, None, (), ()),
            DailyTopicEvidence(c2, None, (), ()),
            DailyTopicEvidence(c3, None, (), ()),
        ]
        summary = [
            DailyTopicSummary(100, "这是一段经过证据校验的正式稿件。", (1,)),
            DailyTopicSummary(101, "这是第二篇经过证据校验的正式稿件。", (1,)),
            DailyTopicSummary(102, "这是一条经过证据校验的简讯。", (1,)),
        ]
        issue = DailyEditorialIssue(
            "具体的日报主标题",
            "这是整期导语，不是帖子列表。",
            (
                DailyEditorialBlock("lead", (100,), "真正的头条标题", "头条导语句。"),
                DailyEditorialBlock("feature", (101,), "第二篇标题", "第二篇导语句。"),
                DailyEditorialBlock("brief", (102,), "第三篇标题", "第三篇导语句。"),
            ),
        )
        rendered = _render_issue_tex([c1, c2, c3], evidence, summary, issue, "2026-09-08", "owner-json")
        self.assertIn("超理日报", rendered)
        self.assertIn("TECHNICAL \\& ACADEMIC BULLETIN", rendered)
        self.assertIn("\\begin{multicols}{2}", rendered)
        self.assertNotIn("\\begin{multicols}{3}", rendered)
        self.assertIn("研究简报", rendered)
        self.assertIn("本期导读", rendered)
        self.assertIn("专题讨论", rendered)
        self.assertNotIn("\\newpage", rendered)
        self.assertNotIn("本期索引", rendered)
        self.assertNotIn("\\IndexItem{", rendered)
        self.assertNotIn("本期其余", rendered)
        self.assertIn("\\fancyhead", rendered)
        self.assertIn("\\MethodNote", rendered)
        self.assertNotIn("ContentsItem", rendered)
        self.assertNotIn("\\vfill", rendered)
        self.assertIn("真正的头条标题", rendered)
        self.assertIn("这是整期导语", rendered)
        self.assertNotIn("<html", rendered.lower())
        self.assertNotIn("今日概览", rendered)
        self.assertNotIn("逐主题证据", rendered)

    def test_medium_bulletin_balances_pages_and_keeps_evidence_index(self):
        cards = [card(100 + i, replies=8 - i, title=f"讨论{i}") for i in range(5)]
        evidence = [DailyTopicEvidence(c, None, (), ()) for c in cards]
        summary = [
            DailyTopicSummary(c.thread_id, "经过证据校验的正文。" * (12 if i < 2 else 5), (1,))
            for i, c in enumerate(cards)
        ]
        issue = DailyEditorialIssue(
            "期标题",
            "整期导语。",
            (
                DailyEditorialBlock("lead", (100,), "专题标题", "专题导语。"),
                DailyEditorialBlock("feature", (101,), "研究札记", "札记导语。"),
                DailyEditorialBlock("brief", (102,), "简讯二", "简讯导语。"),
                DailyEditorialBlock("brief", (103,), "简讯三", "简讯导语。"),
                DailyEditorialBlock("brief", (104,), "简讯四", "简讯导语。"),
            ),
        )
        rendered = _render_issue_tex(cards, evidence, summary, issue, "2026-09-08", "owner-json")
        self.assertIn("\\newpage", rendered)
        self.assertIn("研究简报", rendered)
        self.assertIn("本期索引", rendered)
        self.assertIn("\\IndexItem", rendered)
        self.assertNotIn("\\begin{multicols}{3}", rendered)

    def test_tex_escape_neutralizes_forum_commands(self):
        raw = r"\\input{/etc/passwd} % # $ & _ ^ ~ {x}"
        escaped = _tex_escape(raw)
        self.assertNotIn(r"\\input{/etc/passwd}", escaped)
        for token in (r"\%", r"\#", r"\$", r"\&", r"\_", r"\{", r"\}"):
            self.assertIn(token, escaped)


if __name__ == "__main__":
    unittest.main()
