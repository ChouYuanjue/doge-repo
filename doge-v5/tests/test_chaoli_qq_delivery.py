from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
pkg=sys.modules.setdefault("data",types.ModuleType("data"))
plugs=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
plugs.__path__=[str(ROOT/"plugins")]
pkg.plugins=plugs

from doge_chaoli.main import DogeChaoli
from doge_chaoli.daily_report import (
    DailyEditorialIssue,DailyEditorialBlock,DailyReportBundle,
    DailyTopicEvidence,DailyTopicSummary,
)
from data.plugins.doge_shared.chaoli import ThreadCard
from astrbot.api.message_components import Nodes,File,Image

def card():
    return ThreadCard(55,"测试讨论","","数学","maths","甲",1,"2026-10-30",
                      "乙",2,"2026-10-30 15:00","5",
                      "https://chaoli.club/index.php/55","abc")

def make_report(root):
    pdf=Path(root)/"issue.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    png=Path(root)/"issue-page-01.png"
    from PIL import Image as PILImage
    PILImage.new("RGB",(8,8),"white").save(png)
    manifest=Path(root)/"manifest.json"
    manifest.write_text("{}")
    c=card()
    return DailyReportBundle(
        "2026-10-30","owner-json",(c,),
        (DailyTopicEvidence(c,None,(),()),),
        (DailyTopicSummary(55,"今天新增了数值反例。",(6,)),),
        DailyEditorialIssue("","研究讨论新增回复",
                            (DailyEditorialBlock("lead",(55,),"最新论证","证据简讯"),)),
        "# Issue","\\documentclass{article}",pdf,(png,),manifest
    )

class OneBotDailyDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_true_pdf_upload_uses_napcat_group_action_and_image_forward_only(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            calls=[]
            async def action(kind,**kwargs):
                calls.append((kind,kwargs))
                if kind=="get_login_info":
                    return {"user_id":"123","nickname":"豆子"}
                if kind=="upload_group_file":
                    return {"retcode":0,"status":"ok"}
                raise AssertionError(kind)
            bot=types.SimpleNamespace(call_action=action)
            plugin.context=types.SimpleNamespace(
                get_platform_inst=lambda _name:types.SimpleNamespace(bot=bot),
                send_message=AsyncMock(return_value=True)
            )
            issue=make_report(td)
            ok=await plugin._send_daily_report("napcat:GroupMessage:group_456",issue)
            self.assertTrue(ok)
            action_calls=[(kind,kw) for kind,kw in calls if kind=="upload_group_file"]
            self.assertEqual(len(action_calls),1)
            params=action_calls[0][1]
            self.assertEqual(params["group_id"],456)
            self.assertEqual(params["name"],"Chaoli-Daily-2026-10-30.pdf")
            self.assertEqual(params["file"],str(issue.pdf.resolve()))
            chain=plugin.context.send_message.await_args.args[1]
            self.assertEqual(len(chain.chain),1)
            self.assertIsInstance(chain.chain[0],Nodes)
            nodes=chain.chain[0].nodes
            self.assertEqual(len(nodes),2)
            self.assertIn("已单独上传",nodes[0].content[0].text)
            self.assertTrue(any(isinstance(seg,Image) for seg in nodes[1].content))
            self.assertFalse(any(isinstance(seg,File) for node in nodes for seg in node.content))
            payload=await chain.chain[0].to_dict()
            self.assertEqual(len(payload["messages"]),2)
            self.assertTrue(payload["messages"][1]["data"]["content"][1]["data"]["file"].startswith("base64://"))

    async def test_pdf_upload_failure_allows_readable_preview_and_no_false_pdf_claim(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            async def action(kind,**kwargs):
                if kind=="upload_group_file":
                    raise RuntimeError("simulated QQ PDF upload rejected")
                return {"user_id":"123","nickname":"豆子"}
            plugin.context=types.SimpleNamespace(
                get_platform_inst=lambda _name:types.SimpleNamespace(
                    bot=types.SimpleNamespace(call_action=action)
                ),
                send_message=AsyncMock(return_value=True)
            )
            success=await plugin._send_daily_report("napcat:GroupMessage:456",make_report(td))
            self.assertTrue(success)
            first=plugin.context.send_message.await_args.args[1].chain[0].nodes[0].content[0].text
            self.assertIn("本次未上传成功",first)

    async def test_pdf_success_prevents_retry_spam_when_forward_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            async def action(kind,**kwargs):
                return {"retcode":0} if kind=="upload_group_file" else {"user_id":"123"}
            plugin.context=types.SimpleNamespace(
                get_platform_inst=lambda _name:types.SimpleNamespace(
                    bot=types.SimpleNamespace(call_action=action)
                ),
                send_message=AsyncMock(side_effect=RuntimeError("forward failed"))
            )
            self.assertTrue(await plugin._send_daily_report("napcat:GroupMessage:456",make_report(td)))

    async def test_no_delivery_fails_without_pretending_watermark_success(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            async def action(kind,**kwargs):
                raise RuntimeError("offline")
            plugin.context=types.SimpleNamespace(
                get_platform_inst=lambda _name:types.SimpleNamespace(
                    bot=types.SimpleNamespace(call_action=action)
                ),
                send_message=AsyncMock(return_value=False)
            )
            self.assertFalse(await plugin._send_daily_report("napcat:GroupMessage:456",make_report(td)))

if __name__=="__main__":
    unittest.main()
