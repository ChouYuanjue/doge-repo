from __future__ import annotations

import json
import re
from pathlib import Path

from .markdown_typeset import _check_cjk, _compile
from .typeset import TypesetError, _out_dir, _token

# Dedicated Help visual language. This intentionally does not reuse the generic
# /md card theme: Help is product UI, not a Markdown document screenshot.
_BG = "081018"
_PANEL = "0d1722"
_PANEL_ALT = "101c29"
_CODE_BG = "07121c"
_BORDER = "203247"
_FG = "dce7f3"
_MUTED = "8190a5"
_CYAN = "56d4dd"
_GREEN = "7ee787"
_VIOLET = "bd93f9"
_AMBER = "e3b341"
_RED = "ff7b72"

_SECTION_LABELS = {
    "GROUPS": "功能分组",
    "QUICK START": "快速入口",
    "SCALE": "能力规模",
    "SYNTAX": "语法",
    "COMMANDS": "指令",
    "SUBCOMMANDS": "子功能",
    "FUNCTIONS": "功能",
    "DIRECT": "直接用法",
    "ABOUT": "说明",
    "PARAMETERS": "参数",
    "INPUTS": "附加输入",
    "EXAMPLES": "示例",
    "ALIASES": "兼容写法",
    "NEXT": "继续探索",
    "BACK": "返回",
    "STATUS": "状态",
    "BROWSE": "浏览",
    "DETAIL": "详情",
    "HISTORICAL USAGE": "历史用法",
    "HISTORICAL SUBFEATURES": "历史子功能",
}
_SECTION_SET = set(_SECTION_LABELS)
_TITLE_RE = re.compile(r"^(COMMAND|GROUP|LEGACY(?: STATE)?)\s+(.*)$")
_GROUP_RE = re.compile(r"^\s{2}([a-z][a-z0-9_-]*)\s+(\d+)\s{2}(.+)$")
_COMMAND_SUMMARY_RE = re.compile(r"^\s{2}(/\S+)\s+(\d+)\s{2}(.+)$")
_NAMED_RE = re.compile(r"^\s{2}([A-Za-z0-9_+.#-]+)\s{2,}(.+)$")
_TRAILING_NUMBER_RE = re.compile(r"^\s{2}(.+?)\s{2,}(\d+)(?:\s{2}(.+))?$")
_STATUS_RE = re.compile(r"^\s{2}([a-z][a-z0-9_-]*)\s+(.+)$")


def _q(text: str) -> str:
    return json.dumps(str(text), ensure_ascii=False)


def _split_help(text: str) -> tuple[str, list[str], list[tuple[str, list[str]]]]:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    if not lines:
        return "Doge Help", [], []
    title = lines[0].strip() or "Doge Help"
    intro: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for raw in lines[1:]:
        stripped = raw.strip()
        if stripped in _SECTION_SET:
            current = (stripped, [])
            sections.append(current)
            continue
        if current is None:
            if stripped:
                intro.append(stripped)
        else:
            current[1].append(raw.rstrip())
    return title, intro, sections


def _command_tokens(command: str) -> str:
    parts = command.strip().split()
    rendered: list[str] = []
    for i, token in enumerate(parts):
        if i == 0 and token.startswith("/"):
            color = "green"
        elif token.startswith("<") or token.endswith(">"):
            color = "amber"
        elif token.startswith("[") or token.endswith("]") or token.startswith("{") or token.endswith("}") or "|" in token:
            color = "violet"
        else:
            color = "cyan"
        rendered.append(f'#ctok({_q(token)}, color: {color})')
    return "#h(3.2pt)".join(rendered) if rendered else '#tx("", fill: muted)'


def _command_line(command: str, *, prompt: str = "›", compact: bool = False) -> str:
    size = "8.6pt" if compact else "9.1pt"
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 6pt), radius: 4pt, '
        'fill: codebg, stroke: 0.45pt + border)['
        f'#grid(columns: (auto, 1fr), gutter: 7pt, align: (left, horizon))'
        f'[#tx({_q(prompt)}, fill: muted, size: {size}, weight: "bold")]'
        f'[{_command_tokens(command)}]'
        ']'
    )


def _group_row(key: str, count: str, title: str, desc: str = "") -> str:
    below = f'#v(2.5pt)#tx({_q(desc)}, fill: muted, size: 8.8pt)' if desc else ""
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 7pt), radius: 5pt, fill: panel2)['
        '#grid(columns: (62pt, 30pt, 1fr), gutter: 7pt, align: (left, horizon))'
        f'[#pill({_q(key)}, color: cyan)]'
        f'[#tx({_q(count)}, fill: violet, size: 9pt, weight: "bold")]'
        f'[#tx({_q(title)}, fill: fg, size: 9.7pt, weight: "semibold")]'
        f'{below}]'
    )


def _group_tile(key: str, count: str, title: str, desc: str = "") -> str:
    desc_src = f'#v(2.5pt)#tx({_q(desc)}, fill: muted, size: 8.15pt)' if desc else ""
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 7pt), radius: 5pt, '
        'fill: panel2, stroke: 0.35pt + border)['
        '#grid(columns: (1fr, auto), gutter: 6pt, align: (left, horizon))'
        f'[#pill({_q(key)}, color: cyan)]'
        f'[#tx({_q(count)}, fill: violet, size: 8.7pt, weight: "bold")]'
        '#v(4pt)'
        f'#tx({_q(title)}, fill: fg, size: 9.3pt, weight: "semibold")'
        f'{desc_src}]'
    )


def _summary_row(command: str, count: str, desc: str) -> str:
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 7pt), radius: 5pt, fill: panel2)['
        '#grid(columns: (105pt, 28pt, 1fr), gutter: 7pt, align: (left, horizon))'
        f'[{_command_tokens(command)}]'
        f'[#tx({_q(count)}, fill: violet, size: 8.8pt, weight: "bold")]'
        f'[#tx({_q(desc)}, fill: fg, size: 8.9pt)]'
        ']'
    )


def _function_row(name: str, desc: str, usage: str = "") -> str:
    use = f'#v(5pt){_command_line(usage, prompt="$", compact=True)}' if usage else ""
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 7pt), radius: 5pt, '
        'fill: panel2, stroke: 0.35pt + border)['
        '#grid(columns: (82pt, 1fr), gutter: 8pt, align: (left, top))'
        f'[#pill({_q(name)}, color: cyan)]'
        f'[#tx({_q(desc)}, fill: fg, size: 9pt)]'
        f'{use}]'
    )


def _stat_row(label: str, value: str, detail: str = "") -> str:
    detail_part = f'#h(5pt)#tx({_q(detail)}, fill: muted, size: 8.2pt)' if detail else ""
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 5pt), radius: 4pt, fill: panel2)['
        '#grid(columns: (1fr, auto), gutter: 8pt, align: (left, horizon))'
        f'[#tx({_q(label)}, fill: muted, size: 8.9pt)]'
        f'[#tx({_q(value)}, fill: green, size: 11pt, weight: "bold")' + detail_part + ']'
        ']'
    )


def _stat_tile(label: str, value: str, detail: str = "") -> str:
    detail_src = f'#v(2pt)#tx({_q(detail)}, fill: muted, size: 7.8pt)' if detail else ""
    return (
        '#block(width: 100%, inset: (x: 9pt, y: 7pt), radius: 5pt, '
        'fill: panel2, stroke: 0.35pt + border)['
        f'#tx({_q(value)}, fill: green, size: 14pt, weight: "bold")'
        '#v(2pt)'
        f'#tx({_q(label)}, fill: muted, size: 8.3pt, weight: "medium")'
        f'{detail_src}]'
    )


def _status_row(name: str, rest: str) -> str:
    status_color = {
        "migrated": "green",
        "archived": "violet",
        "retired": "muted",
        "offline": "amber",
        "broken": "red",
        "sealed": "cyan",
    }.get(name, "cyan")
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 5.5pt), radius: 4pt, fill: panel2)['
        '#grid(columns: (76pt, 1fr), gutter: 8pt, align: (left, horizon))'
        f'[#pill({_q(name)}, color: {status_color})]'
        f'[#tx({_q(rest)}, fill: fg, size: 8.8pt)]'
        ']'
    )


def _parameter_row(name: str, desc: str, *, input_item: bool = False) -> str:
    token = name.strip()
    if input_item:
        color = "green"
        badge = "INPUT"
    elif token.startswith("<") or token.startswith("{"):
        color = "amber"
        badge = "REQ"
    else:
        color = "violet"
        badge = "OPT"
    return (
        '#block(width: 100%, inset: (x: 8pt, y: 6pt), radius: 5pt, '
        'fill: panel2, stroke: 0.35pt + border)['
        '#grid(columns: (34pt, 1fr), gutter: 7pt, align: (left, top))'
        f'[#pill({_q(badge)}, color: {color})]'
        '['
        f'#text(fill: {color}, size: 8.7pt, weight: "bold")[#raw({_q(token)})]'
        + (f'#v(2.8pt)#tx({_q(desc)}, fill: muted, size: 8.3pt)' if desc else '')
        + ']]'
    )


def _plain_line(text: str, *, muted_line: bool = False) -> str:
    fill = "muted" if muted_line else "fg"
    return f'#tx({_q(text.strip())}, fill: {fill}, size: 9pt)'


def _render_group_grid(rows: list[str]) -> str | None:
    cards: list[str] = []
    i = 0
    while i < len(rows):
        raw = rows[i]
        if not raw.strip():
            i += 1
            continue
        m = _GROUP_RE.match(raw)
        if not m:
            return None
        desc = ""
        if i + 1 < len(rows) and len(rows[i + 1]) - len(rows[i + 1].lstrip(" ")) >= 4:
            desc = rows[i + 1].strip()
            i += 1
        cards.append(_group_tile(m.group(1), m.group(2), m.group(3), desc))
        i += 1
    if not cards:
        return None
    return '#grid(columns: (1fr, 1fr), gutter: 5pt)' + ''.join(f'[{card}]' for card in cards)


def _render_quick_terminal(rows: list[str]) -> str | None:
    entries: list[str] = []
    i = 0
    while i < len(rows):
        stripped = rows[i].strip()
        if not stripped:
            i += 1
            continue
        if not stripped.startswith("/"):
            return None
        desc = ""
        if i + 1 < len(rows) and rows[i + 1].strip() and not rows[i + 1].strip().startswith("/"):
            desc = rows[i + 1].strip()
            i += 1
        desc_src = f'#v(1.5pt)#block(inset: (left: 15pt))[#tx({_q(desc)}, fill: muted, size: 8.1pt)]' if desc else ""
        entries.append(
            '#block(width: 100%, inset: (x: 5pt, y: 3.5pt))['
            '#grid(columns: (auto, 1fr), gutter: 6pt, align: (left, horizon))'
            '[#tx("$", fill: green, size: 8.3pt, weight: "bold")]'
            f'[{_command_tokens(stripped)}]'
            f'{desc_src}]'
        )
        i += 1
    if not entries:
        return None
    body = '#v(1pt)'.join(entries)
    return (
        '#block(width: 100%, inset: 7pt, radius: 5pt, fill: codebg, stroke: 0.55pt + border)['
        '#grid(columns: (auto, auto, 1fr), gutter: 5pt, align: (left, horizon))'
        '[#tx("●", fill: red, size: 6pt)][#tx("●", fill: amber, size: 6pt)]'
        '[#align(right)[#tx("shell://help", fill: muted, size: 6.8pt)]]'
        '#v(5pt)'
        f'{body}]'
    )


def _scale_parts(raw: str) -> tuple[str, str, str] | None:
    m = _TRAILING_NUMBER_RE.match(raw)
    if m:
        return m.group(1).strip(), m.group(2), (m.group(3) or "").strip()
    m = re.match(r"^\s{2}(.+?)\s+(\d+)\s{2}(.+)$", raw)
    if m:
        return m.group(1).strip(), m.group(2), m.group(3).strip()
    return None


def _render_scale_grid(rows: list[str]) -> str | None:
    cards: list[str] = []
    for raw in rows:
        if not raw.strip():
            continue
        parts = _scale_parts(raw)
        if parts is None:
            return None
        cards.append(_stat_tile(*parts))
    if not cards:
        return None
    return '#grid(columns: (1fr, 1fr), gutter: 5pt)' + ''.join(f'[{card}]' for card in cards)


def _render_general_rows(name: str, rows: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(rows):
        raw = rows[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        # Root/group summary row plus one indented description line.
        m = _GROUP_RE.match(raw)
        if m and not stripped.startswith("/"):
            desc = ""
            if i + 1 < len(rows) and len(rows[i + 1]) - len(rows[i + 1].lstrip(" ")) >= 4:
                desc = rows[i + 1].strip()
                i += 1
            out.append(_group_row(m.group(1), m.group(2), m.group(3), desc))
            i += 1
            continue

        # Category command summary: /paper 14 description.
        m = _COMMAND_SUMMARY_RE.match(raw)
        if m:
            out.append(_summary_row(m.group(1), m.group(2), m.group(3)))
            i += 1
            continue

        # Concrete command usage.
        if stripped.startswith("/"):
            out.append(_command_line(stripped, prompt="$" if name == "QUICK START" else "›"))
            # Quick Start descriptions are indented directly below commands.
            if i + 1 < len(rows) and rows[i + 1].strip() and not rows[i + 1].strip().startswith("/"):
                next_indent = len(rows[i + 1]) - len(rows[i + 1].lstrip(" "))
                if next_indent >= 4:
                    out.append(f'#block(inset: (left: 17pt, right: 4pt))[#tx({_q(rows[i + 1].strip())}, fill: muted, size: 8.6pt)]')
                    i += 1
            i += 1
            continue

        # Parameter/input rows are semantic registry metadata: the primary line
        # is the token, the deeper line is its human explanation.
        if name in {"PARAMETERS", "INPUTS"} and raw.startswith("  "):
            token = stripped
            desc = ""
            if i + 1 < len(rows):
                next_indent = len(rows[i + 1]) - len(rows[i + 1].lstrip(" "))
                if next_indent >= 4 and rows[i + 1].strip():
                    desc = rows[i + 1].strip()
                    i += 1
            out.append(_parameter_row(token, desc, input_item=name == "INPUTS"))
            i += 1
            continue

        # Named subcommand plus nested concrete usage.
        m = _NAMED_RE.match(raw)
        if m and name not in {"SCALE", "STATUS", "SYNTAX"}:
            usage = ""
            if i + 1 < len(rows) and rows[i + 1].strip().startswith("/"):
                usage = rows[i + 1].strip()
                i += 1
            out.append(_function_row(m.group(1), m.group(2), usage))
            i += 1
            continue

        # Numeric scale entries.
        if name == "SCALE":
            m = _TRAILING_NUMBER_RE.match(raw)
            if m:
                out.append(_stat_row(m.group(1).strip(), m.group(2), m.group(3) or ""))
                i += 1
                continue
            # Handles forms like "正式调用形式 449 （含 254 个兼容别名）".
            m2 = re.match(r"^\s{2}(.+?)\s+(\d+)\s{2}(.+)$", raw)
            if m2:
                out.append(_stat_row(m2.group(1).strip(), m2.group(2), m2.group(3).strip()))
                i += 1
                continue

        if name == "STATUS":
            m = _STATUS_RE.match(raw)
            if m:
                out.append(_status_row(m.group(1), m.group(2)))
                i += 1
                continue

        # Syntax lines are slightly terminal-like, but remain readable Chinese.
        if name == "SYNTAX":
            out.append(
                '#block(width: 100%, inset: (x: 8pt, y: 5pt))['
                '#grid(columns: (10pt, 1fr), gutter: 6pt, align: (left, top))'
                '[#tx("·", fill: cyan, size: 10pt, weight: "bold")]'
                f'[#tx({_q(stripped)}, fill: fg, size: 8.8pt)]'
                ']'
            )
            i += 1
            continue

        out.append(_plain_line(stripped, muted_line=stripped.startswith("说明：")))
        i += 1
    return out


def build_help_card_source(text: str) -> str:
    title, intro, sections = _split_help(text)
    match = _TITLE_RE.match(title)
    if match:
        hero_tag = match.group(1)
        hero_title = match.group(2)
    else:
        hero_tag = "DOGE // HELP"
        hero_title = title

    hero_intro = "#v(5pt)".join(f'#tx({_q(x)}, fill: muted, size: 9.2pt)' for x in intro)
    if hero_intro:
        hero_intro = "#v(7pt)" + hero_intro

    section_blocks: list[str] = []
    is_root = title.strip() in {"Doge Help", "Doge CLI"}
    for name, rows in sections:
        # Root help is a dashboard, not a long man page.  Compact two-column
        # groups/statistics and a terminal-like quick-start block keep it mobile.
        compact = None
        if is_root and name == "GROUPS":
            compact = _render_group_grid(rows)
        elif is_root and name == "QUICK START":
            compact = _render_quick_terminal(rows)
        elif is_root and name == "SCALE":
            compact = _render_scale_grid(rows)
        if compact is not None:
            body = compact
        else:
            body_rows = _render_general_rows(name, rows)
            if not body_rows:
                continue
            body = "#v(4.5pt)".join(body_rows)
        section_blocks.append(
            f'#section({_q(_SECTION_LABELS.get(name, name))}, {_q(name)})[{body}]'
        )

    sections_src = "#v(9pt)".join(section_blocks)
    return f'''#set page(width: 15cm, height: auto, margin: 0pt, fill: rgb("{_BG}"))
#set text(size: 10pt, fill: rgb("{_FG}"))
#set par(justify: false, leading: 0.68em, spacing: 0.55em)

#let bg = rgb("{_BG}")
#let panel = rgb("{_PANEL}")
#let panel2 = rgb("{_PANEL_ALT}")
#let codebg = rgb("{_CODE_BG}")
#let border = rgb("{_BORDER}")
#let fg = rgb("{_FG}")
#let muted = rgb("{_MUTED}")
#let cyan = rgb("{_CYAN}")
#let green = rgb("{_GREEN}")
#let violet = rgb("{_VIOLET}")
#let amber = rgb("{_AMBER}")
#let red = rgb("{_RED}")

#let tx(s, fill: fg, size: 10pt, weight: "regular") = text(fill: fill, size: size, weight: weight, s)
#let pill(s, color: cyan) = box(
  inset: (x: 5pt, y: 2.1pt), radius: 3pt,
  fill: codebg, stroke: 0.45pt + border,
)[#text(fill: color, size: 7.8pt, weight: "bold")[#raw(s)]]
#let ctok(s, color: cyan) = box(
  inset: (x: 3.2pt, y: 1.1pt), radius: 2.2pt,
  fill: codebg,
)[#text(fill: color, size: 8.3pt, weight: "medium")[#raw(s)]]
#let section(title, tag, body) = block(
  width: 100%, inset: 11pt, radius: 7pt,
  fill: panel, stroke: 0.6pt + border,
)[
  #grid(columns: (1fr, auto), gutter: 8pt, align: (left, horizon))[
    #tx(title, fill: fg, size: 11.5pt, weight: "bold")
  ][
    #pill(tag, color: violet)
  ]
  #v(7pt)
  #body
]

#block(width: 100%, inset: (x: 15pt, y: 14pt))[
  #grid(columns: (1fr, auto), gutter: 10pt, align: (left, horizon))[
    #tx({_q(hero_tag)}, fill: cyan, size: 8pt, weight: "bold")
  ][
    #tx("registry://doge/v5", fill: muted, size: 7.3pt)
  ]
  #v(7pt)
  #tx({_q(hero_title)}, fill: fg, size: 20pt, weight: "bold")
  {hero_intro}
  #v(10pt)
  #line(length: 100%, stroke: 0.85pt + cyan)
  #v(3pt)
  #line(length: 42%, stroke: 0.45pt + violet)
  #v(11pt)
  {sections_src}
  #v(10pt)
  #grid(columns: (1fr, auto), align: (left, horizon))[
    #tx("DOGE CLI", fill: muted, size: 7pt, weight: "bold")
  ][
    #tx("LOCAL TYPESET // LIVE REGISTRY", fill: muted, size: 6.8pt)
  ]
]
'''


def render_geek_help_card(output_dir: Path, text: str, *, ppi: float = 210.0) -> Path:
    source_text = (text or "").strip()
    if not source_text:
        raise TypesetError("Help 内容不能为空")
    if len(source_text) > 24000:
        raise TypesetError("Help 内容过长，无法作为单页卡片")
    _check_cjk(source_text)
    src = build_help_card_source(source_text)
    data = _compile(src, fmt="png", ppi=ppi)
    pages = data if isinstance(data, list) else [data]
    if len(pages) != 1:
        raise TypesetError("Help 卡片必须是单页")
    raw = bytes(pages[0])
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise TypesetError("Help 卡片没有生成有效 PNG")
    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(raw)) as im:
            if im.width > 5000 or im.height > 14000:
                raise TypesetError("Help 卡片尺寸异常")
    except TypesetError:
        raise
    except Exception:
        pass
    path = _out_dir(Path(output_dir)) / f"help-{_token('geek-help-v1', source_text)}.png"
    path.write_bytes(raw)
    return path
