from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from astrbot.core.message.components import Image, Reply
from doge_shared.materials import MaterialCache


class Event:
    def __init__(self, sender: str, message_id: str, chain, *, umo: str = "qq:group:1"):
        self._sender = sender
        self.unified_msg_origin = umo
        self.message_obj = SimpleNamespace(message_id=message_id, message=list(chain))

    def get_sender_id(self):
        return self._sender

    def get_messages(self):
        return self.message_obj.message


def make_png(path: Path, value: int) -> Path:
    PILImage.new("RGB", (24, 24), (value, value, value)).save(path)
    return path


class MaterialResolverTests(unittest.TestCase):
    def test_current_then_explicit_reply_priority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = make_png(root / "current.png", 20)
            quoted = make_png(root / "quoted.png", 220)
            cache = MaterialCache(root / "cache")
            event = Event(
                "u1",
                "m2",
                [Image.fromFileSystem(current), Reply(id="m1", chain=[Image.fromFileSystem(quoted)])],
            )
            got = asyncio.run(cache.resolve(event, "image", needed=2))
            self.assertEqual([x.source for x in got], ["current", "reply"])
            self.assertEqual(Path(got[0].path).resolve(), current.resolve())
            self.assertEqual(Path(got[1].path).resolve(), quoted.resolve())

    def test_reply_is_used_when_command_has_no_attachment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            quoted = make_png(root / "quoted.png", 128)
            cache = MaterialCache(root / "cache")
            event = Event("u1", "m2", [Reply(id="m1", chain=[Image.fromFileSystem(quoted)])])
            got = asyncio.run(cache.resolve(event, "image"))
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0].source, "reply")

    def test_recent_material_is_same_sender_same_session_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = make_png(root / "previous.png", 80)
            cache = MaterialCache(root / "cache")
            asyncio.run(cache.remember_event(Event("alice", "m1", [Image.fromFileSystem(original)])))

            alice = asyncio.run(cache.resolve(Event("alice", "m2", []), "image"))
            bob = asyncio.run(cache.resolve(Event("bob", "m3", []), "image"))
            other_session = asyncio.run(cache.resolve(Event("alice", "m4", [], umo="qq:group:2"), "image"))

            self.assertEqual(len(alice), 1)
            self.assertEqual(alice[0].source, "recent")
            self.assertTrue(Path(alice[0].path).exists())
            self.assertEqual(bob, [])
            self.assertEqual(other_session, [])

    def test_current_message_is_not_reused_as_recent_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = make_png(root / "same.png", 100)
            cache = MaterialCache(root / "cache")
            event = Event("u1", "m1", [Image.fromFileSystem(image)])
            asyncio.run(cache.remember_event(event))
            got = asyncio.run(cache.resolve(event, "image", needed=2))
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0].source, "current")


if __name__ == "__main__":
    unittest.main()
