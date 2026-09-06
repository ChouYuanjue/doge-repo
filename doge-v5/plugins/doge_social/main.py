from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.agent_tools import DogeEmojiSearchTool, DogeEmojiSendTool, DogeEmojiStealTool, register_domain_tools
from data.plugins.doge_shared.module_control import is_group_admin
from data.plugins.doge_shared.presentation import text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head

_SENTINEL = "__doge_no_group__"


@register("doge_social", "runnel", "Doge 群聊社交增强：读空气与 vendored 大表情/贴纸库", "5.10.11")
class DogeSocial(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        register_domain_tools(
            context,
            "doge_social",
            DogeEmojiSearchTool(),
            DogeEmojiSendTool(),
            DogeEmojiStealTool(),
        )

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
    def _require_bot_admin(event: AstrMessageEvent) -> None:
        if not event.is_admin():
            raise PermissionError("这个大表情/贴纸库管理动作只允许 Bot 管理员执行")

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
                    "/social emoji on|off|status  当前群自动收集/选择大表情与贴纸\n"
                    "模板 meme 使用独立的 /meme；两个功能互不影响。",
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
                _, engine = self._external("astrbot_plugin_stealer")
                handler = engine.command_handler

                if action in {"help", "?"}:
                    yield text_result(event,
                        "/social emoji on|off|status    当前群大表情/贴纸库开关\n"
                        "/social emoji list [分类] [数量] [页码]\n"
                        "/social emoji collect on|off   全局自动收集（Bot 管理员）\n"
                        "/social emoji auto on|off      全局自动发送（Bot 管理员）\n"
                        "/social emoji capture          30 秒强制收图窗口（Bot 管理员）\n"
                        "/social emoji analysis on|off  情绪分析（Bot 管理员）\n"
                        "/social emoji emotion-stats\n"
                        "/social emoji tag-stats [N]\n"
                        "/social emoji delete|blacklist <编号|文件名>\n"
                        "/social emoji scope <编号|文件名> <public|local>\n"
                        "/social emoji group <scope> <wl|bl> <add|del|clear|show> [target] [id]\n"
                        "/social emoji clean|capacity|rebuild-index\n"
                        "固定模板 meme 使用独立 /meme；不受这些开关影响。", markdown=False)
                    return

                if action in {"on", "off"}:
                    gid = await self._require_group_manager(event)
                    groups = self._set_emoji_group(gid, action == "on")
                    yield text_result(event, f"当前群自动大表情/贴纸：{'ON' if action=='on' else 'OFF'}\n启用群：{len(groups)}；会按标签/语义和回复情绪挑选。模板 /meme 不受此开关影响。", markdown=False)
                    return

                if action == "status":
                    groups = sorted(str(x).removeprefix("group:") for x in engine.plugin_config.send_target_whitelist if str(x).startswith("group:") and _SENTINEL not in str(x))
                    total = engine.db_service.count_total() if getattr(engine, "db_service", None) else 0
                    yield text_result(event, f"当前群自动大表情/贴纸：{'ON' if gid in groups else 'OFF'}\n已分类大表情/贴纸：{total}\n启用群：{len(groups)}\n模板 /meme：独立可用，不受这里的开关影响。", markdown=False)
                    return

                args = rest.split() if rest else []
                if action == "list":
                    category = args[0] if len(args) > 0 else ""
                    limit = args[1] if len(args) > 1 else "10"
                    page = args[2] if len(args) > 2 else "1"
                    async for item in handler.list_images(event, category, limit, page): yield item
                    return
                if action in {"emotion-stats", "emotion_stats"}:
                    async for item in handler.emotion_analysis_stats(event): yield item
                    return

                # Remaining operations preserve the upstream Bot-admin boundary.
                self._require_bot_admin(event)
                if action == "collect":
                    if not args or args[0] not in {"on", "off"}: raise ValueError("用法：/social emoji collect on|off")
                    it = handler.meme_on(event) if args[0] == "on" else handler.meme_off(event)
                    async for item in it: yield item
                    return
                if action == "auto":
                    if not args or args[0] not in {"on", "off"}: raise ValueError("用法：/social emoji auto on|off")
                    it = handler.auto_on(event) if args[0] == "on" else handler.auto_off(event)
                    async for item in it: yield item
                    return
                if action in {"capture", "偷"}:
                    async for item in handler.capture(event): yield item
                    return
                if action in {"analysis", "natural-analysis", "natural_analysis"}:
                    mode = args[0] if args else ""
                    async for item in handler.toggle_natural_analysis(event, mode): yield item
                    return
                if action in {"clear-analysis-cache", "clear_emotion_cache"}:
                    async for item in handler.clear_emotion_cache(event): yield item
                    return
                if action in {"tag-stats", "tag_stats"}:
                    # Upstream 2.8.x accidentally appended raw-cache cleanup code to
                    # tag_stats and left command_handler.clean undefined. Consume only
                    # the intended first statistics result, then close the generator.
                    gen = handler.tag_stats(event, args[0] if args else "")
                    try:
                        yield await gen.__anext__()
                    finally:
                        await gen.aclose()
                    return
                if action == "clean":
                    deleted = await handler._force_clean_raw_directory()
                    yield text_result(event, f"raw 临时缓存清理完成，共删除 {deleted} 张；已分类大表情/贴纸不受影响。", markdown=False)
                    return
                if action == "capacity":
                    async for item in handler.enforce_capacity(event): yield item
                    return
                if action in {"rebuild-index", "rebuild_index"}:
                    async for item in handler.rebuild_index(event): yield item
                    return
                if action == "delete":
                    async for item in handler.delete_image(event, args[0] if args else ""): yield item
                    return
                if action == "blacklist":
                    async for item in handler.blacklist_image(event, args[0] if args else ""): yield item
                    return
                if action == "scope":
                    async for item in handler.set_image_scope(event, args[0] if args else "", args[1] if len(args)>1 else ""): yield item
                    return
                if action == "group":
                    padded=(args+["","","","",""])[:5]
                    async for item in handler.group_filter(event, *padded): yield item
                    return
                raise ValueError("用法：/social emoji help")

            raise ValueError("用法：/social air|emoji ...；模板 meme 请用 /meme")
        except Exception as exc:
            yield text_result(event, f"ERROR  /social\n  {exc}\n\n  /social help", markdown=False)
