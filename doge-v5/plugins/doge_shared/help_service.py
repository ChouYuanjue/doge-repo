from __future__ import annotations

from collections import Counter, defaultdict

from .capabilities import (
    counts,
    formal_operations,
    legacy_operations,
    operations_for_prefix,
    registry,
    suggestions,
)

CATEGORY_ALIASES = {
    "start": "system", "状态": "system", "开始": "system", "系统": "system",
    "科研": "research", "研究": "research",
    "计算": "compute", "计算机": "compute",
    "排版": "create", "创作": "create", "工程": "create",
    "语言": "language", "语言学": "language",
    "游戏": "play", "玩": "play",
    "图片": "media", "媒体": "media",
    "管理": "admin", "历史": "legacy", "旧版": "legacy",
}

GROUP_LABELS = {
    "game 24": "24 点", "game nc": "九子棋", "game signal": "Signal 解密",
    "game mine": "扫雷", "game sudoku": "数独", "game dice": "桌面骰池",
    "lang tangut": "西夏文双向翻译 / 字典 / 拟音 / 渲染",
    "lang cthuvian": "R'lyehian / Cthuvian",
    "lang han": "汉字历史音系 / 方言", "lang rrpl": "RRPL · 递归部件语法 / 解释 / 渲染",
    "math formal": "Lean / Coq(Rocq) / Rzk 轻量形式化入口",
    "eng circuit": "电路", "eng control": "经典控制",
    "mat crystal": "真实 CIF / XRD", "media trace": "动漫 / Gal 识图",
    "media mirage": "幻影坦克", "lab fractal": "分形", "lab number": "数论图形",
    "arena chaos": "原 /wp 多能力组合", "arena fight": "原味弱能力直接对决",
}


def _norm(topic: str) -> str:
    t = " ".join((topic or "").strip().lower().split())
    return t[1:] if t.startswith("/") else t


def _alias_note(op: dict) -> str:
    aliases = op.get("aliases") or []
    if not aliases:
        return ""
    shown = aliases[:8]
    text = "  " + "\n  ".join("/" + x for x in shown)
    if len(aliases) > len(shown):
        text += f"\n  … 另有 {len(aliases)-len(shown)} 个兼容写法"
    return text


def _relative(path: str, prefix: str) -> str:
    if path == prefix:
        return "(direct)"
    return path[len(prefix):].strip()


def _argument_help_lines(op: dict) -> list[str]:
    lines: list[str] = []
    params = op.get("parameters") or []
    if params:
        lines += ["", "PARAMETERS"]
        for item in params:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "<arg>")
            desc = str(item.get("description") or "").strip()
            lines.append(f"  {name}")
            if desc:
                lines.append(f"    {desc}")
    inputs = op.get("inputs") or []
    if inputs:
        lines += ["", "INPUTS"]
        for item in inputs:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "<input>")
            required = bool(item.get("required", True))
            desc = str(item.get("description") or "").strip()
            lines.append(f"  {name}  {'必需' if required else '可选'}")
            if desc:
                lines.append(f"    {desc}")
    examples = [str(x).strip() for x in (op.get("examples") or []) if str(x).strip()]
    if examples:
        lines += ["", "EXAMPLES"]
        lines.extend(f"  {x}" for x in examples)
    return lines


def _prefix_groups(prefix: str, ops: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    direct: list[dict] = []
    plen = len(prefix.split())
    for op in ops:
        toks = op["path"].split()
        if len(toks) <= plen:
            direct.append(op)
        else:
            groups[" ".join(toks[: plen + 1])].append(op)
    return dict(groups), direct


def _category_function_count(commands: list[str]) -> int:
    tops = set(commands)
    return sum(1 for op in formal_operations() if op["path"].split()[0] in tops)


def _render_root() -> str:
    d = registry(); c = counts()
    lines = [
        "Doge CLI",
        "",
        "USAGE",
        "  /help <group>",
        "  /help <command>",
        "  /help <command> <subcommand>",
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
        "  /help research        论文与真实科研数据源",
        "  /help compute         CS / AI / 数学 / 代码",
        "  /help lang            Language Lab",
        "  /help lang tangut     西夏文双向翻译、拟音、字典和渲染",
        "  /help game            全部游戏",
        "  /help lab             全部科学小实验",
        "  /help legacy          历史功能状态",
        "",
        "SCALE",
        f"  顶层指令       {c['top_level']}",
        f"  正式叶子功能   {c['functions']}",
        f"  正式调用形式   {c['forms']}  （含 {c['aliases']} 个兼容别名）",
        f"  Legacy 叶子    {c['legacy_functions']}",
        "",
        "SYNTAX",
        "  <arg> 必填    [arg] 可选    {a|b} 必选其一    [{a|b}] 可选其一",
        "  [arg ...] 可重复    + <附件> 表示同一条消息附带的非文本输入",
        "  帮助只推荐 canonical 写法；旧别名仍可调用，但统计会归一到同一个功能。",
        "  `/` 同时是唤醒符；没有命中本表的 `/anything` 不会被算作指令。",
    ]
    return "\n".join(lines)


def _render_category(cat_id: str) -> str:
    d = registry(); cat = next(x for x in d["categories"] if x["id"] == cat_id)
    lines = [f"GROUP  {cat_id}", cat["title"], cat["summary"], "", "COMMANDS"]
    for cmd in cat["commands"]:
        meta = d["commands"].get(cmd, {})
        ops = operations_for_prefix(cmd)
        lines.append(f"  /{cmd:<11} {len(ops):>3}  {meta.get('summary','')}")
    lines += ["", "NEXT", f"  /help {cat['commands'][0]}", "  /help"]
    return "\n".join(lines)


def _render_prefix(prefix: str) -> str:
    d = registry(); ops = operations_for_prefix(prefix)
    if not ops:
        raise KeyError(prefix)
    top = prefix.split()[0]
    summary = GROUP_LABELS.get(prefix) or (d["commands"].get(top, {}).get("summary", "") if prefix == top else "")
    groups, direct = _prefix_groups(prefix, ops)
    lines = [f"COMMAND  /{prefix}"]
    if summary:
        lines.append(summary)
    lines.append("")

    # A true leaf gets a compact man-page view.
    exact = next((x for x in ops if x["path"] == prefix), None)
    if exact and len(ops) == 1:
        lines += ["USAGE", f"  {exact['usage']}"]
        lines += _argument_help_lines(exact)
        lines += ["", "ABOUT", f"  {exact['summary']}"]
        aliases = _alias_note(exact)
        if aliases:
            lines += ["", "ALIASES", aliases]
        parent = " ".join(prefix.split()[:-1])
        lines += ["", "BACK", f"  /help {parent}" if parent else "  /help"]
        return "\n".join(lines)

    if direct:
        lines += ["DIRECT"]
        for op in direct:
            lines.append(f"  {op['usage']}")
            lines.append(f"    {op['summary']}")
        lines.append("")

    if groups:
        lines += ["SUBCOMMANDS"]
        for child, child_ops in groups.items():
            rel = child.split()[-1]
            label = GROUP_LABELS.get(child, "")
            if len(child_ops) == 1:
                op = child_ops[0]
                desc = label or op["summary"]
                lines.append(f"  {rel:<16} {desc}")
                lines.append(f"    {op['usage']}")
            else:
                desc = label or child_ops[0]["summary"]
                lines.append(f"  {rel:<16} {len(child_ops):>2} 功能  {desc}")
        first = next(iter(groups))
        lines += ["", "NEXT", f"  /help {first}"]
    elif not direct:
        lines += ["FUNCTIONS"]
        for op in ops:
            lines.append(f"  {op['usage']}")
            lines.append(f"    {op['summary']}")
    parent = " ".join(prefix.split()[:-1])
    lines += ["", "BACK", f"  /help {parent}" if parent else "  /help"]
    return "\n".join(lines)


def _legacy_state_counts() -> Counter:
    commands = ((registry().get("legacy") or {}).get("commands") or {})
    return Counter(x.get("state", "legacy") for x in commands.values())


def _render_legacy(topic: str = "") -> str:
    d = registry(); legacy = d.get("legacy") or {}; commands = legacy.get("commands", {})
    ops = legacy_operations(); c = counts(); t = _norm(topic)
    states = _legacy_state_counts()
    if not t:
        lines = [
            "LEGACY  Doge v2-v4 历史博物馆",
            legacy.get("summary", ""),
            "",
            "STATUS",
        ]
        for state, n in sorted(states.items()):
            leaves = sum(1 for op in ops if op.get("state") == state)
            lines.append(f"  {state:<10} {n:>2} 入口 / {leaves:>2} 叶子功能")
        lines += [
            "",
            "SCALE",
            f"  历史顶层入口   {c['legacy_top_level']}",
            f"  历史叶子功能   {c['legacy_functions']}",
            "",
            "BROWSE",
            "  /help legacy retired",
            "  /help legacy archived",
            "  /help legacy offline",
            "  /help legacy gpt",
            "  /help legacy gan",
            "  /help legacy mc",
            "",
            "说明：Legacy 默认不加载；这里的‘存在’表示历史语义已被收容，不等于当前正式 profile 可执行。",
        ]
        return "\n".join(lines)

    if t in states:
        rows = [(cmd, meta) for cmd, meta in commands.items() if meta.get("state") == t]
        lines = [f"LEGACY STATE  {t}", f"{len(rows)} 个历史入口", "", "COMMANDS"]
        for cmd, meta in rows:
            leaf_n = sum(1 for op in ops if op["path"] == cmd or op["path"].startswith(cmd + " "))
            lines.append(f"  /{cmd:<12} {leaf_n:>2}  {meta.get('title','')}")
        lines += ["", "DETAIL", f"  /help legacy {rows[0][0]}" if rows else "  /help legacy", "", "BACK", "  /help legacy"]
        return "\n".join(lines)

    parts = t.split()
    cmd = parts[0]
    if cmd not in commands:
        raise KeyError("legacy " + t)
    meta = commands[cmd]
    cmd_ops = [op for op in ops if op["path"] == cmd or op["path"].startswith(cmd + " ")]
    if len(parts) > 1:
        path = " ".join(parts)
        leaf = next((op for op in cmd_ops if op["path"] == path), None)
        if leaf:
            return "\n".join([
                f"LEGACY  /{leaf['path']}",
                f"状态：{leaf.get('state', meta.get('state','legacy'))}",
                "",
                "HISTORICAL USAGE",
                f"  {leaf['usage']}",
                "",
                "ABOUT",
                f"  {leaf['summary']}",
                "",
                "BACK",
                f"  /help legacy {cmd}",
            ])
    lines = [
        f"LEGACY  /{cmd}",
        f"状态：{meta.get('state','legacy')}",
        f"原功能：{meta.get('title','')}",
        "",
        meta.get("note", ""),
    ]
    if len(cmd_ops) > 1 or (cmd_ops and cmd_ops[0]["path"] != cmd):
        lines += ["", "HISTORICAL SUBFEATURES"]
        for op in cmd_ops:
            rel = op["path"][len(cmd):].strip() or "(direct)"
            lines.append(f"  {rel:<14} {op['summary']}")
    lines += ["", "BACK", "  /help legacy"]
    return "\n".join(lines)


def _alias_prefix_to_canonical(topic: str) -> str | None:
    hits = []
    for op in formal_operations():
        if op.get("kind", "command") != "command":
            continue
        for alias in op.get("aliases", []):
            if alias == topic or alias.startswith(topic + " "):
                ct = op["path"].split(); n = len(topic.split())
                hits.append(" ".join(ct[: min(n, len(ct))]))
    if not hits:
        return None
    return max(set(hits), key=hits.count)


def render_help(topic: str = "") -> tuple[str, bool]:
    t = _norm(topic); d = registry()
    if not t:
        return _render_root(), False
    t = CATEGORY_ALIASES.get(t, t)
    if t == "legacy":
        return _render_legacy(), False
    if t.startswith("legacy "):
        try:
            return _render_legacy(t[7:]), False
        except KeyError:
            pass
    if any(x["id"] == t for x in d["categories"]):
        return _render_category(t), False
    if t in d.get("commands", {}):
        return _render_prefix(t), False
    if operations_for_prefix(t):
        return _render_prefix(t), False
    # `/help gpt` is useful even though Legacy is disabled.
    if t.split()[0] in ((d.get("legacy") or {}).get("commands") or {}):
        try:
            return _render_legacy(t), False
        except KeyError:
            pass
    canonical = _alias_prefix_to_canonical(t)
    if canonical and operations_for_prefix(canonical):
        return "兼容写法已归一到推荐入口：\n\n" + _render_prefix(canonical), False
    sugg = suggestions(t)
    lines = [f"NOT FOUND  /{t}", "", "TRY"]
    for x in sugg:
        lines.append(f"  /help {x}")
    lines += ["", "ROOT", "  /help"]
    return "\n".join(lines), False


def _infer_error_topic(message: str, fallback: str) -> str:
    """Recover the most specific registered command mentioned by an error.

    Many handlers intentionally raise messages such as
    ``用法：/math oeis <数列或关键词>`` when a required argument is missing.
    Those failures happen *before* the invocation can satisfy the normal
    registry matcher, so infer the leaf from any slash form mentioned in the
    error and then let the registry provide the canonical usage/parameters.
    """
    import re

    candidates: list[tuple[int, str]] = []
    lower = (message or "").lower()
    for op in formal_operations():
        if op.get("kind", "command") != "command":
            continue
        for form in [op["path"], *(op.get("aliases") or [])]:
            pattern = r"/" + re.escape(form.lower()) + r"(?=$|[\s<\[{:@|，,；;])"
            if re.search(pattern, lower):
                candidates.append((len(form.split()), op["path"]))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return _norm(fallback)


def format_cli_error(command: str, error: object, topic: str | None = None) -> str:
    """Reusable CLI-style failure with actionable parameter guidance."""
    cmd = _norm(command).split()[0] if _norm(command) else ""
    msg = str(error).strip() or "执行失败"
    target = _norm(topic) if topic else _infer_error_topic(msg, command)
    lines = [f"ERROR  /{cmd}" if cmd else "ERROR", f"  {msg}"]

    exact = None
    if target:
        exact = next((x for x in operations_for_prefix(target) if x["path"] == target), None)
    if exact:
        lines += ["", "USAGE", f"  {exact['usage']}"]
        lines += _argument_help_lines(exact)

    lines += ["", "NEXT"]
    if target:
        lines.append(f"  /help {target}")
    if cmd and target != cmd:
        lines.append(f"  /help {cmd}")
    lines.append("  /help")
    return "\n".join(lines)
