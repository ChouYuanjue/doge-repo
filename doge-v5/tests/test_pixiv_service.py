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

    def test_seen_store_rotates_pages_per_query_scope(self):
        with tempfile.TemporaryDirectory() as td:
            store = SeenStore(Path(td) / "seen.json")
            key_a = "group:1|search:patchouli"
            key_b = "group:1|search:miku"
            self.assertEqual([store.next_page(key_a) for _ in range(3)], [1, 2, 3])
            self.assertEqual(store.next_page(key_b), 1)
            restored = SeenStore(Path(td) / "seen.json")
            self.assertEqual(restored.next_page(key_a), 4)
            self.assertEqual(restored.next_page(key_b), 2)

    def test_web_detail_normalization_keeps_r18_and_ai_hard_fields(self):
        from doge_pixiv.service import PixivWebClient
        safe = PixivWebClient._normalize_detail({
            "illustId": "123",
            "illustTitle": "safe",
            "userId": "5",
            "userName": "artist",
            "xRestrict": 0,
            "aiType": 1,
            "width": 3000,
            "height": 2000,
            "urls": {"original": "https://i.pximg.net/a.png", "regular": "https://i.pximg.net/b.jpg"},
            "tags": {"tags": [{"tag": "東方"}]},
        })
        ai = dict(safe, ai_type=2)
        r18 = dict(safe, x_restrict=1)
        self.assertTrue(PixivService._hard_allowed(safe))
        self.assertFalse(PixivService._hard_allowed(ai))
        self.assertFalse(PixivService._hard_allowed(r18))
        self.assertEqual(safe["meta_single_page"]["original_image_url"], "https://i.pximg.net/a.png")

    def test_web_search_rotates_pages_and_downloads_original_first(self):
        class FakeWeb:
            available = True
            def __init__(self, root):
                self.root = Path(root)
                self.pages = []
                self.downloads = []
            async def search_bundle(self, query, *, page=1):
                self.pages.append(page)
                pid = str(page * 100 + 1)
                return ([{
                    "id": pid + ":0", "pid": pid, "page": 0,
                    "title": f"work-{pid}", "user": {"id": "7", "name": "artist"},
                    "x_restrict": 0, "ai_type": 1, "width": 3000, "height": 2000,
                    "tags": [{"name": query}],
                    "meta_single_page": {"original_image_url": ""}, "image_urls": {},
                    "_source": "pixiv-web-search",
                }], 1000, [])
            async def recommend(self, pid, *, limit=60):
                return []
            async def detail(self, pid):
                return {
                    "id": pid + ":0", "pid": pid, "page": 0,
                    "title": f"work-{pid}", "user": {"id": "7", "name": "artist"},
                    "x_restrict": 0, "ai_type": 1, "width": 3000, "height": 2000,
                    "tags": [{"name": "patchouli"}],
                    "meta_single_page": {"original_image_url": f"https://i.pximg.net/{pid}-original.png"},
                    "image_urls": {"large": f"https://i.pximg.net/{pid}-regular.jpg"},
                    "_source": "pixiv-web",
                }
            async def download_image(self, url, *, pid, max_bytes, timeout=18.0):
                self.downloads.append(url)
                path = self.root / f"{pid}-{len(self.downloads)}.png"
                path.write_bytes(b"image")
                return str(path), path.stat().st_size

        async def scenario(td):
            service = PixivService(td)
            fake = FakeWeb(td)
            service.web = fake
            first = await service.search("patchouli", count=1, scope="group:1")
            second = await service.search("patchouli", count=1, scope="group:1")
            return fake, first, second

        with tempfile.TemporaryDirectory() as td:
            fake, first, second = __import__('asyncio').run(scenario(td))
            self.assertEqual(fake.pages, [1, 2])
            self.assertEqual([first[0].pid, second[0].pid], ["101", "201"])
            self.assertTrue(fake.downloads[0].endswith("101-original.png"))
            self.assertTrue(fake.downloads[1].endswith("201-original.png"))
            self.assertEqual(first[0].quality, "original")
            self.assertEqual(second[0].quality, "original")

    def test_quality_tiers_use_popular_then_recommendations_before_fresh(self):
        class FakeWeb:
            available = True
            def __init__(self, root):
                self.root = Path(root)
                self.recommend_calls = []
            @staticmethod
            def row(pid, source, tag="若葉睦", ai=1, restrict=0):
                return {
                    "id": f"{pid}:0", "pid": str(pid), "page": 0,
                    "title": str(pid), "user": {"id": "7", "name": "artist"},
                    "x_restrict": restrict, "ai_type": ai, "width": 1200, "height": 1200,
                    "tags": [{"name": tag}],
                    "meta_single_page": {"original_image_url": ""}, "image_urls": {},
                    "_source": source,
                }
            async def search_bundle(self, query, *, page=1):
                latest = [self.row("900", "pixiv-web-search")]
                popular = [
                    self.row("101", "pixiv-web-popular"),
                    self.row("102", "pixiv-web-popular"),
                ]
                return latest, 1000, popular
            async def recommend(self, pid, *, limit=60):
                self.recommend_calls.append(str(pid))
                return [
                    self.row("201", "pixiv-web-recommend"),
                    self.row("202", "pixiv-web-recommend", tag="别的角色"),
                    self.row("203", "pixiv-web-recommend", ai=2),
                    self.row("204", "pixiv-web-recommend", restrict=1),
                ]
            async def detail(self, pid):
                src = "pixiv-web-recommend" if str(pid).startswith("2") else (
                    "pixiv-web-popular" if str(pid).startswith("1") else "pixiv-web-search"
                )
                row = self.row(pid, src)
                row["meta_single_page"] = {"original_image_url": f"https://i.pximg.net/{pid}.png"}
                row["image_urls"] = {"large": f"https://i.pximg.net/{pid}.jpg"}
                return row
            async def download_image(self, url, *, pid, max_bytes, timeout=18.0):
                path = self.root / f"{pid}.png"
                path.write_bytes(b"image")
                return str(path), path.stat().st_size

        async def scenario(td):
            service = PixivService(td)
            fake = FakeWeb(td)
            service.web = fake
            a = await service.search("若葉睦", count=1, scope="g")
            b = await service.search("若葉睦", count=1, scope="g")
            c = await service.search("若葉睦", count=1, scope="g")
            return fake, a, b, c

        with tempfile.TemporaryDirectory() as td:
            fake, a, b, c = __import__('asyncio').run(scenario(td))
            self.assertEqual([a[0].pid, b[0].pid, c[0].pid], ["101", "102", "201"])
            self.assertEqual(a[0].item.get("_selection_source"), "pixiv-web-popular")
            self.assertEqual(b[0].item.get("_selection_source"), "pixiv-web-popular")
            self.assertEqual(c[0].item.get("_selection_source"), "pixiv-web-recommend")
            self.assertTrue(fake.recommend_calls)
            self.assertNotIn(c[0].pid, {"202", "203", "204", "900"})

    def test_no_popular_seed_uses_fresh_search_without_recommender(self):
        class FakeWeb:
            available = True
            def __init__(self, root):
                self.root = Path(root)
                self.recommend_calls = 0
            async def search_bundle(self, query, *, page=1):
                return ([{
                    "id": "9:0", "pid": "9", "page": 0,
                    "title": "niche", "user": {"id": "1", "name": "a"},
                    "x_restrict": 0, "ai_type": 1, "width": 900, "height": 900,
                    "tags": [{"name": query}],
                    "meta_single_page": {"original_image_url": ""}, "image_urls": {},
                    "_source": "pixiv-web-search",
                }], 1, [])
            async def recommend(self, pid, *, limit=60):
                self.recommend_calls += 1
                return []
            async def detail(self, pid):
                return {
                    "id": "9:0", "pid": "9", "page": 0, "title": "niche",
                    "user": {"id": "1", "name": "a"}, "x_restrict": 0, "ai_type": 1,
                    "width": 900, "height": 900, "tags": [{"name": "双魚座"}],
                    "meta_single_page": {"original_image_url": "https://i.pximg.net/9.png"},
                    "image_urls": {"large": "https://i.pximg.net/9.jpg"},
                    "_source": "pixiv-web",
                }
            async def download_image(self, url, *, pid, max_bytes, timeout=18.0):
                path = self.root / "9.png"; path.write_bytes(b"image")
                return str(path), path.stat().st_size

        async def scenario(td):
            service = PixivService(td); fake = FakeWeb(td); service.web = fake
            result = await service.search("双魚座", count=1, scope="g")
            return fake, result

        with tempfile.TemporaryDirectory() as td:
            fake, result = __import__('asyncio').run(scenario(td))
            self.assertEqual(result[0].pid, "9")
            self.assertEqual(fake.recommend_calls, 0)
            self.assertEqual(result[0].item.get("_selection_source"), "pixiv-web-search")

    def test_recommendation_tag_match_is_exact_after_normalization(self):
        self.assertTrue(PixivService._matches_query_tag(
            {"tags": [{"name": "Ave_Mujica"}, {"name": "若葉睦"}]}, "若葉睦"
        ))
        self.assertTrue(PixivService._matches_query_tag(
            {"tags": [{"name": "Ave_Mujica"}]}, "Ave Mujica"
        ))
        self.assertFalse(PixivService._matches_query_tag(
            {"tags": [{"name": "パチュリー"}]}, "パチュリー・ノーレッジ"
        ))

    def test_web_original_failure_falls_back_to_regular(self):
        from doge_pixiv.service import PixivError

        class FakeWeb:
            def __init__(self, root):
                self.root = Path(root)
                self.calls = []
            async def download_image(self, url, *, pid, max_bytes, timeout=18.0):
                self.calls.append(url)
                if "original" in url:
                    raise PixivError("too large")
                path = self.root / "regular.jpg"
                path.write_bytes(b"image")
                return str(path), path.stat().st_size

        with tempfile.TemporaryDirectory() as td:
            service = PixivService(td)
            fake = FakeWeb(td)
            service.web = fake
            item = {
                "id": "9:0", "pid": "9", "page": 0, "title": "x",
                "user": {"id": "1", "name": "a"}, "x_restrict": 0, "ai_type": 1,
                "meta_single_page": {"original_image_url": "https://i.pximg.net/9-original.png"},
                "image_urls": {"large": "https://i.pximg.net/9-regular.jpg"},
            }
            image = __import__('asyncio').run(service._download_web_item(item))
            self.assertEqual(image.quality, "regular")
            self.assertEqual(fake.calls, [
                "https://i.pximg.net/9-original.png",
                "https://i.pximg.net/9-regular.jpg",
            ])

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
