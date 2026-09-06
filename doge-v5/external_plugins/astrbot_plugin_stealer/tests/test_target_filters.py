import asyncio
import sys
import tempfile
import types
from pathlib import Path


_DATA_ROOT = Path(tempfile.mkdtemp(prefix="stealer-target-filters-"))


def _install_astrbot_stubs() -> None:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )

    class DummyAstrBotConfig(dict):
        def save_config(self, updates=None):
            if updates:
                self.update(updates)

    astrbot_module = sys.modules.get("astrbot", types.ModuleType("astrbot"))
    api_module = sys.modules.get("astrbot.api", types.ModuleType("astrbot.api"))
    api_module.logger = logger
    api_module.AstrBotConfig = DummyAstrBotConfig

    event_module = sys.modules.get(
        "astrbot.api.event", types.ModuleType("astrbot.api.event")
    )
    event_module.AstrMessageEvent = object
    event_module.MessageChain = list

    message_components_module = sys.modules.get(
        "astrbot.api.message_components",
        types.ModuleType("astrbot.api.message_components"),
    )
    message_components_module.Image = object
    message_components_module.Plain = object

    star_module = sys.modules.get("astrbot.api.star", types.ModuleType("astrbot.api.star"))
    star_module.Context = object
    star_module.StarTools = types.SimpleNamespace(
        get_data_dir=lambda name: str((_DATA_ROOT / name).resolve())
    )

    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.message_components"] = message_components_module
    sys.modules["astrbot.api.star"] = star_module


_install_astrbot_stubs()

from core.commands.command_handler import CommandHandler
from core.config.config import PluginConfig


class DummyEvent:
    def __init__(self, group_id: str = "100", user_id: str = "42"):
        self._group_id = group_id
        self._user_id = user_id

    def get_group_id(self):
        return self._group_id

    def get_sender_id(self):
        return self._user_id

    def plain_result(self, text):
        return text


async def _collect_asyncgen(async_gen):
    results = []
    async for item in async_gen:
        results.append(item)
    return results


def _build_config() -> PluginConfig:
    return PluginConfig({}, None)


def test_whitelist_first_allows_whitelisted_group_even_if_user_is_blacklisted():
    cfg = _build_config()
    cfg.send_target_whitelist = ["group:100"]
    cfg.send_target_blacklist = ["user:42"]
    cfg.send_target_filter_mode = "whitelist_first"

    assert cfg.is_action_allowed("send", DummyEvent()) is True


def test_blacklist_first_blocks_blacklisted_user_inside_whitelisted_group():
    cfg = _build_config()
    cfg.send_target_whitelist = ["group:100"]
    cfg.send_target_blacklist = ["user:42"]
    cfg.send_target_filter_mode = "blacklist_first"

    assert cfg.is_action_allowed("send", DummyEvent()) is False


def test_user_whitelist_can_match_group_event_sender():
    cfg = _build_config()
    cfg.steal_target_whitelist = ["user:42"]

    assert cfg.is_action_allowed("steal", DummyEvent(group_id="100", user_id="42")) is True
    assert cfg.is_action_allowed("steal", DummyEvent(group_id="100", user_id="99")) is False


def test_group_filter_priority_command_updates_mode():
    cfg = _build_config()
    plugin = types.SimpleNamespace(plugin_config=cfg)
    handler = CommandHandler(plugin)

    results = asyncio.run(
        _collect_asyncgen(handler.group_filter(DummyEvent(), "send", "priority", "bl"))
    )

    assert cfg.send_target_filter_mode == "blacklist_first"
    assert results == ["已将发表情优先级设置为黑名单优先"]
