from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from doge_shared import lookup as lookup_mod
from doge_shared.agent_tools import DogeLookupTool
from doge_shared.lookup import LookupError, LookupService


class LookupWebTests(unittest.TestCase):
    def test_agent_tool_exposes_current_web_actions(self):
        action = DogeLookupTool().parameters["properties"]["action"]["enum"]
        self.assertIn("web", action)
        self.assertIn("read", action)
        self.assertIn("最新进展", DogeLookupTool().description)

    def test_anysearch_primary_needs_no_key(self):
        async def run():
            with patch.object(lookup_mod, "_anysearch_call", new=AsyncMock(return_value="## Search Results\n### 1. fresh")) as primary, \
                 patch.object(lookup_mod, "_bing_web_search", new=AsyncMock()) as fallback:
                out = await LookupService.web_search("new theorem", 5)
                self.assertIn("AnySearch anonymous", out)
                self.assertIn("fresh", out)
                primary.assert_awaited_once()
                fallback.assert_not_called()
        asyncio.run(run())

    def test_bing_public_fallback_when_anonymous_search_fails(self):
        async def run():
            with patch.object(lookup_mod, "_anysearch_call", new=AsyncMock(side_effect=LookupError("offline"))), \
                 patch.object(lookup_mod, "_bing_web_search", new=AsyncMock(return_value="Bing fallback result")) as fallback:
                out = await LookupService.web_search("recent result", 4)
                self.assertEqual(out, "Bing fallback result")
                fallback.assert_awaited_once_with("recent result", 4)
        asyncio.run(run())

    def test_extract_rejects_private_network_before_upstream(self):
        async def run():
            with patch.object(lookup_mod, "_anysearch_call", new=AsyncMock()) as upstream:
                for url in ("http://127.0.0.1/secret", "http://localhost/admin", "file:///etc/passwd"):
                    with self.assertRaises(LookupError):
                        await LookupService.web_extract(url)
                upstream.assert_not_called()
        asyncio.run(run())

    def test_extract_public_url_uses_anonymous_reader(self):
        async def run():
            fake_dns = [(2, 1, 6, "", ("93.184.216.34", 443))]
            with patch.object(lookup_mod.socket, "getaddrinfo", return_value=fake_dns), \
                 patch.object(lookup_mod, "_anysearch_call", new=AsyncMock(return_value='{"title":"Example","content":"hello"}')) as upstream:
                out = await LookupService.web_extract("https://example.com/a")
                self.assertIn("Web extract", out)
                self.assertIn("hello", out)
                upstream.assert_awaited_once_with("extract", {"url": "https://example.com/a"}, timeout=26)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
