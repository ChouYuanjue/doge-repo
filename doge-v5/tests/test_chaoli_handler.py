from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

# Production plugin imports use data.plugins.*. Recreate that namespace while
# still loading the checked-out repository modules.
data_pkg = sys.modules.get("data") or types.ModuleType("data")
if not hasattr(data_pkg, "__path__"):
    data_pkg.__path__ = []  # type: ignore[attr-defined]
plugins_pkg = sys.modules.get("data.plugins") or types.ModuleType("data.plugins")
plugins_pkg.__path__ = [str(PLUGINS)]  # type: ignore[attr-defined]
data_pkg.plugins = plugins_pkg  # type: ignore[attr-defined]
sys.modules["data"] = data_pkg
sys.modules["data.plugins"] = plugins_pkg

import doge_chaoli.main as chaoli_module
from doge_chaoli.main import DogeChaoli


class _MessageObj:
    def __init__(self, text: str):
        self.message_str = text


class _Event:
    def __init__(self, current: str, original: str):
        self.message_str = current
        self.message_obj = _MessageObj(original)


async def _collect(event):
    plugin = object.__new__(DogeChaoli)
    return [item async for item in plugin.auto_preview(event)]


class ChaoliAutoPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_chaoli_command_does_not_trigger_passive_preview_after_slash_stripping(self):
        event = _Event(
            "chaoli preview https://chaoli.club/index.php/12202",
            "/chaoli preview https://chaoli.club/index.php/12202",
        )
        preview = AsyncMock(return_value="PREVIEW")
        with patch.object(chaoli_module.ChaoliService, "preview", preview), patch.object(
            chaoli_module, "text_result", lambda _event, text, markdown=False: ("RESULT", text)
        ):
            out = await _collect(event)
        self.assertEqual(out, [])
        preview.assert_not_awaited()

    async def test_any_explicit_slash_command_is_excluded_from_passive_chaoli_preview(self):
        event = _Event(
            "lookup https://chaoli.club/index.php/12202",
            "/lookup https://chaoli.club/index.php/12202",
        )
        preview = AsyncMock(return_value="PREVIEW")
        with patch.object(chaoli_module.ChaoliService, "preview", preview):
            out = await _collect(event)
        self.assertEqual(out, [])
        preview.assert_not_awaited()

    async def test_bare_chaoli_link_still_previews_exactly_once(self):
        url = "https://chaoli.club/index.php/12202"
        event = _Event(url, url)
        preview = AsyncMock(return_value="PREVIEW")
        with patch.object(chaoli_module.ChaoliService, "preview", preview), patch.object(
            chaoli_module, "text_result", lambda _event, text, markdown=False: ("RESULT", text)
        ):
            out = await _collect(event)
        self.assertEqual(out, [("RESULT", "PREVIEW")])
        preview.assert_awaited_once_with(url)


if __name__ == "__main__":
    unittest.main()
