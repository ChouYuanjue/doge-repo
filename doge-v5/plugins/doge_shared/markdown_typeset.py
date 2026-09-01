from __future__ import annotations

import json
import re
from pathlib import Path

from .typeset import TypesetDependencyError, TypesetError, _has_cjk_font, _out_dir, _token, _typst_font_paths

_CMARKER_VERSION = "0.1.10"
_MITEX_VERSION = "0.2.7"
_CODLY_VERSION = "1.3.0"
_CJK_RE = re.compile(r"[\u2e80-\u2eff\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LANG_RE = re.compile(r"^[A-Za-z0-9_+.#-]{0,32}$")
_HIGHLIGHT_RE = re.compile(r"^(?:\d+(?:-\d+)?)(?:,\d+(?:-\d+)?)*$")


def _clean(source: str, limit: int, label: str) -> str:
    source = (source or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not source:
        raise TypesetError(f"{label} 内容不能为空")
    if "\x00" in source:
        raise TypesetError(f"{label} 内容包含 NUL 字符")
    if len(source) > limit:
        raise TypesetError(f"{label} 内容过长：最多 {limit} 个字符")
    return source


def _compile(source: str, *, fmt: str, ppi: float | None = None):
    try:
        import typst
    except Exception as exc:
        raise TypesetDependencyError("Markdown/Snippet 排版需要 typst-py") from exc
    kwargs = {"format": fmt, "root": str(Path(__file__).resolve().parent)}
    if ppi is not None:
        kwargs["ppi"] = float(ppi)
    font_paths = _typst_font_paths()
    if font_paths:
        kwargs["font_paths"] = font_paths
    try:
        return typst.compile(source.encode("utf-8"), **kwargs)
    except Exception as exc:
        msg = str(exc).strip() or type(exc).__name__
        raise TypesetError(f"排版编译失败：{msg[:1600]}") from exc


def _check_cjk(source: str) -> None:
    paths = _typst_font_paths()
    if _CJK_RE.search(source) and not _has_cjk_font(paths):
        raise TypesetDependencyError(
            "检测到中文/CJK 文本，但当前环境没有可用 CJK 字体；请安装 Noto/Source Han 等字体，或设置 DOGE_TYPST_FONT_PATHS。"
        )


def _markdown_document(markdown: str, mode: str) -> str:
    md = json.dumps(markdown, ensure_ascii=False)
    if mode == "card":
        page = '#set page(width: 15cm, height: auto, margin: (x: 22pt, y: 18pt), fill: rgb("fbfbfc"))'
        base = '#set text(size: 10.5pt)\n#set par(justify: false, leading: 0.72em, spacing: 0.72em)'
    else:
        page = '#set page(paper: "a4", margin: (x: 24mm, y: 20mm), fill: white)'
        base = '#set text(size: 10.5pt)\n#set par(justify: true, leading: 0.7em, spacing: 0.78em)'
    return f'''#import "vendor/cmarker/lib.typ": render
#import "vendor/mitex/lib.typ": mitex
{page}
{base}
#set heading(numbering: none)
#show heading.where(level: 1): it => block(above: 0.5em, below: 0.7em)[#text(size: 20pt, weight: "bold")[#it.body]]
#show heading.where(level: 2): it => block(above: 1em, below: 0.45em)[#text(size: 15pt, weight: "bold")[#it.body]]
#show quote.where(block: true): it => block(width: 100%, inset: (left: 11pt, right: 8pt, y: 6pt), stroke: (left: 2pt + rgb("8b8b92")), fill: rgb("f5f5f7"), radius: 2pt)[#it.body]
#show raw.where(block: true): it => block(width: 100%, inset: 9pt, fill: rgb("f3f4f6"), radius: 5pt, breakable: true)[#it]
#let taskmark(checked) = if checked {{ text(fill: rgb("238636"))[☑] }} else {{ text(fill: rgb("777777"))[☐] }}
#render(
  {md},
  math: mitex,
  task-list-marker: taskmark,
  raw-typst: false,
  set-document-title: false,
  smart-punctuation: true,
)
'''


def render_markdown(output_dir: Path, source: str, mode: str = "card", ppi: float = 190.0, max_pages: int = 6) -> tuple[list[Path], str]:
    source = _clean(source, 32000, "Markdown")
    mode = mode.lower()
    if mode not in {"card", "doc", "pdf"}:
        raise TypesetError("Markdown 模式支持 card / doc / pdf")
    _check_cjk(source)
    typ = _markdown_document(source, "card" if mode == "card" else "doc")
    out = _out_dir(output_dir)
    stem = _token(f"md-{mode}", source)
    if mode == "pdf":
        data = _compile(typ, fmt="pdf")
        if not isinstance(data, (bytes, bytearray)) or not bytes(data).startswith(b"%PDF"):
            raise TypesetError("Markdown 没有生成有效 PDF")
        path = out / f"markdown-{stem}.pdf"
        path.write_bytes(bytes(data))
        return [path], f"Markdown → PDF · cmarker {_CMARKER_VERSION} + MiTeX {_MITEX_VERSION}"
    data = _compile(typ, fmt="png", ppi=ppi)
    pages = data if isinstance(data, list) else [data]
    if not pages:
        raise TypesetError("Markdown 没有生成页面")
    if mode == "card" and len(pages) != 1:
        raise TypesetError("Markdown card 应生成单页；请改用 /md doc")
    if len(pages) > max_pages:
        raise TypesetError(f"Markdown 生成了 {len(pages)} 页；群聊最多发送 {max_pages} 页，请改用 /md pdf")
    paths: list[Path] = []
    try:
        from PIL import Image
        import io
    except Exception:
        Image = None
        io = None
    for i, page in enumerate(pages, 1):
        raw = bytes(page)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise TypesetError(f"Markdown 第 {i} 页不是有效 PNG")
        if Image is not None:
            with Image.open(io.BytesIO(raw)) as im:
                if im.width > 5000 or im.height > 14000:
                    raise TypesetError("Markdown 图片过大；请缩短 card 或改用 /md doc / /md pdf")
        p = out / f"markdown-{stem}-{i}.png"
        p.write_bytes(raw)
        paths.append(p)
    return paths, f"Markdown · {mode} · {len(paths)} page(s) · cmarker {_CMARKER_VERSION} + MiTeX {_MITEX_VERSION}"


def markdown_help() -> str:
    return (
        "Doge Markdown /md\n"
        "  /md card <Markdown>       自适应单页分享卡（默认）\n"
        "  /md doc <Markdown>        A4 多页 PNG，最多 6 页\n"
        "  /md pdf <Markdown>        真 PDF 文件\n"
        "支持 CommonMark、表格、引用、链接、任务列表、语法高亮代码块、脚注/引用能力和 LaTeX 数学。\n"
        "为安全起见禁止 Markdown 注入 raw Typst。保留全部空格和换行。"
    )


def _parse_highlights(spec: str, max_line: int) -> list[int]:
    if not spec:
        return []
    if not _HIGHLIGHT_RE.fullmatch(spec):
        raise TypesetError("--hl 使用如 3,5-7 的行号范围")
    result: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = map(int, part.split("-", 1))
        else:
            a = b = int(part)
        if a < 1 or b < a or b > max_line or b - a > 200:
            raise TypesetError("--hl 行号超出代码范围")
        result.update(range(a, b + 1))
    return sorted(result)


def render_snippet(output_dir: Path, code: str, *, language: str = "text", title: str = "", highlight: str = "", ppi: float = 200.0) -> tuple[Path, str]:
    code = _clean(code, 20000, "Snippet")
    language = (language or "text").lower()
    if not _LANG_RE.fullmatch(language):
        raise TypesetError("语言标识只允许字母、数字和 _+.#-")
    title = (title or "").strip()
    if len(title) > 100:
        raise TypesetError("Snippet 标题最多 100 字符")
    _check_cjk(code + title)
    lines = code.splitlines() or [code]
    highlights = _parse_highlights(highlight, len(lines))
    code_q = json.dumps(code, ensure_ascii=False)
    lang_q = json.dumps(language, ensure_ascii=False)
    title_q = json.dumps(title, ensure_ascii=False)
    hl_rows = ", ".join(f"(line: {n-1}, start: 0, end: none, fill: rgb(\"fff3bf\"))" for n in highlights)
    hl = f"#codly(highlights: ({hl_rows},))" if highlights else ""
    heading = f'#text(size: 11pt, weight: "bold")[#raw({title_q})]\n#v(6pt)' if title else ""
    src = f'''#import "vendor/codly/codly.typ": *
#set page(width: 16cm, height: auto, margin: 14pt, fill: rgb("f7f8fa"))
#set text(size: 9pt)
#show: codly-init.with()
#codly(display-icon: false, smart-indent: true, zebra-fill: rgb("fafafa"), stroke: 0.6pt + rgb("dadde3"), radius: 5pt)
{heading}
{hl}
#raw({code_q}, lang: {lang_q}, block: true)
'''
    data = _compile(src, fmt="png", ppi=ppi)
    pages = data if isinstance(data, list) else [data]
    if len(pages) != 1:
        raise TypesetError("Snippet 过长，无法作为单页代码卡；请减少代码行数")
    raw = bytes(pages[0])
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise TypesetError("Snippet 没有生成有效 PNG")
    path = _out_dir(output_dir) / f"snippet-{_token(language + title + highlight, code)}.png"
    path.write_bytes(raw)
    return path, f"Snippet · {language} · {len(lines)} lines · Codly {_CODLY_VERSION}"


def markdown_help() -> str:
    return (
        "Doge Markdown /md\n"
        "  /md card <Markdown>       自适应单页分享卡（默认）\n"
        "  /md doc <Markdown>        A4 多页 PNG，最多 6 页\n"
        "  /md pdf <Markdown>        真 PDF 文件\n"
        "支持 CommonMark、表格、引用、链接、任务列表、语法高亮代码块、脚注/引用能力和 LaTeX 数学。\n"
        "为安全起见禁止 Markdown 注入 raw Typst。保留全部空格和换行。"
    )


def snippet_help() -> str:
    return (
        "Doge Snippet /snippet\n"
        "  /snippet <lang> <code>\n"
        "  /snippet <lang> --title=标题 <code>\n"
        "  /snippet <lang> --hl=3,5-7 <code>\n"
        "适合代码、diff、shell/terminal 输出的正式展示：语法高亮、行号、智能缩进和重点行。\n"
        "例如：/snippet python --title=fib.py --hl=2-4 def fib(n): ..."
    )
