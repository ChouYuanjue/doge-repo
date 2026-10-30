from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,patch

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
from doge_shared.agent_tools import DogeChaoliTool
from astrbot.api.message_components import Nodes,File,Image,Plain

def card():
    return ThreadCard(
        55,"测试讨论","","数学","maths","甲",1,"2026-10-30",
        "乙",2,"2026-10-30 15:00","5",
        "https://chaoli.club/index.php/55","abc"
    )

def report_in(root):
    root=Path(root)
    pdf=root/"issue.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    from PIL import Image as PILImage
    pages=[]
    for i in range(2):
        png=root/f"page{i+1}.png"
        PILImage.new("RGB",(8,8),"white").save(png)
        pages.append(png)
    manifest=root/"manifest.json"
    manifest.write_text("{}",encoding="utf-8")
    c=card()
    return DailyReportBundle(
        "2026-10-30","owner-json",(c,),
        (DailyTopicEvidence(c,None,(),()),),
        (DailyTopicSummary(55,"一条真实新进展。",(6,)),),
        DailyEditorialIssue("","研究讨论更新",
            (DailyEditorialBlock("lead",(55,),"最新论证","证据简讯"),)),
        "# Issue","\\documentclass{article}",pdf,tuple(pages),manifest
    )

def bot_context(send=True,actions=None):
    async def action(kind,**kwargs):
        if actions is not None:actions.append(kind)
        if kind=="get_login_info":return {"user_id":"123","nickname":"豆子"}
        raise AssertionError("Group-file action forbidden: "+kind)
    return types.SimpleNamespace(
        get_platform_inst=lambda _name:types.SimpleNamespace(
            bot=types.SimpleNamespace(call_action=action)),
        send_message=AsyncMock(return_value=send)
    )

class QQForwardOnly(unittest.IsolatedAsyncioTestCase):
    async def test_one_forward_has_pdf_node_and_two_preview_nodes_no_group_file_upload(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            actions=[]
            plugin.context=bot_context(actions=actions)
            issue=report_in(td)
            ok=await plugin._send_daily_report("napcat:GroupMessage:456",issue)
            self.assertTrue(ok)
            plugin.context.send_message.assert_awaited_once()
            self.assertEqual(actions,["get_login_info"])
            args=plugin.context.send_message.await_args.args
            self.assertEqual(args[0],"napcat:GroupMessage:456")
            self.assertEqual(len(args[1].chain),1)
            self.assertIsInstance(args[1].chain[0],Nodes)
            nodes=args[1].chain[0].nodes
            self.assertEqual(len(nodes),4)  # intro + PDF + two PNGs
            self.assertIn("超理日报",nodes[0].content[0].text)
            self.assertIsInstance(nodes[1].content[1],File)
            self.assertEqual(nodes[1].content[1].file,str(issue.pdf.resolve()))
            self.assertEqual(nodes[1].content[1].name,"Chaoli-Daily-2026-10-30.pdf")
            self.assertEqual(sum(isinstance(seg,Image) for node in nodes for seg in node.content),2)
            payload=await args[1].chain[0].to_dict()
            self.assertEqual(len(payload["messages"]),4)
            file_segment=payload["messages"][1]["data"]["content"][1]
            self.assertEqual(file_segment["type"],"file")
            self.assertEqual(file_segment["data"]["name"],"Chaoli-Daily-2026-10-30.pdf")
            self.assertEqual(file_segment["data"]["file"],str(issue.pdf.resolve()))
            for index in (2,3):
                segments=payload["messages"][index]["data"]["content"]
                self.assertEqual(segments[1]["type"],"image")
                self.assertTrue(segments[1]["data"]["file"].startswith("base64://"))

    async def test_failed_forward_does_not_claim_delivery_or_upload_file(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            calls=[]
            plugin.context=bot_context(send=False,actions=calls)
            self.assertFalse(await plugin._send_daily_report("napcat:GroupMessage:456",report_in(td)))
            plugin.context.send_message.assert_awaited_once()
            self.assertEqual(calls,["get_login_info"])

    async def test_transport_exception_cannot_fallback_to_group_file(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            actions=[]
            plugin.context=bot_context(actions=actions)
            plugin.context.send_message=AsyncMock(side_effect=RuntimeError("forward unsupported"))
            self.assertFalse(await plugin._send_daily_report("napcat:GroupMessage:456",report_in(td)))
            self.assertEqual(actions,["get_login_info"])

    async def test_missing_or_invalid_pdf_fails_before_any_network_action(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            actions=[]
            plugin.context=bot_context(actions=actions)
            issue=report_in(td)
            issue.pdf.write_bytes(b"wrong format")
            self.assertFalse(await plugin._send_daily_report("napcat:GroupMessage:456",issue))
            self.assertEqual(actions,[])
            plugin.context.send_message.assert_not_awaited()

class IncomingMessage:
    def __init__(self,original="/chaoli daily",umo="napcat:GroupMessage:456"):
        self.message_str=original
        self.message_obj=types.SimpleNamespace(message_str=original)
        self.unified_msg_origin=umo
        self._extras={}
        self.stopped=False
    def get_group_id(self):return "456"
    def set_extra(self,key,value):self._extras[key]=value
    def get_extra(self,key=None,default=None):
        if key is None:return self._extras
        return self._extras.get(key,default)
    def stop_event(self):self.stopped=True

class DoubleDispatchRegression(unittest.IsolatedAsyncioTestCase):
    async def test_same_event_formal_handler_invoked_twice_sends_only_once(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            plugin._latest_existing_report=lambda umo:report_in(td)
            plugin._send_daily_report=AsyncMock(return_value=True)
            event=IncomingMessage()
            self.assertIsNone(await plugin._daily_command(event,""))
            self.assertIsNone(await plugin._daily_command(event,""))
            plugin._send_daily_report.assert_awaited_once()

    async def test_slash_command_triggers_native_stop_before_agent_runs(self):
        plugin=object.__new__(DogeChaoli)
        plugin._daily_command=AsyncMock(return_value=None)
        event=IncomingMessage()
        out=[result async for result in plugin.command(event)]
        self.assertEqual(out,[])
        self.assertTrue(event.stopped)
        plugin._daily_command.assert_awaited_once_with(event,"")

    async def test_agent_tool_cannot_replay_raw_slash_even_if_agent_woke(self):
        event=IncomingMessage()
        outer=types.SimpleNamespace(context=types.SimpleNamespace(event=event))
        with patch("doge_shared.agent_tools.execute_formal_command",AsyncMock()) as executor:
            result=await DogeChaoliTool().call(outer,action="daily")
        self.assertIn("禁止再次",result)
        executor.assert_not_awaited()

    async def test_agent_tool_does_not_double_execute_same_natural_message(self):
        event=IncomingMessage(original="给我看看昨天的日报")
        event.set_extra("_doge_chaoli_daily_sent_from_event",True)
        outer=types.SimpleNamespace(context=types.SimpleNamespace(event=event))
        with patch("doge_shared.agent_tools.execute_formal_command",AsyncMock()) as executor:
            result=await DogeChaoliTool().call(outer,action="daily")
        self.assertIn("拒绝重复",result)
        executor.assert_not_awaited()

if __name__=="__main__":
    unittest.main()
