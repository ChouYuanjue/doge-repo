from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from data.plugins.doge_shared.chaoli import ChaoliError, ChaoliService, Floor, ThreadCard
from data.plugins.doge_shared.markdown_typeset import render_markdown

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
class DailyReportBundle:
    date: str
    source: str
    cards: tuple[ThreadCard, ...]
    evidence: tuple[DailyTopicEvidence, ...]
    summaries: tuple[DailyTopicSummary, ...]
    markdown: str
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
            resp = await provider.text_chat(
                prompt=prompt,
                system_prompt=system,
                temperature=0.0,
                max_tokens=min(2200, 420 + 420 * len(batch)),
                request_max_retries=1,
                thinking={"type": "disabled"},
                response_format={"type": "json_object"},
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
    markdown = _report_markdown(cards, evidence, summaries, date, source)
    sig = _signature(cards, date, source)
    source_path = out / f"chaoli-daily-{date}-{sig}.md"
    source_path.write_text(markdown, encoding="utf-8")

    manifest_data = {
        "schema": 1,
        "date": date,
        "generated_at": datetime.now(SHANGHAI).isoformat(),
        "source": source,
        "topic_count": len(cards),
        "signature": sig,
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

    pages, _backend = await asyncio.to_thread(
        render_markdown,
        out,
        markdown,
        "doc",
        205.0,
        12,
    )
    return DailyReportBundle(date, source, tuple(cards), tuple(evidence), tuple(summaries), markdown, tuple(pages), manifest)
