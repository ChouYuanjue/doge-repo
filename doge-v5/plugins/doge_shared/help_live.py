from __future__ import annotations

import json
import random
import re
from pathlib import Path
from threading import Lock

from .capabilities import formal_operations, operations_for_prefix, registry
from .help_service import render_help
from .markdown_typeset import render_markdown

_STYLE_ALIASES = {
    "image": "image",
    "img": "image",
    "pic": "image",
    "图片": "image",
    "图": "image",
    "text": "text",
    "txt": "text",
    "plain": "text",
    "文字": "text",
    "文本": "text",
}
_SECTION_LABELS = {
    "GROUPS": "功能分组",
    "QUICK START": "随手看看",
    "SCALE": "能力规模",
    "SYNTAX": "语法说明",
    "COMMANDS": "指令",
    "SUBCOMMANDS": "子功能",
    "FUNCTIONS": "功能",
    "DIRECT": "直接用法",
    "ABOUT": "说明",
    "ALIASES": "兼容写法",
    "NEXT": "继续查看",
    "BACK": "返回",
    "STATUS": "状态",
    "BROWSE": "浏览",
    "DETAIL": "详情",
    "HISTORICAL USAGE": "历史用法",
    "HISTORICAL SUBFEATURES": "历史子功能",
}


def normalize_help_style_topic(topic: str) -> tuple[str, str | None] | None:
    """Parse `/help style ...` without creating a second command namespace."""
    t = " ".join((topic or "").strip().lower().split())
    if not t:
        return None
    parts = t.split()
    if parts[0] not in {"style", "mode", "显示", "样式"}:
        return None
    if len(parts) == 1:
        return "query", None
    mode = _STYLE_ALIASES.get(parts[1])
    if mode is None:
        return "invalid", parts[1]
    return "set", mode


def scope_key(platform: str, group_id: str | None, unified_origin: str) -> tuple[str, str]:
    """Group preferences are isolated per transport; private chats fall back to conversation scope."""
    platform = (platform or "unknown").strip().lower() or "unknown"
    gid = str(group_id or "").strip()
    if gid:
        return f"{platform}:group:{gid}", "当前群"
    return f"{platform}:chat:{unified_origin}", "当前会话"


class HelpPreferenceStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema": 1, "scopes": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema") == 1 and isinstance(data.get("scopes"), dict):
                return data
        except Exception:
            pass
        return {"schema": 1, "scopes": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def get(self, key: str) -> str:
        mode = self._data.get("scopes", {}).get(key, "image")
        return mode if mode in {"image", "text"} else "image"

    def set(self, key: str, mode: str) -> str:
        if mode not in {"image", "text"}:
            raise ValueError("Help 样式只能是 image 或 text")
        with self._lock:
            self._data.setdefault("scopes", {})[key] = mode
            self._save()
        return mode


def _quick_start_candidates() -> dict[int, list[tuple[str, str]]]:
    d = registry()
    by_depth: dict[int, list[tuple[str, str]]] = {1: [], 2: [], 3: [], 4: []}

    for cat in d.get("categories", []):
        by_depth[1].append((cat["id"], cat.get("title", "功能分组")))
    for cmd, meta in d.get("commands", {}).items():
        if cmd != "help":
            by_depth[1].append((cmd, meta.get("summary", "")))

    seen: set[str] = set()
    for op in formal_operations():
        if op.get("kind", "command") != "command":
            continue
        toks = op["path"].split()
        if not toks or toks[0] == "help":
            continue
        max_depth = min(4, len(toks))
        for depth in range(2, max_depth + 1):
            topic = " ".join(toks[:depth])
            if topic in seen or not operations_for_prefix(topic):
                continue
            seen.add(topic)
            desc = op.get("summary", "")
            by_depth[depth].append((topic, desc))
    by_depth[1].append(("legacy", "看看 v2-v4 的历史功能去了哪里"))
    return {k: v for k, v in by_depth.items() if v}


def random_quick_start(rng: random.Random | random.SystemRandom | None = None, count: int = 5) -> list[tuple[str, str]]:
    rng = rng or random.SystemRandom()
    pools = _quick_start_candidates()
    depths = sorted(pools)
    chosen: list[tuple[str, str]] = []
    used: set[str] = set()
    attempts = 0
    while len(chosen) < count and attempts < count * 20:
        attempts += 1
        depth = rng.choice(depths)
        topic, desc = rng.choice(pools[depth])
        if topic in used:
            continue
        used.add(topic)
        chosen.append((topic, desc))
    return chosen


def _category_function_count(commands: list[str]) -> int:
    tops = set(commands)
    return sum(1 for op in formal_operations() if op["path"].split()[0] in tops)


def render_live_root(rng: random.Random | random.SystemRandom | None = None) -> str:
    d = registry()
    from .capabilities import counts

    c = counts()
    lines = [
        "Doge Help",
        "",
        "GROUPS",
    ]
    for cat in d["categories"]:
        fn = _category_function_count(cat["commands"])
        lines.append(f"  {cat['id']:<10} {fn:>3}  {cat['title']}")
        lines.append(f"             {cat['summary']}")
    lines += [
        f"  {'legacy':<10} {c['legacy_functions']:>3}  Legacy / 历史博物馆（默认不加载）",
        "             v2-v4 旧入口、迁移状态与仍可追溯的历史子功能。",
        "",
        "QUICK START",
    ]
    for topic, desc in random_quick_start(rng):
        lines.append(f"  /help {topic}")
        if desc:
            lines.append(f"    {desc}")
    lines += [
        "",
        "SCALE",
        f"  顶层指令       {c['top_level']}",
        f"  正式叶子功能   {c['functions']}",
        f"  正式调用形式   {c['forms']}  （含 {c['aliases']} 个兼容别名）",
        f"  Legacy 叶子    {c['legacy_functions']}",
        "",
        "SYNTAX",
        "  /help 后接分类、指令或子功能即可逐层查看。",
        "  <arg> 必填    [arg] 可选    A|B 任选其一",
        "  /help style image|text  切换当前群的帮助显示；默认 image。",
        "  `/` 同时是唤醒符；没有命中注册表的 `/anything` 不会被算作指令。",
    ]
    return "\n".join(lines)


def render_help_live(topic: str = "", rng: random.Random | random.SystemRandom | None = None) -> tuple[str, bool]:
    t = " ".join((topic or "").strip().split())
    if not t:
        return render_live_root(rng), False
    return render_help(topic)


def help_to_markdown(text: str) -> str:
    """Turn the CLI-oriented plain help into a clean mobile card without losing text-mode fidelity."""
    lines = (text or "").splitlines()
    if not lines:
        return "# Doge Help"
    out = [f"# {lines[0].strip() or 'Doge Help'}"]
    for raw in lines[1:]:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if stripped in _SECTION_LABELS:
            out.extend(["", f"## {_SECTION_LABELS[stripped]}"])
            continue
        if re.fullmatch(r"(?:COMMAND|GROUP|LEGACY(?: STATE)?)\s+.*", stripped):
            out.extend(["", f"## {stripped}"])
            continue
        if line.startswith("  "):
            # Keep command-shaped tokens visually distinct while allowing CJK descriptions to wrap.
            if stripped.startswith("/"):
                parts = re.split(r"\s{2,}", stripped, maxsplit=1)
                cmd = parts[0]
                desc = parts[1] if len(parts) > 1 else ""
                out.append(f"- `{cmd}`" + (f" — {desc}" if desc else ""))
            elif re.match(r"^[a-z][a-z0-9_-]*\s+\d+\s+", stripped):
                parts = re.split(r"\s{2,}", stripped, maxsplit=2)
                out.append("- " + " · ".join(parts))
            else:
                out.append(f"  {stripped}")
            continue
        out.append(stripped)
    return "\n".join(out).strip() + "\n"


def render_help_card(output_dir: Path, text: str) -> Path:
    """Render help locally with the existing Typst/cmarker pipeline; no generative image service is involved."""
    markdown = help_to_markdown(text)
    paths, _ = render_markdown(Path(output_dir), markdown, mode="card", ppi=210.0, max_pages=1)
    return paths[0]
