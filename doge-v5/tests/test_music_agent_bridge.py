from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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

from astrbot.core.message.components import Music
from astrbot.core.message.message_event_result import MessageChain
import doge_shared.agent_bridge as bridge


class _PluginContext:
    def get_config(self):
        return {"data_dir": "/tmp"}


class _AgentContext:
    def __init__(self, event):
        self.event = event
        self.context = _PluginContext()


class _RunContext:
    def __init__(self, event):
        self.context = _AgentContext(event)


class _Event:
    def __init__(self):
        self.message_str = "original user text"
        self.is_wake = False
        self.is_at_or_wake_command = False
        self._force_stopped = False
        self._result = None
        self._extras = {}
        self.sent = []
        self.send = self._send

    async def _send(self, message):
        self.sent.append(message)

    def get_result(self): return self._result
    def clear_result(self): self._result = None
    def set_result(self, value): self._result = value
    def get_extra(self, key=None, default=None):
        if key is None: return self._extras if default is None else self._extras
        return self._extras.get(key, default)
    def set_extra(self, key, value): self._extras[key] = value
    def chain_result(self, chain):
        from astrbot.core.message.message_event_result import MessageEventResult
        result = MessageEventResult()
        result.chain = list(chain)
        return result


class _HandlerMeta:
    @staticmethod
    async def handler(event, **kwargs):
        card = Music(id=1859245776)
        object.__setattr__(card, "_type", "163")
        yield event.chain_result([card])
        # Simulate AstrBot wrappers also leaving the same result as residual.
        residual = event.chain_result([card])
        event.set_result(residual)


class MusicAgentBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_formal_music_output_is_sent_exactly_once(self):
        event = _Event()
        run = _RunContext(event)
        fake_inv = types.SimpleNamespace(capability_id="music.id")
        with patch.object(bridge, "match_invocation", return_value=fake_inv), \
             patch.object(bridge, "operation_by_id", return_value={"summary": "music"}), \
             patch.object(bridge, "_find_handler", AsyncMock(return_value=(_HandlerMeta, {}))):
            raw = await bridge.execute_formal_command(run, "/music id 1859245776")

        self.assertEqual(len(event.sent), 1)
        sent = event.sent[0]
        self.assertIsInstance(sent, MessageChain)
        self.assertEqual(len(sent.chain), 1)
        payload = sent.chain[0].toDict()
        self.assertEqual(payload["type"], "music")
        self.assertEqual(payload["data"]["type"], "163")
        self.assertEqual(payload["data"]["id"], 1859245776)

        tool_result = json.loads(raw)
        self.assertEqual(len(tool_result["rich_sent"]), 1)
        self.assertEqual(tool_result["rich_sent"][0]["data"]["id"], 1859245776)
        self.assertEqual(tool_result["media"][0]["delivery"], "direct")
        self.assertIn("already been delivered", tool_result["guidance"])


if __name__ == "__main__":
    unittest.main()
