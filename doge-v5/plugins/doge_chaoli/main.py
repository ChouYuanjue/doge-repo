from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import File, Image, Node, Nodes, Plain
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.agent_tools import DogeChaoliTool, register_domain_tools
from data.plugins.doge_shared.chaoli import ChaoliError, ChaoliService
from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.module_control import is_group_admin, is_plugin_enabled
from data.plugins.doge_shared.presentation import long_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, original_message_text, split_head
from .daily_report import DailyReportBundle, build_daily_report, load_latest_daily_report
from .push import (
    DAILY_DEFAULT_TIME,
    ChaoliDailyPool,
    ChaoliPushStore,
    PushEvent,
    classify_cards,
    format_daily_message,
    format_push_message,
    shanghai_date,
    daily_issue_window,
    latest_closed_issue_date,
)

HELP = """Doge Chaoli /chaoli
  /chaoli search <查询> [--board 板块] [--limit N]
                                      原生论坛搜索；支持 #精品 等超理搜索语法
  /chaoli latest [板块] [数量]           最新主题（默认跳过置顶）；板块可用 数学/物理/化学/生物/技术/语言/社科/科幻/合集
  /chaoli channel <板块> [数量]         指定板块主题流
  /chaoli read <帖子号|链接>            读取主题；长楼自动压缩中段
  /chaoli floor <帖子号> <楼层>         精确读取一层
  /chaoli context <帖子号> <楼层> [1-3] 读取该层及前后文
  /chaoli outline <帖子号|链接>         长帖楼层提纲，按层快速定位
  /chaoli user <用户名|用户ID|链接>       用户公开主页与近期活动
  /chaoli links <帖子号|链接>           沿帖内超理链接阅读相关旧帖
  /chaoli preview <帖子号|链接>         一屏预览
  /chaoli push on [板块]                开启本群新帖/旧帖新回复推送（群主/管理员）
  /chaoli push off [板块]               关闭本群推送；不写板块则全部关闭
  /chaoli push status                   查看本群订阅
  /chaoli push test [板块]              预览实时推送样式，不改变水位（群主/管理员）
  /chaoli daily                         单条合并转发最近一期（PDF 原件与逐页图片在同一聊天记录）；不占群文件、不临时生成
  /chaoli daily push                    管理员重发最近一期已生成日报；仅当刊期为今天才推进今天水位
  /chaoli daily on [HH:MM]              开启本群日报，默认 23:45（Doge 管理员/群主/群管理员）
  /chaoli daily off|status|test          日报管理/已生成刊物预览；每期在本群设置的截稿时间自动生成
  /chaoli status                        检查 Chaoli 专用代理链
日报以本群每天固定截稿时刻（默认 23:45，北京时间）向前24小时为窗口；候选由论坛 #今日活跃 提供。写稿模型沿用当前普通聊天的已配置候补顺序，但禁止使用私人付费 DeepSeek/OpenRouter 额度。
搜索使用超理前端自己的 POST AJAX 接口，不经过会被 Cloudflare 拦截的 GET 查询页。
严格归属：首帖作者/最后回复者分开，真实楼号/删除楼保留，引用与本层正文分开；用户名只代表论坛账号，不推断现实身份。"""


@register("doge_chaoli", "runnel", "超理论坛原生搜索、精确楼层、单条转发 PDF 日报与实时群推送", "5.10.44")
class DogeChaoli(Star):
    PUSH_LIMIT = 30
    PUSH_INTERVAL = max(60, min(int(os.getenv("DOGE_CHAOLI_PUSH_INTERVAL", "120") or 120), 600))
    CHANNEL_LABELS = {
        "all": "全站", "maths": "数学", "physics": "物理", "chem": "化学",
        "biology": "生物", "tech": "技术", "others": "其他", "admin": "站务",
        "lang": "语言", "soc-sci": "社科", "sci-fi": "科幻", "collections": "合集",
    }

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.data_dir = StarTools.get_data_dir("doge_chaoli")
        self.push_store = ChaoliPushStore(self.data_dir / "push-subscriptions.json")
        self.daily_pool = ChaoliDailyPool(self.data_dir / "daily-pool.json")
        self._push_lock = asyncio.Lock()
        self._push_task: asyncio.Task | None = None
        register_domain_tools(context, "doge_chaoli", DogeChaoliTool())
        if self.push_store.load_error:
            logger.warning(f"doge chaoli push state load failed: {self.push_store.load_error}")

    @filter.on_platform_loaded()
    async def on_platform_loaded(self):
        if self._push_task is None or self._push_task.done():
            self._push_task = asyncio.create_task(self._push_loop(), name="doge-chaoli-push")
            logger.info(f"doge chaoli push+daily loop started interval={self.PUSH_INTERVAL}s daily_default={DAILY_DEFAULT_TIME}")

    async def terminate(self):
        task, self._push_task = self._push_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @classmethod
    def _channel_label(cls, slug: str) -> str:
        return cls.CHANNEL_LABELS.get(slug, slug)

    async def _push_command(self, event: AstrMessageEvent, raw: str) -> str:
        if not event.get_group_id():
            raise ValueError("超理推送订阅只支持群聊")
        parts = split_head(raw.strip(), 1)
        sub = parts[0].lower() if parts else "status"
        arg = parts[1].strip() if len(parts) > 1 else ""
        umo = str(event.unified_msg_origin)

        if sub in {"status", "show", "list"}:
            async with self._push_lock:
                slugs = self.push_store.channel_slugs(umo)
            if not slugs:
                return f"本群未开启超理自动推送。检查间隔约 {self.PUSH_INTERVAL} 秒。"
            labels = "、".join(self._channel_label(x) for x in slugs)
            return f"本群超理自动推送：{labels}。新帖和旧帖新回复分开标记；检查间隔约 {self.PUSH_INTERVAL} 秒。"

        if not await is_group_admin(event):
            raise ValueError("只有 Doge 管理员、本群群主或群管理员可以修改或测试超理推送")

        if sub in {"on", "add", "enable"}:
            slug = ChaoliService._channel_slug(arg or "all")
            # Prime from the current active window; enabling never backfills history.
            cards = await ChaoliService.latest_cards(slug, self.PUSH_LIMIT)
            async with self._push_lock:
                result = self.push_store.enable(umo, slug, cards)
                state = self.push_store.channel_state(umo, slug)
            label = self._channel_label(slug)
            if result == "covered":
                return f"本群已经订阅全站，已覆盖{label}。"
            if result == "exists":
                return f"本群已经订阅{label}，水位保持不变。"
            water = int((state or {}).get("max_seen_thread_id") or 0)
            return f"已开启本群超理{label}推送，从当前水位 #{water} 开始；不会补发历史。之后会区分【新帖】和【旧帖新回复】。"

        if sub in {"off", "del", "remove", "disable"}:
            slug = ChaoliService._channel_slug(arg) if arg else None
            async with self._push_lock:
                result = self.push_store.disable(umo, slug)
            if result == "covered":
                return "当前是全站订阅，不能只关闭其中一个板块；用 /chaoli push off 关闭后再按板块开启。"
            if result == "missing":
                return "本群没有这项超理推送订阅。"
            return "已关闭本群全部超理推送。" if slug is None else f"已关闭本群超理{self._channel_label(slug)}推送。"

        if sub in {"test", "preview"}:
            slug = ChaoliService._channel_slug(arg or "all")
            cards = await ChaoliService.latest_cards(slug, 1)
            return format_push_message([PushEvent("new_thread", cards[0])], test=True)

        raise ValueError("用法：/chaoli push on [板块] | off [板块] | status | test [板块]")

    @staticmethod
    def _normalize_daily_time(value: str | None) -> str:
        raw = str(value or DAILY_DEFAULT_TIME).strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw):
            raise ValueError("日报时间必须是 HH:MM，例如 23:45")
        return raw

    async def _daily_command(self, event: AstrMessageEvent, raw: str) -> str | None:
        if not event.get_group_id():
            raise ValueError("超理日报订阅只支持群聊")
        parts = raw.strip().split()
        sub = parts[0].lower() if parts else "now"
        umo = str(event.unified_msg_origin)
        # One inbound message may pass both the raw /chaoli command and the
        # Agent tool bridge. Mark it *before* awaiting QQ delivery so only
        # the first entry can send the edition, even with concurrent handlers.
        if sub in {"now","show","today","push","send","test","preview"}:
            get_extra=getattr(event,"get_extra",None)
            if callable(get_extra) and get_extra("_doge_chaoli_daily_sent_from_event"):
                logger.info("doge chaoli duplicate daily command suppressed for same event")
                return None
            set_extra=getattr(event,"set_extra",None)
            if callable(set_extra):
                set_extra("_doge_chaoli_daily_sent_from_event",True)
        if sub in {"now", "show", "today"}:
            report = self._latest_existing_report(umo)
            delivered = await self._send_daily_report(umo, report)
            if not delivered:
                raise ValueError("已有日报重发失败；不会临时生成新刊")
            return None
        if sub == "status":
            async with self._push_lock:
                state = self.push_store.daily_state(umo)
            return f"本群超理日报：{'ON' if state['enabled'] else 'OFF'} · 截稿/推送时间 {state['time']}（北京时间，统计此前24小时）· 最近推送 {state['last_sent'] or '无'}。/chaoli daily 仅取已生成的最新一期，不会临时生成。"
        if not await is_group_admin(event):
            raise ValueError("只有 Doge 管理员、本群群主或群管理员可以修改、测试或主动推送超理日报")
        if sub in {"push", "send"}:
            report = self._latest_existing_report(umo)
            today = shanghai_date()
            try:
                delivered = await self._send_daily_report(umo, report)
            except Exception as exc:
                logger.warning(f"doge chaoli manual daily push failed umo={umo}: {type(exc).__name__}: {exc}")
                delivered = False
            if not delivered:
                raise ValueError("超理日报主动推送失败；发送水位未推进")
            async with self._push_lock:
                state = self.push_store.daily_state(umo)
                if state.get("enabled") and report.date == today:
                    self.push_store.mark_daily_sent(umo, today)
            logger.info(f"doge chaoli manual archived daily resent umo={umo} issue_date={report.date}")
            # Direct platform send is the command result. Returning None prevents
            # raw commands and Agent formal bridges from duplicating the digest.
            return None
        if sub in {"on", "enable"}:
            time_text = self._normalize_daily_time(parts[1] if len(parts) > 1 else DAILY_DEFAULT_TIME)
            async with self._push_lock:
                state = self.push_store.set_daily(umo, True, time_text)
            return f"已开启本群超理日报，每天北京时间 {state['time']}，统计该时刻往前24小时；浏览命令仅显示已有日报。实时 push 保持原设置。"
        if sub in {"off", "disable"}:
            async with self._push_lock:
                self.push_store.set_daily(umo, False)
            return "已关闭本群超理日报；实时 push 不受影响。"
        if sub in {"test", "preview"}:
            report = self._latest_existing_report(umo)
            delivered = await self._send_daily_report(umo, report)
            if not delivered:
                raise ValueError("超理日报测试发送失败")
            return None
        raise ValueError("用法：/chaoli daily [now|push|on [HH:MM]|off|status|test]")

    async def _ensure_daily_pool(self) -> None:
        today = shanghai_date()
        if self.daily_pool.data.get("date") == today:
            return
        # A day rollover or restart may otherwise lose activity that happened
        # while Doge was offline. Seed from the forum-owner JSON POST first;
        # native POST search is only the transport fallback.
        try:
            cards = await ChaoliService.daily_json_cards(self.PUSH_LIMIT)
            self.daily_pool.reset(today, cards)
            logger.info(f"doge chaoli daily pool seeded date={today} cards={len(cards)} via official JSON POST")
            return
        except Exception as json_exc:
            logger.info(f"doge chaoli daily JSON seed unavailable: {type(json_exc).__name__}: {json_exc}")
        try:
            cards = await ChaoliService.daily_native_cards(self.PUSH_LIMIT)
            self.daily_pool.reset(today, cards)
            logger.info(f"doge chaoli daily pool seeded date={today} cards={len(cards)} via native POST fallback")
        except Exception as exc:
            self.daily_pool.reset(today, [])
            logger.warning(f"doge chaoli daily pool seed failed: {type(exc).__name__}: {exc}")

    def _latest_existing_report(self, umo: str) -> DailyReportBundle:
        state=self.push_store.daily_state(umo)
        preferred_time=self._normalize_daily_time(state.get("time"))
        now=datetime.now(ZoneInfo("Asia/Shanghai"))
        report=load_latest_daily_report(
            self.data_dir,as_of=now,preferred_time=preferred_time,
        )
        if report is None:
            cutoff=latest_closed_issue_date(now,preferred_time)
            raise ValueError(
                f"尚无已生成且有真实楼层证据的超理日报存档。"
                f"本群固定截稿时间为北京时间 {preferred_time}；"
                f"当前最多只能查看截止 {cutoff} 的已完成刊期。"
                "历史空白/401 日报不能充当正式刊物；请等待下一次定时生成。"
            )
        return report

    @staticmethod
    def _free_daily_provider(provider) -> bool:
        """Report never spends the user's personal API funds.

        Derive routes from ordinary AstrBot chat fallback configuration. Keep
        only the explicitly free local sources (and :free OpenRouter models),
        in the same order as chat. Never silently use official paid DeepSeek.
        """
        if provider is None:
            return False
        config=getattr(provider,"provider_config",None)
        if not isinstance(config,dict):
            # Lightweight providers in tests and custom nonstandard adapters.
            return True
        name=str(config.get("id") or "")
        source=str(config.get("provider_source_id") or name.split("/",1)[0]).lower()
        if source in {"workbuddy","freellmapi"}:
            return True
        if source=="openrouter" and str(config.get("model") or "").endswith(":free"):
            return True
        return False

    async def _daily_report_for_send(
        self, today: str, umo: str | None = None,
        issue_time: str = DAILY_DEFAULT_TIME,
    ) -> DailyReportBundle:
        cards, source = await self._daily_cards_for_send(today)
        selected=await self.context.get_using_provider_async(umo=umo)

        # Exactly the ordinary chat provider chain from this session's config,
        # minus paid routes explicitly disallowed for daily production.
        cfg_getter=getattr(self.context,"get_config",None)
        cfg=cfg_getter(umo=umo) if callable(cfg_getter) else {}
        provider_settings=cfg.get("provider_settings",{}) if hasattr(cfg,"get") else {}
        if not isinstance(provider_settings,dict):
            provider_settings={}
        fallback_ids=provider_settings.get("fallback_chat_models",[])
        if not isinstance(fallback_ids,list):
            fallback_ids=[]
        get_by_id=getattr(self.context,"get_provider_by_id",None)
        route=[selected] if selected is not None else []
        if callable(get_by_id):
            for pid in fallback_ids:
                if not isinstance(pid,str) or not pid:
                    continue
                try:
                    alternate=get_by_id(pid)
                except Exception:
                    alternate=None
                if alternate is not None and all(alternate is not x for x in route):
                    route.append(alternate)
        free_route=[p for p in route if self._free_daily_provider(p)]
        if not free_route:
            raise ValueError(
                "当前聊天路由中没有可用的免费日报写稿模型；"
                "已禁止自动使用官方 DeepSeek 或付费 OpenRouter 额度。"
            )
        primary, backups=free_route[0],free_route[1:]
        def provider_id(p):
            try:return str(p.meta().id)
            except Exception:return str(getattr(p,"provider_config",{}).get("id","unknown"))
        logger.info(
            "doge chaoli daily scheduled cutoff=%s %s, "
            "chat route selected=%s, allowed_free_route=%s, "
            "paid_candidates_omitted=%d",
            today,issue_time,provider_id(selected) if selected else "none",
            [provider_id(p) for p in free_route],len(route)-len(free_route),
        )
        return await build_daily_report(
            self.data_dir,cards,today,source,
            provider=primary,fallback_providers=tuple(backups),issue_time=issue_time,
        )

    async def _daily_forward_identity(self, umo: str) -> tuple[str, str]:
        """Resolve the active OneBot account without hardcoding Doge's QQ id."""
        try:
            platform_id = str(umo).split(":", 1)[0]
            get_platform = getattr(self.context, "get_platform_inst", None)
            platform = get_platform(platform_id) if callable(get_platform) else None
            bot = getattr(platform, "bot", None)
            call_action = getattr(bot, "call_action", None)
            if callable(call_action):
                info = await call_action("get_login_info")
                if isinstance(info, dict):
                    uin = str(info.get("user_id") or info.get("uin") or "").strip()
                    name = str(info.get("nickname") or info.get("nick") or "豆子").strip() or "豆子"
                    if uin:
                        return uin, name
        except Exception as exc:
            logger.debug(f"doge chaoli daily forward identity fallback: {type(exc).__name__}: {exc}")
        return "0", "豆子"

    async def _daily_report_chain(self, umo: str, report: DailyReportBundle) -> MessageChain:
        """One QQ merged-forward: archive note, actual PDF attachment, page previews.

        NapCat turns File segments within node content into forwarded file
        elements. No upload_group_file is ever called (no group-file quota).
        """
        uin, name = await self._daily_forward_identity(umo)
        nodes = [
            Node(
                uin=uin,
                name=name,
                content=[Plain(
                    f"{report.caption}\n"
                    f"正文与引用完整保存在 PDF 中，共 {len(report.pages)} 页；"
                    "以下依次附 PDF 原件和逐页图片，全部位于本条聊天记录内。"
                )],
            ),
            Node(
                uin=uin,
                name=name,
                content=[
                    Plain("超理日报 PDF 原件 · 点击文件下载（不会存入群文件）"),
                    File(
                        name=f"Chaoli-Daily-{report.date}.pdf",
                        file=str(report.pdf.resolve()),
                    ),
                ],
            ),
        ]
        for index, path in enumerate(report.pages, 1):
            nodes.append(Node(
                uin=uin,
                name=name,
                content=[
                    Plain(f"第 {index}/{len(report.pages)} 页"),
                    Image.fromFileSystem(str(path)),
                ],
            ))
        return MessageChain([Nodes(nodes)])

    async def _send_daily_report(self, umo: str, report: DailyReportBundle) -> bool:
        """One merged-forward send, never one file upload plus another message.

        A success marks the whole edition delivered; any exception leaves the
        scheduled watermark unchanged, with no automatic group-file fallback.
        """
        try:
            with report.pdf.open("rb") as handle:
                if handle.read(4) != b"%PDF":
                    raise ValueError("missing valid scholarly PDF artifact")
            chain=await self._daily_report_chain(umo, report)
            return bool(await self.context.send_message(umo, chain))
        except Exception as exc:
            logger.warning(
                f"doge chaoli single merged-forward failed umo={umo}: "
                f"{type(exc).__name__}: {str(exc)[:180]}"
            )
            return False

    async def _daily_cards_for_send(self, today: str) -> tuple[list, str]:
        # Primary path: exactly the forum-owner recommended JSON URL through the
        # dedicated Chaoli proxy. This is attempted once and shared by every
        # group whose digest is due in this polling cycle.
        try:
            cards = await ChaoliService.daily_json_cards(self.PUSH_LIMIT)
            if cards:
                self.daily_pool.merge(today, cards)
                return cards, "坛主推荐 #今日活跃 JSON（Chaoli 专用代理）"
        except Exception as exc:
            logger.info(f"doge chaoli daily JSON unavailable; using daily pool: {type(exc).__name__}: {exc}")
        cards = self.daily_pool.cards(today)
        if not cards:
            # Repair only an empty pool (typically after downtime); normal JSON
            # failures consume the pool without generating another forum poll.
            try:
                cards = await ChaoliService.daily_native_cards(self.PUSH_LIMIT)
                self.daily_pool.merge(today, cards)
                return cards, "按日活跃池（原生 #今日活跃 一次校准）"
            except Exception:
                pass
        return cards, "实时 push 差分维护的按日活跃池"

    async def _poll_daily_once(self) -> None:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        today = now.date().isoformat()
        hhmm = now.strftime("%H:%M")
        async with self._push_lock:
            subscriptions = self.push_store.subscriptions()
        due: dict[str,list[str]] = {}
        for umo, sub in subscriptions.items():
            if not isinstance(sub,dict) or not await is_plugin_enabled(str(umo),"doge_chaoli"):
                continue
            daily=sub.get("daily")
            if not isinstance(daily,dict) or not daily.get("enabled"):
                continue
            target=str(daily.get("time") or DAILY_DEFAULT_TIME)
            try:
                _,end=daily_issue_window(today,target)
            except ValueError:
                logger.warning(f"doge chaoli invalid daily target={target!r}; skipping")
                continue
            if now>=end and str(daily.get("last_sent") or "")!=today:
                due.setdefault(target,[]).append(str(umo))
        for target,groups in due.items():
            # Different subscriber times imply genuinely different source
            # windows, signatures, PDFs and cache entries.
            try:
                report=await self._daily_report_for_send(
                    today,umo=groups[0],issue_time=target
                )
            except Exception as exc:
                logger.warning(
                    f"doge chaoli scheduled issue generation failed "
                    f"date={today} cutoff={target}: {type(exc).__name__}: {str(exc)[:155]}"
                )
                continue
            for umo in groups:
                try:
                    delivered=await self._send_daily_report(umo,report)
                except Exception as exc:
                    delivered=False
                    logger.warning(
                        f"doge chaoli scheduled send failed umo={umo}: "
                        f"{type(exc).__name__}: {str(exc)[:150]}"
                    )
                if delivered:
                    async with self._push_lock:
                        self.push_store.mark_daily_sent(umo,today)

    async def _push_loop(self) -> None:
        try:
            await self._ensure_daily_pool()
            while True:
                await asyncio.sleep(self.PUSH_INTERVAL)
                try:
                    await self._ensure_daily_pool()
                    await self._poll_push_once()
                    await self._poll_daily_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(f"doge chaoli push/daily poll failed: {type(exc).__name__}: {exc}")
        except asyncio.CancelledError:
            raise

    async def _poll_push_once(self) -> None:
        async with self._push_lock:
            subscriptions = self.push_store.subscriptions()
        if not subscriptions:
            return

        active: dict[str, dict] = {}
        needed: set[str] = set()
        for umo, sub in subscriptions.items():
            if not isinstance(sub, dict) or not await is_plugin_enabled(str(umo), "doge_chaoli"):
                continue
            channels = sub.get("channels", {})
            if not isinstance(channels, dict) or not channels:
                continue
            active[str(umo)] = channels
            needed.update(str(x) for x in channels)
        if not needed:
            return

        fetched: dict[str, list] = {}
        for slug in sorted(needed):
            try:
                fetched[slug] = await ChaoliService.latest_cards(slug, self.PUSH_LIMIT)
            except Exception as exc:
                logger.warning(f"doge chaoli push fetch failed channel={slug}: {type(exc).__name__}: {exc}")

        pool_cards: dict[int, object] = {}
        for umo, channels in active.items():
            all_events = []
            next_states: dict[str, dict] = {}
            for slug, state in channels.items():
                cards = fetched.get(str(slug))
                if cards is None:
                    continue
                events, next_state = classify_cards(state if isinstance(state, dict) else {}, cards)
                all_events.extend(events)
                for push_event in events:
                    pool_cards[push_event.card.thread_id] = push_event.card
                next_states[str(slug)] = next_state
            if not next_states:
                continue

            delivered = True
            if all_events:
                message = format_push_message(all_events)
                try:
                    delivered = bool(await self.context.send_message(umo, MessageChain([Plain(message)])))
                except Exception as exc:
                    delivered = False
                    logger.warning(f"doge chaoli push send failed umo={umo}: {type(exc).__name__}: {exc}")
            if not delivered:
                # Do not advance watermarks for a message that never reached QQ.
                continue

            async with self._push_lock:
                for slug, next_state in next_states.items():
                    self.push_store.update_channel(umo, slug, next_state, save=False)
                self.push_store.save()

        if pool_cards and getattr(self, "daily_pool", None) is not None:
            self.daily_pool.merge(shanghai_date(), list(pool_cards.values()))

    @filter.command("chaoli")
    async def command(self, event: AstrMessageEvent):
        try:
            raw = command_payload(event.message_str, "chaoli").strip()
            if not raw or raw.lower() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return
            p = split_head(raw, 1)
            action = p[0].lower()
            rest = p[1].strip() if len(p) > 1 else ""
            if action in {"search", "find"}:
                if not rest:
                    raise ValueError("缺少搜索词")
                tokens = rest.split()
                query_parts: list[str] = []
                board = "all"
                limit = 10
                i = 0
                while i < len(tokens):
                    token = tokens[i]
                    if token in {"--board", "-b"}:
                        if i + 1 >= len(tokens):
                            raise ValueError("--board 后需要板块名")
                        board = tokens[i + 1]
                        i += 2
                        continue
                    if token.startswith("--board="):
                        board = token.split("=", 1)[1]
                        i += 1
                        continue
                    if token in {"--limit", "-n"}:
                        if i + 1 >= len(tokens) or not tokens[i + 1].isdigit():
                            raise ValueError("--limit 后需要整数")
                        limit = int(tokens[i + 1])
                        i += 2
                        continue
                    if token.startswith("--limit="):
                        value = token.split("=", 1)[1]
                        if not value.isdigit():
                            raise ValueError("--limit 需要整数")
                        limit = int(value)
                        i += 1
                        continue
                    query_parts.append(token)
                    i += 1
                query = " ".join(query_parts).strip()
                if not query:
                    raise ValueError("缺少搜索词")
                out = await ChaoliService.search(query, board, limit)
            elif action in {"latest", "new"}:
                xs = rest.split()
                channel = xs[0] if xs and not xs[0].isdigit() else "all"
                limit = int(xs[-1]) if xs and xs[-1].isdigit() else 10
                out = await ChaoliService.latest(channel, limit)
            elif action in {"channel", "board"}:
                xs = rest.split()
                if not xs:
                    raise ValueError("缺少板块")
                out = await ChaoliService.latest(xs[0], int(xs[1]) if len(xs) > 1 and xs[1].isdigit() else 10)
            elif action in {"read", "thread"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.read(rest)
            elif action == "floor":
                xs = rest.split()
                if len(xs) < 2 or not xs[1].isdigit():
                    raise ValueError("用法：/chaoli floor <帖子号> <楼层>")
                out = await ChaoliService.read(xs[0], int(xs[1]), 0)
            elif action in {"context", "ctx"}:
                xs = rest.split()
                if len(xs) < 2 or not xs[1].isdigit():
                    raise ValueError("用法：/chaoli context <帖子号> <楼层> [1-3]")
                out = await ChaoliService.read(xs[0], int(xs[1]), int(xs[2]) if len(xs) > 2 and xs[2].isdigit() else 1)
            elif action in {"outline", "toc"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.outline(rest)
            elif action in {"user", "member"}:
                if not rest:
                    raise ValueError("缺少用户名、用户 ID 或链接")
                out = await ChaoliService.user(rest)
            elif action in {"links", "refs", "related"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.links(rest)
            elif action in {"preview", "peek"}:
                if not rest:
                    raise ValueError("缺少帖子号或链接")
                out = await ChaoliService.preview(rest)
            elif action == "push":
                out = await self._push_command(event, rest)
            elif action == "daily":
                # /chaoli daily is already a fully handled native command.
                # Stop the same message entering the Agent stage and invoking
                # doge_chaoli(daily) a second time 15-20 seconds later.
                stop=getattr(event,"stop_event",None)
                if callable(stop):
                    stop()
                out = await self._daily_command(event, rest)
            elif action == "status":
                out = await ChaoliService.status()
            else:
                raise ValueError("未知 chaoli 子命令")
            if out is None:
                return
            yield long_result(event, "Chaoli", out, fold_threshold=1800)
        except (ChaoliError, ValueError) as exc:
            yield text_result(event, format_cli_error("chaoli", exc), markdown=False)
        except Exception as exc:
            logger.warning(f"doge chaoli failed: {exc}")
            yield text_result(event, format_cli_error("chaoli", exc), markdown=False)

    @filter.regex(r"https?://(?:www\.)?chaoli\.club/index\.php/(?:\d+(?:/p?\d+)?(?:#p\d+)?|conversation/post/\d+)$")
    async def auto_preview(self, event: AstrMessageEvent):
        # Passive preview is only for ordinary messages. AstrBot's wake stage may
        # strip the leading slash from event.message_str, so use the untouched
        # transport text to keep explicit commands from triggering a second handler.
        text = original_message_text(event).strip()
        if text.lstrip().startswith("/"):
            return
        m = re.search(r"https?://(?:www\.)?chaoli\.club/index\.php/(?:\d+(?:/p?\d+)?(?:#p\d+)?|conversation/post/\d+)", text, re.I)
        if not m:
            return
        try:
            yield text_result(event, await ChaoliService.preview(m.group(0)), markdown=False)
        except Exception as exc:
            logger.debug(f"chaoli link preview skipped: {exc}")
