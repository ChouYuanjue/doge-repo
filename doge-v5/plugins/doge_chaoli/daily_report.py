from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from data.plugins.doge_shared.chaoli import ChaoliError, ChaoliService, Floor, ThreadCard
from .push import reply_count

SHANGHAI = ZoneInfo("Asia/Shanghai")


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
    body: str


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
    html: str
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
                "text": _one_line(floor.text, 520),
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


async def summarize_daily_topics(provider, evidence: list[DailyTopicEvidence], *, batch_size: int = 4) -> list[DailyTopicSummary]:
    """Evidence-grounded editorial summaries via direct provider calls.

    This deliberately bypasses AstrBot event/Agent hooks: no conversation
    contexts, no Doge persona, no group history and no tools are supplied.
    """
    if provider is None:
        return [DailyTopicSummary(x.card.thread_id, "", (), "no_provider") for x in evidence]

    system = (
        "你是技术论坛日报的严谨编辑，不是聊天机器人。仅依据输入中的论坛证据写中文摘要。"
        "每个主题写一个自然连贯的短段落，不套固定分段或固定句式；让读者只看这段就能判断帖子在讲什么、"
        "最近24小时有哪些值得注意的推进，以及是否值得点进原帖继续读。句子从具体内容本身开始，避免泛泛的导语和总结腔。"
        "不要寒暄，不使用第一人称，不带人格，不评价坛友，不推断现实身份，不补充外部知识。"
        "如果证据不足就明确说证据不足。每条摘要必须列出支撑它的楼层号；楼层号只能来自输入。"
        "返回严格 JSON：{\"topics\":[{\"thread_id\":123,\"summary\":\"2到4句摘要\",\"evidence_floors\":[1,5]}]}。"
    )
    out: dict[int, DailyTopicSummary] = {}
    batch_size = max(1, min(int(batch_size), 5))
    for start in range(0, len(evidence), batch_size):
        batch = evidence[start : start + batch_size]
        payload = [_summary_evidence_payload(item) for item in batch]
        allowed = {
            item.card.thread_id: {floor["floor"] for floor in row["floors"]}
            for item, row in zip(batch, payload)
        }
        prompt = (
            "请按输入顺序编辑这些主题。不要遗漏任何 thread_id。\n\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
        try:
            resp = await _report_provider_json(
                provider, system, prompt, max_tokens=min(2200, 420 + 420 * len(batch))
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
                text = _one_line(str(row.get("summary") or ""), 520)
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
        body = (summary.text if summary and summary.text else "") or (
            _floor_excerpt(item.first_floor, 360) if item.first_floor is not None else "本次正文证据不足。"
        )
        blocks.append(DailyEditorialBlock(
            "lead" if idx == 0 else ("feature" if len(item.activity_floors) >= 2 else "brief"),
            (item.card.thread_id,),
            item.card.title,
            _one_line(body, 520 if idx == 0 else 360),
        ))
    lead = ordered[0].card.title if ordered else "今日论坛"
    stand = "；".join(
        _one_line((summary_by_id.get(item.card.thread_id).text if summary_by_id.get(item.card.thread_id) else "") or item.card.title, 100)
        for item in ordered[:2]
    )
    return DailyEditorialIssue(_one_line(lead, 42), _one_line(stand, 220), tuple(blocks), error)


async def editorialize_daily(provider, evidence: list[DailyTopicEvidence], summaries: list[DailyTopicSummary]) -> DailyEditorialIssue:
    """Turn validated topic capsules into one edited issue with real hierarchy.

    The editor only sees already-grounded capsules and activity metadata. It does
    not see chat history, persona state, raw tools or unrelated forum content.
    Every active thread must appear exactly once in the returned issue.
    """
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
            "capsule": summary.text if summary and summary.text else (
                _floor_excerpt(item.first_floor, 420) if item.first_floor is not None else "正文证据不足"
            ),
            "capsule_evidence_floors": list(summary.evidence_floors if summary else ()),
        })

    system = (
        "你是一份小型技术社区日报的编辑。输入已经是逐主题、逐楼层校验过的事实胶囊；你的任务不是再把它们按顺序复述一遍，"
        "而是编辑成一份读者可以直接读完的日报。先判断今天真正的主线和信息价值，再决定版面层级。"
        "必须把信息密度和主次拉开：有实质推进的讨论可以成为头条；只是顶帖、邀请反馈或轻量更新的主题应压成短讯。"
        "如果两个主题没有真实关系，不要为了制造叙事强行关联；如果确实相关，可以放在同一个 block 中。"
        "整期 headline 要具体到今天发生的内容，不写‘今日看点/值得关注/论坛动态/精彩回顾’这类空标题。"
        "standfirst 用一小段话交代今天整体发生了什么，让没点原帖的人也能获得信息。"
        "每个 block 的 headline 和 body 都从具体内容开始，body 可以重组输入 capsule，但不得加入 capsule 没有的事实、外部知识或人物判断。"
        "所有 thread_id 必须且只能出现一次；必须恰好有一个 lead。level 只能是 lead/feature/brief。"
        "lead 通常 180-360 中文字，feature 100-220 字，brief 40-110 字；不是字数任务，信息说完就停。"
        "返回严格 JSON：{\"headline\":\"...\",\"standfirst\":\"...\",\"blocks\":["
        "{\"level\":\"lead\",\"thread_ids\":[123],\"headline\":\"...\",\"body\":\"...\"}]}。"
    )
    prompt = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    try:
        resp = await _report_provider_json(
            provider, system, prompt, max_tokens=min(3600, 1000 + 480 * len(entries))
        )
        root = _extract_json_object(resp.completion_text or "")
        headline = _one_line(str(root.get("headline") or ""), 56)
        standfirst = _one_line(str(root.get("standfirst") or ""), 320)
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
            if not isinstance(tids_raw, list) or not tids_raw:
                raise ValueError("editorial_thread_ids")
            tids: list[int] = []
            for value in tids_raw:
                tid = int(value)
                if tid not in known or tid in seen or tid in tids:
                    raise ValueError("editorial_thread_reference")
                tids.append(tid)
            seen.extend(tids)
            if level == "lead":
                lead_count += 1
            block_head = _one_line(str(row.get("headline") or ""), 72)
            body_limit = 700 if level == "lead" else (460 if level == "feature" else 240)
            body = _one_line(str(row.get("body") or ""), body_limit)
            if not block_head or not body:
                raise ValueError("editorial_empty_block")
            blocks.append(DailyEditorialBlock(level, tuple(tids), block_head, body))
        if set(seen) != known or len(seen) != len(known) or lead_count != 1:
            raise ValueError("editorial_coverage")
        # Keep lead first, then features, then briefs; model still chooses which
        # stories receive each tier and may group genuinely related threads.
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



def _html_text(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def _block_source_refs(
    block: DailyEditorialBlock,
    evidence_by_id: dict[int, DailyTopicEvidence],
    summary_by_id: dict[int, DailyTopicSummary],
) -> tuple[str, str]:
    refs: list[str] = []
    urls: list[str] = []
    for tid in block.thread_ids:
        item = evidence_by_id[tid]
        summary = summary_by_id.get(tid)
        floors = list(summary.evidence_floors if summary else ())
        if floors:
            refs.append(f"#{tid} · " + " / ".join(f"{n}F" for n in floors[:6]))
        else:
            refs.append(f"#{tid}")
        urls.append(f"chaoli.club/index.php/{tid}")
    return " · ".join(refs), " · ".join(urls)


def _lead_quote(
    block: DailyEditorialBlock,
    evidence_by_id: dict[int, DailyTopicEvidence],
    summary_by_id: dict[int, DailyTopicSummary],
) -> tuple[str, str] | None:
    candidates: list[Floor] = []
    for tid in block.thread_ids:
        item = evidence_by_id[tid]
        summary = summary_by_id.get(tid)
        floor_map = _summary_floor_map(item)
        for floor_no in (summary.evidence_floors if summary else ()):
            floor = floor_map.get(floor_no)
            if floor is not None and len(_one_line(floor.text, 500)) >= 24:
                candidates.append(floor)
    if not candidates:
        return None
    floor = max(candidates, key=lambda x: len(_one_line(x.text, 500)))
    return _one_line(floor.text, 150), f"{floor.author or '作者未标注'} · {floor.number}楼"


def _render_issue_html(
    cards: list[ThreadCard],
    evidence: list[DailyTopicEvidence],
    summaries: list[DailyTopicSummary],
    editorial: DailyEditorialIssue,
    date: str,
    source: str,
) -> str:
    evidence_by_id = {x.card.thread_id: x for x in evidence}
    summary_by_id = {x.thread_id: x for x in summaries}
    activity_count = sum(len(x.activity_floors) for x in evidence)
    active_authors = len({f.author for x in evidence for f in x.activity_floors if f.author})
    generated = datetime.now(SHANGHAI).strftime("%H:%M")

    lead_blocks = [x for x in editorial.blocks if x.level == "lead"]
    feature_blocks = [x for x in editorial.blocks if x.level == "feature"]
    brief_blocks = [x for x in editorial.blocks if x.level == "brief"]

    def meta_for(block: DailyEditorialBlock) -> str:
        boards: list[str] = []
        updates = 0
        latest = ""
        for tid in block.thread_ids:
            item = evidence_by_id[tid]
            if item.card.channel and item.card.channel not in boards:
                boards.append(item.card.channel)
            updates += len(item.activity_floors)
            latest = max(latest, str(item.card.updated or ""))
        parts = boards + [f"24H 更新 {updates}"]
        if latest:
            parts.append(f"最近 {latest}")
        return " · ".join(parts)

    def story_html(block: DailyEditorialBlock, css_class: str) -> str:
        refs, urls = _block_source_refs(block, evidence_by_id, summary_by_id)
        source_titles = []
        for tid in block.thread_ids:
            card = evidence_by_id[tid].card
            source_titles.append(f"#{tid} {_html_text(card.title)}")
        quote = _lead_quote(block, evidence_by_id, summary_by_id) if block.level == "lead" else None
        quote_html = ""
        if quote:
            quote_html = (
                '<aside class="pullquote"><span class="quote-mark">“</span>'
                f'<p>{_html_text(quote[0])}</p><cite>{_html_text(quote[1])}</cite></aside>'
            )
        return (
            f'<article class="story {css_class}">'
            f'<div class="story-meta">{_html_text(meta_for(block))}</div>'
            f'<h2>{_html_text(block.headline)}</h2>'
            f'<div class="story-grid"><div class="story-copy"><p>{_html_text(block.body)}</p>'
            f'<div class="source-title">{"<br>".join(source_titles)}</div>'
            f'<div class="evidence-ref">证据 {_html_text(refs)}</div>'
            f'<div class="url-ref">{_html_text(urls)}</div></div>{quote_html}</div>'
            '</article>'
        )

    lead_html = "".join(story_html(x, "lead") for x in lead_blocks)
    features_html = "".join(story_html(x, "feature") for x in feature_blocks)
    briefs_html = "".join(story_html(x, "brief") for x in brief_blocks)

    source_note = (
        f"主题集合：{source}。正文证据来自公开楼层并绑定作者、楼层与 permalink；"
        "编辑摘要不读取群聊上下文或豆子人格。主题 replies 为历史累计值。"
    )
    error_note = ""
    errors = sum(1 for x in evidence if x.error) + sum(1 for x in summaries if x.error)
    if errors or editorial.error:
        error_note = f" · 取证/编辑退化 {errors + (1 if editorial.error else 0)} 项"

    css = r'''
    @page { size: 1200px 1600px; margin: 68px 76px 76px; }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: #f7f4ed; color: #172129; }
    body { font-family: "Noto Sans CJK SC", "Droid Sans", sans-serif; font-size: 20px; line-height: 1.62; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .issue { max-width: 1048px; margin: 0 auto; }
    .masthead { display: grid; grid-template-columns: 1fr auto; align-items: end; border-top: 8px solid #173d43; border-bottom: 1px solid #9aa5a3; padding: 18px 0 16px; margin-bottom: 46px; }
    .brand-cn { font-family: "Noto Serif CJK SC", serif; font-size: 42px; font-weight: 700; letter-spacing: .08em; line-height: 1; }
    .brand-en { font: 600 12px/1.2 sans-serif; letter-spacing: .26em; color: #557075; margin-top: 9px; }
    .dateline { text-align: right; font-size: 14px; line-height: 1.55; letter-spacing: .06em; color: #5f696d; }
    .issue-head { border-bottom: 1px solid #cfd5d1; padding-bottom: 40px; margin-bottom: 42px; }
    .issue-head h1 { font-family: "Noto Serif CJK SC", serif; font-size: 56px; line-height: 1.22; font-weight: 700; letter-spacing: -.02em; margin: 0 0 22px; max-width: 980px; }
    .standfirst { font-family: "Noto Serif CJK SC", serif; font-size: 25px; line-height: 1.7; color: #33434a; margin: 0; max-width: 950px; }
    .numbers { display: flex; gap: 24px; margin-top: 26px; color: #657278; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; }
    .numbers b { color: #1d5158; font-size: 19px; margin-right: 5px; }
    .story { break-inside: avoid-page; page-break-inside: avoid; }
    .story-meta { font-size: 13px; font-weight: 600; letter-spacing: .06em; color: #577176; text-transform: uppercase; margin-bottom: 10px; }
    .story h2 { font-family: "Noto Serif CJK SC", serif; margin: 0; color: #162a30; }
    .story-copy > p { margin: 0; white-space: normal; }
    .lead { border-bottom: 3px solid #173d43; padding-bottom: 44px; margin-bottom: 44px; }
    .lead h2 { font-size: 39px; line-height: 1.28; margin-bottom: 20px; }
    .lead .story-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(260px, .65fr); gap: 44px; align-items: start; }
    .lead .story-copy > p { font-family: "Noto Serif CJK SC", serif; font-size: 23px; line-height: 1.75; }
    .pullquote { margin: 0; border-left: 4px solid #3c7a7c; padding: 8px 0 8px 24px; color: #31555a; }
    .pullquote .quote-mark { font-family: Georgia, serif; font-size: 62px; line-height: .55; color: #78a4a1; }
    .pullquote p { font-family: "Noto Serif CJK SC", serif; font-size: 19px; line-height: 1.68; margin: 10px 0 12px; }
    .pullquote cite { font-style: normal; font-size: 12px; color: #758183; }
    .features { column-count: 2; column-gap: 46px; column-rule: 1px solid #d7d9d5; margin-bottom: 38px; }
    .feature { display: inline-block; width: 100%; break-inside: avoid; padding: 0 0 34px; margin: 0 0 34px; border-bottom: 1px solid #c9cfcc; }
    .feature h2 { font-size: 28px; line-height: 1.35; margin-bottom: 14px; }
    .feature .story-copy > p { font-size: 18px; line-height: 1.7; color: #28373d; }
    .feature .story-grid { display: block; }
    .briefs { display: grid; grid-template-columns: 1fr 1fr; gap: 20px 34px; margin-top: 10px; }
    .brief { border-top: 2px solid #88a4a4; padding-top: 16px; }
    .brief h2 { font-size: 21px; line-height: 1.35; margin-bottom: 9px; }
    .brief .story-copy > p { font-size: 15px; line-height: 1.62; color: #344249; }
    .brief .story-grid { display: block; }
    .source-title { margin-top: 18px; font-size: 12px; line-height: 1.5; color: #526166; }
    .evidence-ref { margin-top: 8px; font: 600 11px/1.5 monospace; color: #42696c; }
    .url-ref { margin-top: 4px; font: 11px/1.45 monospace; color: #7a8587; word-break: break-all; }
    .footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid #aeb6b3; font-size: 10.5px; line-height: 1.55; color: #778083; }
    @media print { a { color: inherit; text-decoration: none; } }
    '''
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>超理日报 {html.escape(date)}</title><style>{css}</style></head>
<body><main class="issue">
<header class="masthead"><div><div class="brand-cn">超理日报</div><div class="brand-en">CHAOLI DAILY</div></div>
<div class="dateline">{_html_text(date)}<br>北京时间 {_html_text(generated)}</div></header>
<section class="issue-head"><h1>{_html_text(editorial.headline)}</h1><p class="standfirst">{_html_text(editorial.standfirst)}</p>
<div class="numbers"><span><b>{len(cards)}</b> active threads</span><span><b>{activity_count}</b> 24h updates</span><span><b>{active_authors}</b> participants</span></div></section>
{lead_html}
<section class="features">{features_html}</section>
<section class="briefs">{briefs_html}</section>
<footer class="footer">{_html_text(source_note + error_note)}</footer>
</main></body></html>'''


def _render_html_pages(out: Path, html_text: str, stem: str) -> tuple[Path, ...]:
    chromium = Path("/usr/lib64/chromium-browser/headless_shell")
    convert = Path("/usr/bin/convert")
    if not chromium.exists() or not convert.exists():
        raise RuntimeError("HTML report renderer missing Chromium headless or ImageMagick")
    html_path = out / f"{stem}.html"
    pdf_path = out / f"{stem}.pdf"
    html_path.write_text(html_text, encoding="utf-8")
    subprocess.run(
        [str(chromium), "--no-sandbox", "--disable-gpu", "--hide-scrollbars", f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", html_path.resolve().as_uri()],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
    )
    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        raise RuntimeError("Chromium produced no usable report PDF")
    page_stem = out / f"{stem}-page-%02d.png"
    subprocess.run(
        [str(convert), "-density", "120", str(pdf_path), "-background", "white", "-alpha", "remove", "-alpha", "off", "-quality", "92", str(page_stem)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
    )
    pages = tuple(sorted(out.glob(f"{stem}-page-*.png")))
    if not pages:
        raise RuntimeError("HTML report renderer produced no PNG pages")
    return pages

def _signature(cards: list[ThreadCard], date: str, source: str) -> str:
    payload = {
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


async def build_daily_report(output_dir: Path, cards: list[ThreadCard], date: str, source: str, *, provider=None) -> DailyReportBundle:
    out = Path(output_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    evidence = await collect_daily_evidence(cards)
    summaries = await summarize_daily_topics(provider, evidence)
    editorial = await editorialize_daily(provider, evidence, summaries)
    markdown = _report_markdown(cards, evidence, summaries, date, source)  # audit trail only; never rendered
    html_text = _render_issue_html(cards, evidence, summaries, editorial, date, source)
    sig = _signature(cards, date, source)
    source_path = out / f"chaoli-daily-{date}-{sig}.md"
    source_path.write_text(markdown, encoding="utf-8")
    html_path = out / f"chaoli-daily-{date}-{sig}.html"
    html_path.write_text(html_text, encoding="utf-8")

    manifest_data = {
        "schema": 1,
        "date": date,
        "generated_at": datetime.now(SHANGHAI).isoformat(),
        "source": source,
        "topic_count": len(cards),
        "signature": sig,
        "editorial": {
            "headline": editorial.headline,
            "standfirst": editorial.standfirst,
            "error": editorial.error,
            "blocks": [
                {"level": x.level, "thread_ids": list(x.thread_ids), "headline": x.headline, "body": x.body}
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
                "summary": next((x.text for x in summaries if x.thread_id == item.card.thread_id), ""),
                "summary_evidence_floors": list(next((x.evidence_floors for x in summaries if x.thread_id == item.card.thread_id), ())),
                "summary_error": next((x.error for x in summaries if x.thread_id == item.card.thread_id), ""),
                "first_floor": item.first_floor.number if item.first_floor else None,
                "activity_floors_24h": [floor.number for floor in item.activity_floors],
                "latest_floors": [floor.number for floor in item.latest_floors],
            }
            for item in evidence
        ],
    }
    manifest = out / f"chaoli-daily-{date}-{sig}.json"
    manifest.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    render_stem = f"chaoli-daily-{date}-{sig}-{hashlib.sha256(html_text.encode('utf-8')).hexdigest()[:10]}"
    pages = await asyncio.to_thread(_render_html_pages, out, html_text, render_stem)
    return DailyReportBundle(
        date, source, tuple(cards), tuple(evidence), tuple(summaries), editorial, markdown, html_text, tuple(pages), manifest
    )
