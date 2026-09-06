from __future__ import annotations

from astrbot.api import logger
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import star_handlers_registry

UPSTREAM_STEALER_TOOL_NAMES = ("search_meme", "send_meme", "steal_meme")


def is_stealer_meme_root(handler) -> bool:
    module = str(getattr(handler, "handler_module_path", "") or "")
    if "astrbot_plugin_stealer" not in module:
        return False
    for filt in getattr(handler, "event_filters", []) or []:
        if isinstance(filt, CommandGroupFilter) and filt.parent_group is None and filt.group_name == "meme":
            return True
    return False


def remove_stealer_meme_command_group(registry=star_handlers_registry) -> int:
    removed = 0
    for handler in list(registry):
        if not is_stealer_meme_root(handler):
            continue
        registry.remove(handler)
        removed += 1
    if removed:
        logger.info("Doge media namespace: removed %d upstream /meme root; template /meme is authoritative", removed)
    return removed


def strip_legacy_stealer_tools(toolset) -> list[str]:
    removed: list[str] = []
    if toolset is None:
        return removed
    for name in UPSTREAM_STEALER_TOOL_NAMES:
        if toolset.get_tool(name) is not None:
            toolset.remove_tool(name)
            removed.append(name)
    return removed
