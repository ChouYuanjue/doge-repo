from __future__ import annotations

import hashlib
import json
import sys
import tempfile
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

from doge_pixiv.main import DogePixiv
from doge_pixiv.service import PixivService, SeenStore
from doge_shared.agent_tools import DogePixivTool
from doge_shared.capabilities import match_invocation


class PixivServiceTests(unittest.TestCase):
    def test_get_px_vendor_subset_is_unmodified_and_license_is_present(self):
        vendor = PLUGINS / "doge_pixiv" / "vendor" / "get_px"
        self.assertTrue((vendor / "LICENSE").exists())
        self.assertIn("MIT License", (vendor / "LICENSE").read_text(encoding="utf-8"))
        provenance = (vendor / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("shitianyaa/astrbot_plugin_get_px", provenance)
        self.assertIn("63a0dd23fcc5197cf010630f89013dfb05992d41", provenance)
        hashes = {
            "lolicon.py": "774f371b9bf8bedccc748a066d516410d86f90dccae14ecd4a4316ed337cbdb0",
            "downloader.py": "afc5a8b8999efde100450f38e5b26b9060e29c552e9d2a2410313ec3357857b9",
        }
        for name, expected in hashes.items():
            actual = hashlib.sha256((vendor / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected)

    def test_hard_filter_rejects_r18_and_ai_even_after_upstream_filtering(self):
        rows = [
            {"id": "1:0", "x_restrict": 0, "ai_type": 0, "meta_single_page": {"original_image_url": "https://i.pixiv.re/a.jpg"}},
            {"id": "2:0", "x_restrict": 1, "ai_type": 0, "meta_single_page": {"original_image_url": "https://i.pixiv.re/b.jpg"}},
            {"id": "3:0", "x_restrict": 0, "ai_type": 2, "meta_single_page": {"original_image_url": "https://i.pixiv.re/c.jpg"}},
            {"id": "4:0", "x_restrict": 0, "ai_type": 0, "meta_single_page": {"original_image_url": ""}},
        ]
        self.assertEqual([x["id"] for x in PixivService._filter(rows)], ["1:0"])

    def test_seen_store_prefers_unseen_images_within_each_chat_scope(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "seen.json"
            store = SeenStore(path)
            rows = [{"id": "1:0"}, {"id": "2:0"}, {"id": "3:0"}]
            first = store.choose("group:1", rows, 2)
            self.assertEqual([x["id"] for x in first], ["1:0", "2:0"])
            second = store.choose("group:1", rows, 1)
            self.assertEqual([x["id"] for x in second], ["3:0"])
            other = store.choose("group:2", rows, 1)
            self.assertEqual([x["id"] for x in other], ["1:0"])
            restored = SeenStore(path)
            self.assertIn("3:0", restored.data["group:1"])

    def test_count_parser_supports_spaces_and_clamps_group_limit(self):
        self.assertEqual(DogePixiv._split_count("初音 ミク 3", 1, 3), ("初音 ミク", 3))
        self.assertEqual(DogePixiv._split_count("初音ミク 99", 1, 3), ("初音ミク", 3))
        self.assertEqual(DogePixiv._split_count("3", 1, 3), ("", 3))

    def test_formal_router_prefers_specific_pixiv_subcommands_over_search(self):
        self.assertEqual(match_invocation("/pixiv 初音ミク 2").capability_id, "pixiv.search")
        self.assertEqual(match_invocation("/pixiv random 2").capability_id, "pixiv.random")
        self.assertEqual(match_invocation("/pixiv artist 6757228 1").capability_id, "pixiv.artist")
        self.assertEqual(match_invocation("/pixiv status").capability_id, "pixiv.status")

    def test_manifest_registry_and_agent_tool_expose_only_thin_pixiv_surface(self):
        manifest = json.loads((ROOT / "plugin_manifest.json").read_text(encoding="utf-8"))
        row = next(x for x in manifest["plugins"] if x["name"] == "doge_pixiv")
        self.assertEqual((row["status"], row["default"]), ("formal", True))
        registry = json.loads((PLUGINS / "doge_shared" / "resources" / "capability_registry.json").read_text(encoding="utf-8"))
        ids = {x["id"] for x in registry["operations"] if x["id"].startswith("pixiv.")}
        self.assertEqual(ids, {"pixiv.search", "pixiv.random", "pixiv.artist", "pixiv.status"})
        tool = DogePixivTool()
        self.assertEqual(tool.name, "doge_pixiv")
        self.assertEqual(set(tool.parameters["properties"]["action"]["enum"]), {"search", "random", "artist"})


if __name__ == "__main__":
    unittest.main()
