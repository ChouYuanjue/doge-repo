from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

data_pkg = sys.modules.get("data") or types.ModuleType("data")
if not hasattr(data_pkg, "__path__"):
    data_pkg.__path__ = []  # type: ignore[attr-defined]
plugins_pkg = sys.modules.get("data.plugins") or types.ModuleType("data.plugins")
plugins_pkg.__path__ = [str(PLUGINS)]  # type: ignore[attr-defined]
data_pkg.plugins = plugins_pkg  # type: ignore[attr-defined]
sys.modules["data"] = data_pkg
sys.modules["data.plugins"] = plugins_pkg

from doge_music.main import DogeMusic
from doge_music.service import NetEaseMusicService
from doge_shared.capabilities import match_invocation


class _Result:
    def __init__(self, chain): self.chain=chain
    def use_markdown(self, value): self.markdown=value; return self


class _Event:
    unified_msg_origin = "aiocqhttp:GroupMessage:1"
    def get_platform_name(self): return "aiocqhttp"
    def chain_result(self, chain): return _Result(chain)


class MusicServiceTests(unittest.TestCase):
    def test_search_payload_is_strictly_bound_to_returned_song_fields(self):
        payload = {
            "result": {"songs": [
                {"id": 1859245776, "name": "Test Song", "artists": [{"name": "A"}, {"name": "B"}], "album": {"name": "Album"}, "duration": 123456},
                {"id": None, "name": "bad", "artists": []},
            ]}
        }
        rows = NetEaseMusicService.parse_search_payload(payload, 5)
        self.assertEqual(len(rows), 1)
        song = rows[0]
        self.assertEqual((song.song_id, song.name, song.artists, song.album, song.duration_text), (1859245776, "Test Song", "A / B", "Album", "2:03"))

    def test_native_onebot_card_contains_only_netease_type_and_song_id(self):
        result = DogeMusic._card_result(_Event(), 1859245776)
        self.assertEqual(len(result.chain), 1)
        card = result.chain[0]
        data = card.toDict()
        self.assertEqual(data["type"], "music")
        self.assertEqual(data["data"]["type"], "163")
        self.assertEqual(data["data"]["id"], 1859245776)
        self.assertEqual(data["data"]["audio"], "")

    def test_registry_routes_music_specific_subcommands_before_root_search(self):
        self.assertEqual(match_invocation("/music 晴天").capability_id, "music.search")
        self.assertEqual(match_invocation("/music play 2").capability_id, "music.play")
        self.assertEqual(match_invocation("/music id 1859245776").capability_id, "music.id")
        self.assertEqual(match_invocation("/music status").capability_id, "music.status")

    def test_manifest_and_policy_include_music(self):
        manifest = json.loads((ROOT / "plugin_manifest.json").read_text(encoding="utf-8"))
        row = next(x for x in manifest["plugins"] if x["name"] == "doge_music")
        self.assertEqual((row["status"], row["default"]), ("formal", True))
        policy = json.loads((ROOT / "truthfulness_policy.json").read_text(encoding="utf-8"))["plugins"]["doge_music"]
        self.assertIn("NetEase", policy["source"])
        self.assertIn("native", policy["source"])

    def test_upstream_note_explicitly_says_no_source_was_vendored(self):
        text = (PLUGINS / "doge_music" / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("Mnbqq/astrbot_plugin_m", text)
        self.assertIn("does **not** vendor or copy", text)


if __name__ == "__main__":
    unittest.main()
