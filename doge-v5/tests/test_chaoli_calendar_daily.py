from __future__ import annotations

import json
from pathlib import Path
from dataclasses import replace
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/"plugins") not in sys.path:
    sys.path.insert(0,str(ROOT/"plugins"))
pkg=sys.modules.setdefault("data",types.ModuleType("data"))
plugins=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
plugins.__path__=[str(ROOT/"plugins")]
pkg.plugins=plugins

from data.plugins.doge_shared.chaoli import ChaoliService,Floor,ThreadCard
from doge_chaoli.daily_report import (
    DailyTopicEvidence,DailyTopicSummary,DailyEditorialIssue,DailyEditorialBlock,
    _topic_evidence,_summary_evidence_payload,_spread_floors,_render_issue_tex,build_daily_report,editorialize_daily,
)
import doge_chaoli.daily_report as report

def card(tid,updated):
    return ThreadCard(tid,f"主题{tid}","","数学","maths","作者",4,
                      "2024-03-01","新作者",5,updated,"9",
                      f"https://chaoli.club/index.php/{tid}",str(tid))

def floor(number,time,text=None):
    return Floor(number,"作者",4,time,text or "这是针对本帖的数学讨论，有明确的证明步骤和条件。",
                 (),f"https://chaoli.club/index.php/conversation/post/{number}")

def fake_compile(out,tex,stem):
    pdf=out/(stem+".pdf");pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    page=out/(stem+"-page-01.png");page.write_bytes(b"\x89PNG\r\n\x1a\n"+b"0"*2400)
    return pdf,(page,)

class CalendarDateEvidence(unittest.IsolatedAsyncioTestCase):
    async def test_last_redirect_timeout_uses_first_page_only_if_truly_complete(self):
        c=replace(card(42,"2026-10-30 14:00"),replies="2")
        f=[floor(1,"2025-03-01 10:00"),floor(2,"2026-10-29 23:00"),
           floor(3,"2026-10-30 14:00")]
        with (
            patch.object(ChaoliService,"_get",AsyncMock(return_value="<html>no pagination</html>")),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(
                side_effect=RuntimeError("transient last permalink timeout"))),
            patch.object(ChaoliService,"_parse_thread",return_value=("topic",f))
        ):
            ev=await _topic_evidence(c,issue_date="2026-10-30")
        self.assertEqual([x.number for x in ev.activity_floors],[3])
        self.assertFalse(ev.error)
        self.assertEqual(ev.context_pages,(1,))

    async def test_last_redirect_timeout_cannot_hide_long_topic_missing_pages(self):
        c=replace(card(42,"2026-10-30 14:00"),replies="20")
        f=[floor(1,"2025-03-01 10:00"),floor(2,"2026-10-30 14:00")]
        with (
            patch.object(ChaoliService,"_get",AsyncMock(return_value="<html>partial</html>")),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(
                side_effect=RuntimeError("last permalink timeout"))),
            patch.object(ChaoliService,"_parse_thread",return_value=("topic",f))
        ):
            ev=await _topic_evidence(c,issue_date="2026-10-30")
        self.assertIn("timeout",ev.error)
        self.assertFalse(ev.activity_floors)

    async def test_first_page_with_pagination_is_not_treated_as_complete_on_timeout(self):
        c=replace(card(42,"2026-10-30 14:00"),replies="2")
        f=[floor(1,"2025-03-01 10:00"),floor(2,"2026-10-30 13:00"),
           floor(3,"2026-10-30 14:00")]
        with (
            patch.object(ChaoliService,"_get",AsyncMock(
                return_value='<a href="/index.php/42/p2">下页</a>')),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(
                side_effect=RuntimeError("last permalink timeout"))),
            patch.object(ChaoliService,"_parse_thread",return_value=("topic",f))
        ):
            ev=await _topic_evidence(c,issue_date="2026-10-30")
        self.assertIn("timeout",ev.error)
        self.assertFalse(ev.activity_floors)

    async def test_midnight_boundary_excludes_yesterday_and_tomorrow(self):
        c=card(42,"2026-10-30 00:01")
        f=[
            floor(1,"2026-10-29 23:59:59","昨天夜间讨论的原问题"),
            floor(2,"2026-10-30 00:00:00","刚进入今天的首条反例"),
            floor(3,"2026-10-30 23:59:59","今晚的另一条修正"),
            floor(4,"2026-10-31 00:00:00","下一日期不能误算作今日"),
        ]
        with (
            patch.object(ChaoliService,"_get",AsyncMock(return_value="one")),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(return_value=
                         (42,None,"one","https://chaoli.club/index.php/42/p1"))),
            patch.object(ChaoliService,"_parse_thread",return_value=("topic",f))
        ):
            e=await _topic_evidence(c,issue_date="2026-10-31",issue_time="00:00")
        self.assertEqual([x.number for x in e.activity_floors],[2,3])
        self.assertEqual([x.number for x in e.context_floors],[1,2,3])  # 严禁截止后楼层混入历史
        self.assertEqual(e.issue_date,"2026-10-31")
        payload=_summary_evidence_payload(e)
        self.assertEqual(payload["today_update_floor_numbers"],[2,3])
        self.assertEqual(payload["issue_date"],"2026-10-31")
        self.assertEqual(next(x for x in payload["floors"] if x["floor"]==1)["role"],
                         "opening_background")

    async def test_yesterday_evening_updates_not_promoted_to_today(self):
        c=card(43,"2026-10-29 22:46")
        f=[floor(1,"2024-01-01 10:00:00"),floor(4,"2026-10-29 22:46:00")]
        with (
            patch.object(ChaoliService,"_get",AsyncMock(return_value="old")),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(return_value=
                         (43,None,"old","https://chaoli.club/index.php/43/p1"))),
            patch.object(ChaoliService,"_parse_thread",return_value=("topic",f))
        ):
            e=await _topic_evidence(c,issue_date="2026-10-31",issue_time="00:00")
        self.assertFalse(e.activity_floors)
        self.assertEqual(e.context_floors[-1].time,"2026-10-29 22:46:00")

    async def test_natural_day_collects_all_pages_around_date_boundary(self):
        c=card(42,"2026-10-30 18:00")
        page1=[floor(1,"2020-03-01 12:00:00")]
        page2=[floor(11,"2026-10-29 23:59:00"),floor(12,"2026-10-30 00:00:00")]
        page3=[floor(20,"2026-10-30 18:00:00")]
        async def get(path):
            if path.endswith("/p2"):return "second"
            return "first"
        with (
            patch.object(ChaoliService,"_get",side_effect=get),
            patch.object(ChaoliService,"_fetch_exact_ref",AsyncMock(return_value=
                         (42,None,"last","https://chaoli.club/index.php/42/p3"))),
            patch.object(ChaoliService,"_parse_thread",side_effect=lambda html,tid:
                         ("topic",{"first":page1,"second":page2,"last":page3}[html]))
        ):
            e=await _topic_evidence(c,issue_date="2026-10-31",issue_time="00:00")
        self.assertEqual([x.number for x in e.activity_floors],[12,20])
        self.assertEqual(e.context_pages,(1,2,3))
        self.assertFalse(e.recent_window_truncated)

class PublicationSelection(unittest.IsolatedAsyncioTestCase):
    async def test_index_has_three_but_digest_contains_only_true_date_updates(self):
        cards=[
            card(1,"2026-10-30 15:00"),
            card(2,"2026-10-29 22:46"),
            card(3,"2026-10-29 21:18"),
        ]
        fresh=floor(6,"2026-10-30 15:00:00")
        stale=floor(9,"2026-10-29 22:46:00")
        evidence=[
            DailyTopicEvidence(cards[0],fresh,(fresh,),(fresh,),context_floors=(fresh,)),
            DailyTopicEvidence(cards[1],stale,(),(stale,),context_floors=(stale,)),
            DailyTopicEvidence(cards[2],stale,(),(stale,),context_floors=(stale,)),
        ]
        summaries=[DailyTopicSummary(1,"当天仅第一帖新增了一条有证据的回复。",(6,))]
        issue=DailyEditorialIssue("","当日只有一个主题出现新增楼层。",
                                  (DailyEditorialBlock("lead",(1,),"今日新增回复","简要说明"),))
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(report,"collect_daily_evidence",AsyncMock(return_value=evidence)) as collect,
            patch.object(report,"summarize_daily_topics",AsyncMock(return_value=summaries)) as summarize,
            patch.object(report,"editorialize_daily",AsyncMock(return_value=issue)) as editorial,
            patch.object(report,"_compile_issue_tex",side_effect=fake_compile) as compiler
        ):
            first=await build_daily_report(Path(td),cards,"2026-10-30","owner-json",provider=object(),issue_time="00:00")
            second=await build_daily_report(Path(td),cards,"2026-10-30","owner-json",provider=object(),issue_time="00:00")
            manifest=json.loads(first.manifest.read_text())
        self.assertEqual([c.thread_id for c in first.cards],[1])
        self.assertEqual([c.thread_id for c in second.cards],[1])
        self.assertEqual(first.manifest,second.manifest)
        self.assertEqual(manifest["index_topic_count"],3)
        self.assertEqual(manifest["topic_count"],1)
        self.assertEqual(len(manifest["excluded_index_topics"]),2)
        self.assertEqual(manifest["topics"][0]["activity_floors_in_window"],[6])
        collect.assert_awaited_once_with(cards,issue_date="2026-10-30",issue_time="00:00")
        summarize.assert_awaited_once()
        editorial.assert_awaited_once()
        compiler.assert_called_once()

    async def test_no_calendar_day_updates_never_creates_yesterday_news_issue(self):
        c=card(88,"2026-10-29 23:45")
        prev=floor(9,"2026-10-29 23:45:00")
        item=DailyTopicEvidence(c,prev,(),(prev,),context_floors=(prev,))
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(report,"collect_daily_evidence",AsyncMock(return_value=[item])),
            patch.object(report,"summarize_daily_topics",AsyncMock()) as model,
            patch.object(report,"_compile_issue_tex") as compile_pdf
        ):
            with self.assertRaisesRegex(ValueError,"没有核验到本期24小时窗口内的更新楼层"):
                await build_daily_report(Path(td),[c],"2026-10-30","owner-json",provider=object(),issue_time="00:00")
            self.assertFalse(list(Path(td).rglob("*.json")))
            model.assert_not_awaited()
            compile_pdf.assert_not_called()

    async def test_previous_day_valid_issue_is_attached_before_summarization(self):
        c=card(77,"2026-10-30 09:00")
        new=floor(56,"2026-10-30 09:00:00")
        e=DailyTopicEvidence(c,new,(new,),(new,),context_floors=(new,))
        captured=[]
        async def summarize(provider,evidence):
            captured.append(_summary_evidence_payload(evidence[0]))
            return [DailyTopicSummary(77,"今天新证据补全了昨天的反例。",(56,))]
        issue=DailyEditorialIssue("","最新进展与此前讨论持续相关。",
                                  (DailyEditorialBlock("lead",(77,),"补全反例","短导语"),))
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"reports";out.mkdir()
            previous={
                "date":"2026-10-29","topics":[{
                    "thread_id":77,"article":"昨天已经介绍了此前的反例。",
                    "article_evidence_floors":[1,50],
                    "activity_floors_on_date":[50],
                    "article_error":"",
                }]
            }
            (out/"chaoli-daily-2026-10-29-historical.json").write_text(
                json.dumps(previous,ensure_ascii=False),encoding="utf-8")
            with (
                patch.object(report,"collect_daily_evidence",AsyncMock(return_value=[e])),
                patch.object(report,"summarize_daily_topics",side_effect=summarize),
                patch.object(report,"editorialize_daily",AsyncMock(return_value=issue)),
                patch.object(report,"_compile_issue_tex",side_effect=fake_compile)
            ):
                result=await build_daily_report(Path(td),[c],"2026-10-30","owner-json",provider=object(),issue_time="00:00")
        self.assertEqual(result.evidence[0].previous_date,"2026-10-29")
        self.assertIn("昨天已经介绍",captured[0]["previous_issue"]["published_article"])
        self.assertEqual(captured[0]["previous_issue"]["previously_active_floors"],[50])
        self.assertEqual(captured[0]["previous_issue"]["potential_new_since_previous_issue"],[56])

class EditorialQuietDay(unittest.IsolatedAsyncioTestCase):
    async def test_one_minor_reply_remains_brief_not_forced_headline(self):
        c=card(54,"2026-10-30 14:56")
        only=floor(7,"2026-10-30 14:56:00","有人疯了")
        evidence=DailyTopicEvidence(c,only,(only,),(only,),context_floors=(only,))
        provider=types.SimpleNamespace(text_chat=AsyncMock(return_value=types.SimpleNamespace(
            completion_text=json.dumps({
                "headline":"","standfirst":"这一天只有一条轻量评论，未提供新的技术论证。",
                "blocks":[{"level":"brief","thread_ids":[54],
                           "headline":"新增回复没有补充证明","deck":"没有提供新的证明细节"}]
            },ensure_ascii=False))))
        issue=await editorialize_daily(provider,[evidence],
                                      [DailyTopicSummary(54,"今天只出现一条短评，无新证据。",(7,))])
        self.assertEqual(issue.error,"")
        self.assertEqual(len(issue.blocks),1)
        self.assertEqual(issue.blocks[0].level,"brief")
        tex=_render_issue_tex([c],[evidence],[DailyTopicSummary(54,"今天只出现一条短评，无新证据。",(7,))],issue,"2026-10-30","owner-json")
        self.assertNotIn(r"\StoryDeck{",tex)
        self.assertIn("新增回复没有补充证明",tex)


class AcademicFontCoverage(unittest.TestCase):
    def test_publication_explicitly_embeds_greek_capable_opentype(self):
        template=(ROOT/"plugins/doge_chaoli/templates/chaoli_daily.tex").read_text()
        self.assertIn(r"\setmainfont[Path=/usr/share/fonts/urw-base35/",template)
        self.assertIn("NimbusRoman-Regular.otf",template)
        self.assertIn("NimbusRoman-Bold.otf",template)
        self.assertIn(r"\setsansfont[Path=/usr/share/fonts/urw-base35/",template)
        self.assertIn("NimbusSans-Regular.otf",template)
        self.assertIn(r"\setCJKmainfont",template)


class HighVolumeRecency(unittest.TestCase):
    def test_extra_activity_is_covered_by_skim_and_requestable_floor_ids(self):
        self.assertEqual(_spread_floors([floor(1,"2026-10-30 10:00")],0),[])
        c=card(100,"2026-10-30 20:00")
        history=[floor(i,"2020-01-01 00:00:00") for i in range(1,101)]
        updates=[floor(i,f"2026-10-30 12:{i%60:02d}:00",
                       f"第{i}楼报告了一个重要数值计算验证和新的反例，尚有待核实的边界条件。")
                 for i in range(101,221)]
        evidence=DailyTopicEvidence(c,history[0],tuple(updates),tuple(updates[-10:]),
                                    context_floors=tuple(history+updates),
                                    recent_window_truncated=True,
                                    issue_date="2026-10-30")
        p=_summary_evidence_payload(evidence)
        included={x["floor"] for x in p["floors"]}
        skim={x["floor"] for x in p["today_update_skim"]}
        self.assertEqual(p["today_update_total"],120)
        self.assertLessEqual(len(included),52)
        self.assertLessEqual(len(skim),80)
        self.assertTrue(skim.isdisjoint(included))
        self.assertGreater(p["today_update_unread_count"],0)
        self.assertIn("未覆盖",p["coverage_warning"])
        self.assertEqual(p["issue_date"],"2026-10-30")

if __name__=="__main__":
    unittest.main()
