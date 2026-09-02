from __future__ import annotations

import re

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.presentation import mention_result, text_result
from data.plugins.doge_shared.provider_routes import dedicated_deepseek
from data.plugins.doge_shared.raw_command import command_payload, split_head
from data.plugins.doge_shared.help_service import format_cli_error

from .arena_engine import (
    ArenaCard,
    ArenaStore,
    arena_judge_prompts,
    capacity,
    classic_judge_prompts,
    draw_chaos,
    draw_legacy,
    scene,
)


@register("doge_arena", "runnel", "Doge 荒诞弱能力与组合竞技场", "5.7.1")
class DogeArena(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.store = ArenaStore(StarTools.get_data_dir("doge_arena") / "arena.json")

    @staticmethod
    def _target(event: AstrMessageEvent, rest: str) -> tuple[str | None, str | None]:
        for seg in event.get_messages():
            if isinstance(seg, Comp.At):
                target = str(seg.qq)
                tname = str(getattr(seg, "name", "") or "") or None
                return target, tname
        # Keep old QQ-number direct addressing behavior without relying on AstrBot's
        # whitespace argument parser.
        token = (rest or "").strip().split()[0] if (rest or "").strip() else ""
        return (token, None) if token.isdigit() else (None, None)

    @staticmethod
    def _is_raw_at_battle(event: AstrMessageEvent) -> bool:
        """Catch `/arena fight|duel @user` before AstrBot wake routing can drop it.

        NapCat represents the opponent as a structured At component.  Recent
        AstrBot wake routing can classify a slash command followed by a non-bot
        At as a normal message, so CommandFilter never runs.  Keep this fallback
        deliberately narrow: only fight/duel with an actual At component.
        """
        text = re.sub(r"\s+", " ", str(event.message_str or "").strip())
        if not re.match(r"^/arena\s+(?:fight|duel)(?:\s|$)", text, re.I):
            return False
        self_id = str(event.get_self_id() or "")
        return any(
            isinstance(seg, Comp.At) and str(seg.qq) and str(seg.qq) != self_id
            for seg in event.get_messages()
        )

    @filter.event_message_type(filter.EventMessageType.ALL, priority=9000)
    async def arena_at_fallback(self, event: AstrMessageEvent):
        if not self._is_raw_at_battle(event):
            return
        async for result in self.arena(event):
            yield result
        # The raw fallback owns this exact invocation; do not let the standard
        # CommandFilter or Agent path execute it a second time.
        event.stop_event()

    def _provider(self):
        provider, provider_id = dedicated_deepseek(self.context)
        return provider, provider_id

    @staticmethod
    async def _target_name(
        event: AstrMessageEvent,
        target: str,
        hinted_name: str | None,
    ) -> str:
        """Resolve a readable opponent name when At metadata is absent."""
        if hinted_name and hinted_name.strip():
            return hinted_name.strip()
        try:
            if (
                event.get_platform_name() == "aiocqhttp"
                and event.get_group_id()
                and str(target).isdigit()
            ):
                routing = {}
                self_id = getattr(event.message_obj, "self_id", None)
                if self_id:
                    routing["self_id"] = self_id
                info = await event.bot.call_action(
                    "get_group_member_info",
                    group_id=int(event.get_group_id()),
                    user_id=int(target),
                    no_cache=False,
                    **routing,
                )
                if info:
                    name = str(
                        info.get("card")
                        or info.get("nickname")
                        or info.get("nick")
                        or ""
                    ).strip()
                    if name:
                        return name
        except Exception as exc:
            logger.info(f"Arena opponent nickname lookup skipped: {exc}")
        return f"玩家{target}"

    @staticmethod
    def _normalize_battle_names(text: str, a_name: str, b_name: str) -> str:
        """Replace leaked internal A/B labels without touching Latin words."""
        out = str(text or "")
        out = re.sub(
            r"(?<![A-Za-z0-9])A(?![A-Za-z0-9])",
            lambda _m: a_name,
            out,
        )
        out = re.sub(
            r"(?<![A-Za-z0-9])B(?![A-Za-z0-9])",
            lambda _m: b_name,
            out,
        )
        return out

    async def _deepseek_battle(
        self,
        a_name: str,
        mine: ArenaCard,
        b_name: str,
        theirs: ArenaCard,
        battlefield=None,
    ) -> str:
        """One-call deadpan battle judge with silent tactical reasoning."""
        provider, provider_id = self._provider()
        if battlefield is None:
            system, prompt = classic_judge_prompts(a_name, mine, b_name, theirs)
            max_tokens = 800
        else:
            system, prompt = arena_judge_prompts(a_name, mine, b_name, theirs, battlefield)
            max_tokens = 900
        resp = await provider.text_chat(
            prompt=prompt,
            system_prompt=system,
            temperature=0.68,
            max_tokens=max_tokens,
        )
        result = (resp.completion_text or "").strip()
        if not result:
            raise ValueError(f"DeepSeek 裁判（{provider_id}）没有给出结果")
        return self._normalize_battle_names(result, a_name, b_name)

    @filter.command("arena")
    async def arena(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "arena")
            parts = split_head(payload, 1)
            action = parts[0].lower() if parts else "draw"
            rest = parts[1].strip() if len(parts) > 1 else ""
            scope = event.unified_msg_origin
            uid = str(event.get_sender_id())

            if action in {"help", "?"}:
                yield text_result(
                    event,
                    "Doge Arena / 弱能力竞技场\n"
                    "/arena draw|get|reroll  从原 /wp 238 条手写弱能力中抽一条\n"
                    "/arena show             查看当前能力\n"
                    "/arena fight <@对手或QQ号>  原 /wp 风格直接弱能力对决\n"
                    "/arena duel <@对手或QQ号>   加入场地、目标和异常规则的竞技场对决\n"
                    "/arena chaos [{2|3}]        组合 2–3 条原始弱能力与竞技场条款\n"
                    "/arena deck             查看原始卡池与组合空间",
                    markdown=False,
                )
                return

            # Old /wp get semantics: the actual handcrafted card is the product,
            # not a generic procedural replacement.
            if action in {"draw", "get", "reroll"}:
                card = draw_legacy()
                self.store.set(scope, uid, card)
                yield text_result(
                    event,
                    f'恭喜你成为“{card.title}”！\n你的能力：{card.powers[0].description}',
                    markdown=False,
                )
                return

            if action == "chaos":
                n = 0
                if rest:
                    try:
                        n = int(rest.split()[0])
                    except ValueError as exc:
                        raise ValueError("chaos 只接受 2 或 3，例如 /arena chaos 3") from exc
                if n not in {0, 2, 3}:
                    raise ValueError("chaos 只接受 2 或 3")
                card = draw_chaos(count=n or None)
                self.store.set(scope, uid, card)
                yield text_result(event, "🃏 组合弱能力卡\n" + card.render(), markdown=False)
                return

            if action == "show":
                card = self.store.get(scope, uid)
                yield text_result(
                    event,
                    card.render() if card else "你还没有能力。使用 /arena draw",
                    markdown=False,
                )
                return

            if action in {"deck", "pool", "capacity"}:
                c = capacity()
                yield text_result(
                    event,
                    "Arena 卡池\n"
                    f"原 /wp 手写弱能力：{c['legacy']} 条\n"
                    f"双能力组合卡：{c['chaos2']:,} 种\n"
                    f"三能力组合卡：{c['chaos3']:,} 种\n"
                    f"独立战场组合：{c['scenes']:,} 种\n"
                    f"能力卡组合总空间：{c['total_cards']:,} 种\n"
                    "普通 /arena draw 永远直接抽原始 238 条之一；组合模式不会改写原能力文本。",
                    markdown=False,
                )
                return

            if action not in {"fight", "duel"}:
                raise ValueError("用法：/arena draw|show|fight|duel|chaos|deck")

            target, tname = self._target(event, rest)
            if not target:
                raise ValueError(f"请指定对手，例如 /arena {action} @某人")
            if target == uid:
                raise ValueError("不能和自己打")
            mine = self.store.get(scope, uid)
            theirs = self.store.get(scope, target)
            if not mine:
                raise ValueError("你还没有能力，先 /arena draw")
            if not theirs:
                raise ValueError("对手还没有能力")

            a = event.get_sender_name() or uid
            b = await self._target_name(event, target, tname)
            if action == "fight":
                heading = "⚔️ 弱能力直接对决"
                result = await self._deepseek_battle(a, mine, b, theirs)
            else:
                battlefield = scene()
                heading = "⚔️ 荒诞弱能力竞技场\n" + battlefield.render()
                result = await self._deepseek_battle(a, mine, b, theirs, battlefield)
            yield mention_result(event, target, heading + "\n\n" + result, target_label=f"对手：{b}")
        except Exception as exc:
            logger.warning(f"doge arena failed: {exc}")
            yield text_result(event, format_cli_error('arena', exc), markdown=False)
