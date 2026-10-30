from __future__ import annotations
from datetime import datetime
from pathlib import Path
import sys,tempfile,types,unittest
from unittest.mock import AsyncMock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
pkg=sys.modules.setdefault("data",types.ModuleType("data"))
mod=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
mod.__path__=[str(ROOT/"plugins")]
pkg.plugins=mod
from doge_chaoli.main import DogeChaoli
from doge_chaoli.push import ChaoliPushStore,SHANGHAI,DAILY_DEFAULT_TIME
import doge_chaoli.main as bot
import doge_chaoli.push as store_module

class ScheduledDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_group_times_generate_distinct_issues(self):
        with tempfile.TemporaryDirectory() as td:
            plugin=object.__new__(DogeChaoli)
            plugin.push_store=ChaoliPushStore(Path(td)/"subs.json")
            plugin._push_lock=__import__("asyncio").Lock()
            for index,target in enumerate(("20:15","23:45","23:45","23:59"),1):
                umo=f"napcat:GroupMessage:{index}"
                plugin.push_store.set_daily(umo,True,target)
                plugin.push_store.data["subscriptions"][umo]["daily"]["last_sent"]="2026-10-29"
            plugin.push_store.save()
            async def produce(today,umo=None,issue_time=DAILY_DEFAULT_TIME):
                return types.SimpleNamespace(date=today,issue_time=issue_time)
            plugin._daily_report_for_send=AsyncMock(side_effect=produce)
            plugin._send_daily_report=AsyncMock(return_value=True)
            class Clock:
                @staticmethod
                def now(tz):return datetime(2026,10,30,23,50,tzinfo=SHANGHAI)
            with patch.object(bot,"datetime",Clock),patch.object(
                bot,"is_plugin_enabled",AsyncMock(return_value=True)
            ):
                await plugin._poll_daily_once()
            self.assertEqual(plugin._daily_report_for_send.await_count,2)
            self.assertEqual({x.kwargs["issue_time"] for x in plugin._daily_report_for_send.await_args_list},{"20:15","23:45"})
            self.assertEqual(plugin._send_daily_report.await_count,3)
            for index in range(1,4):
                self.assertEqual(plugin.push_store.daily_state(f"napcat:GroupMessage:{index}")["last_sent"],"2026-10-30")
            self.assertEqual(plugin.push_store.daily_state("napcat:GroupMessage:4")["last_sent"],"2026-10-29")

    def test_adjusting_cutoff_before_deadline_preserves_future_send(self):
        with tempfile.TemporaryDirectory() as td:
            store=ChaoliPushStore(Path(td)/"subs.json")
            store.set_daily("group",True,"23:45")
            store.data["subscriptions"]["group"]["daily"]["last_sent"]="2026-10-29"
            store.save()
            class Clock:
                @staticmethod
                def now(tz):return datetime(2026,10,30,20,0,tzinfo=SHANGHAI)
                @staticmethod
                def strptime(value,fmt):return datetime.strptime(value,fmt)
            with patch.object(store_module,"datetime",Clock):
                state=store.set_daily("group",True,"21:15")
            self.assertEqual(state["time"],"21:15")
            self.assertEqual(state["last_sent"],"2026-10-29")

    def test_adjusting_cutoff_after_deadline_does_not_backfill(self):
        with tempfile.TemporaryDirectory() as td:
            store=ChaoliPushStore(Path(td)/"subs.json")
            store.set_daily("group",True,"23:45")
            store.data["subscriptions"]["group"]["daily"]["last_sent"]="2026-10-29"
            store.save()
            class Clock:
                @staticmethod
                def now(tz):return datetime(2026,10,30,20,0,tzinfo=SHANGHAI)
                @staticmethod
                def strptime(value,fmt):return datetime.strptime(value,fmt)
            with patch.object(store_module,"datetime",Clock):
                state=store.set_daily("group",True,"19:30")
            self.assertEqual(state["last_sent"],"2026-10-30")

if __name__=="__main__":
    unittest.main()
