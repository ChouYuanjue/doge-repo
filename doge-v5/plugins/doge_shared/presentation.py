from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp


def platform_name(event: AstrMessageEvent) -> str:
    try:
        return str(event.get_platform_name() or "").lower()
    except Exception:
        return ""


def is_qq_official(event: AstrMessageEvent) -> bool:
    return platform_name(event) == "qq_official"


def is_onebot(event: AstrMessageEvent) -> bool:
    return platform_name(event) == "aiocqhttp"


def markdown_to_plain(text: str) -> str:
    """Conservatively remove Markdown syntax for transports that cannot render it.

    This is intentionally presentation-only: content is preserved, formatting
    markers are not.  It handles the Markdown constructs Doge and upstream APIs
    commonly emit without trying to become another Markdown renderer.
    """
    import html
    import re

    if not text:
        return ""
    text = html.unescape(str(text).replace("\r\n", "\n").replace("\r", "\n"))
    # fenced code: keep code, drop fence marker / language tag
    text = re.sub(r"(?ms)^```[^\n]*\n(.*?)^```\s*$", lambda m: m.group(1).rstrip(), text)
    text = re.sub(r"(?ms)^~~~[^\n]*\n(.*?)^~~~\s*$", lambda m: m.group(1).rstrip(), text)
    # images and links
    text = re.sub(r"!\[([^]]*)\]\([^)]*\)", lambda m: m.group(1) or "[image]", text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", lambda m: f"{m.group(1)} ({m.group(2)})", text)
    # headings / quotes / lists / task markers
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "• ", text)
    text = re.sub(r"(?m)^(\s*\d+)[.)]\s+", r"\1. ", text)
    text = re.sub(r"(?i)\[(?:x| )\]\s*", "", text)
    text = re.sub(r"(?m)^\s*(?:---+|___+|\*\*\*+)\s*$", "────────", text)
    # paired inline emphasis / code; avoid touching lone '*' used in math.
    for pat in (r"\*\*(.+?)\*\*", r"__(.+?)__", r"~~(.+?)~~", r"`([^`]+)`"):
        text = re.sub(pat, r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    # raw HTML sometimes appears in upstream Markdown.
    text = re.sub(r"<[^>]+>", "", text)
    # unescape common Markdown escapes.
    text = re.sub(r"\\([\\`*_{}\[\]()#+.!>~-])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_result(
    event: AstrMessageEvent,
    text: str,
    *,
    markdown: bool = True,
):
    """Return text using QQ Official Markdown and OneBot plain text.

    QQ Official's adapter defaults to Markdown for text, while OneBot has no
    equivalent Markdown transport.  Setting the flag explicitly keeps behavior
    stable when global AstrBot presentation settings change.
    """
    if is_onebot(event):
        text = markdown_to_plain(text)
    result = event.plain_result(text)
    result.use_markdown(bool(markdown) if is_qq_official(event) else False)
    return result


def image_result(
    event: AstrMessageEvent,
    source: str | Path,
    caption: str = "",
    *,
    remote: bool | None = None,
):
    source_s = str(source)
    if remote is None:
        remote = source_s.startswith(("http://", "https://"))
    image = Comp.Image.fromURL(source_s) if remote else Comp.Image.fromFileSystem(source_s)
    chain = [image]
    if caption:
        if is_onebot(event):
            caption = markdown_to_plain(caption)
        chain.append(Comp.Plain("\n" + caption))
    result = event.chain_result(chain)
    # QQ Official media messages are msg_type=7; its adapter drops Markdown for
    # those payloads anyway.  Marking it false makes the intended behavior clear.
    result.use_markdown(False)
    return result


def images_result(
    event: AstrMessageEvent,
    sources: Sequence[str | Path],
    caption: str = "",
):
    chain = [Comp.Image.fromFileSystem(str(p)) for p in sources]
    if caption:
        if is_onebot(event):
            caption = markdown_to_plain(caption)
        chain.append(Comp.Plain("\n" + caption))
    result = event.chain_result(chain)
    result.use_markdown(False)
    return result


def _paragraph_chunks(text: str, max_chars: int = 1000) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[i : i + max_chars])
            continue
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


def long_result(
    event: AstrMessageEvent,
    title: str,
    body: str,
    *,
    fold_threshold: int = 1600,
):
    """Present long structured output optimally on the two QQ transports.

    * QQ Official: Markdown heading/list text. The official adapter itself
      handles API fallback when Markdown is rejected.
    * NapCat/OneBot: long output becomes native merged-forward nodes, avoiding
      group spam while retaining copyable text.
    """
    if is_onebot(event):
        body = markdown_to_plain(body)
        title = markdown_to_plain(title)
    if is_onebot(event) and len(body) >= fold_threshold and event.get_group_id():
        uin = str(event.get_self_id() or "0")
        nodes = [
            Comp.Node(
                name="Doge",
                uin=uin,
                content=[Comp.Plain(chunk)],
            )
            for chunk in _paragraph_chunks(body)
        ]
        result = event.chain_result([Comp.Nodes(nodes)])
        result.use_markdown(False)
        return result

    if is_qq_official(event):
        text = f"## {title}\n\n{body}" if title else body
        return text_result(event, text, markdown=True)

    text = f"{title}\n{body}" if title else body
    return text_result(event, text, markdown=False)


def mention_result(
    event: AstrMessageEvent,
    target_id: str | None,
    text: str,
    *,
    target_label: str | None = None,
):
    """Use a real At on OneBot; use readable text on QQ Official.

    AstrBot's QQ Official outgoing generic parser currently ignores At and Reply
    components, so emitting Comp.At there would silently lose information.
    """
    if is_onebot(event):
        text = markdown_to_plain(text)
        if target_label:
            target_label = markdown_to_plain(target_label)
    if is_onebot(event) and target_id:
        result = event.chain_result([
            Comp.At(qq=str(target_id)),
            Comp.Plain("\n" + text),
        ])
        result.use_markdown(False)
        return result
    prefix = f"**{target_label}**\n\n" if target_label and is_qq_official(event) else (f"{target_label}\n" if target_label else "")
    return text_result(event, prefix + text, markdown=True)


def file_result(
    event: AstrMessageEvent,
    path: str | Path,
    *,
    name: str | None = None,
    caption: str = "",
):
    p = Path(path)
    chain = [Comp.File(name=name or p.name, file=str(p))]
    if caption:
        if is_onebot(event):
            caption = markdown_to_plain(caption)
        chain.append(Comp.Plain("\n" + caption))
    result = event.chain_result(chain)
    result.use_markdown(False)
    return result
