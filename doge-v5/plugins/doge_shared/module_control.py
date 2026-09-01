from __future__ import annotations

from dataclasses import dataclass

from astrbot.core import sp
from astrbot.core.star.star import star_map

_LOCKED = {"doge_core", "doge_admin"}
_EXCLUDED = {"doge_legacy", "doge_shared"}
_ALIASES = {
    "game": "doge_games",
    "games": "doge_games",
    "lab": "doge_playground",
    "playground": "doge_playground",
    "lang": "doge_linguistics",
    "language": "doge_linguistics",
    "linguistics": "doge_linguistics",
    "paper": "doge_papers",
    "papers": "doge_papers",
    "mat": "doge_materials",
    "materials": "doge_materials",
    "eng": "doge_engineering",
    "engineering": "doge_engineering",
    "type": "doge_typeset",
    "typeset": "doge_typeset",
    "diagram": "doge_diagrams",
    "diagrams": "doge_diagrams",
    "admin": "doge_admin",
    "core": "doge_core",
}


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    plugin_name: str
    short_name: str
    description: str
    enabled: bool
    locked: bool = False


def _short(plugin_name: str) -> str:
    return plugin_name.removeprefix("doge_")


def _session_payload(raw: object, umo: str) -> dict:
    """AstrBot stores session_plugin_config as {umo: {...}}."""
    if not isinstance(raw, dict):
        return {}
    nested = raw.get(umo, {})
    return dict(nested) if isinstance(nested, dict) else {}


async def get_session_module_config(umo: str) -> dict:
    raw = await sp.session_get(umo, "session_plugin_config", {})
    return _session_payload(raw, umo)


async def disabled_plugins(umo: str) -> set[str]:
    cfg = await get_session_module_config(umo)
    return {str(x) for x in cfg.get("disabled_plugins", []) if x}


async def is_plugin_enabled(umo: str, plugin_name: str) -> bool:
    if plugin_name in _LOCKED:
        return True
    return plugin_name not in await disabled_plugins(umo)


def available_doge_plugins(context) -> dict[str, object]:
    result: dict[str, object] = {}
    for star in context.get_all_stars():
        name = str(getattr(star, "name", "") or "")
        if not name.startswith("doge_") or name in _EXCLUDED:
            continue
        if getattr(star, "reserved", False):
            continue
        result[name] = star
    return result


def resolve_module(context, raw_name: str) -> str | None:
    name = str(raw_name or "").strip().lower().replace("-", "_")
    if not name:
        return None
    plugins = available_doge_plugins(context)
    candidate = _ALIASES.get(name)
    if candidate in plugins:
        return candidate
    if name in plugins:
        return name
    prefixed = name if name.startswith("doge_") else "doge_" + name
    if prefixed in plugins:
        return prefixed
    return None


async def list_modules(context, umo: str) -> list[ModuleInfo]:
    disabled = await disabled_plugins(umo)
    rows: list[ModuleInfo] = []
    for name, star in sorted(available_doge_plugins(context).items(), key=lambda x: _short(x[0])):
        rows.append(
            ModuleInfo(
                plugin_name=name,
                short_name=_short(name),
                description=str(getattr(star, "desc", "") or ""),
                enabled=name not in disabled or name in _LOCKED,
                locked=name in _LOCKED,
            )
        )
    return rows


async def set_module_enabled(context, umo: str, raw_name: str, enabled: bool) -> ModuleInfo:
    plugin_name = resolve_module(context, raw_name)
    if not plugin_name:
        raise ValueError(f"未知模块：{raw_name}")
    if plugin_name in _EXCLUDED or plugin_name == "doge_legacy":
        raise ValueError("Legacy 不属于正式热插拔模块")
    if plugin_name in _LOCKED and not enabled:
        raise ValueError("core/admin 是恢复入口，不能在群内关闭")

    cfg = await get_session_module_config(umo)
    enabled_set = {str(x) for x in cfg.get("enabled_plugins", []) if x}
    disabled_set = {str(x) for x in cfg.get("disabled_plugins", []) if x}
    if enabled:
        disabled_set.discard(plugin_name)
        enabled_set.add(plugin_name)
    else:
        enabled_set.discard(plugin_name)
        disabled_set.add(plugin_name)
    cfg["enabled_plugins"] = sorted(enabled_set)
    cfg["disabled_plugins"] = sorted(disabled_set)
    await sp.session_put(umo, "session_plugin_config", {umo: cfg})

    star = available_doge_plugins(context)[plugin_name]
    return ModuleInfo(
        plugin_name=plugin_name,
        short_name=_short(plugin_name),
        description=str(getattr(star, "desc", "") or ""),
        enabled=enabled,
        locked=plugin_name in _LOCKED,
    )


async def reset_modules(umo: str) -> None:
    """Return to AstrBot's native default: all non-Legacy loaded plugins enabled."""
    await sp.session_put(
        umo,
        "session_plugin_config",
        {umo: {"enabled_plugins": [], "disabled_plugins": []}},
    )


async def is_group_admin(event) -> bool:
    """Verify actual group owner/admin status; AstrBot global admin alone is not enough."""
    if not event.get_group_id():
        return False
    sender = str(event.get_sender_id())
    group = getattr(event.message_obj, "group", None)
    if not group or (not getattr(group, "group_owner", None) and not getattr(group, "group_admins", None)):
        getter = getattr(event, "get_group", None)
        if getter:
            try:
                group = await getter()
            except Exception:
                group = None
    if not group:
        return False
    owner = str(getattr(group, "group_owner", "") or "")
    admins = {str(x) for x in (getattr(group, "group_admins", None) or [])}
    return sender == owner or sender in admins


async def filter_toolset_for_session(umo: str, toolset) -> list[str]:
    """Apply the same session plugin switch to Agent tools that AstrBot applies to command handlers."""
    disabled = await disabled_plugins(umo)
    if not disabled or not toolset:
        return []
    removed: list[str] = []
    for tool in list(toolset.tools):
        module_path = getattr(tool, "handler_module_path", None)
        if not module_path:
            continue
        star = star_map.get(module_path)
        plugin_name = str(getattr(star, "name", "") or "") if star else ""
        if plugin_name in disabled and plugin_name not in _LOCKED:
            toolset.remove_tool(tool.name)
            removed.append(plugin_name)
    return sorted(set(removed))
