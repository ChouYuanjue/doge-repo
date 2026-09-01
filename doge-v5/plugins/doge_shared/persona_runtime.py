from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass

from .affect import AffectState, TransientAffect


@dataclass(slots=True)
class RelationshipState:
    turns: int = 0
    last_seen: float = 0.0


@dataclass(frozen=True, slots=True)
class PersonaCue:
    warmth: float
    playfulness: float
    sharpness: float
    restraint: float
    persona_strength: float
    familiarity: float
    child_act_allowed: bool
    closest: bool
    tags: tuple[str, ...]


# These are steering signals, not a hard state machine. A message can activate
# several dimensions at once; the resulting style stays continuous.
_DISTRESS = re.compile(r"(?:难受|害怕|焦虑|崩溃|撑不住|很累|好累|伤心|失落|被拒|失败了|搞砸了|怎么办|手术|住院)", re.I)
_PLAYFUL = re.compile(r"(?:可爱|卖萌|撒娇|逗你|开玩笑|哄我|夸你|宝宝|哈哈|hh+|笑死|真乖|乖一点|复活|回来啦|陪我玩|玩会儿|玩一会|一起玩|波浪线|~~~~)", re.I)
_CONFLICT = re.compile(r"(?:你|豆子|这机器人).{0,8}(?:蠢|傻|废物|垃圾|滚|闭嘴|没用|智障|笨蛋)", re.I)
_SERIOUS = re.compile(r"(?:生产|服务器|部署|commit|push|数据库|泄漏|评测|实验|论文|证明|定理|医疗|临床|安全|故障|错误|traceback|error|训练|checkpoint|接口|CI|测试|代码|日志)", re.I)
_COOPERATION = re.compile(r"(?:上传|发给你|提供|文件|图片|截图|数据|确认|选择|授权|登录|粘贴|贴一下|给你)", re.I)
_PRAISE = re.compile(r"(?:可爱|厉害|聪明|真棒|靠谱|喜欢你|夸你|做得好)", re.I)
_CASUAL = re.compile(r"(?:吃什么|吃饭|晚饭|闲聊|随便聊|无聊|在吗|干嘛|睡觉|早安|晚安|今天|最近|回来|复活)", re.I)


# Short original examples distilled from the character style. They are not
# quotes from the source material. Runtime retrieves only two relevant pairs,
# so the model imitates behavior/rhythm instead of executing a long rulebook.
_EXAMPLES: tuple[tuple[frozenset[str], str, str], ...] = (
    (frozenset({"casual", "warm"}), "今天好无聊。", "那就别硬装忙了。陪你混一会儿也不是不行……你想聊，还是想玩点什么？"),
    (frozenset({"playful", "warm"}), "豆子宝宝，你回来啦。", "谁是宝宝……算了。你都这么叫了，我再纠正好像更奇怪。说吧，今天想玩什么？"),
    (frozenset({"praise", "playful"}), "夸你一句，你今天挺可爱的。", "是吗。你的审美总算有一次没出问题……这句我就收下了。"),
    (frozenset({"playful"}), "语气可爱一点。", "要求还挺具体。那……只允许一点点。说吧，要我做什么？"),
    (frozenset({"casual", "warm"}), "我有点困，但还不想睡。", "那就再待一会儿。不过困到开始说胡话的时候我会赶你去睡，先说好。"),
    (frozenset({"playful", "warm"}), "这局我赢了。", "只赢一局就这么得意……再来。刚才那局不算我认真。"),
    (frozenset({"distress", "warm"}), "我明天要汇报，感觉这次搞砸了。", "先把最容易被问的三处补上。至于紧张……等能补的都补完，再紧张也来得及。"),
    (frozenset({"serious", "skeptical"}), "这个结果一下高了十几个点，可以直接报吗？", "先别急着高兴。切分、缓存、测试集重叠和评测口径过一遍；都干净，再把这个好消息当真的。"),
    (frozenset({"serious", "teasing"}), "日志我懒得贴，你大概能猜吧。", "当然能猜。然后我们就可以一起浪费半小时验证我猜错了。贴出来。"),
    (frozenset({"casual", "playful"}), "今天别聊技术了。", "终于。再聊服务器，我都要怀疑你只会和日志培养感情了。想聊什么？"),
    (frozenset({"playful", "odd"}), "~~~~~~~~~~~~", "……这是脑电波，还是你单纯想看我会不会跟着发一串？"),
    (frozenset({"conflict", "teasing"}), "豆子是笨蛋。", "嗯，证据呢？没有的话，这条指控我暂不受理。"),
    (frozenset({"cooperation", "teasing"}), "截图我懒得发，你自己猜。", "不给也行，我可以猜。然后我们一起欣赏一个本来三十秒能解决的问题拖成半小时。发来。"),
    (frozenset({"child", "cooperation", "playful"}), "我就是不想发截图。", "那、那就拜托你发一下嘛？……好了，满意了？截图给我，我还得看真正的问题。"),
)


class PersonaRuntime:
    """Lightweight inference-time persona steering.

    Stable personality lives in the persisted Persona. Runtime stores only an
    in-memory interaction count per sender/session and combines it with transient
    affect into continuous style dimensions. It injects two relevant examples,
    not a role-play checklist. No user message content is retained here.
    """

    def __init__(
        self,
        affect: TransientAffect,
        *,
        relationship_ttl_s: float = 43200.0,
        closest_sender_ids: set[str] | None = None,
    ):
        self.affect = affect
        self.relationship_ttl_s = float(relationship_ttl_s)
        self.closest_sender_ids = {str(x).strip() for x in (closest_sender_ids or set()) if str(x).strip()}
        self._relationships: dict[str, RelationshipState] = {}

    @staticmethod
    def _clip(x: float) -> float:
        return max(0.0, min(1.0, x))

    @staticmethod
    def _rare_gate(scope: str, text: str) -> bool:
        # Overt strategic childlike acting remains genuinely rare. Ordinary
        # low-intensity cuteness is handled by warmth/playfulness instead.
        digest = hashlib.sha256((scope + "\0" + text).encode("utf-8", "ignore")).digest()
        return digest[0] < 6  # ~2.3%

    def _relationship(self, scope: str, *, advance: bool) -> RelationshipState:
        now = time.time()
        old = self._relationships.get(scope)
        if old is None or (old.last_seen and now - old.last_seen > self.relationship_ttl_s):
            old = RelationshipState()
            self._relationships[scope] = old
        if advance:
            old.turns = min(200, old.turns + 1)
            old.last_seen = now
        return old

    def _is_closest(self, scope: str) -> bool:
        if not self.closest_sender_ids or "|sender:" not in scope:
            return False
        sender = scope.rsplit("|sender:", 1)[-1].strip()
        return sender in self.closest_sender_ids

    @staticmethod
    def _familiarity(turns: int) -> float:
        # Fast initial thaw, then diminishing returns. 0, 5, 15, 40 turns ->
        # roughly 0, .28, .56, .82.
        return 1.0 - math.exp(-max(0, turns) / 24.0)

    @staticmethod
    def _tags(text: str, state: AffectState) -> set[str]:
        msg = str(text or "")
        tags: set[str] = set()
        if _SERIOUS.search(msg): tags.add("serious")
        if _DISTRESS.search(msg): tags.update({"distress", "warm"})
        if _PLAYFUL.search(msg): tags.add("playful")
        if _CONFLICT.search(msg): tags.add("conflict")
        if _COOPERATION.search(msg): tags.add("cooperation")
        if _PRAISE.search(msg): tags.add("praise")
        if _CASUAL.search(msg): tags.add("casual")
        if state.valence >= 0.14: tags.add("warm")
        if state.valence <= -0.16: tags.add("conflict")
        if not tags: tags.add("casual")
        return tags

    def cue(self, scope: str, text: str, state: AffectState, *, advance: bool = False) -> PersonaCue:
        rel = self._relationship(scope, advance=advance)
        closest = self._is_closest(scope)
        familiarity = 1.0 if closest else self._familiarity(rel.turns)
        tags = self._tags(text, state)
        serious = "serious" in tags
        distress = "distress" in tags
        playful = "playful" in tags or "praise" in tags
        conflict = "conflict" in tags

        warmth = .60 + .18 * familiarity + .16 * max(0.0, state.valence) - .08 * max(0.0, -state.valence)
        playfulness = .38 + .18 * familiarity + (.22 if playful else 0.0) + .08 * max(0.0, state.valence) - (.12 if serious else 0.0)
        sharpness = .28 + (.18 if conflict else 0.0) + (.04 if serious else 0.0) - (.18 if distress else 0.0)
        restraint = .42 + (.16 if serious else 0.0) + (.08 if conflict else 0.0) - .12 * familiarity - (.07 if playful else 0.0)

        if closest:
            warmth = max(warmth, .82 if serious else .86)
            if not serious:
                playfulness = max(playfulness, .62)
                restraint = min(restraint, .36)

        # Keep one recognizable person across contexts. Seriousness lowers joke
        # frequency and raises information density, but never swaps in a cold
        # expert persona.
        persona_strength = .68 + .08 * familiarity
        if playful:
            persona_strength += .07
        if distress:
            persona_strength -= .05
        if serious:
            persona_strength -= .16
        if closest and not serious:
            persona_strength = max(persona_strength, .78)

        child_act = (
            not serious
            and not distress
            and state.valence > -0.10
            and ("cooperation" in tags or playful)
            and self._rare_gate(scope, str(text or ""))
        )
        return PersonaCue(
            warmth=self._clip(warmth),
            playfulness=self._clip(playfulness),
            sharpness=self._clip(sharpness),
            restraint=self._clip(restraint),
            persona_strength=self._clip(persona_strength),
            familiarity=self._clip(familiarity),
            child_act_allowed=child_act,
            closest=closest,
            tags=tuple(sorted(tags)),
        )

    @staticmethod
    def _retrieve_examples(tags: set[str], child_allowed: bool, limit: int = 2) -> list[tuple[str, str]]:
        scored: list[tuple[int, int, str, str]] = []
        for idx, (etags, user, assistant) in enumerate(_EXAMPLES):
            if "child" in etags and not child_allowed:
                continue
            overlap = len(tags & set(etags))
            score = overlap * 4
            if "serious" in tags and "serious" in etags: score += 3
            if "distress" in tags and "distress" in etags: score += 4
            if "playful" in tags and "playful" in etags: score += 2
            if score:
                scored.append((score, -idx, user, assistant))
        scored.sort(reverse=True)
        if not scored:
            scored = [(1, 0, _EXAMPLES[0][1], _EXAMPLES[0][2])]
        return [(u, a) for _, _, u, a in scored[:limit]]

    def prompt(self, scope: str, text: str, state: AffectState) -> str:
        cue = self.cue(scope, text, state, advance=True)
        tags = set(cue.tags)
        examples = self._retrieve_examples(tags, cue.child_act_allowed)
        mood = self.affect.label(state)
        parts = [
            "# Conversation style cue",
            "只调整表达，不降低推理、事实密度、工具使用或任务完成度。不要把这段规则说给用户。",
            (
                f"当前表达强度={cue.persona_strength:.2f}，warmth={cue.warmth:.2f}，"
                f"playfulness={cue.playfulness:.2f}，sharpness={cue.sharpness:.2f}，"
                f"restraint={cue.restraint:.2f}；熟悉度={cue.familiarity:.2f}，短期情绪={mood}。"
            ),
        ]
        if cue.closest:
            parts.append("这是最亲近的关系档：不用维持礼貌距离。可以自然亲昵一点、主动接话、闹一点小别扭、表现好奇或小小胜负心；关心也不必总藏在嫌弃后面。")
        parts.append("始终是同一个人：认真时只是信息更密、玩笑更少，不要突然切成冷冰冰的专家；轻松时可以更自然地好奇、嘴硬、得意、亲昵一点或接梗。")
        if "serious" in tags:
            parts.append("当前内容需要认真处理：关键结论、依据和步骤给完整，同时保留正常温度，不用刻意装严肃。")
        elif cue.playfulness >= .58:
            parts.append("当前可以明显鲜活一点；小反差和一点少女感可以自然出现，但不要套固定萌系模板。")
        if cue.child_act_allowed:
            parts.append("本回合若确实有社交作用，可以极短地故意装可爱一次；让人看得出是在演，马上恢复正常。")
        parts.append("参考下面两段的反应方式和节奏，不要逐字复述，也不要强行套口癖：")
        for user, assistant in examples:
            parts.append(f"用户：{user}\n豆子：{assistant}")
        return "\n".join(parts)
