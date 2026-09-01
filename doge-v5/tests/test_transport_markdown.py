from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

# Production imports use AstrBot's ``data.plugins`` package.  Recreate only
# that namespace for repository tests; the actual modules still come from the
# checked-out plugin tree.
data_pkg = types.ModuleType("data")
data_pkg.__path__ = []  # type: ignore[attr-defined]
plugins_pkg = types.ModuleType("data.plugins")
plugins_pkg.__path__ = [str(PLUGINS)]  # type: ignore[attr-defined]
data_pkg.plugins = plugins_pkg  # type: ignore[attr-defined]
sys.modules.setdefault("data", data_pkg)
sys.modules.setdefault("data.plugins", plugins_pkg)

from doge_core.main import DogeCore


class _Result:
    def __init__(self, llm: bool):
        self.llm = llm
        self.markdown = None

    def is_llm_result(self) -> bool:
        return self.llm

    def use_markdown(self, value):
        self.markdown = value
        return self


class _Event:
    def __init__(self, platform: str, result: _Result):
        self.platform = platform
        self.result = result

    def get_platform_name(self):
        return self.platform

    def get_result(self):
        return self.result


class TransportMarkdownTests(unittest.TestCase):
    def _run(self, platform: str, llm: bool):
        result = _Result(llm)
        event = _Event(platform, result)
        asyncio.run(DogeCore.transport_markdown_result(object(), event))
        return result.markdown

    def test_qq_official_llm_forces_markdown(self):
        self.assertIs(self._run("qq_official", True), True)

    def test_napcat_onebot_forces_plain_text(self):
        self.assertIs(self._run("aiocqhttp", True), False)

    def test_qq_official_non_llm_keeps_plugin_media_choice(self):
        self.assertIsNone(self._run("qq_official", False))


if __name__ == "__main__":
    unittest.main()
