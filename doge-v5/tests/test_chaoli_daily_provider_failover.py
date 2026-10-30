from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
pkg=sys.modules.setdefault("data",types.ModuleType("data"))
plugins=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
plugins.__path__=[str(ROOT/"plugins")]
pkg.plugins=plugins

import doge_chaoli.daily_report as report_module
from doge_chaoli.daily_report import (
    DailyTopicEvidence, DailyTopicSummary, build_daily_report,
)
from doge_chaoli.main import DogeChaoli
import doge_chaoli.main as chaoli_main
from data.plugins.doge_shared.chaoli import Floor,ThreadCard
from doge_shared.agent_tools import DogeChaoliTool

def card():
    return ThreadCard(
        101,"一个数学反例","","数学","maths","甲",1,
        "2026-10-22","乙",2,"2026-10-30 14:56","2",
        "https://chaoli.club/index.php/101","stable"
    )

def actual_floor():
    return Floor(
        3,"乙",2,"2026-10-30 14:56:16","新加入了一条有日期的讨论。",
        (),"https://chaoli.club/index.php/conversation/post/103990"
    )

class BrokenModel:
    def __init__(self,provider_id):
        self.provider_id=provider_id
        self.calls=0
    def meta(self):return types.SimpleNamespace(id=self.provider_id)
    async def text_chat(self,**kwargs):
        self.calls+=1
        raise RuntimeError("AuthenticationError: Error code 401 Unauthorized")

class ReadyModel:
    def __init__(self,provider_id="workbuddy/glm-5.3"):
        self.provider_id=provider_id
        self.provider_config={"id":provider_id,"model":provider_id.split("/")[-1],"provider_source_id":provider_id.split("/")[0]}
        self.calls=0
    def meta(self):return types.SimpleNamespace(id=self.provider_id)
    async def text_chat(self,**kwargs):
        self.calls+=1
        prompt=kwargs["prompt"]
        if "按输入顺序" in prompt:
            output={"topics":[{"thread_id":101,"article":"10月30日3楼提出了一个条件限制，尚未有完整证明。",
                               "evidence_floors":[3],"context_requests":[]}]}
        else:
            output={"headline":"","standfirst":"本期收录了一条关于条件限制的数学讨论更新。",
                    "blocks":[{"level":"brief","thread_ids":[101],
                               "headline":"一条新的条件限制","deck":"已有讨论被补充"}]}
        return types.SimpleNamespace(completion_text=json.dumps(output,ensure_ascii=False))

def fake_pdf(out,tex,stem):
    pdf=out/(stem+".pdf");pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    page=out/(stem+"-page-01.png");page.write_bytes(b"\x89PNG\r\n\x1a\n"+b"1"*2200)
    return pdf,(page,)


class ProviderFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_report_primary_401_falls_back_using_same_verified_floors(self):
        c=card();f=actual_floor()
        ev=DailyTopicEvidence(c,f,(f,),(f,),context_floors=(f,),issue_date="2026-10-30")
        workbuddy=BrokenModel("workbuddy/deepseek-v4.1-flash")
        deepseek=ReadyModel()
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(report_module,"collect_daily_evidence",AsyncMock(return_value=[ev])) as collector,
            patch.object(report_module,"_compile_issue_tex",side_effect=fake_pdf),
        ):
            issue=await build_daily_report(
                Path(td),[c],"2026-10-30","owner-json",
                provider=workbuddy,fallback_providers=(deepseek,)
            )
            metadata=json.loads(issue.manifest.read_text())
            self.assertEqual(metadata["draft_provider"],"workbuddy/glm-5.3")
            self.assertEqual(metadata["provider_recovery"],[
                "workbuddy/deepseek-v4.1-flash -> workbuddy/glm-5.3"
            ])
        collector.assert_awaited_once_with([c],issue_date="2026-10-30",issue_time="23:45")
        self.assertEqual(workbuddy.calls,1)
        self.assertGreaterEqual(deepseek.calls,2)
        self.assertEqual(issue.summaries[0].evidence_floors,(3,))
        self.assertTrue(issue.pdf.exists() is False) # temporary directory is removed

    async def test_all_providers_unauthorized_remains_hard_fail_with_no_manifest(self):
        c=card();f=actual_floor()
        ev=DailyTopicEvidence(c,f,(f,),(f,),context_floors=(f,),issue_date="2026-10-30")
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(report_module,"collect_daily_evidence",AsyncMock(return_value=[ev])),
            patch.object(report_module,"_compile_issue_tex") as compile,
        ):
            with self.assertRaisesRegex(ValueError,"401"):
                await build_daily_report(
                    Path(td),[c],"2026-10-30","owner-json",
                    provider=BrokenModel("workbuddy/deepseek-v4.1-flash"),
                    fallback_providers=(BrokenModel("deepseek/deepseek-v4-flash"),)
                )
            self.assertFalse(list(Path(td).rglob("*.json")))
            compile.assert_not_called()

    async def test_plugin_prepares_configured_chat_free_fallback(self):
        chosen=BrokenModel("workbuddy/deepseek-v4.1-flash")
        healthy=ReadyModel()
        plugin=object.__new__(DogeChaoli)
        plugin.data_dir=Path("/tmp/unused")
        plugin._daily_cards_for_send=AsyncMock(return_value=([card()],"owner-json"))
        plugin.context=types.SimpleNamespace(
            get_using_provider_async=AsyncMock(return_value=chosen),
            get_config=lambda umo=None: {"provider_settings":{"fallback_chat_models":["workbuddy/glm-5.3"]}},
            get_provider_by_id=lambda id: healthy if id=="workbuddy/glm-5.3" else None,
        )
        with patch.object(chaoli_main,"build_daily_report",AsyncMock(return_value="done")) as build:
            self.assertEqual(await plugin._daily_report_for_send("2026-10-30","umo"),"done")
        self.assertIs(build.await_args.kwargs["provider"],chosen)
        self.assertEqual(build.await_args.kwargs["fallback_providers"],(healthy,))
        self.assertEqual(build.await_args.kwargs["issue_time"],"23:45")


class AgentDailyErrorVisibility(unittest.IsolatedAsyncioTestCase):
    async def test_agent_tool_401_is_not_silently_swallowed(self):
        response={"capability_id":"chaoli.daily","text":"[chaoli] 日报摘要模型认证失败（HTTP 401）"}
        with patch("doge_shared.agent_tools.execute_formal_command",
                   AsyncMock(return_value=json.dumps(response,ensure_ascii=False))) as execute:
            result=await DogeChaoliTool().call(None,action="daily")
        self.assertIn("401",result)
        self.assertIn("执行失败",result)
        execute.assert_awaited_once_with(None,"/chaoli daily")

    async def test_agent_daily_push_permission_error_is_visible(self):
        response={"capability_id":"chaoli.daily","text":"只有管理员可以主动推送"}
        with patch("doge_shared.agent_tools.execute_formal_command",
                   AsyncMock(return_value=json.dumps(response,ensure_ascii=False))) as execute:
            result=await DogeChaoliTool().call(None,action="daily_push")
        self.assertIn("管理员",result)
        execute.assert_awaited_once_with(None,"/chaoli daily push")

    async def test_agent_success_distinguishes_sent_report_from_empty_result(self):
        response={"capability_id":"chaoli.daily","text":"","media":[]}
        with patch("doge_shared.agent_tools.execute_formal_command",
                   AsyncMock(return_value=json.dumps(response,ensure_ascii=False))):
            result=await DogeChaoliTool().call(None,action="daily")
        self.assertIn("已完成",result)
        self.assertNotIn("执行失败",result)

if __name__=="__main__":
    unittest.main()
