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
    ChaoliPushStore,
    PushEvent,
    classify_cards,
    format_push_message,
    primed_channel_state,
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


if __name__ == "__main__":
    unittest.main()
