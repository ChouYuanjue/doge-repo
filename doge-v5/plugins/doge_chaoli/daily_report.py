from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from data.plugins.doge_shared.chaoli import ChaoliError, ChaoliService, Floor, ThreadCard
from data.plugins.doge_shared.typeset import _render_tex_document
from .push import reply_count

SHANGHAI = ZoneInfo("Asia/Shanghai")
REPORT_SCHEMA = 3
REPORT_TEMPLATE_REV = "tex-journal-v6"


@dataclass(frozen=True, slots=True)
class DailyTopicEvidence:
    card: ThreadCard
    first_floor: Floor | None
    activity_floors: tuple[Floor, ...]
    latest_floors: tuple[Floor, ...]
    error: str = ""


@dataclass(frozen=True, slots=True)
class DailyTopicSummary:
    thread_id: int
    text: str
    evidence_floors: tuple[int, ...]
    error: str = ""


@dataclass(frozen=True, slots=True)
class DailyEditorialBlock:
    level: str
    thread_ids: tuple[int, ...]
    headline: str
    deck: str


@dataclass(frozen=True, slots=True)
class DailyEditorialIssue:
    headline: str
    standfirst: str
    blocks: tuple[DailyEditorialBlock, ...]
    error: str = ""


@dataclass(frozen=True, slots=True)
class DailyReportBundle:
    date: str
    source: str
    cards: tuple[ThreadCard, ...]
    evidence: tuple[DailyTopicEvidence, ...]
    summaries: tuple[DailyTopicSummary, ...]
    editorial: DailyEditorialIssue
    markdown: str
    tex: str
    pdf: Path
    pages: tuple[Path, ...]
    manifest: Path

    @property
    def caption(self) -> str:
        failures = sum(1 for item in self.evidence if item.error)
        tail = f" · {failures} 个主题正文证据未补全" if failures else ""
        return f"超理日报 · {self.date} · 今日活跃 {len(self.cards)} 主题{tail}"


def _one_line(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) > limit:
        value = value[: max(1, limit - 1)].rstrip() + "…"
    return value


def _prose(text: str, limit: int) -> str:
    """Normalize model prose while preserving editorial paragraph structure."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = []
    for part in re.split(r"\n\s*\n+", raw):
        line = re.sub(r"[ \t]+", " ", part).strip()
        line = re.sub(r"\n+", " ", line).strip()
        if line:
            paragraphs.append(line)
    value = "\n\n".join(paragraphs)
    if len(value) > limit:
        value = value[: max(1, limit - 1)].rstrip() + "…"
    return value


def _md(text: str) -> str:
    # Forum text is evidence, not Markdown source. Escape syntax so a post cannot
    # alter the report's structure or accidentally trigger math/raw formatting.
    value = str(text or "")
    value = value.replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "#", "<", ">", "$", "|"):
        value = value.replace(char, "\\" + char)
    return value


def _floor_excerpt(floor: Floor, limit: int) -> str:
    if floor.deleted:
        return "〔该楼已删除；公开页无正文〕"
    body = _one_line(floor.text, limit)
    return body or "〔无可抽取文本，可能只有图片或附件〕"


async def _topic_evidence(card: ThreadCard, *, recent: int = 4) -> DailyTopicEvidence:
    """Fetch first-page context and all discoverable activity in the last 24h."""
    try:
        first_html, last_ref = await asyncio.gather(
            ChaoliService._get(f"/index.php/{card.thread_id}"),
            ChaoliService._fetch_exact_ref(f"https://chaoli.club/index.php/{card.thread_id}/last"),
        )
        _, first_floors = ChaoliService._parse_thread(first_html, card.thread_id)
        last_tid, _post_id, last_html, resolved_url = last_ref
        if last_tid != card.thread_id:
            raise ChaoliError("末页重定向到了其他主题")
        _, last_floors = ChaoliService._parse_thread(last_html, card.thread_id)
        first = next((x for x in first_floors if not x.deleted), first_floors[0] if first_floors else None)

        pages: list[list[Floor]] = [last_floors]
        page_match = re.search(rf"/{card.thread_id}/p(\d+)(?:$|[?#])", resolved_url)
        page_no = int(page_match.group(1)) if page_match else 1
        cutoff = datetime.now(SHANGHAI) - timedelta(hours=24)

        def floor_dt(floor: Floor) -> datetime | None:
            raw = str(floor.time or "").strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    return datetime.strptime(raw, fmt).replace(tzinfo=SHANGHAI)
                except ValueError:
                    continue
            return None

        # Walk backwards only while the whole current earliest page is still
        # inside the display window. This captures all recent floors without
        # crawling the entire historical thread.
        while page_no > 1:
            dated = [floor_dt(x) for x in pages[-1] if floor_dt(x) is not None]
            if dated and min(dated) < cutoff:
                break
            page_no -= 1
            prev_html = await ChaoliService._get(f"/index.php/{card.thread_id}/p{page_no}")
            _, prev_floors = ChaoliService._parse_thread(prev_html, card.thread_id)
            pages.append(prev_floors)

        merged: dict[str, Floor] = {}
        for floors in reversed(pages):
            for floor in floors:
                merged[floor.url] = floor
        chronological = sorted(merged.values(), key=lambda x: x.number)
        available = [x for x in chronological if not x.deleted]
        activity = tuple(x for x in available if (floor_dt(x) is not None and floor_dt(x) >= cutoff))
        latest = tuple(available[-max(1, min(int(recent), 6)):])
        return DailyTopicEvidence(card, first, activity, latest)
    except Exception as exc:
        # Never drop the topic selected by #今日活跃 merely because enrichment
        # failed. The index row remains authoritative and the report records the
        # missing evidence explicitly.
        return DailyTopicEvidence(card, None, (), (), f"{type(exc).__name__}: {exc}")


async def collect_daily_evidence(cards: list[ThreadCard], *, concurrency: int = 3) -> list[DailyTopicEvidence]:
    sem = asyncio.Semaphore(max(1, min(int(concurrency), 5)))

    async def one(card: ThreadCard) -> DailyTopicEvidence:
        async with sem:
            return await _topic_evidence(card)

    return list(await asyncio.gather(*(one(card) for card in cards)))



def _summary_evidence_payload(item: DailyTopicEvidence) -> dict:
    floors: list[Floor] = []
    if item.first_floor is not None:
        floors.append(item.first_floor)
    for floor in item.activity_floors:
        if all(floor.url != old.url for old in floors):
            floors.append(floor)
    if len(floors) == (1 if item.first_floor is not None else 0):
        for floor in item.latest_floors[-2:]:
            if all(floor.url != old.url for old in floors):
                floors.append(floor)
    return {
        "thread_id": item.card.thread_id,
        "title": item.card.title,
        "channel": item.card.channel,
        "author": item.card.author,
        "started": item.card.started,
        "last_author": item.card.last_author,
        "updated": item.card.updated,
        "cumulative_replies": reply_count(item.card.replies),
        "floors": [
            {
                "floor": floor.number,
                "author": floor.author,
                "time": floor.time,
                "text": _one_line(floor.text, 900),
            }
            for floor in floors
        ],
    }



async def _report_provider_json(provider, system: str, prompt: str, *, max_tokens: int):
    """One explicit non-agent JSON request for the report pipeline.

    AstrBot 4.27's public OpenAI-compatible ``text_chat`` currently discards
    arbitrary kwargs while preparing payloads. For report calls we therefore
    reuse the configured provider's own query/client path but make the sampling
    and reasoning controls explicit. This stays local to the report generator.
    """
    query = getattr(provider, "_query", None)
    get_model = getattr(provider, "get_model", None)
    if callable(query) and callable(get_model):
        payload = {
            "model": get_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": int(max_tokens),
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }
        return await query(payload, None, request_max_retries=1)
    # Compatibility fallback for tests or non-OpenAI providers. The prompt still
    # fully specifies JSON-only behavior; providers that honor kwargs get the
    # same controls, while validation below rejects malformed output.
    return await provider.text_chat(
        prompt=prompt,
        system_prompt=system,
        temperature=0.0,
        max_tokens=int(max_tokens),
        request_max_retries=1,
        thinking={"type": "disabled"},
        response_format={"type": "json_object"},
    )

def _extract_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    lo, hi = text.find("{"), text.rfind("}")
    if lo < 0 or hi <= lo:
        raise ValueError("summary JSON object missing")
    value = json.loads(text[lo : hi + 1])
    if not isinstance(value, dict):
        raise ValueError("summary JSON root is not object")
    return value


async def summarize_daily_topics(provider, evidence: list[DailyTopicEvidence], *, batch_size: int = 3) -> list[DailyTopicSummary]:
    """Write evidence-grounded newsroom copy for every active forum topic.

    This is direct provider work: no chat history, no persona, no Agent tools.
    The returned prose is the factual article body used in the final issue; the
    chief-editor pass may rank and title it but may not rewrite these facts.
    """
    if provider is None:
        return [DailyTopicSummary(x.card.thread_id, "", (), "no_provider") for x in evidence]

    system = (
        "你是严肃技术社区日报的采编记者。仅依据输入中的论坛楼层证据写中文稿件，不能使用群聊上下文、人物设定、外部知识或常识补全。"
        "每个主题都要写成一篇可以直接刊登的小稿，而不是标题列表或三句摘要。先用自然语言交代讨论对象和必要背景，再写最近24小时真正出现的推进、论证、反例、修正、分歧或结果；"
        "如果某条更新只是在顶帖、征求意见或补链接，就如实写短，不制造进展。数学/物理/语言学等技术内容尽量保留具体对象、条件、数值、构造或结论，但不要伪造公式。"
        "根据证据量写2到5个自然段；实质内容丰富时约350到750中文字符，证据稀薄时可以更短。不要使用‘主题概述/今日进展/关键观点/待解决问题’之类模板小标题，"
        "不要寒暄，不使用第一人称，不评价坛友人格。若证据无法支持某一点，直接不写；若整帖证据不足，明确写证据不足。"
        "每条稿件必须列出支撑它的楼层号，楼层号只能来自输入。返回严格 JSON："
        "{\"topics\":[{\"thread_id\":123,\"article\":\"多段正文\",\"evidence_floors\":[1,5]}]}。"
    )
    out: dict[int, DailyTopicSummary] = {}
    batch_size = max(1, min(int(batch_size), 4))
    for start in range(0, len(evidence), batch_size):
        batch = evidence[start : start + batch_size]
        payload = [_summary_evidence_payload(item) for item in batch]
        allowed = {
            item.card.thread_id: {floor["floor"] for floor in row["floors"]}
            for item, row in zip(batch, payload)
        }
        prompt = "按输入顺序撰写可直接刊登的日报稿件，不遗漏 thread_id。\n\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            resp = await _report_provider_json(
                provider, system, prompt, max_tokens=min(5200, 900 + 1100 * len(batch))
            )
            root = _extract_json_object(resp.completion_text or "")
            rows = root.get("topics")
            if not isinstance(rows, list):
                raise ValueError("topics missing")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    tid = int(row.get("thread_id"))
                except Exception:
                    continue
                if tid not in allowed:
                    continue
                text = _prose(str(row.get("article") or row.get("summary") or ""), 1800)
                raw_floors = row.get("evidence_floors")
                if not isinstance(raw_floors, list):
                    raw_floors = []
                floors: list[int] = []
                invalid_ref = False
                for value in raw_floors:
                    try:
                        floor_no = int(value)
                    except Exception:
                        invalid_ref = True
                        continue
                    if floor_no not in allowed[tid]:
                        invalid_ref = True
                        continue
                    if floor_no not in floors:
                        floors.append(floor_no)
                if not text:
                    continue
                if invalid_ref or not floors:
                    out[tid] = DailyTopicSummary(tid, "", (), "invalid_evidence_refs")
                else:
                    out[tid] = DailyTopicSummary(tid, text, tuple(floors))
        except Exception as exc:
            for item in batch:
                out.setdefault(item.card.thread_id, DailyTopicSummary(item.card.thread_id, "", (), f"{type(exc).__name__}: {exc}"))

    return [out.get(item.card.thread_id, DailyTopicSummary(item.card.thread_id, "", (), "summary_missing")) for item in evidence]



def _fallback_editorial(evidence: list[DailyTopicEvidence], summaries: list[DailyTopicSummary], error: str = "") -> DailyEditorialIssue:
    summary_by_id = {x.thread_id: x for x in summaries}

    def score(item: DailyTopicEvidence) -> tuple[int, int, int]:
        replies = reply_count(item.card.replies) or 0
        substantive = sum(1 for floor in item.activity_floors if len(_one_line(floor.text, 500)) >= 40)
        return (substantive * 4 + len(item.activity_floors) * 2, replies, item.card.thread_id)

    ordered = sorted(evidence, key=score, reverse=True)
    blocks: list[DailyEditorialBlock] = []
    for idx, item in enumerate(ordered):
        summary = summary_by_id.get(item.card.thread_id)
        text = summary.text if summary and summary.text else item.card.title
        blocks.append(DailyEditorialBlock(
            "lead" if idx == 0 else ("feature" if len(item.activity_floors) >= 2 else "brief"),
            (item.card.thread_id,),
            item.card.title,
            _one_line(text, 120),
        ))
    lead = ordered[0].card.title if ordered else "今日论坛"
    stand = "；".join(
        _one_line((summary_by_id.get(item.card.thread_id).text if summary_by_id.get(item.card.thread_id) else "") or item.card.title, 120)
        for item in ordered[:2]
    )
    return DailyEditorialIssue(_one_line(lead, 48), _one_line(stand, 280), tuple(blocks), error)


async def editorialize_daily(provider, evidence: list[DailyTopicEvidence], summaries: list[DailyTopicSummary]) -> DailyEditorialIssue:
    """Assign newspaper hierarchy and headlines without rewriting article facts."""
    if not evidence:
        return DailyEditorialIssue("今日没有活跃主题", "论坛 #今日活跃 当前为空。", (), "empty")
    if provider is None:
        return _fallback_editorial(evidence, summaries, "no_provider")

    summary_by_id = {x.thread_id: x for x in summaries}
    entries = []
    for item in evidence:
        summary = summary_by_id.get(item.card.thread_id)
        entries.append({
            "thread_id": item.card.thread_id,
            "title": item.card.title,
            "channel": item.card.channel,
            "updated": item.card.updated,
            "cumulative_replies": reply_count(item.card.replies),
            "activity_24h": len(item.activity_floors),
            "authors_24h": list(dict.fromkeys(x.author for x in item.activity_floors if x.author))[:8],
            "article": summary.text if summary and summary.text else "正文证据不足",
            "evidence_floors": list(summary.evidence_floors if summary else ()),
        })

    system = (
        "你是一份正式学术技术社区 bulletin 的总编辑。输入中的 article 已经逐楼层校验，是最终事实正文；你绝对不能重写、扩写或补充正文事实。"
        "你的工作只包括：给整期拟一个具体、克制、有信息量的期标题；写一段80到180字的整期导语，说明今天主要研究议题及其关系；"
        "为每个 thread 单独决定 lead/feature/brief 版面等级，并拟一个学术简报式稿件标题和一句很短的 deck。"
        "期标题和稿件标题都要像学会 newsletter 或研究简报：优先准确概括对象、问题和新进展，避免‘热议/引爆/震撼/焦点/重磅’等媒体化措辞。"
        "必须根据实际信息量拉开主次：真正有推导、实验、计算、争论或结论推进的可以做专题；只有轻量更新的必须降为简讯。"
        "不要写‘今日看点/精彩回顾/值得关注/社区动态’等空标题，不要为了叙事强行关联无关主题。"
        "每个 thread_id 必须且只能出现一次，每个 block 只能包含一个 thread_id，整期恰好一个 lead。"
        "返回严格 JSON：{\"headline\":\"...\",\"standfirst\":\"...\",\"blocks\":["
        "{\"level\":\"lead\",\"thread_ids\":[123],\"headline\":\"...\",\"deck\":\"...\"}]}。"
    )
    prompt = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    try:
        resp = await _report_provider_json(provider, system, prompt, max_tokens=min(2600, 800 + 300 * len(entries)))
        root = _extract_json_object(resp.completion_text or "")
        headline = _one_line(str(root.get("headline") or ""), 72)
        standfirst = _prose(str(root.get("standfirst") or ""), 420)
        raw_blocks = root.get("blocks")
        if not headline or not standfirst or not isinstance(raw_blocks, list):
            raise ValueError("editorial_shape")
        known = {x.card.thread_id for x in evidence}
        seen: list[int] = []
        blocks: list[DailyEditorialBlock] = []
        lead_count = 0
        for row in raw_blocks:
            if not isinstance(row, dict):
                raise ValueError("editorial_block_not_object")
            level = str(row.get("level") or "").strip().lower()
            if level not in {"lead", "feature", "brief"}:
                raise ValueError("editorial_level")
            tids_raw = row.get("thread_ids")
            if not isinstance(tids_raw, list) or len(tids_raw) != 1:
                raise ValueError("editorial_thread_ids")
            tid = int(tids_raw[0])
            if tid not in known or tid in seen:
                raise ValueError("editorial_thread_reference")
            seen.append(tid)
            if level == "lead":
                lead_count += 1
            block_head = _one_line(str(row.get("headline") or ""), 78)
            deck = _one_line(str(row.get("deck") or ""), 180)
            if not block_head or not deck:
                raise ValueError("editorial_empty_block")
            blocks.append(DailyEditorialBlock(level, (tid,), block_head, deck))
        if set(seen) != known or len(seen) != len(known) or lead_count != 1:
            raise ValueError("editorial_coverage")
        order = {"lead": 0, "feature": 1, "brief": 2}
        blocks.sort(key=lambda x: order[x.level])
        return DailyEditorialIssue(headline, standfirst, tuple(blocks))
    except Exception as exc:
        return _fallback_editorial(evidence, summaries, f"{type(exc).__name__}: {exc}")


def _topic_activity_meta(item: DailyTopicEvidence) -> str:
    activity = list(item.activity_floors)
    if not activity:
        return "过去24小时未解析到独立楼层更新"
    authors = []
    for floor in activity:
        if floor.author and floor.author not in authors:
            authors.append(floor.author)
    first_time = activity[0].time[11:16] if len(activity[0].time) >= 16 else activity[0].time
    last_time = activity[-1].time[11:16] if len(activity[-1].time) >= 16 else activity[-1].time
    who = "、".join(authors[:4]) + (" 等" if len(authors) > 4 else "")
    return f"过去24小时 {len(activity)} 个公开楼层更新 · {first_time}–{last_time}" + (f" · {who}" if who else "")


def _summary_floor_map(item: DailyTopicEvidence) -> dict[int, Floor]:
    rows: dict[int, Floor] = {}
    if item.first_floor is not None:
        rows[item.first_floor.number] = item.first_floor
    for floor in item.activity_floors:
        rows[floor.number] = floor
    for floor in item.latest_floors:
        rows.setdefault(floor.number, floor)
    return rows

def _report_markdown(
    cards: list[ThreadCard],
    evidence: list[DailyTopicEvidence],
    summaries: list[DailyTopicSummary],
    date: str,
    source: str,
) -> str:
    generated = datetime.now(SHANGHAI).strftime("%H:%M")
    board_counts = Counter((card.channel or "未标注板块") for card in cards)
    activity_count = sum(len(item.activity_floors) for item in evidence)
    failures = sum(1 for item in evidence if item.error)
    summary_failures = sum(1 for item in summaries if item.error or not item.text)
    summary_by_id = {item.thread_id: item for item in summaries}
    evidence_by_id = {item.card.thread_id: item for item in evidence}
    board_deck = " · ".join(f"{board} {count}" for board, count in sorted(board_counts.items(), key=lambda x: (-x[1], x[0])))

    lines: list[str] = [
        f"# 超理日报 · {date}",
        "",
        f"{len(cards)} 个 `#今日活跃` 主题 · 过去 24h 解析到 {activity_count} 个公开楼层更新 · {board_deck} · 截至 {generated}",
        "",
    ]

    for index, card in enumerate(cards, 1):
        item = evidence_by_id[card.thread_id]
        summary = summary_by_id.get(card.thread_id, DailyTopicSummary(card.thread_id, "", (), "missing"))
        lines += [
            f"## {index:02d} · {_md(card.title)}",
            "",
        ]
        meta = [card.channel or "未标注板块", f"#{card.thread_id}"]
        if card.author:
            meta.append(f"发帖 {card.author}")
        if card.last_author:
            meta.append(f"最后回复 {card.last_author}")
        if card.updated:
            meta.append(card.updated)
        rc = reply_count(card.replies)
        if rc is not None:
            meta.append(f"累计 {rc} 回复")
        lines += [" · ".join(_md(x) for x in meta), ""]

        if summary.text:
            lines += [summary.text, ""]
            floor_list = "、".join(f"{n}楼" for n in summary.evidence_floors)
            if floor_list:
                lines += [f"*摘要证据：{floor_list}*", ""]
        elif item.error:
            lines += ["正文证据本次未能补全；该主题仍按官方 `#今日活跃` 结果保留，不对内容作推断。", ""]
        else:
            first = item.first_floor
            fallback = _floor_excerpt(first, 360) if first is not None else "证据不足，自动概括未生成。"
            lines += [fallback, "", "*自动概括未生成；以下只保留可核验楼层。*", ""]

        lines += [f"**{_md(_topic_activity_meta(item))}**", ""]

        floor_map = _summary_floor_map(item)
        shown: set[int] = set()
        for floor_no in summary.evidence_floors[:4]:
            floor = floor_map.get(floor_no)
            if floor is None:
                continue
            shown.add(floor.number)
            lines += [
                f"> **{floor.number}楼 · {_md(floor.author or '作者未标注')} · {_md(floor.time)}**  ",
                f"> {_md(_floor_excerpt(floor, 320))}  ",
                f"> {floor.url}",
                "",
            ]

        # Keep the daily evidence complete without turning the issue into a raw
        # transcript: every remaining 24h floor is still represented once in a
        # compact timeline, while the summary-cited floors receive larger cards.
        remaining = [floor for floor in item.activity_floors if floor.number not in shown]
        if remaining:
            for floor in remaining:
                lines += [
                    f"- **{floor.number}楼 · {_md(floor.author or '作者未标注')} · {_md(floor.time)}** — {_md(_floor_excerpt(floor, 180))}  ",
                    f"  {floor.url}",
                ]
            lines.append("")
        elif not shown and item.first_floor is not None:
            floor = item.first_floor
            lines += [
                f"> **{floor.number}楼 · {_md(floor.author or card.author or '作者未标注')} · {_md(floor.time)}**  ",
                f"> {_md(_floor_excerpt(floor, 320))}  ",
                f"> {floor.url}",
                "",
            ]

        lines += [card.url, "", "---", ""]

    footer = (
        f"数据主题集合来自 {_md(source)}；逐帖正文只读取公开页面并强绑定真实楼层/作者/permalink。"
        "摘要由独立日报摘要器基于本页可核验楼层生成，不读取群聊上下文或豆子人格，不补充外部事实；"
        "主题 replies 为历史累计值，不代表当日新增。"
        f"正文补全失败 {failures}/{len(evidence)}，摘要失败 {summary_failures}/{len(summaries)}。"
    )
    lines += [footer]
    return "\n".join(lines).strip() + "\n"




def _tex_escape(value: str) -> str:
    """Escape untrusted forum/model text for literal XeLaTeX prose."""
    text = str(value or "")
    mapping = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "&": r"\&",
        "_": r"\_",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    return "".join(mapping.get(ch, ch) for ch in text)


def _tex_prose(value: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", str(value or "")) if p.strip()]
    return "\n\n".join(_tex_escape(p) + r"\par" for p in paragraphs)


def _tex_url(value: str) -> str:
    # Hyperref's \url reads a verbatim-like argument. Braces/backslashes are not
    # expected in Chaoli permalinks; percent-encode the few unsafe characters.
    from urllib.parse import quote
    safe = quote(str(value or ""), safe=":/?#[]@!$&'()*+,;=-._~%")
    return r"\url{" + safe.replace("{", "%7B").replace("}", "%7D").replace("\\", "%5C") + "}"


def _story_meta(item: DailyTopicEvidence) -> str:
    card = item.card
    parts = [card.channel or "未标注板块", f"#{card.thread_id}"]
    if card.author:
        parts.append(card.author)
    return " · ".join(parts)


def _article_body(item: DailyTopicEvidence, summary: DailyTopicSummary) -> str:
    if summary.text:
        return summary.text
    if item.error:
        return "本次逐帖证据未能补全。该主题仍按论坛 #今日活跃 索引保留，日报不对正文内容作推断。"
    if item.first_floor is not None:
        return _floor_excerpt(item.first_floor, 900) + "\n\n自动采编稿未生成，本页只保留可核验首楼内容。"
    return "本次公开正文证据不足，日报仅保留该主题的索引记录。"


def _source_line(item: DailyTopicEvidence, summary: DailyTopicSummary) -> str:
    floors = "、".join(str(n) for n in summary.evidence_floors) if summary.evidence_floors else "首楼"
    return _tex_escape(f"证据 {floors} · chaoli.club/index.php/{item.card.thread_id}")


def _render_story_tex(
    block: DailyEditorialBlock,
    evidence_by_id: dict[int, DailyTopicEvidence],
    summary_by_id: dict[int, DailyTopicSummary],
    *,
    lead: bool = False,
) -> str:
    tid = block.thread_ids[0]
    item = evidence_by_id[tid]
    summary = summary_by_id.get(tid, DailyTopicSummary(tid, "", (), "missing"))
    body = _article_body(item, summary)
    meta = _tex_escape(_story_meta(item))
    headline = _tex_escape(block.headline)
    source = _source_line(item, summary)
    if lead:
        return (
            r"\Needspace{15\baselineskip}" + "\n"
            r"\begin{minipage}{\textwidth}" + "\n"
            r"\Meta{" + meta + r"}\vspace{1.35mm}" + "\n"
            r"\MainTitle{" + headline + r"}" + "\n"
            r"\end{minipage}\par\nopagebreak[4]\vspace{2.9mm}" + "\n"
            r"\begingroup\begin{multicols}{2}" + "\n"
            r"{\sloppy\fontsize{9.55}{14.2}\selectfont " + _tex_prose(body) + "}\n"
            r"\end{multicols}\endgroup" + "\n"
            r"\vspace{0.9mm}\Source{" + source + r"}\ArticleRule" + "\n"
        )

    story = (
        r"\Needspace{12\baselineskip}" + "\n"
        r"\begin{minipage}{\textwidth}" + "\n"
        r"\Meta{" + meta + r"}\vspace{1.15mm}" + "\n"
        r"\StoryTitle{" + headline + "}\n"
        r"\end{minipage}\par\nopagebreak[4]\vspace{2.7mm}" + "\n"
        r"\begingroup\begin{multicols}{2}" + "\n"
        r"{\sloppy\fontsize{9.55}{14.2}\selectfont " + _tex_prose(body) + "}\n"
        r"\end{multicols}\endgroup" + "\n"
        r"\vspace{0.9mm}\Source{" + source + r"}\ArticleRule" + "\n"
    )
    return story


def _issue_number(date: str) -> str:
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
        return d.strftime("%Y%m%d")
    except Exception:
        return re.sub(r"\D+", "", date) or "DAILY"


def _render_issue_tex(
    cards: list[ThreadCard],
    evidence: list[DailyTopicEvidence],
    summaries: list[DailyTopicSummary],
    editorial: DailyEditorialIssue,
    date: str,
    source: str,
) -> str:
    template_path = Path(__file__).resolve().parent / "templates" / "chaoli_daily.tex"
    template = template_path.read_text(encoding="utf-8")
    evidence_by_id = {x.card.thread_id: x for x in evidence}
    summary_by_id = {x.thread_id: x for x in summaries}
    lead = next((x for x in editorial.blocks if x.level == "lead"), None)
    columns = [x for x in editorial.blocks if x.level != "lead"]
    lead_tex = _render_story_tex(lead, evidence_by_id, summary_by_id, lead=True) if lead else ""
    secondary_tex = ""
    if columns:
        # Pages are composed from whole article units. For ordinary small issues
        # natural flow is sufficient; once there are at least five topics,
        # choose a single page break by estimated article height so page two is
        # not left as a sparse tail. The article order and editorial hierarchy
        # remain unchanged.
        if len(cards) >= 6 and len(columns) >= 5 and lead is not None:
            def layout_weight(block: DailyEditorialBlock) -> int:
                tid = block.thread_ids[0]
                summary = summary_by_id.get(tid, DailyTopicSummary(tid, "", (), "missing"))
                return len(_article_body(evidence_by_id[tid], summary)) + 110

            lead_weight = layout_weight(lead) + 40
            total_weight = lead_weight + sum(layout_weight(x) for x in columns)
            target = total_weight * 0.46
            running = lead_weight
            candidates: list[tuple[float, int]] = []
            # Keep at least two complete stories for page two.
            max_first = max(1, len(columns) - 2)
            for count in range(1, max_first + 1):
                running += layout_weight(columns[count - 1])
                candidates.append((abs(running - target), count))
            split = min(candidates)[1]
            first_tex = "\n".join(
                _render_story_tex(x, evidence_by_id, summary_by_id) for x in columns[:split]
            )
            rest_tex = "\n".join(
                _render_story_tex(x, evidence_by_id, summary_by_id) for x in columns[split:]
            )
            secondary_tex = first_tex + "\n" + r"\newpage" + "\n" + rest_tex + "\n"
        else:
            story_tex = "\n".join(_render_story_tex(x, evidence_by_id, summary_by_id) for x in columns)
            secondary_tex = story_tex + "\n"
    generated = datetime.now(SHANGHAI).strftime("%H:%M")
    replacements = {
        "@@DATE@@": _tex_escape(date),
        "@@ISSUE@@": _tex_escape(_issue_number(date)),
        "@@TIME@@": _tex_escape(generated),
        "@@LEAD_STORY@@": lead_tex,
        "@@SECONDARY_SECTION@@": secondary_tex,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    if re.search(r"@@[A-Z_]+@@", template):
        raise RuntimeError("Chaoli TeX template contains unresolved placeholders")
    return template


def _rasterize_pdf_pages(pdf_path: Path, out: Path, stem: str, *, scale: float = 2.55) -> tuple[Path, ...]:
    try:
        import pypdfium2 as pdfium
    except Exception as exc:
        raise RuntimeError("Chaoli PDF preview requires pypdfium2") from exc
    doc = pdfium.PdfDocument(str(pdf_path))
    pages: list[Path] = []
    for index in range(len(doc)):
        page = doc[index]
        bitmap = page.render(scale=scale, rev_byteorder=True)
        image = bitmap.to_pil().convert("RGB")
        path = out / f"{stem}-page-{index + 1:02d}.png"
        image.save(path, "PNG", optimize=True)
        pages.append(path)
        bitmap.close()
        page.close()
    doc.close()
    if not pages:
        raise RuntimeError("Chaoli report PDF contains no pages")
    return tuple(pages)


def _compile_issue_tex(out: Path, tex_text: str, stem: str) -> tuple[Path, tuple[Path, ...]]:
    generated_pdf, _caption = _render_tex_document(out, tex_text)
    final_pdf = out / f"{stem}.pdf"
    if generated_pdf.resolve() != final_pdf.resolve():
        shutil.copy2(generated_pdf, final_pdf)
    pages = _rasterize_pdf_pages(final_pdf, out, stem)
    return final_pdf, pages

def _signature(cards: list[ThreadCard], date: str, source: str) -> str:
    payload = {
        "template_revision": REPORT_TEMPLATE_REV,
        "date": date,
        "source": source,
        "cards": [
            {
                "id": card.thread_id,
                "crc": card.crc,
                "title": card.title,
                "updated": card.updated,
                "replies": card.replies,
            }
            for card in cards
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _load_frozen_report(out: Path, cards: list[ThreadCard], date: str, source: str, sig: str) -> DailyReportBundle | None:
    manifest = out / f"chaoli-daily-{date}-{sig}.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema") != REPORT_SCHEMA or data.get("template_revision") != REPORT_TEMPLATE_REV:
            return None
        if data.get("signature") != sig or data.get("date") != date:
            return None
        pdf = out / str(data.get("pdf_file") or "")
        pages = tuple(out / str(x) for x in (data.get("page_files") or []))
        tex_path = out / f"chaoli-daily-{date}-{sig}.tex"
        md_path = out / f"chaoli-daily-{date}-{sig}.md"
        if not pdf.exists() or not pdf.read_bytes()[:4] == b"%PDF" or not pages or not all(x.exists() and x.stat().st_size > 1000 for x in pages):
            return None
        editorial_raw = data.get("editorial") or {}
        editorial = DailyEditorialIssue(
            str(editorial_raw.get("headline") or "超理日报"),
            str(editorial_raw.get("standfirst") or ""),
            tuple(
                DailyEditorialBlock(
                    str(x.get("level") or "brief"),
                    tuple(int(v) for v in (x.get("thread_ids") or [])),
                    str(x.get("headline") or ""),
                    str(x.get("deck") or ""),
                )
                for x in (editorial_raw.get("blocks") or [])
            ),
            str(editorial_raw.get("error") or ""),
        )
        topics = {int(x.get("thread_id")): x for x in (data.get("topics") or []) if x.get("thread_id") is not None}
        evidence = []
        summaries = []
        for card in cards:
            row = topics.get(card.thread_id, {})
            evidence.append(DailyTopicEvidence(card, None, (), (), str(row.get("evidence_error") or "")))
            summaries.append(DailyTopicSummary(
                card.thread_id,
                str(row.get("article") or ""),
                tuple(int(x) for x in (row.get("article_evidence_floors") or [])),
                str(row.get("article_error") or ""),
            ))
        return DailyReportBundle(
            date, source, tuple(cards), tuple(evidence), tuple(summaries), editorial,
            md_path.read_text(encoding="utf-8") if md_path.exists() else "",
            tex_path.read_text(encoding="utf-8") if tex_path.exists() else "",
            pdf, pages, manifest,
        )
    except Exception:
        return None


async def build_daily_report(output_dir: Path, cards: list[ThreadCard], date: str, source: str, *, provider=None) -> DailyReportBundle:
    out = Path(output_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    sig = _signature(cards, date, source)
    frozen = _load_frozen_report(out, cards, date, source, sig)
    if frozen is not None:
        return frozen
    evidence = await collect_daily_evidence(cards)
    summaries = await summarize_daily_topics(provider, evidence)
    editorial = await editorialize_daily(provider, evidence, summaries)
    markdown = _report_markdown(cards, evidence, summaries, date, source)  # audit trail only
    tex_text = _render_issue_tex(cards, evidence, summaries, editorial, date, source)
    source_path = out / f"chaoli-daily-{date}-{sig}.md"
    source_path.write_text(markdown, encoding="utf-8")
    tex_path = out / f"chaoli-daily-{date}-{sig}.tex"
    tex_path.write_text(tex_text, encoding="utf-8")

    manifest_data = {
        "schema": REPORT_SCHEMA,
        "template_revision": REPORT_TEMPLATE_REV,
        "date": date,
        "generated_at": datetime.now(SHANGHAI).isoformat(),
        "source": source,
        "topic_count": len(cards),
        "signature": sig,
        "renderer": "XeTeX/Tectonic Chaoli journal template",
        "editorial": {
            "headline": editorial.headline,
            "standfirst": editorial.standfirst,
            "error": editorial.error,
            "blocks": [
                {"level": x.level, "thread_ids": list(x.thread_ids), "headline": x.headline, "deck": x.deck}
                for x in editorial.blocks
            ],
        },
        "topics": [
            {
                "thread_id": item.card.thread_id,
                "title": item.card.title,
                "channel": item.card.channel,
                "author": item.card.author,
                "last_author": item.card.last_author,
                "started": item.card.started,
                "updated": item.card.updated,
                "replies": reply_count(item.card.replies),
                "url": item.card.url,
                "evidence_error": item.error,
                "article": next((x.text for x in summaries if x.thread_id == item.card.thread_id), ""),
                "article_evidence_floors": list(next((x.evidence_floors for x in summaries if x.thread_id == item.card.thread_id), ())),
                "article_error": next((x.error for x in summaries if x.thread_id == item.card.thread_id), ""),
                "first_floor": item.first_floor.number if item.first_floor else None,
                "activity_floors_24h": [floor.number for floor in item.activity_floors],
                "latest_floors": [floor.number for floor in item.latest_floors],
            }
            for item in evidence
        ],
    }
    manifest = out / f"chaoli-daily-{date}-{sig}.json"

    render_stem = f"chaoli-daily-{date}-{sig}-{hashlib.sha256(tex_text.encode('utf-8')).hexdigest()[:10]}"
    pdf_path, pages = await asyncio.to_thread(_compile_issue_tex, out, tex_text, render_stem)
    manifest_data["render_stem"] = render_stem
    manifest_data["pdf_file"] = pdf_path.name
    manifest_data["page_files"] = [x.name for x in pages]
    manifest.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return DailyReportBundle(
        date, source, tuple(cards), tuple(evidence), tuple(summaries), editorial, markdown, tex_text, pdf_path, tuple(pages), manifest
    )

