from __future__ import annotations

from astrbot.core import sp
from astrbot.core.star.session_llm_manager import SessionServiceManager

NORMAL_PERSONA_ID = "doge"
RESEARCH_PERSONA_ID = "doge_research"


def persona_id_for_mode(mode: str) -> str:
    value = str(mode or "").strip().lower()
    if value in {"normal", "default", "daily", "日常", "普通"}:
        return NORMAL_PERSONA_ID
    if value in {"research", "science", "scientific", "科研", "学术"}:
        return RESEARCH_PERSONA_ID
    raise ValueError("人格模式只支持 normal / research")


async def get_session_service_config(umo: str) -> dict:
    raw = await sp.get_async(
        scope="umo",
        scope_id=str(umo),
        key="session_service_config",
        default={},
    )
    return dict(raw) if isinstance(raw, dict) else {}


async def get_session_persona_id(umo: str) -> str | None:
    cfg = await get_session_service_config(umo)
    value = str(cfg.get("persona_id") or "").strip()
    return value or None


async def set_session_persona_mode(umo: str, mode: str) -> str:
    persona_id = persona_id_for_mode(mode)
    cfg = await get_session_service_config(umo)
    cfg["persona_id"] = persona_id
    await sp.put_async(
        scope="umo",
        scope_id=str(umo),
        key="session_service_config",
        value=cfg,
    )
    return persona_id


async def is_agent_enabled(umo: str) -> bool:
    return await SessionServiceManager.is_llm_enabled_for_session(str(umo))


async def set_agent_enabled(umo: str, enabled: bool) -> None:
    await SessionServiceManager.set_llm_status_for_session(str(umo), bool(enabled))
