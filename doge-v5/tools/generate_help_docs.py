from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins" / "doge_shared" / "resources" / "help_catalog.json"
DST = ROOT / "HELP.md"


def generate() -> str:
    c = json.loads(SRC.read_text(encoding="utf-8"))
    lines = ["# Doge v5 command guide", "", c["intro"], ""]
    for cat in c["categories"]:
        lines += [f"## {cat['title']} (`{cat['id']}`)", "", cat["summary"], ""]
        for cmd in cat["commands"]:
            e = c["commands"][cmd]
            lines += [f"### `/{cmd}`", "", e["summary"], ""]
            if e.get("usage"):
                lines += ["用法：", ""] + [f"- `{x}`" for x in e["usage"]] + [""]
            if e.get("examples"):
                lines += ["例子：", ""] + [f"- `{x}`" for x in e["examples"]] + [""]
            if e.get("notes"):
                lines += [x for x in e["notes"]] + [""]
    if c.get("subtopics"):
        lines += ["## 下钻帮助", ""]
        for key,e in c["subtopics"].items():
            lines += [f"### `/help {key}`", "", e["summary"], ""]
            if e.get("usage"):
                lines += ["用法：", ""] + [f"- `{x}`" for x in e["usage"]] + [""]
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    text = generate()
    DST.write_text(text, encoding="utf-8")
    print(DST)
