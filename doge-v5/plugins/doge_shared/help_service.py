from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("resources") / "help_catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _lines_for_entry(title: str, entry: dict) -> list[str]:
    lines = [title, entry.get("summary", "").strip()]
    usage = entry.get("usage") or []
    if usage:
        lines += ["", "用法：", *[f"  {x}" for x in usage]]
    examples = entry.get("examples") or []
    if examples:
        lines += ["", "例子：", *[f"  {x}" for x in examples]]
    notes = entry.get("notes") or []
    if notes:
        lines += ["", *[f"注：{x}" for x in notes]]
    return lines


def render_help(topic: str = "") -> tuple[str, bool]:
    """Return help text and whether Markdown is useful on capable transports."""
    c = load_catalog()
    topic = " ".join((topic or "").strip().lower().split())
    categories = {x["id"]: x for x in c["categories"]}
    commands = c["commands"]
    subtopics = c.get("subtopics", {})
    # A few natural aliases; these are help-only, never AstrBot command aliases.
    aliases = {
        "科研": "research", "研究": "research", "research": "research",
        "计算": "compute", "ai": "ai", "cs": "cs",
        "排版": "create", "创作": "create", "create": "create",
        "语言": "language", "语言学": "language",
        "游戏": "play", "play": "play",
        "图片": "media", "媒体": "media",
        "管理": "admin", "状态": "start"
    }
    topic = aliases.get(topic, topic)
    if not topic:
        lines = ["Doge Help", c["intro"], ""]
        for cat in c["categories"]:
            cmds = " ".join("/" + x for x in cat["commands"])
            lines.append(f"{cat['id']:<8}  {cat['title']}  ·  {cmds}")
        lines += ["", "例：/help research · /help game · /help game mine"]
        return "\n".join(lines), True
    if topic in categories:
        cat = categories[topic]
        lines = [cat["title"], cat["summary"], ""]
        for cmd in cat["commands"]:
            entry = commands.get(cmd, {})
            lines.append(f"/{cmd}  {entry.get('summary','')}")
        lines += ["", f"继续：/help {cat['commands'][0]} 或 /help <上面的指令>"]
        return "\n".join(lines), True
    if topic in subtopics:
        return "\n".join(_lines_for_entry(topic, subtopics[topic])), True
    if topic in commands:
        return "\n".join(_lines_for_entry("/" + topic, commands[topic])), True
    # Try longest known prefix so `/help game minesweeper` can fail gracefully.
    head = topic.split()[0] if topic else ""
    if head in commands:
        lines = _lines_for_entry("/" + head, commands[head])
        lines += ["", f"没有 `{topic}` 这个帮助子项。先看 /help {head}。"]
        return "\n".join(lines), True
    return f"没有找到 `{topic}`。用 /help 查看分类。", False
