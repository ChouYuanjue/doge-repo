from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from doge_shared.capabilities import counts, legacy_operations, operations_for_prefix, registry
from doge_shared.help_service import render_help

HELP_DST = ROOT / "HELP.md"
LEGACY_DST = ROOT / "LEGACY.md"


def generate() -> str:
    d = registry()
    lines = [
        "# Doge v5 command guide",
        "",
        "本文件由 `capability_registry.json` 自动生成；运行时 `/help`、功能统计、命令归一化和 Agent 能力认知使用同一份注册表。",
        "",
    ]
    root, _ = render_help("")
    lines += ["```text", root, "```", ""]
    for cat in d["categories"]:
        lines += [f"## {cat['title']} (`{cat['id']}`)", "", cat["summary"], ""]
        for cmd in cat["commands"]:
            text, _ = render_help(cmd)
            lines += [f"### `/{cmd}`", "", "```text", text, "```", ""]
            groups = []
            for op in operations_for_prefix(cmd):
                toks = op["path"].split()
                if len(toks) >= 2:
                    p = " ".join(toks[:2])
                    if p not in groups:
                        groups.append(p)
            for p in groups:
                sub = operations_for_prefix(p)
                if len(sub) > 1:
                    text, _ = render_help(p)
                    lines += [f"#### `/help {p}`", "", "```text", text, "```", ""]
    lines += [
        "## Legacy",
        "",
        "Legacy 默认不加载。完整历史入口、状态和子功能见 [`LEGACY.md`](LEGACY.md)。",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def generate_legacy() -> str:
    d = registry(); legacy = d.get("legacy") or {}; c = counts()
    lines = [
        "# Doge Legacy reference",
        "",
        legacy.get("summary", ""),
        "",
        f"- 历史顶层入口：**{c['legacy_top_level']}**",
        f"- 历史叶子功能：**{c['legacy_functions']}**",
        "- 默认 profile：**不加载**",
        "",
        "这里的‘收容’表示旧功能的用途、入口和迁移状态仍可追溯；`offline` / `broken` / `retired` 等状态不代表当前可以正常执行。",
        "",
    ]
    ops = legacy_operations()
    for cmd, meta in legacy.get("commands", {}).items():
        lines += [
            f"## `/{cmd}` — {meta.get('title','')}",
            "",
            f"状态：`{meta.get('state','legacy')}`",
            "",
            meta.get("note", ""),
            "",
        ]
        cmd_ops = [x for x in ops if x["path"] == cmd or x["path"].startswith(cmd + " ")]
        if cmd_ops:
            lines += ["历史叶子：", ""]
            for op in cmd_ops:
                lines.append(f"- `{op['usage']}` — {op['summary']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_docs() -> None:
    HELP_DST.write_text(generate(), encoding="utf-8")
    LEGACY_DST.write_text(generate_legacy(), encoding="utf-8")
    print(HELP_DST)
    print(LEGACY_DST)


if __name__ == "__main__":
    write_docs()
