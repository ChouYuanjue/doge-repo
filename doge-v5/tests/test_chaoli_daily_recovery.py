from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
data=sys.modules.setdefault("data",types.ModuleType("data"))
plugins=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
plugins.__path__=[str(ROOT/"plugins")]
data.plugins=plugins

from doge_chaoli.daily_report import (
    REPORT_SCHEMA,REPORT_TEMPLATE_REV,DailyTopicSummary,
    _load_frozen_report,build_daily_report,
)
from doge_chaoli.main import DogeChaoli
import doge_chaoli.main as chaoli_module
import doge_chaoli.daily_report as report


class ReportRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_uses_active_group_provider_instead_of_global_default(self):
        plugin=object.__new__(DogeChaoli)
        plugin.context=types.SimpleNamespace(get_using_provider_async=AsyncMock(return_value=object()))
        plugin.data_dir=Path("/tmp/fake-doge")
        plugin._daily_cards_for_send=AsyncMock(return_value=([types.SimpleNamespace(thread_id=100)],"owner-json"))
        with patch.object(chaoli_module,"build_daily_report",AsyncMock(return_value="report")) as build:
            result=await plugin._daily_report_for_send("2026-10-30",umo="napcat:GroupMessage:test")
            self.assertEqual(result,"report")
            plugin.context.get_using_provider_async.assert_awaited_once_with(umo="napcat:GroupMessage:test")
            self.assertIs(build.await_args.kwargs["provider"],plugin.context.get_using_provider_async.return_value)

    async def test_zero_articles_401_rejects_instead_of_writing_success_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            card=types.SimpleNamespace(thread_id=101)
            evidence=[types.SimpleNamespace(card=card)]
            summarized=[DailyTopicSummary(101,"",(),"AuthenticationError: HTTP 401")]
            with (
                patch.object(report,"_signature",return_value="noauth"),
                patch.object(report,"collect_daily_evidence",AsyncMock(return_value=evidence)),
                patch.object(report,"summarize_daily_topics",AsyncMock(return_value=summarized)),
                patch.object(report,"editorialize_daily",AsyncMock()) as edit,
                patch.object(report,"_compile_issue_tex") as compile,
            ):
                with self.assertRaisesRegex(ValueError,"401"):
                    await build_daily_report(Path(td),[card],"2026-10-30","owner-json",provider=object())
                edit.assert_not_awaited()
                compile.assert_not_called()
                self.assertFalse(list(Path(td).rglob("*.json")))

    async def test_empty_index_refuses_blank_issue(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"数据为空"):
                await build_daily_report(Path(td),[],"2026-10-30","owner-json",provider=None)


class InvalidFrozenReports(unittest.TestCase):
    def test_old_401_pdf_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            signature="past"
            date="2026-10-29"
            bad={
                "schema":REPORT_SCHEMA,"template_revision":REPORT_TEMPLATE_REV,
                "signature":signature,"date":date,
                "topics":[{"thread_id":100,"article":"","article_error":"HTTP 401"}],
                "pdf_file":"frozen.pdf","page_files":["frozen-1.png"],
            }
            (d/f"chaoli-daily-{date}-{signature}.json").write_text(json.dumps(bad))
            (d/"frozen.pdf").write_bytes(b"%PDF-1.7\n")
            (d/"frozen-1.png").write_bytes(b"0"*2000)
            card=types.SimpleNamespace(thread_id=100)
            self.assertIsNone(_load_frozen_report(d,[card],date,"owner-json",signature))


if __name__=="__main__":unittest.main()
