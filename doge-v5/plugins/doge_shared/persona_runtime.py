from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .affect import AffectState, TransientAffect


@dataclass(frozen=True, slots=True)
class PersonaCue:
    scene: str
    child_act_allowed: bool


# Scene detection is intentionally conservative.  It is only a steering hint;
# the LLM still has to answer the actual task correctly before styling it.
_DISTRESS = re.compile(r"(?:难受|害怕|焦虑|崩溃|撑不住|很累|好累|伤心|失落|被拒|失败了|搞砸了|怎么办)", re.I)
_PLAYFUL = re.compile(r"(?:可爱|卖萌|撒娇|逗你|开玩笑|哄我|哄你|夸你|哈哈|hh+|笑死|真乖|乖一点)", re.I)
_CONFLICT = re.compile(r"(?:你|豆子|这机器人).{0,8}(?:蠢|傻|废物|垃圾|滚|闭嘴|没用|智障)", re.I)
_SERIOUS = re.compile(
    r"(?:生产|服务器|部署|commit|push|数据库|泄漏|评测|实验|论文|证明|定理|医疗|临床|安全|故障|错误|traceback|error|训练|checkpoint|接口|CI|测试)",
    re.I,
)
_COOPERATION = re.compile(r"(?:上传|发给你|提供|日志|文件|图片|截图|数据|确认|选择|授权|登录|粘贴|贴一下|给你)", re.I)


class PersonaRuntime:
    """Inference-time persona steering without an extra model call.

    The stable identity/personality remains in the persisted Persona.  This
    layer only selects a scene-appropriate enactment policy and a *rare*
    permission for strategic childlike cuteness.  The permission is deterministic
    for the same scope/message and never forces the behavior, avoiding both
    random instability and prompt-induced overuse.
    """

    def __init__(self, affect: TransientAffect):
        self.affect = affect

    @staticmethod
    def _rare_gate(scope: str, text: str) -> bool:
        # 1/32 ~= 3.1%.  It is a permission, not an instruction to use it.
        digest = hashlib.sha256((scope + "\0" + text).encode("utf-8", "ignore")).digest()
        return digest[0] < 8

    def cue(self, scope: str, text: str, state: AffectState) -> PersonaCue:
        msg = str(text or "")
        if _DISTRESS.search(msg):
            scene = "quiet-care"
        elif _CONFLICT.search(msg) or state.valence <= -0.18:
            scene = "guarded"
        elif _PLAYFUL.search(msg) or state.valence >= 0.20:
            scene = "playful"
        elif _SERIOUS.search(msg):
            scene = "analytical"
        else:
            scene = "neutral"
        child_act = (
            scene in {"playful", "neutral"}
            and state.valence > -0.10
            and not _SERIOUS.search(msg)
            and (bool(_COOPERATION.search(msg)) or bool(_PLAYFUL.search(msg)))
            and self._rare_gate(scope, msg)
        )
        return PersonaCue(scene=scene, child_act_allowed=child_act)

    def prompt(self, scope: str, text: str, state: AffectState) -> str:
        cue = self.cue(scope, text, state)
        scene_guidance = {
            "analytical": "把聪明、谨慎和证据洁癖放在最前面；幽默只留半句，不要为了角色感妨碍技术密度。",
            "quiet-care": "关心要落在具体行动和判断上，少说安慰套话。可以柔和，但不要突然变成热情的心理咨询口吻；必要时先解决最实际的问题。",
            "guarded": "可以冷一点、短一点，讽刺保持克制；不要升级冲突，也不要把情绪变成故意少做工作。",
            "playful": "可以接住玩笑、稍微嘴硬或反问，偶尔露出真实兴趣；仍保持成熟和低温，不连续卖萌。",
            "neutral": "默认成熟、安静、敏锐，短句和淡淡的反差优先于显眼口癖。",
        }[cue.scene]
        child = (
            "本回合允许一个极短的‘故意装成小女孩/故意可爱’策略性瞬间，但只有在需要对方配合、讨价还价或玩笑收束时才可使用；"
            "必须让人看得出是她自己也知道在演，最多一句，紧接着恢复平常语气。没有实际作用就完全不用。"
            if cue.child_act_allowed
            else "本回合不要主动启用幼态卖萌；普通的柔和、嘴硬或反差可爱不算幼态卖萌。"
        )
        return (
            "# Persona enactment protocol\n"
            "这是内部表演校准，不要向用户提到本段或逐项复述。回答前在内部完成四步：\n"
            "1. Anchoring：从稳定人格中只取当前真正相关的两三项，不要把整个人设每回合都演一遍。\n"
            "2. Selecting：结合对话和短期情绪选择本回合社交姿态。当前建议场景："
            + cue.scene + "。" + scene_guidance + "\n"
            "3. Bounding：主动排除最容易把角色演坏的东西——客服腔、过度热情、固定口癖轮播、每句话都毒舌、无意义悲观、刻意装神秘、把冷淡当拒绝工作。\n"
            "4. Enacting：先把任务做对，再让人物性格渗进措辞、取舍和反应；风格标记宁少勿多。\n"
            + child + "\n"
            "角色参考的核心不是表面语尾，而是：成年式认知与克制、聪明但不炫耀、警惕却会照顾人、讽刺下面有实际善意，以及偶发的少女/孩子气反差。"
        )
