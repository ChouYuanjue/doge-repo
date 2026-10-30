from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
d=sys.modules.setdefault("data",types.ModuleType("data"))
plug=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
plug.__path__=[str(ROOT/"plugins")]
d.plugins=plug

from data.plugins.doge_shared.chaoli import ChaoliService, Floor, ThreadCard
from doge_chaoli.push import (
    SHANGHAI,daily_issue_window,latest_closed_issue_date,
    ChaoliPushStore,DAILY_DEFAULT_TIME,
)
from doge_chaoli.daily_report import (
    DailyTopicEvidence,DailyTopicSummary,DailyEditorialIssue,DailyEditorialBlock,
    _topic_evidence,_signature,build_daily_report,load_latest_daily_report,
    _render_issue_tex,
)
from doge_chaoli.main import DogeChaoli
import doge_chaoli.daily_report as report
import doge_chaoli.main as plugin_module

def card(number=77,updated="2026-10-30 23:44"):
    return ThreadCard(number,"一篇学术帖子","","数学","maths","作者",12,
                      "2026-10-28","回应人",13,updated,"3",
                      f"https://chaoli.club/index.php/{number}","f92")

def floor(no,when):
    return Floor(no,"作者",12,when,"一条有确切日期的论证或修正，含有数学问题的明确限制条件。",(),
                 f"https://chaoli.club/index.php/conversation/post/{no}")

def physical_pdf(out,tex,stem):
    pdf=out/(stem+".pdf")
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    png=out/(stem+"-page-01.png")
    png.write_bytes(b"\x89PNG\r\n\x1a\n"+b"X"*2400)
    return pdf,(png,)

class ScheduledIssueWindowTests(unittest.TestCase):
    def test_default_2345_cutoff_is_previous_day_2345(self):
        start,end=daily_issue_window("2026-10-30")
        self.assertEqual(start.isoformat(),"2026-10-29T23:45:00+08:00")
        self.assertEqual(end.isoformat(),"2026-10-30T23:45:00+08:00")
        self.assertEqual((end-start).total_seconds(),86400)

    def test_custom_2015_changes_both_ends(self):
        start,end=daily_issue_window("2026-10-30","20:15")
        self.assertEqual(start.strftime("%Y-%m-%d %H:%M"),"2026-10-29 20:15")
        self.assertEqual(end.strftime("%Y-%m-%d %H:%M"),"2026-10-30 20:15")
        self.assertEqual((end-start).total_seconds(),86400)

    def test_pre_cutoff_request_refers_to_yesterday(self):
        self.assertEqual(latest_closed_issue_date(
            datetime(2026,10,30,20,0,tzinfo=SHANGHAI)),"2026-10-29")
        self.assertEqual(latest_closed_issue_date(
            datetime(2026,10,30,23,45,tzinfo=SHANGHAI)),"2026-10-30")
        self.assertEqual(latest_closed_issue_date(
            datetime(2026,10,30,19,0,tzinfo=SHANGHAI),"18:00"),"2026-10-30")
        self.assertEqual(latest_closed_issue_date(
            datetime(2026,10,30,17,59,tzinfo=SHANGHAI),"18:00"),"2026-10-29")

    def test_cache_signatures_are_schedule_specific(self):
        c=[card()]
        self.assertNotEqual(_signature(c,"2026-10-30","json","23:45"),
                            _signature(c,"2026-10-30","json","20:15"))
        self.assertEqual(DAILY_DEFAULT_TIME,"23:45")

    def test_bad_time_is_rejected(self):
        with self.assertRaises(ValueError):
            daily_issue_window("2026-10-30","24:00")

class RealReplyTimestampTests(unittest.IsolatedAsyncioTestCase):
    async def test_2345_boundary_both_days_and_next_issue_exact_cutoff(self):
        c=card()
        posts=[
            floor(1,"2026-10-29 23:44:59"),
            floor(2,"2026-10-29 23:45:00"),
            floor(3,"2026-10-30 23:44:59"),
            floor(4,"2026-10-30 23:45:00"),
        ]
        with (
            patch.object(ChaoliService,"_get",AsyncMock(return_value="one")),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(
                return_value=(77,None,"one","https://chaoli.club/index.php/77/p1"))),
            patch.object(ChaoliService,"_parse_thread",return_value=("topic",posts))
        ):
            issue=await _topic_evidence(c,issue_date="2026-10-30")
            next_issue=await _topic_evidence(c,issue_date="2026-10-31")
        self.assertEqual([f.number for f in issue.activity_floors],[2,3])
        self.assertNotIn(4,[f.number for f in issue.context_floors])
        self.assertEqual([f.number for f in next_issue.activity_floors],[4])
        self.assertEqual(issue.window_start,"2026-10-29T23:45:00+08:00")
        self.assertEqual(issue.window_end,"2026-10-30T23:45:00+08:00")

    async def test_1800_custom_cutoff_at_eighteen(self):
        c=card()
        posts=[
            floor(1,"2026-10-29 17:59:59"),
            floor(2,"2026-10-29 18:00:00"),
            floor(3,"2026-10-30 17:59:59"),
            floor(4,"2026-10-30 18:00:00"),
        ]
        with (
            patch.object(ChaoliService,"_get",AsyncMock(return_value="one")),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(
                return_value=(77,None,"one","https://chaoli.club/index.php/77/p1"))),
            patch.object(ChaoliService,"_parse_thread",return_value=("topic",posts))
        ):
            issue=await _topic_evidence(c,issue_date="2026-10-30",issue_time="18:00")
        self.assertEqual([f.number for f in issue.activity_floors],[2,3])
        self.assertEqual(issue.issue_time,"18:00")

class ArchivedReports(unittest.IsolatedAsyncioTestCase):
    async def test_manual_view_before_today_cutoff_reads_only_previous_frozen_issue(self):
        c=card()
        f=floor(3,"2026-10-29 16:45:00")
        e=DailyTopicEvidence(c,f,(f,),(f,),context_floors=(f,))
        edit=DailyEditorialIssue("","上期论坛有一则信息简讯。",
            (DailyEditorialBlock("brief",(77,),"讨论近况","短导语"),))
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(report,"collect_daily_evidence",AsyncMock(return_value=[e])) as collected,
            patch.object(report,"summarize_daily_topics",AsyncMock(return_value=[
                DailyTopicSummary(77,"上期第3楼明确给出新的论证限制。",(3,))
            ])) as summarized,
            patch.object(report,"editorialize_daily",AsyncMock(return_value=edit)),
            patch.object(report,"_compile_issue_tex",side_effect=physical_pdf)
        ):
            previous=await build_daily_report(
                Path(td),[c],"2026-10-29","json",provider=object()
            )
            archive=load_latest_daily_report(
                Path(td),as_of=datetime(2026,10,30,20,0,tzinfo=SHANGHAI)
            )
            self.assertIsNotNone(archive)
            self.assertEqual(archive.date,"2026-10-29")
            self.assertEqual(archive.manifest,previous.manifest)
            self.assertEqual(archive.issue_time,"23:45")
            self.assertIn("23:45",archive.tex)
            self.assertEqual(len(archive.pages),1)
            self.assertEqual(collected.await_count,1)
            self.assertEqual(summarized.await_count,1)

    async def test_future_issue_cannot_be_seen_early(self):
        c=card()
        f=floor(3,"2026-10-30 16:45:00")
        e=DailyTopicEvidence(c,f,(f,),(f,),context_floors=(f,))
        edit=DailyEditorialIssue("","今日论坛有一则简讯。",
            (DailyEditorialBlock("brief",(77,),"相关话题","导语"),))
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(report,"collect_daily_evidence",AsyncMock(return_value=[e])),
            patch.object(report,"summarize_daily_topics",AsyncMock(return_value=[
                DailyTopicSummary(77,"新论证出现。",(3,))
            ])),
            patch.object(report,"editorialize_daily",AsyncMock(return_value=edit)),
            patch.object(report,"_compile_issue_tex",side_effect=physical_pdf)
        ):
            await build_daily_report(Path(td),[c],"2026-10-30","json",provider=object())
            self.assertIsNone(load_latest_daily_report(
                Path(td),as_of=datetime(2026,10,30,20,0,tzinfo=SHANGHAI)))
            self.assertIsNotNone(load_latest_daily_report(
                Path(td),as_of=datetime(2026,10,30,23,47,tzinfo=SHANGHAI)))

    async def test_other_groups_early_issue_is_not_viewable_before_own_cutoff(self):
        c=card()
        f=floor(3,"2026-10-30 14:00:00")
        e=DailyTopicEvidence(c,f,(f,),(f,),context_floors=(f,))
        editor=DailyEditorialIssue("","短讯",
            (DailyEditorialBlock("brief",(77,),"新的讨论","内容"),))
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(report,"collect_daily_evidence",AsyncMock(return_value=[e])),
            patch.object(report,"summarize_daily_topics",AsyncMock(return_value=[
                DailyTopicSummary(77,"第3楼有具体的学术更新。",(3,))
            ])),
            patch.object(report,"editorialize_daily",AsyncMock(return_value=editor)),
            patch.object(report,"_compile_issue_tex",side_effect=physical_pdf)
        ):
            await build_daily_report(Path(td),[c],"2026-10-30","json",
                                     provider=object(),issue_time="18:00")
            now=datetime(2026,10,30,20,0,tzinfo=SHANGHAI)
            self.assertIsNone(load_latest_daily_report(
                Path(td),as_of=now,preferred_time="23:45"))
            self.assertIsNotNone(load_latest_daily_report(
                Path(td),as_of=now,preferred_time="18:00"))

    async def test_manual_chat_is_read_only_and_never_spends_models(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            plugin.data_dir=Path(td)
            plugin.push_store=ChaoliPushStore(Path(td)/"subscriptions.json")
            plugin._daily_report_for_send=AsyncMock()
            plugin._daily_cards_for_send=AsyncMock()
            plugin.context=types.SimpleNamespace(get_using_provider_async=AsyncMock())
            event=types.SimpleNamespace(
                get_group_id=lambda:"777",
                unified_msg_origin="napcat:GroupMessage:777",
            )
            with self.assertRaisesRegex(ValueError,"尚无已生成"):
                await plugin._daily_command(event,"now")
            plugin._daily_report_for_send.assert_not_awaited()
            plugin._daily_cards_for_send.assert_not_awaited()
            plugin.context.get_using_provider_async.assert_not_awaited()

class DynamicProviderRouting(unittest.IsolatedAsyncioTestCase):
    async def test_actual_chat_order_minus_paid_sources_is_used(self):
        def provider(pid,source):
            return types.SimpleNamespace(provider_config={
                "id":pid,"provider_source_id":source,"model":pid.split("/")[-1]},
                meta=lambda:types.SimpleNamespace(id=pid))
        active=provider("workbuddy/deepseek-v4.1-flash","workbuddy")
        wbfallback=provider("workbuddy/glm-5.3","workbuddy")
        freellm=provider("freellmapi/auto","freellmapi")
        charged=provider("deepseek/deepseek-v4-flash","deepseek")
        other=provider("openrouter/z-ai/glm-5.3-flash","openrouter")
        mapping={p.provider_config["id"]:p for p in (wbfallback,freellm,charged,other)}
        plugin=object.__new__(DogeChaoli)
        plugin.data_dir=Path("/tmp/unused")
        plugin._daily_cards_for_send=AsyncMock(return_value=([card()],"json"))
        plugin.context=types.SimpleNamespace(
            get_using_provider_async=AsyncMock(return_value=active),
            get_config=lambda umo=None: {"provider_settings":{
                "fallback_chat_models":list(mapping)}},
            get_provider_by_id=lambda name:mapping.get(name),
        )
        with patch.object(plugin_module,"build_daily_report",AsyncMock(return_value="issue")) as build:
            result=await plugin._daily_report_for_send("2026-10-30","group",issue_time="20:15")
        self.assertEqual(result,"issue")
        self.assertIs(build.await_args.kwargs["provider"],active)
        self.assertEqual(build.await_args.kwargs["fallback_providers"],(wbfallback,freellm))
        self.assertEqual(build.await_args.kwargs["issue_time"],"20:15")

    async def test_paid_session_primary_routes_to_first_free_configured_chat_provider(self):
        def provider(pid,source):
            return types.SimpleNamespace(provider_config={"id":pid,"provider_source_id":source},
                                          meta=lambda:types.SimpleNamespace(id=pid))
        paid=provider("deepseek/deepseek-v4-flash","deepseek")
        free=provider("freellmapi/auto","freellmapi")
        plugin=object.__new__(DogeChaoli)
        plugin.data_dir=Path("/tmp/unused")
        plugin._daily_cards_for_send=AsyncMock(return_value=([card()],"json"))
        plugin.context=types.SimpleNamespace(
            get_using_provider_async=AsyncMock(return_value=paid),
            get_config=lambda umo=None:{"provider_settings":{"fallback_chat_models":["freellmapi/auto"]}},
            get_provider_by_id=lambda _id:free,
        )
        with patch.object(plugin_module,"build_daily_report",AsyncMock(return_value="issue")) as build:
            await plugin._daily_report_for_send("2026-10-30","group")
        self.assertIs(build.await_args.kwargs["provider"],free)
        self.assertEqual(build.await_args.kwargs["fallback_providers"],())

    async def test_no_free_route_raises_without_using_paid_api(self):
        charged=types.SimpleNamespace(provider_config={
            "id":"deepseek/deepseek-v4-flash","provider_source_id":"deepseek"})
        plugin=object.__new__(DogeChaoli)
        plugin.data_dir=Path("/tmp/unused")
        plugin._daily_cards_for_send=AsyncMock(return_value=([card()],"json"))
        plugin.context=types.SimpleNamespace(
            get_using_provider_async=AsyncMock(return_value=charged),
            get_config=lambda umo=None:{"provider_settings":{"fallback_chat_models":[]}},
        )
        with patch.object(plugin_module,"build_daily_report",AsyncMock()) as build:
            with self.assertRaisesRegex(ValueError,"付费"):
                await plugin._daily_report_for_send("2026-10-30","group")
            build.assert_not_awaited()

if __name__=="__main__":
    unittest.main()
