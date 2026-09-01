from __future__ import annotations

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from data.plugins.doge_shared.presentation import mention_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head

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


@register("doge_arena", "runnel", "Doge 荒诞弱能力与组合竞技场", "5.6.0")
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

    async def _provider(self, scope: str):
        provider = await self.context.get_using_provider_async(umo=scope)
        if not provider:
            raise ValueError("竞技场解说需要聊天模型 provider")
        return provider

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
                    "/arena fight @某人      原 /wp 风格直接弱能力对决\n"
                    "/arena duel @某人       加入场地、目标和异常规则的竞技场对决\n"
                    "/arena chaos [2|3]      组合 2–3 条原始弱能力与竞技场条款\n"
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
            b = tname or f"玩家{target}"
            provider = await self._provider(scope)
            if action == "fight":
                system, prompt = classic_judge_prompts(a, mine, b, theirs)
                heading = "⚔️ 弱能力直接对决"
            else:
                battlefield = scene()
                system, prompt = arena_judge_prompts(a, mine, b, theirs, battlefield)
                heading = "⚔️ 荒诞弱能力竞技场\n" + battlefield.render()

            resp = await provider.text_chat(prompt=prompt, system_prompt=system)
            result = (resp.completion_text or "").strip()
            if not result:
                raise ValueError("裁判没有给出结果")
            yield mention_result(event, target, heading + "\n\n" + result, target_label=f"对手：{b}")
        except Exception as exc:
            logger.warning(f"doge arena failed: {exc}")
            yield text_result(event, f"arena 失败：{exc}", markdown=False)
