from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
            plugin._daily_cards_for_send = AsyncMock(return_value=([card(100)], "owner-json"))

            event = type("Event", (), {
                "unified_msg_origin": umo,
                "get_group_id": lambda self: "1",
            })()
            with patch.object(chaoli_main, "is_group_admin", AsyncMock(return_value=True)):
                result = await plugin._daily_command(event, "push")

            self.assertIsNone(result)
            plugin.context.send_message.assert_awaited_once()
            self.assertEqual(plugin.context.send_message.await_args.args[0], umo)
            self.assertIn("超理日报", str(plugin.context.send_message.await_args.args[1]))
            self.assertEqual(plugin.push_store.daily_state(umo)["last_sent"], shanghai_date())

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
            plugin._daily_cards_for_send = AsyncMock(return_value=([card(100)], "owner-json"))
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
            fetch = AsyncMock(return_value=([card(100)], "owner-json"))
            plugin._daily_cards_for_send = fetch
            with patch.object(chaoli_main, "is_plugin_enabled", AsyncMock(return_value=True)):
                await plugin._poll_daily_once()
            fetch.assert_awaited_once()
            self.assertEqual(plugin.context.send_message.await_count, 2)
            for umo in ("napcat:GroupMessage:1", "napcat:GroupMessage:2"):
                self.assertEqual(plugin.push_store.daily_state(umo)["last_sent"], shanghai_date())



if __name__ == "__main__":
    unittest.main()
