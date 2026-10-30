from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
pkg=sys.modules.setdefault("data",types.ModuleType("data"))
plug=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
plug.__path__=[str(ROOT/"plugins")]
pkg.plugins=plug

from data.plugins.doge_shared.chaoli import ChaoliService,Floor,ThreadCard
from doge_chaoli.daily_report import (
    DailyTopicEvidence,DailyTopicSummary,DailyEditorialIssue,DailyEditorialBlock,
    _attach_previous_issue,_expand_context_requests,_previous_issue_topics,
    _summary_evidence_payload,_render_issue_tex,_source_line,_tex_inline,summarize_daily_topics
)

def floor(number,text=None):
    return Floor(number,"甲",12,f"2026-10-30 12:{number%60:02d}:00",
                 text or f"关于第{number}楼的实际数学讨论和前提条件，进一步区分命题与反例。",
                 (),f"https://chaoli.club/index.php/conversation/post/{number}")

def card(tid=42):
    return ThreadCard(tid,"一个有长期背景的讨论","", "数学","maths","甲",12,
                      "2020-01-01","乙",13,"2026-10-30","98",
                      f"https://chaoli.club/index.php/{tid}","abc")

class ContextWindowTests(unittest.TestCase):
    def test_origin_prior_turn_today_and_prev_issue_have_distinct_roles(self):
        history=[floor(i) for i in range(1,81)]
        item=DailyTopicEvidence(card(),history[0],tuple(history[-3:]),tuple(history[-8:]),
                               context_floors=tuple(history),previous_date="2026-10-29",
                               previous_article="昨天已经报道了初步论证和第二个反例。",
                               previous_evidence_floors=(3,25),previous_activity_floors=(75,76),
                               context_pages=tuple(range(1,9)),last_page_number=8)
        payload=_summary_evidence_payload(item)
        items={x["floor"]:x for x in payload["floors"]}
        self.assertEqual(items[1]["role"],"opening_background")
        self.assertEqual(items[78]["role"],"today_update")
        self.assertEqual(items[77]["role"],"prior_turn_context")
        self.assertEqual(items[25]["role"],"previously_discussed")
        self.assertEqual(payload["previous_issue"]["date"],"2026-10-29")
        self.assertEqual(payload["previous_issue"]["potential_new_since_previous_issue"],[78,79,80])
        self.assertLessEqual(payload["provided_floor_count"],52)

    def test_identical_issue_title_and_lead_title_are_not_printed_twice(self):
        c=card()
        item=DailyTopicEvidence(c,floor(1),(),())
        lead=DailyEditorialBlock("lead",(42,),"同一个研究主题","短导语")
        issue=DailyEditorialIssue("同一个研究主题","这是一份用来核实排版的报刊导语。",(lead,))
        tex=_render_issue_tex([c],[item],[DailyTopicSummary(42,"讨论正文。",(1,))],
                              issue,"2026-10-30","owner-json")
        self.assertEqual(tex.count("同一个研究主题"),1)
        self.assertIn("这是一份用来核实排版的报刊导语",tex)

    def test_source_line_links_the_actual_cited_floor(self):
        a=floor(12)
        b=floor(19)
        item=DailyTopicEvidence(card(),a,(b,),(b,),context_floors=(a,b))
        rendered=_source_line(item,DailyTopicSummary(42,"具体的更新。",(12,19)))
        self.assertIn(r"\href{https://chaoli.club/index.php/conversation/post/12}{12楼}",rendered)
        self.assertIn(r"\href{https://chaoli.club/index.php/conversation/post/19}{19楼}",rendered)
        self.assertNotIn(r"\input",rendered)

    def test_safe_inline_academic_math_and_untrusted_tex_are_separate(self):
        rendered=_tex_inline(r"积分 $\int_0^1 x^2\,dx$，比例 $\frac{1}{2}$。")
        self.assertIn(r"\(\int_0^1 x^2\,dx\)",rendered)
        self.assertIn(r"\(\frac{1}{2}\)",rendered)
        attack=_tex_inline(r"公式 $\input{/etc/passwd}$ 不得执行。")
        self.assertNotIn(r"\input{/etc/passwd}",attack)
        self.assertIn(r"\textbackslash{}input",attack)
        self.assertNotIn(r"\(12 and 20\)",_tex_inline("$12 and $20"))

    def test_length_is_chosen_by_new_activity_not_old_thread_size(self):
        history=[floor(i) for i in range(1,151)]
        activity=(floor(150,"收到，先谢谢大家。"),)
        item=DailyTopicEvidence(card(),history[0],activity,activity,
                                context_floors=tuple(history),
                                context_pages=(1,6,9,12,15),last_page_number=15)
        payload=_summary_evidence_payload(item)
        self.assertEqual(payload["recommended_chars"],"100-220")
        self.assertEqual(payload["floors"][-1]["floor"],150)
        self.assertEqual(payload["floors"][0]["floor"],1)

    def test_prior_issue_only_uses_immediately_previous_successful_publication(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)
            prefix="chaoli-daily-2026-10-29-"
            good={"date":"2026-10-29","topics":[
                {"thread_id":42,"article":"昨天完成了前半部分讨论。",
                 "article_evidence_floors":[1,20],
                 "activity_floors_24h":[19,20],"article_error":""}
            ]}
            (out/(prefix+"good.json")).write_text(json.dumps(good))
            previous=_previous_issue_topics(out,"2026-10-30")
            self.assertIn(42,previous)
            item=DailyTopicEvidence(card(),floor(1),(floor(21),),(floor(21),))
            attached=_attach_previous_issue([item],previous)[0]
            self.assertEqual(attached.previous_evidence_floors,(1,20))
            self.assertEqual(attached.previous_date,"2026-10-29")
            self.assertEqual(_previous_issue_topics(out,"2026-11-01"),{})
            bad=dict(good)
            bad["topics"]=[{"thread_id":42,"article":"","article_error":"AuthenticationError: 401"}]
            (out/(prefix+"bad.json")).write_text(json.dumps(bad))
            self.assertIn(42,_previous_issue_topics(out,"2026-10-30"))

class GuidedContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_previous_published_article_is_visible_as_explicit_comparison(self):
        history=[floor(1),floor(57)]
        item=DailyTopicEvidence(card(),history[0],(history[-1],),(history[-1],),
                                context_floors=tuple(history),previous_date="2026-10-29",
                                previous_article="昨天发表过该主题关于初步推导的说明。",
                                previous_evidence_floors=(1,42))
        payload=_summary_evidence_payload(item)
        self.assertIn("昨天发表过",payload["previous_issue"]["published_article"])
        self.assertEqual(payload["previous_issue"]["previously_cited_floors"],[1,42])
        self.assertTrue(any(f["role"]=="today_update" for f in payload["floors"]))

    async def test_model_requests_missing_floor_and_cites_new_update(self):
        history=[floor(1),floor(2),floor(55),floor(56)]
        item=DailyTopicEvidence(card(),history[0],(history[-1],),(history[-1],),
                                context_floors=tuple(history),last_page_number=6)
        class Provider:
            async def text_chat(self,**kwargs):
                return types.SimpleNamespace(completion_text=json.dumps({
                    "topics":[{"thread_id":42,"article":"今天第56楼提出了一个新反例。",
                               "evidence_floors":[1,56],
                               "context_requests":[33,300,1]}]}))
        result=(await summarize_daily_topics(Provider(),[item]))[0]
        self.assertEqual(result.context_requests,(33,))
        self.assertEqual(result.evidence_floors,(1,56))

    async def test_invalid_model_floor_is_rewritten_not_silently_filled(self):
        history=[floor(1),floor(56)]
        item=DailyTopicEvidence(card(),history[0],(history[-1],),(history[-1],),
                                context_floors=tuple(history))
        provider=types.SimpleNamespace(text_chat=AsyncMock(side_effect=[
            types.SimpleNamespace(completion_text=json.dumps({
                "topics":[{"thread_id":42,"article":"第999楼发现了突破。",
                           "evidence_floors":[999]}]})),
            types.SimpleNamespace(completion_text=json.dumps({
                "topics":[{"thread_id":42,
                           "article":"目前只有第56楼的一条评论，尚无证明。",
                           "evidence_floors":[1,56]}]})),
        ]))
        result=(await summarize_daily_topics(provider,[item]))[0]
        self.assertEqual(provider.text_chat.await_count,2)
        self.assertEqual(result.evidence_floors,(1,56))
        self.assertEqual(result.error,"")
        self.assertNotIn("999",result.text)

    async def test_repeated_fake_floor_still_fails_after_single_repair(self):
        history=[floor(1),floor(56)]
        item=DailyTopicEvidence(card(),history[0],(history[-1],),(history[-1],),
                                context_floors=tuple(history))
        provider=types.SimpleNamespace(text_chat=AsyncMock(return_value=
            types.SimpleNamespace(completion_text=json.dumps({
                "topics":[{"thread_id":42,"article":"不存在的来源。",
                           "evidence_floors":[999]}]}))))
        result=(await summarize_daily_topics(provider,[item]))[0]
        self.assertEqual(provider.text_chat.await_count,2)
        self.assertEqual(result.error,"invalid_evidence_refs")
        self.assertEqual(result.text,"")

    async def test_today_update_required_for_publication(self):
        history=[floor(1),floor(56)]
        item=DailyTopicEvidence(card(),history[0],(history[-1],),(history[-1],),
                                context_floors=tuple(history))
        class Provider:
            async def text_chat(self,**kwargs):
                return types.SimpleNamespace(completion_text=json.dumps({
                    "topics":[{"thread_id":42,"article":"旧帖子原本的观点。",
                               "evidence_floors":[1]}]}))
        result=(await summarize_daily_topics(Provider(),[item]))[0]
        self.assertEqual(result.error,"missing_recent_evidence")
        self.assertFalse(result.text)


    async def test_build_report_rechecks_model_requested_floor_once(self):
        import doge_chaoli.daily_report as report_module
        with tempfile.TemporaryDirectory() as td:
            first=floor(1)
            recent=floor(56)
            historical=floor(33)
            base=DailyTopicEvidence(card(),first,(recent,),(recent,),
                                    context_floors=(first,recent),last_page_number=6)
            expanded=replace(base,context_floors=(first,historical,recent),
                             focused_floors=(33,))
            initial=DailyTopicSummary(42,"刚出现新回复。",(56,),context_requests=(33,))
            updated=DailyTopicSummary(42,"结合第33楼的论证，第56楼增加了新的限制条件。",(33,56))
            editor=DailyEditorialIssue("","本期收录了持续演进的讨论。",
                                      (DailyEditorialBlock("lead",(42,),"最新进展","关注新前提"),))
            def fake_compile(out,tex,stem):
                pdf=out/(stem+".pdf")
                png=out/(stem+"-01.png")
                pdf.write_bytes(b"%PDF-1.6\n")
                png.write_bytes(b"PNG_RENDER_DATA"*200)
                return pdf,(png,)
            with (
                patch.object(report_module,"collect_daily_evidence",AsyncMock(return_value=[base])),
                patch.object(report_module,"summarize_daily_topics",AsyncMock(side_effect=[[initial],[updated]])) as summarizer,
                patch.object(report_module,"_expand_context_requests",AsyncMock(return_value=expanded)) as expand,
                patch.object(report_module,"editorialize_daily",AsyncMock(return_value=editor)),
                patch.object(report_module,"_compile_issue_tex",side_effect=fake_compile),
            ):
                output=await report_module.build_daily_report(Path(td),[card()],"2026-10-30","owner-json",provider=object())
            self.assertEqual(summarizer.await_count,2)
            expand.assert_awaited_once()
            self.assertEqual(output.summaries[0].evidence_floors,(33,56))
            self.assertEqual(output.evidence[0].focused_floors,(33,))
            manifest=json.loads(output.manifest.read_text())
            self.assertEqual(manifest["topics"][0]["context_focus_floors"],[33])
            self.assertTrue(output.pdf.exists())

    async def test_missing_context_page_binary_search_stays_within_forum(self):
        page_map={i:[floor(n) for n in range((i-1)*10+1,i*10+1)] for i in range(1,7)}
        item=DailyTopicEvidence(card(),page_map[1][0],tuple(page_map[6][-2:]),
                                tuple(page_map[6][-5:]),
                                context_floors=tuple(page_map[1]+page_map[6]),
                                context_pages=(1,6),last_page_number=6)
        paths=[]
        async def get(path):
            paths.append(path)
            match=re.search(r"/p(\d+)$",path)
            return str(int(match.group(1)) if match else 1)
        with patch.object(ChaoliService,"_get",side_effect=get),patch.object(
            ChaoliService,"_parse_thread",side_effect=lambda html,tid:("topic",page_map[int(html)])
        ):
            expanded=await _expand_context_requests(item,(33,))
        self.assertIn(33,{x.number for x in expanded.context_floors})
        self.assertIn(33,expanded.focused_floors)
        self.assertTrue(all(p.startswith("/index.php/42/") for p in paths))
        self.assertLessEqual(len(paths),7)

if __name__=="__main__":
    unittest.main()
