from __future__ import annotations

import json
import math
from pathlib import Path

_ALLOWED = frozenset("012345678|-()")
_BLOCK_LINES = {
    "1": (0.0, 0.0, 0.5, 0.5),
    "2": (0.5, 0.0, 0.5, 0.5),
    "3": (1.0, 0.0, 0.5, 0.5),
    "4": (1.0, 0.5, 0.5, 0.5),
    "5": (1.0, 1.0, 0.5, 0.5),
    "6": (0.5, 1.0, 0.5, 0.5),
    "7": (0.0, 1.0, 0.5, 0.5),
    "8": (0.0, 0.5, 0.5, 0.5),
}


class RrplError(ValueError):
    pass


def load_reference_dict(path: Path) -> dict[str, str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RrplError("RRPL reference dictionary is invalid")
    return {str(k): str(v) for k, v in raw.items()}


def expand_references(code: str, refs: dict[str, str], max_depth: int = 40) -> str:
    """Expand RRPL single-character references recursively.

    The legacy JS implementation repeatedly replaced all 5k dictionary keys.
    This version follows only references that actually occur in the submitted
    expression, retaining the same textual-substitution semantics while being
    bounded and deterministic.
    """
    if len(code) > 5000:
        raise RrplError("RRPL 代码过长；最多 5000 字符")

    memo: dict[str, str] = {}
    active: set[str] = set()

    def expand_char(ch: str, depth: int) -> str:
        if ch in _ALLOWED:
            return ch
        if ch.isspace():
            return ""
        if ch in memo:
            return memo[ch]
        if ch not in refs:
            raise RrplError(f"未知 RRPL 引用：{ch}")
        if depth > max_depth:
            raise RrplError("RRPL 引用展开层数过深")
        if ch in active:
            raise RrplError(f"RRPL 引用出现循环：{ch}")
        active.add(ch)
        value = "".join(expand_char(c, depth + 1) for c in refs[ch])
        active.remove(ch)
        memo[ch] = value
        return value

    expanded = "".join(expand_char(ch, 0) for ch in code)
    if not expanded or any(ch not in _ALLOWED for ch in expanded):
        raise RrplError("RRPL 展开后包含非法字符")
    if len(expanded) > 200_000:
        raise RrplError("RRPL 引用展开结果过大")
    return expanded


def parse(code: str):
    """Parse pure RRPL into [operator-string, child...] trees.

    '-' packs left-to-right, '|' packs top-to-bottom. Repeated operators define
    equal-width/equal-height slots, matching rrpl_parser.js.
    """
    pos = 0

    def parse_group(stop: str | None = None):
        nonlocal pos
        items: list[object] = []
        ops: list[str] = []
        atom = ""

        def flush_atom() -> None:
            nonlocal atom
            if atom:
                items.append(atom)
                atom = ""

        while pos < len(code):
            ch = code[pos]
            if ch == stop:
                flush_atom()
                pos += 1
                break
            if ch == "(":
                flush_atom()
                pos += 1
                items.append(parse_group(")"))
                continue
            if ch == ")":
                if stop is None:
                    raise RrplError("多余的右括号")
                flush_atom()
                pos += 1
                break
            if ch in "|-":
                flush_atom()
                ops.append(ch)
                pos += 1
                continue
            if ch in "012345678":
                atom += ch
                pos += 1
                continue
            raise RrplError(f"非法 RRPL 字符：{ch}")
        else:
            flush_atom()
            if stop is not None:
                raise RrplError("缺少右括号")

        if not items:
            return "0"
        if len(items) == 1:
            if ops:
                raise RrplError("RRPL 运算符缺少操作数")
            return items[0]
        if len(ops) != len(items) - 1:
            raise RrplError("RRPL packing 运算符数量不匹配")
        return ["".join(ops), *items]

    tree = parse_group()
    if pos != len(code):
        raise RrplError("RRPL 解析未完整结束")
    return tree


def to_rects(tree) -> list[tuple[float, float, float, float, str]]:
    if isinstance(tree, str):
        return [(0.0, 0.0, 1.0, 1.0, tree)]
    if not isinstance(tree, list) or len(tree) < 2:
        raise RrplError("无效 RRPL AST")
    op = str(tree[0])
    children = tree[1:]
    slots = len(op) + 1
    if slots != len(children):
        raise RrplError("无效 RRPL packing")
    horizontal = "-" in op
    result: list[tuple[float, float, float, float, str]] = []
    for idx, child in enumerate(children):
        for x0, y0, x1, y1, block in to_rects(child):
            if horizontal:
                result.append(((idx + x0) / slots, y0, (idx + x1) / slots, y1, block))
            else:
                result.append((x0, (idx + y0) / slots, x1, (idx + y1) / slots, block))
    return result


def to_lines(rects: list[tuple[float, float, float, float, str]]) -> list[tuple[float, float, float, float]]:
    lines: list[tuple[float, float, float, float]] = []
    for x0, y0, x1, y1, block in rects:
        for digit in block.replace("0", ""):
            base = _BLOCK_LINES.get(digit)
            if base is None:
                continue
            ax0, ay0, ax1, ay1 = base
            lines.append(
                (
                    (1 - ax0) * x0 + ax0 * x1,
                    (1 - ay0) * y0 + ay0 * y1,
                    (1 - ax1) * x0 + ax1 * x1,
                    (1 - ay1) * y0 + ay1 * y1,
                )
            )
    return lines


def render_svg(code: str, refs: dict[str, str], *, grid: bool = True, size: int = 512) -> tuple[str, str]:
    expanded = expand_references(code, refs)
    tree = parse(expanded)
    lines = to_lines(to_rects(tree))
    if len(lines) > 20_000:
        raise RrplError("RRPL 笔画过多")

    pad = size * 0.11
    width = size - 2 * pad
    elems: list[str] = [f'<rect width="{size}" height="{size}" fill="white"/>']
    if grid:
        g = "#e9e9e9"
        for a, b, c, d in ((0, .5, 1, .5), (.5, 0, .5, 1), (0, 0, 1, 1), (1, 0, 0, 1)):
            elems.append(
                f'<line x1="{pad+a*width:.2f}" y1="{pad+b*width:.2f}" x2="{pad+c*width:.2f}" y2="{pad+d*width:.2f}" stroke="{g}" stroke-width="2"/>'
            )
    stroke = max(3.0, size / 150)
    for a, b, c, d in lines:
        elems.append(
            f'<line x1="{pad+a*width:.2f}" y1="{pad+b*width:.2f}" x2="{pad+c*width:.2f}" y2="{pad+d*width:.2f}" stroke="black" stroke-width="{stroke:.2f}" stroke-linecap="round"/>'
        )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">' + "".join(elems) + "</svg>"
    return svg, expanded


def render_png(code: str, refs_path: Path, output_path: Path, *, grid: bool = True) -> tuple[Path, str]:
    refs = load_reference_dict(refs_path)
    svg, expanded = render_svg(code, refs, grid=grid)
    try:
        import resvg_py
    except Exception as exc:
        raise RuntimeError("RRPL 渲染需要 resvg_py") from exc
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg, zoom=2.0, background="#ffffff"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png)
    return output_path, expanded
