from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from data.plugins.doge_shared.chaoli import ThreadCard


MAX_TRACKED_THREADS = 800


def reply_count(value: str | int | None) -> int | None:
    if isinstance(value, int):
        return max(0, value)
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def card_snapshot(card: ThreadCard) -> dict:
    return {
        "replies": reply_count(card.replies),
        "crc": str(card.crc or ""),
        "title": str(card.title or ""),
        "last_author": str(card.last_author or ""),
        "last_author_id": card.last_author_id,
    }


def primed_channel_state(cards: list[ThreadCard]) -> dict:
    return {
        "max_seen_thread_id": max((card.thread_id for card in cards), default=0),
        "threads": {str(card.thread_id): card_snapshot(card) for card in cards},
    }


@dataclass(frozen=True, slots=True)
class PushEvent:
    kind: str  # new_thread | new_reply
    card: ThreadCard
    previous_replies: int | None = None
    resurfaced: bool = False


def classify_cards(state: dict, cards: list[ThreadCard]) -> tuple[list[PushEvent], dict]:
    """Classify new threads separately from replies to older threads.

    `updated` is deliberately NOT a trigger because Chaoli renders recent times as
    drifting relative text (e.g. 1小时前 -> 2小时前). Reply-count growth is the
    stable signal for already tracked threads. For a previously unseen thread that
    resurfaces after a reply, the monotonic thread-id high-water mark tells us it is
    old rather than newly created.
    """
    old_max = int(state.get("max_seen_thread_id") or 0)
    old_threads = state.get("threads") if isinstance(state.get("threads"), dict) else {}
    threads = {str(k): dict(v) for k, v in old_threads.items() if isinstance(v, dict)}
    events: list[PushEvent] = []
    current_keys: set[str] = set()

    for card in cards:
        key = str(card.thread_id)
        current_keys.add(key)
        current = card_snapshot(card)
        previous = threads.get(key)
        if previous is None:
            if card.thread_id > old_max:
                events.append(PushEvent("new_thread", card))
            else:
                # An older id that was outside our recent-window cache can only
                # re-enter the active list because it became active again.
                events.append(PushEvent("new_reply", card, resurfaced=True))
        else:
            before = reply_count(previous.get("replies"))
            after = reply_count(current.get("replies"))
            if before is not None and after is not None and after > before:
                events.append(PushEvent("new_reply", card, previous_replies=before))
        # Refresh metadata even when only title/CRC/relative-time presentation
        # changed; those changes must not themselves generate a reply push.
        threads[key] = current

    new_max = max([old_max, *(card.thread_id for card in cards)] if cards else [old_max])

    # Bound disk growth. `max_seen_thread_id` remains the durable classification
    # watermark, so a pruned old thread that later resurfaces is still a reply.
    if len(threads) > MAX_TRACKED_THREADS:
        keep = set(current_keys)
        for key in sorted(threads, key=lambda x: int(x) if x.isdigit() else -1, reverse=True):
            if len(keep) >= MAX_TRACKED_THREADS:
                break
            keep.add(key)
        threads = {key: value for key, value in threads.items() if key in keep}

    return events, {"max_seen_thread_id": new_max, "threads": threads}


def _event_block(event: PushEvent) -> str:
    card = event.card
    if event.kind == "new_thread":
        head = f"【新帖】#{card.thread_id} {card.title}"
        meta = []
        if card.channel:
            meta.append(card.channel)
        if card.author:
            meta.append(f"发帖：{card.author}")
        return "\n".join([head, " · ".join(meta), card.url] if meta else [head, card.url])

    head = f"【旧帖新回复】#{card.thread_id} {card.title}"
    meta = []
    if card.channel:
        meta.append(card.channel)
    if card.last_author:
        meta.append(f"最后回复：{card.last_author}")
    after = reply_count(card.replies)
    if event.previous_replies is not None and after is not None:
        meta.append(f"回复 {event.previous_replies}→{after}")
    elif after is not None:
        meta.append(f"当前回复 {after}")
    if card.updated:
        meta.append(f"更新于 {card.updated}")
    return "\n".join([head, " · ".join(meta), card.url] if meta else [head, card.url])


def format_push_message(events: list[PushEvent], *, test: bool = False) -> str:
    new_threads = [event for event in events if event.kind == "new_thread"]
    replies = [event for event in events if event.kind == "new_reply"]
    title = "超理推送测试" if test else "超理 · 新动态"
    sections = [title]
    if new_threads:
        sections.append(f"新帖（{len(new_threads)}）\n" + "\n\n".join(_event_block(x) for x in new_threads))
    if replies:
        sections.append(f"旧帖新回复（{len(replies)}）\n" + "\n\n".join(_event_block(x) for x in replies))
    return "\n\n".join(sections)


class ChaoliPushStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {"schema": 1, "subscriptions": {}}
        self.load_error = ""
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("subscriptions", {}), dict):
                raise ValueError("invalid root")
            self.data = {"schema": 1, "subscriptions": raw.get("subscriptions", {})}
        except Exception as exc:
            self.load_error = type(exc).__name__

    def save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def subscriptions(self) -> dict:
        return copy.deepcopy(self.data.get("subscriptions", {}))

    def channel_state(self, umo: str, slug: str) -> dict | None:
        sub = self.data.get("subscriptions", {}).get(umo, {})
        channels = sub.get("channels", {}) if isinstance(sub, dict) else {}
        value = channels.get(slug) if isinstance(channels, dict) else None
        return copy.deepcopy(value) if isinstance(value, dict) else None

    def enable(self, umo: str, slug: str, cards: list[ThreadCard]) -> str:
        subs = self.data.setdefault("subscriptions", {})
        sub = subs.setdefault(umo, {"channels": {}})
        channels = sub.setdefault("channels", {})
        if slug == "all":
            if set(channels) == {"all"}:
                return "exists"
            channels.clear()
            channels["all"] = primed_channel_state(cards)
            self.save()
            return "enabled"
        if "all" in channels:
            return "covered"
        if slug in channels:
            return "exists"
        channels[slug] = primed_channel_state(cards)
        self.save()
        return "enabled"

    def disable(self, umo: str, slug: str | None = None) -> str:
        subs = self.data.setdefault("subscriptions", {})
        sub = subs.get(umo)
        if not isinstance(sub, dict):
            return "missing"
        channels = sub.get("channels", {})
        if slug is None:
            subs.pop(umo, None)
            self.save()
            return "disabled"
        if not isinstance(channels, dict) or slug not in channels:
            return "covered" if isinstance(channels, dict) and "all" in channels and slug != "all" else "missing"
        channels.pop(slug, None)
        if not channels:
            subs.pop(umo, None)
        self.save()
        return "disabled"

    def update_channel(self, umo: str, slug: str, state: dict, *, save: bool = True) -> None:
        sub = self.data.setdefault("subscriptions", {}).get(umo)
        if not isinstance(sub, dict):
            return
        channels = sub.get("channels")
        if not isinstance(channels, dict) or slug not in channels:
            return
        channels[slug] = copy.deepcopy(state)
        if save:
            self.save()

    def channel_slugs(self, umo: str) -> list[str]:
        sub = self.data.get("subscriptions", {}).get(umo, {})
        channels = sub.get("channels", {}) if isinstance(sub, dict) else {}
        return sorted(str(x) for x in channels) if isinstance(channels, dict) else []
