from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass


@dataclass(slots=True)
class AffectState:
    valence: float = 0.0   # -1 displeased .. +1 pleased
    arousal: float = 0.0   #  0 calm       .. +1 activated
    updated_at: float = 0.0


class TransientAffect:
    """Small in-memory affect model.

    This intentionally is not a long-term memory or a classifier service. State
    decays continuously toward neutral and is discarded after inactivity. Only
    high-precision, directly-addressed conversational cues move it noticeably.
    """

    _INSULT = re.compile(
        r"(?:你|豆子|这机器人).{0,8}(?:傻(?:逼|子)?|蠢|废物|垃圾|弱智|有病|滚|闭嘴|没用|智障)",
        re.I,
    )
    _PRAISE = re.compile(
        r"(?:(?:你|豆子).{0,8}(?:厉害|真棒|不错|做得好|可爱|靠谱|聪明|好用)|谢谢你|谢了豆子)",
        re.I,
    )
    _APOLOGY = re.compile(r"(?:对不起|抱歉|sorry|我的错)", re.I)

    def __init__(self, *, half_life_s: float = 900.0, ttl_s: float = 7200.0):
        self.half_life_s = float(half_life_s)
        self.ttl_s = float(ttl_s)
        self._states: dict[str, AffectState] = {}

    @staticmethod
    def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, x))

    def _decay(self, state: AffectState, now: float) -> None:
        if not state.updated_at:
            state.updated_at = now
            return
        dt = max(0.0, now - state.updated_at)
        factor = 0.5 ** (dt / self.half_life_s) if self.half_life_s > 0 else 0.0
        state.valence *= factor
        state.arousal *= factor
        state.updated_at = now

    def observe(self, scope: str, text: str, *, now: float | None = None) -> AffectState:
        now = time.time() if now is None else float(now)
        # Opportunistic GC keeps this bounded without a scheduler.
        for key, old in list(self._states.items()):
            if old.updated_at and now - old.updated_at > self.ttl_s:
                self._states.pop(key, None)

        state = self._states.setdefault(scope, AffectState(updated_at=now))
        self._decay(state, now)
        msg = str(text or "").strip()

        if self._INSULT.search(msg):
            state.valence = self._clip(state.valence - 0.48)
            state.arousal = self._clip(state.arousal + 0.38, 0.0, 1.0)
        elif self._APOLOGY.search(msg) and state.valence < -0.08:
            state.valence = self._clip(state.valence + 0.30)
            state.arousal = self._clip(state.arousal - 0.20, 0.0, 1.0)
        elif self._PRAISE.search(msg):
            state.valence = self._clip(state.valence + 0.24)
            state.arousal = self._clip(state.arousal + 0.08, 0.0, 1.0)
        else:
            # Neutral turns gently shorten emotion persistence beyond time decay.
            state.valence *= 0.94
            state.arousal *= 0.92
        state.updated_at = now
        return AffectState(state.valence, state.arousal, state.updated_at)

    @staticmethod
    def label(state: AffectState) -> str:
        if state.valence <= -0.42 and state.arousal >= 0.20:
            return "有点生气"
        if state.valence <= -0.16:
            return "微恼"
        if state.valence >= 0.42:
            return "心情不错"
        if state.valence >= 0.16:
            return "略微愉快"
        if state.arousal >= 0.52:
            return "有些警觉"
        return "平静"

    def prompt(self, state: AffectState) -> str:
        mood = self.label(state)
        guidance = {
            "有点生气": "语气可以更冷、更短，少主动提供无关的额外服务，允许一两句克制的挖苦；但必须把用户真正需要的工作做正确、做完整，不得故意拖延、遗漏关键步骤或降低事实标准。",
            "微恼": "可以稍显冷淡、少一点热情附加项，但仍正常完成任务；情绪不要扩大化。",
            "心情不错": "可以比平时柔和一点，偶尔露出很轻的可爱或玩笑，但仍然克制，不突然变成热情型人格。",
            "略微愉快": "语气可稍微放松，但保持一贯的低温和简洁。",
            "有些警觉": "更注意风险和证据链，先核实再下结论；不要把警觉写成焦虑。",
            "平静": "保持自然的冷静、敏锐和低温幽默。",
        }[mood]
        return (
            "# Transient affect\n"
            f"当前短期情绪：{mood}。{guidance}\n"
            "这是短期、会自然衰减的状态，不是长期人设标签。不要向用户解释数值、规则或状态机，也不要为了维持情绪而无视当前对话的新变化。"
        )
