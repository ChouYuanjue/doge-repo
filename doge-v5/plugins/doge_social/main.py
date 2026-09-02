from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.module_control import is_group_admin
from data.plugins.doge_shared.presentation import text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head

_SENTINEL = "__doge_no_group__"


@register("doge_social", "runnel", "Doge 群聊社交增强控制面", "5.10.9")
class DogeSocial(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

    def _external(self, name: str) -> tuple[Any, Any]:
        meta = self.context.get_registered_star(name)
        if not meta or not getattr(meta, "star_cls", None):
            raise RuntimeError(f"社交引擎未加载：{name}")
        return meta, meta.star_cls

    @staticmethod
    async def _require_group_manager(event: AstrMessageEvent) -> str:
        gid = str(event.get_group_id() or "")
        if not gid:
            raise PermissionError("这个开关只按群配置，请在群聊里操作")
        if not event.is_admin() and not await is_group_admin(event):
            raise PermissionError("只有 Doge 管理员、群主或群管理员可以修改当前群")
        return gid

    @staticmethod
    def _real_groups(values: Any) -> list[str]:
        return sorted({str(x) for x in (values or []) if str(x) and str(x) != _SENTINEL})

    @staticmethod
    def _guarded_groups(values: Any) -> list[str]:
        return [_SENTINEL, *DogeSocial._real_groups(values)]

    @staticmethod
    def _set_cfg(meta: Any, updates: dict[str, Any]) -> None:
        cfg = getattr(meta, "config", None)
        if cfg is None:
            raise RuntimeError("上游插件没有可写配置")
        for key, value in updates.items():
            cfg[key] = value
        cfg.save_config()

    def _set_air_groups(self, gid: str, enabled: bool) -> tuple[list[str], list[str]]:
        meta, engine = self._external("astrbot_plugin_group_chat_plus")
        groups = set(self._real_groups(getattr(engine, "enabled_groups", [])))
        proactive = set(self._real_groups(getattr(engine, "proactive_enabled_groups", [])))
        if enabled:
            groups.add(gid)
            proactive.add(gid)
        else:
            groups.discard(gid)
            proactive.discard(gid)
        guarded = self._guarded_groups(groups)
        guarded_proactive = self._guarded_groups(proactive)
        updates = {
            "enable_group_chat": True,
            "enabled_groups": guarded,
            "enable_proactive_chat": True,
            "proactive_enabled_groups": guarded_proactive,
            "enable_proactive_ai_judge": True,
            "decision_ai_provider_id": "deepseek/deepseek-v4-flash",
            "enable_decision_ai_reasoning": False,
            "enable_proactive_ai_reasoning": False,
        }
        self._set_cfg(meta, updates)
        for key, value in updates.items():
            if hasattr(engine, key):
                setattr(engine, key, value)
        # ProactiveChatManager keeps its group allow-list in class state.
        try:
            module = __import__(
                engine.__class__.__module__.rsplit(".", 1)[0] + ".utils.proactive_chat_manager",
                fromlist=["ProactiveChatManager"],
            )
            manager = module.ProactiveChatManager
            manager._proactive_enabled_groups = guarded_proactive
        except Exception:
            pass
        return self._real_groups(guarded), self._real_groups(guarded_proactive)

    def _set_emoji_group(self, gid: str, enabled: bool) -> list[str]:
        meta, engine = self._external("astrbot_plugin_stealer")
        cfg = engine.plugin_config
        send = set(self._real_groups([x.removeprefix("group:") for x in cfg.send_target_whitelist if str(x).startswith("group:")]))
        steal = set(self._real_groups([x.removeprefix("group:") for x in cfg.steal_target_whitelist if str(x).startswith("group:")]))
        if enabled:
            send.add(gid); steal.add(gid)
        else:
            send.discard(gid); steal.discard(gid)
        send_wl = [f"group:{_SENTINEL}", *[f"group:{x}" for x in sorted(send)]]
        steal_wl = [f"group:{_SENTINEL}", *[f"group:{x}" for x in sorted(steal)]]
        updates = {
            "steal_meme": True,
            "auto_send_meme": True,
            "send_target_whitelist": send_wl,
            "steal_target_whitelist": steal_wl,
            "send_target_filter_mode": "whitelist_first",
            "steal_target_filter_mode": "whitelist_first",
            "meme_chance": 0.22,
            "smart_meme_selection": True,
            "enable_natural_emotion_analysis": True,
            "vision_provider_id": "deepseek/deepseek-v4-flash-vision-exp",
            "emotion_analysis_provider_id": "deepseek/deepseek-v4-flash",
        }
        self._set_cfg(meta, updates)
        engine.update_config(updates)
        return sorted(send)

    @contextmanager
    def _meme_event(self, event: AstrMessageEvent, payload: str):
        old_message = event.message_str
        plains = [seg for seg in event.get_messages() if isinstance(seg, Comp.Plain)]
        old_plain = [seg.text for seg in plains]
        event.message_str = payload
        if plains:
            plains[0].text = payload
            for seg in plains[1:]:
                seg.text = ""
        try:
            yield
        finally:
            event.message_str = old_message
            for seg, text in zip(plains, old_plain):
                seg.text = text

    async def _meme_make(self, event: AstrMessageEvent, payload: str):
        _, engine = self._external("astrbot_plugin_meme_generator")
        if not payload.strip():
            raise ValueError("用法：/social meme make <模板关键词> [文字参数]")
        with self._meme_event(event, payload.strip()):
            data = await engine.meme_manager.generate_meme(event)
        if not data:
            raise ValueError("没有匹配到模板，或当前还在冷却/资源初始化")
        return event.chain_result([Comp.Image.fromBytes(data)])

    async def _meme_list(self, query: str = "") -> str:
        _, engine = self._external("astrbot_plugin_meme_generator")
        keys = await engine.meme_manager.template_manager.get_all_keywords()
        q = query.strip().lower()
        if q:
            keys = [k for k in keys if q in str(k).lower()]
        shown = keys[:120]
        suffix = f"\n……另有 {len(keys)-len(shown)} 个" if len(keys) > len(shown) else ""
        return "Meme 模板关键词\n" + " · ".join(map(str, shown)) + suffix

    async def _meme_info(self, keyword: str) -> str:
        _, engine = self._external("astrbot_plugin_meme_generator")
        info = await engine.meme_manager.get_template_info(keyword.strip())
        if not info:
            raise ValueError("没有这个 meme 模板")
        return (
            f"{info['name']}\n"
            f"关键词：{' / '.join(map(str, info.get('keywords') or []))}\n"
            f"图片：{info['min_images']}–{info['max_images']} 张；"
            f"文字：{info['min_texts']}–{info['max_texts']} 段\n"
            f"标签：{' / '.join(map(str, info.get('tags') or [])) or '—'}"
        )

    @filter.command("social")
    async def social(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "social")
            parts = split_head(payload, 2)
            domain = parts[0].lower() if parts else "help"
            action = parts[1].lower() if len(parts) > 1 else "status"
            rest = parts[2].strip() if len(parts) > 2 else ""

            if domain in {"help", "?"}:
                yield text_result(event,
                    "/social air on|off|status    当前群读空气 + 合适时机主动发言\n"
                    "/social emoji on|off|status  当前群自动收集/选择大表情包\n"
                    "/social meme list [过滤词]\n"
                    "/social meme info <模板>\n"
                    "/social meme make <模板> [文字]  （支持当前/引用图片与 @ 人）",
                    markdown=False)
                return

            if domain == "air":
                gid = str(event.get_group_id() or "")
                if action in {"on", "off"}:
                    gid = await self._require_group_manager(event)
                    groups, proactive = self._set_air_groups(gid, action == "on")
                    yield text_result(event, f"当前群读空气：{'ON' if action=='on' else 'OFF'}\n启用群：{len(groups)}；主动发言群：{len(proactive)}", markdown=False)
                    return
                _, engine = self._external("astrbot_plugin_group_chat_plus")
                groups = self._real_groups(getattr(engine, "enabled_groups", []))
                proactive = self._real_groups(getattr(engine, "proactive_enabled_groups", []))
                state = bool(gid and gid in groups)
                yield text_result(event, f"当前群读空气：{'ON' if state else 'OFF'}\n主动发言：{'ON' if gid in proactive else 'OFF'}\n默认策略：未显式开启的群绝不触发。", markdown=False)
                return

            if domain in {"emoji", "sticker"}:
                gid = str(event.get_group_id() or "")
                if action in {"on", "off"}:
                    gid = await self._require_group_manager(event)
                    groups = self._set_emoji_group(gid, action == "on")
                    yield text_result(event, f"当前群自动大表情：{'ON' if action=='on' else 'OFF'}\n启用群：{len(groups)}；会按标签/语义和回复情绪挑选。", markdown=False)
                    return
                _, engine = self._external("astrbot_plugin_stealer")
                cfg = engine.plugin_config
                groups = sorted(str(x).removeprefix("group:") for x in cfg.send_target_whitelist if str(x).startswith("group:") and _SENTINEL not in str(x))
                total = engine.db_service.count_total() if getattr(engine, "db_service", None) else 0
                yield text_result(event, f"当前群自动大表情：{'ON' if gid in groups else 'OFF'}\n已分类大表情：{total}\n启用群：{len(groups)}", markdown=False)
                return

            if domain == "meme":
                if action in {"list", "ls"}:
                    yield text_result(event, await self._meme_list(rest), markdown=False); return
                if action in {"info", "detail"}:
                    if not rest: raise ValueError("用法：/social meme info <模板关键词>")
                    yield text_result(event, await self._meme_info(rest), markdown=False); return
                if action in {"make", "gen", "generate"}:
                    yield await self._meme_make(event, rest); return
                raise ValueError("用法：/social meme list|info|make ...")

            raise ValueError("用法：/social air|emoji|meme ...")
        except Exception as exc:
            yield text_result(event, f"ERROR  /social\n  {exc}\n\n  /social help", markdown=False)
